`ifndef OBI_CALCULATOR_SV
`define OBI_CALCULATOR_SV

`timescale 1ns / 1ps

/**
 * obi_calculator.sv
 *
 * High-Frequency Quantitative Microstructure Engine (AURA-HFT).
 * Computes:
 *   1. Order Book Imbalance (OBI) at L1:
 *        OBI = (V_bid - V_ask) / (V_bid + V_ask) in signed Q1.31 fixed-point.
 *   2. Micro-Price:
 *        P_micro = P_bid + ((1 + OBI) / 2) * Spread in fixed-point (4 decimal places).
 *
 * Architecture:
 *   - Fully unrolled 32-stage pipelined non-restoring divider (II = 1 cycle).
 *   - DSP48 single-cycle multiplication for Micro-Price (no second divider required!).
 *   - Line-rate throughput at 156.25 MHz (6.4 ns clock period).
 */

module obi_calculator #(
    parameter int unsigned PIPELINE_STAGES = 32
) (
    input  logic        clk,
    input  logic        rst_n,

    // Input BBO Stream from Top-of-Book Cache
    input  logic        bbo_valid,
    input  logic [31:0] best_bid_price,
    input  logic [31:0] best_bid_shares,
    input  logic [31:0] best_ask_price,
    input  logic [31:0] best_ask_shares,
    input  logic [31:0] spread,

    // Output Quantitative Signals
    output logic        obi_valid,
    output logic signed [31:0] obi_val,        // Signed Q1.31: -1.0 to +1.0
    output logic [31:0] micro_price,           // Fixed-point price (4 decimal places)
    output logic [31:0] out_bid_price,
    output logic [31:0] out_ask_price,
    output logic [31:0] out_spread
);

    // -------------------------------------------------------------
    // Stage 0: Pre-computation of Numerator, Denominator, and Sign
    // -------------------------------------------------------------
    logic        s0_valid;
    logic        s0_sign;       // 1 if V_bid < V_ask (negative OBI)
    logic [63:0] s0_remainder;  // Initialized with |V_bid - V_ask| << 31
    logic [32:0] s0_denom;      // V_bid + V_ask
    logic [31:0] s0_bid_price;
    logic [31:0] s0_ask_price;
    logic [31:0] s0_spread;
    logic        s0_denom_zero;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s0_valid      <= 1'b0;
            s0_sign       <= 1'b0;
            s0_remainder  <= '0;
            s0_denom      <= '0;
            s0_bid_price  <= '0;
            s0_ask_price  <= '0;
            s0_spread     <= '0;
            s0_denom_zero <= 1'b1;
        end else begin
            s0_valid     <= bbo_valid;
            s0_bid_price <= best_bid_price;
            s0_ask_price <= best_ask_price;
            s0_spread    <= spread;

            if (best_bid_shares >= best_ask_shares) begin
                s0_sign      <= 1'b0;
                s0_remainder <= {1'b0, (best_bid_shares - best_ask_shares), 31'd0};
            end else begin
                s0_sign      <= 1'b1;
                s0_remainder <= {1'b0, (best_ask_shares - best_bid_shares), 31'd0};
            end

            s0_denom      <= {1'b0, best_bid_shares} + {1'b0, best_ask_shares};
            s0_denom_zero <= (best_bid_shares == 32'd0 && best_ask_shares == 32'd0);
        end
    end

    // -------------------------------------------------------------
    // Pipelined Restoring Divider: 32 Stages
    // In each stage k (0 to 31):
    //   Compare remainder with (denom << (31 - k)).
    //   If remainder >= shifted denom, subtract and set quotient bit.
    // -------------------------------------------------------------
    typedef struct packed {
        logic        valid;
        logic        sign;
        logic        denom_zero;
        logic [63:0] rem;
        logic [32:0] denom;
        logic [31:0] quot;
        logic [31:0] bid_price;
        logic [31:0] ask_price;
        logic [31:0] spread;
    } pipe_stage_t;

    pipe_stage_t pipe [0:PIPELINE_STAGES-1];

    // First pipeline stage logic
    always_comb begin
        pipe[0].valid      = s0_valid;
        pipe[0].sign       = s0_sign;
        pipe[0].denom_zero = s0_denom_zero;
        pipe[0].denom      = s0_denom;
        pipe[0].bid_price  = s0_bid_price;
        pipe[0].ask_price  = s0_ask_price;
        pipe[0].spread     = s0_spread;

        if (!s0_denom_zero && (s0_remainder >= {s0_denom, 31'd0})) begin
            pipe[0].rem  = s0_remainder - {s0_denom, 31'd0};
            pipe[0].quot = 32'h8000_0000;
        end else begin
            pipe[0].rem  = s0_remainder;
            pipe[0].quot = 32'd0;
        end
    end

    // Pipeline registers for stages 1 to 31
    genvar i;
    generate
        for (i = 1; i < 32; i++) begin : gen_pipe_stages
            logic [63:0] shifted_d;
            assign shifted_d = 64'({pipe[i-1].denom, 31'd0} >> i);

            always_ff @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    pipe[i] <= '0;
                end else begin
                    pipe[i].valid      <= pipe[i-1].valid;
                    pipe[i].sign       <= pipe[i-1].sign;
                    pipe[i].denom_zero <= pipe[i-1].denom_zero;
                    pipe[i].denom      <= pipe[i-1].denom;
                    pipe[i].bid_price  <= pipe[i-1].bid_price;
                    pipe[i].ask_price  <= pipe[i-1].ask_price;
                    pipe[i].spread     <= pipe[i-1].spread;

                    if (!pipe[i-1].denom_zero && (pipe[i-1].rem >= shifted_d)) begin
                        pipe[i].rem  <= pipe[i-1].rem - shifted_d;
                        pipe[i].quot <= pipe[i-1].quot | (32'h8000_0000 >> i);
                    end else begin
                        pipe[i].rem  <= pipe[i-1].rem;
                        pipe[i].quot <= pipe[i-1].quot;
                    end
                end
            end
        end
    endgenerate

    // -------------------------------------------------------------
    // Post-division formatting & DSP Micro-Price Calculation
    // -------------------------------------------------------------
    logic signed [31:0] next_obi_val;
    logic [31:0]        next_w_raw;
    logic [63:0]        next_mult_prod;
    logic [31:0]        next_micro_price;

    always_comb begin
        next_w_raw       = '0;
        next_mult_prod   = '0;
        if (pipe[31].denom_zero) begin
            next_obi_val     = 32'sd0;
            next_micro_price = pipe[31].bid_price;
        end else begin
            // Format signed Q1.31
            if (pipe[31].sign) begin
                if (pipe[31].quot >= 32'h8000_0000) begin
                    next_obi_val = 32'sh8000_0000; // -1.0
                end else begin
                    next_obi_val = -32'(pipe[31].quot);
                end
            end else begin
                if (pipe[31].quot >= 32'h8000_0000) begin
                    next_obi_val = 32'sh7FFF_FFFF; // +0.9999999995
                end else begin
                    next_obi_val = 32'(pipe[31].quot);
                end
            end

            // Micro-Price: P_micro = P_bid + ((1 + OBI) / 2) * Spread
            next_w_raw       = 32'(next_obi_val) + 32'h8000_0000;
            next_mult_prod   = 64'(next_w_raw) * 64'(pipe[31].spread);
            next_micro_price = pipe[31].bid_price + next_mult_prod[63:32];
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            obi_valid       <= 1'b0;
            obi_val         <= '0;
            micro_price     <= '0;
            out_bid_price   <= '0;
            out_ask_price   <= '0;
            out_spread      <= '0;
        end else begin
            obi_valid     <= pipe[31].valid;
            out_bid_price <= pipe[31].bid_price;
            out_ask_price <= pipe[31].ask_price;
            out_spread    <= pipe[31].spread;
            obi_val       <= next_obi_val;
            micro_price   <= next_micro_price;
        end
    end

endmodule : obi_calculator

`endif // OBI_CALCULATOR_SV
