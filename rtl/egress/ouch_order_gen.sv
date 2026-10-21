`ifndef OUCH_ORDER_GEN_SV
`define OUCH_ORDER_GEN_SV

`timescale 1ns / 1ps

`include "ouch_pkg.sv"

/**
 * ouch_order_gen.sv
 *
 * Ultra-Low-Latency NASDAQ OUCH 5.0 Binary Packet Generator (AURA-HFT).
 * Encapsulates Enter Order ('O') into Ethernet II + IPv4 + UDP packet (91 bytes total).
 * Streams at line rate over 64-bit AXI4-Stream master interface.
 *
 * Latency to first beat: 1 cycle after order_valid.
 * Transmission duration: 12 clock cycles.
 */

module ouch_order_gen (
    input  logic        clk,
    input  logic        rst_n,

    // Inbound Approved Order Strobe
    input  logic        order_valid,
    input  logic        order_side,         // 1'b0: Buy ('B'), 1'b1: Sell ('S')
    input  logic [31:0] order_shares,
    input  logic [31:0] order_price,        // 4 decimal places
    input  logic [63:0] order_stock,        // 8 ASCII chars ("AAPL    ")
    input  logic [31:0] order_token,        // Unique order integer
    input  logic [47:0] order_timestamp,    // Ingress/decision timestamp

    // Outbound AXI4-Stream 64-bit Interface
    output logic [63:0] m_axis_tdata,
    output logic [7:0]  m_axis_tkeep,
    output logic        m_axis_tvalid,
    output logic        m_axis_tlast,
    input  logic        m_axis_tready,

    // Status & Telemetry
    output logic        busy,
    output logic [31:0] tx_order_count,
    output logic [47:0] tx_egress_timestamp
);

    import ouch_pkg::*;

    typedef enum logic [1:0] {
        ST_IDLE     = 2'd0,
        ST_TRANSMIT = 2'd1
    } tx_state_e;

    tx_state_e state;
    logic [3:0] word_idx;

    // Latched order parameters
    logic        reg_side;
    logic [31:0] reg_shares;
    logic [31:0] reg_price;
    logic [63:0] reg_stock;
    logic [31:0] reg_token;
    logic [47:0] reg_timestamp;

    assign busy = (state != ST_IDLE);

    // Pre-assemble 12 64-bit words for the 91-byte packet
    logic [63:0] packet_words [0:11];

    always_comb begin
        automatic logic [7:0]  side_ascii;
        automatic logic [31:0] shares_be;
        automatic logic [31:0] price_be;
        automatic logic [111:0] token_ascii;

        side_ascii = reg_side ? 8'h53 : 8'h42; // 'S' or 'B'
        shares_be  = {reg_shares[7:0], reg_shares[15:8], reg_shares[23:16], reg_shares[31:24]};
        price_be   = {reg_price[7:0],  reg_price[15:8],  reg_price[23:16],  reg_price[31:24]};

        // Order token: 14 ASCII chars: "ORD" + 11-digit representation
        token_ascii = {
            8'h4F, 8'h52, 8'h44, // "ORD"
            8'h30, 8'h30, 8'h30, 8'h30, 8'h30, 8'h30, 8'h30,
            8'h30 + 8'(reg_token[15:12]),
            8'h30 + 8'(reg_token[11:8]),
            8'h30 + 8'(reg_token[7:4]),
            8'h30 + 8'(reg_token[3:0])
        };

        // Word 0: Dest MAC [0:5] (00:11:22:33:44:55), Src MAC [0:1] (66:77)
        packet_words[0] = {8'h77, 8'h66, 8'h55, 8'h44, 8'h33, 8'h22, 8'h11, 8'h00};

        // Word 1: Src MAC [2:5] (88:99:AA:BB), EtherType (08:00), IP Ver/IHL (45), DSCP (00)
        packet_words[1] = {8'h00, 8'h45, 8'h00, 8'h08, 8'hBB, 8'hAA, 8'h99, 8'h88};

        // Word 2: IP Total Len (00:4D = 77B), Ident (00:01), Flags/Frag (40:00), TTL (40), Proto (11 = UDP)
        packet_words[2] = {8'h11, 8'h40, 8'h00, 8'h40, 8'h01, 8'h00, 8'h4D, 8'h00};

        // Word 3: IP Checksum (26:9D), Src IP (0A:00:00:01), Dest IP [0:1] (0A:00)
        packet_words[3] = {8'h00, 8'h0A, 8'h01, 8'h00, 8'h00, 8'h0A, 8'h9D, 8'h26};

        // Word 4: Dest IP [2:3] (00:02), UDP Src Port (12345 = 30:39), Dest Port (40002 = 9C:42), UDP Len (00:39 = 57B)
        packet_words[4] = {8'h39, 8'h00, 8'h42, 8'h9C, 8'h39, 8'h30, 8'h02, 8'h00};

        // Word 5: UDP Chk (00:00), OUCH Type 'O' (4F), Token [0:4]
        packet_words[5] = {token_ascii[79:40], 8'h4F, 8'h00, 8'h00};

        // Word 6: Token [5:12] (8 bytes)
        packet_words[6] = {token_ascii[7:0], token_ascii[15:8], token_ascii[23:16], token_ascii[31:24],
                           token_ascii[39:32], token_ascii[47:40], token_ascii[55:48], token_ascii[63:56]};

        // Word 7: Token [13], Side, Shares [0:3], Stock [0:1]
        packet_words[7] = {
            reg_stock[55:48], reg_stock[63:56],
            shares_be[31:24], shares_be[23:16], shares_be[15:8], shares_be[7:0],
            side_ascii, token_ascii[111:104]
        };

        // Word 8: Stock [2:7] (6 bytes), Price [0:1] (2 bytes)
        packet_words[8] = {
            price_be[15:8], price_be[7:0],
            reg_stock[7:0], reg_stock[15:8], reg_stock[23:16],
            reg_stock[31:24], reg_stock[39:32], reg_stock[47:40]
        };

        // Word 9: Price [2:3] (2 bytes), TIF (00:00:00:00), Firm [0:1] ("AU")
        packet_words[9] = {8'h55, 8'h41, 8'h00, 8'h00, 8'h00, 8'h00, price_be[31:24], price_be[23:16]};

        // Word 10: Firm [2:3] ("RA"), Display 'Y' (59), Cap 'P' (50), ISO 'N' (4E), MinQty [0:2] (00:00:00)
        packet_words[10] = {8'h00, 8'h00, 8'h00, 8'h4E, 8'h50, 8'h59, 8'h41, 8'h52};

        // Word 11: MinQty [3] (00), CrossType 'N' (4E), CustomerType 'N' (4E) - 3 valid bytes
        packet_words[11] = {40'd0, 8'h4E, 8'h4E, 8'h00};
    end

    // Transmission State Machine
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state              <= ST_IDLE;
            word_idx           <= '0;
            reg_side           <= 1'b0;
            reg_shares         <= '0;
            reg_price          <= '0;
            reg_stock          <= '0;
            reg_token          <= '0;
            reg_timestamp      <= '0;
            m_axis_tvalid      <= 1'b0;
            m_axis_tdata       <= '0;
            m_axis_tkeep       <= '0;
            m_axis_tlast       <= 1'b0;
            tx_order_count     <= '0;
            tx_egress_timestamp<= '0;
        end else begin
            case (state)
                ST_IDLE: begin
                    m_axis_tvalid <= 1'b0;
                    m_axis_tlast  <= 1'b0;
                    word_idx      <= '0;

                    if (order_valid) begin
                        reg_side            <= order_side;
                        reg_shares          <= order_shares;
                        reg_price           <= order_price;
                        reg_stock           <= order_stock;
                        reg_token           <= order_token;
                        reg_timestamp       <= order_timestamp;
                        tx_egress_timestamp <= order_timestamp;
                        state               <= ST_TRANSMIT;

                        // Start outputting word 0 immediately next cycle
                        m_axis_tvalid <= 1'b1;
                        m_axis_tdata  <= {8'h77, 8'h66, 8'h55, 8'h44, 8'h33, 8'h22, 8'h11, 8'h00};
                        m_axis_tkeep  <= 8'hFF;
                        m_axis_tlast  <= 1'b0;
                        word_idx      <= 4'd1;
                    end
                end

                ST_TRANSMIT: begin
                    if (m_axis_tready) begin
                        if (word_idx < 4'd11) begin
                            m_axis_tvalid <= 1'b1;
                            m_axis_tdata  <= packet_words[word_idx];
                            m_axis_tkeep  <= 8'hFF;
                            m_axis_tlast  <= 1'b0;
                            word_idx      <= word_idx + 1'b1;
                        end else if (word_idx == 4'd11) begin
                            // Final beat: 3 valid bytes, assert tlast
                            m_axis_tvalid <= 1'b1;
                            m_axis_tdata  <= packet_words[11];
                            m_axis_tkeep  <= 8'h07;
                            m_axis_tlast  <= 1'b1;
                            word_idx      <= 4'd12;
                        end else begin
                            // Complete
                            m_axis_tvalid  <= 1'b0;
                            m_axis_tlast   <= 1'b0;
                            tx_order_count <= tx_order_count + 1'b1;
                            state          <= ST_IDLE;
                        end
                    end
                end

                default: state <= ST_IDLE;
            endcase
        end
    end

endmodule : ouch_order_gen

`endif // OUCH_ORDER_GEN_SV
