`timescale 1ns/1ps

// Race-safe HW-12 HMAC controller. Uses the raw compression primitive from
// cosmic_hw_12_hmac.v and explicitly tracks one in-flight compression phase.
module cosmic_hmac_sha256_shortmsg_safe (
    input  wire         clk,
    input  wire         reset,
    input  wire         message_valid,
    output wire         message_ready,
    input  wire [511:0] key_block,
    input  wire [439:0] message_data,
    input  wire [5:0]   message_len,
    output reg          tag_valid,
    input  wire         tag_ready,
    output reg  [255:0] tag_data,
    output reg          busy,
    output reg  [2:0]   compression_count,
    output wire         compression_busy,
    output wire [6:0]   compression_round_count,
    output wire         compression_accept_pulse
);
    localparam [255:0] SHA256_IV = 256'h6a09e667bb67ae853c6ef372a54ff53a510e527f9b05688c1f83d9ab5be0cd19;
    localparam [2:0] ST_IDLE       = 3'd0;
    localparam [2:0] ST_INNER_PAD  = 3'd1;
    localparam [2:0] ST_INNER_MSG  = 3'd2;
    localparam [2:0] ST_OUTER_PAD  = 3'd3;
    localparam [2:0] ST_OUTER_DIG  = 3'd4;

    reg [2:0] state;
    reg phase_inflight;
    reg [511:0] key_reg;
    reg [439:0] message_reg;
    reg [5:0] message_len_reg;
    reg [255:0] inner_state;
    reg [255:0] inner_digest;
    reg [255:0] outer_state;

    reg compress_valid;
    wire compress_ready;
    reg [255:0] compress_state_in;
    reg [511:0] compress_block;
    wire compress_state_valid;
    wire [255:0] compress_state_out;

    wire tag_fire = tag_valid && tag_ready;
    assign message_ready = (state == ST_IDLE) && !busy && (!tag_valid || tag_ready);
    assign compression_accept_pulse = compress_valid && compress_ready;

    function [511:0] xor_pad;
        input [511:0] key;
        input [7:0] pad;
        integer xp_i;
        begin
            xor_pad = 512'b0;
            for (xp_i=0; xp_i<64; xp_i=xp_i+1)
                xor_pad[511-(xp_i*8) -: 8] = key[511-(xp_i*8) -: 8] ^ pad;
        end
    endfunction

    reg [511:0] inner_message_block;
    reg [511:0] outer_digest_block;
    reg [63:0] inner_total_bits;
    integer msg_i;
    always @* begin
        inner_message_block = 512'b0;
        for (msg_i=0; msg_i<55; msg_i=msg_i+1)
            if (msg_i < message_len_reg)
                inner_message_block[511-(msg_i*8) -: 8] = message_reg[439-(msg_i*8) -: 8];
        if (message_len_reg <= 6'd55)
            inner_message_block[511-(message_len_reg*8) -: 8] = 8'h80;
        inner_total_bits = (64 + message_len_reg) * 8;
        inner_message_block[63:0] = inner_total_bits;

        // 64-byte opad-key block was already compressed. The second outer
        // block is inner_digest(32) || 0x80 || 23*0x00 || bit_length(96*8).
        outer_digest_block = 512'b0;
        outer_digest_block[511:256] = inner_digest;
        outer_digest_block[255:248] = 8'h80;
        outer_digest_block[63:0] = 64'd768;
    end

    always @* begin
        compress_valid = 1'b0;
        compress_state_in = SHA256_IV;
        compress_block = 512'b0;
        if (!phase_inflight) begin
            case (state)
                ST_INNER_PAD: begin
                    compress_valid = 1'b1;
                    compress_state_in = SHA256_IV;
                    compress_block = xor_pad(key_reg, 8'h36);
                end
                ST_INNER_MSG: begin
                    compress_valid = 1'b1;
                    compress_state_in = inner_state;
                    compress_block = inner_message_block;
                end
                ST_OUTER_PAD: begin
                    compress_valid = 1'b1;
                    compress_state_in = SHA256_IV;
                    compress_block = xor_pad(key_reg, 8'h5c);
                end
                ST_OUTER_DIG: begin
                    compress_valid = 1'b1;
                    compress_state_in = outer_state;
                    compress_block = outer_digest_block;
                end
                default: begin end
            endcase
        end
    end

    cosmic_sha256_compress_iterative compress (
        .clk(clk), .reset(reset),
        .block_valid(compress_valid), .block_ready(compress_ready),
        .state_in(compress_state_in), .block_data(compress_block),
        .state_valid(compress_state_valid), .state_ready(1'b1),
        .state_out(compress_state_out),
        .busy(compression_busy), .round_count(compression_round_count)
    );

    always @(posedge clk) begin
        if (reset) begin
            state<=ST_IDLE;
            phase_inflight<=1'b0;
            key_reg<=0;
            message_reg<=0;
            message_len_reg<=0;
            inner_state<=0;
            inner_digest<=0;
            outer_state<=0;
            tag_valid<=0;
            tag_data<=0;
            busy<=0;
            compression_count<=0;
        end else begin
            if (tag_fire)
                tag_valid <= 1'b0;

            if (message_valid && message_ready) begin
                if (message_len <= 6'd55) begin
                    key_reg <= key_block;
                    message_reg <= message_data;
                    message_len_reg <= message_len;
                    compression_count <= 0;
                    phase_inflight <= 1'b0;
                    busy <= 1'b1;
                    state <= ST_INNER_PAD;
                end
            end

            if (compression_accept_pulse) begin
                phase_inflight <= 1'b1;
                compression_count <= compression_count + 3'd1;
            end

            if (compress_state_valid && phase_inflight) begin
                phase_inflight <= 1'b0;
                case (state)
                    ST_INNER_PAD: begin
                        inner_state <= compress_state_out;
                        state <= ST_INNER_MSG;
                    end
                    ST_INNER_MSG: begin
                        inner_digest <= compress_state_out;
                        state <= ST_OUTER_PAD;
                    end
                    ST_OUTER_PAD: begin
                        outer_state <= compress_state_out;
                        state <= ST_OUTER_DIG;
                    end
                    ST_OUTER_DIG: begin
                        tag_data <= compress_state_out;
                        tag_valid <= 1'b1;
                        busy <= 1'b0;
                        state <= ST_IDLE;
                    end
                    default: begin end
                endcase
            end
        end
    end
endmodule
