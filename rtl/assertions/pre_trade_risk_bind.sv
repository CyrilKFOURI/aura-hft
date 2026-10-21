// Binds the risk safety checker into every pre_trade_risk instance.
// Simulation: add rtl/assertions/*.sv and --assert to the Verilator build.
`ifndef PRE_TRADE_RISK_BIND_SV
`define PRE_TRADE_RISK_BIND_SV

bind pre_trade_risk pre_trade_risk_props u_risk_props (
    .clk                        (clk),
    .rst_n                      (rst_n),
    .cfg_kill_switch            (cfg_kill_switch),
    .cfg_circuit_breaker_tripped(cfg_circuit_breaker_tripped),
    .cfg_max_order_shares       (cfg_max_order_shares),
    .cfg_price_collar_threshold (cfg_price_collar_threshold),
    .cfg_max_notional_raw       (cfg_max_notional_raw),
    .cfg_max_cum_notional_raw   (cfg_max_cum_notional_raw),
    .bbo_bid_price              (bbo_bid_price),
    .bbo_ask_price              (bbo_ask_price),
    .intent_shares              (intent_shares),
    .intent_price               (intent_price),
    .risk_approved              (risk_approved),
    .risk_rejected              (risk_rejected),
    .out_side                   (out_side),
    .out_shares                 (out_shares),
    .out_price                  (out_price),
    .accumulated_notional_raw   (accumulated_notional_raw)
);

`endif // PRE_TRADE_RISK_BIND_SV
