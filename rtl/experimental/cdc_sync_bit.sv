// ============================================================================
// Module Name:   cdc_sync_bit
// Description:   Double-Flop Clock Domain Crossing (CDC) Synchronizer for
//                single-bit control signals and strobes.
//                Infers Xilinx ASYNC_REG attribute to prevent synthesis
//                merging and optimize placement in adjacent slices.
// Standard:      SystemVerilog IEEE 1800-2017
// Target:        AMD Kria KR260 / UltraScale+
// ============================================================================

`ifndef CDC_SYNC_BIT_SV
`define CDC_SYNC_BIT_SV

`timescale 1ns / 1ps

module cdc_sync_bit #(
    parameter bit INIT_VALUE = 1'b0,
    parameter int STAGES     = 2
)(
    input  logic dest_clk,
    input  logic dest_rst_n,
    input  logic src_signal,
    output logic dest_signal
);

    (* ASYNC_REG = "TRUE" *) logic [STAGES-1:0] sync_reg;

    always_ff @(posedge dest_clk or negedge dest_rst_n) begin
        if (!dest_rst_n) begin
            sync_reg <= {STAGES{INIT_VALUE}};
        end else begin
            sync_reg <= {sync_reg[STAGES-2:0], src_signal};
        end
    end

    assign dest_signal = sync_reg[STAGES-1];

endmodule : cdc_sync_bit

`endif // CDC_SYNC_BIT_SV
