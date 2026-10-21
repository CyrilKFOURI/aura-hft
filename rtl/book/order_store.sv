`ifndef ORDER_STORE_SV
`define ORDER_STORE_SV

`timescale 1ns / 1ps

/* verilator lint_off IMPORTSTAR */
import lob_pkg::*;
/* verilator lint_on IMPORTSTAR */

// Live-order table sized for real markets (step P4).
//
// Two-choice hashing: each order reference has one candidate set in each of
// two banks (independent multiplicative hashes, *high* product bits) and is
// inserted in the less loaded one (tie -> bank0). A small fully-associative
// stash absorbs the rare case where both sets are full. Sized on real NASDAQ
// data (01/30/2019, AAPL up to 39,964 live orders): 2 x 8192 sets x 4 ways
// needed at most 6 stash entries.
//
// Step P5a (synthesizable memories): each bank is a set-indexed RAM whose
// word holds the NUM_WAYS entries of a set, with a registered read
// (1-cycle latency) and one write port, so it maps to URAM/BRAM:
//   IDLE  : accept a request, hash its key, issue both set reads;
//   PROC  : compare / modify the read sets, write the set word back;
//   RD2   : (REPLACE) issue the reads for the new reference's sets;
//   PROC2 : (REPLACE) insert the new reference.
// A set write always lands before the next read is issued, so no bypass is
// needed. The stash stays in registers.
//
// A request is accepted only in IDLE, when `out_ready` is high and no
// response pulse is in flight; the downstream depth book is multi-cycle.
module order_store #(
    parameter int SET_BITS = 13,
    parameter int NUM_WAYS = 4,
    parameter int STASH    = 16
)(
    input  logic             clk,
    input  logic             rst_n,

    // Request (op: 1 Add, 2 Exec, 3 Cancel, 4 Delete, 5 Replace)
    input  logic             req_valid,
    output logic             req_ready,
    input  logic [2:0]       req_op,
    input  logic [63:0]      req_order_ref,
    input  logic [63:0]      req_orig_ref,
    input  logic             req_side,
    input  logic [31:0]      req_shares,
    input  logic [31:0]      req_price,

    // Command to the depth book (one-cycle pulse)
    input  logic             out_ready,
    output logic             out_valid,
    output lob_cmd_e         out_cmd,
    output logic             out_side,
    output logic [31:0]      out_price,
    output logic [31:0]      out_shares,
    output logic [31:0]      out_old_price,
    output logic [31:0]      out_old_shares,

    // Telemetry
    output logic             table_hit,
    output logic             table_miss,
    output logic             table_full,      // pulse: order could not be stored
    output logic [31:0]      active_order_count,
    output logic [$clog2(STASH+1)-1:0] stash_count,
    output logic [31:0]      overflow_count
);

    localparam int NUM_SETS = 1 << SET_BITS;
    localparam int WAY_BITS = $clog2(NUM_WAYS);
    localparam int STB      = $clog2(STASH);
    localparam logic [63:0] HASH_M0 = 64'h9e3779b97f4a7c15;
    localparam logic [63:0] HASH_M1 = 64'hc2b2ae3d27d4eb4f;

    // Table entry with a reset epoch: an entry is live only if its epoch
    // matches the current one, so a reset invalidates the whole table in
    // O(1) instead of a 65,536-cycle scrub. (Epoch wrap after 256 resets
    // would need a background scrub; not an issue for one session per day.)
    typedef struct packed {
        logic        valid;
        logic [7:0]  epoch;
        logic [63:0] order_ref;
        logic [31:0] price;
        logic [31:0] shares;
        logic        side;
    } store_entry_t;

    typedef store_entry_t [NUM_WAYS-1:0] store_set_t;   // one RAM word

    logic [7:0] epoch;
    logic       armed, armed_d;   // async-reset flags: low during reset

    initial epoch = 8'd1;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            armed   <= 1'b0;
            armed_d <= 1'b0;
        end else begin
            armed   <= 1'b1;
            armed_d <= armed;
        end
    end

    // New epoch on the first cycle after each reset release (not itself reset).
    always_ff @(posedge clk) begin
        if (armed && !armed_d) epoch <= epoch + 8'd1;
    end

    function automatic logic live(input store_entry_t e);
        return e.valid && (e.epoch == epoch);
    endfunction

    function automatic logic [SET_BITS-1:0] hash0(input logic [63:0] key);
        logic [63:0] p;
        p = key * HASH_M0;
        return p[63 -: SET_BITS];
    endfunction

    function automatic logic [SET_BITS-1:0] hash1(input logic [63:0] key);
        logic [63:0] p;
        p = key * HASH_M1;
        return p[63 -: SET_BITS];
    endfunction

    // ------------------------------------------------------------------ memories
    store_set_t   bank0 [0:NUM_SETS-1];
    store_set_t   bank1 [0:NUM_SETS-1];
    store_entry_t stash [0:STASH-1];

    logic                re;
    logic [SET_BITS-1:0] raddr0, raddr1;
    store_set_t          rd0, rd1;           // registered read data
    logic                we0, we1;
    logic [SET_BITS-1:0] set0_q, set1_q;     // addresses of the sets in rd0/rd1
    store_set_t          wd0, wd1;

`ifndef SYNTHESIS  // simulation power-up state (entries are gated by the epoch)
    initial begin
        for (int s = 0; s < NUM_SETS; s++) begin
            bank0[s] = '0;
            bank1[s] = '0;
        end
        for (int i = 0; i < STASH; i++) stash[i] = '0;
        rd0 = '0;
        rd1 = '0;
    end
`endif

    always_ff @(posedge clk) begin
        if (we0) bank0[set0_q] <= wd0;
        if (re)  rd0 <= bank0[raddr0];
    end

    always_ff @(posedge clk) begin
        if (we1) bank1[set1_q] <= wd1;
        if (re)  rd1 <= bank1[raddr1];
    end

    // Location of a reference: where = 0 none, 1 bank0, 2 bank1, 3 stash
    typedef struct packed {
        logic [1:0] where;
        logic [7:0] way;  // way index, or stash index
    } loc_t;

    // ------------------------------------------------------------------ FSM
    typedef enum logic [1:0] {S_IDLE, S_PROC, S_RD2, S_PROC2} state_e;
    state_e state;

    // Latched request
    logic [2:0]  q_op;
    logic [63:0] q_key;          // reference looked up in PROC
    logic [63:0] q_new_ref;      // reference inserted (ADD, REPLACE phase 2)
    logic        q_side;
    logic [31:0] q_shares, q_price;
    logic [31:0] rep_old_price, rep_old_shares;

    assign req_ready = armed_d && out_ready && !out_valid && (state == S_IDLE);

    // -------- read port
    logic [63:0] rd_key;
    always_comb begin
        re     = 1'b0;
        rd_key = (req_op == 3'd5) ? req_orig_ref : req_order_ref;
        if (state == S_IDLE && req_valid && req_ready) re = 1'b1;
        if (state == S_RD2) begin
            re     = 1'b1;
            rd_key = q_new_ref;
        end
        raddr0 = hash0(rd_key);
        raddr1 = hash1(rd_key);
    end

    // -------- lookup / free slot on the read sets (combinational)
    loc_t         lk, fl;
    store_entry_t cur_e, upd_e, new_e;
    logic         full_removal;

    always_comb begin
        int n0, n1, f0, f1, fs;
        lk = '0;
        for (int w = 0; w < NUM_WAYS; w++)
            if (lk.where == 2'd0 && live(rd0[w]) && rd0[w].order_ref == q_key) begin
                lk.where = 2'd1; lk.way = 8'(w);
            end
        for (int w = 0; w < NUM_WAYS; w++)
            if (lk.where == 2'd0 && live(rd1[w]) && rd1[w].order_ref == q_key) begin
                lk.where = 2'd2; lk.way = 8'(w);
            end
        for (int i = 0; i < STASH; i++)
            if (lk.where == 2'd0 && live(stash[i]) && stash[i].order_ref == q_key) begin
                lk.where = 2'd3; lk.way = 8'(i);
            end

        // Free slot: less loaded bank first (tie -> bank0), then stash.
        fl = '0;
        n0 = 0; n1 = 0; f0 = -1; f1 = -1; fs = -1;
        for (int w = 0; w < NUM_WAYS; w++) begin
            if (live(rd0[w])) n0++; else if (f0 < 0) f0 = w;
            if (live(rd1[w])) n1++; else if (f1 < 0) f1 = w;
        end
        for (int i = 0; i < STASH; i++)
            if (!live(stash[i]) && fs < 0) fs = i;
        if (f0 >= 0 && (n0 <= n1 || f1 < 0)) begin
            fl.where = 2'd1; fl.way = 8'(f0);
        end else if (f1 >= 0) begin
            fl.where = 2'd2; fl.way = 8'(f1);
        end else if (fs >= 0) begin
            fl.where = 2'd3; fl.way = 8'(fs);
        end

        case (lk.where)
            2'd1:    cur_e = rd0[lk.way[WAY_BITS-1:0]];
            2'd2:    cur_e = rd1[lk.way[WAY_BITS-1:0]];
            2'd3:    cur_e = stash[lk.way[STB-1:0]];
            default: cur_e = '0;
        endcase
        full_removal = (q_op == 3'd4) || (cur_e.shares <= q_shares);
        upd_e        = cur_e;
        upd_e.valid  = !full_removal;
        upd_e.shares = full_removal ? 32'd0 : cur_e.shares - q_shares;
        if (q_op == 3'd5) upd_e.valid = 1'b0;      // REPLACE phase 1: free

        new_e = '{valid: 1'b1, epoch: epoch, order_ref: q_new_ref, price: q_price,
                  shares: q_shares, side: q_side};
    end

    // Insert happens in PROC (ADD) and PROC2 (REPLACE); modify in PROC.
    logic do_insert, do_modify;
    assign do_insert = (state == S_PROC && q_op == 3'd1) || (state == S_PROC2);
    assign do_modify = (state == S_PROC) && (q_op inside {3'd2, 3'd3, 3'd4, 3'd5})
                       && (lk.where != 2'd0);

    // -------- write-back of the set words
    always_comb begin
        we0 = 1'b0; we1 = 1'b0;
        wd0 = rd0;  wd1 = rd1;
        if (do_insert) begin
            if (fl.where == 2'd1) begin we0 = 1'b1; wd0[fl.way[WAY_BITS-1:0]] = new_e; end
            if (fl.where == 2'd2) begin we1 = 1'b1; wd1[fl.way[WAY_BITS-1:0]] = new_e; end
        end else if (do_modify) begin
            if (lk.where == 2'd1) begin we0 = 1'b1; wd0[lk.way[WAY_BITS-1:0]] = upd_e; end
            if (lk.where == 2'd2) begin we1 = 1'b1; wd1[lk.way[WAY_BITS-1:0]] = upd_e; end
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state              <= S_IDLE;
            out_valid          <= 1'b0;
            out_cmd            <= LOB_CMD_NOP;
            out_side           <= 1'b0;
            out_price          <= '0;
            out_shares         <= '0;
            out_old_price      <= '0;
            out_old_shares     <= '0;
            table_hit          <= 1'b0;
            table_miss         <= 1'b0;
            table_full         <= 1'b0;
            active_order_count <= '0;
            stash_count        <= '0;
            overflow_count     <= '0;
            q_op <= '0; q_key <= '0; q_new_ref <= '0; q_side <= 1'b0;
            q_shares <= '0; q_price <= '0;
            rep_old_price <= '0; rep_old_shares <= '0;
            set0_q <= '0; set1_q <= '0;
        end else begin
            out_valid  <= 1'b0;
            out_cmd    <= LOB_CMD_NOP;
            table_hit  <= 1'b0;
            table_miss <= 1'b0;
            table_full <= 1'b0;

            if (re) begin
                set0_q <= raddr0;
                set1_q <= raddr1;
            end

            // Insertion bookkeeping (stash write, counters), PROC/ADD and PROC2
            if (do_insert) begin
                case (fl.where)
                    2'd3: begin
                        stash[fl.way[STB-1:0]] <= new_e;
                        stash_count <= stash_count + 1'b1;
                    end
                    2'd0: begin
                        table_full     <= 1'b1;
                        overflow_count <= overflow_count + 1'b1;
                    end
                    default: ;
                endcase
                if (fl.where != 2'd0) active_order_count <= active_order_count + 1'b1;
            end

            case (state)
                S_IDLE: begin
                    if (req_valid && req_ready) begin
                        q_op      <= req_op;
                        q_key     <= (req_op == 3'd5) ? req_orig_ref : req_order_ref;
                        q_new_ref <= req_order_ref;
                        q_side    <= req_side;
                        q_shares  <= req_shares;
                        q_price   <= req_price;
                        state     <= S_PROC;
                    end
                end

                S_PROC: begin
                    state <= S_IDLE;
                    case (q_op)
                        3'd1: begin // Add
                            out_valid  <= 1'b1;
                            out_cmd    <= LOB_CMD_ADD;
                            out_side   <= q_side;
                            out_price  <= q_price;
                            out_shares <= q_shares;
                            table_hit  <= 1'b1;
                        end

                        3'd2, 3'd3, 3'd4: begin // Exec / Cancel / Delete
                            if (lk.where == 2'd0) begin
                                table_miss <= 1'b1;
                            end else begin
                                table_hit  <= 1'b1;
                                out_valid  <= 1'b1;
                                out_cmd    <= LOB_CMD_SUB;
                                out_side   <= cur_e.side;
                                out_price  <= cur_e.price;
                                out_shares <= full_removal ? cur_e.shares : q_shares;
                                if (lk.where == 2'd3) begin
                                    stash[lk.way[STB-1:0]] <= upd_e;
                                    if (full_removal) stash_count <= stash_count - 1'b1;
                                end
                                if (full_removal) active_order_count <= active_order_count - 1'b1;
                            end
                        end

                        3'd5: begin // Replace phase 1: free the original order
                            if (lk.where == 2'd0) begin
                                table_miss <= 1'b1;
                            end else begin
                                table_hit <= 1'b1;
                                if (lk.where == 2'd3) begin
                                    stash[lk.way[STB-1:0]].valid <= 1'b0;
                                    stash_count <= stash_count - 1'b1;
                                end
                                active_order_count <= active_order_count - 1'b1;
                                q_side         <= cur_e.side;
                                rep_old_price  <= cur_e.price;
                                rep_old_shares <= cur_e.shares;
                                state          <= S_RD2;
                            end
                        end

                        default: ;
                    endcase
                end

                S_RD2: state <= S_PROC2;

                S_PROC2: begin // Replace phase 2: store the new order
                    // active_order_count: -1 in phase 1, +1 here (if stored)
                    out_valid      <= 1'b1;
                    out_cmd        <= LOB_CMD_REPLACE;
                    out_side       <= q_side;
                    out_old_price  <= rep_old_price;
                    out_old_shares <= rep_old_shares;
                    out_price      <= q_price;
                    out_shares     <= q_shares;
                    state          <= S_IDLE;
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule : order_store

`endif // ORDER_STORE_SV
