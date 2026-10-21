`ifndef TOP_OF_BOOK_CACHE_SV
`define TOP_OF_BOOK_CACHE_SV

`timescale 1ns / 1ps

/* verilator lint_off IMPORTSTAR */
import lob_pkg::*;
/* verilator lint_on IMPORTSTAR */

module top_of_book_cache #(
    parameter int DEPTH = 16
)(
    input  logic             clk,
    input  logic             rst_n,

    // Input from Price Ladder
    input  price_level_t     bid_levels [0:DEPTH-1],
    input  price_level_t     ask_levels [0:DEPTH-1],
    input  logic [4:0]       bid_count,
    input  logic [4:0]       ask_count,
    input  logic             book_updated,

    // BBO Snapshot Outputs
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
    output logic [31:0]      top5_ask_shares [0:4]
);

    logic [31:0] reg_bid_price;
    logic [31:0] reg_bid_shares;
    logic [31:0] reg_ask_price;
    logic [31:0] reg_ask_shares;
    logic        reg_bbo_valid;

    assign bbo_valid       = reg_bbo_valid;
    assign best_bid_price  = reg_bid_price;
    assign best_bid_shares = reg_bid_shares;
    assign best_ask_price  = reg_ask_price;
    assign best_ask_shares = reg_ask_shares;
    assign spread          = (reg_bbo_valid && reg_ask_price >= reg_bid_price) ? (reg_ask_price - reg_bid_price) : 32'd0;
    assign mid_price       = (reg_bbo_valid) ? ((reg_bid_price + reg_ask_price) >> 1) : 32'd0;

    // Top-5 combinational assignment from ladder
    always_comb begin
        for (int i = 0; i < 5; i++) begin
            if (i < DEPTH && bid_levels[i].valid) begin
                top5_bid_price[i]  = bid_levels[i].price;
                top5_bid_shares[i] = bid_levels[i].shares;
            end else begin
                top5_bid_price[i]  = 32'd0;
                top5_bid_shares[i] = 32'd0;
            end

            if (i < DEPTH && ask_levels[i].valid) begin
                top5_ask_price[i]  = ask_levels[i].price;
                top5_ask_shares[i] = ask_levels[i].shares;
            end else begin
                top5_ask_price[i]  = 32'd0;
                top5_ask_shares[i] = 32'd0;
            end
        end
    end

    // Sequential tracking of BBO changes
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            reg_bbo_valid   <= 1'b0;
            reg_bid_price   <= '0;
            reg_bid_shares  <= '0;
            reg_ask_price   <= '0;
            reg_ask_shares  <= '0;
            bbo_updated     <= 1'b0;
        end else begin
            bbo_updated <= 1'b0;

            if (book_updated) begin
                automatic logic new_valid = bid_levels[0].valid && ask_levels[0].valid;
                automatic logic [31:0] new_bp = bid_levels[0].valid ? bid_levels[0].price : 32'd0;
                automatic logic [31:0] new_bs = bid_levels[0].valid ? bid_levels[0].shares : 32'd0;
                automatic logic [31:0] new_ap = ask_levels[0].valid ? ask_levels[0].price : 32'd0;
                automatic logic [31:0] new_as = ask_levels[0].valid ? ask_levels[0].shares : 32'd0;

                if ((new_valid != reg_bbo_valid) ||
                    (new_bp != reg_bid_price) || (new_bs != reg_bid_shares) ||
                    (new_ap != reg_ask_price) || (new_as != reg_ask_shares)) begin
                    bbo_updated <= 1'b1;
                end

                reg_bbo_valid  <= new_valid;
                reg_bid_price  <= new_bp;
                reg_bid_shares <= new_bs;
                reg_ask_price  <= new_ap;
                reg_ask_shares <= new_as;
            end
        end
    end

endmodule : top_of_book_cache

`endif // TOP_OF_BOOK_CACHE_SV
