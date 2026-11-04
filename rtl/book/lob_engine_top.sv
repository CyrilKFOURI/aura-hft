`ifndef LOB_ENGINE_TOP_SV
`define LOB_ENGINE_TOP_SV

`timescale 1ns / 1ps

/* verilator lint_off IMPORTSTAR */
import itch_pkg::*;
import lob_pkg::*;
/* verilator lint_on IMPORTSTAR */

module lob_engine_top #(
    parameter bit [63:0] TARGET_STOCK         = 64'h4141504c20202020, // "AAPL    "
    parameter bit        ENABLE_SYMBOL_FILTER = 1'b1,
    parameter int        NUM_SETS             = 512,
    parameter int        NUM_WAYS             = 4,
    parameter int        BOOK_DEPTH            = 16
)(
    input  logic             clk,
    input  logic             rst_n,

    // Ingress from ITCH Parser
    input  logic             parsed_msg_valid,
    input  itch_parsed_msg_t parsed_msg,

    // BBO & Quant Output Interface
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

    // Telemetry & Monitoring
    output logic [4:0]       bid_depth_count,
    output logic [4:0]       ask_depth_count,
    output logic [31:0]      active_order_count,
    output logic             table_hit,
    output logic             table_miss,
    output logic             table_full,

    // Depletion Event Outputs for Queue Tracker
    output logic             depletion_event_valid,
    output logic             depletion_event_side,
    output logic [31:0]      depletion_event_price,
    output logic [31:0]      depletion_event_shares
);

    // Map ITCH message to Hash Table request
    logic        ht_req_valid;
    logic [2:0]  ht_req_op;
    logic [63:0] ht_req_order_ref;
    logic [63:0] ht_req_orig_ref;
    logic        ht_req_side;
    logic [31:0] ht_req_shares;
    logic [31:0] ht_req_price;

    always_comb begin
        ht_req_valid     = 1'b0;
        ht_req_op        = 3'd0;
        ht_req_order_ref = parsed_msg.order_ref;
        ht_req_orig_ref  = parsed_msg.orig_order_ref;
        ht_req_side      = parsed_msg.side;
        ht_req_shares    = parsed_msg.shares;
        ht_req_price     = parsed_msg.price;

        if (parsed_msg_valid) begin
            case (parsed_msg.msg_type)
                ITCH_MSG_ADD, ITCH_MSG_ADD_MPID: begin // 'A', 'F'
                    if (!ENABLE_SYMBOL_FILTER || parsed_msg.stock == TARGET_STOCK) begin
                        ht_req_valid = 1'b1;
                        ht_req_op    = 3'd1; // Insert
                    end
                end

                ITCH_MSG_EXEC, ITCH_MSG_EXEC_PRICE: begin // 'E', 'C'
                    ht_req_valid = 1'b1;
                    ht_req_op    = 3'd2; // Exec
                end

                ITCH_MSG_CANCEL: begin // 'X'
                    ht_req_valid = 1'b1;
                    ht_req_op    = 3'd3; // Cancel
                end

                ITCH_MSG_DELETE: begin // 'D'
                    ht_req_valid = 1'b1;
                    ht_req_op    = 3'd4; // Delete
                end

                ITCH_MSG_REPLACE: begin // 'U'
                    ht_req_valid     = 1'b1;
                    ht_req_op        = 3'd5; // Replace
                    ht_req_order_ref = parsed_msg.new_order_ref;
                    ht_req_orig_ref  = parsed_msg.orig_order_ref;
                end

                default: ;
            endcase
        end
    end

    // Interconnect between Hash Table and Price Ladder
    logic        ht_out_valid;
    lob_cmd_e    ht_out_cmd;
    logic        ht_out_side;
    logic [31:0] ht_out_price;
    logic [31:0] ht_out_shares;
    logic [31:0] ht_out_old_price;
    logic [31:0] ht_out_old_shares;

    // Instantiate Order Hash Table
    order_hash_table #(
        .NUM_SETS(NUM_SETS),
        .NUM_WAYS(NUM_WAYS)
    ) u_hash_table (
        .clk               (clk),
        .rst_n             (rst_n),
        .req_valid         (ht_req_valid),
        .req_op            (ht_req_op),
        .req_order_ref     (ht_req_order_ref),
        .req_orig_ref      (ht_req_orig_ref),
        .req_side          (ht_req_side),
        .req_shares        (ht_req_shares),
        .req_price         (ht_req_price),
        .out_valid         (ht_out_valid),
        .out_cmd           (ht_out_cmd),
        .out_side          (ht_out_side),
        .out_price         (ht_out_price),
        .out_shares        (ht_out_shares),
        .out_old_price     (ht_out_old_price),
        .out_old_shares    (ht_out_old_shares),
        .table_hit         (table_hit),
        .table_miss        (table_miss),
        .table_full        (table_full),
        .active_order_count(active_order_count)
    );

    // Drive depletion events for queue tracking
    assign depletion_event_valid  = ht_out_valid && (ht_out_cmd == LOB_CMD_SUB || ht_out_cmd == LOB_CMD_REPLACE);
    assign depletion_event_side   = ht_out_side;
    assign depletion_event_price  = (ht_out_cmd == LOB_CMD_REPLACE) ? ht_out_old_price : ht_out_price;
    assign depletion_event_shares = (ht_out_cmd == LOB_CMD_REPLACE) ? ht_out_old_shares : ht_out_shares;

    // Interconnect between Price Ladder and Top-of-Book Cache
    price_level_t ladder_bid_levels [0:BOOK_DEPTH-1];
    price_level_t ladder_ask_levels [0:BOOK_DEPTH-1];
    logic [4:0]   ladder_bid_count;
    logic [4:0]   ladder_ask_count;
    logic         ladder_book_updated;
    logic         ladder_busy;

    assign bid_depth_count = ladder_bid_count;
    assign ask_depth_count = ladder_ask_count;

    // Instantiate Price Ladder
    price_ladder_l2 #(
        .DEPTH(BOOK_DEPTH)
    ) u_price_ladder (
        .clk           (clk),
        .rst_n         (rst_n),
        .cmd_valid     (ht_out_valid),
        .cmd_op        (ht_out_cmd),
        .cmd_side      (ht_out_side),
        .cmd_price     (ht_out_price),
        .cmd_shares    (ht_out_shares),
        .cmd_old_price (ht_out_old_price),
        .cmd_old_shares(ht_out_old_shares),
        .bid_levels    (ladder_bid_levels),
        .ask_levels    (ladder_ask_levels),
        .bid_count     (ladder_bid_count),
        .ask_count     (ladder_ask_count),
        .book_updated  (ladder_book_updated),
        .busy          (ladder_busy)
    );

    // Instantiate Top-of-Book Cache
    top_of_book_cache #(
        .DEPTH(BOOK_DEPTH)
    ) u_top_of_book (
        .clk            (clk),
        .rst_n          (rst_n),
        .bid_levels     (ladder_bid_levels),
        .ask_levels     (ladder_ask_levels),
        .bid_count      (ladder_bid_count),
        .ask_count      (ladder_ask_count),
        .book_updated   (ladder_book_updated),
        .bbo_valid      (bbo_valid),
        .best_bid_price (best_bid_price),
        .best_bid_shares(best_bid_shares),
        .best_ask_price (best_ask_price),
        .best_ask_shares(best_ask_shares),
        .spread         (spread),
        .mid_price      (mid_price),
        .bbo_updated    (bbo_updated),
        .top5_bid_price (top5_bid_price),
        .top5_bid_shares(top5_bid_shares),
        .top5_ask_price (top5_ask_price),
        .top5_ask_shares(top5_ask_shares)
    );

endmodule : lob_engine_top

`endif // LOB_ENGINE_TOP_SV
