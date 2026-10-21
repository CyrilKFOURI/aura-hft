`ifndef ITCH_PKG_SV
`define ITCH_PKG_SV

`timescale 1ns / 1ps

package itch_pkg;

    // ITCH 5.0 Message Type ASCII Opcodes
    typedef enum logic [7:0] {
        ITCH_MSG_ADD         = 8'h41, // 'A' : Add Order (36 bytes)
        ITCH_MSG_ADD_MPID    = 8'h46, // 'F' : Add Order with MPID (40 bytes)
        ITCH_MSG_EXEC        = 8'h45, // 'E' : Order Executed (31 bytes)
        ITCH_MSG_EXEC_PRICE  = 8'h43, // 'C' : Order Executed with Price (36 bytes)
        ITCH_MSG_CANCEL      = 8'h58, // 'X' : Order Cancel (23 bytes)
        ITCH_MSG_DELETE      = 8'h44, // 'D' : Order Delete (19 bytes)
        ITCH_MSG_REPLACE     = 8'h55  // 'U' : Order Replace (35 bytes)
    } itch_msg_type_e;

    // Expected byte lengths for critical ITCH 5.0 messages
    localparam int unsigned LEN_MSG_A = 36;
    localparam int unsigned LEN_MSG_F = 40;
    localparam int unsigned LEN_MSG_E = 31;
    localparam int unsigned LEN_MSG_C = 36;
    localparam int unsigned LEN_MSG_X = 23;
    localparam int unsigned LEN_MSG_D = 19;
    localparam int unsigned LEN_MSG_U = 35;

    // MoldUDP64 Session Header Length
    localparam int unsigned MOLD_HEADER_BYTES = 20;

    // Network Headers (Ethernet II + IPv4 + UDP)
    localparam int unsigned ETH_HEADER_BYTES = 14;
    localparam int unsigned IP_HEADER_BYTES  = 20;
    localparam int unsigned UDP_HEADER_BYTES = 8;
    localparam int unsigned NET_HEADER_BYTES = ETH_HEADER_BYTES + IP_HEADER_BYTES + UDP_HEADER_BYTES; // 42 bytes

    // Decoded / Parsed ITCH message structure
    typedef struct packed {
        logic        valid;
        logic [7:0]  msg_type;
        logic [15:0] stock_locate;
        logic [15:0] tracking_num;
        logic [47:0] timestamp;
        logic [63:0] order_ref;
        logic        side;          // 1'b0: Buy ('B'), 1'b1: Sell ('S')
        logic [31:0] shares;
        logic [63:0] stock;         // 8-character ASCII stock symbol
        logic [31:0] price;         // Fixed-point price (4 decimal places)
        logic [63:0] match_number;  // For 'E' and 'C'
        logic [7:0]  printable;     // For 'C' ('Y' / 'N')
        logic [63:0] orig_order_ref;// For 'U'
        logic [63:0] new_order_ref; // For 'U'
        logic [31:0] mpid;          // For 'F' (4 ASCII chars)
    } itch_parsed_msg_t;

    // Helper functions for byte swapping (Big Endian network order to native Little Endian)
    function automatic logic [15:0] bswap16(input logic [15:0] in);
        return {in[7:0], in[15:8]};
    endfunction

    function automatic logic [31:0] bswap32(input logic [31:0] in);
        return {in[7:0], in[15:8], in[23:16], in[31:24]};
    endfunction

    function automatic logic [47:0] bswap48(input logic [47:0] in);
        return {in[7:0], in[15:8], in[23:16], in[31:24], in[39:32], in[47:40]};
    endfunction

    function automatic logic [63:0] bswap64(input logic [63:0] in);
        return {in[7:0], in[15:8], in[23:16], in[31:24], in[39:32], in[47:40], in[55:48], in[63:56]};
    endfunction

endpackage : itch_pkg

`endif // ITCH_PKG_SV
