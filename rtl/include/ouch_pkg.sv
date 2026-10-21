`ifndef OUCH_PKG_SV
`define OUCH_PKG_SV

`timescale 1ns / 1ps

package ouch_pkg;

    // OUCH 5.0 Message Opcodes
    typedef enum logic [7:0] {
        OUCH_MSG_ENTER_ORDER = 8'h4F, // 'O' : Enter Order (49 bytes)
        OUCH_MSG_CANCEL      = 8'h58  // 'X' : Cancel Order
    } ouch_msg_type_e;

    // Pre-Trade Risk Reject Reasons
    typedef enum logic [3:0] {
        RISK_PASS                       = 4'd0,
        RISK_REJECT_KILL_SWITCH         = 4'd1,
        RISK_REJECT_MAX_SHARES          = 4'd2,
        RISK_REJECT_PRICE_COLLAR        = 4'd3,
        RISK_REJECT_MAX_NOTIONAL        = 4'd4,
        RISK_REJECT_CUMULATIVE_NOTIONAL = 4'd5,
        RISK_REJECT_CIRCUIT_BREAKER     = 4'd6
    } risk_reject_reason_e;

    // Strategy Trigger Source
    typedef enum logic [1:0] {
        TRIG_NONE      = 2'd0,
        TRIG_OBI_BUY   = 2'd1,
        TRIG_OBI_SELL  = 2'd2,
        TRIG_QUEUE_TOP = 2'd3
    } strategy_trigger_e;

    // Packet Lengths
    localparam int unsigned OUCH_ENTER_ORDER_BYTES = 49;
    localparam int unsigned ETH_HDR_BYTES          = 14;
    localparam int unsigned IP_HDR_BYTES           = 20;
    localparam int unsigned UDP_HDR_BYTES          = 8;
    localparam int unsigned TOTAL_FRAME_BYTES      = ETH_HDR_BYTES + IP_HDR_BYTES + UDP_HDR_BYTES + OUCH_ENTER_ORDER_BYTES; // 91 bytes

    // Order Intent Request Structure
    typedef struct packed {
        logic        valid;
        logic        side;          // 1'b0: Buy ('B'), 1'b1: Sell ('S')
        logic [31:0] shares;
        logic [31:0] price;         // 4 decimal places
        logic [63:0] stock;         // 8-character ASCII symbol
        logic [31:0] token_id;      // Unique numeric order reference
        logic [47:0] timestamp;     // Ingress / Decision Timestamp
    } order_intent_t;

endpackage : ouch_pkg

`endif // OUCH_PKG_SV
