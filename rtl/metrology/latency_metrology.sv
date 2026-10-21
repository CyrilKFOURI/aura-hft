// ============================================================================
// File: latency_metrology.sv
// Description: Real-Time Hardware Wire-to-Wire Latency Metrology Unit
// Function:
//   - Captures PTP timestamp at RX SOP (first beat of incoming ITCH frame)
//   - Captures PTP timestamp at TX SOP (first beat of outgoing OUCH frame)
//   - Matches RX and TX timestamps using a hardware FIFO
//   - Computes wire-to-wire latency Delta-t = T_tx - T_rx in nanoseconds
//   - Registers: min_latency, max_latency, last_latency, cum_latency, event_count
// ============================================================================

`timescale 1ns / 1ps

module latency_metrology #(
    parameter int FIFO_DEPTH = 16
)(
    input  logic        clk,
    input  logic        rst_n,

    // Current PTP 96-bit time
    input  logic [95:0] ptp_timestamp,

    // Ingress (RX) and Egress (TX) event triggers
    input  logic        rx_sop,  // Start of packet on RX network stream
    input  logic        tx_sop,  // Start of packet on TX network stream

    // Statistics clear / reset
    input  logic        stats_clear,

    // Metrology Outputs
    output logic [31:0] last_latency_ns,
    output logic [31:0] min_latency_ns,
    output logic [31:0] max_latency_ns,
    output logic [63:0] cum_latency_ns,
    output logic [31:0] event_count,
    output logic        latency_valid
);

    // Unpack PTP time
    wire [47:0] current_sec = ptp_timestamp[95:48];
    wire [31:0] current_ns  = ptp_timestamp[47:16];

    // RX timestamp FIFO (stores {sec[15:0], ns[31:0]} = 48 bits)
    localparam int ADDR_W = $clog2(FIFO_DEPTH);
    logic [47:0] rx_fifo_mem [0:FIFO_DEPTH-1];
    logic [ADDR_W:0] wr_ptr;
    logic [ADDR_W:0] rd_ptr;
    wire fifo_empty = (wr_ptr == rd_ptr);
    wire fifo_full  = (wr_ptr[ADDR_W] != rd_ptr[ADDR_W]) && 
                      (wr_ptr[ADDR_W-1:0] == rd_ptr[ADDR_W-1:0]);

    // Active head of FIFO (combinational read)
    wire [47:0] active_rx_ts = rx_fifo_mem[rd_ptr[ADDR_W-1:0]];

    // Delta-t computation
    logic [31:0] delta_ns;

    always_comb begin
        if (current_sec[15:0] == active_rx_ts[47:32]) begin
            delta_ns = current_ns - active_rx_ts[31:0];
        end else if (current_sec[15:0] == active_rx_ts[47:32] + 16'd1) begin
            delta_ns = (32'd1_000_000_000 + current_ns) - active_rx_ts[31:0];
        end else begin
            delta_ns = 32'hFFFFFFFF; // Overflow / saturated delta
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_ptr          <= '0;
            rd_ptr          <= '0;
            last_latency_ns <= 32'd0;
            min_latency_ns  <= 32'hFFFFFFFF;
            max_latency_ns  <= 32'd0;
            cum_latency_ns  <= 64'd0;
            event_count     <= 32'd0;
            latency_valid   <= 1'b0;
        end else begin
            latency_valid <= 1'b0;

            if (stats_clear) begin
                min_latency_ns <= 32'hFFFFFFFF;
                max_latency_ns <= 32'd0;
                cum_latency_ns <= 64'd0;
                event_count    <= 32'd0;
            end

            // Push RX timestamp on rx_sop
            if (rx_sop && !fifo_full) begin
                rx_fifo_mem[wr_ptr[ADDR_W-1:0]] <= {current_sec[15:0], current_ns};
                wr_ptr <= wr_ptr + 1'b1;
            end

            // Pop and measure on tx_sop
            if (tx_sop && !fifo_empty) begin
                rd_ptr          <= rd_ptr + 1'b1;
                last_latency_ns <= delta_ns;
                cum_latency_ns  <= cum_latency_ns + 64'(delta_ns);
                event_count     <= event_count + 32'd1;
                latency_valid   <= 1'b1;

                if (delta_ns < min_latency_ns) begin
                    min_latency_ns <= delta_ns;
                end
                if (delta_ns > max_latency_ns) begin
                    max_latency_ns <= delta_ns;
                end
            end
        end
    end

endmodule
