// ============================================================================
// Module Name:   cdc_msg_fifo
// Description:   Dedicated Clock Domain Crossing (CDC) Asynchronous FIFO for
//                ITCH 5.0 Decoded Messages (itch_parsed_msg_t).
//                Crosses from network domain (clk_src @ 156.25 MHz) to
//                accelerated compute core domain (clk_dest @ 312.5 MHz).
//                Uses Gray-code pointer synchronization and ASYNC_REG attributes.
// Standard:      SystemVerilog IEEE 1800-2017
// Target:        AMD Kria KR260 / UltraScale+
// ============================================================================

`ifndef CDC_MSG_FIFO_SV
`define CDC_MSG_FIFO_SV

`timescale 1ns / 1ps

/* verilator lint_off IMPORTSTAR */
import itch_pkg::*;
/* verilator lint_on IMPORTSTAR */

module cdc_msg_fifo #(
    parameter int ADDR_WIDTH = 4   // Depth = 1 << ADDR_WIDTH (e.g. 16 entries)
)(
    // Source Clock Domain (Network clk_net @ 156.25 MHz)
    input  logic              clk_src,
    input  logic              rst_n_src,
    input  logic              src_valid,
    input  itch_parsed_msg_t  src_msg,
    output logic              src_ready,

    // Destination Clock Domain (Core clk_core @ 312.5 MHz)
    input  logic              clk_dest,
    input  logic              rst_n_dest,
    output logic              dest_valid,
    output itch_parsed_msg_t  dest_msg,
    input  logic              dest_ready,

    // Telemetry
    output logic              fifo_full_src,
    output logic              fifo_empty_dest
);

    localparam int DEPTH = 1 << ADDR_WIDTH;

    // Dual-Port Storage RAM
    (* ram_style = "distributed" *) itch_parsed_msg_t mem [0:DEPTH-1];

    // ------------------------------------------------------------------------
    // Write Domain (clk_src)
    // ------------------------------------------------------------------------
    logic [ADDR_WIDTH:0] wr_ptr_bin;
    logic [ADDR_WIDTH:0] wr_ptr_gray;
    logic [ADDR_WIDTH:0] wr_ptr_bin_next;
    logic [ADDR_WIDTH:0] wr_ptr_gray_next;

    (* ASYNC_REG = "TRUE" *) logic [ADDR_WIDTH:0] rd_ptr_gray_sync1;
    (* ASYNC_REG = "TRUE" *) logic [ADDR_WIDTH:0] rd_ptr_gray_sync2;

    wire wr_en = src_valid && src_ready;

    assign wr_ptr_bin_next  = wr_ptr_bin + { {ADDR_WIDTH{1'b0}}, wr_en };
    assign wr_ptr_gray_next = (wr_ptr_bin_next >> 1) ^ wr_ptr_bin_next;

    wire [ADDR_WIDTH:0] full_test = {~rd_ptr_gray_sync2[ADDR_WIDTH:ADDR_WIDTH-1], rd_ptr_gray_sync2[ADDR_WIDTH-2:0]};
    wire fifo_full = (wr_ptr_gray == full_test);

    assign src_ready      = !fifo_full;
    assign fifo_full_src  = fifo_full;

    always_ff @(posedge clk_src or negedge rst_n_src) begin
        if (!rst_n_src) begin
            wr_ptr_bin        <= '0;
            wr_ptr_gray       <= '0;
            rd_ptr_gray_sync1 <= '0;
            rd_ptr_gray_sync2 <= '0;
        end else begin
            rd_ptr_gray_sync1 <= rd_ptr_gray;
            rd_ptr_gray_sync2 <= rd_ptr_gray_sync1;

            if (wr_en) begin
                mem[wr_ptr_bin[ADDR_WIDTH-1:0]] <= src_msg;
                wr_ptr_bin                      <= wr_ptr_bin_next;
                wr_ptr_gray                     <= wr_ptr_gray_next;
            end
        end
    end

    // ------------------------------------------------------------------------
    // Read Domain (clk_dest)
    // ------------------------------------------------------------------------
    logic [ADDR_WIDTH:0] rd_ptr_bin;
    logic [ADDR_WIDTH:0] rd_ptr_gray;
    logic [ADDR_WIDTH:0] rd_ptr_bin_next;
    logic [ADDR_WIDTH:0] rd_ptr_gray_next;

    (* ASYNC_REG = "TRUE" *) logic [ADDR_WIDTH:0] wr_ptr_gray_sync1;
    (* ASYNC_REG = "TRUE" *) logic [ADDR_WIDTH:0] wr_ptr_gray_sync2;

    wire fifo_empty = (rd_ptr_gray == wr_ptr_gray_sync2);
    assign fifo_empty_dest = fifo_empty;

    // FWFT Output Register
    itch_parsed_msg_t out_msg_reg;
    logic             out_valid_reg;

    wire rd_from_ram = !fifo_empty && (!out_valid_reg || dest_ready);

    assign rd_ptr_bin_next  = rd_ptr_bin + { {ADDR_WIDTH{1'b0}}, rd_from_ram };
    assign rd_ptr_gray_next = (rd_ptr_bin_next >> 1) ^ rd_ptr_bin_next;

    always_ff @(posedge clk_dest or negedge rst_n_dest) begin
        if (!rst_n_dest) begin
            rd_ptr_bin        <= '0;
            rd_ptr_gray       <= '0;
            wr_ptr_gray_sync1 <= '0;
            wr_ptr_gray_sync2 <= '0;
            out_valid_reg     <= 1'b0;
            out_msg_reg       <= '0;
        end else begin
            wr_ptr_gray_sync1 <= wr_ptr_gray;
            wr_ptr_gray_sync2 <= wr_ptr_gray_sync1;

            if (dest_ready && out_valid_reg) begin
                out_valid_reg <= 1'b0;
            end

            if (rd_from_ram) begin
                out_msg_reg   <= mem[rd_ptr_bin[ADDR_WIDTH-1:0]];
                out_valid_reg <= 1'b1;
                rd_ptr_bin    <= rd_ptr_bin_next;
                rd_ptr_gray   <= rd_ptr_gray_next;
            end
        end
    end

    assign dest_valid = out_valid_reg;
    assign dest_msg   = out_msg_reg;

endmodule : cdc_msg_fifo

`endif // CDC_MSG_FIFO_SV
