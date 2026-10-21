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
    parameter int        NUM_SETS             = 8192,  // per bank (two banks, two-choice hashing)
    parameter int        NUM_WAYS             = 4,
    parameter int        BOOK_DEPTH            = 16,   // legacy, unused: full depth is now kept
    parameter logic [31:0] PRICE_BASE         = 32'd0  // raw price of tick 0 of the depth window
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
    output logic             req_almost_full,   // backpressure to the ingress (P3b)

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

    // ------------------------------------------------------------------
    // Request FIFO: the full-depth book is multi-cycle, the parser is not.
    // ------------------------------------------------------------------
    localparam int FIFO_BITS = 6;
    typedef struct packed {
        logic [2:0]  op;
        logic [63:0] order_ref;
        logic [63:0] orig_ref;
        logic        side;
        logic [31:0] shares;
        logic [31:0] price;
    } book_req_t;

    book_req_t             fifo_mem [0:(1<<FIFO_BITS)-1];
    logic [FIFO_BITS:0]    fifo_wr, fifo_rd;
    logic                  fifo_empty, fifo_full;
    book_req_t             fifo_head;
    logic                  store_req_ready;
    logic [31:0]           fifo_overflow_count;

    assign fifo_empty = (fifo_wr == fifo_rd);
    assign fifo_full  = (fifo_wr[FIFO_BITS] != fifo_rd[FIFO_BITS]) &&
                        (fifo_wr[FIFO_BITS-1:0] == fifo_rd[FIFO_BITS-1:0]);
    assign fifo_head  = fifo_mem[fifo_rd[FIFO_BITS-1:0]];
    // Stall the ingress with room to spare: when the ingress stops, the parser
    // can still drain its 64-byte window (<= 3 messages) plus one in flight.
    localparam int FIFO_STALL_LEVEL = (1 << FIFO_BITS) - 8;
    logic [FIFO_BITS:0] fifo_level;
    assign fifo_level      = fifo_wr - fifo_rd;
    assign req_almost_full = (32'(fifo_level) >= FIFO_STALL_LEVEL);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            fifo_wr             <= '0;
            fifo_rd             <= '0;
            fifo_overflow_count <= '0;
        end else begin
            if (ht_req_valid) begin
                if (!fifo_full) begin
                    fifo_mem[fifo_wr[FIFO_BITS-1:0]] <= '{op: ht_req_op, order_ref: ht_req_order_ref,
                        orig_ref: ht_req_orig_ref, side: ht_req_side, shares: ht_req_shares, price: ht_req_price};
                    fifo_wr <= fifo_wr + 1'b1;
                end else begin
                    fifo_overflow_count <= fifo_overflow_count + 1'b1;
                end
            end
            if (!fifo_empty && store_req_ready) fifo_rd <= fifo_rd + 1'b1;
        end
    end

    // ------------------------------------------------------------------
    // Live-order table (two-choice hashing + stash)
    // ------------------------------------------------------------------
    logic        ht_out_valid;
    lob_cmd_e    ht_out_cmd;
    logic        ht_out_side;
    logic [31:0] ht_out_price;
    logic [31:0] ht_out_shares;
    logic [31:0] ht_out_old_price;
    logic [31:0] ht_out_old_shares;
    logic        book_ready;
    logic [$clog2(17)-1:0] stash_count;
    logic [31:0] store_overflow_count;

    order_store #(
        .SET_BITS($clog2(NUM_SETS)),
        .NUM_WAYS(NUM_WAYS)
    ) u_store (
        .clk               (clk),
        .rst_n             (rst_n),
        .req_valid         (!fifo_empty),
        .req_ready         (store_req_ready),
        .req_op            (fifo_head.op),
        .req_order_ref     (fifo_head.order_ref),
        .req_orig_ref      (fifo_head.orig_ref),
        .req_side          (fifo_head.side),
        .req_shares        (fifo_head.shares),
        .req_price         (fifo_head.price),
        .out_ready         (book_ready),
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
        .active_order_count(active_order_count),
        .stash_count       (stash_count),
        .overflow_count    (store_overflow_count)
    );

    // Drive depletion events for queue tracking
    assign depletion_event_valid  = ht_out_valid && (ht_out_cmd == LOB_CMD_SUB || ht_out_cmd == LOB_CMD_REPLACE);
    assign depletion_event_side   = ht_out_side;
    assign depletion_event_price  = (ht_out_cmd == LOB_CMD_REPLACE) ? ht_out_old_price : ht_out_price;
    assign depletion_event_shares = (ht_out_cmd == LOB_CMD_REPLACE) ? ht_out_old_shares : ht_out_shares;

    // ------------------------------------------------------------------
    // Full-depth price book with exact top-5 extraction
    // ------------------------------------------------------------------
    price_level_t top_bid_levels [0:TOP_N-1];
    price_level_t top_ask_levels [0:TOP_N-1];
    logic [15:0]  bid_level_count, ask_level_count;
    logic         book_updated;
    logic [31:0]  out_of_window_orders;

    depth_book #(
        .PRICE_BASE(PRICE_BASE),
        .TOP_LEVELS(TOP_N)
    ) u_depth_book (
        .clk                 (clk),
        .rst_n               (rst_n),
        .cmd_valid           (ht_out_valid),
        .cmd_ready           (book_ready),
        .cmd_op              (ht_out_cmd),
        .cmd_side            (ht_out_side),
        .cmd_price           (ht_out_price),
        .cmd_shares          (ht_out_shares),
        .cmd_old_price       (ht_out_old_price),
        .cmd_old_shares      (ht_out_old_shares),
        .bid_levels          (top_bid_levels),
        .ask_levels          (top_ask_levels),
        .bid_level_count     (bid_level_count),
        .ask_level_count     (ask_level_count),
        .book_updated        (book_updated),
        .out_of_window_orders(out_of_window_orders)
    );

    assign bid_depth_count = (bid_level_count > 16'd31) ? 5'd31 : bid_level_count[4:0];
    assign ask_depth_count = (ask_level_count > 16'd31) ? 5'd31 : ask_level_count[4:0];

    top_of_book_cache #(
        .DEPTH(TOP_N)
    ) u_top_of_book (
        .clk            (clk),
        .rst_n          (rst_n),
        .bid_levels     (top_bid_levels),
        .ask_levels     (top_ask_levels),
        .bid_count      (bid_depth_count),
        .ask_count      (ask_depth_count),
        .book_updated   (book_updated),
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
