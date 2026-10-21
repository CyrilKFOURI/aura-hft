`ifndef LOB_PKG_SV
`define LOB_PKG_SV

`timescale 1ns / 1ps

package lob_pkg;

    // Maximum price ladder depth supported per side in registers
    localparam int unsigned LOB_DEPTH = 16;
    localparam int unsigned TOP_N     = 5;

    // Price level structure for L2 book
    typedef struct packed {
        logic        valid;
        logic [31:0] price;
        logic [31:0] shares;
    } price_level_t;

    // Top-of-Book / BBO snapshot structure
    typedef struct packed {
        logic        valid;
        logic [31:0] best_bid_price;
        logic [31:0] best_bid_shares;
        logic [31:0] best_ask_price;
        logic [31:0] best_ask_shares;
        logic [31:0] spread;
    } bbo_t;

    // Order Book command types from parser/hash table to price ladder
    typedef enum logic [2:0] {
        LOB_CMD_NOP     = 3'b000,
        LOB_CMD_ADD     = 3'b001, // Add volume at price
        LOB_CMD_SUB     = 3'b010, // Subtract volume at price (Exec/Cancel/Delete)
        LOB_CMD_REPLACE = 3'b011, // Replace: Sub old, Add new
        LOB_CMD_CLEAR   = 3'b100  // Reset book
    } lob_cmd_e;

    // Order entry in Hash Table
    typedef struct packed {
        logic        valid;
        logic [63:0] order_ref;
        logic [31:0] price;
        logic [31:0] shares;
        logic        side; // 1'b0: Buy ('B'), 1'b1: Sell ('S')
    } order_entry_t;

endpackage : lob_pkg

`endif // LOB_PKG_SV
