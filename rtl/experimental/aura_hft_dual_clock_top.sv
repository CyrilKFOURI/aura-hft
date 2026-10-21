// ============================================================================
// Module Name:   aura_hft_dual_clock_top
// Description:   Dual-Clock Domain Crossing (CDC) High-Frequency Trading Pipeline.
//                Decouples physical 10GbE network interfaces (clk_net @ 156.25 MHz)
//                from internal compute engines (clk_core @ 312.5 MHz).
//                Uses Gray-code pointer asynchronous FIFOs for zero-loss,
//                sub-microsecond tick-to-trade processing.
// Standard:      SystemVerilog IEEE 1800-2017
// Target:        AMD Kria KR260 (UltraScale+ xck26-sfvc784-2LV-c)
// ============================================================================

`ifndef AURA_HFT_DUAL_CLOCK_TOP_SV
`define AURA_HFT_DUAL_CLOCK_TOP_SV

`timescale 1ns / 1ps

/* verilator lint_off IMPORTSTAR */
import itch_pkg::*;
import lob_pkg::*;
import ouch_pkg::*;
/* verilator lint_on IMPORTSTAR */

module aura_hft_dual_clock_top #(
    parameter bit          STRIP_ETH_IP_UDP     = 1'b1,
    parameter logic [63:0] TARGET_STOCK         = 64'h4141504C20202020, // "AAPL    "
    parameter bit          ENABLE_SYMBOL_FILTER = 1'b1,
    parameter int unsigned NUM_SETS             = 8192,
    parameter int unsigned NUM_WAYS             = 4,
    parameter int unsigned BOOK_DEPTH           = 16,
    parameter int unsigned NUM_TRACKED_ORDERS   = 4
)(
    // Dual Asynchronous Clock Sources
    input  logic        clk_net,            // 156.25 MHz (6.4 ns) - Network Ingress & Egress domain
    input  logic        clk_core,           // 312.50 MHz (3.2 ns) - Accelerated LOB & Quant Compute domain
    /* verilator lint_off SYNCASYNCNET */ // rst_n also feeds the core reset synchronizer (see u_rst_sync_core)
    input  logic        rst_n,              // Asynchronous active-low system reset
    /* verilator lint_on SYNCASYNCNET */

    // Ingress (RX) 64-bit AXI4-Stream Interface from 10G SFP+ MAC (clk_net domain)
    input  logic [63:0] s_axis_tdata,
    input  logic [7:0]  s_axis_tkeep,
    input  logic        s_axis_tvalid,
    input  logic        s_axis_tlast,
    output logic        s_axis_tready,

    // Egress (TX) 64-bit AXI4-Stream Interface to 10G SFP+ MAC (clk_net domain)
    output logic [63:0] m_axis_tdata,
    output logic [7:0]  m_axis_tkeep,
    output logic        m_axis_tvalid,
    output logic        m_axis_tlast,
    input  logic        m_axis_tready,

    // Strategy & Risk Configuration Pins
    input  logic               cfg_auto_trade_enable,
    input  logic signed [31:0] cfg_obi_buy_thresh,    // Q1.31
    input  logic signed [31:0] cfg_obi_sell_thresh,   // Q1.31
    input  logic [31:0]        cfg_default_order_shares,
    input  logic               cfg_kill_switch,
    input  logic [31:0]        cfg_max_order_shares,
    input  logic [31:0]        cfg_price_collar_threshold,
    input  logic [63:0]        cfg_max_notional_raw,
    input  logic [63:0]        cfg_max_cum_notional_raw,

    // Host Manual Order Intent Port (clk_core domain or synchronized)
    input  logic        host_intent_valid,
    input  logic        host_intent_side,
    input  logic [31:0] host_intent_shares,
    input  logic [31:0] host_intent_price,
    input  logic [31:0] host_intent_token,

    // Live Market & Quant Telemetry (clk_core domain)
    output logic               bbo_valid,
    output logic [31:0]        best_bid_price,
    output logic [31:0]        best_bid_shares,
    output logic [31:0]        best_ask_price,
    output logic [31:0]        best_ask_shares,
    output logic [31:0]        spread,
    output logic [31:0]        mid_price,
    output logic               bbo_updated,

    output logic               obi_valid,
    output logic signed [31:0] obi_val,
    output logic [31:0]        micro_price,

    // Risk Telemetry
    output logic        risk_approved_strobe,
    output logic        risk_rejected_strobe,
    output logic [3:0]  risk_reject_reason,

    // Hardware Latency Telemetry (measured in clk_net cycles)
    output logic [47:0] cycle_counter_net,
    output logic [15:0] last_tick_to_trade_cycles,
    output logic        tick_to_trade_strobe,
    output logic [31:0] tx_order_count,
    output logic [31:0] parsed_msg_count,

    // CDC FIFO Status Indicators
    output logic        ingress_cdc_full,
    output logic        ingress_cdc_empty,
    output logic        egress_cdc_full,
    output logic        egress_cdc_empty,

    // IEEE 1588 PTP & Wire-to-Wire Metrology Outputs
    output logic [95:0] ptp_timestamp_out,
    output logic [31:0] fcs_error_count_out,
    output logic [31:0] wire_to_wire_latency_ns,
    output logic [31:0] min_latency_ns,
    output logic [31:0] max_latency_ns,
    output logic        latency_measurement_valid
);

    // ------------------------------------------------------------------------
    // 1. Reset Synchronization into clk_core domain
    // ------------------------------------------------------------------------
    logic rst_n_core;
    // rst_n is intentionally sampled as data by this reset synchronizer.
    // TODO(P4): switch to async-assert / sync-deassert reset bridge.
    /* verilator lint_off SYNCASYNCNET */
    cdc_sync_bit #(
        .INIT_VALUE(1'b0),
        .STAGES(2)
    ) u_rst_sync_core (
        .dest_clk   (clk_core),
        .dest_rst_n (1'b1),
        .src_signal (rst_n),
        .dest_signal(rst_n_core)
    );
    /* verilator lint_on SYNCASYNCNET */

    // Synchronize control inputs into clk_core domain
    logic sync_kill_switch_core;
    cdc_sync_bit u_kill_sync (
        .dest_clk   (clk_core),
        .dest_rst_n (rst_n_core),
        .src_signal (cfg_kill_switch),
        .dest_signal(sync_kill_switch_core)
    );

    logic sync_auto_trade_core;
    cdc_sync_bit u_auto_sync (
        .dest_clk   (clk_core),
        .dest_rst_n (rst_n_core),
        .src_signal (cfg_auto_trade_enable),
        .dest_signal(sync_auto_trade_core)
    );

    // ------------------------------------------------------------------------
    // 2. Free-Running Network Latency Timer (clk_net domain)
    // ------------------------------------------------------------------------
    logic [47:0] timer_net;
    logic [47:0] frame_rx_start_time_net;
    logic        in_rx_frame_net;

    assign cycle_counter_net = timer_net;

    always_ff @(posedge clk_net or negedge rst_n) begin
        if (!rst_n) begin
            timer_net                 <= '0;
            frame_rx_start_time_net   <= '0;
            in_rx_frame_net           <= 1'b0;
            last_tick_to_trade_cycles <= '0;
            tick_to_trade_strobe      <= 1'b0;
        end else begin
            timer_net            <= timer_net + 1'b1;
            tick_to_trade_strobe <= 1'b0;

            if (s_axis_tvalid && s_axis_tready) begin
                if (!in_rx_frame_net) begin
                    frame_rx_start_time_net <= timer_net;
                    in_rx_frame_net         <= 1'b1;
                end
                if (s_axis_tlast) begin
                    in_rx_frame_net <= 1'b0;
                end
            end

            // Measure end-to-end latency when first word of OUCH order leaves on network
            if (m_axis_tvalid && m_axis_tready) begin
                if (frame_rx_start_time_net != 48'd0) begin
                    last_tick_to_trade_cycles <= 16'(timer_net - frame_rx_start_time_net);
                    tick_to_trade_strobe      <= 1'b1;
                end
            end
        end
    end

    // ------------------------------------------------------------------------
    // 2.1 Ethernet FCS CRC-32 Cut-Through Checker (clk_net domain)
    // ------------------------------------------------------------------------
    logic [63:0] fcs_axis_tdata;
    logic [7:0]  fcs_axis_tkeep;
    logic        fcs_axis_tvalid;
    logic        fcs_axis_tlast;
    logic        fcs_axis_tready;
    logic [31:0] fcs_calculated;
    logic        fcs_valid;
    logic        fcs_error;
    logic [31:0] fcs_error_count;

    /* verilator lint_off PINCONNECTEMPTY */
    axis_eth_fcs_checker #(
        .CHECK_TRAILING_FCS(0)
    ) u_fcs_checker (
        .clk               (clk_net),
        .rst_n             (rst_n),
        .s_axis_tdata      (s_axis_tdata),
        .s_axis_tkeep      (s_axis_tkeep),
        .s_axis_tvalid     (s_axis_tvalid),
        .s_axis_tlast      (s_axis_tlast),
        .s_axis_tready     (s_axis_tready),
        .m_axis_tdata      (fcs_axis_tdata),
        .m_axis_tkeep      (fcs_axis_tkeep),
        .m_axis_tvalid     (fcs_axis_tvalid),
        .m_axis_tlast      (fcs_axis_tlast),
        .m_axis_tready     (fcs_axis_tready),
        .expected_fcs_valid(1'b0),
        .expected_fcs      (32'h0),
        .fcs_calculated    (fcs_calculated),
        .fcs_valid         (fcs_valid),
        .fcs_error         (fcs_error),
        .frame_count       (),
        .fcs_error_count   (fcs_error_count)
    );
    /* verilator lint_on PINCONNECTEMPTY */

    // ------------------------------------------------------------------------
    // 2.2 IEEE 1588-2008 PTP 96-bit Hardware Timer (clk_net domain)
    // ------------------------------------------------------------------------
    logic [95:0] ptp_timestamp;
    logic [47:0] ptp_sec;
    logic [31:0] ptp_ns;
    logic [15:0] ptp_fns;
    logic        ptp_pps;

    ptp_timer_96b #(
        .DEFAULT_STEP_NS (6),
        .DEFAULT_STEP_FNS(26214) // 6.4 ns @ 156.25 MHz
    ) u_ptp_timer (
        .clk           (clk_net),
        .rst_n         (rst_n),
        .cfg_step_ns   (8'd6),
        .cfg_step_fns  (16'd26214),
        .cfg_step_load (1'b0),
        .load_en       (1'b0),
        .load_timestamp(96'd0),
        .ptp_timestamp (ptp_timestamp),
        .ptp_sec       (ptp_sec),
        .ptp_ns        (ptp_ns),
        .ptp_fns       (ptp_fns),
        .pps_pulse     (ptp_pps)
    );

    // ------------------------------------------------------------------------
    // 2.3 Wire-to-Wire Hardware Latency Metrology (clk_net domain)
    // ------------------------------------------------------------------------
    logic        rx_sop_strobe;
    logic        tx_sop_strobe;
    logic [31:0] metrology_last_latency_ns;
    logic [31:0] metrology_min_latency_ns;
    logic [31:0] metrology_max_latency_ns;
    logic [63:0] metrology_cum_latency_ns;
    logic [31:0] metrology_event_count;
    logic        metrology_valid;

    assign rx_sop_strobe = s_axis_tvalid && s_axis_tready && !in_rx_frame_net;
    assign tx_sop_strobe = m_axis_tvalid && m_axis_tready;

    latency_metrology #(
        .FIFO_DEPTH(16)
    ) u_metrology (
        .clk            (clk_net),
        .rst_n          (rst_n),
        .ptp_timestamp  (ptp_timestamp),
        .rx_sop         (rx_sop_strobe),
        .tx_sop         (tx_sop_strobe),
        .stats_clear    (1'b0),
        .last_latency_ns(metrology_last_latency_ns),
        .min_latency_ns (metrology_min_latency_ns),
        .max_latency_ns (metrology_max_latency_ns),
        .cum_latency_ns (metrology_cum_latency_ns),
        .event_count    (metrology_event_count),
        .latency_valid  (metrology_valid)
    );

    // Top-Level Metrology Assignments
    assign ptp_timestamp_out         = ptp_timestamp;
    assign fcs_error_count_out       = fcs_error_count;
    assign wire_to_wire_latency_ns   = metrology_last_latency_ns;
    assign min_latency_ns            = metrology_min_latency_ns;
    assign max_latency_ns            = metrology_max_latency_ns;
    assign latency_measurement_valid = metrology_valid;

    // ------------------------------------------------------------------------
    // 3. Network Ingress Pipeline (clk_net @ 156.25 MHz)
    // ------------------------------------------------------------------------
    logic             parsed_msg_valid_net;
    itch_parsed_msg_t parsed_msg_net;

    /* verilator lint_off PINCONNECTEMPTY */
    ingress_pipeline_top #(
        .STRIP_ETH_IP_UDP       (STRIP_ETH_IP_UDP),
        .USE_SPECULATIVE_PARSER (1'b1)
    ) u_ingress (
        .clk                  (clk_net),
        .rst_n                (rst_n),
        .book_backpressure    (1'b0),  // book is behind a CDC FIFO here: not wired (experimental)
        .s_axis_tdata         (fcs_axis_tdata),
        .s_axis_tkeep         (fcs_axis_tkeep),
        .s_axis_tvalid        (fcs_axis_tvalid),
        .s_axis_tlast         (fcs_axis_tlast),
        .s_axis_tready        (fcs_axis_tready),
        .parsed_msg_valid     (parsed_msg_valid_net),
        .parsed_msg           (parsed_msg_net),
        .out_msg_type         (),
        .out_stock_locate     (),
        .out_tracking_num     (),
        .out_timestamp        (),
        .out_order_ref        (),
        .out_side             (),
        .out_shares           (),
        .out_stock            (),
        .out_price            (),
        .out_match_number     (),
        .out_printable        (),
        .out_orig_order_ref   (),
        .out_new_order_ref    (),
        .out_mpid             (),
        .session_name         (),
        .sequence_number      (),
        .message_count        (),
        .pkt_header_valid     (),
        .gap_detected         (),
        .gap_count            (),
        .duplicate_detected   (),
        .expected_seq_out     (),
        .msg_drop             (),
        .unsupported_type_code(),
        .parsed_msg_count     (parsed_msg_count),
        .dropped_msg_count    ()
    );

    // ------------------------------------------------------------------------
    // 4. Ingress CDC Bridge: clk_net (156.25 MHz) -> clk_core (312.5 MHz)
    // ------------------------------------------------------------------------
    logic             parsed_msg_valid_core;
    itch_parsed_msg_t parsed_msg_core;

    cdc_msg_fifo #(
        .ADDR_WIDTH(4) // 16-deep dual-clock FIFO
    ) u_ingress_cdc (
        .clk_src        (clk_net),
        .rst_n_src      (rst_n),
        .src_valid      (parsed_msg_valid_net),
        .src_msg        (parsed_msg_net),
        .src_ready      (),
        .clk_dest       (clk_core),
        .rst_n_dest     (rst_n_core),
        .dest_valid     (parsed_msg_valid_core),
        .dest_msg       (parsed_msg_core),
        .dest_ready     (1'b1),
        .fifo_full_src  (ingress_cdc_full),
        .fifo_empty_dest(ingress_cdc_empty)
    );

    // ------------------------------------------------------------------------
    // 5. High-Frequency Compute Core (clk_core @ 312.5 MHz)
    // ------------------------------------------------------------------------
    logic [31:0] core_top5_bid_price  [0:4];
    logic [31:0] core_top5_bid_shares [0:4];
    logic [31:0] core_top5_ask_price  [0:4];
    logic [31:0] core_top5_ask_shares [0:4];
    logic [31:0] active_orders_core;
    logic        core_depletion_valid;
    logic        core_depletion_side;
    logic [31:0] core_depletion_price;
    logic [31:0] core_depletion_shares;

    /* verilator lint_off PINMISSING */
    lob_engine_top #(
        .TARGET_STOCK        (TARGET_STOCK),
        .ENABLE_SYMBOL_FILTER(ENABLE_SYMBOL_FILTER),
        .NUM_SETS            (NUM_SETS),
        .NUM_WAYS            (NUM_WAYS),
        .BOOK_DEPTH          (BOOK_DEPTH)
    ) u_lob_core (
        .clk                  (clk_core),
        .rst_n                (rst_n_core),
        .parsed_msg_valid     (parsed_msg_valid_core),
        .parsed_msg           (parsed_msg_core),
        .bbo_valid            (bbo_valid),
        .best_bid_price       (best_bid_price),
        .best_bid_shares      (best_bid_shares),
        .best_ask_price       (best_ask_price),
        .best_ask_shares      (best_ask_shares),
        .spread               (spread),
        .mid_price            (mid_price),
        .bbo_updated          (bbo_updated),
        .top5_bid_price       (core_top5_bid_price),
        .top5_bid_shares      (core_top5_bid_shares),
        .top5_ask_price       (core_top5_ask_price),
        .top5_ask_shares      (core_top5_ask_shares),
        .active_order_count   (active_orders_core),
        .depletion_event_valid(core_depletion_valid),
        .depletion_event_side (core_depletion_side),
        .depletion_event_price(core_depletion_price),
        .depletion_event_shares(core_depletion_shares)
    );

    // Microstructure Quantitative Engine on clk_core
    quant_engine_top #(
        .NUM_TRACKED_ORDERS(NUM_TRACKED_ORDERS)
    ) u_quant_core (
        .clk                 (clk_core),
        .rst_n               (rst_n_core),
        .bbo_valid           (bbo_valid),
        .best_bid_price      (best_bid_price),
        .best_bid_shares     (best_bid_shares),
        .best_ask_price      (best_ask_price),
        .best_ask_shares     (best_ask_shares),
        .spread              (spread),
        .event_valid         (core_depletion_valid),
        .event_side          (core_depletion_side),
        .event_price         (core_depletion_price),
        .event_shares_reduced(core_depletion_shares),
        .cfg_valid           (1'b0),
        .cfg_slot_idx        ('0),
        .cfg_side            (1'b0),
        .cfg_price           ('0),
        .cfg_shares          ('0),
        .cfg_initial_volume  ('0),
        .cfg_cancel          (1'b0),
        .obi_valid           (obi_valid),
        .obi_val             (obi_val),
        .micro_price         (micro_price),
        .quant_bid_price     (),
        .quant_ask_price     (),
        .quant_spread        (),
        .slot_active         (),
        .slot_volume_ahead   (),
        .slot_is_top_of_queue()
    );
    /* verilator lint_on PINMISSING */

    // Circuit Breaker on clk_core
    logic circuit_breaker_tripped_core;
    pnl_circuit_breaker u_breaker_core (
        .clk                     (clk_core),
        .rst_n                   (rst_n_core),
        .exec_valid              (1'b0),
        .exec_side               (1'b0),
        .exec_shares             (32'd0),
        .exec_price              (32'd0),
        .mid_valid               (bbo_valid),
        .mid_price               (mid_price),
        .cfg_max_drawdown_limit  (64'd100_000_000),
        .cfg_breaker_manual_reset(1'b0),
        .allow_tx                (),
        .breaker_tripped         (circuit_breaker_tripped_core),
        .breaker_trip_strobe     (),
        .telemetry_cash_flow     (),
        .telemetry_inventory     (),
        .telemetry_mtm_pnl       (),
        .telemetry_peak_pnl      (),
        .telemetry_drawdown      (),
        .total_trip_events       ()
    );

    // ------------------------------------------------------------------------
    // 6. Pre-Trade Risk & OUCH Generator (clk_core domain)
    // ------------------------------------------------------------------------
    logic [63:0] core_axis_tdata;
    logic [7:0]  core_axis_tkeep;
    logic        core_axis_tvalid;
    logic        core_axis_tlast;
    logic        core_axis_tready;

    /* verilator lint_off PINMISSING */
    risk_ouch_top #(
        .DEFAULT_STOCK(TARGET_STOCK)
    ) u_risk_ouch_core (
        .clk                       (clk_core),
        .rst_n                     (rst_n_core),
        .bbo_valid                 (bbo_valid),
        .bbo_bid_shares            (best_bid_shares),
        .bbo_ask_shares            (best_ask_shares),
        .bbo_bid_price             (best_bid_price),
        .bbo_ask_price             (best_ask_price),
        .current_timestamp         (timer_net), // Coarse network timestamp
        .cfg_auto_trade_enable     (sync_auto_trade_core),
        .cfg_obi_buy_thresh        (cfg_obi_buy_thresh),
        .cfg_obi_sell_thresh       (cfg_obi_sell_thresh),
        .cfg_default_order_shares  (cfg_default_order_shares),
        .host_intent_valid         (host_intent_valid),
        .host_intent_side          (host_intent_side),
        .host_intent_shares        (host_intent_shares),
        .host_intent_price         (host_intent_price),
        .host_intent_token         (host_intent_token),
        .cfg_kill_switch           (sync_kill_switch_core),
        .cfg_circuit_breaker_tripped(circuit_breaker_tripped_core),
        .cfg_max_order_shares      (cfg_max_order_shares),
        .cfg_price_collar_threshold(cfg_price_collar_threshold),
        .cfg_max_notional_raw      (cfg_max_notional_raw),
        .cfg_max_cum_notional_raw  (cfg_max_cum_notional_raw),
        .risk_approved_strobe      (risk_approved_strobe),
        .risk_rejected_strobe      (risk_rejected_strobe),
        .risk_reject_reason        (risk_reject_reason),
        .accumulated_notional_raw  (),
        .total_orders_approved     (),
        .total_orders_rejected     (),
        .m_axis_tdata              (core_axis_tdata),
        .m_axis_tkeep              (core_axis_tkeep),
        .m_axis_tvalid             (core_axis_tvalid),
        .m_axis_tlast              (core_axis_tlast),
        .m_axis_tready             (core_axis_tready),
        .tx_busy                   (),
        .tx_order_count            (tx_order_count),
        .tx_egress_timestamp       ()
    );
    /* verilator lint_on PINMISSING */

    // ------------------------------------------------------------------------
    // 7. Egress CDC Bridge: clk_core (312.5 MHz) -> clk_net (156.25 MHz)
    // ------------------------------------------------------------------------
    axis_async_fifo #(
        .DATA_WIDTH(64),
        .ADDR_WIDTH(4) // 16-deep dual-clock FIFO
    ) u_egress_cdc (
        .s_clk        (clk_core),
        .s_rst_n      (rst_n_core),
        .s_axis_tdata (core_axis_tdata),
        .s_axis_tkeep (core_axis_tkeep),
        .s_axis_tvalid(core_axis_tvalid),
        .s_axis_tlast (core_axis_tlast),
        .s_axis_tuser (1'b0),
        .s_axis_tready(core_axis_tready),

        .m_clk        (clk_net),
        .m_rst_n      (rst_n),
        .m_axis_tdata (m_axis_tdata),
        .m_axis_tkeep (m_axis_tkeep),
        .m_axis_tvalid(m_axis_tvalid),
        .m_axis_tlast (m_axis_tlast),
        .m_axis_tuser (),
        .m_axis_tready(m_axis_tready),

        .s_fifo_full  (egress_cdc_full),
        .m_fifo_empty (egress_cdc_empty),
        .s_fifo_level (),
        .m_fifo_level ()
    );
    /* verilator lint_on PINCONNECTEMPTY */

endmodule : aura_hft_dual_clock_top

`endif // AURA_HFT_DUAL_CLOCK_TOP_SV
