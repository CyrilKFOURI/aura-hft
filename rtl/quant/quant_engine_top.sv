`ifndef QUANT_ENGINE_TOP_SV
`define QUANT_ENGINE_TOP_SV

`timescale 1ns / 1ps

`include "lob_pkg.sv"

/**
 * quant_engine_top.sv
 *
 * Top-Level Quantitative Engine (AURA-HFT).
 * Interconnects:
 *   - obi_calculator: Computes OBI (Q1.31) and Micro-Price at line rate.
 *   - queue_tracker: Computes FIFO queue position and priority for proprietary orders.
 */

module quant_engine_top #(
    parameter int unsigned NUM_TRACKED_ORDERS = 4
) (
    input  logic        clk,
    input  logic        rst_n,

    // BBO Inputs from LOB Top-of-Book Cache
    input  logic        bbo_valid,
    input  logic [31:0] best_bid_price,
    input  logic [31:0] best_bid_shares,
    input  logic [31:0] best_ask_price,
    input  logic [31:0] best_ask_shares,
    input  logic [31:0] spread,

    // Depletion Events from LOB Engine
    input  logic        event_valid,
    input  logic        event_side,
    input  logic [31:0] event_price,
    input  logic [31:0] event_shares_reduced,

    // User Configuration for Tracked Orders
    input  logic        cfg_valid,
    input  logic [1:0]  cfg_slot_idx,
    input  logic        cfg_side,
    input  logic [31:0] cfg_price,
    input  logic [31:0] cfg_shares,
    input  logic [31:0] cfg_initial_volume,
    input  logic        cfg_cancel,

    // Quantitative Output Signals
    output logic               obi_valid,
    output logic signed [31:0] obi_val,
    output logic [31:0]        micro_price,
    output logic [31:0]        quant_bid_price,
    output logic [31:0]        quant_ask_price,
    output logic [31:0]        quant_spread,

    // Queue Tracker Output Status
    output logic [NUM_TRACKED_ORDERS-1:0]        slot_active,
    output logic [NUM_TRACKED_ORDERS-1:0][31:0]  slot_volume_ahead,
    output logic [NUM_TRACKED_ORDERS-1:0]        slot_is_top_of_queue
);

    // Instantiate OBI and Micro-Price Calculator
    obi_calculator #(
        .PIPELINE_STAGES(32)
    ) u_obi_calc (
        .clk            (clk),
        .rst_n          (rst_n),
        .bbo_valid      (bbo_valid),
        .best_bid_price (best_bid_price),
        .best_bid_shares(best_bid_shares),
        .best_ask_price (best_ask_price),
        .best_ask_shares(best_ask_shares),
        .spread         (spread),
        .obi_valid      (obi_valid),
        .obi_val        (obi_val),
        .micro_price    (micro_price),
        .out_bid_price  (quant_bid_price),
        .out_ask_price  (quant_ask_price),
        .out_spread     (quant_spread)
    );

    // Instantiate Queue Tracker
    queue_tracker #(
        .NUM_ORDERS(NUM_TRACKED_ORDERS)
    ) u_queue_tracker (
        .clk                 (clk),
        .rst_n               (rst_n),
        .cfg_valid           (cfg_valid),
        .cfg_slot_idx        (cfg_slot_idx),
        .cfg_side            (cfg_side),
        .cfg_price           (cfg_price),
        .cfg_shares          (cfg_shares),
        .cfg_initial_volume  (cfg_initial_volume),
        .cfg_cancel          (cfg_cancel),
        .event_valid         (event_valid),
        .event_side          (event_side),
        .event_price         (event_price),
        .event_shares_reduced(event_shares_reduced),
        .slot_active         (slot_active),
        .slot_volume_ahead   (slot_volume_ahead),
        .slot_is_top_of_queue(slot_is_top_of_queue)
    );

endmodule : quant_engine_top

`endif // QUANT_ENGINE_TOP_SV
