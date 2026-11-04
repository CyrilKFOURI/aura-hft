`ifndef ITCH_LOB_PIPELINE_TOP_SV
`define ITCH_LOB_PIPELINE_TOP_SV

`timescale 1ns / 1ps

/* verilator lint_off IMPORTSTAR */
import itch_pkg::*;
import lob_pkg::*;
/* verilator lint_on IMPORTSTAR */

module itch_lob_pipeline_top #(
    parameter bit [63:0] TARGET_STOCK         = 64'h4141504c20202020, // "AAPL    "
    parameter bit        ENABLE_SYMBOL_FILTER = 1'b1,
    parameter bit        STRIP_ETH_IP_UDP     = 1'b1,
    parameter int        NUM_SETS             = 512,
    parameter int        NUM_WAYS             = 4,
    parameter int        BOOK_DEPTH           = 16
)(
    input  logic             clk,
    input  logic             rst_n,

    // Ingress AXI4-Stream (Ethernet/IP/UDP/MoldUDP64 frame)
    input  logic [63:0]      s_axis_tdata,
    input  logic [7:0]       s_axis_tkeep,
    input  logic             s_axis_tvalid,
    input  logic             s_axis_tlast,
    output logic             s_axis_tready,

    // Live L2 Limit Order Book & BBO Outputs
    output logic             bbo_valid,
    output logic [31:0]      best_bid_price,
    output logic [31:0]      best_bid_shares,
    output logic [31:0]      best_ask_price,
    output logic [31:0]      best_ask_shares,
    output logic [31:0]      spread,
    output logic [31:0]      mid_price,
    output logic             bbo_updated,

    // Top-5 Depth Arrays
    output logic [31:0]      top5_bid_price  [0:4],
    output logic [31:0]      top5_bid_shares [0:4],
    output logic [31:0]      top5_ask_price  [0:4],
    output logic [31:0]      top5_ask_shares [0:4],

    // Ingress Telemetry
    output logic [79:0]      session_name,
    output logic [63:0]      sequence_number,
    output logic             gap_detected,
    output logic [31:0]      parsed_msg_count,

    // LOB Telemetry
    output logic [4:0]       bid_depth_count,
    output logic [4:0]       ask_depth_count,
    output logic [31:0]      active_order_count,
    output logic             table_hit,
    output logic             table_miss
);

    // Ingress pipeline interconnects
    logic             parsed_msg_valid;
    itch_parsed_msg_t parsed_msg;
    logic             parser_msg_drop;
    logic [7:0]       parser_unsupported_type;
    logic [31:0]      parser_dropped_msg_count;

    logic [15:0]      unused_msg_count;
    logic             unused_pkt_valid;
    logic [63:0]      unused_gap_count;
    logic             unused_dup_detected;
    logic [63:0]      unused_expected_seq;
    logic             unused_table_full;
    logic             unused_dep_valid;
    logic             unused_dep_side;
    logic [31:0]      unused_dep_price;
    logic [31:0]      unused_dep_shares;

    // Instantiate Ingress Pipeline Top (Depacketizer + Parser)
    /* verilator lint_off PINMISSING */
    ingress_pipeline_top #(
        .STRIP_ETH_IP_UDP(STRIP_ETH_IP_UDP)
    ) u_ingress (
        .clk                  (clk),
        .rst_n                (rst_n),
        .s_axis_tdata         (s_axis_tdata),
        .s_axis_tkeep         (s_axis_tkeep),
        .s_axis_tvalid        (s_axis_tvalid),
        .s_axis_tlast         (s_axis_tlast),
        .s_axis_tready        (s_axis_tready),
        .parsed_msg_valid     (parsed_msg_valid),
        .parsed_msg           (parsed_msg),
        .session_name         (session_name),
        .sequence_number      (sequence_number),
        .message_count        (unused_msg_count),
        .pkt_header_valid     (unused_pkt_valid),
        .gap_detected         (gap_detected),
        .gap_count            (unused_gap_count),
        .duplicate_detected   (unused_dup_detected),
        .expected_seq_out     (unused_expected_seq),
        .msg_drop             (parser_msg_drop),
        .unsupported_type_code(parser_unsupported_type),
        .parsed_msg_count     (parsed_msg_count),
        .dropped_msg_count    (parser_dropped_msg_count)
    );
    /* verilator lint_on PINMISSING */

    // Instantiate Hardware Limit Order Book Engine Top
    lob_engine_top #(
        .TARGET_STOCK        (TARGET_STOCK),
        .ENABLE_SYMBOL_FILTER(ENABLE_SYMBOL_FILTER),
        .NUM_SETS            (NUM_SETS),
        .NUM_WAYS            (NUM_WAYS),
        .BOOK_DEPTH          (BOOK_DEPTH)
    ) u_lob_engine (
        .clk               (clk),
        .rst_n             (rst_n),
        .parsed_msg_valid  (parsed_msg_valid),
        .parsed_msg        (parsed_msg),
        .bbo_valid         (bbo_valid),
        .best_bid_price    (best_bid_price),
        .best_bid_shares   (best_bid_shares),
        .best_ask_price    (best_ask_price),
        .best_ask_shares   (best_ask_shares),
        .spread            (spread),
        .mid_price         (mid_price),
        .bbo_updated       (bbo_updated),
        .top5_bid_price    (top5_bid_price),
        .top5_bid_shares   (top5_bid_shares),
        .top5_ask_price    (top5_ask_price),
        .top5_ask_shares   (top5_ask_shares),
        .bid_depth_count   (bid_depth_count),
        .ask_depth_count   (ask_depth_count),
        .active_order_count(active_order_count),
        .table_hit         (table_hit),
        .table_miss        (table_miss),
        .table_full        (unused_table_full),
        .depletion_event_valid (unused_dep_valid),
        .depletion_event_side  (unused_dep_side),
        .depletion_event_price (unused_dep_price),
        .depletion_event_shares(unused_dep_shares)
    );

endmodule : itch_lob_pipeline_top

`endif // ITCH_LOB_PIPELINE_TOP_SV
