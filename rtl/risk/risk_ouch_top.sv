`ifndef RISK_OUCH_TOP_SV
`define RISK_OUCH_TOP_SV

`timescale 1ns / 1ps

`include "ouch_pkg.sv"

/**
 * risk_ouch_top.sv
 *
 * Top-Level Pre-Trade Risk and OUCH 5.0 Egress Subsystem (AURA-HFT).
 * Interconnects:
 *   - Autonomous Trading Strategy Trigger (OBI & Queue Tracker driven)
 *   - pre_trade_risk: 1-cycle deterministic compliance checks
 *   - ouch_order_gen: 91-byte Ethernet/IP/UDP/OUCH Enter Order transmitter
 */

module risk_ouch_top #(
    parameter logic [63:0] DEFAULT_STOCK = 64'h4141504C20202020 // "AAPL    "
) (
    input  logic        clk,
    input  logic        rst_n,

    // Market State & Quantitative Inputs
    input  logic        obi_valid,
    input  logic signed [31:0] obi_val,         // Q1.31
    input  logic [31:0] micro_price,
    input  logic [31:0] bbo_bid_price,
    input  logic [31:0] bbo_ask_price,
    input  logic [47:0] current_timestamp,

    // Strategy Parameters & Auto-Trade Configuration
    input  logic        cfg_auto_trade_enable,
    input  logic signed [31:0] cfg_obi_buy_thresh,   // e.g. +0.40 in Q1.31
    input  logic signed [31:0] cfg_obi_sell_thresh,  // e.g. -0.40 in Q1.31
    input  logic [31:0] cfg_default_order_shares,    // e.g. 100 shares

    // Manual / Host Injected Order Intent
    input  logic        host_intent_valid,
    input  logic        host_intent_side,
    input  logic [31:0] host_intent_shares,
    input  logic [31:0] host_intent_price,
    input  logic [31:0] host_intent_token,

    // Pre-Trade Risk Limit Registers
    input  logic        cfg_kill_switch,
    input  logic        cfg_circuit_breaker_tripped,
    input  logic [31:0] cfg_max_order_shares,
    input  logic [31:0] cfg_price_collar_threshold,
    input  logic [63:0] cfg_max_notional_raw,
    input  logic [63:0] cfg_max_cum_notional_raw,

    // Risk Telemetry Outputs
    output logic        risk_approved_strobe,
    output logic        risk_rejected_strobe,
    output logic [3:0]  risk_reject_reason,
    output logic [63:0] accumulated_notional_raw,
    output logic [31:0] total_orders_approved,
    output logic [31:0] total_orders_rejected,

    // Outbound AXI4-Stream 64-bit Network Transmit Port
    output logic [63:0] m_axis_tdata,
    output logic [7:0]  m_axis_tkeep,
    output logic        m_axis_tvalid,
    output logic        m_axis_tlast,
    input  logic        m_axis_tready,

    // Transmitter Telemetry
    output logic        tx_busy,
    output logic [31:0] tx_order_count,
    output logic [47:0] tx_egress_timestamp
);

    import ouch_pkg::*;

    // -------------------------------------------------------------
    // Strategy Trigger & Order Intent Arbiter
    // -------------------------------------------------------------
    logic        strategy_intent_valid;
    logic        strategy_intent_side;
    logic [31:0] strategy_intent_shares;
    logic [31:0] strategy_intent_price;
    logic [31:0] strategy_intent_token;
    logic [31:0] auto_token_counter;

    logic        eff_intent_valid;
    logic        eff_intent_side;
    logic [31:0] eff_intent_shares;
    logic [31:0] eff_intent_price;
    logic [63:0] eff_intent_stock;
    logic [31:0] eff_intent_token;
    logic [47:0] eff_intent_timestamp;

    // Evaluate autonomous trigger condition
    always_comb begin
        strategy_intent_valid  = 1'b0;
        strategy_intent_side   = 1'b0;
        strategy_intent_shares = cfg_default_order_shares;
        strategy_intent_price  = micro_price;
        strategy_intent_token  = auto_token_counter;

        if (cfg_auto_trade_enable && obi_valid && !tx_busy) begin
            if (obi_val >= cfg_obi_buy_thresh) begin
                strategy_intent_valid = 1'b1;
                strategy_intent_side  = 1'b0; // Buy
                strategy_intent_price = bbo_bid_price;
            end else if (obi_val <= cfg_obi_sell_thresh) begin
                strategy_intent_valid = 1'b1;
                strategy_intent_side  = 1'b1; // Sell
                strategy_intent_price = bbo_ask_price;
            end
        end

        // Priority: Host manual order over autonomous strategy
        if (host_intent_valid) begin
            eff_intent_valid     = 1'b1;
            eff_intent_side      = host_intent_side;
            eff_intent_shares    = host_intent_shares;
            eff_intent_price     = host_intent_price;
            eff_intent_stock     = DEFAULT_STOCK;
            eff_intent_token     = host_intent_token;
            eff_intent_timestamp = current_timestamp;
        end else begin
            eff_intent_valid     = strategy_intent_valid;
            eff_intent_side      = strategy_intent_side;
            eff_intent_shares    = strategy_intent_shares;
            eff_intent_price     = strategy_intent_price;
            eff_intent_stock     = DEFAULT_STOCK;
            eff_intent_token     = strategy_intent_token;
            eff_intent_timestamp = current_timestamp;
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            auto_token_counter <= 32'd1000;
        end else if (strategy_intent_valid) begin
            auto_token_counter <= auto_token_counter + 1'b1;
        end
    end

    // -------------------------------------------------------------
    // Pre-Trade Risk Engine Instance
    // -------------------------------------------------------------
    logic        risk_approved;
    logic        risk_rejected;
    logic [3:0]  reject_reason;
    logic        approved_side;
    logic [31:0] approved_shares;
    logic [31:0] approved_price;
    logic [63:0] approved_stock;
    logic [31:0] approved_token;
    logic [47:0] approved_timestamp;

    assign risk_approved_strobe = risk_approved;
    assign risk_rejected_strobe = risk_rejected;
    assign risk_reject_reason   = reject_reason;

    pre_trade_risk u_risk_engine (
        .clk                       (clk),
        .rst_n                     (rst_n),
        .cfg_kill_switch           (cfg_kill_switch),
        .cfg_circuit_breaker_tripped(cfg_circuit_breaker_tripped),
        .cfg_max_order_shares      (cfg_max_order_shares),
        .cfg_price_collar_threshold(cfg_price_collar_threshold),
        .cfg_max_notional_raw      (cfg_max_notional_raw),
        .cfg_max_cum_notional_raw  (cfg_max_cum_notional_raw),
        .bbo_bid_price             (bbo_bid_price),
        .bbo_ask_price             (bbo_ask_price),
        .intent_valid              (eff_intent_valid),
        .intent_side               (eff_intent_side),
        .intent_shares             (eff_intent_shares),
        .intent_price              (eff_intent_price),
        .intent_stock              (eff_intent_stock),
        .intent_token              (eff_intent_token),
        .intent_timestamp          (eff_intent_timestamp),
        .risk_approved             (risk_approved),
        .risk_rejected             (risk_rejected),
        .reject_reason             (reject_reason),
        .out_side                  (approved_side),
        .out_shares                (approved_shares),
        .out_price                 (approved_price),
        .out_stock                 (approved_stock),
        .out_token                 (approved_token),
        .out_timestamp             (approved_timestamp),
        .accumulated_notional_raw  (accumulated_notional_raw),
        .total_orders_approved     (total_orders_approved),
        .total_orders_rejected     (total_orders_rejected)
    );

    // -------------------------------------------------------------
    // OUCH 5.0 Enter Order Packet Generator Instance
    // -------------------------------------------------------------
    ouch_order_gen u_ouch_tx (
        .clk                (clk),
        .rst_n              (rst_n),
        .order_valid        (risk_approved),
        .order_side         (approved_side),
        .order_shares       (approved_shares),
        .order_price        (approved_price),
        .order_stock        (approved_stock),
        .order_token        (approved_token),
        .order_timestamp    (approved_timestamp),
        .m_axis_tdata       (m_axis_tdata),
        .m_axis_tkeep       (m_axis_tkeep),
        .m_axis_tvalid      (m_axis_tvalid),
        .m_axis_tlast       (m_axis_tlast),
        .m_axis_tready      (m_axis_tready),
        .busy               (tx_busy),
        .tx_order_count     (tx_order_count),
        .tx_egress_timestamp(tx_egress_timestamp)
    );

endmodule : risk_ouch_top

`endif // RISK_OUCH_TOP_SV
