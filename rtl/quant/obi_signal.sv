`ifndef OBI_SIGNAL_SV
`define OBI_SIGNAL_SV

`timescale 1ns / 1ps

// Division-free OBI threshold decision (step P4).
//
// The strategy only needs to know whether OBI = (Vb - Va) / (Vb + Va)
// crosses a buy or sell threshold T (signed Q1.31). Since Vb + Va > 0:
//     OBI >= T   <=>   (Vb - Va) * 2^31 >= T * (Vb + Va)
// so the 32-stage divider is replaced by one signed multiply per threshold.
// Latency: 2 cycles (register the volumes, then multiply + compare). The
// exact OBI value is still produced by obi_calculator for telemetry only.
module obi_signal (
    input  logic               clk,
    input  logic               rst_n,

    input  logic               bbo_valid,
    input  logic [31:0]        bid_shares,
    input  logic [31:0]        ask_shares,
    input  logic signed [31:0] buy_thresh,    // Q1.31
    input  logic signed [31:0] sell_thresh,   // Q1.31

    output logic               sig_valid,     // follows bbo_valid (2 cycles later), 0 if book empty
    output logic               sig_buy,       // OBI >= buy_thresh
    output logic               sig_sell       // OBI <= sell_thresh
);

    logic               s1_valid;
    logic signed [33:0] s1_diff;   // Vb - Va
    logic signed [33:0] s1_sum;    // Vb + Va (>= 0)

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s1_valid <= 1'b0;
            s1_diff  <= '0;
            s1_sum   <= '0;
        end else begin
            s1_valid <= bbo_valid;
            s1_diff  <= $signed({2'b00, bid_shares}) - $signed({2'b00, ask_shares});
            s1_sum   <= $signed({2'b00, bid_shares}) + $signed({2'b00, ask_shares});
        end
    end

    logic signed [65:0] lhs, rhs_buy, rhs_sell;
    assign lhs      = 66'(s1_diff) <<< 31;
    assign rhs_buy  = 66'(buy_thresh) * 66'(s1_sum);
    assign rhs_sell = 66'(sell_thresh) * 66'(s1_sum);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sig_valid <= 1'b0;
            sig_buy   <= 1'b0;
            sig_sell  <= 1'b0;
        end else begin
            sig_valid <= s1_valid && (s1_sum != 0);
            sig_buy   <= s1_valid && (s1_sum != 0) && (lhs >= rhs_buy);
            sig_sell  <= s1_valid && (s1_sum != 0) && (lhs <= rhs_sell);
        end
    end

endmodule : obi_signal

`endif // OBI_SIGNAL_SV
