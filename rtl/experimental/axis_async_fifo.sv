// ============================================================================
// Module Name:   axis_async_fifo
// Description:   Parameterized Clock Domain Crossing (CDC) AXI4-Stream Asynchronous FIFO.
//                Implements Gray-code pointer synchronization with Xilinx ASYNC_REG
//                attributes and First-Word Fall-Through (FWFT) low-latency read logic.
// Standard:      SystemVerilog IEEE 1800-2017
// Target:        AMD Kria KR260 / UltraScale+
// ============================================================================

`ifndef AXIS_ASYNC_FIFO_SV
`define AXIS_ASYNC_FIFO_SV

`timescale 1ns / 1ps

module axis_async_fifo #(
    parameter int DATA_WIDTH = 64,
    parameter int KEEP_WIDTH = (DATA_WIDTH / 8),
    parameter int ADDR_WIDTH = 4,              // Depth = 1 << ADDR_WIDTH (e.g., 16 entries)
    parameter int USER_WIDTH = 1
)(
    // AXI4-Stream Ingress Interface (Source Clock Domain)
    input  logic                   s_clk,
    input  logic                   s_rst_n,
    input  logic [DATA_WIDTH-1:0]  s_axis_tdata,
    input  logic [KEEP_WIDTH-1:0]  s_axis_tkeep,
    input  logic                   s_axis_tvalid,
    input  logic                   s_axis_tlast,
    input  logic [USER_WIDTH-1:0]  s_axis_tuser,
    output logic                   s_axis_tready,

    // AXI4-Stream Egress Interface (Destination Clock Domain)
    input  logic                   m_clk,
    input  logic                   m_rst_n,
    output logic [DATA_WIDTH-1:0]  m_axis_tdata,
    output logic [KEEP_WIDTH-1:0]  m_axis_tkeep,
    output logic                   m_axis_tvalid,
    output logic                   m_axis_tlast,
    output logic [USER_WIDTH-1:0]  m_axis_tuser,
    input  logic                   m_axis_tready,

    // Status Telemetry
    output logic                   s_fifo_full,
    output logic                   m_fifo_empty,
    output logic [ADDR_WIDTH:0]    s_fifo_level,
    output logic [ADDR_WIDTH:0]    m_fifo_level
);

    localparam int DEPTH = 1 << ADDR_WIDTH;
    localparam int PAYLOAD_WIDTH = DATA_WIDTH + KEEP_WIDTH + 1 + USER_WIDTH;

    // Pack input payload
    wire [PAYLOAD_WIDTH-1:0] s_payload = {s_axis_tuser, s_axis_tlast, s_axis_tkeep, s_axis_tdata};

    // Dual-Port Storage RAM
    (* ram_style = "distributed" *) logic [PAYLOAD_WIDTH-1:0] mem [0:DEPTH-1];

    // ------------------------------------------------------------------------
    // Write Domain (s_clk) Logic
    // ------------------------------------------------------------------------
    logic [ADDR_WIDTH:0] wr_ptr_bin;
    logic [ADDR_WIDTH:0] wr_ptr_gray;
    logic [ADDR_WIDTH:0] wr_ptr_bin_next;
    logic [ADDR_WIDTH:0] wr_ptr_gray_next;

    // Synchronized read pointer into write domain
    (* ASYNC_REG = "TRUE" *) logic [ADDR_WIDTH:0] rd_ptr_gray_sync1;
    (* ASYNC_REG = "TRUE" *) logic [ADDR_WIDTH:0] rd_ptr_gray_sync2;

    wire wr_en = s_axis_tvalid && s_axis_tready;

    assign wr_ptr_bin_next  = wr_ptr_bin + { {ADDR_WIDTH{1'b0}}, wr_en };
    assign wr_ptr_gray_next = (wr_ptr_bin_next >> 1) ^ wr_ptr_bin_next;

    // Full detection: MSB and MSB-1 inverted, rest match
    wire [ADDR_WIDTH:0] full_test = {~rd_ptr_gray_sync2[ADDR_WIDTH:ADDR_WIDTH-1], rd_ptr_gray_sync2[ADDR_WIDTH-2:0]};
    wire fifo_full = (wr_ptr_gray == full_test);

    assign s_axis_tready = !fifo_full;
    assign s_fifo_full   = fifo_full;

    always_ff @(posedge s_clk or negedge s_rst_n) begin
        if (!s_rst_n) begin
            wr_ptr_bin         <= '0;
            wr_ptr_gray        <= '0;
            rd_ptr_gray_sync1  <= '0;
            rd_ptr_gray_sync2  <= '0;
        end else begin
            // Synchronize read pointer
            rd_ptr_gray_sync1 <= rd_ptr_gray;
            rd_ptr_gray_sync2 <= rd_ptr_gray_sync1;

            if (wr_en) begin
                mem[wr_ptr_bin[ADDR_WIDTH-1:0]] <= s_payload;
                wr_ptr_bin                      <= wr_ptr_bin_next;
                wr_ptr_gray                     <= wr_ptr_gray_next;
            end
        end
    end

    // ------------------------------------------------------------------------
    // Read Domain (m_clk) Logic
    // ------------------------------------------------------------------------
    logic [ADDR_WIDTH:0] rd_ptr_bin;
    logic [ADDR_WIDTH:0] rd_ptr_gray;
    logic [ADDR_WIDTH:0] rd_ptr_bin_next;
    logic [ADDR_WIDTH:0] rd_ptr_gray_next;

    // Synchronized write pointer into read domain
    (* ASYNC_REG = "TRUE" *) logic [ADDR_WIDTH:0] wr_ptr_gray_sync1;
    (* ASYNC_REG = "TRUE" *) logic [ADDR_WIDTH:0] wr_ptr_gray_sync2;

    // FIFO empty detection in read domain
    wire fifo_empty = (rd_ptr_gray == wr_ptr_gray_sync2);
    assign m_fifo_empty = fifo_empty;

    // FWFT Output Buffer Register
    logic [PAYLOAD_WIDTH-1:0] out_payload_reg;
    logic                     out_valid_reg;

    wire rd_from_ram = !fifo_empty && (!out_valid_reg || m_axis_tready);

    assign rd_ptr_bin_next  = rd_ptr_bin + { {ADDR_WIDTH{1'b0}}, rd_from_ram };
    assign rd_ptr_gray_next = (rd_ptr_bin_next >> 1) ^ rd_ptr_bin_next;

    always_ff @(posedge m_clk or negedge m_rst_n) begin
        if (!m_rst_n) begin
            rd_ptr_bin         <= '0;
            rd_ptr_gray        <= '0;
            wr_ptr_gray_sync1  <= '0;
            wr_ptr_gray_sync2  <= '0;
            out_valid_reg      <= 1'b0;
            out_payload_reg    <= '0;
        end else begin
            // Synchronize write pointer
            wr_ptr_gray_sync1 <= wr_ptr_gray;
            wr_ptr_gray_sync2 <= wr_ptr_gray_sync1;

            if (m_axis_tready && out_valid_reg) begin
                out_valid_reg <= 1'b0;
            end

            if (rd_from_ram) begin
                out_payload_reg <= mem[rd_ptr_bin[ADDR_WIDTH-1:0]];
                out_valid_reg   <= 1'b1;
                rd_ptr_bin      <= rd_ptr_bin_next;
                rd_ptr_gray     <= rd_ptr_gray_next;
            end
        end
    end

    // Unpack output payload
    assign m_axis_tvalid = out_valid_reg;
    assign {m_axis_tuser, m_axis_tlast, m_axis_tkeep, m_axis_tdata} = out_payload_reg;

    // Gray-to-Binary helper for level indicators
    function automatic logic [ADDR_WIDTH:0] gray2bin(input logic [ADDR_WIDTH:0] g);
        logic [ADDR_WIDTH:0] b;
        b[ADDR_WIDTH] = g[ADDR_WIDTH];
        for (int i = ADDR_WIDTH - 1; i >= 0; i--) begin
            b[i] = b[i+1] ^ g[i];
        end
        return b;
    endfunction

    assign s_fifo_level = wr_ptr_bin - gray2bin(rd_ptr_gray_sync2);
    assign m_fifo_level = gray2bin(wr_ptr_gray_sync2) - rd_ptr_bin;

endmodule : axis_async_fifo

`endif // AXIS_ASYNC_FIFO_SV
