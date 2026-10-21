// ============================================================================
// Module Name:   egress_arbiter
// Description:   4-Channel Round-Robin Fair Arbiter for Egress Order Routing.
//                Prevents starvation and serializes concurrent quoting signals
//                into a single OUCH / Pre-Trade Risk execution pipeline.
// Standard:      SystemVerilog IEEE 1800-2017
// Target:        AMD Kria KR260 @ 156.25 MHz (6.4 ns)
// ============================================================================

`timescale 1ns / 1ps

module egress_arbiter (
    input  logic                   clk,
    input  logic                   rst_n,

    // 4 Channel Order Requests
    input  logic [3:0]             req_valid,
    input  logic [3:0]             req_side,     // 0 = Buy, 1 = Sell
    input  logic [31:0]            req_price  [0:3],
    input  logic [31:0]            req_shares [0:3],
    input  logic [31:0]            req_token  [0:3],
    input  logic [15:0]            req_locate [0:3],

    // Channel Grant Acknowledgements
    output logic [3:0]             grant_ack,

    // Unified Arbitrated Output Stream (1 cycle registered)
    output logic                   out_valid,
    output logic [1:0]             out_channel,
    output logic                   out_side,
    output logic [31:0]            out_price,
    output logic [31:0]            out_shares,
    output logic [31:0]            out_token,
    output logic [15:0]            out_locate,

    // Arbiter Telemetry
    output logic [31:0]            total_arbitrated_orders,
    output logic [31:0]            collision_count
);

    logic [1:0] last_grant;
    logic [1:0] chosen_channel;
    logic       request_found;
    logic [2:0] active_req_count;

    // Count concurrent requests to detect collisions
    always_comb begin
        active_req_count = 3'd0;
        for (int i = 0; i < 4; i++) begin
            if (req_valid[i]) active_req_count = active_req_count + 3'd1;
        end
    end

    // Round-Robin Selection Logic
    always_comb begin
        chosen_channel = 2'd0;
        request_found  = 1'b0;

        case (last_grant)
            2'd0: begin
                if      (req_valid[1]) begin chosen_channel = 2'd1; request_found = 1'b1; end
                else if (req_valid[2]) begin chosen_channel = 2'd2; request_found = 1'b1; end
                else if (req_valid[3]) begin chosen_channel = 2'd3; request_found = 1'b1; end
                else if (req_valid[0]) begin chosen_channel = 2'd0; request_found = 1'b1; end
            end
            2'd1: begin
                if      (req_valid[2]) begin chosen_channel = 2'd2; request_found = 1'b1; end
                else if (req_valid[3]) begin chosen_channel = 2'd3; request_found = 1'b1; end
                else if (req_valid[0]) begin chosen_channel = 2'd0; request_found = 1'b1; end
                else if (req_valid[1]) begin chosen_channel = 2'd1; request_found = 1'b1; end
            end
            2'd2: begin
                if      (req_valid[3]) begin chosen_channel = 2'd3; request_found = 1'b1; end
                else if (req_valid[0]) begin chosen_channel = 2'd0; request_found = 1'b1; end
                else if (req_valid[1]) begin chosen_channel = 2'd1; request_found = 1'b1; end
                else if (req_valid[2]) begin chosen_channel = 2'd2; request_found = 1'b1; end
            end
            2'd3: begin
                if      (req_valid[0]) begin chosen_channel = 2'd0; request_found = 1'b1; end
                else if (req_valid[1]) begin chosen_channel = 2'd1; request_found = 1'b1; end
                else if (req_valid[2]) begin chosen_channel = 2'd2; request_found = 1'b1; end
                else if (req_valid[3]) begin chosen_channel = 2'd3; request_found = 1'b1; end
            end
        endcase
    end

    // Sequential Pipeline Register
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            last_grant              <= 2'd0;
            grant_ack               <= 4'b0000;
            out_valid               <= 1'b0;
            out_channel             <= 2'd0;
            out_side                <= 1'b0;
            out_price               <= 32'd0;
            out_shares              <= 32'd0;
            out_token               <= 32'd0;
            out_locate              <= 16'd0;
            total_arbitrated_orders <= 32'd0;
            collision_count         <= 32'd0;
        end else begin
            grant_ack <= 4'b0000;
            out_valid <= 1'b0;

            if (request_found) begin
                last_grant                 <= chosen_channel;
                grant_ack[chosen_channel]  <= 1'b1;
                out_valid                  <= 1'b1;
                out_channel                <= chosen_channel;
                out_side                   <= req_side[chosen_channel];
                out_price                  <= req_price[chosen_channel];
                out_shares                 <= req_shares[chosen_channel];
                out_token                  <= req_token[chosen_channel];
                out_locate                 <= req_locate[chosen_channel];
                total_arbitrated_orders    <= total_arbitrated_orders + 32'd1;

                if (active_req_count > 3'd1) begin
                    collision_count <= collision_count + 32'd1;
                end
            end
        end
    end

endmodule
