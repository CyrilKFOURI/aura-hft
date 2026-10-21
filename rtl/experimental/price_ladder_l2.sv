`ifndef PRICE_LADDER_L2_SV
`define PRICE_LADDER_L2_SV

`timescale 1ns / 1ps

/* verilator lint_off IMPORTSTAR */
import lob_pkg::*;
/* verilator lint_on IMPORTSTAR */

module price_ladder_l2 #(
    parameter int DEPTH = 16
)(
    input  logic             clk,
    input  logic             rst_n,

    // Command Interface (from Order Hash Table)
    input  logic             cmd_valid,
    input  lob_cmd_e         cmd_op,
    input  logic             cmd_side,       // 0: Buy, 1: Sell
    input  logic [31:0]      cmd_price,
    input  logic [31:0]      cmd_shares,
    input  logic [31:0]      cmd_old_price,  // For REPLACE
    input  logic [31:0]      cmd_old_shares, // For REPLACE

    // L2 Book Output
    output price_level_t     bid_levels [0:DEPTH-1],
    output price_level_t     ask_levels [0:DEPTH-1],
    output logic [4:0]       bid_count,
    output logic [4:0]       ask_count,
    output logic             book_updated,
    output logic             busy
);

    typedef enum logic [1:0] {
        ST_IDLE,
        ST_REPLACE_ADD
    } ladder_state_e;

    ladder_state_e state;

    // Latched state for REPLACE 2-phase operation
    logic        saved_side;
    logic [31:0] saved_new_price;
    logic [31:0] saved_new_shares;

    assign busy = (state != ST_IDLE);

    // Helper functions for search
    function automatic int find_bid_level(input logic [31:0] price);
        for (int i = 0; i < DEPTH; i++) begin
            if (bid_levels[i].valid && bid_levels[i].price == price) return i;
        end
        return -1;
    endfunction

    function automatic int find_ask_level(input logic [31:0] price);
        for (int i = 0; i < DEPTH; i++) begin
            if (ask_levels[i].valid && ask_levels[i].price == price) return i;
        end
        return -1;
    endfunction

    function automatic int find_bid_insert_pos(input logic [31:0] price);
        for (int i = 0; i < DEPTH; i++) begin
            if (!bid_levels[i].valid || bid_levels[i].price < price) return i;
        end
        return DEPTH;
    endfunction

    function automatic int find_ask_insert_pos(input logic [31:0] price);
        for (int i = 0; i < DEPTH; i++) begin
            if (!ask_levels[i].valid || ask_levels[i].price > price) return i;
        end
        return DEPTH;
    endfunction

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state        <= ST_IDLE;
            bid_count    <= '0;
            ask_count    <= '0;
            book_updated <= 1'b0;
            saved_side   <= 1'b0;
            saved_new_price  <= '0;
            saved_new_shares <= '0;

            for (int i = 0; i < DEPTH; i++) begin
                bid_levels[i] <= '0;
                ask_levels[i] <= '0;
            end
        end else begin
            book_updated <= 1'b0;

            case (state)
                ST_IDLE: begin
                    if (cmd_valid) begin
                        case (cmd_op)
                            // ---------------------------------------------------------
                            // ADD VOLUME
                            // ---------------------------------------------------------
                            LOB_CMD_ADD: begin
                                book_updated <= 1'b1;
                                if (!cmd_side) begin // Buy side
                                    automatic int match_idx = find_bid_level(cmd_price);
                                    if (match_idx != -1) begin
                                        bid_levels[match_idx].shares <= bid_levels[match_idx].shares + cmd_shares;
                                    end else begin
                                        automatic int ins_pos = find_bid_insert_pos(cmd_price);
                                        if (ins_pos < DEPTH) begin
                                            for (int k = DEPTH - 1; k > 0; k--) begin
                                                if (k > ins_pos) begin
                                                    bid_levels[k] <= bid_levels[k-1];
                                                end
                                            end
                                            bid_levels[ins_pos].valid  <= 1'b1;
                                            bid_levels[ins_pos].price  <= cmd_price;
                                            bid_levels[ins_pos].shares <= cmd_shares;
                                            if (bid_count < 5'(DEPTH)) bid_count <= bid_count + 1'b1;
                                        end
                                    end
                                end else begin // Sell side
                                    automatic int match_idx = find_ask_level(cmd_price);
                                    if (match_idx != -1) begin
                                        ask_levels[match_idx].shares <= ask_levels[match_idx].shares + cmd_shares;
                                    end else begin
                                        automatic int ins_pos = find_ask_insert_pos(cmd_price);
                                        if (ins_pos < DEPTH) begin
                                            for (int k = DEPTH - 1; k > 0; k--) begin
                                                if (k > ins_pos) begin
                                                    ask_levels[k] <= ask_levels[k-1];
                                                end
                                            end
                                            ask_levels[ins_pos].valid  <= 1'b1;
                                            ask_levels[ins_pos].price  <= cmd_price;
                                            ask_levels[ins_pos].shares <= cmd_shares;
                                            if (ask_count < 5'(DEPTH)) ask_count <= ask_count + 1'b1;
                                        end
                                    end
                                end
                            end

                            // ---------------------------------------------------------
                            // SUBTRACT VOLUME (Execute / Cancel / Delete)
                            // ---------------------------------------------------------
                            LOB_CMD_SUB: begin
                                book_updated <= 1'b1;
                                if (!cmd_side) begin // Buy side
                                    automatic int match_idx = find_bid_level(cmd_price);
                                    if (match_idx != -1) begin
                                        if (bid_levels[match_idx].shares > cmd_shares) begin
                                            bid_levels[match_idx].shares <= bid_levels[match_idx].shares - cmd_shares;
                                        end else begin
                                            // Level depleted: shift up
                                            for (int k = 0; k < DEPTH - 1; k++) begin
                                                if (k >= match_idx) begin
                                                    bid_levels[k] <= bid_levels[k+1];
                                                end
                                            end
                                            bid_levels[DEPTH-1] <= '0;
                                            if (bid_count > 0) bid_count <= bid_count - 1'b1;
                                        end
                                    end
                                end else begin // Sell side
                                    automatic int match_idx = find_ask_level(cmd_price);
                                    if (match_idx != -1) begin
                                        if (ask_levels[match_idx].shares > cmd_shares) begin
                                            ask_levels[match_idx].shares <= ask_levels[match_idx].shares - cmd_shares;
                                        end else begin
                                            // Level depleted: shift up
                                            for (int k = 0; k < DEPTH - 1; k++) begin
                                                if (k >= match_idx) begin
                                                    ask_levels[k] <= ask_levels[k+1];
                                                end
                                            end
                                            ask_levels[DEPTH-1] <= '0;
                                            if (ask_count > 0) ask_count <= ask_count - 1'b1;
                                        end
                                    end
                                end
                            end

                            // ---------------------------------------------------------
                            // REPLACE (Phase 1: Sub old, latch new)
                            // ---------------------------------------------------------
                            LOB_CMD_REPLACE: begin
                                saved_side       <= cmd_side;
                                saved_new_price  <= cmd_price;
                                saved_new_shares <= cmd_shares;
                                state            <= ST_REPLACE_ADD;

                                // Perform Sub on old order
                                if (!cmd_side) begin
                                    automatic int match_idx = find_bid_level(cmd_old_price);
                                    if (match_idx != -1) begin
                                        if (bid_levels[match_idx].shares > cmd_old_shares) begin
                                            bid_levels[match_idx].shares <= bid_levels[match_idx].shares - cmd_old_shares;
                                        end else begin
                                            for (int k = 0; k < DEPTH - 1; k++) begin
                                                if (k >= match_idx) bid_levels[k] <= bid_levels[k+1];
                                            end
                                            bid_levels[DEPTH-1] <= '0;
                                            if (bid_count > 0) bid_count <= bid_count - 1'b1;
                                        end
                                    end
                                end else begin
                                    automatic int match_idx = find_ask_level(cmd_old_price);
                                    if (match_idx != -1) begin
                                        if (ask_levels[match_idx].shares > cmd_old_shares) begin
                                            ask_levels[match_idx].shares <= ask_levels[match_idx].shares - cmd_old_shares;
                                        end else begin
                                            for (int k = 0; k < DEPTH - 1; k++) begin
                                                if (k >= match_idx) ask_levels[k] <= ask_levels[k+1];
                                            end
                                            ask_levels[DEPTH-1] <= '0;
                                            if (ask_count > 0) ask_count <= ask_count - 1'b1;
                                        end
                                    end
                                end
                            end

                            // ---------------------------------------------------------
                            // CLEAR
                            // ---------------------------------------------------------
                            LOB_CMD_CLEAR: begin
                                bid_count    <= '0;
                                ask_count    <= '0;
                                book_updated <= 1'b1;
                                for (int i = 0; i < DEPTH; i++) begin
                                    bid_levels[i] <= '0;
                                    ask_levels[i] <= '0;
                                end
                            end

                            default: ;
                        endcase
                    end
                end

                // -------------------------------------------------------------
                // REPLACE Phase 2: Add new order
                // -------------------------------------------------------------
                ST_REPLACE_ADD: begin
                    state        <= ST_IDLE;
                    book_updated <= 1'b1;

                    if (!saved_side) begin // Buy side
                        automatic int match_idx = find_bid_level(saved_new_price);
                        if (match_idx != -1) begin
                            bid_levels[match_idx].shares <= bid_levels[match_idx].shares + saved_new_shares;
                        end else begin
                            automatic int ins_pos = find_bid_insert_pos(saved_new_price);
                            if (ins_pos < DEPTH) begin
                                for (int k = DEPTH - 1; k > 0; k--) begin
                                    if (k > ins_pos) bid_levels[k] <= bid_levels[k-1];
                                end
                                bid_levels[ins_pos].valid  <= 1'b1;
                                bid_levels[ins_pos].price  <= saved_new_price;
                                bid_levels[ins_pos].shares <= saved_new_shares;
                                if (bid_count < 5'(DEPTH)) bid_count <= bid_count + 1'b1;
                            end
                        end
                    end else begin // Sell side
                        automatic int match_idx = find_ask_level(saved_new_price);
                        if (match_idx != -1) begin
                            ask_levels[match_idx].shares <= ask_levels[match_idx].shares + saved_new_shares;
                        end else begin
                            automatic int ins_pos = find_ask_insert_pos(saved_new_price);
                            if (ins_pos < DEPTH) begin
                                for (int k = DEPTH - 1; k > 0; k--) begin
                                    if (k > ins_pos) ask_levels[k] <= ask_levels[k-1];
                                end
                                ask_levels[ins_pos].valid  <= 1'b1;
                                ask_levels[ins_pos].price  <= saved_new_price;
                                ask_levels[ins_pos].shares <= saved_new_shares;
                                if (ask_count < 5'(DEPTH)) ask_count <= ask_count + 1'b1;
                            end
                        end
                    end
                end

                default: state <= ST_IDLE;
            endcase
        end
    end

endmodule : price_ladder_l2

`endif // PRICE_LADDER_L2_SV
