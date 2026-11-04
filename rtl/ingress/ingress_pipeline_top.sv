`ifndef INGRESS_PIPELINE_TOP_SV
`define INGRESS_PIPELINE_TOP_SV

`timescale 1ns / 1ps

/* verilator lint_off IMPORTSTAR */
import itch_pkg::*;
/* verilator lint_on IMPORTSTAR */

module ingress_pipeline_top #(
    parameter bit STRIP_ETH_IP_UDP       = 1'b1,
    parameter bit USE_SPECULATIVE_PARSER = 1'b1
)(
    input  logic             clk,
    input  logic             rst_n,

    // Backpressure from the order book request FIFO (P3b): stalls the
    // depacketizer -> parser stream, which propagates to s_axis_tready.
    input  logic             book_backpressure,

    // Ingress AXI4-Stream (Ethernet/IP/UDP/MoldUDP64 frame)
    input  logic [63:0]      s_axis_tdata,
    input  logic [7:0]       s_axis_tkeep,
    input  logic             s_axis_tvalid,
    input  logic             s_axis_tlast,
    output logic             s_axis_tready,

    // Parsed ITCH Message Output Interface
    output logic             parsed_msg_valid,
    output itch_parsed_msg_t parsed_msg,

    // Discrete output ports for testbench/waveform inspection
    output logic [7:0]       out_msg_type,
    output logic [15:0]      out_stock_locate,
    output logic [15:0]      out_tracking_num,
    output logic [47:0]      out_timestamp,
    output logic [63:0]      out_order_ref,
    output logic             out_side,
    output logic [31:0]      out_shares,
    output logic [63:0]      out_stock,
    output logic [31:0]      out_price,
    output logic [63:0]      out_match_number,
    output logic [7:0]       out_printable,
    output logic [63:0]      out_orig_order_ref,
    output logic [63:0]      out_new_order_ref,
    output logic [31:0]      out_mpid,

    // MoldUDP64 Telemetry & Gap Monitoring
    output logic [79:0]      session_name,
    output logic [63:0]      sequence_number,
    output logic [15:0]      message_count,
    output logic             pkt_header_valid,
    output logic             gap_detected,
    output logic [63:0]      gap_count,
    output logic             duplicate_detected,
    output logic [63:0]      expected_seq_out,

    // Parser Telemetry
    output logic             msg_drop,
    output logic [7:0]       unsupported_type_code,
    output logic [31:0]      parsed_msg_count,
    output logic [31:0]      dropped_msg_count
);

    // Assign discrete output ports
    assign out_msg_type       = parsed_msg.msg_type;
    assign out_stock_locate   = parsed_msg.stock_locate;
    assign out_tracking_num   = parsed_msg.tracking_num;
    assign out_timestamp      = parsed_msg.timestamp;
    assign out_order_ref      = parsed_msg.order_ref;
    assign out_side           = parsed_msg.side;
    assign out_shares         = parsed_msg.shares;
    assign out_stock          = parsed_msg.stock;
    assign out_price          = parsed_msg.price;
    assign out_match_number   = parsed_msg.match_number;
    assign out_printable      = parsed_msg.printable;
    assign out_orig_order_ref = parsed_msg.orig_order_ref;
    assign out_new_order_ref  = parsed_msg.new_order_ref;
    assign out_mpid           = parsed_msg.mpid;

    // Interconnect between depacketizer and parser
    logic [63:0] mold_axis_tdata;
    logic [7:0]  mold_axis_tkeep;
    logic        mold_axis_tvalid;
    logic        mold_axis_tlast;
    logic        mold_axis_tready;
    logic        parser_axis_tvalid;
    logic        parser_axis_tready;
    logic [31:0] parser_truncated_count;

    assign parser_axis_tvalid = mold_axis_tvalid && !book_backpressure;
    assign mold_axis_tready   = parser_axis_tready && !book_backpressure;

    // Instantiate MoldUDP64 Depacketizer
    moldudp64_depacketizer #(
        .STRIP_ETH_IP_UDP(STRIP_ETH_IP_UDP)
    ) u_depacketizer (
        .clk               (clk),
        .rst_n             (rst_n),
        .s_axis_tdata      (s_axis_tdata),
        .s_axis_tkeep      (s_axis_tkeep),
        .s_axis_tvalid     (s_axis_tvalid),
        .s_axis_tlast      (s_axis_tlast),
        .s_axis_tready     (s_axis_tready),
        .m_axis_tdata      (mold_axis_tdata),
        .m_axis_tkeep      (mold_axis_tkeep),
        .m_axis_tvalid     (mold_axis_tvalid),
        .m_axis_tlast      (mold_axis_tlast),
        .m_axis_tready     (mold_axis_tready),
        .session_name      (session_name),
        .sequence_number   (sequence_number),
        .message_count     (message_count),
        .pkt_header_valid  (pkt_header_valid),
        .gap_detected      (gap_detected),
        .gap_count         (gap_count),
        .duplicate_detected(duplicate_detected),
        .expected_seq_out  (expected_seq_out)
    );

    // Instantiate ITCH 5.0 Streaming Parser (Speculative or Classic)
    generate
        if (USE_SPECULATIVE_PARSER) begin : gen_speculative_parser
            speculative_itch_parser u_itch_parser (
                .clk                  (clk),
                .rst_n                (rst_n),
                .s_axis_tdata         (mold_axis_tdata),
                .s_axis_tkeep         (mold_axis_tkeep),
                .s_axis_tvalid        (parser_axis_tvalid),
                .s_axis_tlast         (mold_axis_tlast),
                .s_axis_tready        (parser_axis_tready),
                .parsed_msg_valid     (parsed_msg_valid),
                .parsed_msg           (parsed_msg),
                .msg_drop             (msg_drop),
                .unsupported_type_code(unsupported_type_code),
                .parsed_msg_count     (parsed_msg_count),
                .dropped_msg_count    (dropped_msg_count),
                .truncated_msg_count  (parser_truncated_count)
            );
        end else begin : gen_classic_parser
            itch_parser_fsm u_itch_parser (
                .clk                  (clk),
                .rst_n                (rst_n),
                .s_axis_tdata         (mold_axis_tdata),
                .s_axis_tkeep         (mold_axis_tkeep),
                .s_axis_tvalid        (parser_axis_tvalid),
                .s_axis_tlast         (mold_axis_tlast),
                .s_axis_tready        (parser_axis_tready),
                .parsed_msg_valid     (parsed_msg_valid),
                .parsed_msg           (parsed_msg),
                .msg_drop             (msg_drop),
                .unsupported_type_code(unsupported_type_code),
                .parsed_msg_count     (parsed_msg_count),
                .dropped_msg_count    (dropped_msg_count)
            );
            assign parser_truncated_count = 32'd0; // classic FSM: no frame-boundary recovery
        end
    endgenerate

endmodule : ingress_pipeline_top

`endif // INGRESS_PIPELINE_TOP_SV
