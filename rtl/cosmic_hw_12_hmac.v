`timescale 1ns/1ps

// COSMIC-HW-12/v0.1
// Standard SHA-256 compression with explicit chaining state plus a finite
// four-compression HMAC-SHA256 engine for normalized keys and short messages.
//
// Scientific boundary:
// - HMAC is an observational authenticity layer only;
// - this file does not alter A/M/C, receipt, leaf, Merkle, or proof semantics;
// - the public deterministic test key is measurement-only, not a production
//   secret and not evidence of secure key storage or side-channel resistance.

module cosmic_sha256_compress_iterative (
    input  wire         clk,
    input  wire         reset,
    input  wire         block_valid,
    output wire         block_ready,
    input  wire [255:0] state_in,
    input  wire [511:0] block_data,
    output reg          state_valid,
    input  wire         state_ready,
    output reg  [255:0] state_out,
    output reg          busy,
    output reg  [6:0]   round_count
);
    reg [31:0] base0,base1,base2,base3,base4,base5,base6,base7;
    reg [31:0] a,b,c,d,e,f,g,h;
    reg [31:0] w [0:63];
    reg [6:0] round_idx;
    integer reset_i;
    integer load_i;

    wire state_fire = state_valid && state_ready;
    assign block_ready = !busy && (!state_valid || state_ready);

    function [31:0] rotr;
        input [31:0] x;
        input integer n;
        begin rotr = (x >> n) | (x << (32-n)); end
    endfunction
    function [31:0] ch;
        input [31:0] x,y,z;
        begin ch = (x & y) ^ (~x & z); end
    endfunction
    function [31:0] maj;
        input [31:0] x,y,z;
        begin maj = (x & y) ^ (x & z) ^ (y & z); end
    endfunction
    function [31:0] bsig0;
        input [31:0] x;
        begin bsig0 = rotr(x,2) ^ rotr(x,13) ^ rotr(x,22); end
    endfunction
    function [31:0] bsig1;
        input [31:0] x;
        begin bsig1 = rotr(x,6) ^ rotr(x,11) ^ rotr(x,25); end
    endfunction
    function [31:0] ssig0;
        input [31:0] x;
        begin ssig0 = rotr(x,7) ^ rotr(x,18) ^ (x >> 3); end
    endfunction
    function [31:0] ssig1;
        input [31:0] x;
        begin ssig1 = rotr(x,17) ^ rotr(x,19) ^ (x >> 10); end
    endfunction
    function [31:0] kval;
        input [5:0] idx;
        begin
            case (idx)
              0: kval=32'h428a2f98; 1: kval=32'h71374491; 2: kval=32'hb5c0fbcf; 3: kval=32'he9b5dba5;
              4: kval=32'h3956c25b; 5: kval=32'h59f111f1; 6: kval=32'h923f82a4; 7: kval=32'hab1c5ed5;
              8: kval=32'hd807aa98; 9: kval=32'h12835b01; 10:kval=32'h243185be; 11:kval=32'h550c7dc3;
              12:kval=32'h72be5d74; 13:kval=32'h80deb1fe; 14:kval=32'h9bdc06a7; 15:kval=32'hc19bf174;
              16:kval=32'he49b69c1; 17:kval=32'hefbe4786; 18:kval=32'h0fc19dc6; 19:kval=32'h240ca1cc;
              20:kval=32'h2de92c6f; 21:kval=32'h4a7484aa; 22:kval=32'h5cb0a9dc; 23:kval=32'h76f988da;
              24:kval=32'h983e5152; 25:kval=32'ha831c66d; 26:kval=32'hb00327c8; 27:kval=32'hbf597fc7;
              28:kval=32'hc6e00bf3; 29:kval=32'hd5a79147; 30:kval=32'h06ca6351; 31:kval=32'h14292967;
              32:kval=32'h27b70a85; 33:kval=32'h2e1b2138; 34:kval=32'h4d2c6dfc; 35:kval=32'h53380d13;
              36:kval=32'h650a7354; 37:kval=32'h766a0abb; 38:kval=32'h81c2c92e; 39:kval=32'h92722c85;
              40:kval=32'ha2bfe8a1; 41:kval=32'ha81a664b; 42:kval=32'hc24b8b70; 43:kval=32'hc76c51a3;
              44:kval=32'hd192e819; 45:kval=32'hd6990624; 46:kval=32'hf40e3585; 47:kval=32'h106aa070;
              48:kval=32'h19a4c116; 49:kval=32'h1e376c08; 50:kval=32'h2748774c; 51:kval=32'h34b0bcb5;
              52:kval=32'h391c0cb3; 53:kval=32'h4ed8aa4a; 54:kval=32'h5b9cca4f; 55:kval=32'h682e6ff3;
              56:kval=32'h748f82ee; 57:kval=32'h78a5636f; 58:kval=32'h84c87814; 59:kval=32'h8cc70208;
              60:kval=32'h90befffa; 61:kval=32'ha4506ceb; 62:kval=32'hbef9a3f7; default:kval=32'hc67178f2;
            endcase
        end
    endfunction

    reg [31:0] wn,t1,t2;
    reg [31:0] ns0,ns1,ns2,ns3,ns4,ns5,ns6,ns7;
    always @* begin
        if (round_idx < 16)
            wn = w[round_idx];
        else
            wn = ssig1(w[round_idx-2]) + w[round_idx-7] + ssig0(w[round_idx-15]) + w[round_idx-16];
        t1 = h + bsig1(e) + ch(e,f,g) + kval(round_idx[5:0]) + wn;
        t2 = bsig0(a) + maj(a,b,c);
        ns0 = base0 + (t1+t2);
        ns1 = base1 + a;
        ns2 = base2 + b;
        ns3 = base3 + c;
        ns4 = base4 + (d+t1);
        ns5 = base5 + e;
        ns6 = base6 + f;
        ns7 = base7 + g;
    end

    always @(posedge clk) begin
        if (reset) begin
            base0<=0; base1<=0; base2<=0; base3<=0; base4<=0; base5<=0; base6<=0; base7<=0;
            a<=0; b<=0; c<=0; d<=0; e<=0; f<=0; g<=0; h<=0;
            round_idx<=0; round_count<=0; busy<=0; state_valid<=0; state_out<=0;
            for (reset_i=0; reset_i<64; reset_i=reset_i+1) w[reset_i]<=0;
        end else begin
            if (state_fire)
                state_valid <= 1'b0;

            if (block_valid && block_ready) begin
                base0<=state_in[255:224]; base1<=state_in[223:192];
                base2<=state_in[191:160]; base3<=state_in[159:128];
                base4<=state_in[127:96];  base5<=state_in[95:64];
                base6<=state_in[63:32];   base7<=state_in[31:0];
                a<=state_in[255:224]; b<=state_in[223:192];
                c<=state_in[191:160]; d<=state_in[159:128];
                e<=state_in[127:96];  f<=state_in[95:64];
                g<=state_in[63:32];   h<=state_in[31:0];
                for (load_i=0; load_i<16; load_i=load_i+1)
                    w[load_i] <= block_data[511-(load_i*32) -: 32];
                for (load_i=16; load_i<64; load_i=load_i+1)
                    w[load_i] <= 32'b0;
                round_idx<=0;
                round_count<=0;
                busy<=1'b1;
            end else if (busy) begin
                if (round_idx >= 16)
                    w[round_idx] <= wn;
                h<=g; g<=f; f<=e; e<=d+t1; d<=c; c<=b; b<=a; a<=t1+t2;
                round_count <= round_count + 7'd1;
                if (round_idx == 7'd63) begin
                    busy<=1'b0;
                    state_out<={ns0,ns1,ns2,ns3,ns4,ns5,ns6,ns7};
                    state_valid<=1'b1;
                end else begin
                    round_idx <= round_idx + 7'd1;
                end
            end
        end
    end
endmodule


module cosmic_hmac_sha256_shortmsg (
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

        outer_digest_block = 512'b0;
        outer_digest_block[511:256] = inner_digest;
        outer_digest_block[255:248] = 8'h80;
        outer_digest_block[63:0] = 64'd768;
    end

    always @* begin
        compress_valid = 1'b0;
        compress_state_in = SHA256_IV;
        compress_block = 512'b0;
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
                if (message_len > 6'd55) begin
                    // Unsupported by this frozen short-message engine. The
                    // caller must never issue such a message in HW-12/v0.1.
                    state <= ST_IDLE;
                    busy <= 1'b0;
                end else begin
                    key_reg <= key_block;
                    message_reg <= message_data;
                    message_len_reg <= message_len;
                    compression_count <= 0;
                    busy <= 1'b1;
                    state <= ST_INNER_PAD;
                end
            end

            if (compression_accept_pulse)
                compression_count <= compression_count + 3'd1;

            if (compress_state_valid) begin
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
