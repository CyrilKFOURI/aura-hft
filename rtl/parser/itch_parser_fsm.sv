`ifndef ITCH_PARSER_FSM_SV
`define ITCH_PARSER_FSM_SV

`timescale 1ns / 1ps

/* verilator lint_off IMPORTSTAR */
import itch_pkg::*;
/* verilator lint_on IMPORTSTAR */

module itch_parser_fsm (
    input  logic             clk,
    input  logic             rst_n,

    // AXI4-Stream Slave (from MoldUDP64 depacketizer)
    input  logic [63:0]      s_axis_tdata,
    input  logic [7:0]       s_axis_tkeep,
    input  logic             s_axis_tvalid,
    input  logic             s_axis_tlast,
    output logic             s_axis_tready,

    // Decoded ITCH Output Interface
    output logic             parsed_msg_valid,
    output itch_parsed_msg_t parsed_msg,

    // Telemetry & Unsupported / Drop indicators
    output logic             msg_drop,
    output logic [7:0]       unsupported_type_code,
    output logic [31:0]      parsed_msg_count,
    output logic [31:0]      dropped_msg_count
);

    // 64-byte sliding window buffer (512 bits)
    logic [7:0] buf_data [0:63];
    logic [6:0] buf_count;

    // Ready signal when buffer has room for an 8-byte word
    assign s_axis_tready = (buf_count <= 7'd56);

    // Count valid input bytes from tkeep
    function automatic logic [3:0] get_keep_bytes(input logic [7:0] keep);
        case (keep)
            8'h01: return 4'd1;
            8'h03: return 4'd2;
            8'h07: return 4'd3;
            8'h0F: return 4'd4;
            8'h1F: return 4'd5;
            8'h3F: return 4'd6;
            8'h7F: return 4'd7;
            8'hFF: return 4'd8;
            default: return (keep[7] ? 4'd8 : (keep[6] ? 4'd7 : (keep[5] ? 4'd6 : (keep[4] ? 4'd5 : (keep[3] ? 4'd4 : (keep[2] ? 4'd3 : (keep[1] ? 4'd2 : (keep[0] ? 4'd1 : 4'd0))))))));
        endcase
    endfunction

    // Combinational evaluation of buffer update and message decoding
    logic [7:0]  temp_buf [0:63];
    logic [6:0]  total_bytes;
    logic [15:0] cur_msg_len;
    logic [7:0]  cur_msg_type;
    logic        can_decode;
    logic [6:0]  consumed_bytes;
    logic        is_supported;

    itch_parsed_msg_t dec_msg;
    logic             dec_valid;
    logic             dec_drop;
    logic [7:0]       dec_unsupported_type;

    always_comb begin
        // 1. Incorporate newly arrived bytes into temporary buffer
        temp_buf = buf_data;
        total_bytes = buf_count;

        if (s_axis_tvalid && s_axis_tready) begin
            automatic logic [3:0] in_bytes = get_keep_bytes(s_axis_tkeep);
            for (int i = 0; i < 8; i++) begin
                if (i < 32'(in_bytes) && (32'(buf_count) + i < 64)) begin
                    temp_buf[32'(buf_count) + i] = s_axis_tdata[i*8 +: 8];
                end
            end
            total_bytes = buf_count + {3'd0, in_bytes};
        end

        // 2. Inspect head of buffer for 2-byte message length
        dec_msg              = '0;
        dec_valid            = 1'b0;
        dec_drop             = 1'b0;
        dec_unsupported_type = 8'd0;
        consumed_bytes       = 7'd0;

        if (total_bytes >= 7'd2) begin
            cur_msg_len  = {temp_buf[0], temp_buf[1]};
            cur_msg_type = (total_bytes >= 7'd3) ? temp_buf[2] : 8'd0;

            // Check if full message payload is available in buffer
            if (cur_msg_len > 16'd0 && total_bytes >= (7'd2 + cur_msg_len[6:0])) begin
                consumed_bytes = 7'd2 + cur_msg_len[6:0];

                // Decode Common ITCH Header (offset 2..12 in temp_buf)
                dec_msg.msg_type     = cur_msg_type;
                dec_msg.stock_locate = {temp_buf[3], temp_buf[4]};
                dec_msg.tracking_num = {temp_buf[5], temp_buf[6]};
                dec_msg.timestamp    = {temp_buf[7], temp_buf[8], temp_buf[9], temp_buf[10], temp_buf[11], temp_buf[12]};

                case (cur_msg_type)
                    ITCH_MSG_ADD: begin // 'A' : 36 bytes payload
                        if (cur_msg_len >= 16'd36) begin
                            dec_msg.valid     = 1'b1;
                            dec_valid         = 1'b1;
                            dec_msg.order_ref = {temp_buf[13], temp_buf[14], temp_buf[15], temp_buf[16],
                                                 temp_buf[17], temp_buf[18], temp_buf[19], temp_buf[20]};
                            dec_msg.side      = (temp_buf[21] == 8'h42) ? 1'b0 : 1'b1; // 'B' = 0, 'S' = 1
                            dec_msg.shares    = {temp_buf[22], temp_buf[23], temp_buf[24], temp_buf[25]};
                            dec_msg.stock     = {temp_buf[26], temp_buf[27], temp_buf[28], temp_buf[29],
                                                 temp_buf[30], temp_buf[31], temp_buf[32], temp_buf[33]};
                            dec_msg.price     = {temp_buf[34], temp_buf[35], temp_buf[36], temp_buf[37]};
                        end else begin
                            dec_drop = 1'b1;
                        end
                    end

                    ITCH_MSG_ADD_MPID: begin // 'F' : 40 bytes payload
                        if (cur_msg_len >= 16'd40) begin
                            dec_msg.valid     = 1'b1;
                            dec_valid         = 1'b1;
                            dec_msg.order_ref = {temp_buf[13], temp_buf[14], temp_buf[15], temp_buf[16],
                                                 temp_buf[17], temp_buf[18], temp_buf[19], temp_buf[20]};
                            dec_msg.side      = (temp_buf[21] == 8'h42) ? 1'b0 : 1'b1;
                            dec_msg.shares    = {temp_buf[22], temp_buf[23], temp_buf[24], temp_buf[25]};
                            dec_msg.stock     = {temp_buf[26], temp_buf[27], temp_buf[28], temp_buf[29],
                                                 temp_buf[30], temp_buf[31], temp_buf[32], temp_buf[33]};
                            dec_msg.price     = {temp_buf[34], temp_buf[35], temp_buf[36], temp_buf[37]};
                            dec_msg.mpid      = {temp_buf[38], temp_buf[39], temp_buf[40], temp_buf[41]};
                        end else begin
                            dec_drop = 1'b1;
                        end
                    end

                    ITCH_MSG_EXEC: begin // 'E' : 31 bytes payload
                        if (cur_msg_len >= 16'd31) begin
                            dec_msg.valid        = 1'b1;
                            dec_valid            = 1'b1;
                            dec_msg.order_ref    = {temp_buf[13], temp_buf[14], temp_buf[15], temp_buf[16],
                                                    temp_buf[17], temp_buf[18], temp_buf[19], temp_buf[20]};
                            dec_msg.shares       = {temp_buf[21], temp_buf[22], temp_buf[23], temp_buf[24]};
                            dec_msg.match_number = {temp_buf[25], temp_buf[26], temp_buf[27], temp_buf[28],
                                                    temp_buf[29], temp_buf[30], temp_buf[31], temp_buf[32]};
                        end else begin
                            dec_drop = 1'b1;
                        end
                    end

                    ITCH_MSG_EXEC_PRICE: begin // 'C' : 36 bytes payload
                        if (cur_msg_len >= 16'd36) begin
                            dec_msg.valid        = 1'b1;
                            dec_valid            = 1'b1;
                            dec_msg.order_ref    = {temp_buf[13], temp_buf[14], temp_buf[15], temp_buf[16],
                                                    temp_buf[17], temp_buf[18], temp_buf[19], temp_buf[20]};
                            dec_msg.shares       = {temp_buf[21], temp_buf[22], temp_buf[23], temp_buf[24]};
                            dec_msg.match_number = {temp_buf[25], temp_buf[26], temp_buf[27], temp_buf[28],
                                                    temp_buf[29], temp_buf[30], temp_buf[31], temp_buf[32]};
                            dec_msg.printable    = temp_buf[33];
                            dec_msg.price        = {temp_buf[34], temp_buf[35], temp_buf[36], temp_buf[37]};
                        end else begin
                            dec_drop = 1'b1;
                        end
                    end

                    ITCH_MSG_CANCEL: begin // 'X' : 23 bytes payload
                        if (cur_msg_len >= 16'd23) begin
                            dec_msg.valid     = 1'b1;
                            dec_valid         = 1'b1;
                            dec_msg.order_ref = {temp_buf[13], temp_buf[14], temp_buf[15], temp_buf[16],
                                                 temp_buf[17], temp_buf[18], temp_buf[19], temp_buf[20]};
                            dec_msg.shares    = {temp_buf[21], temp_buf[22], temp_buf[23], temp_buf[24]};
                        end else begin
                            dec_drop = 1'b1;
                        end
                    end

                    ITCH_MSG_DELETE: begin // 'D' : 19 bytes payload
                        if (cur_msg_len >= 16'd19) begin
                            dec_msg.valid     = 1'b1;
                            dec_valid         = 1'b1;
                            dec_msg.order_ref = {temp_buf[13], temp_buf[14], temp_buf[15], temp_buf[16],
                                                 temp_buf[17], temp_buf[18], temp_buf[19], temp_buf[20]};
                        end else begin
                            dec_drop = 1'b1;
                        end
                    end

                    ITCH_MSG_REPLACE: begin // 'U' : 35 bytes payload
                        if (cur_msg_len >= 16'd35) begin
                            dec_msg.valid          = 1'b1;
                            dec_valid              = 1'b1;
                            dec_msg.orig_order_ref = {temp_buf[13], temp_buf[14], temp_buf[15], temp_buf[16],
                                                      temp_buf[17], temp_buf[18], temp_buf[19], temp_buf[20]};
                            dec_msg.new_order_ref  = {temp_buf[21], temp_buf[22], temp_buf[23], temp_buf[24],
                                                      temp_buf[25], temp_buf[26], temp_buf[27], temp_buf[28]};
                            dec_msg.shares         = {temp_buf[29], temp_buf[30], temp_buf[31], temp_buf[32]};
                            dec_msg.price          = {temp_buf[33], temp_buf[34], temp_buf[35], temp_buf[36]};
                        end else begin
                            dec_drop = 1'b1;
                        end
                    end

                    default: begin
                        // Unsupported ITCH message type (e.g. System Event 'S', Directory 'R')
                        dec_drop             = 1'b1;
                        dec_unsupported_type = cur_msg_type;
                    end
                endcase
            end
        end
    end

    // Sequential update of buffer and output registers
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            buf_count             <= '0;
            for (int i = 0; i < 64; i++) begin
                buf_data[i] <= 8'd0;
            end
            parsed_msg_valid      <= 1'b0;
            parsed_msg            <= '0;
            msg_drop              <= 1'b0;
            unsupported_type_code <= 8'd0;
            parsed_msg_count      <= 32'd0;
            dropped_msg_count     <= 32'd0;
        end else begin
            parsed_msg_valid      <= dec_valid;
            parsed_msg            <= dec_msg;
            msg_drop              <= dec_drop;
            unsupported_type_code <= dec_unsupported_type;

            if (dec_valid) begin
                parsed_msg_count <= parsed_msg_count + 1'b1;
            end
            if (dec_drop) begin
                dropped_msg_count <= dropped_msg_count + 1'b1;
            end

            // Shift remaining bytes in buffer
            if (consumed_bytes > 7'd0) begin
                buf_count <= total_bytes - consumed_bytes;
                for (int i = 0; i < 64; i++) begin
                    if (i + 32'(consumed_bytes) < 64) begin
                        buf_data[i] <= temp_buf[i + 32'(consumed_bytes)];
                    end else begin
                        buf_data[i] <= 8'd0;
                    end
                end
            end else begin
                buf_count <= total_bytes;
                buf_data  <= temp_buf;
            end
        end
    end

endmodule : itch_parser_fsm

`endif // ITCH_PARSER_FSM_SV
