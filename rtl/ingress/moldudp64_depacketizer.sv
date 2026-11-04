`ifndef MOLDUDP64_DEPACKETIZER_SV
`define MOLDUDP64_DEPACKETIZER_SV

`timescale 1ns / 1ps

/* verilator lint_off IMPORTSTAR */
import itch_pkg::*;
/* verilator lint_on IMPORTSTAR */

module moldudp64_depacketizer #(
    parameter bit STRIP_ETH_IP_UDP = 1'b1 // 1: Strip Eth+IP+UDP (42B) + Mold (20B) = 62B. 0: Mold only (20B)
)(
    input  logic        clk,
    input  logic        rst_n,

    // AXI4-Stream Slave (Incoming network frame)
    input  logic [63:0] s_axis_tdata,
    input  logic [7:0]  s_axis_tkeep,
    input  logic        s_axis_tvalid,
    input  logic        s_axis_tlast,
    output logic        s_axis_tready,

    // AXI4-Stream Master (Outgoing MoldUDP64 payload: ITCH message blocks)
    output logic [63:0] m_axis_tdata,
    output logic [7:0]  m_axis_tkeep,
    output logic        m_axis_tvalid,
    output logic        m_axis_tlast,
    input  logic        m_axis_tready,

    // MoldUDP64 Telemetry & Status
    output logic [79:0] session_name,
    output logic [63:0] sequence_number,
    output logic [15:0] message_count,
    output logic        pkt_header_valid,
    output logic        gap_detected,
    output logic [63:0] gap_count,
    output logic        duplicate_detected,
    output logic [63:0] expected_seq_out
);

    typedef enum logic [2:0] {
        ST_IDLE,
        ST_HEADER_PARSE,
        ST_PAYLOAD_STREAM,
        ST_FLUSH_TRAIL
    } state_e;

    state_e state;

    // Word counter in frame
    logic [7:0] word_idx;

    // Registers for MoldUDP64 Header fields
    logic [79:0] reg_session_name;
    logic [63:0] reg_seq_num;
    logic [15:0] reg_msg_count;
    logic [63:0] expected_seq_num;
    logic        seq_initialized;

    // Carryover buffer for barrel-shift alignment
    // When STRIP_ETH_IP_UDP=1: 62 bytes stripped -> 6 bytes in word 7 are header, 2 bytes are payload (bytes 6..7).
    // Shift needed: carryover of 2 bytes (16 bits) from previous word.
    // When STRIP_ETH_IP_UDP=0: 20 bytes stripped -> 4 bytes in word 2 are header, 4 bytes are payload (bytes 4..7).
    // Shift needed: carryover of 4 bytes (32 bits) from previous word.
    logic [63:0] prev_data;
    logic [7:0]  prev_keep;
    logic        has_trail;

    assign session_name       = reg_session_name;
    assign sequence_number    = reg_seq_num;
    assign message_count      = reg_msg_count;
    assign expected_seq_out   = expected_seq_num;

    // Pass-through ready when in streaming or idle
    assign s_axis_tready = (state == ST_FLUSH_TRAIL) ? 1'b0 : (m_axis_tready || state != ST_PAYLOAD_STREAM);

    // Helpers to convert AXI tkeep to length and vice-versa
    function automatic logic [3:0] keep_to_len(input logic [7:0] keep);
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

    function automatic logic [7:0] len_to_keep(input logic [3:0] len);
        case (len)
            4'd1: return 8'h01;
            4'd2: return 8'h03;
            4'd3: return 8'h07;
            4'd4: return 8'h0F;
            4'd5: return 8'h1F;
            4'd6: return 8'h3F;
            4'd7: return 8'h7F;
            4'd8: return 8'hFF;
            default: return 8'h00;
        endcase
    endfunction

    // Header word thresholds
    // If STRIP_ETH_IP_UDP == 1:
    //   Word 0..4: Eth (14) + IP (20) + UDP (8) = 42B
    //   Word 5: UDP (2B) + Session[0:5] (6B)
    //   Word 6: Session[6:9] (4B) + Seq[0:3] (4B)
    //   Word 7: Seq[4:7] (4B) + MsgCount[0:1] (2B) + Payload[0:1] (2B)
    //   Payload streaming starts at Word 7!
    // If STRIP_ETH_IP_UDP == 0:
    //   Word 0: Session[0:7] (8B)
    //   Word 1: Session[8:9] (2B) + Seq[0:5] (6B)
    //   Word 2: Seq[6:7] (2B) + MsgCount[0:1] (2B) + Payload[0:3] (4B)
    //   Payload streaming starts at Word 2!

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state               <= ST_IDLE;
            word_idx            <= '0;
            reg_session_name    <= '0;
            reg_seq_num         <= '0;
            reg_msg_count       <= '0;
            expected_seq_num    <= '0;
            seq_initialized     <= 1'b0;
            pkt_header_valid    <= 1'b0;
            gap_detected        <= 1'b0;
            gap_count           <= '0;
            duplicate_detected  <= 1'b0;
            m_axis_tvalid       <= 1'b0;
            m_axis_tdata        <= '0;
            m_axis_tkeep        <= '0;
            m_axis_tlast        <= 1'b0;
            prev_data           <= '0;
            prev_keep           <= '0;
            has_trail           <= 1'b0;
        end else begin
            // Default strobes
            pkt_header_valid   <= 1'b0;
            gap_detected       <= 1'b0;
            duplicate_detected <= 1'b0;

            // Clear master valid if transaction accepted
            if (m_axis_tvalid && m_axis_tready) begin
                m_axis_tvalid <= 1'b0;
                m_axis_tlast  <= 1'b0;
            end

            case (state)
                ST_IDLE: begin
                    word_idx  <= '0;
                    has_trail <= 1'b0;
                    if (s_axis_tvalid && s_axis_tready) begin
                        state    <= ST_HEADER_PARSE;
                        word_idx <= 8'd1;
                        if (!STRIP_ETH_IP_UDP) begin
                            // Word 0 is Session[0:7]
                            reg_session_name[79:16] <= {
                                s_axis_tdata[7:0],   s_axis_tdata[15:8],
                                s_axis_tdata[23:16], s_axis_tdata[31:24],
                                s_axis_tdata[39:32], s_axis_tdata[47:40],
                                s_axis_tdata[55:48], s_axis_tdata[63:56]
                            };
                        end
                        if (s_axis_tlast) begin
                            state <= ST_IDLE;
                        end
                    end
                end

                ST_HEADER_PARSE: begin
                    if (s_axis_tvalid && s_axis_tready) begin
                        word_idx <= word_idx + 1'b1;

                        if (STRIP_ETH_IP_UDP) begin
                            // Strip Ethernet (14) + IPv4 (20) + UDP (8) = 42 bytes
                            if (word_idx == 8'd5) begin
                                // Word 5: s_axis_tdata[15:0] = UDP[6:7], s_axis_tdata[63:16] = Session[0:5]
                                reg_session_name[79:32] <= {
                                    s_axis_tdata[23:16], s_axis_tdata[31:24],
                                    s_axis_tdata[39:32], s_axis_tdata[47:40],
                                    s_axis_tdata[55:48], s_axis_tdata[63:56]
                                };
                            end else if (word_idx == 8'd6) begin
                                // Word 6: s_axis_tdata[31:0] = Session[6:9], s_axis_tdata[63:32] = Seq[0:3]
                                reg_session_name[31:0] <= {
                                    s_axis_tdata[7:0],   s_axis_tdata[15:8],
                                    s_axis_tdata[23:16], s_axis_tdata[31:24]
                                };
                                reg_seq_num[63:32] <= {
                                    s_axis_tdata[39:32], s_axis_tdata[47:40],
                                    s_axis_tdata[55:48], s_axis_tdata[63:56]
                                };
                            end else if (word_idx == 8'd7) begin
                                // Word 7: s_axis_tdata[31:0] = Seq[4:7], s_axis_tdata[47:32] = MsgCount[0:1]
                                // s_axis_tdata[63:48] = Payload bytes 0..1 (2 bytes)
                                automatic logic [63:0] cur_seq;
                                automatic logic [15:0] cur_cnt;

                                cur_seq = {
                                    reg_seq_num[63:32],
                                    s_axis_tdata[7:0],   s_axis_tdata[15:8],
                                    s_axis_tdata[23:16], s_axis_tdata[31:24]
                                };
                                cur_cnt = {s_axis_tdata[39:32], s_axis_tdata[47:40]};

                                reg_seq_num   <= cur_seq;
                                reg_msg_count <= cur_cnt;
                                pkt_header_valid <= 1'b1;

                                // Sequence Gap & Duplicate Check
                                if (!seq_initialized) begin
                                    seq_initialized  <= 1'b1;
                                    expected_seq_num <= cur_seq + 64'(cur_cnt);
                                end else begin
                                    if (cur_seq == expected_seq_num) begin
                                        expected_seq_num <= cur_seq + 64'(cur_cnt);
                                    end else if (cur_seq > expected_seq_num) begin
                                        gap_detected     <= 1'b1;
                                        gap_count        <= cur_seq - expected_seq_num;
                                        expected_seq_num <= cur_seq + 64'(cur_cnt);
                                    end else begin
                                        duplicate_detected <= 1'b1;
                                    end
                                end

                                // Save the 2 carryover payload bytes (s_axis_tdata[63:48])
                                prev_data <= {48'd0, s_axis_tdata[63:48]};
                                prev_keep <= 8'h03; // 2 valid bytes

                                if (s_axis_tlast) begin
                                    // Extremely short packet with only 2 bytes of payload
                                    m_axis_tvalid <= 1'b1;
                                    m_axis_tdata  <= {48'd0, s_axis_tdata[63:48]};
                                    m_axis_tkeep  <= 8'h03;
                                    m_axis_tlast  <= 1'b1;
                                    state         <= ST_IDLE;
                                end else begin
                                    state <= ST_PAYLOAD_STREAM;
                                end
                            end
                        end else begin
                            // STRIP_ETH_IP_UDP == 0 (Pure MoldUDP64 frame)
                            if (word_idx == 8'd1) begin
                                // Word 1: s_axis_tdata[15:0] = Session[8:9], s_axis_tdata[63:16] = Seq[0:5]
                                reg_session_name[15:0] <= {s_axis_tdata[7:0], s_axis_tdata[15:8]};
                                reg_seq_num[63:16] <= {
                                    s_axis_tdata[23:16], s_axis_tdata[31:24],
                                    s_axis_tdata[39:32], s_axis_tdata[47:40],
                                    s_axis_tdata[55:48], s_axis_tdata[63:56]
                                };
                            end else if (word_idx == 8'd2) begin
                                // Word 2: s_axis_tdata[15:0] = Seq[6:7], s_axis_tdata[31:16] = MsgCount[0:1]
                                // s_axis_tdata[63:32] = Payload bytes 0..3 (4 bytes)
                                automatic logic [63:0] cur_seq;
                                automatic logic [15:0] cur_cnt;

                                cur_seq = {
                                    reg_seq_num[63:16],
                                    s_axis_tdata[7:0], s_axis_tdata[15:8]
                                };
                                cur_cnt = {s_axis_tdata[23:16], s_axis_tdata[31:24]};

                                reg_seq_num   <= cur_seq;
                                reg_msg_count <= cur_cnt;
                                pkt_header_valid <= 1'b1;

                                if (!seq_initialized) begin
                                    seq_initialized  <= 1'b1;
                                    expected_seq_num <= cur_seq + 64'(cur_cnt);
                                end else begin
                                    if (cur_seq == expected_seq_num) begin
                                        expected_seq_num <= cur_seq + 64'(cur_cnt);
                                    end else if (cur_seq > expected_seq_num) begin
                                        gap_detected     <= 1'b1;
                                        gap_count        <= cur_seq - expected_seq_num;
                                        expected_seq_num <= cur_seq + 64'(cur_cnt);
                                    end else begin
                                        duplicate_detected <= 1'b1;
                                    end
                                end

                                // Save the 4 carryover payload bytes (s_axis_tdata[63:32])
                                prev_data <= {32'd0, s_axis_tdata[63:32]};
                                prev_keep <= 8'h0F; // 4 valid bytes

                                if (s_axis_tlast) begin
                                    m_axis_tvalid <= 1'b1;
                                    m_axis_tdata  <= {32'd0, s_axis_tdata[63:32]};
                                    m_axis_tkeep  <= 8'h0F;
                                    m_axis_tlast  <= 1'b1;
                                    state         <= ST_IDLE;
                                end else begin
                                    state <= ST_PAYLOAD_STREAM;
                                end
                            end
                        end

                        if (s_axis_tlast && state != ST_PAYLOAD_STREAM) begin
                            state <= ST_IDLE;
                        end
                    end
                end

                ST_PAYLOAD_STREAM: begin
                    if (s_axis_tvalid && s_axis_tready) begin
                        automatic logic [3:0] in_k;
                        automatic logic [4:0] total_k;
                        in_k = keep_to_len(s_axis_tkeep);
                        word_idx <= word_idx + 1'b1;

                        if (STRIP_ETH_IP_UDP) begin
                            total_k = 5'd2 + {1'b0, in_k};
                            if (!s_axis_tlast) begin
                                m_axis_tvalid <= 1'b1;
                                m_axis_tlast  <= 1'b0;
                                m_axis_tdata  <= {s_axis_tdata[47:0], prev_data[15:0]};
                                m_axis_tkeep  <= 8'hFF;
                                prev_data     <= {48'd0, s_axis_tdata[63:48]};
                                prev_keep     <= 8'h03;
                            end else begin
                                if (total_k <= 5'd8) begin
                                    m_axis_tvalid <= 1'b1;
                                    m_axis_tlast  <= 1'b1;
                                    m_axis_tdata  <= {s_axis_tdata[47:0], prev_data[15:0]};
                                    m_axis_tkeep  <= len_to_keep(total_k[3:0]);
                                    state         <= ST_IDLE;
                                end else begin
                                    m_axis_tvalid <= 1'b1;
                                    m_axis_tlast  <= 1'b0;
                                    m_axis_tdata  <= {s_axis_tdata[47:0], prev_data[15:0]};
                                    m_axis_tkeep  <= 8'hFF;
                                    prev_data     <= {48'd0, s_axis_tdata[63:48]};
                                    prev_keep     <= len_to_keep(total_k[3:0] - 4'd8);
                                    has_trail     <= 1'b1;
                                    state         <= ST_FLUSH_TRAIL;
                                end
                            end
                        end else begin
                            total_k = 5'd4 + {1'b0, in_k};
                            if (!s_axis_tlast) begin
                                m_axis_tvalid <= 1'b1;
                                m_axis_tlast  <= 1'b0;
                                m_axis_tdata  <= {s_axis_tdata[31:0], prev_data[31:0]};
                                m_axis_tkeep  <= 8'hFF;
                                prev_data     <= {32'd0, s_axis_tdata[63:32]};
                                prev_keep     <= 8'h0F;
                            end else begin
                                if (total_k <= 5'd8) begin
                                    m_axis_tvalid <= 1'b1;
                                    m_axis_tlast  <= 1'b1;
                                    m_axis_tdata  <= {s_axis_tdata[31:0], prev_data[31:0]};
                                    m_axis_tkeep  <= len_to_keep(total_k[3:0]);
                                    state         <= ST_IDLE;
                                end else begin
                                    m_axis_tvalid <= 1'b1;
                                    m_axis_tlast  <= 1'b0;
                                    m_axis_tdata  <= {s_axis_tdata[31:0], prev_data[31:0]};
                                    m_axis_tkeep  <= 8'hFF;
                                    prev_data     <= {32'd0, s_axis_tdata[63:32]};
                                    prev_keep     <= len_to_keep(total_k[3:0] - 4'd8);
                                    has_trail     <= 1'b1;
                                    state         <= ST_FLUSH_TRAIL;
                                end
                            end
                        end
                    end
                end

                ST_FLUSH_TRAIL: begin
                    if (!m_axis_tvalid || m_axis_tready) begin
                        m_axis_tvalid <= 1'b1;
                        m_axis_tlast  <= 1'b1;
                        m_axis_tdata  <= prev_data;
                        m_axis_tkeep  <= prev_keep;
                        state         <= ST_IDLE;
                    end
                end

                default: state <= ST_IDLE;
            endcase
        end
    end

endmodule : moldudp64_depacketizer

`endif // MOLDUDP64_DEPACKETIZER_SV
