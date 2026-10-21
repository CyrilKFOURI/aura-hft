// ============================================================================
// File: ptp_timer_96b.sv
// Description: IEEE 1588-2008 PTP 96-bit Hardware Timer with Fractional Sub-ns Accumulator
// Standard:
//   - [95:48] : 48-bit Seconds (UNIX epoch)
//   - [47:16] : 32-bit Nanoseconds (0 to 999,999,999)
//   - [15:0]  : 16-bit Fractional Nanoseconds (2^-16 ns ~ 15.25 ps)
// Clock:
//   - Tuned for 156.25 MHz (6.4 ns per cycle -> step_ns = 6, step_fns = 26214)
// ============================================================================

`timescale 1ns / 1ps

module ptp_timer_96b #(
    parameter int DEFAULT_STEP_NS  = 6,
    parameter int DEFAULT_STEP_FNS = 26214 // 0.4 * 65536 = 26214.4
)(
    input  logic        clk,
    input  logic        rst_n,

    // Step configuration (for fine-grain frequency tuning via software/servo)
    input  logic [7:0]  cfg_step_ns,
    input  logic [15:0] cfg_step_fns,
    input  logic        cfg_step_load,

    // Time synchronization / PPS reload
    input  logic        load_en,
    input  logic [95:0] load_timestamp,

    // PTP Timestamp output
    output logic [95:0] ptp_timestamp,
    output logic [47:0] ptp_sec,
    output logic [31:0] ptp_ns,
    output logic [15:0] ptp_fns,
    output logic        pps_pulse
);

    logic [47:0] sec_reg;
    logic [31:0] ns_reg;
    logic [15:0] fns_reg;

    logic [7:0]  step_ns_reg;
    logic [15:0] step_fns_reg;

    // Internal sum registers
    logic [16:0] fns_sum;
    logic [32:0] ns_sum;

    always_comb begin
        fns_sum = {1'b0, fns_reg} + {1'b0, step_fns_reg};
        ns_sum  = {1'b0, ns_reg} + {25'd0, step_ns_reg} + {32'd0, fns_sum[16]};
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sec_reg       <= 48'd0;
            ns_reg        <= 32'd0;
            fns_reg       <= 16'd0;
            step_ns_reg   <= 8'(DEFAULT_STEP_NS);
            step_fns_reg  <= 16'(DEFAULT_STEP_FNS);
            pps_pulse     <= 1'b0;
        end else begin
            pps_pulse <= 1'b0;

            if (cfg_step_load) begin
                step_ns_reg  <= cfg_step_ns;
                step_fns_reg <= cfg_step_fns;
            end

            if (load_en) begin
                sec_reg <= load_timestamp[95:48];
                ns_reg  <= load_timestamp[47:16];
                fns_reg <= load_timestamp[15:0];
            end else begin
                fns_reg <= fns_sum[15:0];
                if (ns_sum >= 33'd1_000_000_000) begin
                    ns_reg    <= 32'(ns_sum - 33'd1_000_000_000);
                    sec_reg   <= sec_reg + 48'd1;
                    pps_pulse <= 1'b1;
                end else begin
                    ns_reg <= ns_sum[31:0];
                end
            end
        end
    end

    assign ptp_sec       = sec_reg;
    assign ptp_ns        = ns_reg;
    assign ptp_fns       = fns_reg;
    assign ptp_timestamp = {sec_reg, ns_reg, fns_reg};

endmodule
