`ifndef ICEBERG_TWAP_ENGINE_SV
`define ICEBERG_TWAP_ENGINE_SV

`timescale 1ns / 1ps

/**
 * iceberg_twap_engine.sv
 *
 * Hardware Execution Slicing Engine (AURA-HFT v4.0).
 * Supports:
 *   1) Native Hardware Iceberg Orders:
 *      - Exposes only visible 'display_qty' to the exchange.
 *      - Automatically replenishes next slice in 1 cycle upon full fill.
 *      - Handles odd residuals on final slice.
 *      - Instant emergency cancellation.
 *   2) Hardware TWAP (Time-Weighted Average Price):
 *      - Uniform volume distribution across programmable cycle intervals.
 *      - 16-bit Galois LFSR pseudo-random jitter generator to foil predatory algorithms.
 *      - Autonomous termination when target parent volume is fulfilled.
 *   3) Priority Egress Arbitre to OUCH Order Generation.
 */

module iceberg_twap_engine (
    input  logic        clk,
    input  logic        rst_n,

    // =========================================================================
    // 1. Iceberg Parent Order Configuration
    // =========================================================================
    input  logic        iceberg_arm,
    input  logic        iceberg_side,         // 1'b0: Buy ('B'), 1'b1: Sell ('S')
    input  logic [31:0] iceberg_total_qty,
    input  logic [31:0] iceberg_display_qty,
    input  logic [31:0] iceberg_price,
    input  logic [63:0] iceberg_stock,
    input  logic [31:0] iceberg_token_base,
    input  logic        iceberg_cancel,

    // =========================================================================
    // 2. Market Fill / Execution Feedback
    // =========================================================================
    input  logic        exec_valid,
    input  logic [31:0] exec_token,
    input  logic [31:0] exec_shares,

    // =========================================================================
    // 3. TWAP Parent Order Configuration
    // =========================================================================
    input  logic        twap_arm,
    input  logic        twap_side,
    input  logic [31:0] twap_total_qty,
    input  logic [31:0] twap_slice_qty,
    input  logic [31:0] twap_interval_cycles,
    input  logic        twap_jitter_enable,
    input  logic [31:0] twap_price,
    input  logic [63:0] twap_stock,
    input  logic [31:0] twap_token_base,
    input  logic        twap_cancel,

    // =========================================================================
    // 4. Outbound Child Order Egress (To OUCH Order Gen)
    // =========================================================================
    output logic        child_order_valid,
    output logic        child_order_side,
    output logic [31:0] child_order_shares,
    output logic [31:0] child_order_price,
    output logic [63:0] child_order_stock,
    output logic [31:0] child_order_token,
    output logic        child_is_cancel,

    // =========================================================================
    // 5. Telemetry & Status
    // =========================================================================
    output logic        iceberg_busy,
    output logic        iceberg_done,
    output logic [31:0] iceberg_rem_qty,
    output logic [31:0] iceberg_active_qty,
    output logic [15:0] iceberg_slice_count,

    output logic        twap_busy,
    output logic        twap_done,
    output logic [31:0] twap_rem_qty,
    output logic [15:0] twap_slice_count
);

    // =========================================================================
    // Pseudo-Random Number Generator: 16-bit Galois LFSR
    // Polynomial: x^16 + x^14 + x^13 + x^11 + 1 (Taps: 0xB400)
    // =========================================================================
    logic [15:0] lfsr_reg;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            lfsr_reg <= 16'hACE1;
        end else begin
            lfsr_reg <= {lfsr_reg[14:0], 1'b0} ^ (lfsr_reg[15] ? 16'hB400 : 16'h0000);
        end
    end

    // =========================================================================
    // Iceberg Execution Logic
    // =========================================================================
    typedef enum logic [2:0] {
        ICE_IDLE      = 3'd0,
        ICE_ARM_EMIT  = 3'd1,
        ICE_ACTIVE    = 3'd2,
        ICE_REPLENISH = 3'd3,
        ICE_CANCEL    = 3'd4,
        ICE_DONE      = 3'd5
    } ice_state_e;

    ice_state_e ice_state;

    logic        ice_reg_side;
    logic [31:0] ice_reg_price;
    logic [63:0] ice_reg_stock;
    logic [31:0] ice_reg_token_base;
    logic [31:0] ice_reg_display_qty;
    logic [31:0] ice_current_token;

    logic        ice_out_valid;
    logic        ice_out_side;
    logic [31:0] ice_out_shares;
    logic [31:0] ice_out_price;
    logic [63:0] ice_out_stock;
    logic [31:0] ice_out_token;
    logic        ice_out_cancel;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ice_state          <= ICE_IDLE;
            iceberg_busy       <= 1'b0;
            iceberg_done       <= 1'b0;
            iceberg_rem_qty    <= 32'd0;
            iceberg_active_qty <= 32'd0;
            iceberg_slice_count<= 16'd0;
            ice_reg_side       <= 1'b0;
            ice_reg_price      <= 32'd0;
            ice_reg_stock      <= 64'd0;
            ice_reg_token_base <= 32'd0;
            ice_reg_display_qty<= 32'd0;
            ice_current_token  <= 32'd0;
            ice_out_valid      <= 1'b0;
            ice_out_side       <= 1'b0;
            ice_out_shares     <= 32'd0;
            ice_out_price      <= 32'd0;
            ice_out_stock      <= 64'd0;
            ice_out_token      <= 32'd0;
            ice_out_cancel     <= 1'b0;
        end else begin
            // Default 1-cycle strobe deassertions
            ice_out_valid  <= 1'b0;
            ice_out_cancel <= 1'b0;

            case (ice_state)
                ICE_IDLE: begin
                    iceberg_done <= 1'b0;
                    if (iceberg_arm && (iceberg_total_qty > 0) && (iceberg_display_qty > 0)) begin
                        logic [31:0] first_slice;
                        first_slice = (iceberg_total_qty >= iceberg_display_qty) ? 
                                      iceberg_display_qty : iceberg_total_qty;

                        ice_reg_side        <= iceberg_side;
                        ice_reg_price       <= iceberg_price;
                        ice_reg_stock       <= iceberg_stock;
                        ice_reg_token_base  <= iceberg_token_base;
                        ice_reg_display_qty <= iceberg_display_qty;
                        ice_current_token   <= iceberg_token_base;

                        iceberg_rem_qty     <= iceberg_total_qty - first_slice;
                        iceberg_active_qty  <= first_slice;
                        iceberg_slice_count <= 16'd1;
                        iceberg_busy        <= 1'b1;

                        // Emit first slice
                        ice_out_valid       <= 1'b1;
                        ice_out_side        <= iceberg_side;
                        ice_out_shares      <= first_slice;
                        ice_out_price       <= iceberg_price;
                        ice_out_stock       <= iceberg_stock;
                        ice_out_token       <= iceberg_token_base;
                        ice_out_cancel      <= 1'b0;

                        ice_state           <= ICE_ACTIVE;
                    end
                end

                ICE_ACTIVE: begin
                    if (iceberg_cancel) begin
                        // Emergency cancel active slice
                        ice_out_valid      <= 1'b1;
                        ice_out_side       <= ice_reg_side;
                        ice_out_shares     <= iceberg_active_qty;
                        ice_out_price      <= ice_reg_price;
                        ice_out_stock      <= ice_reg_stock;
                        ice_out_token      <= ice_current_token;
                        ice_out_cancel     <= 1'b1;

                        iceberg_busy       <= 1'b0;
                        iceberg_rem_qty    <= 32'd0;
                        iceberg_active_qty <= 32'd0;
                        ice_state          <= ICE_IDLE;
                    end else if (exec_valid && (exec_token == ice_current_token)) begin
                        logic [31:0] actual_fill;
                        actual_fill = (exec_shares >= iceberg_active_qty) ? iceberg_active_qty : exec_shares;

                        if (actual_fill >= iceberg_active_qty) begin
                            // Current slice fully filled! Check if remainder exists
                            if (iceberg_rem_qty > 0) begin
                                logic [31:0] next_slice;
                                next_slice = (iceberg_rem_qty >= ice_reg_display_qty) ? 
                                             ice_reg_display_qty : iceberg_rem_qty;

                                ice_current_token   <= ice_current_token + 32'd1;
                                iceberg_active_qty  <= next_slice;
                                iceberg_rem_qty     <= iceberg_rem_qty - next_slice;
                                iceberg_slice_count <= iceberg_slice_count + 16'd1;

                                // Instantly emit next slice in 1 cycle
                                ice_out_valid       <= 1'b1;
                                ice_out_side        <= ice_reg_side;
                                ice_out_shares      <= next_slice;
                                ice_out_price       <= ice_reg_price;
                                ice_out_stock       <= ice_reg_stock;
                                ice_out_token       <= ice_current_token + 32'd1;
                                ice_out_cancel      <= 1'b0;

                                ice_state           <= ICE_ACTIVE;
                            end else begin
                                // Everything filled!
                                iceberg_active_qty  <= 32'd0;
                                iceberg_busy        <= 1'b0;
                                iceberg_done        <= 1'b1;
                                ice_state           <= ICE_IDLE;
                            end
                        end else begin
                            // Partial fill
                            iceberg_active_qty <= iceberg_active_qty - actual_fill;
                        end
                    end
                end

                default: ice_state <= ICE_IDLE;
            endcase
        end
    end

    // =========================================================================
    // TWAP Execution Logic
    // =========================================================================
    typedef enum logic [1:0] {
        TWAP_IDLE   = 2'd0,
        TWAP_ACTIVE = 2'd1,
        TWAP_DONE_ST= 2'd2
    } twap_state_e;

    twap_state_e twap_state;

    logic        twap_reg_side;
    logic [31:0] twap_reg_price;
    logic [63:0] twap_reg_stock;
    logic [31:0] twap_reg_token_base;
    logic [31:0] twap_reg_slice_qty;
    logic [31:0] twap_reg_interval;
    logic        twap_reg_jitter_en;
    logic [31:0] twap_current_token;
    logic [31:0] twap_timer;

    logic        twap_out_valid;
    logic        twap_out_side;
    logic [31:0] twap_out_shares;
    logic [31:0] twap_out_price;
    logic [63:0] twap_out_stock;
    logic [31:0] twap_out_token;

    // Jitter computation: interval +/- (lfsr[5:0] - 32)
    function automatic logic [31:0] calc_next_interval(
        input logic [31:0] base_interval,
        input logic        jitter_en,
        input logic [15:0] lfsr
    );
        logic signed [31:0] jitter_offset;
        logic signed [31:0] computed;
        begin
            if (!jitter_en || base_interval < 64) begin
                calc_next_interval = base_interval;
            end else begin
                // Jitter offset between -32 and +31 cycles
                jitter_offset = $signed({26'd0, lfsr[5:0]}) - 32'sd32;
                computed = $signed(base_interval) + jitter_offset;
                if (computed < 16)
                    calc_next_interval = 32'd16;
                else
                    calc_next_interval = computed[31:0];
            end
        end
    endfunction

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            twap_state         <= TWAP_IDLE;
            twap_busy          <= 1'b0;
            twap_done          <= 1'b0;
            twap_rem_qty       <= 32'd0;
            twap_slice_count   <= 16'd0;
            twap_reg_side      <= 1'b0;
            twap_reg_price     <= 32'd0;
            twap_reg_stock     <= 64'd0;
            twap_reg_token_base<= 32'd0;
            twap_reg_slice_qty <= 32'd0;
            twap_reg_interval  <= 32'd0;
            twap_reg_jitter_en <= 1'b0;
            twap_current_token <= 32'd0;
            twap_timer         <= 32'd0;
            twap_out_valid     <= 1'b0;
            twap_out_side      <= 1'b0;
            twap_out_shares    <= 32'd0;
            twap_out_price     <= 32'd0;
            twap_out_stock     <= 64'd0;
            twap_out_token     <= 32'd0;
        end else begin
            twap_out_valid <= 1'b0;

            case (twap_state)
                TWAP_IDLE: begin
                    twap_done <= 1'b0;
                    if (twap_arm && (twap_total_qty > 0) && (twap_slice_qty > 0)) begin
                        logic [31:0] first_slice;
                        first_slice = (twap_total_qty >= twap_slice_qty) ? 
                                      twap_slice_qty : twap_total_qty;

                        twap_reg_side       <= twap_side;
                        twap_reg_price      <= twap_price;
                        twap_reg_stock      <= twap_stock;
                        twap_reg_token_base <= twap_token_base;
                        twap_reg_slice_qty  <= twap_slice_qty;
                        twap_reg_interval   <= twap_interval_cycles;
                        twap_reg_jitter_en  <= twap_jitter_enable;
                        twap_current_token  <= twap_token_base;

                        twap_rem_qty        <= twap_total_qty - first_slice;
                        twap_slice_count    <= 16'd1;
                        twap_busy           <= 1'b1;

                        // Emit first slice immediately
                        twap_out_valid      <= 1'b1;
                        twap_out_side       <= twap_side;
                        twap_out_shares     <= first_slice;
                        twap_out_price      <= twap_price;
                        twap_out_stock      <= twap_stock;
                        twap_out_token      <= twap_token_base;

                        // Initialize timer for next slice
                        twap_timer          <= calc_next_interval(twap_interval_cycles, twap_jitter_enable, lfsr_reg);
                        twap_state          <= TWAP_ACTIVE;
                    end
                end

                TWAP_ACTIVE: begin
                    if (twap_cancel) begin
                        twap_busy    <= 1'b0;
                        twap_rem_qty <= 32'd0;
                        twap_state   <= TWAP_IDLE;
                    end else if (twap_rem_qty == 0) begin
                        // All slices sent
                        twap_busy  <= 1'b0;
                        twap_done  <= 1'b1;
                        twap_state <= TWAP_IDLE;
                    end else if (twap_timer > 1) begin
                        twap_timer <= twap_timer - 32'd1;
                    end else begin
                        // Timer expired! Emit next slice
                        logic [31:0] next_slice;
                        next_slice = (twap_rem_qty >= twap_reg_slice_qty) ? 
                                     twap_reg_slice_qty : twap_rem_qty;

                        twap_current_token <= twap_current_token + 32'd1;
                        twap_rem_qty       <= twap_rem_qty - next_slice;
                        twap_slice_count   <= twap_slice_count + 16'd1;

                        twap_out_valid     <= 1'b1;
                        twap_out_side      <= twap_reg_side;
                        twap_out_shares    <= next_slice;
                        twap_out_price     <= twap_reg_price;
                        twap_out_stock     <= twap_reg_stock;
                        twap_out_token     <= twap_current_token + 32'd1;

                        // Reload timer
                        twap_timer         <= calc_next_interval(twap_reg_interval, twap_reg_jitter_en, lfsr_reg);
                    end
                end

                default: twap_state <= TWAP_IDLE;
            endcase
        end
    end

    // =========================================================================
    // Egress Priority Arbiter
    // Priority: Iceberg (execution-driven real-time) > TWAP (periodic timer)
    // =========================================================================
    always_comb begin
        if (ice_out_valid) begin
            child_order_valid  = 1'b1;
            child_order_side   = ice_out_side;
            child_order_shares = ice_out_shares;
            child_order_price  = ice_out_price;
            child_order_stock  = ice_out_stock;
            child_order_token  = ice_out_token;
            child_is_cancel    = ice_out_cancel;
        end else if (twap_out_valid) begin
            child_order_valid  = 1'b1;
            child_order_side   = twap_out_side;
            child_order_shares = twap_out_shares;
            child_order_price  = twap_out_price;
            child_order_stock  = twap_out_stock;
            child_order_token  = twap_out_token;
            child_is_cancel    = 1'b0;
        end else begin
            child_order_valid  = 1'b0;
            child_order_side   = 1'b0;
            child_order_shares = 32'd0;
            child_order_price  = 32'd0;
            child_order_stock  = 64'd0;
            child_order_token  = 32'd0;
            child_is_cancel    = 1'b0;
        end
    end

endmodule

`endif // ICEBERG_TWAP_ENGINE_SV
