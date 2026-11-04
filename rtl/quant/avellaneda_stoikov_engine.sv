// ============================================================================
// Module Name:   avellaneda_stoikov_engine
// Description:   High-Frequency Market Making Quoting Engine based on
//                Avellaneda & Stoikov (2008) Inventory Skew & Reservation Price.
// Standard:      SystemVerilog IEEE 1800-2017
// Pipeline:      3 clock cycles fixed deterministic latency on DSP48E2.
// ============================================================================

`timescale 1ns / 1ps

module avellaneda_stoikov_engine #(
    parameter int unsigned DEFAULT_SKEW_FACTOR = 2,
    parameter int unsigned DEFAULT_HALF_SPREAD = 100, // 0.0100 $ = 1 cent
    parameter int unsigned DEFAULT_MAX_INV     = 2000
)(
    input  logic                   clk,
    input  logic                   rst_n,

    // Market Mid-Price Feed
    input  logic                   mid_valid,
    input  logic [31:0]            mid_price,

    // Execution / Trade Fill Feedback (1-cycle inventory update)
    input  logic                   exec_valid,
    input  logic                   exec_side,     // 0 = Buy (long), 1 = Sell (short)
    input  logic [15:0]            exec_shares,

    // Dynamic Strategy Parameters (from AXI-Lite / Host)
    input  logic [15:0]            cfg_skew_factor,
    input  logic [31:0]            cfg_half_spread,
    input  logic [15:0]            cfg_max_inventory,

    // Quoting Outputs (Pipelined 3 Cycles)
    output logic                   as_valid,
    output logic [31:0]            as_reservation_price,
    output logic [31:0]            as_bid_price,
    output logic [31:0]            as_ask_price,
    output logic signed [15:0]     as_inventory,
    output logic                   as_skew_active
);

    // ------------------------------------------------------------------------
    // 1. Inventory State Tracker (1-cycle instantaneous update)
    // ------------------------------------------------------------------------
    logic signed [15:0] current_inventory;
    logic signed [17:0] max_inv_limit;
    logic signed [17:0] next_inv_buy;
    logic signed [17:0] next_inv_sell;

    assign max_inv_limit = (cfg_max_inventory != 16'h0) ? $signed({2'b00, cfg_max_inventory}) : $signed(18'(DEFAULT_MAX_INV));
    assign next_inv_buy  = $signed({{2{current_inventory[15]}}, current_inventory}) + $signed({2'b00, exec_shares});
    assign next_inv_sell = $signed({{2{current_inventory[15]}}, current_inventory}) - $signed({2'b00, exec_shares});

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            current_inventory <= 16'sd0;
        end else if (exec_valid) begin
            if (exec_side == 1'b0) begin
                // Executed Buy -> inventory increases
                if (next_inv_buy > max_inv_limit)
                    current_inventory <= max_inv_limit[15:0];
                else
                    current_inventory <= next_inv_buy[15:0];
            end else begin
                // Executed Sell -> inventory decreases
                if (next_inv_sell < -max_inv_limit)
                    current_inventory <= -max_inv_limit[15:0];
                else
                    current_inventory <= next_inv_sell[15:0];
            end
        end
    end

    // ------------------------------------------------------------------------
    // 2. Hardware Pipeline Stage 1: DSP Multiplication (q * skew_factor)
    // ------------------------------------------------------------------------
    logic signed [15:0] factor_stage1;
    logic signed [31:0] skew_offset_stage1;
    logic [31:0]        mid_price_stage1;
    logic [31:0]        half_spread_stage1;
    logic               valid_stage1;
    logic signed [15:0] inv_stage1;

    assign factor_stage1 = (cfg_skew_factor != 16'h0) ? $signed(cfg_skew_factor) : $signed(16'(DEFAULT_SKEW_FACTOR));

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            skew_offset_stage1 <= 32'sd0;
            mid_price_stage1   <= '0;
            half_spread_stage1 <= '0;
            valid_stage1       <= 1'b0;
            inv_stage1         <= 16'sd0;
        end else begin
            valid_stage1       <= mid_valid;
            mid_price_stage1   <= mid_price;
            half_spread_stage1 <= (cfg_half_spread != 0) ? cfg_half_spread : DEFAULT_HALF_SPREAD;
            inv_stage1         <= current_inventory;
            // Signed 16-bit x 16-bit multiplier inferred into DSP48E2
            skew_offset_stage1 <= current_inventory * factor_stage1;
        end
    end

    // ------------------------------------------------------------------------
    // 3. Hardware Pipeline Stage 2: Reservation Price Calculation
    //    r(s, q) = mid_price - skew_offset
    // ------------------------------------------------------------------------
    logic signed [32:0] calc_res_stage2;
    logic [31:0]        clamped_reservation_stage2;
    logic [31:0]        half_spread_stage2;
    logic               valid_stage2;
    logic signed [15:0] inv_stage2;

    assign calc_res_stage2 = $signed({1'b0, mid_price_stage1}) - $signed({{1{skew_offset_stage1[31]}}, skew_offset_stage1});

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            clamped_reservation_stage2 <= '0;
            half_spread_stage2         <= '0;
            valid_stage2               <= 1'b0;
            inv_stage2                 <= 16'sd0;
        end else begin
            valid_stage2       <= valid_stage1;
            half_spread_stage2 <= half_spread_stage1;
            inv_stage2         <= inv_stage1;

            if (calc_res_stage2 <= 33'sd0)
                clamped_reservation_stage2 <= 32'd1;
            else
                clamped_reservation_stage2 <= calc_res_stage2[31:0];
        end
    end

    // ------------------------------------------------------------------------
    // 4. Hardware Pipeline Stage 3: Optimal Dual-Sided Bid & Ask Quotes
    //    bid_quote = r - delta, ask_quote = r + delta
    // ------------------------------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            as_valid             <= 1'b0;
            as_reservation_price <= '0;
            as_bid_price         <= '0;
            as_ask_price         <= '0;
            as_inventory         <= 16'sd0;
            as_skew_active       <= 1'b0;
        end else begin
            as_valid             <= valid_stage2;
            as_reservation_price <= clamped_reservation_stage2;
            as_inventory         <= inv_stage2;
            as_skew_active       <= (inv_stage2 != 16'sd0);

            // Compute Bid Quote (clamped to at least 1 unit)
            if (clamped_reservation_stage2 > half_spread_stage2)
                as_bid_price <= clamped_reservation_stage2 - half_spread_stage2;
            else
                as_bid_price <= 32'd1;

            // Compute Ask Quote
            as_ask_price <= clamped_reservation_stage2 + half_spread_stage2;
        end
    end

endmodule
