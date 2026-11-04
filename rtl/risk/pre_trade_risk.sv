`ifndef PRE_TRADE_RISK_SV
`define PRE_TRADE_RISK_SV

`timescale 1ns / 1ps

`include "ouch_pkg.sv"

/**
 * pre_trade_risk.sv
 *
 * Deterministic 1-Cycle Pre-Trade Risk Engine (AURA-HFT).
 * Evaluates 5 financial risk rules in parallel:
 *   1. Hard Kill Switch: Emergency cutoff preventing all outbound orders.
 *   2. Max Order Shares: Single-order size boundary.
 *   3. Price Collar vs BBO: Prevents fat-finger aggressive limit orders.
 *   4. Max Order Notional: Bounds total dollar value per order.
 *   5. Cumulative Notional: Bounds total daily capital commitment.
 */

module pre_trade_risk (
    input  logic        clk,
    input  logic        rst_n,

    // Dynamic Risk Configuration Parameters
    input  logic        cfg_kill_switch,            // 1'b1 = Hard Kill Switch Active
    input  logic        cfg_circuit_breaker_tripped,// 1'b1 = Reflex PnL Drawdown Breaker Tripped
    input  logic [31:0] cfg_max_order_shares,       // e.g. 1,000 shares
    input  logic [31:0] cfg_price_collar_threshold, // e.g. 5,000 = $0.5000
    input  logic [63:0] cfg_max_notional_raw,       // (max_dollars * 10000)
    input  logic [63:0] cfg_max_cum_notional_raw,   // cumulative boundary

    // Live Reference BBO Prices
    input  logic [31:0] bbo_bid_price,
    input  logic [31:0] bbo_ask_price,

    // Inbound Order Intent from Strategy Engine
    input  logic        intent_valid,
    input  logic        intent_side,                // 1'b0: Buy, 1'b1: Sell
    input  logic [31:0] intent_shares,
    input  logic [31:0] intent_price,
    input  logic [63:0] intent_stock,
    input  logic [31:0] intent_token,
    input  logic [47:0] intent_timestamp,

    // Outbound Risk Decision & Approved Order to OUCH Transmitter
    output logic        risk_approved,
    output logic        risk_rejected,
    output logic [3:0]  reject_reason,              // risk_reject_reason_e

    output logic        out_side,
    output logic [31:0] out_shares,
    output logic [31:0] out_price,
    output logic [63:0] out_stock,
    output logic [31:0] out_token,
    output logic [47:0] out_timestamp,

    // Cumulative Tracking Telemetry
    output logic [63:0] accumulated_notional_raw,
    output logic [31:0] total_orders_approved,
    output logic [31:0] total_orders_rejected
);

    import ouch_pkg::*;

    // Combinational Risk Evaluation
    logic [63:0] current_notional_raw;
    logic        kill_switch_violation;
    logic        circuit_breaker_violation;
    logic        max_shares_violation;
    logic        collar_violation;
    logic        notional_violation;
    logic        cum_notional_violation;

    logic [3:0]  comb_reason;
    logic        comb_pass;

    always_comb begin
        current_notional_raw = 64'(intent_shares) * 64'(intent_price);

        // 1. Hard Kill Switch & Circuit Breaker Check
        kill_switch_violation = cfg_kill_switch;
        circuit_breaker_violation = cfg_circuit_breaker_tripped;

        // 2. Max Shares Check
        max_shares_violation = (cfg_max_order_shares > 32'd0) && (intent_shares > cfg_max_order_shares);

        // 3. Price Collar Check vs Live BBO
        collar_violation = 1'b0;
        if (cfg_price_collar_threshold > 32'd0) begin
            if (intent_side == 1'b0) begin
                // Buy order: cannot exceed (Ask + Collar)
                if ((bbo_ask_price > 32'd0) && (intent_price > (bbo_ask_price + cfg_price_collar_threshold))) begin
                    collar_violation = 1'b1;
                end
            end else begin
                // Sell order: cannot fall below (Bid - Collar)
                if ((bbo_bid_price > 32'd0) && (bbo_bid_price > cfg_price_collar_threshold)) begin
                    if (intent_price < (bbo_bid_price - cfg_price_collar_threshold)) begin
                        collar_violation = 1'b1;
                    end
                end
            end
        end

        // 4. Single-Order Max Notional Check
        notional_violation = (cfg_max_notional_raw > 64'd0) && (current_notional_raw > cfg_max_notional_raw);

        // 5. Cumulative Daily Notional Check
        cum_notional_violation = (cfg_max_cum_notional_raw > 64'd0) &&
                                 ((accumulated_notional_raw + current_notional_raw) > cfg_max_cum_notional_raw);

        // Strict priority evaluation of reject reasons
        if (kill_switch_violation) begin
            comb_reason = RISK_REJECT_KILL_SWITCH;
            comb_pass   = 1'b0;
        end else if (circuit_breaker_violation) begin
            comb_reason = RISK_REJECT_CIRCUIT_BREAKER;
            comb_pass   = 1'b0;
        end else if (max_shares_violation) begin
            comb_reason = RISK_REJECT_MAX_SHARES;
            comb_pass   = 1'b0;
        end else if (collar_violation) begin
            comb_reason = RISK_REJECT_PRICE_COLLAR;
            comb_pass   = 1'b0;
        end else if (notional_violation) begin
            comb_reason = RISK_REJECT_MAX_NOTIONAL;
            comb_pass   = 1'b0;
        end else if (cum_notional_violation) begin
            comb_reason = RISK_REJECT_CUMULATIVE_NOTIONAL;
            comb_pass   = 1'b0;
        end else begin
            comb_reason = RISK_PASS;
            comb_pass   = 1'b1;
        end
    end

    // Sequential update of decisions and telemetry registers (1-cycle deterministic latency)
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            risk_approved            <= 1'b0;
            risk_rejected            <= 1'b0;
            reject_reason            <= RISK_PASS;
            out_side                 <= 1'b0;
            out_shares               <= '0;
            out_price                <= '0;
            out_stock                <= '0;
            out_token                <= '0;
            out_timestamp            <= '0;
            accumulated_notional_raw <= '0;
            total_orders_approved    <= '0;
            total_orders_rejected    <= '0;
        end else begin
            // Strobes default to 0
            risk_approved <= 1'b0;
            risk_rejected <= 1'b0;

            if (intent_valid) begin
                if (comb_pass) begin
                    risk_approved            <= 1'b1;
                    reject_reason            <= RISK_PASS;
                    out_side                 <= intent_side;
                    out_shares               <= intent_shares;
                    out_price                <= intent_price;
                    out_stock                <= intent_stock;
                    out_token                <= intent_token;
                    out_timestamp            <= intent_timestamp;
                    accumulated_notional_raw <= accumulated_notional_raw + current_notional_raw;
                    total_orders_approved    <= total_orders_approved + 1'b1;
                end else begin
                    risk_rejected         <= 1'b1;
                    reject_reason         <= comb_reason;
                    total_orders_rejected <= total_orders_rejected + 1'b1;
                end
            end
        end
    end

endmodule : pre_trade_risk

`endif // PRE_TRADE_RISK_SV
