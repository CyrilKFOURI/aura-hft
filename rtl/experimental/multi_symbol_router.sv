// ============================================================================
// Module Name:   multi_symbol_router
// Description:   High-Throughput Ingress Demultiplexer based on ITCH 5.0
//                16-bit Stock Locate & 64-bit Symbol.
//                Routes to 4 concurrent symbol channels in 1 clock cycle.
// Standard:      SystemVerilog IEEE 1800-2017
// Target:        AMD Kria KR260 @ 156.25 MHz (6.4 ns)
// ============================================================================

`timescale 1ns / 1ps

/* verilator lint_off IMPORTSTAR */
import itch_pkg::*;
/* verilator lint_on IMPORTSTAR */

module multi_symbol_router #(
    parameter bit [15:0] LOCATE_CH0 = 16'd1, // AAPL
    parameter bit [15:0] LOCATE_CH1 = 16'd2, // MSFT
    parameter bit [15:0] LOCATE_CH2 = 16'd3, // NVDA
    parameter bit [15:0] LOCATE_CH3 = 16'd4  // TSLA
)(
    input  logic                   clk,
    input  logic                   rst_n,

    // Unified Ingress stream from ITCH parser
    input  logic                   in_valid,
    input  itch_parsed_msg_t       in_msg,

    // 4 Independent Symbol Channel Streams (1-cycle registered output)
    output logic [3:0]             chan_valid,
    output itch_parsed_msg_t       chan_msg [0:3],

    // Unrouted / Dropped Counter Telemetry
    output logic                   unrouted_valid,
    output logic [31:0]            routed_count,
    output logic [31:0]            unrouted_count
);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            chan_valid     <= 4'b0000;
            unrouted_valid <= 1'b0;
            routed_count   <= 32'd0;
            unrouted_count <= 32'd0;
            for (int i = 0; i < 4; i++) begin
                chan_msg[i] <= '0;
            end
        end else begin
            chan_valid     <= 4'b0000;
            unrouted_valid <= 1'b0;

            if (in_valid) begin
                if (in_msg.stock_locate == LOCATE_CH0) begin
                    chan_valid[0] <= 1'b1;
                    chan_msg[0]   <= in_msg;
                    routed_count  <= routed_count + 1;
                end else if (in_msg.stock_locate == LOCATE_CH1) begin
                    chan_valid[1] <= 1'b1;
                    chan_msg[1]   <= in_msg;
                    routed_count  <= routed_count + 1;
                end else if (in_msg.stock_locate == LOCATE_CH2) begin
                    chan_valid[2] <= 1'b1;
                    chan_msg[2]   <= in_msg;
                    routed_count  <= routed_count + 1;
                end else if (in_msg.stock_locate == LOCATE_CH3) begin
                    chan_valid[3] <= 1'b1;
                    chan_msg[3]   <= in_msg;
                    routed_count  <= routed_count + 1;
                end else begin
                    unrouted_valid <= 1'b1;
                    unrouted_count <= unrouted_count + 1;
                end
            end
        end
    end

endmodule
