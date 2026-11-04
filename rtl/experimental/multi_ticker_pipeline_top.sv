// ============================================================================
// Module Name:   multi_ticker_pipeline_top
// Description:   Top-Level Multi-Ticker Concurrent Trading Pipeline (4 Symbols).
//                Interconnects:
//                  - multi_symbol_router (Ingress 16-bit stock_locate Demux)
//                  - 4 x lob_engine_top (Parallel L2 Order Books)
//                  - 4 x avellaneda_stoikov_engine (Inventory Skew & Quoting)
//                  - egress_arbiter (Round-Robin Fair Serializer)
//                  - risk_ouch_top (Pre-Trade Risk & 10G OUCH Egress)
// Standard:      SystemVerilog IEEE 1800-2017
// Target:        AMD Kria KR260 @ 156.25 MHz (6.4 ns)
// ============================================================================

`timescale 1ns / 1ps

/* verilator lint_off IMPORTSTAR */
import itch_pkg::*;
import lob_pkg::*;
/* verilator lint_on IMPORTSTAR */

module multi_ticker_pipeline_top #(
    parameter bit [15:0] LOCATE_0 = 16'd1, // AAPL
    parameter bit [15:0] LOCATE_1 = 16'd2, // MSFT
    parameter bit [15:0] LOCATE_2 = 16'd3, // NVDA
    parameter bit [15:0] LOCATE_3 = 16'd4  // TSLA
)(
    input  logic                   clk,
    input  logic                   rst_n,

    // Ingress from ITCH Parser
    input  logic                   parsed_msg_valid,
    input  itch_parsed_msg_t       parsed_msg,

    // Dynamic AXI-Lite / Host Configuration
    input  logic                   cfg_kill_switch,
    input  logic [15:0]            cfg_skew_factor,
    input  logic [31:0]            cfg_half_spread,
    input  logic [15:0]            cfg_max_inventory,
    input  logic [31:0]            cfg_max_order_shares,
    input  logic [31:0]            cfg_price_collar_threshold,
    input  logic [63:0]            cfg_max_notional_raw,
    input  logic [63:0]            cfg_max_cum_notional_raw,

    // 4 Channel BBO Outputs
    output logic [3:0]             bbo_valid,
    output logic [31:0]            best_bid_price [0:3],
    output logic [31:0]            best_ask_price [0:3],
    output logic [31:0]            mid_price      [0:3],

    // 4 Channel Avellaneda Quoting Outputs
    output logic [3:0]             as_valid,
    output logic [31:0]            as_reservation_price [0:3],
    output logic [31:0]            as_bid_price         [0:3],
    output logic [31:0]            as_ask_price         [0:3],
    output logic signed [15:0]     as_inventory         [0:3],

    // Arbiter & Egress Monitoring
    output logic [31:0]            total_arbitrated_orders,
    output logic [31:0]            collision_count,
    output logic [31:0]            routed_ingress_count,

    // Risk Telemetry
    output logic                   risk_approved_strobe,
    output logic                   risk_rejected_strobe,
    output logic [3:0]             risk_reject_reason,

    // Outbound AXI4-Stream 64-bit Network Port (OUCH 5.0)
    output logic [63:0]            m_axis_tdata,
    output logic [7:0]             m_axis_tkeep,
    output logic                   m_axis_tvalid,
    output logic                   m_axis_tlast,
    input  logic                   m_axis_tready
);

    // ------------------------------------------------------------------------
    // 1. Ingress Multi-Symbol Router
    // ------------------------------------------------------------------------
    logic [3:0]       router_chan_valid;
    itch_parsed_msg_t router_chan_msg [0:3];
    logic             unrouted_valid;
    logic [31:0]      unrouted_count;

    multi_symbol_router #(
        .LOCATE_CH0(LOCATE_0),
        .LOCATE_CH1(LOCATE_1),
        .LOCATE_CH2(LOCATE_2),
        .LOCATE_CH3(LOCATE_3)
    ) u_router (
        .clk           (clk),
        .rst_n         (rst_n),
        .in_valid      (parsed_msg_valid),
        .in_msg        (parsed_msg),
        .chan_valid    (router_chan_valid),
        .chan_msg      (router_chan_msg),
        .unrouted_valid(unrouted_valid),
        .routed_count  (routed_ingress_count),
        .unrouted_count(unrouted_count)
    );

    // ------------------------------------------------------------------------
    // 2. Parallel Order Books & Avellaneda Engines (4 Channels)
    // ------------------------------------------------------------------------
    logic [3:0]  arb_req_valid;
    logic [3:0]  arb_req_side;
    logic [31:0] arb_req_price  [0:3];
    logic [31:0] arb_req_shares [0:3];
    logic [31:0] arb_req_token  [0:3];
    logic [15:0] arb_req_locate [0:3];
    logic [3:0]  arb_grant_ack;

    logic [31:0] ch_best_bid_shares [0:3];
    logic [31:0] ch_best_ask_shares [0:3];
    logic [31:0] ch_spread          [0:3];
    logic [3:0]  ch_bbo_updated;

    // Fixed locate codes per channel for order routing
    localparam bit [15:0] CH_LOCATES [0:3] = '{LOCATE_0, LOCATE_1, LOCATE_2, LOCATE_3};

    genvar i;
    generate
        for (i = 0; i < 4; i++) begin : gen_symbol_channels
            // L2 Limit Order Book instance
            lob_engine_top #(
                .ENABLE_SYMBOL_FILTER(1'b0)
            ) u_lob (
                .clk                  (clk),
                .rst_n                (rst_n),
                .parsed_msg_valid     (router_chan_valid[i]),
                .parsed_msg           (router_chan_msg[i]),
                .bbo_valid            (bbo_valid[i]),
                .best_bid_price       (best_bid_price[i]),
                .best_bid_shares      (ch_best_bid_shares[i]),
                .best_ask_price       (best_ask_price[i]),
                .best_ask_shares      (ch_best_ask_shares[i]),
                .spread               (ch_spread[i]),
                .mid_price            (mid_price[i]),
                .bbo_updated          (ch_bbo_updated[i]),
                .top5_bid_price       (),
                .top5_bid_shares      (),
                .top5_ask_price       (),
                .top5_ask_shares      (),
                .bid_depth_count      (),
                .ask_depth_count      (),
                .active_order_count   (),
                .table_hit            (),
                .table_miss           (),
                .table_full           (),
                .req_almost_full      (),  // shared ingress: no per-book backpressure (experimental)
                .depletion_event_valid(),
                .depletion_event_side (),
                .depletion_event_price(),
                .depletion_event_shares()
            );

            // Avellaneda-Stoikov Market Making Engine instance
            avellaneda_stoikov_engine u_as (
                .clk                  (clk),
                .rst_n                (rst_n),
                .mid_valid            (bbo_valid[i]),
                .mid_price            (mid_price[i]),
                .exec_valid           (1'b0), // Execution feedback can be routed via OUCH Exec
                .exec_side            (1'b0),
                .exec_shares          (16'd0),
                .cfg_skew_factor      (cfg_skew_factor),
                .cfg_half_spread      (cfg_half_spread),
                .cfg_max_inventory    (cfg_max_inventory),
                .as_valid             (as_valid[i]),
                .as_reservation_price (as_reservation_price[i]),
                .as_bid_price         (as_bid_price[i]),
                .as_ask_price         (as_ask_price[i]),
                .as_inventory         (as_inventory[i]),
                .as_skew_active       ()
            );

            // Quoting Order Generation Logic (trigger order intent on updated AS quotes)
            always_ff @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    arb_req_valid[i]  <= 1'b0;
                    arb_req_side[i]   <= 1'b0;
                    arb_req_price[i]  <= 32'd0;
                    arb_req_shares[i] <= 32'd0;
                    arb_req_token[i]  <= 32'd0;
                    arb_req_locate[i] <= CH_LOCATES[i];
                end else begin
                    if (arb_grant_ack[i]) begin
                        arb_req_valid[i] <= 1'b0;
                    end else if (as_valid[i] && !cfg_kill_switch) begin
                        arb_req_valid[i]  <= 1'b1;
                        arb_req_side[i]   <= 1'b0; // Place bid quote
                        arb_req_price[i]  <= as_bid_price[i];
                        arb_req_shares[i] <= 32'd100;
                        arb_req_token[i]  <= 32'hA000_0000 | 32'(i);
                        arb_req_locate[i] <= CH_LOCATES[i];
                    end
                end
            end
        end
    endgenerate

    // ------------------------------------------------------------------------
    // 3. Egress Round-Robin Arbiter
    // ------------------------------------------------------------------------
    logic        arb_out_valid;
    logic [1:0]  arb_out_channel;
    logic        arb_out_side;
    logic [31:0] arb_out_price;
    logic [31:0] arb_out_shares;
    logic [31:0] arb_out_token;
    logic [15:0] arb_out_locate;

    egress_arbiter u_arbiter (
        .clk                    (clk),
        .rst_n                  (rst_n),
        .req_valid              (arb_req_valid),
        .req_side               (arb_req_side),
        .req_price              (arb_req_price),
        .req_shares             (arb_req_shares),
        .req_token              (arb_req_token),
        .req_locate             (arb_req_locate),
        .grant_ack              (arb_grant_ack),
        .out_valid              (arb_out_valid),
        .out_channel            (arb_out_channel),
        .out_side               (arb_out_side),
        .out_price              (arb_out_price),
        .out_shares             (arb_out_shares),
        .out_token              (arb_out_token),
        .out_locate             (arb_out_locate),
        .total_arbitrated_orders(total_arbitrated_orders),
        .collision_count        (collision_count)
    );

    // ------------------------------------------------------------------------
    // 4. Pre-Trade Risk Checks & OUCH 5.0 Egress Subsystem
    // ------------------------------------------------------------------------
    risk_ouch_top u_risk_ouch (
        .clk                       (clk),
        .rst_n                     (rst_n),
        .bbo_valid                 (1'b0),
        .bbo_bid_shares            (32'd0),
        .bbo_ask_shares            (32'd0),
        .bbo_bid_price             (arb_out_price),
        .bbo_ask_price             (arb_out_price + 32'd200),
        .current_timestamp         (48'd0),
        .cfg_auto_trade_enable     (1'b0),
        .cfg_obi_buy_thresh        (32'sd0),
        .cfg_obi_sell_thresh       (32'sd0),
        .cfg_default_order_shares  (32'd100),
        .host_intent_valid         (arb_out_valid),
        .host_intent_side          (arb_out_side),
        .host_intent_shares        (arb_out_shares),
        .host_intent_price         (arb_out_price),
        .host_intent_token         (arb_out_token),
        .cfg_kill_switch           (cfg_kill_switch),
        .cfg_circuit_breaker_tripped(1'b0),
        .cfg_max_order_shares      (cfg_max_order_shares),
        .cfg_price_collar_threshold(cfg_price_collar_threshold),
        .cfg_max_notional_raw      (cfg_max_notional_raw),
        .cfg_max_cum_notional_raw  (cfg_max_cum_notional_raw),
        .risk_approved_strobe      (risk_approved_strobe),
        .risk_rejected_strobe      (risk_rejected_strobe),
        .risk_reject_reason        (risk_reject_reason),
        .accumulated_notional_raw  (),
        .total_orders_approved     (),
        .total_orders_rejected     (),
        .m_axis_tdata              (m_axis_tdata),
        .m_axis_tkeep              (m_axis_tkeep),
        .m_axis_tvalid             (m_axis_tvalid),
        .m_axis_tlast              (m_axis_tlast),
        .m_axis_tready             (m_axis_tready),
        .tx_busy                   (),
        .tx_order_count            (),
        .tx_egress_timestamp       ()
    );

endmodule
