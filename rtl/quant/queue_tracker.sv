`ifndef QUEUE_TRACKER_SV
`define QUEUE_TRACKER_SV

`timescale 1ns / 1ps

/**
 * queue_tracker.sv
 *
 * Microstructure Queue Position Estimator (AURA-HFT).
 * Tracks the FIFO priority of passive proprietary limit orders:
 *   - Registers initial volume ahead at posting time.
 *   - Decrements volume ahead in real-time on executions ('E','C') and cancels ('X','D').
 *   - Asserts is_top_of_queue flag as soon as volume ahead reaches 0 (highest fill priority).
 *
 * Supports up to NUM_ORDERS concurrent active tracked orders.
 */

module queue_tracker #(
    parameter int unsigned NUM_ORDERS = 4
) (
    input  logic        clk,
    input  logic        rst_n,

    // Configuration / Placement of Tracked Orders
    input  logic        cfg_valid,
    input  logic [1:0]  cfg_slot_idx,
    input  logic        cfg_side,             // 1'b0: Buy, 1'b1: Sell
    input  logic [31:0] cfg_price,
    input  logic [31:0] cfg_shares,
    input  logic [31:0] cfg_initial_volume,   // Depth ahead at posting
    input  logic        cfg_cancel,           // Cancel/deactivate tracked order in slot

    // LOB Execution / Depletion Events
    input  logic        event_valid,
    input  logic        event_side,
    input  logic [31:0] event_price,
    input  logic [31:0] event_shares_reduced,

    // Status per slot
    output logic [NUM_ORDERS-1:0]        slot_active,
    output logic [NUM_ORDERS-1:0][31:0]  slot_volume_ahead,
    output logic [NUM_ORDERS-1:0]        slot_is_top_of_queue
);

    // Tracking registers per slot
    logic        reg_active        [0:NUM_ORDERS-1];
    logic        reg_side          [0:NUM_ORDERS-1];
    logic [31:0] reg_price         [0:NUM_ORDERS-1];
    logic [31:0] reg_shares        [0:NUM_ORDERS-1];
    logic [31:0] reg_volume_ahead  [0:NUM_ORDERS-1];
    logic        reg_is_top        [0:NUM_ORDERS-1];

    genvar s;
    generate
        for (s = 0; s < NUM_ORDERS; s++) begin : gen_slots
            assign slot_active[s]          = reg_active[s];
            assign slot_volume_ahead[s]    = reg_volume_ahead[s];
            assign slot_is_top_of_queue[s] = reg_is_top[s];

            always_ff @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    reg_active[s]       <= 1'b0;
                    reg_side[s]         <= 1'b0;
                    reg_price[s]        <= '0;
                    reg_shares[s]       <= '0;
                    reg_volume_ahead[s] <= '0;
                    reg_is_top[s]       <= 1'b0;
                end else begin
                    // Priority 1: Configuration / Placement / Cancellation
                    if (cfg_valid && (cfg_slot_idx == 2'(s))) begin
                        if (cfg_cancel) begin
                            reg_active[s]       <= 1'b0;
                            reg_is_top[s]       <= 1'b0;
                            reg_volume_ahead[s] <= '0;
                        end else begin
                            reg_active[s]       <= 1'b1;
                            reg_side[s]         <= cfg_side;
                            reg_price[s]        <= cfg_price;
                            reg_shares[s]       <= cfg_shares;
                            reg_volume_ahead[s] <= cfg_initial_volume;
                            reg_is_top[s]       <= (cfg_initial_volume == 32'd0);
                        end
                    end
                    // Priority 2: Real-time Queue Depletion from Market Events
                    else if (reg_active[s] && event_valid) begin
                        if ((event_side == reg_side[s]) && (event_price == reg_price[s])) begin
                            if (reg_volume_ahead[s] > event_shares_reduced) begin
                                reg_volume_ahead[s] <= reg_volume_ahead[s] - event_shares_reduced;
                                reg_is_top[s]       <= 1'b0;
                            end else begin
                                reg_volume_ahead[s] <= 32'd0;
                                reg_is_top[s]       <= 1'b1;
                            end
                        end
                    end
                end
            end
        end
    endgenerate

endmodule : queue_tracker

`endif // QUEUE_TRACKER_SV
