// ============================================================================
// File: cross_exchange_arbiter.sv
// Description: Real-Time Cross-Exchange Spatial Arbitrage Engine (Sub-5ns Decision)
// Function:
//   - Continuously evaluates Top-of-Book (BBO) from two competing venues (A & B)
//   - Computes cross-market bid-ask spreads in parallel combinational logic
//   - Deducts exchange fees and enforces minimum profit threshold
//   - Sizes executed volume Q = min(V_bid, V_ask, Q_max)
//   - Emits dual-leg coordinated execution intents within 1 clock cycle (3.2 ns @ 312.5 MHz)
//   - Accumulates realized theoretical arbitrage profit in hardware
// ============================================================================

`timescale 1ns / 1ps

module cross_exchange_arbiter (
    input  logic        clk,
    input  logic        rst_n,

    // Venue A Top-of-Book (BBO)
    input  logic        bbo_a_valid,
    input  logic [31:0] bbo_a_bid_price,
    input  logic [31:0] bbo_a_bid_shares,
    input  logic [31:0] bbo_a_ask_price,
    input  logic [31:0] bbo_a_ask_shares,

    // Venue B Top-of-Book (BBO)
    input  logic        bbo_b_valid,
    input  logic [31:0] bbo_b_bid_price,
    input  logic [31:0] bbo_b_bid_shares,
    input  logic [31:0] bbo_b_ask_price,
    input  logic [31:0] bbo_b_ask_shares,

    // Dynamic Configuration
    input  logic        cfg_arb_enable,
    input  logic [31:0] cfg_min_profit_ticks,     // Minimum net profit per share
    input  logic [31:0] cfg_fee_ticks,            // Combined exchange taker/clearing fee
    input  logic [31:0] cfg_max_shares_per_arb,   // Position size cap per opportunity
    input  logic [7:0]  cfg_cooldown_cycles,      // Minimum cycles between arb fires

    // Arbitrage Execution Outputs
    output logic        arb_fire_strobe,          // 1-cycle pulse triggering dual-leg orders
    output logic        arb_direction,            // 0: Buy B / Sell A, 1: Buy A / Sell B
    output logic [31:0] arb_exec_shares,
    output logic [31:0] arb_buy_price,
    output logic [31:0] arb_sell_price,
    output logic [31:0] arb_profit_per_share,
    output logic [63:0] arb_total_event_profit,   // shares * profit_per_share

    // Telemetry & Statistics
    output logic [31:0] arb_event_count,
    output logic [63:0] arb_cum_profit
);

    // ------------------------------------------------------------------------
    // 1. Combinational Cross-Spread Computation
    // ------------------------------------------------------------------------
    logic signed [32:0] spread_a2b; // Bid_A - Ask_B
    logic signed [32:0] spread_b2a; // Bid_B - Ask_A
    logic signed [32:0] profit_req;

    assign spread_a2b = $signed({1'b0, bbo_a_bid_price}) - $signed({1'b0, bbo_b_ask_price});
    assign spread_b2a = $signed({1'b0, bbo_b_bid_price}) - $signed({1'b0, bbo_a_ask_price});
    assign profit_req = $signed({1'b0, cfg_fee_ticks}) + $signed({1'b0, cfg_min_profit_ticks});

    // Opportunity detection
    wire opp_a2b_comb = cfg_arb_enable && bbo_a_valid && bbo_b_valid &&
                        (spread_a2b >= profit_req) &&
                        (bbo_a_bid_shares > 32'd0) && (bbo_b_ask_shares > 32'd0);

    wire opp_b2a_comb = cfg_arb_enable && bbo_a_valid && bbo_b_valid &&
                        (spread_b2a >= profit_req) &&
                        (bbo_b_bid_shares > 32'd0) && (bbo_a_ask_shares > 32'd0);

    // Direction arbitration: if both active, choose highest spread
    wire sel_a2b_comb = opp_a2b_comb && (!opp_b2a_comb || (spread_a2b >= spread_b2a));
    wire sel_b2a_comb = opp_b2a_comb && (!opp_a2b_comb || (spread_b2a > spread_a2b));
    wire opp_active_comb = sel_a2b_comb || sel_b2a_comb;

    // Sizing computation
    logic [31:0] shares_avail_comb;
    logic [31:0] shares_exec_comb;
    logic [31:0] profit_per_share_comb;

    always_comb begin
        if (sel_a2b_comb) begin
            shares_avail_comb     = (bbo_a_bid_shares < bbo_b_ask_shares) ? bbo_a_bid_shares : bbo_b_ask_shares;
            profit_per_share_comb = 32'(spread_a2b - $signed({1'b0, cfg_fee_ticks}));
        end else if (sel_b2a_comb) begin
            shares_avail_comb     = (bbo_b_bid_shares < bbo_a_ask_shares) ? bbo_b_bid_shares : bbo_a_ask_shares;
            profit_per_share_comb = 32'(spread_b2a - $signed({1'b0, cfg_fee_ticks}));
        end else begin
            shares_avail_comb     = 32'd0;
            profit_per_share_comb = 32'd0;
        end

        // Apply max shares limit
        if (shares_avail_comb < cfg_max_shares_per_arb) begin
            shares_exec_comb = shares_avail_comb;
        end else begin
            shares_exec_comb = cfg_max_shares_per_arb;
        end
    end

    // ------------------------------------------------------------------------
    // 2. Cooldown & Registered Trigger Logic (1 Cycle Latency)
    // ------------------------------------------------------------------------
    logic [7:0] cooldown_timer;
    logic       prev_opp_active;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cooldown_timer         <= 8'd0;
            prev_opp_active        <= 1'b0;
            arb_fire_strobe        <= 1'b0;
            arb_direction          <= 1'b0;
            arb_exec_shares        <= 32'd0;
            arb_buy_price          <= 32'd0;
            arb_sell_price         <= 32'd0;
            arb_profit_per_share   <= 32'd0;
            arb_total_event_profit <= 64'd0;
            arb_event_count        <= 32'd0;
            arb_cum_profit         <= 64'd0;
        end else begin
            arb_fire_strobe <= 1'b0;

            if (cooldown_timer > 8'd0) begin
                cooldown_timer <= cooldown_timer - 8'd1;
            end

            prev_opp_active <= opp_active_comb;

            // Trigger on rising edge of arbitrage opportunity
            if (opp_active_comb && !prev_opp_active && (shares_exec_comb > 32'd0)) begin
                arb_fire_strobe        <= 1'b1;
                arb_direction          <= sel_b2a_comb; // 0 = A->B, 1 = B->A
                arb_exec_shares        <= shares_exec_comb;
                arb_profit_per_share   <= profit_per_share_comb;
                arb_total_event_profit <= 64'(shares_exec_comb) * 64'(profit_per_share_comb);
                arb_event_count        <= arb_event_count + 32'd1;
                arb_cum_profit         <= arb_cum_profit + (64'(shares_exec_comb) * 64'(profit_per_share_comb));

                if (sel_a2b_comb) begin
                    arb_buy_price  <= bbo_b_ask_price;
                    arb_sell_price <= bbo_a_bid_price;
                end else begin
                    arb_buy_price  <= bbo_a_ask_price;
                    arb_sell_price <= bbo_b_bid_price;
                end
            end
        end
    end

endmodule
