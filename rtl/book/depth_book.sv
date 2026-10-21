`ifndef DEPTH_BOOK_SV
`define DEPTH_BOOK_SV

`timescale 1ns / 1ps

/* verilator lint_off IMPORTSTAR */
import lob_pkg::*;
/* verilator lint_on IMPORTSTAR */

// Full-depth L2 book with exact top-N extraction (step P4).
//
// Aggregated shares are stored per price tick in a price-indexed array
// (TICK_BITS = 16 -> 65,536 ticks of $0.01 = $0..$655.35 above PRICE_BASE),
// one per side. A three-level occupancy bitmap (65,536 / 2,048 / 64 bits)
// finds the next non-empty level in a bounded number of steps, so the top
// N levels are always exact whatever the depth of the book.
//
// Orders outside the window or off the penny grid (stub quotes far from the
// market, sub-penny prices) are not stored by price: they are counted in
// `out_of_window_*` and can never appear in the top N. On real NASDAQ data
// (01/30/2019) the top 5 of AAPL, MSFT and TSLA always stayed inside
// $1.01..$369.00, i.e. inside the window with PRICE_BASE = 0.
//
// Step P5a (synthesizable memories):
//   * the share array is a synchronous-read RAM (one read port, one write
//     port, 1-cycle read latency, address {side, tick}) -> BRAM/URAM;
//   * the L0 bitmap is a RAM written from a reset-free process (async read,
//     distributed RAM); L1/L2 stay registers and are the only state reset;
//   * price -> tick uses a reciprocal multiply + exact grid check instead of
//     a divider (see price_to_tick).
//
// Latency: IDLE -> RD -> APPLY (3 cycles per price-level update, REPLACE adds
// RD2 -> APPLY2), then 1 cycle per extracted level on the touched side
// (the share read of level k overlaps the search of level k+1), 1 flush
// cycle when TOP_LEVELS levels are found, and 1 publish cycle.
module depth_book #(
    parameter logic [31:0] PRICE_BASE = 32'd0,   // raw price (x10^4) of tick 0
    parameter int          TICK_RAW   = 100,     // $0.01 in raw units
    parameter int          TICK_BITS  = 16,
    parameter int          TOP_LEVELS = 5
)(
    input  logic             clk,
    input  logic             rst_n,

    input  logic             cmd_valid,
    output logic             cmd_ready,
    input  lob_cmd_e         cmd_op,
    input  logic             cmd_side,       // 0: Buy, 1: Sell
    input  logic [31:0]      cmd_price,
    input  logic [31:0]      cmd_shares,
    input  logic [31:0]      cmd_old_price,
    input  logic [31:0]      cmd_old_shares,

    output price_level_t     bid_levels [0:TOP_LEVELS-1],
    output price_level_t     ask_levels [0:TOP_LEVELS-1],
    output logic [15:0]      bid_level_count,  // non-empty in-window levels
    output logic [15:0]      ask_level_count,
    output logic             book_updated,     // pulse: top levels refreshed
    output logic [31:0]      out_of_window_orders
);

    localparam int NTICKS = 1 << TICK_BITS;
    localparam int L0W    = NTICKS / 32;       // 2048 words
    localparam int L1W    = L0W / 32;          // 64 words
    localparam int L2B    = L1W;               // 64 bits
    localparam int AW     = TICK_BITS + 1;     // {side, tick}
    localparam int L0AW   = TICK_BITS - 5;

    // Division-free price -> tick. off / TICK_RAW = (off * RECIP) >> (32 + RSH)
    // with RECIP = ceil(2^(32+RSH) / TICK_RAW), RSH = ceil(log2 TICK_RAW)
    // (round-up reciprocal, Granlund-Montgomery; RECIP fits in 33 bits):
    // exact for every 32-bit off. For TICK_RAW = 100: RSH = 7,
    // RECIP = 0x147AE147B. The grid check is then exact: off == q * TICK_RAW
    // (constant multiply, no divider). RECIP is an elaboration-time constant.
    localparam int          RSH   = $clog2(TICK_RAW);
    localparam logic [64:0] RECIP = ((65'd1 << (32 + RSH)) + 65'(TICK_RAW) - 65'd1) / 65'(TICK_RAW);
    localparam int          PW    = 64 + RSH;   // product width

    // ------------------------------------------------------------------ memories
    logic [31:0]   shares_mem [0:(1 << AW)-1];
    logic          sh_re, sh_we;
    logic [AW-1:0] sh_raddr, sh_waddr;
    logic [31:0]   sh_rdata, sh_wdata;

    logic [31:0]    l0 [0:1][0:L0W-1];
    logic [31:0]    l1 [0:1][0:L1W-1];
    logic [L2B-1:0] l2 [0:1];
    logic           l0_we, l0_ws;
    logic [L0AW-1:0] l0_wa;
    logic [31:0]    l0_wdata;

`ifndef SYNTHESIS  // simulation power-up state (RAM contents are don't-care: O(1) reset)
    initial begin
        for (int i = 0; i < (1 << AW); i++) shares_mem[i] = '0;
        for (int s = 0; s < 2; s++) begin
            for (int i = 0; i < L0W; i++) l0[s][i] = '0;
            for (int i = 0; i < L1W; i++) l1[s][i] = '0;
            l2[s] = '0;
        end
        sh_rdata = '0;
    end
`endif

    // Share RAM: registered read, one write port (read-first is irrelevant:
    // the FSM never reads and writes the same cycle).
    always_ff @(posedge clk) begin
        if (sh_we) shares_mem[sh_waddr] <= sh_wdata;
        if (sh_re) sh_rdata <= shares_mem[sh_raddr];
    end

    // L0 bitmap RAM (reset-free so it can map to distributed RAM).
    always_ff @(posedge clk) begin
        if (l0_we) l0[l0_ws][l0_wa] <= l0_wdata;
    end

    // O(1) clear: reset only clears the small L1/L2 bitmaps (registers). A
    // tick is occupied iff its L1 word bit and its L0 bit are both set, so
    // stale L0 words and share counts left in RAM are ignored after a reset.
    function automatic logic [31:0] l0_eff(input int s, input int w);
        return l1[s][w >> 5][w & 31] ? l0[s][w] : 32'd0;
    endfunction

    // ------------------------------------------------------------------ helpers
    function automatic int hsb32(input logic [31:0] v);  // highest set bit, -1 if none
        for (int b = 31; b >= 0; b--) if (v[b]) return b;
        return -1;
    endfunction

    function automatic int lsb32(input logic [31:0] v);
        for (int b = 0; b < 32; b++) if (v[b]) return b;
        return -1;
    endfunction

    function automatic int hsb64(input logic [63:0] v);
        for (int b = 63; b >= 0; b--) if (v[b]) return b;
        return -1;
    endfunction

    function automatic int lsb64(input logic [63:0] v);
        for (int b = 0; b < 64; b++) if (v[b]) return b;
        return -1;
    endfunction

    function automatic logic [31:0] mask_le(input int b);  // bits [b:0]
        return (b >= 31) ? 32'hFFFF_FFFF : ((32'd1 << (b + 1)) - 32'd1);
    endfunction

    function automatic logic [31:0] mask_ge(input int b);  // bits [31:b]
        return ~((32'd1 << b) - 32'd1);
    endfunction

    // Highest occupied tick <= p on side s (-1 if none). Used for bids.
    function automatic int find_le(input int s, input int p);
        int w, w1, b, ww;
        logic [31:0] m;
        logic [63:0] m2;
        if (p < 0) return -1;
        w = p >> 5;
        m = l0_eff(s, w) & mask_le(p & 31);
        if (m != 0) return (w << 5) + hsb32(m);
        w1 = w >> 5;
        m  = ((w & 31) == 0) ? 32'd0 : (l1[s][w1] & mask_le((w & 31) - 1));
        if (m != 0) begin
            ww = (w1 << 5) + hsb32(m);
            return (ww << 5) + hsb32(l0[s][ww]);
        end
        m2 = (w1 == 0) ? 64'd0 : (l2[s] & ((64'd1 << w1) - 64'd1));
        if (m2 == 0) return -1;
        b  = hsb64(m2);
        ww = (b << 5) + hsb32(l1[s][b]);
        return (ww << 5) + hsb32(l0[s][ww]);
    endfunction

    // Lowest occupied tick >= p on side s (-1 if none). Used for asks.
    function automatic int find_ge(input int s, input int p);
        int w, w1, b, ww;
        logic [31:0] m;
        logic [63:0] m2;
        if (p >= NTICKS) return -1;
        w = p >> 5;
        m = l0_eff(s, w) & mask_ge(p & 31);
        if (m != 0) return (w << 5) + lsb32(m);
        w1 = w >> 5;
        m  = ((w & 31) == 31) ? 32'd0 : (l1[s][w1] & mask_ge((w & 31) + 1));
        if (m != 0) begin
            ww = (w1 << 5) + lsb32(m);
            return (ww << 5) + lsb32(l0[s][ww]);
        end
        m2 = (w1 == L1W - 1) ? 64'd0 : (l2[s] & ~((64'd2 << w1) - 64'd1));
        if (m2 == 0) return -1;
        b  = lsb64(m2);
        ww = (b << 5) + lsb32(l1[s][b]);
        return (ww << 5) + lsb32(l0[s][ww]);
    endfunction

    // Raw price -> tick; ok only inside the window and on the grid.
    typedef struct packed {
        logic                 ok;
        logic [TICK_BITS-1:0] tick;
    } tick_t;

    function automatic tick_t price_to_tick(input logic [31:0] price);
        tick_t       r;
        logic [31:0] off, q;
        logic [PW-1:0] prod;
        r = '0;
        /* verilator lint_off UNSIGNED */ // constant-false when PRICE_BASE == 0
        if (price < PRICE_BASE) return r;
        /* verilator lint_on UNSIGNED */
        off  = price - PRICE_BASE;
        prod = PW'(off) * PW'(RECIP);
        q    = prod[32 + RSH +: 32];
        r.ok   = (off == q * 32'(TICK_RAW)) && (q < 32'(NTICKS));
        r.tick = q[TICK_BITS-1:0];
        return r;
    endfunction

    // ------------------------------------------------------------------ FSM
    typedef enum logic [3:0] {S_IDLE, S_RD, S_APPLY, S_RD2, S_APPLY2, S_SCAN, S_FLUSH, S_DONE} state_e;
    state_e state;

    logic        c_side;
    logic        c_add;          // first step: add (1) or subtract (0)
    logic [31:0] c_shares;
    tick_t       c_tk;
    logic        c_second;       // REPLACE: an add follows
    logic [31:0] c_new_shares;
    tick_t       c_tk2;

    int          scan_k;
    int          scan_pos;
    logic        pend;           // a level share read is in flight
    int          pend_k;
    logic [TICK_BITS-1:0] pend_t;
    price_level_t next_levels [0:TOP_LEVELS-1];

    assign cmd_ready = (state == S_IDLE);

    // -------- apply step (combinational, on the registered share read)
    logic                 a_act, a_add, a_ok, a_birth, a_death;
    logic [TICK_BITS-1:0] a_t;
    logic [31:0]          a_qty, a_cur, a_nxt, a_w0, a_w0n, a_l1, a_l1n;
    int                   a_s, a_w, a_w1;

    always_comb begin
        a_act   = (state == S_APPLY) || (state == S_APPLY2);
        a_add   = (state == S_APPLY2) ? 1'b1 : c_add;
        a_ok    = (state == S_APPLY2) ? c_tk2.ok : c_tk.ok;
        a_t     = (state == S_APPLY2) ? c_tk2.tick : c_tk.tick;
        a_qty   = (state == S_APPLY2) ? c_new_shares : c_shares;
        a_s     = c_side ? 1 : 0;
        a_w     = int'(a_t) >> 5;
        a_w1    = a_w >> 5;
        a_w0    = l0_eff(a_s, a_w);
        a_l1    = l1[a_s][a_w1];
        a_cur   = a_w0[a_t[4:0]] ? sh_rdata : 32'd0;
        a_nxt   = a_add ? a_cur + a_qty : ((a_cur > a_qty) ? a_cur - a_qty : 32'd0);
        a_birth = (a_cur == 0) && (a_nxt != 0);
        a_death = (a_cur != 0) && (a_nxt == 0);
        a_w0n   = a_w0;
        a_l1n   = a_l1;
        if (a_birth) begin
            a_w0n = a_w0 | (32'd1 << a_t[4:0]);
            a_l1n = a_l1 | (32'd1 << (a_w & 31));
        end else if (a_death) begin
            a_w0n = a_w0 & ~(32'd1 << a_t[4:0]);
            a_l1n = (a_w0n == 0) ? (a_l1 & ~(32'd1 << (a_w & 31))) : a_l1;
        end
    end

    // -------- scan step: next non-empty level of the touched side (bitmaps)
    int scan_t;
    always_comb begin
        scan_t = c_side ? find_ge(1, scan_pos) : find_le(0, scan_pos);
    end

    // -------- memory ports
    always_comb begin
        sh_re    = 1'b0;
        sh_raddr = {c_side, c_tk.tick};
        if (state == S_RD) begin
            sh_re = 1'b1;
        end else if (state == S_RD2) begin
            sh_re    = 1'b1;
            sh_raddr = {c_side, c_tk2.tick};
        end else if (state == S_SCAN && scan_t >= 0) begin
            sh_re    = 1'b1;
            sh_raddr = {c_side, scan_t[TICK_BITS-1:0]};
        end
        sh_we    = a_act && a_ok;
        sh_waddr = {c_side, a_t};
        sh_wdata = a_nxt;
        l0_we    = a_act && a_ok && (a_birth || a_death);
        l0_ws    = c_side;
        l0_wa    = a_t[TICK_BITS-1:5];
        l0_wdata = a_w0n;
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state                <= S_IDLE;
            book_updated         <= 1'b0;
            bid_level_count      <= '0;
            ask_level_count      <= '0;
            out_of_window_orders <= '0;
            c_side <= 1'b0; c_add <= 1'b0; c_shares <= '0; c_tk <= '0;
            c_second <= 1'b0; c_new_shares <= '0; c_tk2 <= '0;
            scan_k <= 0; scan_pos <= 0;
            pend <= 1'b0; pend_k <= 0; pend_t <= '0;
            for (int sd = 0; sd < 2; sd++) begin
                for (int i = 0; i < L1W; i++) l1[sd][i] <= '0;
                l2[sd] <= '0;
            end
            for (int i = 0; i < TOP_LEVELS; i++) begin
                bid_levels[i]  <= '0;
                ask_levels[i]  <= '0;
                next_levels[i] <= '0;
            end
        end else begin
            book_updated <= 1'b0;
            case (state)
                S_IDLE: begin
                    if (cmd_valid && cmd_op != LOB_CMD_NOP) begin
                        c_side <= cmd_side;
                        case (cmd_op)
                            LOB_CMD_ADD: begin
                                c_add <= 1'b1; c_tk <= price_to_tick(cmd_price);
                                c_shares <= cmd_shares; c_second <= 1'b0;
                            end
                            LOB_CMD_SUB: begin
                                c_add <= 1'b0; c_tk <= price_to_tick(cmd_price);
                                c_shares <= cmd_shares; c_second <= 1'b0;
                            end
                            default: begin // REPLACE: subtract old, then add new
                                c_add <= 1'b0; c_tk <= price_to_tick(cmd_old_price);
                                c_shares <= cmd_old_shares; c_second <= 1'b1;
                                c_tk2 <= price_to_tick(cmd_price); c_new_shares <= cmd_shares;
                            end
                        endcase
                        state <= S_RD;
                    end
                end

                S_RD:  state <= S_APPLY;
                S_RD2: state <= S_APPLY2;

                S_APPLY, S_APPLY2: begin
                    if (!a_ok) begin
                        if (a_add) out_of_window_orders <= out_of_window_orders + 1;
                        else if (out_of_window_orders != 0) out_of_window_orders <= out_of_window_orders - 1;
                    end else if (a_birth) begin
                        l1[a_s][a_w1] <= a_l1n;
                        l2[a_s]       <= l2[a_s] | (64'd1 << a_w1);
                        if (a_s == 0) bid_level_count <= bid_level_count + 1;
                        else          ask_level_count <= ask_level_count + 1;
                    end else if (a_death) begin
                        l1[a_s][a_w1] <= a_l1n;
                        if (a_l1n == 0) l2[a_s] <= l2[a_s] & ~(64'd1 << a_w1);
                        if (a_s == 0) bid_level_count <= bid_level_count - 1;
                        else          ask_level_count <= ask_level_count - 1;
                    end
                    state    <= (state == S_APPLY && c_second) ? S_RD2 : S_SCAN;
                    scan_k   <= 0;
                    scan_pos <= c_side ? 0 : NTICKS - 1;
                    pend     <= 1'b0;
                end

                S_SCAN: begin
                    // One level per cycle: the shares of level k (read issued
                    // last cycle) are captured while level k+1 is searched.
                    if (pend) next_levels[pend_k] <= '{valid: 1'b1,
                                                       price: PRICE_BASE + 32'(pend_t) * TICK_RAW,
                                                       shares: sh_rdata};
                    if (scan_t < 0) begin
                        for (int i = 0; i < TOP_LEVELS; i++) if (i >= scan_k) next_levels[i] <= '0;
                        pend  <= 1'b0;
                        state <= S_DONE;
                    end else begin
                        pend     <= 1'b1;
                        pend_k   <= scan_k;
                        pend_t   <= scan_t[TICK_BITS-1:0];
                        scan_pos <= c_side ? scan_t + 1 : scan_t - 1;
                        scan_k   <= scan_k + 1;
                        if (scan_k == TOP_LEVELS - 1) state <= S_FLUSH;
                    end
                end

                S_FLUSH: begin
                    next_levels[pend_k] <= '{valid: 1'b1,
                                             price: PRICE_BASE + 32'(pend_t) * TICK_RAW,
                                             shares: sh_rdata};
                    pend  <= 1'b0;
                    state <= S_DONE;
                end

                S_DONE: begin
                    for (int i = 0; i < TOP_LEVELS; i++) begin
                        if (c_side) ask_levels[i] <= next_levels[i];
                        else        bid_levels[i] <= next_levels[i];
                    end
                    book_updated <= 1'b1;
                    state <= S_IDLE;
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule : depth_book

`endif // DEPTH_BOOK_SV
