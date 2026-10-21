// ============================================================================
// Module Name:   pnl_circuit_breaker
// Description:   Real-Time Mark-to-Market PnL Tracker & Autonomous Hardware
//                Circuit Breaker conforming to SEC Rule 15c3-5 and MiFID II RTS 25.
//                Implements continuous cash flow accumulation on DSP48E2 and
//                1-cycle ($6.4 ns) transistor-level order transmission shutdown.
// Standard:      SystemVerilog IEEE 1800-2017
// Target:        AMD Kria KR260 @ 156.25 MHz (6.4 ns period)
// ============================================================================

`timescale 1ns / 1ps

module pnl_circuit_breaker #(
    parameter bit [63:0] DEFAULT_MAX_DRAWDOWN = 64'd100_000_000 // $10,000.0000 in raw 4-decimal fixed point
)(
    input  logic                   clk,
    input  logic                   rst_n,

    // Execution Fill Feedback (from OUCH / Execution receiver)
    input  logic                   exec_valid,
    input  logic                   exec_side,     // 0 = Buy ('B'), 1 = Sell ('S')
    input  logic [31:0]            exec_shares,
    input  logic [31:0]            exec_price,    // Fixed-point price (4 decimal places)

    // Market State (Mid-Price feed for continuous MtM valuation)
    input  logic                   mid_valid,
    input  logic [31:0]            mid_price,

    // Dynamic Risk Configuration (via AXI4-Lite)
    input  logic [63:0]            cfg_max_drawdown_limit,
    input  logic                   cfg_breaker_manual_reset,

    // Reflex Fast-Path Hardware Interlock
    output logic                   allow_tx,            // 1 = Normal trading, 0 = Hardware Trip Active
    output logic                   breaker_tripped,     // Latched circuit breaker state
    output logic                   breaker_trip_strobe, // 1-cycle pulse upon initial trip event

    // Real-Time PnL Telemetry Registers (to AXI4-Lite)
    output logic signed [63:0]     telemetry_cash_flow,
    output logic signed [31:0]     telemetry_inventory,
    output logic signed [63:0]     telemetry_mtm_pnl,
    output logic signed [63:0]     telemetry_peak_pnl,
    output logic [63:0]            telemetry_drawdown,
    output logic [31:0]            total_trip_events
);

    // ------------------------------------------------------------------------
    // 1. Cash Flow & Inventory State Trackers
    // ------------------------------------------------------------------------
    logic signed [63:0] cash_flow;
    logic signed [31:0] net_inventory;
    logic signed [63:0] exec_notional;

    // Multiply execution shares by price (DSP48E2 inferred)
    assign exec_notional = $signed({1'b0, exec_shares}) * $signed({1'b0, exec_price});

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cash_flow     <= 64'sd0;
            net_inventory <= 32'sd0;
        end else if (exec_valid) begin
            if (exec_side == 1'b0) begin
                // Buy fill: cash decreases by notional, inventory increases
                cash_flow     <= cash_flow - exec_notional;
                net_inventory <= net_inventory + $signed(exec_shares);
            end else begin
                // Sell fill: cash increases by notional, inventory decreases
                cash_flow     <= cash_flow + exec_notional;
                net_inventory <= net_inventory - $signed(exec_shares);
            end
        end
    end

    // ------------------------------------------------------------------------
    // 2. Mark-to-Market (MtM) Valuation & Peak PnL Tracking
    //    MtM PnL = CashFlow + (NetInventory * MidPrice)
    // ------------------------------------------------------------------------
    logic [31:0]        reg_mid_price;
    logic [31:0]        effective_mid_price;
    logic signed [63:0] current_inv_value;
    logic signed [63:0] current_mtm_pnl;
    logic signed [63:0] peak_mtm_pnl;
    logic signed [63:0] current_drawdown;
    logic [63:0]        effective_max_drawdown;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            reg_mid_price <= 32'd0;
        end else begin
            if (mid_valid && (mid_price != 32'd0)) begin
                reg_mid_price <= mid_price;
            end else if (exec_valid && (reg_mid_price == 32'd0)) begin
                // In case an execution fill occurs before any BBO mid tick, anchor to fill price
                reg_mid_price <= exec_price;
            end
        end
    end

    assign effective_mid_price = (mid_valid && (mid_price != 32'd0)) ? mid_price : reg_mid_price;
    assign current_inv_value   = net_inventory * $signed({1'b0, effective_mid_price});
    assign current_mtm_pnl     = cash_flow + current_inv_value;

    assign effective_max_drawdown = (cfg_max_drawdown_limit != 64'd0) ?
                                    cfg_max_drawdown_limit : DEFAULT_MAX_DRAWDOWN;

    logic signed [63:0] comb_drawdown;
    assign comb_drawdown = (peak_mtm_pnl > current_mtm_pnl) ? (peak_mtm_pnl - current_mtm_pnl) : 64'sd0;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            peak_mtm_pnl     <= 64'sd0;
            current_drawdown <= 64'sd0;
        end else if (cfg_breaker_manual_reset) begin
            // On authorized manual reset, reset high-water mark to current valuation
            peak_mtm_pnl     <= current_mtm_pnl;
            current_drawdown <= 64'sd0;
        end else begin
            // Update peak historical PnL
            if (current_mtm_pnl > peak_mtm_pnl) begin
                peak_mtm_pnl <= current_mtm_pnl;
            end
            current_drawdown <= comb_drawdown;
        end
    end

    // ------------------------------------------------------------------------
    // 3. Reflex Hardware Circuit Breaker (Transistor-Level Fast Interlock)
    // ------------------------------------------------------------------------
    logic latched_trip;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            latched_trip        <= 1'b0;
            breaker_trip_strobe <= 1'b0;
            total_trip_events   <= 32'd0;
        end else begin
            breaker_trip_strobe <= 1'b0;

            if (cfg_breaker_manual_reset) begin
                latched_trip <= 1'b0;
            end else if (!latched_trip && ($unsigned(comb_drawdown) > effective_max_drawdown)) begin
                // Autonomous trip: triggered in 1 cycle without CPU intervention
                latched_trip        <= 1'b1;
                breaker_trip_strobe <= 1'b1;
                total_trip_events   <= total_trip_events + 32'd1;
            end
        end
    end

    // Allow transmission only when breaker is not tripped
    assign breaker_tripped = latched_trip;
    assign allow_tx        = !latched_trip;

    // ------------------------------------------------------------------------
    // 4. Telemetry Outputs
    // ------------------------------------------------------------------------
    assign telemetry_cash_flow = cash_flow;
    assign telemetry_inventory = net_inventory;
    assign telemetry_mtm_pnl   = current_mtm_pnl;
    assign telemetry_peak_pnl  = peak_mtm_pnl;
    assign telemetry_drawdown  = $unsigned(current_drawdown);

endmodule
