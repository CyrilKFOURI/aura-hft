`ifndef MOLDUDP64_RESILIENCE_ENGINE_SV
`define MOLDUDP64_RESILIENCE_ENGINE_SV

`timescale 1ns / 1ps

/**
 * moldudp64_resilience_engine.sv
 *
 * MoldUDP64 Network Resilience, Gap Detection & Snapshot Recovery Engine (AURA-HFT v4.0).
 *
 * Key Capabilities:
 *   1) Ultra-fast 1-cycle sequence gap detection at 312.5 MHz (3.2 ns).
 *   2) Instant fail-safe trading halt assertion (book_out_of_sync = 1).
 *   3) Autonomous MoldUDP64 Unicast Re-request Generation.
 *   4) Gap reconciliation via incoming infill packets and snapshot recovery via DMA.
 */

module moldudp64_resilience_engine (
    input  logic        clk,
    input  logic        rst_n,

    // =========================================================================
    // 1. Inbound MoldUDP64 Packet Header Stream (from Depacketizer)
    // =========================================================================
    input  logic        pkt_header_valid,
    input  logic [79:0] pkt_session,       // 10 ASCII characters
    input  logic [63:0] pkt_seq_num,       // 64-bit sequence number of 1st message
    input  logic [15:0] pkt_msg_count,     // Number of messages in packet

    // =========================================================================
    // 2. Inbound Retransmission / Infill Stream (from Unicast Client)
    // =========================================================================
    input  logic        infill_valid,
    input  logic [63:0] infill_seq_num,
    input  logic [15:0] infill_msg_count,

    // =========================================================================
    // 3. Snapshot Recovery & Host Control
    // =========================================================================
    input  logic        snap_load_en,
    input  logic [63:0] snap_target_seq,
    input  logic        manual_resync_req,

    // =========================================================================
    // 4. Outbound Retransmission Re-request Strobe (to UDP Egress / CPU)
    // =========================================================================
    output logic        rerequest_valid,
    output logic [79:0] rerequest_session,
    output logic [63:0] rerequest_seq_num,
    output logic [15:0] rerequest_count,

    // =========================================================================
    // 5. Safety & Telemetry
    // =========================================================================
    output logic        book_out_of_sync,
    output logic        gap_detected_strobe,
    output logic [63:0] expected_seq_num,
    output logic [31:0] gap_event_counter,
    output logic [31:0] total_lost_messages
);

    logic [63:0] target_head_seq;
    logic        initialized;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            expected_seq_num    <= 64'd1;
            target_head_seq     <= 64'd1;
            book_out_of_sync    <= 1'b0;
            gap_detected_strobe <= 1'b0;
            initialized         <= 1'b0;
            gap_event_counter   <= 32'd0;
            total_lost_messages <= 32'd0;
            rerequest_valid     <= 1'b0;
            rerequest_session   <= 80'd0;
            rerequest_seq_num   <= 64'd0;
            rerequest_count     <= 16'd0;
        end else begin
            // Default 1-cycle strobes
            rerequest_valid     <= 1'b0;
            gap_detected_strobe <= 1'b0;

            // -----------------------------------------------------------------
            // Snapshot or Manual Host Resynchronization
            // -----------------------------------------------------------------
            if (snap_load_en) begin
                expected_seq_num <= snap_target_seq;
                target_head_seq  <= snap_target_seq;
                book_out_of_sync <= 1'b0;
                initialized      <= 1'b1;
            end else if (manual_resync_req) begin
                book_out_of_sync <= 1'b0;
                if (pkt_header_valid) begin
                    expected_seq_num <= pkt_seq_num + {48'd0, pkt_msg_count};
                    target_head_seq  <= pkt_seq_num + {48'd0, pkt_msg_count};
                end
            end else begin

                // -------------------------------------------------------------
                // Infill / Retransmission Processing (while OUT_OF_SYNC)
                // -------------------------------------------------------------
                if (book_out_of_sync && infill_valid) begin
                    if (infill_seq_num <= expected_seq_num) begin
                        logic [63:0] new_expected;
                        new_expected = infill_seq_num + {48'd0, infill_msg_count};
                        if (new_expected > expected_seq_num) begin
                            expected_seq_num <= new_expected;
                        end

                        // Check if infill has fully caught up with the head of stream
                        if (new_expected >= target_head_seq) begin
                            book_out_of_sync <= 1'b0; // Fully restored!
                        end
                    end
                end

                // -------------------------------------------------------------
                // Inbound Live Packet Stream Processing
                // -------------------------------------------------------------
                if (pkt_header_valid) begin
                    // Ignore heartbeats with msg_count == 0 or 0xFFFF
                    if (pkt_msg_count != 16'd0 && pkt_msg_count != 16'hFFFF) begin
                        if (!initialized) begin
                            // First packet: synchronize baseline
                            expected_seq_num <= pkt_seq_num + {48'd0, pkt_msg_count};
                            target_head_seq  <= pkt_seq_num + {48'd0, pkt_msg_count};
                            initialized      <= 1'b1;
                            book_out_of_sync <= 1'b0;
                        end else if (pkt_seq_num == expected_seq_num) begin
                            // In-order packet arrival
                            expected_seq_num <= expected_seq_num + {48'd0, pkt_msg_count};
                            if (!book_out_of_sync) begin
                                target_head_seq <= expected_seq_num + {48'd0, pkt_msg_count};
                            end
                        end else if (pkt_seq_num > expected_seq_num) begin
                            // GAP DETECTED!
                            logic [63:0] missing_count;
                            missing_count = pkt_seq_num - expected_seq_num;

                            book_out_of_sync    <= 1'b1;
                            gap_detected_strobe <= 1'b1;
                            gap_event_counter   <= gap_event_counter + 32'd1;
                            total_lost_messages <= total_lost_messages + missing_count[31:0];

                            // Track latest head
                            target_head_seq     <= pkt_seq_num + {48'd0, pkt_msg_count};

                            // Emit Unicast re-request strobe in 1 cycle
                            rerequest_valid     <= 1'b1;
                            rerequest_session   <= pkt_session;
                            rerequest_seq_num   <= expected_seq_num;
                            rerequest_count     <= (missing_count > 64'd65535) ? 16'hFFFF : missing_count[15:0];
                        end
                        // Note: If pkt_seq_num < expected_seq_num, it's a duplicate or out-of-order retransmission, ignored
                    end
                end
            end
        end
    end

endmodule

`endif // MOLDUDP64_RESILIENCE_ENGINE_SV
