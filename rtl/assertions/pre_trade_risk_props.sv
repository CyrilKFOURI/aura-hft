// ============================================================================
// pre_trade_risk_props.sv - safety invariants of the pre-trade risk path (P3b).
//
// Checker module bound into pre_trade_risk (Verilator --assert, see
// pre_trade_risk_bind.sv) and instantiated by formal/risk_formal_top.sv
// (yosys + yosys-smtbmc, BMC + k-induction).
//
// Timing reference: stage A samples the intent, kill switch, max shares and
// collar at cycle t; stage B compares the notional against the limits at
// t+1; risk_approved / out_* are visible at t+2. Every property therefore
// checks an approval against the configuration the RTL actually saw.
//
//   P1 no approval (hence no OUCH order: ouch_order_gen.order_valid is wired
//      to risk_approved) unless the kill switch was low at t and t+1
//   P2 approved shares     <= max order shares        (when the limit is set)
//   P3 approved price      inside the BBO collar      (when collar and BBO set)
//   P4 approved notional   <= max order notional      (when the limit is set;
//      notional = shares x price of the intent that produced the approval)
//   P5 accumulated notional <= cumulative limit after an approval
//   P6 approved and rejected strobes never both high
// Plain immediate assertions in a clocked block: accepted by Verilator and by
// the open-source yosys front-end alike.
// ============================================================================

`ifndef PRE_TRADE_RISK_PROPS_SV
`define PRE_TRADE_RISK_PROPS_SV

module pre_trade_risk_props (
    input logic        clk,
    input logic        rst_n,
    input logic        cfg_kill_switch,
    input logic        cfg_circuit_breaker_tripped,
    input logic [31:0] cfg_max_order_shares,
    input logic [31:0] cfg_price_collar_threshold,
    input logic [63:0] cfg_max_notional_raw,
    input logic [63:0] cfg_max_cum_notional_raw,
    input logic [31:0] bbo_bid_price,
    input logic [31:0] bbo_ask_price,
    input logic [31:0] intent_shares,
    input logic [31:0] intent_price,
    input logic        risk_approved,
    input logic        risk_rejected,
    input logic        out_side,
    input logic [31:0] out_shares,
    input logic [31:0] out_price,
    input logic [63:0] accumulated_notional_raw
);

    // History of the inputs, one and two cycles back (reset-qualified).
    logic [1:0]  hist_ok;
    logic        kill_1, kill_2, cb_1, cb_2;
    logic [31:0] max_sh_2, collar_2, bid_2, ask_2;
    logic [31:0] max_sh_1, collar_1, bid_1, ask_1;
    logic [63:0] max_not_1, max_cum_1, acc_1;
    logic [63:0] not_1, not_2;
    // Notional of the intent, computed from the same operands as the RTL
    // product (a single shared multiplier after opt_merge in the formal flow).
    wire  [63:0] intent_notional = 64'(intent_shares) * 64'(intent_price);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            hist_ok <= 2'b00;
            kill_1 <= 1'b0; kill_2 <= 1'b0; cb_1 <= 1'b0; cb_2 <= 1'b0;
            max_sh_1 <= '0; collar_1 <= '0; bid_1 <= '0; ask_1 <= '0;
            max_sh_2 <= '0; collar_2 <= '0; bid_2 <= '0; ask_2 <= '0;
            max_not_1 <= '0; max_cum_1 <= '0; acc_1 <= '0;
            not_1 <= '0; not_2 <= '0;
        end else begin
            hist_ok  <= {hist_ok[0], 1'b1};
            kill_1   <= cfg_kill_switch;            kill_2   <= kill_1;
            cb_1     <= cfg_circuit_breaker_tripped; cb_2     <= cb_1;
            max_sh_1 <= cfg_max_order_shares;       max_sh_2 <= max_sh_1;
            collar_1 <= cfg_price_collar_threshold; collar_2 <= collar_1;
            bid_1    <= bbo_bid_price;              bid_2    <= bid_1;
            ask_1    <= bbo_ask_price;              ask_2    <= ask_1;
            max_not_1 <= cfg_max_notional_raw;
            max_cum_1 <= cfg_max_cum_notional_raw;
            acc_1     <= accumulated_notional_raw;
            not_1     <= intent_notional;           not_2    <= not_1;
        end
    end

    wire        full_hist = rst_n && hist_ok[1];
    wire [64:0] cum_sum_1 = {1'b0, acc_1} + {1'b0, not_2};
    wire [64:0] collar_hi = {33'd0, ask_2} + {33'd0, collar_2};

    always_ff @(posedge clk) begin
        if (full_hist) begin
            // P6
            assert (!(risk_approved && risk_rejected));
            if (risk_approved) begin
                // P1 (and the PnL breaker, same structure)
                assert (!kill_1 && !kill_2);
                assert (!cb_1 && !cb_2);
                // P2
                assert ((max_sh_2 == 32'd0) || (out_shares <= max_sh_2));
                // P3
                if (collar_2 != 32'd0) begin
                    if (!out_side && ask_2 != 32'd0)
                        assert ({33'd0, out_price} <= collar_hi);
                    if (out_side && bid_2 > collar_2)
                        assert (out_price >= bid_2 - collar_2);
                end
                // P4
                assert ((max_not_1 == 64'd0) || (not_2 <= max_not_1));
                // P5: the new accumulated value is the (saturated) sum, and within the limit
                assert (accumulated_notional_raw == (cum_sum_1[64] ? {64{1'b1}} : cum_sum_1[63:0]));
                assert ((max_cum_1 == 64'd0) || (accumulated_notional_raw <= max_cum_1));
            end
        end
    end

endmodule : pre_trade_risk_props

`endif // PRE_TRADE_RISK_PROPS_SV
