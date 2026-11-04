// ============================================================================
// Module Name:   speculative_itch_parser
// Description:   Ultra-Low-Latency Speculative ITCH 5.0 Protocol Decoder.
//                Decodes all 7 supported NASDAQ ITCH 5.0 message formats
//                ('A', 'F', 'E', 'C', 'X', 'D', 'U') speculatively in parallel
//                across dedicated data paths, resolving the valid decoded message
//                via a single-level selection tree with minimal gate depth.
// Standard:      SystemVerilog IEEE 1800-2017
// Target:        AMD Kria KR260 @ 156.25 MHz (6.4 ns period)
// ============================================================================

`ifndef SPECULATIVE_ITCH_PARSER_SV
`define SPECULATIVE_ITCH_PARSER_SV

`timescale 1ns / 1ps

/* verilator lint_off IMPORTSTAR */
import itch_pkg::*;
/* verilator lint_on IMPORTSTAR */

module speculative_itch_parser (
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

    // Buffer ready when space exists for an incoming 8-byte word
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

    // ------------------------------------------------------------------------
    // 1. Sliding Window Buffer Management
    // ------------------------------------------------------------------------
    logic [7:0] temp_buf [0:63];
    logic [6:0] total_bytes;

    always_comb begin
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
    end

    // ------------------------------------------------------------------------
    // 2. Parallel Speculative Extraction of Message Fields
    // ------------------------------------------------------------------------
    logic [15:0] cur_msg_len;
    logic [7:0]  cur_msg_type;
    logic [15:0] common_locate;
    logic [15:0] common_track;
    logic [47:0] common_ts;

    assign cur_msg_len   = {temp_buf[0], temp_buf[1]};
    assign cur_msg_type  = temp_buf[2];
    assign common_locate = {temp_buf[3], temp_buf[4]};
    assign common_track  = {temp_buf[5], temp_buf[6]};
    assign common_ts     = {temp_buf[7], temp_buf[8], temp_buf[9], temp_buf[10], temp_buf[11], temp_buf[12]};

    // Branch A: Add Order (36 bytes payload)
    itch_parsed_msg_t spec_msg_A;
    always_comb begin
        spec_msg_A = '0;
        spec_msg_A.valid        = 1'b1;
        spec_msg_A.msg_type     = ITCH_MSG_ADD;
        spec_msg_A.stock_locate = common_locate;
        spec_msg_A.tracking_num = common_track;
        spec_msg_A.timestamp    = common_ts;
        spec_msg_A.order_ref    = {temp_buf[13], temp_buf[14], temp_buf[15], temp_buf[16],
                                   temp_buf[17], temp_buf[18], temp_buf[19], temp_buf[20]};
        spec_msg_A.side         = (temp_buf[21] == 8'h42) ? 1'b0 : 1'b1; // 'B' = 0, 'S' = 1
        spec_msg_A.shares       = {temp_buf[22], temp_buf[23], temp_buf[24], temp_buf[25]};
        spec_msg_A.stock        = {temp_buf[26], temp_buf[27], temp_buf[28], temp_buf[29],
                                   temp_buf[30], temp_buf[31], temp_buf[32], temp_buf[33]};
        spec_msg_A.price        = {temp_buf[34], temp_buf[35], temp_buf[36], temp_buf[37]};
    end

    // Branch F: Add Order with MPID (40 bytes payload)
    itch_parsed_msg_t spec_msg_F;
    always_comb begin
        spec_msg_F = '0;
        spec_msg_F.valid        = 1'b1;
        spec_msg_F.msg_type     = ITCH_MSG_ADD_MPID;
        spec_msg_F.stock_locate = common_locate;
        spec_msg_F.tracking_num = common_track;
        spec_msg_F.timestamp    = common_ts;
        spec_msg_F.order_ref    = {temp_buf[13], temp_buf[14], temp_buf[15], temp_buf[16],
                                   temp_buf[17], temp_buf[18], temp_buf[19], temp_buf[20]};
        spec_msg_F.side         = (temp_buf[21] == 8'h42) ? 1'b0 : 1'b1;
        spec_msg_F.shares       = {temp_buf[22], temp_buf[23], temp_buf[24], temp_buf[25]};
        spec_msg_F.stock        = {temp_buf[26], temp_buf[27], temp_buf[28], temp_buf[29],
                                   temp_buf[30], temp_buf[31], temp_buf[32], temp_buf[33]};
        spec_msg_F.price        = {temp_buf[34], temp_buf[35], temp_buf[36], temp_buf[37]};
        spec_msg_F.mpid         = {temp_buf[38], temp_buf[39], temp_buf[40], temp_buf[41]};
    end

    // Branch E: Order Executed (31 bytes payload)
    itch_parsed_msg_t spec_msg_E;
    always_comb begin
        spec_msg_E = '0;
        spec_msg_E.valid        = 1'b1;
        spec_msg_E.msg_type     = ITCH_MSG_EXEC;
        spec_msg_E.stock_locate = common_locate;
        spec_msg_E.tracking_num = common_track;
        spec_msg_E.timestamp    = common_ts;
        spec_msg_E.order_ref    = {temp_buf[13], temp_buf[14], temp_buf[15], temp_buf[16],
                                   temp_buf[17], temp_buf[18], temp_buf[19], temp_buf[20]};
        spec_msg_E.shares       = {temp_buf[21], temp_buf[22], temp_buf[23], temp_buf[24]};
        spec_msg_E.match_number = {temp_buf[25], temp_buf[26], temp_buf[27], temp_buf[28],
                                   temp_buf[29], temp_buf[30], temp_buf[31], temp_buf[32]};
    end

    // Branch C: Order Executed with Price (36 bytes payload)
    itch_parsed_msg_t spec_msg_C;
    always_comb begin
        spec_msg_C = '0;
        spec_msg_C.valid        = 1'b1;
        spec_msg_C.msg_type     = ITCH_MSG_EXEC_PRICE;
        spec_msg_C.stock_locate = common_locate;
        spec_msg_C.tracking_num = common_track;
        spec_msg_C.timestamp    = common_ts;
        spec_msg_C.order_ref    = {temp_buf[13], temp_buf[14], temp_buf[15], temp_buf[16],
                                   temp_buf[17], temp_buf[18], temp_buf[19], temp_buf[20]};
        spec_msg_C.shares       = {temp_buf[21], temp_buf[22], temp_buf[23], temp_buf[24]};
        spec_msg_C.match_number = {temp_buf[25], temp_buf[26], temp_buf[27], temp_buf[28],
                                   temp_buf[29], temp_buf[30], temp_buf[31], temp_buf[32]};
        spec_msg_C.printable    = temp_buf[33];
        spec_msg_C.price        = {temp_buf[34], temp_buf[35], temp_buf[36], temp_buf[37]};
    end

    // Branch X: Order Cancel (23 bytes payload)
    itch_parsed_msg_t spec_msg_X;
    always_comb begin
        spec_msg_X = '0;
        spec_msg_X.valid        = 1'b1;
        spec_msg_X.msg_type     = ITCH_MSG_CANCEL;
        spec_msg_X.stock_locate = common_locate;
        spec_msg_X.tracking_num = common_track;
        spec_msg_X.timestamp    = common_ts;
        spec_msg_X.order_ref    = {temp_buf[13], temp_buf[14], temp_buf[15], temp_buf[16],
                                   temp_buf[17], temp_buf[18], temp_buf[19], temp_buf[20]};
        spec_msg_X.shares       = {temp_buf[21], temp_buf[22], temp_buf[23], temp_buf[24]};
    end

    // Branch D: Order Delete (19 bytes payload)
    itch_parsed_msg_t spec_msg_D;
    always_comb begin
        spec_msg_D = '0;
        spec_msg_D.valid        = 1'b1;
        spec_msg_D.msg_type     = ITCH_MSG_DELETE;
        spec_msg_D.stock_locate = common_locate;
        spec_msg_D.tracking_num = common_track;
        spec_msg_D.timestamp    = common_ts;
        spec_msg_D.order_ref    = {temp_buf[13], temp_buf[14], temp_buf[15], temp_buf[16],
                                   temp_buf[17], temp_buf[18], temp_buf[19], temp_buf[20]};
    end

    // Branch U: Order Replace (35 bytes payload)
    itch_parsed_msg_t spec_msg_U;
    always_comb begin
        spec_msg_U = '0;
        spec_msg_U.valid          = 1'b1;
        spec_msg_U.msg_type       = ITCH_MSG_REPLACE;
        spec_msg_U.stock_locate   = common_locate;
        spec_msg_U.tracking_num   = common_track;
        spec_msg_U.timestamp      = common_ts;
        spec_msg_U.orig_order_ref = {temp_buf[13], temp_buf[14], temp_buf[15], temp_buf[16],
                                     temp_buf[17], temp_buf[18], temp_buf[19], temp_buf[20]};
        spec_msg_U.new_order_ref  = {temp_buf[21], temp_buf[22], temp_buf[23], temp_buf[24],
                                     temp_buf[25], temp_buf[26], temp_buf[27], temp_buf[28]};
        spec_msg_U.shares         = {temp_buf[29], temp_buf[30], temp_buf[31], temp_buf[32]};
        spec_msg_U.price          = {temp_buf[33], temp_buf[34], temp_buf[35], temp_buf[36]};
    end

    // ------------------------------------------------------------------------
    // 3. Parallel Validation and Match Comparators
    // ------------------------------------------------------------------------
    logic [6:0] required_len;
    assign required_len = 7'd2 + cur_msg_len[6:0];

    logic has_full_msg;
    assign has_full_msg = (total_bytes >= 7'd3) && (cur_msg_len > 16'd0) && (total_bytes >= required_len);

    logic match_A, match_F, match_E, match_C, match_X, match_D, match_U;
    assign match_A = has_full_msg && (cur_msg_type == ITCH_MSG_ADD)        && (cur_msg_len >= 16'd36);
    assign match_F = has_full_msg && (cur_msg_type == ITCH_MSG_ADD_MPID)   && (cur_msg_len >= 16'd40);
    assign match_E = has_full_msg && (cur_msg_type == ITCH_MSG_EXEC)       && (cur_msg_len >= 16'd31);
    assign match_C = has_full_msg && (cur_msg_type == ITCH_MSG_EXEC_PRICE) && (cur_msg_len >= 16'd36);
    assign match_X = has_full_msg && (cur_msg_type == ITCH_MSG_CANCEL)     && (cur_msg_len >= 16'd23);
    assign match_D = has_full_msg && (cur_msg_type == ITCH_MSG_DELETE)     && (cur_msg_len >= 16'd19);
    assign match_U = has_full_msg && (cur_msg_type == ITCH_MSG_REPLACE)    && (cur_msg_len >= 16'd35);

    // ------------------------------------------------------------------------
    // 4. Single-Level Low-Latency Selection Multiplexer
    // ------------------------------------------------------------------------
    itch_parsed_msg_t dec_msg;
    logic             dec_valid;
    logic             dec_drop;
    logic [7:0]       dec_unsupported_type;
    logic [6:0]       consumed_bytes;

    always_comb begin
        dec_msg              = '0;
        dec_valid            = 1'b0;
        dec_drop             = 1'b0;
        dec_unsupported_type = 8'd0;
        consumed_bytes       = 7'd0;

        if (has_full_msg) begin
            consumed_bytes = required_len;

            if (match_A) begin
                dec_msg   = spec_msg_A;
                dec_valid = 1'b1;
            end else if (match_F) begin
                dec_msg   = spec_msg_F;
                dec_valid = 1'b1;
            end else if (match_E) begin
                dec_msg   = spec_msg_E;
                dec_valid = 1'b1;
            end else if (match_C) begin
                dec_msg   = spec_msg_C;
                dec_valid = 1'b1;
            end else if (match_X) begin
                dec_msg   = spec_msg_X;
                dec_valid = 1'b1;
            end else if (match_D) begin
                dec_msg   = spec_msg_D;
                dec_valid = 1'b1;
            end else if (match_U) begin
                dec_msg   = spec_msg_U;
                dec_valid = 1'b1;
            end else begin
                // Unsupported message opcode (e.g. System Event 'S', Stock Directory 'R')
                dec_drop             = 1'b1;
                dec_unsupported_type = cur_msg_type;
            end
        end
    end

    // ------------------------------------------------------------------------
    // 5. Sequential Update of Output Registers and Sliding Buffer
    // ------------------------------------------------------------------------
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

            if (dec_valid) begin
                parsed_msg_count <= parsed_msg_count + 1'b1;
            end
            if (dec_drop) begin
                dropped_msg_count     <= dropped_msg_count + 1'b1;
                unsupported_type_code <= dec_unsupported_type;
            end

            // Shift remaining bytes in sliding window buffer
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

endmodule : speculative_itch_parser

`endif // SPECULATIVE_ITCH_PARSER_SV
