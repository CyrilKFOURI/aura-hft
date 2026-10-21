`ifndef AURA_HFT_TOP_SV
`define AURA_HFT_TOP_SV

`timescale 1ns / 1ps

`include "itch_pkg.sv"
`include "lob_pkg.sv"
`include "ouch_pkg.sv"

/**
 * aura_hft_top.sv
 *
 * Accelerated Ultra-low-latency Reconfigurable Architecture for High-Frequency Trading (AURA-HFT).
 * Target Device: AMD Kria KR260 (AMD Zynq UltraScale+ xck26-sfvc784-2LV-c).
 * Clock Rate: 156.25 MHz (6.4 ns period).
 *
 * Complete End-to-End Tick-to-Trade Datapath:
 *   1. Ingress Network Pipeline (Ethernet/IPv4/UDP/MoldUDP64 depacketizer + ITCH 5.0 parser)
 *   2. Hardware Limit Order Book Engine (4-way BRAM hash table, L2 ladder, $O(1)$ BBO cache)
 *   3. Microstructure Quantitative Engine (Pipelined OBI Q1.31, DSP Micro-Price, Queue Tracker)
 *   4. Autonomous Strategy Trigger & Pre-Trade Risk Engine (1-cycle combinatorial validation)
 *   5. Egress Network Transmitter (91-byte OUCH 5.0 Enter Order over 64-bit AXI4-Stream)
 *   6. Hardware Cycle-Accurate Latency Telemetry Engine
 */

module aura_hft_top #(
    parameter bit          STRIP_ETH_IP_UDP     = 1'b1,
    parameter logic [63:0] TARGET_STOCK         = 64'h4141504C20202020, // "AAPL    "
    parameter bit          ENABLE_SYMBOL_FILTER = 1'b1,
    parameter int unsigned NUM_SETS             = 8192,
    parameter int unsigned NUM_WAYS             = 4,
    parameter int unsigned BOOK_DEPTH           = 16,
    parameter int unsigned NUM_TRACKED_ORDERS   = 4
) (
    input  logic        clk,
    input  logic        rst_n,

    // Ingress (RX) 64-bit AXI4-Stream Interface from 10G SFP+ MAC
    input  logic [63:0] s_axis_tdata,
    input  logic [7:0]  s_axis_tkeep,
    input  logic        s_axis_tvalid,
    input  logic        s_axis_tlast,
    output logic        s_axis_tready,

    // Egress (TX) 64-bit AXI4-Stream Interface to 10G SFP+ MAC
    output logic [63:0] m_axis_tdata,
    output logic [7:0]  m_axis_tkeep,
    output logic        m_axis_tvalid,
    output logic        m_axis_tlast,
    input  logic        m_axis_tready,

    // AXI4-Lite Slave Interface for Host CPU / Real-Time Live Tuning
    input  logic [7:0]  s_axi_awaddr,
    input  logic [2:0]  s_axi_awprot,
    input  logic        s_axi_awvalid,
    output logic        s_axi_awready,

    input  logic [31:0] s_axi_wdata,
    input  logic [3:0]  s_axi_wstrb,
    input  logic        s_axi_wvalid,
    output logic        s_axi_wready,

    output logic [1:0]  s_axi_bresp,
    output logic        s_axi_bvalid,
    input  logic        s_axi_bready,

    input  logic [7:0]  s_axi_araddr,
    input  logic [2:0]  s_axi_arprot,
    input  logic        s_axi_arvalid,
    output logic        s_axi_arready,

    output logic [31:0] s_axi_rdata,
    output logic [1:0]  s_axi_rresp,
    output logic        s_axi_rvalid,
    input  logic        s_axi_rready,

    // Configuration & Control Registers (from AXI-Lite / Host Interface)
    input  logic               cfg_auto_trade_enable,
    input  logic signed [31:0] cfg_obi_buy_thresh,    // Q1.31
    input  logic signed [31:0] cfg_obi_sell_thresh,   // Q1.31
    input  logic [31:0]        cfg_default_order_shares,

    input  logic        cfg_kill_switch,
    input  logic [31:0] cfg_max_order_shares,
    input  logic [31:0] cfg_price_collar_threshold,
    input  logic [63:0] cfg_max_notional_raw,
    input  logic [63:0] cfg_max_cum_notional_raw,

    // Host Manual Order Intent Port
    input  logic        host_intent_valid,
    input  logic        host_intent_side,
    input  logic [31:0] host_intent_shares,
    input  logic [31:0] host_intent_price,
    input  logic [31:0] host_intent_token,

    // Virtual Order Queue Tracking Configuration
    input  logic        cfg_queue_valid,
    input  logic [1:0]  cfg_queue_slot,
    input  logic        cfg_queue_side,
    input  logic [31:0] cfg_queue_price,
    input  logic [31:0] cfg_queue_shares,
    input  logic [31:0] cfg_queue_initial_vol,
    input  logic        cfg_queue_cancel,

    // Live Market & Quant Telemetry
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

    // Queue Tracking Telemetry
    output logic [NUM_TRACKED_ORDERS-1:0]        slot_active,
    output logic [NUM_TRACKED_ORDERS-1:0][31:0]  slot_volume_ahead,
    output logic [NUM_TRACKED_ORDERS-1:0]        slot_is_top_of_queue,

    // Risk & Execution Telemetry
    output logic        risk_approved_strobe,
    output logic        risk_rejected_strobe,
    output logic [3:0]  risk_reject_reason,
    output logic [63:0] accumulated_notional_raw,
    output logic [31:0] total_orders_approved,
    output logic [31:0] total_orders_rejected,

    // Top-5 Depth Arrays
    output logic [31:0] top5_bid_price  [0:4],
    output logic [31:0] top5_bid_shares [0:4],
    output logic [31:0] top5_ask_price  [0:4],
    output logic [31:0] top5_ask_shares [0:4],

    // Global Telemetry & In-Hardware Latency Engine
    output logic [47:0] cycle_counter,
    output logic [15:0] last_tick_to_trade_cycles,
    output logic        tick_to_trade_strobe,
    output logic [31:0] tx_order_count,
    output logic [31:0] parsed_msg_count,
    output logic [31:0] active_order_count,

    // IEEE 1588 PTP & Wire-to-Wire Metrology Outputs
    output logic [95:0] ptp_timestamp_out,
    output logic [31:0] fcs_error_count_out,
    output logic [31:0] wire_to_wire_latency_ns,
    output logic [31:0] min_latency_ns,
    output logic [31:0] max_latency_ns,
    output logic        latency_measurement_valid
);

    import itch_pkg::*;
    import lob_pkg::*;
    import ouch_pkg::*;

    // -------------------------------------------------------------
    // Free-Running High-Resolution Hardware Cycle Timer
    // -------------------------------------------------------------
    logic [47:0] hw_timer;
    logic [47:0] frame_rx_start_time;
    logic        in_rx_frame;
    logic        in_tx_frame;

    assign cycle_counter = hw_timer;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            hw_timer                   <= '0;
            frame_rx_start_time        <= '0;
            in_rx_frame                <= 1'b0;
            in_tx_frame                <= 1'b0;
            last_tick_to_trade_cycles  <= '0;
            tick_to_trade_strobe       <= 1'b0;
        end else begin
            hw_timer             <= hw_timer + 1'b1;
            tick_to_trade_strobe <= 1'b0;

            // Ingress packet arrival tracking
            if (s_axis_tvalid && s_axis_tready) begin
                if (!in_rx_frame) begin
                    frame_rx_start_time <= hw_timer;
                    in_rx_frame         <= 1'b1;
                end
                if (s_axis_tlast) begin
                    in_rx_frame <= 1'b0;
                end
            end

            // Egress packet transmission tracking
            if (m_axis_tvalid && m_axis_tready) begin
                if (!in_tx_frame) begin
                    in_tx_frame               <= 1'b1;
                    tick_to_trade_strobe      <= 1'b1;
                    last_tick_to_trade_cycles <= 16'(hw_timer - frame_rx_start_time);
                end
                if (m_axis_tlast) begin
                    in_tx_frame <= 1'b0;
                end
            end
        end
    end

    // -------------------------------------------------------------
    // 0. Ethernet FCS CRC-32 Cut-Through Checker
    // -------------------------------------------------------------
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
        .clk               (clk),
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

    // -------------------------------------------------------------
    // 0.1 IEEE 1588-2008 PTP 96-bit Hardware Timer
    // -------------------------------------------------------------
    logic [95:0] ptp_timestamp;
    logic [47:0] ptp_sec;
    logic [31:0] ptp_ns;
    logic [15:0] ptp_fns;
    logic        ptp_pps;

    ptp_timer_96b #(
        .DEFAULT_STEP_NS (6),
        .DEFAULT_STEP_FNS(26214) // 6.4 ns @ 156.25 MHz
    ) u_ptp_timer (
        .clk           (clk),
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

    // -------------------------------------------------------------
    // 0.2 Wire-to-Wire Hardware Latency Metrology
    // -------------------------------------------------------------
    logic        rx_sop_strobe;
    logic        tx_sop_strobe;
    logic [31:0] metrology_last_latency_ns;
    logic [31:0] metrology_min_latency_ns;
    logic [31:0] metrology_max_latency_ns;
    logic [63:0] metrology_cum_latency_ns;
    logic [31:0] metrology_event_count;
    logic        metrology_valid;

    assign rx_sop_strobe = s_axis_tvalid && s_axis_tready && !in_rx_frame;
    assign tx_sop_strobe = m_axis_tvalid && m_axis_tready && !in_tx_frame;

    latency_metrology #(
        .FIFO_DEPTH(16)
    ) u_metrology (
        .clk            (clk),
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

    // -------------------------------------------------------------
    // 1. Ingress Pipeline Instance (MoldUDP64 + ITCH 5.0 Parser)
    // -------------------------------------------------------------
    logic             parsed_msg_valid;
    itch_parsed_msg_t parsed_msg;

    logic book_backpressure;  // order book request FIFO almost full -> stall ingress

    /* verilator lint_off PINMISSING */
    ingress_pipeline_top #(
        .STRIP_ETH_IP_UDP(STRIP_ETH_IP_UDP)
    ) u_ingress (
        .clk                  (clk),
        .rst_n                (rst_n),
        .book_backpressure    (book_backpressure),
        .s_axis_tdata         (fcs_axis_tdata),
        .s_axis_tkeep         (fcs_axis_tkeep),
        .s_axis_tvalid        (fcs_axis_tvalid),
        .s_axis_tlast         (fcs_axis_tlast),
        .s_axis_tready        (fcs_axis_tready),
        .parsed_msg_valid     (parsed_msg_valid),
        .parsed_msg           (parsed_msg),
        .parsed_msg_count     (parsed_msg_count)
    );
    /* verilator lint_on PINMISSING */

    // -------------------------------------------------------------
    // 2. Hardware Limit Order Book Engine Instance
    // -------------------------------------------------------------
    logic        depletion_valid;
    logic        depletion_side;
    logic [31:0] depletion_price;
    logic [31:0] depletion_shares;

    /* verilator lint_off PINMISSING */
    lob_engine_top #(
        .TARGET_STOCK        (TARGET_STOCK),
        .ENABLE_SYMBOL_FILTER(ENABLE_SYMBOL_FILTER),
        .NUM_SETS            (NUM_SETS),
        .NUM_WAYS            (NUM_WAYS),
        .BOOK_DEPTH          (BOOK_DEPTH)
    ) u_lob_engine (
        .clk                  (clk),
        .rst_n                (rst_n),
        .req_almost_full      (book_backpressure),
        .parsed_msg_valid     (parsed_msg_valid),
        .parsed_msg           (parsed_msg),
        .bbo_valid            (bbo_valid),
        .best_bid_price       (best_bid_price),
        .best_bid_shares      (best_bid_shares),
        .best_ask_price       (best_ask_price),
        .best_ask_shares      (best_ask_shares),
        .spread               (spread),
        .mid_price            (mid_price),
        .bbo_updated          (bbo_updated),
        .top5_bid_price       (top5_bid_price),
        .top5_bid_shares      (top5_bid_shares),
        .top5_ask_price       (top5_ask_price),
        .top5_ask_shares      (top5_ask_shares),
        .active_order_count   (active_order_count),
        .depletion_event_valid(depletion_valid),
        .depletion_event_side (depletion_side),
        .depletion_event_price(depletion_price),
        .depletion_event_shares(depletion_shares)
    );
    /* verilator lint_on PINMISSING */

    // -------------------------------------------------------------
    // 3. Quantitative Microstructure Engine Instance
    // -------------------------------------------------------------
    /* verilator lint_off PINCONNECTEMPTY */
    quant_engine_top #(
        .NUM_TRACKED_ORDERS(NUM_TRACKED_ORDERS)
    ) u_quant_engine (
        .clk                 (clk),
        .rst_n               (rst_n),
        .bbo_valid           (bbo_valid),
        .best_bid_price      (best_bid_price),
        .best_bid_shares     (best_bid_shares),
        .best_ask_price      (best_ask_price),
        .best_ask_shares     (best_ask_shares),
        .spread              (spread),
        .event_valid         (depletion_valid),
        .event_side          (depletion_side),
        .event_price         (depletion_price),
        .event_shares_reduced(depletion_shares),
        .cfg_valid           (cfg_queue_valid),
        .cfg_slot_idx        (cfg_queue_slot),
        .cfg_side            (cfg_queue_side),
        .cfg_price           (cfg_queue_price),
        .cfg_shares          (cfg_queue_shares),
        .cfg_initial_volume  (cfg_queue_initial_vol),
        .cfg_cancel          (cfg_queue_cancel),
        .obi_valid           (obi_valid),
        .obi_val             (obi_val),
        .micro_price         (micro_price),
        .quant_bid_price     (),
        .quant_ask_price     (),
        .quant_spread        (),
        .slot_active         (slot_active),
        .slot_volume_ahead   (slot_volume_ahead),
        .slot_is_top_of_queue(slot_is_top_of_queue)
    );

    // -------------------------------------------------------------
    // 3.5. AXI4-Lite Memory-Mapped Control & Telemetry Block
    // -------------------------------------------------------------
    logic        axi_cfg_pipeline_enable;
    logic        axi_cfg_soft_reset;
    logic        axi_cfg_hard_kill_switch;
    logic        axi_cfg_strategy_select;
    logic [31:0] axi_cfg_obi_threshold;
    logic [31:0] axi_cfg_risk_max_shares;
    logic [31:0] axi_cfg_risk_price_collar;
    logic [31:0] axi_cfg_risk_max_notional;
    logic [15:0] axi_cfg_mm_gamma;
    logic [15:0] axi_cfg_mm_sigma_sq;

    axi_lite_control_registers #(
        .ADDR_WIDTH(8),
        .DATA_WIDTH(32)
    ) u_axi_ctrl (
        .clk                      (clk),
        .rst_n                    (rst_n),
        .s_axi_awaddr             (s_axi_awaddr),
        .s_axi_awprot             (s_axi_awprot),
        .s_axi_awvalid            (s_axi_awvalid),
        .s_axi_awready            (s_axi_awready),
        .s_axi_wdata              (s_axi_wdata),
        .s_axi_wstrb              (s_axi_wstrb),
        .s_axi_wvalid             (s_axi_wvalid),
        .s_axi_wready             (s_axi_wready),
        .s_axi_bresp              (s_axi_bresp),
        .s_axi_bvalid             (s_axi_bvalid),
        .s_axi_bready             (s_axi_bready),
        .s_axi_araddr             (s_axi_araddr),
        .s_axi_arprot             (s_axi_arprot),
        .s_axi_arvalid            (s_axi_arvalid),
        .s_axi_arready            (s_axi_arready),
        .s_axi_rdata              (s_axi_rdata),
        .s_axi_rresp              (s_axi_rresp),
        .s_axi_rvalid             (s_axi_rvalid),
        .s_axi_rready             (s_axi_rready),
        .cfg_pipeline_enable      (axi_cfg_pipeline_enable),
        .cfg_soft_reset           (axi_cfg_soft_reset),
        .cfg_hard_kill_switch     (axi_cfg_hard_kill_switch),
        .cfg_strategy_select      (axi_cfg_strategy_select),
        .cfg_obi_threshold        (axi_cfg_obi_threshold),
        .cfg_risk_max_shares      (axi_cfg_risk_max_shares),
        .cfg_risk_price_collar    (axi_cfg_risk_price_collar),
        .cfg_risk_max_notional    (axi_cfg_risk_max_notional),
        .cfg_mm_gamma             (axi_cfg_mm_gamma),
        .cfg_mm_sigma_sq          (axi_cfg_mm_sigma_sq),
        .cfg_max_drawdown_limit   (axi_cfg_max_drawdown),
        .cfg_breaker_manual_reset (axi_cfg_breaker_manual_reset),
        .status_pipeline_ready    (1'b1),
        .status_bbo_valid         (bbo_valid),
        .status_risk_reject       (risk_rejected_strobe),
        .status_breaker_tripped   (circuit_breaker_tripped),
        .status_ingress_count     (parsed_msg_count),
        .status_egress_count      (tx_order_count),
        .status_last_latency      (metrology_last_latency_ns != 32'd0 ? metrology_last_latency_ns : {16'h0, last_tick_to_trade_cycles}),
        .status_current_inventory (pnl_telemetry_inventory),
        .status_mtm_pnl           (pnl_telemetry_mtm),
        .status_drawdown          (pnl_telemetry_drawdown),
        .status_fcs_error_count   (fcs_error_count),
        .status_min_latency       (metrology_min_latency_ns),
        .status_max_latency       (metrology_max_latency_ns),
        .status_ptp_sec           (ptp_sec),
        .status_ptp_ns            (ptp_ns)
    );

    // -------------------------------------------------------------
    // 3.6. Autonomous Real-Time PnL Tracker & Circuit Breaker Instance
    // -------------------------------------------------------------
    logic [63:0]        axi_cfg_max_drawdown;
    logic               axi_cfg_breaker_manual_reset;
    logic               circuit_breaker_tripped;
    logic               circuit_breaker_strobe;
    logic signed [63:0] pnl_telemetry_cash;
    logic signed [31:0] pnl_telemetry_inventory;
    logic signed [63:0] pnl_telemetry_mtm;
    logic signed [63:0] pnl_telemetry_peak;
    logic [63:0]        pnl_telemetry_drawdown;
    logic [31:0]        total_circuit_trips;

    pnl_circuit_breaker #(
        .DEFAULT_MAX_DRAWDOWN(64'd100_000_000) // $10,000.0000
    ) u_pnl_breaker (
        .clk                     (clk),
        .rst_n                   (rst_n),
        .exec_valid              (1'b0), // Will hook execution reports from exchange
        .exec_side               (1'b0),
        .exec_shares             (32'd0),
        .exec_price              (32'd0),
        .mid_valid               (bbo_valid),
        .mid_price               (mid_price),
        .cfg_max_drawdown_limit  (axi_cfg_max_drawdown),
        .cfg_breaker_manual_reset(axi_cfg_breaker_manual_reset),
        .allow_tx                (),
        .breaker_tripped         (circuit_breaker_tripped),
        .breaker_trip_strobe     (circuit_breaker_strobe),
        .telemetry_cash_flow     (pnl_telemetry_cash),
        .telemetry_inventory     (pnl_telemetry_inventory),
        .telemetry_mtm_pnl       (pnl_telemetry_mtm),
        .telemetry_peak_pnl      (pnl_telemetry_peak),
        .telemetry_drawdown      (pnl_telemetry_drawdown),
        .total_trip_events       (total_circuit_trips)
    );

    // Dynamic Merging: AXI-Lite register writes override direct pins if written
    logic               effective_auto_trade_enable;
    logic signed [31:0] effective_obi_buy_thresh;
    logic signed [31:0] effective_obi_sell_thresh;
    logic               effective_kill_switch;
    logic [31:0]        effective_max_order_shares;
    logic [31:0]        effective_price_collar_threshold;
    logic [63:0]        effective_max_notional_raw;

    assign effective_auto_trade_enable      = cfg_auto_trade_enable | axi_cfg_pipeline_enable;
    assign effective_obi_buy_thresh         = (axi_cfg_obi_threshold != 32'h53333333 && axi_cfg_obi_threshold != 32'h0) ? 
                                              $signed(axi_cfg_obi_threshold) : cfg_obi_buy_thresh;
    assign effective_obi_sell_thresh        = (axi_cfg_obi_threshold != 32'h53333333 && axi_cfg_obi_threshold != 32'h0) ? 
                                              -$signed(axi_cfg_obi_threshold) : cfg_obi_sell_thresh;
    assign effective_kill_switch            = cfg_kill_switch | axi_cfg_hard_kill_switch;
    assign effective_max_order_shares       = (axi_cfg_risk_max_shares != 32'd1000 && axi_cfg_risk_max_shares != 32'd0) ?
                                              axi_cfg_risk_max_shares : cfg_max_order_shares;
    assign effective_price_collar_threshold = (axi_cfg_risk_price_collar != 32'h00000666 && axi_cfg_risk_price_collar != 32'd0) ?
                                              axi_cfg_risk_price_collar : cfg_price_collar_threshold;
    assign effective_max_notional_raw       = (axi_cfg_risk_max_notional != 32'd1000000 && axi_cfg_risk_max_notional != 32'd0) ?
                                              {32'h0, axi_cfg_risk_max_notional} : cfg_max_notional_raw;

    // -------------------------------------------------------------
    // 4. Pre-Trade Risk Engine & OUCH 5.0 Transmitter Top Instance
    // -------------------------------------------------------------
    /* verilator lint_off PINMISSING */
    risk_ouch_top #(
        .DEFAULT_STOCK(TARGET_STOCK)
    ) u_risk_ouch (
        .clk                       (clk),
        .rst_n                     (rst_n),
        .bbo_valid                 (bbo_valid),
        .bbo_bid_shares            (best_bid_shares),
        .bbo_ask_shares            (best_ask_shares),
        .bbo_bid_price             (best_bid_price),
        .bbo_ask_price             (best_ask_price),
        .current_timestamp         (hw_timer),
        .cfg_auto_trade_enable     (effective_auto_trade_enable),
        .cfg_obi_buy_thresh        (effective_obi_buy_thresh),
        .cfg_obi_sell_thresh       (effective_obi_sell_thresh),
        .cfg_default_order_shares  (cfg_default_order_shares),
        .host_intent_valid         (host_intent_valid),
        .host_intent_side          (host_intent_side),
        .host_intent_shares        (host_intent_shares),
        .host_intent_price         (host_intent_price),
        .host_intent_token         (host_intent_token),
        .cfg_kill_switch           (effective_kill_switch),
        .cfg_circuit_breaker_tripped(circuit_breaker_tripped),
        .cfg_max_order_shares      (effective_max_order_shares),
        .cfg_price_collar_threshold(effective_price_collar_threshold),
        .cfg_max_notional_raw      (effective_max_notional_raw),
        .cfg_max_cum_notional_raw  (cfg_max_cum_notional_raw),
        .risk_approved_strobe      (risk_approved_strobe),
        .risk_rejected_strobe      (risk_rejected_strobe),
        .risk_reject_reason        (risk_reject_reason),
        .accumulated_notional_raw  (accumulated_notional_raw),
        .total_orders_approved     (total_orders_approved),
        .total_orders_rejected     (total_orders_rejected),
        .m_axis_tdata              (m_axis_tdata),
        .m_axis_tkeep              (m_axis_tkeep),
        .m_axis_tvalid             (m_axis_tvalid),
        .m_axis_tlast              (m_axis_tlast),
        .m_axis_tready             (m_axis_tready),
        .tx_busy                   (),
        .tx_order_count            (tx_order_count),
        .tx_egress_timestamp       ()
    );
    /* verilator lint_on PINMISSING */
    /* verilator lint_on PINCONNECTEMPTY */

endmodule : aura_hft_top

`endif // AURA_HFT_TOP_SV
