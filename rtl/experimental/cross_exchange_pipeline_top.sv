// ============================================================================
// File: cross_exchange_pipeline_top.sv
// Description: Multi-Venue Cross-Exchange Spatial Arbitrage Pipeline Top-Level
// Integrates:
//   - 2 independent Ingress & ITCH Parsing pipelines (Venue A & Venue B)
//   - 2 independent Level 2 Limit Order Book engines (Venue A & Venue B)
//   - Instantaneous sub-5ns combinatorial Cross-Exchange Arbiter
//   - Realized profit tracking & telemetry registers
// ============================================================================

`timescale 1ns / 1ps

module cross_exchange_pipeline_top #(
    parameter bit [63:0] TARGET_STOCK = 64'h4141504c20202020 // "AAPL    "
)(
    input  logic        clk,
    input  logic        rst_n,

    // Ingress Stream Venue A (e.g. NASDAQ ITCH 5.0)
    input  logic [63:0] s_axis_a_tdata,
    input  logic [7:0]  s_axis_a_tkeep,
    input  logic        s_axis_a_tvalid,
    input  logic        s_axis_a_tlast,
    output logic        s_axis_a_tready,

    // Ingress Stream Venue B (e.g. Cboe/BATS PITCH / secondary feed)
    input  logic [63:0] s_axis_b_tdata,
    input  logic [7:0]  s_axis_b_tkeep,
    input  logic        s_axis_b_tvalid,
    input  logic        s_axis_b_tlast,
    output logic        s_axis_b_tready,

    // Arbitrage Configuration
    input  logic        cfg_arb_enable,
    input  logic [31:0] cfg_min_profit_ticks,
    input  logic [31:0] cfg_fee_ticks,
    input  logic [31:0] cfg_max_shares_per_arb,
    input  logic [7:0]  cfg_cooldown_cycles,

    // Venue A BBO Status
    output logic        bbo_a_valid,
    output logic [31:0] bbo_a_bid_price,
    output logic [31:0] bbo_a_bid_shares,
    output logic [31:0] bbo_a_ask_price,
    output logic [31:0] bbo_a_ask_shares,

    // Venue B BBO Status
    output logic        bbo_b_valid,
    output logic [31:0] bbo_b_bid_price,
    output logic [31:0] bbo_b_bid_shares,
    output logic [31:0] bbo_b_ask_price,
    output logic [31:0] bbo_b_ask_shares,

    // Arbitrage Execution Signals
    output logic        arb_fire_strobe,
    output logic        arb_direction,
    output logic [31:0] arb_exec_shares,
    output logic [31:0] arb_buy_price,
    output logic [31:0] arb_sell_price,
    output logic [31:0] arb_profit_per_share,
    output logic [63:0] arb_total_event_profit,
    output logic [31:0] arb_event_count,
    output logic [63:0] arb_cum_profit
);

    import itch_pkg::*;
    import lob_pkg::*;

    // ------------------------------------------------------------------------
    // 1. Ingress & Parser for Venue A
    // ------------------------------------------------------------------------
    logic             parsed_valid_a;
    itch_parsed_msg_t parsed_msg_a;
    logic [31:0]      msg_count_a;

    /* verilator lint_off PINCONNECTEMPTY */
    /* verilator lint_off PINMISSING */
    ingress_pipeline_top #(
        .STRIP_ETH_IP_UDP      (1'b1),
        .USE_SPECULATIVE_PARSER(1'b1)
    ) u_ingress_a (
        .clk             (clk),
        .rst_n           (rst_n),
        .book_backpressure(1'b0),  // experimental top: not wired
        .s_axis_tdata    (s_axis_a_tdata),
        .s_axis_tkeep    (s_axis_a_tkeep),
        .s_axis_tvalid   (s_axis_a_tvalid),
        .s_axis_tlast    (s_axis_a_tlast),
        .s_axis_tready   (s_axis_a_tready),
        .parsed_msg_valid(parsed_valid_a),
        .parsed_msg      (parsed_msg_a),
        .parsed_msg_count(msg_count_a)
    );

    // ------------------------------------------------------------------------
    // 2. Limit Order Book Engine for Venue A
    // ------------------------------------------------------------------------
    lob_engine_top #(
        .TARGET_STOCK(TARGET_STOCK)
    ) u_lob_a (
        .clk                  (clk),
        .rst_n                (rst_n),
        .parsed_msg_valid     (parsed_valid_a),
        .parsed_msg           (parsed_msg_a),
        .bbo_valid            (bbo_a_valid),
        .best_bid_price       (bbo_a_bid_price),
        .best_bid_shares      (bbo_a_bid_shares),
        .best_ask_price       (bbo_a_ask_price),
        .best_ask_shares      (bbo_a_ask_shares),
        .spread               (),
        .mid_price            (),
        .bbo_updated          (),
        .top5_bid_price       (),
        .top5_bid_shares      (),
        .top5_ask_price       (),
        .top5_ask_shares      (),
        .active_order_count   (),
        .depletion_event_valid(),
        .depletion_event_side (),
        .depletion_event_price(),
        .depletion_event_shares()
    );

    // ------------------------------------------------------------------------
    // 3. Ingress & Parser for Venue B
    // ------------------------------------------------------------------------
    logic             parsed_valid_b;
    itch_parsed_msg_t parsed_msg_b;
    logic [31:0]      msg_count_b;

    ingress_pipeline_top #(
        .STRIP_ETH_IP_UDP      (1'b1),
        .USE_SPECULATIVE_PARSER(1'b1)
    ) u_ingress_b (
        .clk             (clk),
        .rst_n           (rst_n),
        .book_backpressure(1'b0),  // experimental top: not wired
        .s_axis_tdata    (s_axis_b_tdata),
        .s_axis_tkeep    (s_axis_b_tkeep),
        .s_axis_tvalid   (s_axis_b_tvalid),
        .s_axis_tlast    (s_axis_b_tlast),
        .s_axis_tready   (s_axis_b_tready),
        .parsed_msg_valid(parsed_valid_b),
        .parsed_msg      (parsed_msg_b),
        .parsed_msg_count(msg_count_b)
    );

    // ------------------------------------------------------------------------
    // 4. Limit Order Book Engine for Venue B
    // ------------------------------------------------------------------------
    lob_engine_top #(
        .TARGET_STOCK(TARGET_STOCK)
    ) u_lob_b (
        .clk                  (clk),
        .rst_n                (rst_n),
        .parsed_msg_valid     (parsed_valid_b),
        .parsed_msg           (parsed_msg_b),
        .bbo_valid            (bbo_b_valid),
        .best_bid_price       (bbo_b_bid_price),
        .best_bid_shares      (bbo_b_bid_shares),
        .best_ask_price       (bbo_b_ask_price),
        .best_ask_shares      (bbo_b_ask_shares),
        .spread               (),
        .mid_price            (),
        .bbo_updated          (),
        .top5_bid_price       (),
        .top5_bid_shares      (),
        .top5_ask_price       (),
        .top5_ask_shares      (),
        .active_order_count   (),
        .depletion_event_valid(),
        .depletion_event_side (),
        .depletion_event_price(),
        .depletion_event_shares()
    );
    /* verilator lint_on PINMISSING */
    /* verilator lint_on PINCONNECTEMPTY */

    // ------------------------------------------------------------------------
    // 5. Cross-Exchange Combinatorial Arbiter Instance
    // ------------------------------------------------------------------------
    cross_exchange_arbiter u_arbiter (
        .clk                   (clk),
        .rst_n                 (rst_n),
        .bbo_a_valid           (bbo_a_valid),
        .bbo_a_bid_price       (bbo_a_bid_price),
        .bbo_a_bid_shares      (bbo_a_bid_shares),
        .bbo_a_ask_price       (bbo_a_ask_price),
        .bbo_a_ask_shares      (bbo_a_ask_shares),
        .bbo_b_valid           (bbo_b_valid),
        .bbo_b_bid_price       (bbo_b_bid_price),
        .bbo_b_bid_shares      (bbo_b_bid_shares),
        .bbo_b_ask_price       (bbo_b_ask_price),
        .bbo_b_ask_shares      (bbo_b_ask_shares),
        .cfg_arb_enable        (cfg_arb_enable),
        .cfg_min_profit_ticks  (cfg_min_profit_ticks),
        .cfg_fee_ticks         (cfg_fee_ticks),
        .cfg_max_shares_per_arb(cfg_max_shares_per_arb),
        .cfg_cooldown_cycles   (cfg_cooldown_cycles),
        .arb_fire_strobe       (arb_fire_strobe),
        .arb_direction         (arb_direction),
        .arb_exec_shares       (arb_exec_shares),
        .arb_buy_price         (arb_buy_price),
        .arb_sell_price        (arb_sell_price),
        .arb_profit_per_share  (arb_profit_per_share),
        .arb_total_event_profit(arb_total_event_profit),
        .arb_event_count       (arb_event_count),
        .arb_cum_profit        (arb_cum_profit)
    );

endmodule
