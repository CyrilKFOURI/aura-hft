// ============================================================================
// File: axis_eth_fcs_checker.sv
// Description: Cut-Through 64-bit AXI-Stream Ethernet FCS CRC-32 Checker
// Standard:
//   - IEEE 802.3 CRC-32 polynomial: 0x04C11DB7 (reversed: 0xEDB88320)
//   - Initial CRC: 0xFFFFFFFF, Final inversion: ~crc
//   - Zero-latency cut-through: s_axis is forwarded directly to m_axis
//   - Parallel combinational CRC-32 calculation over 1 to 8 active bytes (tkeep)
//   - Frame validation strobe & error pulse on tlast
// ============================================================================

`timescale 1ns / 1ps

module axis_eth_fcs_checker #(
    parameter bit CHECK_TRAILING_FCS = 0  // 1: frame includes 4-byte FCS; 0: computes FCS of frame payload
)(
    input  logic        clk,
    input  logic        rst_n,

    // AXI-Stream Slave (from MAC / PHY)
    input  logic [63:0] s_axis_tdata,
    input  logic [7:0]  s_axis_tkeep,
    input  logic        s_axis_tvalid,
    input  logic        s_axis_tlast,
    output logic        s_axis_tready,

    // AXI-Stream Master (cut-through forward to Ingress pipeline)
    output logic [63:0] m_axis_tdata,
    output logic [7:0]  m_axis_tkeep,
    output logic        m_axis_tvalid,
    output logic        m_axis_tlast,
    input  logic        m_axis_tready,

    // Expected FCS input (optional sideband check when CHECK_TRAILING_FCS = 0)
    input  logic        expected_fcs_valid,
    input  logic [31:0] expected_fcs,

    // Metrology & Status
    output logic [31:0] fcs_calculated,
    output logic        fcs_valid,
    output logic        fcs_error,
    output logic [31:0] frame_count,
    output logic [31:0] fcs_error_count
);

    // Cut-through connection: 0 cycle latency pass-through
    assign m_axis_tdata  = s_axis_tdata;
    assign m_axis_tkeep  = s_axis_tkeep;
    assign m_axis_tvalid = s_axis_tvalid;
    assign m_axis_tlast  = s_axis_tlast;
    assign s_axis_tready = m_axis_tready;

    // CRC-32 byte calculation (IEEE 802.3 standard bit-reversed)
    function automatic [31:0] next_crc32_byte(input [31:0] current_crc, input [7:0] byte_in);
        logic [31:0] c;
        c = current_crc ^ {24'h0, byte_in};
        for (int i = 0; i < 8; i = i + 1) begin
            if (c[0]) begin
                c = (c >> 1) ^ 32'hEDB88320;
            end else begin
                c = c >> 1;
            end
        end
        return c;
    endfunction

    // 64-bit parallel CRC step
    function automatic [31:0] next_crc32_d64(input [31:0] current_crc, input [63:0] data, input [7:0] keep);
        logic [31:0] c;
        c = current_crc;
        for (int i = 0; i < 8; i = i + 1) begin
            if (keep[i]) begin
                c = next_crc32_byte(c, data[8*i +: 8]);
            end
        end
        return c;
    endfunction

    // CRC State Tracking
    logic [31:0] crc_state;
    logic [31:0] crc_next;
    logic        in_frame;

    always_comb begin
        if (!in_frame) begin
            crc_next = next_crc32_d64(32'hFFFFFFFF, s_axis_tdata, s_axis_tkeep);
        end else begin
            crc_next = next_crc32_d64(crc_state, s_axis_tdata, s_axis_tkeep);
        end
    end

    // Standard residue when computing over data + 4 bytes FCS (with final inversion)
    localparam logic [31:0] CRC32_ETH_RESIDUE = 32'h2144DF1C;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            crc_state       <= 32'hFFFFFFFF;
            in_frame        <= 1'b0;
            fcs_calculated  <= 32'h0;
            fcs_valid       <= 1'b0;
            fcs_error       <= 1'b0;
            frame_count     <= 32'd0;
            fcs_error_count <= 32'd0;
        end else begin
            fcs_valid <= 1'b0;
            fcs_error <= 1'b0;

            if (s_axis_tvalid && s_axis_tready) begin
                if (s_axis_tlast) begin
                    // End of frame reached
                    in_frame <= 1'b0;
                    crc_state <= 32'hFFFFFFFF;
                    frame_count <= frame_count + 32'd1;
                    fcs_valid <= 1'b1;

                    // Final calculated CRC (inverted)
                    fcs_calculated <= ~crc_next;

                    if (CHECK_TRAILING_FCS) begin
                        // Check against Ethernet magic residue
                        if ((~crc_next) != CRC32_ETH_RESIDUE) begin
                            fcs_error <= 1'b1;
                            fcs_error_count <= fcs_error_count + 32'd1;
                        end
                    end else if (expected_fcs_valid) begin
                        // Check against sideband expected FCS
                        if ((~crc_next) != expected_fcs) begin
                            fcs_error <= 1'b1;
                            fcs_error_count <= fcs_error_count + 32'd1;
                        end
                    end
                end else begin
                    // Intermediate frame beat
                    in_frame  <= 1'b1;
                    crc_state <= crc_next;
                end
            end
        end
    end

endmodule
