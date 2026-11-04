`ifndef ORDER_HASH_TABLE_SV
`define ORDER_HASH_TABLE_SV

`timescale 1ns / 1ps

/* verilator lint_off IMPORTSTAR */
import lob_pkg::*;
/* verilator lint_on IMPORTSTAR */

module order_hash_table #(
    parameter int NUM_SETS = 512,
    parameter int NUM_WAYS = 4
)(
    input  logic             clk,
    input  logic             rst_n,

    // Command Interface (From ITCH Parser)
    input  logic             req_valid,
    input  logic [2:0]       req_op,         // 0: NOP, 1: Add ('A'/'F'), 2: Exec ('E'/'C'), 3: Cancel ('X'), 4: Delete ('D'), 5: Replace ('U')
    input  logic [63:0]      req_order_ref,
    input  logic [63:0]      req_orig_ref,   // For 'U'
    input  logic             req_side,       // 0: Buy, 1: Sell
    input  logic [31:0]      req_shares,
    input  logic [31:0]      req_price,

    // Response to Price Ladder
    output logic             out_valid,
    output lob_cmd_e         out_cmd,        // LOB_CMD_ADD, LOB_CMD_SUB, LOB_CMD_REPLACE
    output logic             out_side,
    output logic [31:0]      out_price,
    output logic [31:0]      out_shares,

    // For Replace ('U'): Old order to remove, New order to add
    output logic [31:0]      out_old_price,
    output logic [31:0]      out_old_shares,

    // Telemetry & Status
    output logic             table_hit,
    output logic             table_miss,
    output logic             table_full,
    output logic [31:0]      active_order_count
);

    localparam int ADDR_WIDTH = $clog2(NUM_SETS);

    // Storage: 2D array [Set][Way]
    order_entry_t order_table [0:NUM_SETS-1][0:NUM_WAYS-1];

    // Hardware Hash Function (Multiplicative hash with Golden Ratio constant)
    function automatic logic [ADDR_WIDTH-1:0] hash_key(input logic [63:0] key);
        logic [63:0] h;
        h = key ^ (key >> 17) ^ (key >> 33);
        h = h * 64'h9e3779b97f4a7c15; // Golden ratio 64-bit constant
        return h[ADDR_WIDTH-1:0];
    endfunction

    // Internal wires for matching logic
    logic [ADDR_WIDTH-1:0] set_idx;
    logic [ADDR_WIDTH-1:0] set_idx_orig;

    assign set_idx      = hash_key(req_order_ref);
    assign set_idx_orig = hash_key(req_orig_ref);

    // Sequential process
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            out_valid          <= 1'b0;
            out_cmd            <= LOB_CMD_NOP;
            out_side           <= 1'b0;
            out_price          <= '0;
            out_shares         <= '0;
            out_old_price      <= '0;
            out_old_shares     <= '0;
            table_hit          <= 1'b0;
            table_miss         <= 1'b0;
            table_full         <= 1'b0;
            active_order_count <= '0;

            for (int s = 0; s < NUM_SETS; s++) begin
                for (int w = 0; w < NUM_WAYS; w++) begin
                    order_table[s][w] <= '0;
                end
            end
        end else begin
            // Default strobes
            out_valid  <= 1'b0;
            out_cmd    <= LOB_CMD_NOP;
            table_hit  <= 1'b0;
            table_miss <= 1'b0;
            table_full <= 1'b0;

            if (req_valid) begin
                case (req_op)
                    // -------------------------------------------------------------
                    // 1: Add Order ('A' or 'F')
                    // -------------------------------------------------------------
                    3'd1: begin
                        automatic int empty_way = -1;
                        automatic int match_way = -1;

                        for (int w = 0; w < NUM_WAYS; w++) begin
                            if (order_table[set_idx][w].valid && order_table[set_idx][w].order_ref == req_order_ref) begin
                                match_way = w;
                            end else if (!order_table[set_idx][w].valid && empty_way == -1) begin
                                empty_way = w;
                            end
                        end

                        if (match_way != -1) begin
                            // Update existing entry
                            order_table[set_idx][match_way].price  <= req_price;
                            order_table[set_idx][match_way].shares <= req_shares;
                            order_table[set_idx][match_way].side   <= req_side;
                        end else if (empty_way != -1) begin
                            // Insert in empty slot
                            order_table[set_idx][empty_way].valid     <= 1'b1;
                            order_table[set_idx][empty_way].order_ref <= req_order_ref;
                            order_table[set_idx][empty_way].price     <= req_price;
                            order_table[set_idx][empty_way].shares    <= req_shares;
                            order_table[set_idx][empty_way].side      <= req_side;
                            active_order_count                  <= active_order_count + 1'b1;
                        end else begin
                            table_full <= 1'b1;
                        end

                        // Forward addition to Price Ladder
                        out_valid  <= 1'b1;
                        out_cmd    <= LOB_CMD_ADD;
                        out_side   <= req_side;
                        out_price  <= req_price;
                        out_shares <= req_shares;
                        table_hit  <= 1'b1;
                    end

                    // -------------------------------------------------------------
                    // 2: Order Executed ('E' or 'C')
                    // -------------------------------------------------------------
                    3'd2: begin
                        automatic int match_way = -1;

                        for (int w = 0; w < NUM_WAYS; w++) begin
                            if (order_table[set_idx][w].valid && order_table[set_idx][w].order_ref == req_order_ref) begin
                                match_way = w;
                            end
                        end

                        if (match_way != -1) begin
                            automatic logic [31:0] cur_sh = order_table[set_idx][match_way].shares;
                            table_hit  <= 1'b1;
                            out_valid  <= 1'b1;
                            out_cmd    <= LOB_CMD_SUB;
                            out_side   <= order_table[set_idx][match_way].side;
                            out_price  <= order_table[set_idx][match_way].price;

                            if (cur_sh <= req_shares) begin
                                // Order fully executed
                                order_table[set_idx][match_way].valid <= 1'b0;
                                out_shares                      <= cur_sh;
                                active_order_count              <= active_order_count - 1'b1;
                            end else begin
                                // Partial execution
                                order_table[set_idx][match_way].shares <= cur_sh - req_shares;
                                out_shares                       <= req_shares;
                            end
                        end else begin
                            table_miss <= 1'b1;
                        end
                    end

                    // -------------------------------------------------------------
                    // 3: Order Cancel ('X')
                    // -------------------------------------------------------------
                    3'd3: begin
                        automatic int match_way = -1;

                        for (int w = 0; w < NUM_WAYS; w++) begin
                            if (order_table[set_idx][w].valid && order_table[set_idx][w].order_ref == req_order_ref) begin
                                match_way = w;
                            end
                        end

                        if (match_way != -1) begin
                            automatic logic [31:0] cur_sh = order_table[set_idx][match_way].shares;
                            table_hit  <= 1'b1;
                            out_valid  <= 1'b1;
                            out_cmd    <= LOB_CMD_SUB;
                            out_side   <= order_table[set_idx][match_way].side;
                            out_price  <= order_table[set_idx][match_way].price;

                            if (cur_sh <= req_shares) begin
                                order_table[set_idx][match_way].valid <= 1'b0;
                                out_shares                      <= cur_sh;
                                active_order_count              <= active_order_count - 1'b1;
                            end else begin
                                order_table[set_idx][match_way].shares <= cur_sh - req_shares;
                                out_shares                       <= req_shares;
                            end
                        end else begin
                            table_miss <= 1'b1;
                        end
                    end

                    // -------------------------------------------------------------
                    // 4: Order Delete ('D')
                    // -------------------------------------------------------------
                    3'd4: begin
                        automatic int match_way = -1;

                        for (int w = 0; w < NUM_WAYS; w++) begin
                            if (order_table[set_idx][w].valid && order_table[set_idx][w].order_ref == req_order_ref) begin
                                match_way = w;
                            end
                        end

                        if (match_way != -1) begin
                            table_hit                       <= 1'b1;
                            out_valid                       <= 1'b1;
                            out_cmd                         <= LOB_CMD_SUB;
                            out_side                        <= order_table[set_idx][match_way].side;
                            out_price                       <= order_table[set_idx][match_way].price;
                            out_shares                      <= order_table[set_idx][match_way].shares;
                            order_table[set_idx][match_way].valid <= 1'b0;
                            active_order_count              <= active_order_count - 1'b1;
                        end else begin
                            table_miss <= 1'b1;
                        end
                    end

                    // -------------------------------------------------------------
                    // 5: Order Replace ('U')
                    // -------------------------------------------------------------
                    3'd5: begin
                        automatic int match_orig = -1;
                        automatic int empty_new  = -1;
                        automatic logic [31:0] old_p = '0;
                        automatic logic [31:0] old_s = '0;
                        automatic logic        ord_side = 1'b0;

                        // Find and remove original order
                        for (int w = 0; w < NUM_WAYS; w++) begin
                            if (order_table[set_idx_orig][w].valid && order_table[set_idx_orig][w].order_ref == req_orig_ref) begin
                                match_orig = w;
                            end
                        end

                        if (match_orig != -1) begin
                            old_p                           = order_table[set_idx_orig][match_orig].price;
                            old_s                           = order_table[set_idx_orig][match_orig].shares;
                            ord_side                        = order_table[set_idx_orig][match_orig].side;
                            order_table[set_idx_orig][match_orig].valid <= 1'b0;

                            // Insert new order
                            for (int w = 0; w < NUM_WAYS; w++) begin
                                if (!order_table[set_idx][w].valid && empty_new == -1) begin
                                    empty_new = w;
                                end
                            end

                            if (empty_new != -1) begin
                                order_table[set_idx][empty_new].valid     <= 1'b1;
                                order_table[set_idx][empty_new].order_ref <= req_order_ref;
                                order_table[set_idx][empty_new].price     <= req_price;
                                order_table[set_idx][empty_new].shares    <= req_shares;
                                order_table[set_idx][empty_new].side      <= ord_side;
                            end

                            out_valid      <= 1'b1;
                            out_cmd        <= LOB_CMD_REPLACE;
                            out_side       <= ord_side;
                            out_old_price  <= old_p;
                            out_old_shares <= old_s;
                            out_price      <= req_price;
                            out_shares     <= req_shares;
                            table_hit      <= 1'b1;
                        end else begin
                            table_miss <= 1'b1;
                        end
                    end

                    default: ;
                endcase
            end
        end
    end

endmodule : order_hash_table

`endif // ORDER_HASH_TABLE_SV
