// ============================================================================
// Module Name:   axi_lite_control_registers
// Description:   AXI4-Lite 32-bit Memory-Mapped Slave for AURA-HFT Configuration
//                and Live Hardware Telemetry Monitoring.
// Standard:      SystemVerilog IEEE 1800-2017 / ARM AMBA AXI4-Lite
// ============================================================================

`timescale 1ns / 1ps

module axi_lite_control_registers #(
    parameter int ADDR_WIDTH = 8,
    parameter int DATA_WIDTH = 32
)(
    input  logic                   clk,
    input  logic                   rst_n,

    // ------------------------------------------------------------------------
    // AXI4-Lite Slave Interface
    // ------------------------------------------------------------------------
    // Write Address Channel
    input  logic [ADDR_WIDTH-1:0]  s_axi_awaddr,
    input  logic [2:0]             s_axi_awprot,
    input  logic                   s_axi_awvalid,
    output logic                   s_axi_awready,

    // Write Data Channel
    input  logic [DATA_WIDTH-1:0]  s_axi_wdata,
    input  logic [DATA_WIDTH/8-1:0] s_axi_wstrb,
    input  logic                   s_axi_wvalid,
    output logic                   s_axi_wready,

    // Write Response Channel
    output logic [1:0]             s_axi_bresp,
    output logic                   s_axi_bvalid,
    input  logic                   s_axi_bready,

    // Read Address Channel
    input  logic [ADDR_WIDTH-1:0]  s_axi_araddr,
    input  logic [2:0]             s_axi_arprot,
    input  logic                   s_axi_arvalid,
    output logic                   s_axi_arready,

    // Read Data Channel
    output logic [DATA_WIDTH-1:0]  s_axi_rdata,
    output logic [1:0]             s_axi_rresp,
    output logic                   s_axi_rvalid,
    input  logic                   s_axi_rready,

    // ------------------------------------------------------------------------
    // Live Hardware Configuration Outputs
    // ------------------------------------------------------------------------
    output logic                   cfg_pipeline_enable,
    output logic                   cfg_soft_reset,
    output logic                   cfg_hard_kill_switch,
    output logic                   cfg_strategy_select, // 0 = OBI Threshold, 1 = Avellaneda-Stoikov
    output logic [31:0]            cfg_obi_threshold,
    output logic [31:0]            cfg_risk_max_shares,
    output logic [31:0]            cfg_risk_price_collar,
    output logic [31:0]            cfg_risk_max_notional,
    output logic [15:0]            cfg_mm_gamma,
    output logic [15:0]            cfg_mm_sigma_sq,
    output logic [63:0]            cfg_max_drawdown_limit,
    output logic                   cfg_breaker_manual_reset,

    // ------------------------------------------------------------------------
    // Read-Only Status & Telemetry Inputs from RTL Pipeline
    // ------------------------------------------------------------------------
    input  logic                   status_pipeline_ready,
    input  logic                   status_bbo_valid,
    input  logic                   status_risk_reject,
    input  logic                   status_breaker_tripped,
    input  logic [31:0]            status_ingress_count,
    input  logic [31:0]            status_egress_count,
    input  logic [31:0]            status_last_latency,
    input  logic signed [31:0]     status_current_inventory,
    input  logic signed [63:0]     status_mtm_pnl,
    input  logic [63:0]            status_drawdown,
    input  logic [31:0]            status_fcs_error_count = '0,
    input  logic [31:0]            status_min_latency     = '0,
    input  logic [31:0]            status_max_latency     = '0,
    input  logic [47:0]            status_ptp_sec         = '0,
    input  logic [31:0]            status_ptp_ns          = '0
);

    // ------------------------------------------------------------------------
    // Register Address Offsets
    // ------------------------------------------------------------------------
    localparam logic [7:0] ADDR_CONTROL           = 8'h00;
    localparam logic [7:0] ADDR_OBI_THRESHOLD     = 8'h04;
    localparam logic [7:0] ADDR_RISK_MAX_SHARES   = 8'h08;
    localparam logic [7:0] ADDR_RISK_PRICE_COLLAR = 8'h0C;
    localparam logic [7:0] ADDR_RISK_MAX_NOTIONAL = 8'h10;
    localparam logic [7:0] ADDR_MM_GAMMA          = 8'h14;
    localparam logic [7:0] ADDR_MM_SIGMA_SQ       = 8'h18;
    localparam logic [7:0] ADDR_STATUS            = 8'h1C;
    localparam logic [7:0] ADDR_INGRESS_COUNT     = 8'h20;
    localparam logic [7:0] ADDR_EGRESS_COUNT      = 8'h24;
    localparam logic [7:0] ADDR_LAST_LATENCY      = 8'h28;
    localparam logic [7:0] ADDR_CURRENT_INVENTORY = 8'h2C;
    localparam logic [7:0] ADDR_MAX_DRAWDOWN_LOW  = 8'h30;
    localparam logic [7:0] ADDR_MAX_DRAWDOWN_HIGH = 8'h34;
    localparam logic [7:0] ADDR_MTM_PNL_LOW       = 8'h38;
    localparam logic [7:0] ADDR_MTM_PNL_HIGH      = 8'h3C;
    localparam logic [7:0] ADDR_DRAWDOWN_LOW      = 8'h40;
    localparam logic [7:0] ADDR_DRAWDOWN_HIGH     = 8'h44;
    localparam logic [7:0] ADDR_FCS_ERROR_COUNT   = 8'h48;
    localparam logic [7:0] ADDR_MIN_LATENCY_NS     = 8'h4C;
    localparam logic [7:0] ADDR_MAX_LATENCY_NS     = 8'h50;
    localparam logic [7:0] ADDR_PTP_TIME_SEC_LOW   = 8'h54;
    localparam logic [7:0] ADDR_PTP_TIME_SEC_HIGH  = 8'h58;
    localparam logic [7:0] ADDR_PTP_TIME_NS        = 8'h5C;

    // ------------------------------------------------------------------------
    // Internal Configuration Registers (with defaults)
    // ------------------------------------------------------------------------
    // Default OBI Threshold: +0.65 in Q1.31 = 0.65 * 2^31 = 1,395,864,371 = 32'h53333333
    localparam logic [31:0] DEFAULT_OBI_THRESHOLD = 32'h53333333;
    // Default Price Collar: 5.0% in Q1.15 = 0.05 * 2^15 = 1638 = 16'h0666
    localparam logic [31:0] DEFAULT_PRICE_COLLAR  = 32'h00000666;

    logic [31:0] reg_control;
    logic [31:0] reg_obi_threshold;
    logic [31:0] reg_risk_max_shares;
    logic [31:0] reg_risk_price_collar;
    logic [31:0] reg_risk_max_notional;
    logic [31:0] reg_mm_gamma;
    logic [31:0] reg_mm_sigma_sq;
    logic [31:0] reg_max_drawdown_low;
    logic [31:0] reg_max_drawdown_high;

    // Register outputs to core
    assign cfg_pipeline_enable      = reg_control[0];
    assign cfg_soft_reset           = reg_control[1];
    assign cfg_hard_kill_switch     = reg_control[2];
    assign cfg_strategy_select      = reg_control[3];
    assign cfg_breaker_manual_reset = reg_control[4]; // bit 4: pulse/write 1 to reset tripped circuit breaker
    assign cfg_obi_threshold        = reg_obi_threshold;
    assign cfg_risk_max_shares      = reg_risk_max_shares;
    assign cfg_risk_price_collar    = reg_risk_price_collar;
    assign cfg_risk_max_notional    = reg_risk_max_notional;
    assign cfg_mm_gamma             = reg_mm_gamma[15:0];
    assign cfg_mm_sigma_sq          = reg_mm_sigma_sq[15:0];
    assign cfg_max_drawdown_limit   = {reg_max_drawdown_high, reg_max_drawdown_low};

    // Status word assembly
    logic [31:0] reg_status;
    assign reg_status = {
        27'h0,
        status_breaker_tripped,  // bit 4: circuit_breaker_tripped
        reg_control[2],          // bit 3: kill_switch_engaged
        status_risk_reject,      // bit 2: risk_reject_active
        status_bbo_valid,        // bit 1: bbo_valid
        status_pipeline_ready    // bit 0: pipeline_ready
    };

    // ------------------------------------------------------------------------
    // AXI4-Lite Write Channel FSM
    // ------------------------------------------------------------------------
    logic [ADDR_WIDTH-1:0] write_addr;
    logic                  write_addr_valid;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s_axi_awready        <= 1'b0;
            s_axi_wready         <= 1'b0;
            s_axi_bvalid         <= 1'b0;
            s_axi_bresp          <= 2'b00;
            write_addr           <= '0;
            write_addr_valid     <= 1'b0;
            // Default register resets
            reg_control          <= 32'h00000001; // pipeline_enable = 1 by default
            reg_obi_threshold    <= DEFAULT_OBI_THRESHOLD;
            reg_risk_max_shares  <= 32'd1000;
            reg_risk_price_collar<= DEFAULT_PRICE_COLLAR;
            reg_risk_max_notional<= 32'd1000000;
            reg_mm_gamma          <= 32'h00000100; // gamma = 0.0078
            reg_mm_sigma_sq       <= 32'h00000200; // sigma^2 = 0.0156
            reg_max_drawdown_low  <= 32'd100_000_000; // Default $10,000.0000 drawdown
            reg_max_drawdown_high <= 32'd0;
        end else begin
            // Address handshake
            if (!s_axi_awready && s_axi_awvalid && !write_addr_valid) begin
                s_axi_awready    <= 1'b1;
                write_addr       <= s_axi_awaddr;
                write_addr_valid <= 1'b1;
            end else begin
                s_axi_awready    <= 1'b0;
            end

            // Data handshake and register write
            if (!s_axi_wready && s_axi_wvalid && (write_addr_valid || s_axi_awvalid)) begin
                s_axi_wready <= 1'b1;
                s_axi_bvalid <= 1'b1;
                s_axi_bresp  <= 2'b00; // OKAY

                // Use latched address or immediate address
                case (write_addr_valid ? write_addr[7:0] : s_axi_awaddr[7:0])
                    ADDR_CONTROL:           reg_control           <= s_axi_wdata;
                    ADDR_OBI_THRESHOLD:     reg_obi_threshold     <= s_axi_wdata;
                    ADDR_RISK_MAX_SHARES:   reg_risk_max_shares   <= s_axi_wdata;
                    ADDR_RISK_PRICE_COLLAR: reg_risk_price_collar <= s_axi_wdata;
                    ADDR_RISK_MAX_NOTIONAL: reg_risk_max_notional <= s_axi_wdata;
                    ADDR_MM_GAMMA:          reg_mm_gamma          <= s_axi_wdata;
                    ADDR_MM_SIGMA_SQ:       reg_mm_sigma_sq       <= s_axi_wdata;
                    ADDR_MAX_DRAWDOWN_LOW:  reg_max_drawdown_low  <= s_axi_wdata;
                    ADDR_MAX_DRAWDOWN_HIGH: reg_max_drawdown_high <= s_axi_wdata;
                    default: ; // Read-only or unmapped addresses ignore writes
                endcase

                write_addr_valid <= 1'b0;
            end else begin
                s_axi_wready <= 1'b0;
            end

            // Response handshake
            if (s_axi_bvalid && s_axi_bready) begin
                s_axi_bvalid <= 1'b0;
            end
        end
    end

    // ------------------------------------------------------------------------
    // AXI4-Lite Read Channel FSM
    // ------------------------------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s_axi_arready <= 1'b0;
            s_axi_rvalid  <= 1'b0;
            s_axi_rresp   <= 2'b00;
            s_axi_rdata   <= '0;
        end else begin
            // Read address handshake
            if (!s_axi_arready && s_axi_arvalid && !s_axi_rvalid) begin
                s_axi_arready <= 1'b1;
                s_axi_rvalid  <= 1'b1;
                s_axi_rresp   <= 2'b00; // OKAY

                // Read multiplexer
                case (s_axi_araddr[7:0])
                    ADDR_CONTROL:           s_axi_rdata <= reg_control;
                    ADDR_OBI_THRESHOLD:     s_axi_rdata <= reg_obi_threshold;
                    ADDR_RISK_MAX_SHARES:   s_axi_rdata <= reg_risk_max_shares;
                    ADDR_RISK_PRICE_COLLAR: s_axi_rdata <= reg_risk_price_collar;
                    ADDR_RISK_MAX_NOTIONAL: s_axi_rdata <= reg_risk_max_notional;
                    ADDR_MM_GAMMA:          s_axi_rdata <= reg_mm_gamma;
                    ADDR_MM_SIGMA_SQ:       s_axi_rdata <= reg_mm_sigma_sq;
                    ADDR_STATUS:            s_axi_rdata <= reg_status;
                    ADDR_INGRESS_COUNT:     s_axi_rdata <= status_ingress_count;
                    ADDR_EGRESS_COUNT:      s_axi_rdata <= status_egress_count;
                    ADDR_LAST_LATENCY:      s_axi_rdata <= status_last_latency;
                    ADDR_CURRENT_INVENTORY: s_axi_rdata <= status_current_inventory;
                    ADDR_MAX_DRAWDOWN_LOW:  s_axi_rdata <= reg_max_drawdown_low;
                    ADDR_MAX_DRAWDOWN_HIGH: s_axi_rdata <= reg_max_drawdown_high;
                    ADDR_MTM_PNL_LOW:       s_axi_rdata <= status_mtm_pnl[31:0];
                    ADDR_MTM_PNL_HIGH:      s_axi_rdata <= status_mtm_pnl[63:32];
                    ADDR_DRAWDOWN_LOW:      s_axi_rdata <= status_drawdown[31:0];
                    ADDR_DRAWDOWN_HIGH:     s_axi_rdata <= status_drawdown[63:32];
                    ADDR_FCS_ERROR_COUNT:   s_axi_rdata <= status_fcs_error_count;
                    ADDR_MIN_LATENCY_NS:    s_axi_rdata <= status_min_latency;
                    ADDR_MAX_LATENCY_NS:    s_axi_rdata <= status_max_latency;
                    ADDR_PTP_TIME_SEC_LOW:  s_axi_rdata <= status_ptp_sec[31:0];
                    ADDR_PTP_TIME_SEC_HIGH: s_axi_rdata <= {16'h0, status_ptp_sec[47:32]};
                    ADDR_PTP_TIME_NS:       s_axi_rdata <= status_ptp_ns;
                    default:                s_axi_rdata <= 32'hDEADBEEF;
                endcase
            end else begin
                s_axi_arready <= 1'b0;
            end

            // Read data handshake
            if (s_axi_rvalid && s_axi_rready) begin
                s_axi_rvalid <= 1'b0;
            end
        end
    end

endmodule
