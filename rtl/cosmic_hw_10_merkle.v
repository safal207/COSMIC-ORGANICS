`timescale 1ns/1ps

// COSMIC-HW-10/v0.1
// Frozen Merkle-16 + inclusion-proof cost candidate over the selected HW-09
// SHA256x2 commitment stream.
//
// Scientific boundary:
// - exact HW-09 x2 leaf commitment path is instantiated unchanged;
// - one dedicated conventional iterative SHA-256 engine hashes Merkle parents;
// - parent = SHA256(0x01 || left[256] || right[256]), a real 65-byte,
//   two-compression-block SHA-256 message;
// - one 16-leaf tree buffer, no double buffering;
// - all 16 leaves + all 15 internal nodes are retained for proof output;
// - Merkle state/root/proof content is observational and never feeds A/M/C.

module cosmic_sha256_parent65_iterative (
    input  wire         clk,
    input  wire         reset,
    input  wire         parent_valid,
    output wire         parent_ready,
    input  wire [255:0] left_digest,
    input  wire [255:0] right_digest,
    output reg          digest_valid,
    input  wire         digest_ready,
    output reg  [255:0] digest_data,
    output reg          busy,
    output reg  [7:0]   round_count
);
    reg [31:0] base0,base1,base2,base3,base4,base5,base6,base7;
    reg [31:0] a,b,c,d,e,f,g,h;
    reg [31:0] w [0:63];
    reg [6:0] round_idx;
    reg       second_block;
    reg [511:0] block1_data;
    integer reset_i;
    integer load_i;

    wire digest_fire = digest_valid && digest_ready;
    assign parent_ready = !busy && (!digest_valid || digest_ready);

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
    reg [511:0] first_block;
    reg [511:0] second_block_data;

    always @* begin
        first_block = {8'h01, left_digest, right_digest[255:8]};
        // 65-byte message: final right byte, 0x80, 54 zero bytes, 64-bit length=520.
        second_block_data = {right_digest[7:0], 8'h80, 432'b0, 64'd520};

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
            round_idx<=0; second_block<=0; block1_data<=0;
            digest_valid<=0; digest_data<=0; busy<=0; round_count<=0;
            for (reset_i=0; reset_i<64; reset_i=reset_i+1) w[reset_i]<=0;
        end else begin
            if (digest_fire)
                digest_valid <= 1'b0;

            if (parent_valid && parent_ready) begin
                base0<=32'h6a09e667; base1<=32'hbb67ae85; base2<=32'h3c6ef372; base3<=32'ha54ff53a;
                base4<=32'h510e527f; base5<=32'h9b05688c; base6<=32'h1f83d9ab; base7<=32'h5be0cd19;
                a<=32'h6a09e667; b<=32'hbb67ae85; c<=32'h3c6ef372; d<=32'ha54ff53a;
                e<=32'h510e527f; f<=32'h9b05688c; g<=32'h1f83d9ab; h<=32'h5be0cd19;
                for (load_i=0; load_i<16; load_i=load_i+1)
                    w[load_i] <= first_block[511-(load_i*32) -: 32];
                for (load_i=16; load_i<64; load_i=load_i+1)
                    w[load_i] <= 32'b0;
                block1_data <= second_block_data;
                round_idx<=0;
                round_count<=0;
                second_block<=0;
                busy<=1'b1;
            end else if (busy) begin
                if (round_idx >= 16)
                    w[round_idx] <= wn;
                h<=g; g<=f; f<=e; e<=d+t1; d<=c; c<=b; b<=a; a<=t1+t2;
                round_count <= round_count + 8'd1;

                if (round_idx == 7'd63) begin
                    if (!second_block) begin
                        // Chaining state after the first compression block.
                        base0<=ns0; base1<=ns1; base2<=ns2; base3<=ns3;
                        base4<=ns4; base5<=ns5; base6<=ns6; base7<=ns7;
                        a<=ns0; b<=ns1; c<=ns2; d<=ns3; e<=ns4; f<=ns5; g<=ns6; h<=ns7;
                        for (load_i=0; load_i<16; load_i=load_i+1)
                            w[load_i] <= block1_data[511-(load_i*32) -: 32];
                        for (load_i=16; load_i<64; load_i=load_i+1)
                            w[load_i] <= 32'b0;
                        round_idx<=0;
                        second_block<=1'b1;
                    end else begin
                        busy<=1'b0;
                        digest_data<={ns0,ns1,ns2,ns3,ns4,ns5,ns6,ns7};
                        digest_valid<=1'b1;
                    end
                end else begin
                    round_idx <= round_idx + 7'd1;
                end
            end
        end
    end
endmodule


module cosmic_hw10_sparse_receipt_sha256x2_merkle16 (
    input  wire         clk,
    input  wire         reset,
    input  wire         tick_valid,
    output wire         tick_ready,
    input  wire [511:0] stimulus_bus,
    input  wire         flush,
    input  wire [15:0]  source_sequence_id,
    input  wire         tree_flush,

    output wire [127:0] phase_bus,
    output wire [63:0]  active_mask,
    output wire [63:0]  changed_mask,
    output wire [63:0]  dirty_mask,

    output wire         leaf_digest_valid,
    input  wire         leaf_digest_ready,
    output wire [255:0] leaf_digest_data,
    output wire [15:0]  leaf_digest_sequence,

    output wire         root_valid,
    input  wire         root_ready,
    output wire [255:0] root_data,
    output wire [15:0]  root_source_sequence,
    output wire [15:0]  root_tree_ordinal,
    output wire [4:0]   root_real_leaf_count,

    output wire         proof_valid,
    input  wire         proof_ready,
    output wire [15:0]  proof_source_sequence,
    output wire [15:0]  proof_tree_ordinal,
    output wire [3:0]   proof_leaf_ordinal,
    output wire [1:0]   proof_level,
    output wire         proof_sibling_is_left,
    output reg  [255:0] proof_sibling_digest,

    output wire         receipt_valid_out,
    output wire         receipt_ready_out,
    output wire [39:0]  receipt_data_out,
    output wire [2:0]   batch_occupancy_out,
    output wire         pending_observation_out,
    output wire [3:0]   leaf_engine_busy_mask,
    output wire [3:0]   leaf_engine_digest_valid_mask,
    output wire [3:0]   leaf_engine_block_accept_mask,

    output wire [4:0]   merkle_leaf_count_out,
    output wire         merkle_tree_busy_out,
    output wire         merkle_sha_busy_out,
    output wire [7:0]   merkle_sha_round_count_out,
    output wire         merkle_parent_accept_pulse,
    output wire         root_emit_pulse,
    output wire         proof_emit_pulse
);
    localparam [255:0] PAD_LEAF = 256'h14681950aa66cab259fa8da32adef6daa59316cf2bf4d43669d27efe69201ebe;
    localparam [2:0] ST_COLLECT = 3'd0;
    localparam [2:0] ST_HASH    = 3'd1;
    localparam [2:0] ST_ROOT    = 3'd2;
    localparam [2:0] ST_PROOF   = 3'd3;

    wire inner_digest_valid;
    wire inner_digest_ready;
    wire [255:0] inner_digest_data;
    wire [15:0] inner_digest_sequence;
    wire [3:0] fill_count_unused;
    wire waiting_unused;

    reg [2:0] tree_state;
    reg [4:0] leaf_count;
    reg [4:0] real_leaf_count;
    reg [15:0] tree_source_sequence_reg;
    reg [15:0] tree_ordinal_reg;

    reg [255:0] leaves [0:15];
    reg [255:0] level1 [0:7];
    reg [255:0] level2 [0:3];
    reg [255:0] level3 [0:1];
    reg [255:0] root_reg;

    reg [2:0] hash_level;
    reg [3:0] hash_index;
    reg       hash_inflight;
    reg [3:0] proof_leaf_reg;
    reg [1:0] proof_level_reg;

    integer reset_leaf_i;
    integer reset_l1_i;
    integer reset_l2_i;
    integer reset_l3_i;
    integer pad_i;

    wire merkle_leaf_ready = (tree_state == ST_COLLECT) && (leaf_count < 5'd16);
    assign leaf_digest_valid = inner_digest_valid && merkle_leaf_ready;
    assign leaf_digest_data = inner_digest_data;
    assign leaf_digest_sequence = inner_digest_sequence;
    assign inner_digest_ready = leaf_digest_ready && merkle_leaf_ready;
    wire leaf_fire = inner_digest_valid && inner_digest_ready;

    cosmic_hw09_sparse_receipt_sha256x2 leaf_path (
        .clk(clk), .reset(reset),
        .tick_valid(tick_valid), .tick_ready(tick_ready),
        .stimulus_bus(stimulus_bus), .flush(flush),
        .phase_bus(phase_bus), .active_mask(active_mask),
        .changed_mask(changed_mask), .dirty_mask(dirty_mask),
        .digest_valid(inner_digest_valid), .digest_ready(inner_digest_ready),
        .digest_data(inner_digest_data), .digest_sequence(inner_digest_sequence),
        .fill_count_out(fill_count_unused), .waiting_block_valid_out(waiting_unused),
        .engine_busy_mask(leaf_engine_busy_mask),
        .engine_digest_valid_mask(leaf_engine_digest_valid_mask),
        .engine_block_accept_mask(leaf_engine_block_accept_mask),
        .receipt_valid_out(receipt_valid_out), .receipt_ready_out(receipt_ready_out),
        .receipt_data_out(receipt_data_out),
        .batch_occupancy_out(batch_occupancy_out),
        .pending_observation_out(pending_observation_out)
    );

    reg [255:0] parent_left;
    reg [255:0] parent_right;
    always @* begin
        parent_left = 256'b0;
        parent_right = 256'b0;
        case (hash_level)
            3'd0: begin parent_left = leaves[hash_index*2]; parent_right = leaves[hash_index*2+1]; end
            3'd1: begin parent_left = level1[hash_index*2]; parent_right = level1[hash_index*2+1]; end
            3'd2: begin parent_left = level2[hash_index*2]; parent_right = level2[hash_index*2+1]; end
            default: begin parent_left = level3[0]; parent_right = level3[1]; end
        endcase
    end

    wire parent_valid = (tree_state == ST_HASH) && !hash_inflight;
    wire parent_ready;
    wire parent_digest_valid;
    wire [255:0] parent_digest_data;
    wire parent_busy;
    wire [7:0] parent_round_count;
    assign merkle_parent_accept_pulse = parent_valid && parent_ready;

    cosmic_sha256_parent65_iterative merkle_sha (
        .clk(clk), .reset(reset),
        .parent_valid(parent_valid), .parent_ready(parent_ready),
        .left_digest(parent_left), .right_digest(parent_right),
        .digest_valid(parent_digest_valid), .digest_ready(1'b1),
        .digest_data(parent_digest_data),
        .busy(parent_busy), .round_count(parent_round_count)
    );

    assign root_valid = (tree_state == ST_ROOT);
    assign root_data = root_reg;
    assign root_source_sequence = tree_source_sequence_reg;
    assign root_tree_ordinal = tree_ordinal_reg;
    assign root_real_leaf_count = real_leaf_count;
    assign root_emit_pulse = root_valid && root_ready;

    assign proof_valid = (tree_state == ST_PROOF);
    assign proof_source_sequence = tree_source_sequence_reg;
    assign proof_tree_ordinal = tree_ordinal_reg;
    assign proof_leaf_ordinal = proof_leaf_reg;
    assign proof_level = proof_level_reg;
    assign proof_sibling_is_left = (proof_leaf_reg >> proof_level_reg) & 1'b1;
    assign proof_emit_pulse = proof_valid && proof_ready;

    reg [3:0] sibling_index;
    always @* begin
        sibling_index = 4'd0;
        proof_sibling_digest = 256'b0;
        case (proof_level_reg)
            2'd0: begin
                sibling_index = proof_leaf_reg ^ 4'd1;
                proof_sibling_digest = leaves[sibling_index];
            end
            2'd1: begin
                sibling_index = (proof_leaf_reg >> 1) ^ 4'd1;
                proof_sibling_digest = level1[sibling_index];
            end
            2'd2: begin
                sibling_index = (proof_leaf_reg >> 2) ^ 4'd1;
                proof_sibling_digest = level2[sibling_index];
            end
            default: begin
                sibling_index = (proof_leaf_reg >> 3) ^ 4'd1;
                proof_sibling_digest = level3[sibling_index];
            end
        endcase
    end

    assign merkle_leaf_count_out = leaf_count;
    assign merkle_tree_busy_out = (tree_state != ST_COLLECT);
    assign merkle_sha_busy_out = parent_busy;
    assign merkle_sha_round_count_out = parent_round_count;

    always @(posedge clk) begin
        if (reset) begin
            tree_state <= ST_COLLECT;
            leaf_count <= 5'd0;
            real_leaf_count <= 5'd0;
            tree_source_sequence_reg <= 16'd0;
            tree_ordinal_reg <= 16'd0;
            hash_level <= 3'd0;
            hash_index <= 4'd0;
            hash_inflight <= 1'b0;
            proof_leaf_reg <= 4'd0;
            proof_level_reg <= 2'd0;
            root_reg <= 256'b0;
            for (reset_leaf_i=0; reset_leaf_i<16; reset_leaf_i=reset_leaf_i+1) leaves[reset_leaf_i] <= 256'b0;
            for (reset_l1_i=0; reset_l1_i<8; reset_l1_i=reset_l1_i+1) level1[reset_l1_i] <= 256'b0;
            for (reset_l2_i=0; reset_l2_i<4; reset_l2_i=reset_l2_i+1) level2[reset_l2_i] <= 256'b0;
            for (reset_l3_i=0; reset_l3_i<2; reset_l3_i=reset_l3_i+1) level3[reset_l3_i] <= 256'b0;
        end else begin
            // Collect the exact x2 commitment digest stream. The external leaf
            // sink remains part of the handshake through inner_digest_ready.
            if (leaf_fire) begin
                leaves[leaf_count] <= inner_digest_data;
                if (leaf_count == 5'd0)
                    tree_source_sequence_reg <= source_sequence_id;

                if (leaf_count == 5'd15) begin
                    real_leaf_count <= 5'd16;
                    leaf_count <= 5'd16;
                    hash_level <= 3'd0;
                    hash_index <= 4'd0;
                    hash_inflight <= 1'b0;
                    tree_state <= ST_HASH;
                end else begin
                    leaf_count <= leaf_count + 5'd1;
                end
            end

            // Explicit source-sequence boundary closes a partial tree. The
            // runner only asserts tree_flush after the final leaf handshake.
            if (tree_flush && tree_state == ST_COLLECT && leaf_count != 0 && !leaf_fire) begin
                real_leaf_count <= leaf_count;
                tree_source_sequence_reg <= source_sequence_id;
                for (pad_i=0; pad_i<16; pad_i=pad_i+1)
                    if (pad_i >= leaf_count)
                        leaves[pad_i] <= PAD_LEAF;
                hash_level <= 3'd0;
                hash_index <= 4'd0;
                hash_inflight <= 1'b0;
                tree_state <= ST_HASH;
            end

            if (parent_valid && parent_ready)
                hash_inflight <= 1'b1;

            if (parent_digest_valid && tree_state == ST_HASH) begin
                hash_inflight <= 1'b0;
                case (hash_level)
                    3'd0: begin
                        level1[hash_index] <= parent_digest_data;
                        if (hash_index == 4'd7) begin hash_level <= 3'd1; hash_index <= 4'd0; end
                        else hash_index <= hash_index + 4'd1;
                    end
                    3'd1: begin
                        level2[hash_index] <= parent_digest_data;
                        if (hash_index == 4'd3) begin hash_level <= 3'd2; hash_index <= 4'd0; end
                        else hash_index <= hash_index + 4'd1;
                    end
                    3'd2: begin
                        level3[hash_index] <= parent_digest_data;
                        if (hash_index == 4'd1) begin hash_level <= 3'd3; hash_index <= 4'd0; end
                        else hash_index <= hash_index + 4'd1;
                    end
                    default: begin
                        root_reg <= parent_digest_data;
                        tree_state <= ST_ROOT;
                    end
                endcase
            end

            if (root_valid && root_ready) begin
                proof_leaf_reg <= 4'd0;
                proof_level_reg <= 2'd0;
                tree_state <= ST_PROOF;
            end

            if (proof_valid && proof_ready) begin
                if (proof_level_reg != 2'd3) begin
                    proof_level_reg <= proof_level_reg + 2'd1;
                end else if ((proof_leaf_reg + 4'd1) < real_leaf_count) begin
                    proof_leaf_reg <= proof_leaf_reg + 4'd1;
                    proof_level_reg <= 2'd0;
                end else begin
                    // Tree is reusable only after every real-leaf proof drains.
                    tree_state <= ST_COLLECT;
                    leaf_count <= 5'd0;
                    real_leaf_count <= 5'd0;
                    tree_ordinal_reg <= tree_ordinal_reg + 16'd1;
                    hash_level <= 3'd0;
                    hash_index <= 4'd0;
                    hash_inflight <= 1'b0;
                    proof_leaf_reg <= 4'd0;
                    proof_level_reg <= 2'd0;
                end
            end
        end
    end
endmodule
