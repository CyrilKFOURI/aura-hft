// Formal harness: pre_trade_risk with every input free (any config, any BBO,
// any intent, any cycle) and the safety checker attached. Reset is asserted
// in the first cycle only.
module risk_formal_top (
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
    input logic        intent_valid,
    input logic        intent_side,
    input logic [31:0] intent_shares,
    input logic [31:0] intent_price,
    input logic [63:0] intent_stock,
    input logic [31:0] intent_token,
    input logic [47:0] intent_timestamp
);
    logic        risk_approved, risk_rejected, out_side;
    logic [3:0]  reject_reason;
    logic [31:0] out_shares, out_price, out_token, n_appr, n_rej;
    logic [63:0] out_stock, acc;
    logic [47:0] out_ts;

    reg init = 1'b1;
    always @(posedge clk) init <= 1'b0;
    always @(*) if (init) assume (!rst_n); else assume (rst_n);

    pre_trade_risk dut (
        .clk(clk), .rst_n(rst_n),
        .cfg_kill_switch(cfg_kill_switch), .cfg_circuit_breaker_tripped(cfg_circuit_breaker_tripped),
        .cfg_max_order_shares(cfg_max_order_shares), .cfg_price_collar_threshold(cfg_price_collar_threshold),
        .cfg_max_notional_raw(cfg_max_notional_raw), .cfg_max_cum_notional_raw(cfg_max_cum_notional_raw),
        .bbo_bid_price(bbo_bid_price), .bbo_ask_price(bbo_ask_price),
        .intent_valid(intent_valid), .intent_side(intent_side), .intent_shares(intent_shares),
        .intent_price(intent_price), .intent_stock(intent_stock), .intent_token(intent_token),
        .intent_timestamp(intent_timestamp),
        .risk_approved(risk_approved), .risk_rejected(risk_rejected), .reject_reason(reject_reason),
        .out_side(out_side), .out_shares(out_shares), .out_price(out_price), .out_stock(out_stock),
        .out_token(out_token), .out_timestamp(out_ts),
        .accumulated_notional_raw(acc), .total_orders_approved(n_appr), .total_orders_rejected(n_rej)
    );

    pre_trade_risk_props props (
        .clk(clk), .rst_n(rst_n),
        .cfg_kill_switch(cfg_kill_switch), .cfg_circuit_breaker_tripped(cfg_circuit_breaker_tripped),
        .cfg_max_order_shares(cfg_max_order_shares), .cfg_price_collar_threshold(cfg_price_collar_threshold),
        .cfg_max_notional_raw(cfg_max_notional_raw), .cfg_max_cum_notional_raw(cfg_max_cum_notional_raw),
        .bbo_bid_price(bbo_bid_price), .bbo_ask_price(bbo_ask_price),
        .intent_shares(intent_shares), .intent_price(intent_price),
        .risk_approved(risk_approved), .risk_rejected(risk_rejected),
        .out_side(out_side), .out_shares(out_shares), .out_price(out_price),
        .accumulated_notional_raw(acc)
    );

endmodule
