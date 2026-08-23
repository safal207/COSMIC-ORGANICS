`timescale 1ns/1ps

// COSMIC-HW-11/v0.1
// Frozen 2x2 Merkle throughput frontier:
//   TREE_BUFFERS = 1 or 2
//   MERKLE_ENGINES = 1 or 2
//
// Semantics are inherited unchanged from COSMIC-HW-10:
// - exact HW-09 SHA256x2 leaf commitment stream;
// - Merkle-16, constant frozen PAD leaf;
// - parent = standard SHA256(0x01 || left || right), 65-byte/two-block hash;
// - one root and four proof fragments per real leaf;
// - one proof serializer lane;
// - observational only: Merkle state never controls A/M/C decisions.
//
// M2 rule: two parent hashes may execute concurrently only inside the same
// dependency-ready tree level. Trees themselves are hashed one at a time.

module cosmic_hw11_merkle_frontier_core #(
    parameter integer TREE_BUFFERS = 1,
    parameter integer MERKLE_ENGINES = 1
) (
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
    output wire         proof_emit_pulse,

    output wire         inner_digest_valid_out,
    output wire         merkle_leaf_ready_out,
    output wire [1:0]   merkle_sha_busy_mask_out,
    output wire [1:0]   merkle_parent_accept_mask_out,
    output reg  [1:0]   buffer_occupied_mask_out,
    output wire         buffer_wait_pulse_out
);
    localparam [255:0] PAD_LEAF = 256'h14681950aa66cab259fa8da32adef6daa59316cf2bf4d43669d27efe69201ebe;
    localparam [2:0] BS_FREE       = 3'd0;
    localparam [2:0] BS_COLLECT    = 3'd1;
    localparam [2:0] BS_READY_HASH = 3'd2;
    localparam [2:0] BS_HASHING    = 3'd3;
    localparam [2:0] BS_READY_PROOF= 3'd4;
    localparam [2:0] BS_PROOFING   = 3'd5;

    // Exact frozen leaf commitment path.
    wire inner_digest_valid;
    wire inner_digest_ready;
    wire [255:0] inner_digest_data;
    wire [15:0] inner_digest_sequence;
    wire [3:0] fill_count_unused;
    wire waiting_unused;

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

    // Per-tree-buffer storage. Sizes elaborate from TREE_BUFFERS, so B1 does
    // not silently pay for a second tree store.
    reg [2:0]   buf_state [0:TREE_BUFFERS-1];
    reg [4:0]   buf_leaf_count [0:TREE_BUFFERS-1];
    reg [4:0]   buf_real_count [0:TREE_BUFFERS-1];
    reg [15:0]  buf_source_seq [0:TREE_BUFFERS-1];
    reg [15:0]  buf_tree_ord [0:TREE_BUFFERS-1];
    reg [255:0] leaves [0:TREE_BUFFERS*16-1];
    reg [255:0] level1 [0:TREE_BUFFERS*8-1];
    reg [255:0] level2 [0:TREE_BUFFERS*4-1];
    reg [255:0] level3 [0:TREE_BUFFERS*2-1];
    reg [255:0] roots [0:TREE_BUFFERS-1];

    reg collect_valid;
    reg collect_buf;
    reg [15:0] next_tree_ordinal;
    reg sequence_closing;

    wire merkle_leaf_ready = collect_valid && (buf_state[collect_buf] == BS_COLLECT) && (buf_leaf_count[collect_buf] < 5'd16);
    assign leaf_digest_valid = inner_digest_valid && merkle_leaf_ready;
    assign leaf_digest_data = inner_digest_data;
    assign leaf_digest_sequence = inner_digest_sequence;
    assign inner_digest_ready = leaf_digest_ready && merkle_leaf_ready;
    wire leaf_fire = inner_digest_valid && inner_digest_ready;

    assign inner_digest_valid_out = inner_digest_valid;
    assign merkle_leaf_ready_out = merkle_leaf_ready;
    assign buffer_wait_pulse_out = inner_digest_valid && leaf_digest_ready && !merkle_leaf_ready;
    assign merkle_leaf_count_out = collect_valid ? buf_leaf_count[collect_buf] : 5'd0;

    // One tree is hashed at a time. M2 parallelism is restricted to two
    // dependency-ready parents in the same level.
    reg compute_active;
    reg compute_buf;
    reg [2:0] hash_level;
    reg [3:0] wave_base;
    reg       wave_inflight;
    reg [1:0] wave_expected_mask;
    reg [1:0] wave_done_mask;

    reg [4:0] parents_this_level;
    reg need_engine1;
    always @* begin
        case (hash_level)
            3'd0: parents_this_level = 5'd8;
            3'd1: parents_this_level = 5'd4;
            3'd2: parents_this_level = 5'd2;
            default: parents_this_level = 5'd1;
        endcase
        need_engine1 = (MERKLE_ENGINES == 2) && ((wave_base + 4'd1) < parents_this_level);
    end

    reg [255:0] parent_left0, parent_right0, parent_left1, parent_right1;
    integer cbase;
    integer p0;
    integer p1;
    always @* begin
        parent_left0 = 256'b0; parent_right0 = 256'b0;
        parent_left1 = 256'b0; parent_right1 = 256'b0;
        cbase = compute_buf;
        p0 = wave_base;
        p1 = wave_base + 1;
        case (hash_level)
            3'd0: begin
                parent_left0  = leaves[cbase*16 + p0*2];
                parent_right0 = leaves[cbase*16 + p0*2 + 1];
                if (need_engine1) begin
                    parent_left1  = leaves[cbase*16 + p1*2];
                    parent_right1 = leaves[cbase*16 + p1*2 + 1];
                end
            end
            3'd1: begin
                parent_left0  = level1[cbase*8 + p0*2];
                parent_right0 = level1[cbase*8 + p0*2 + 1];
                if (need_engine1) begin
                    parent_left1  = level1[cbase*8 + p1*2];
                    parent_right1 = level1[cbase*8 + p1*2 + 1];
                end
            end
            3'd2: begin
                parent_left0  = level2[cbase*4 + p0*2];
                parent_right0 = level2[cbase*4 + p0*2 + 1];
                if (need_engine1) begin
                    parent_left1  = level2[cbase*4 + p1*2];
                    parent_right1 = level2[cbase*4 + p1*2 + 1];
                end
            end
            default: begin
                parent_left0  = level3[cbase*2];
                parent_right0 = level3[cbase*2 + 1];
            end
        endcase
    end

    wire sha0_ready, sha0_digest_valid, sha0_busy;
    wire [255:0] sha0_digest_data;
    wire [7:0] sha0_round_count;
    wire sha1_ready, sha1_digest_valid, sha1_busy;
    wire [255:0] sha1_digest_data;
    wire [7:0] sha1_round_count;

    wire wave_issue = compute_active && !wave_inflight && sha0_ready && (!need_engine1 || sha1_ready);
    wire sha0_parent_valid = wave_issue;
    wire sha1_parent_valid = wave_issue && need_engine1;

    cosmic_sha256_parent65_iterative merkle_sha0 (
        .clk(clk), .reset(reset),
        .parent_valid(sha0_parent_valid), .parent_ready(sha0_ready),
        .left_digest(parent_left0), .right_digest(parent_right0),
        .digest_valid(sha0_digest_valid), .digest_ready(1'b1),
        .digest_data(sha0_digest_data), .busy(sha0_busy), .round_count(sha0_round_count)
    );

    generate
        if (MERKLE_ENGINES == 2) begin : G_SHA1
            cosmic_sha256_parent65_iterative merkle_sha1 (
                .clk(clk), .reset(reset),
                .parent_valid(sha1_parent_valid), .parent_ready(sha1_ready),
                .left_digest(parent_left1), .right_digest(parent_right1),
                .digest_valid(sha1_digest_valid), .digest_ready(1'b1),
                .digest_data(sha1_digest_data), .busy(sha1_busy), .round_count(sha1_round_count)
            );
        end else begin : G_NO_SHA1
            assign sha1_ready = 1'b1;
            assign sha1_digest_valid = 1'b0;
            assign sha1_digest_data = 256'b0;
            assign sha1_busy = 1'b0;
            assign sha1_round_count = 8'b0;
        end
    endgenerate

    assign merkle_sha_busy_mask_out = {sha1_busy, sha0_busy};
    assign merkle_parent_accept_mask_out = {sha1_parent_valid && sha1_ready, sha0_parent_valid && sha0_ready};
    assign merkle_sha_busy_out = sha0_busy || sha1_busy;
    assign merkle_sha_round_count_out = (sha0_round_count > sha1_round_count) ? sha0_round_count : sha1_round_count;
    assign merkle_parent_accept_pulse = |merkle_parent_accept_mask_out;

    // Global ordered root/proof serializer. It may run while the next tree is
    // hashed, but external retirement remains strictly tree order.
    reg proof_active;
    reg proof_buf;
    reg root_phase;
    reg [3:0] proof_leaf_reg;
    reg [1:0] proof_level_reg;

    assign root_valid = proof_active && root_phase;
    assign root_data = roots[proof_buf];
    assign root_source_sequence = buf_source_seq[proof_buf];
    assign root_tree_ordinal = buf_tree_ord[proof_buf];
    assign root_real_leaf_count = buf_real_count[proof_buf];
    assign root_emit_pulse = root_valid && root_ready;

    assign proof_valid = proof_active && !root_phase;
    assign proof_source_sequence = buf_source_seq[proof_buf];
    assign proof_tree_ordinal = buf_tree_ord[proof_buf];
    assign proof_leaf_ordinal = proof_leaf_reg;
    assign proof_level = proof_level_reg;
    assign proof_sibling_is_left = (proof_leaf_reg >> proof_level_reg) & 1'b1;
    assign proof_emit_pulse = proof_valid && proof_ready;

    integer sibling_index;
    integer proof_base;
    always @* begin
        sibling_index = 0;
        proof_base = proof_buf;
        proof_sibling_digest = 256'b0;
        case (proof_level_reg)
            2'd0: begin
                sibling_index = proof_leaf_reg ^ 4'd1;
                proof_sibling_digest = leaves[proof_base*16 + sibling_index];
            end
            2'd1: begin
                sibling_index = (proof_leaf_reg >> 1) ^ 4'd1;
                proof_sibling_digest = level1[proof_base*8 + sibling_index];
            end
            2'd2: begin
                sibling_index = (proof_leaf_reg >> 2) ^ 4'd1;
                proof_sibling_digest = level2[proof_base*4 + sibling_index];
            end
            default: begin
                sibling_index = (proof_leaf_reg >> 3) ^ 4'd1;
                proof_sibling_digest = level3[proof_base*2 + sibling_index];
            end
        endcase
    end

    reg any_tree_busy;
    integer occ_i;
    always @* begin
        any_tree_busy = 1'b0;
        buffer_occupied_mask_out = 2'b0;
        for (occ_i=0; occ_i<TREE_BUFFERS; occ_i=occ_i+1) begin
            if (buf_state[occ_i] != BS_FREE)
                buffer_occupied_mask_out[occ_i] = 1'b1;
            if (buf_state[occ_i] == BS_READY_HASH || buf_state[occ_i] == BS_HASHING ||
                buf_state[occ_i] == BS_READY_PROOF || buf_state[occ_i] == BS_PROOFING)
                any_tree_busy = 1'b1;
        end
    end
    assign merkle_tree_busy_out = any_tree_busy;

    integer reset_b;
    integer reset_leaf;
    integer reset_l1;
    integer reset_l2;
    integer reset_l3;
    integer pad_i;
    reg [1:0] done_now;
    integer chosen;

    always @(posedge clk) begin
        if (reset) begin
            collect_valid <= 1'b1;
            collect_buf <= 1'b0;
            next_tree_ordinal <= 16'd0;
            sequence_closing <= 1'b0;
            compute_active <= 1'b0;
            compute_buf <= 1'b0;
            hash_level <= 3'd0;
            wave_base <= 4'd0;
            wave_inflight <= 1'b0;
            wave_expected_mask <= 2'b0;
            wave_done_mask <= 2'b0;
            proof_active <= 1'b0;
            proof_buf <= 1'b0;
            root_phase <= 1'b1;
            proof_leaf_reg <= 4'd0;
            proof_level_reg <= 2'd0;
            for (reset_b=0; reset_b<TREE_BUFFERS; reset_b=reset_b+1) begin
                buf_state[reset_b] <= BS_FREE;
                buf_leaf_count[reset_b] <= 5'd0;
                buf_real_count[reset_b] <= 5'd0;
                buf_source_seq[reset_b] <= 16'd0;
                buf_tree_ord[reset_b] <= 16'd0;
                roots[reset_b] <= 256'b0;
            end
            buf_state[0] <= BS_COLLECT;
            for (reset_leaf=0; reset_leaf<TREE_BUFFERS*16; reset_leaf=reset_leaf+1) leaves[reset_leaf] <= 256'b0;
            for (reset_l1=0; reset_l1<TREE_BUFFERS*8; reset_l1=reset_l1+1) level1[reset_l1] <= 256'b0;
            for (reset_l2=0; reset_l2<TREE_BUFFERS*4; reset_l2=reset_l2+1) level2[reset_l2] <= 256'b0;
            for (reset_l3=0; reset_l3<TREE_BUFFERS*2; reset_l3=reset_l3+1) level3[reset_l3] <= 256'b0;
        end else begin
            // Reclaim a free buffer as the collector whenever possible, unless
            // the explicit sequence boundary has closed collection.
            if (!collect_valid && !sequence_closing) begin
                if (buf_state[0] == BS_FREE) begin
                    collect_valid <= 1'b1;
                    collect_buf <= 1'b0;
                    buf_state[0] <= BS_COLLECT;
                    buf_leaf_count[0] <= 5'd0;
                    buf_real_count[0] <= 5'd0;
                end else if (TREE_BUFFERS == 2 && buf_state[1] == BS_FREE) begin
                    collect_valid <= 1'b1;
                    collect_buf <= 1'b1;
                    buf_state[1] <= BS_COLLECT;
                    buf_leaf_count[1] <= 5'd0;
                    buf_real_count[1] <= 5'd0;
                end
            end

            // Collect exact leaf digest stream into the currently owned tree.
            if (leaf_fire) begin
                leaves[collect_buf*16 + buf_leaf_count[collect_buf]] <= inner_digest_data;
                if (buf_leaf_count[collect_buf] == 5'd0) begin
                    buf_source_seq[collect_buf] <= source_sequence_id;
                    buf_tree_ord[collect_buf] <= next_tree_ordinal;
                end
                if (buf_leaf_count[collect_buf] == 5'd15) begin
                    buf_leaf_count[collect_buf] <= 5'd16;
                    buf_real_count[collect_buf] <= 5'd16;
                    buf_state[collect_buf] <= BS_READY_HASH;
                    collect_valid <= 1'b0;
                    next_tree_ordinal <= next_tree_ordinal + 16'd1;
                end else begin
                    buf_leaf_count[collect_buf] <= buf_leaf_count[collect_buf] + 5'd1;
                end
            end

            // Explicit end-of-sequence partial-tree close. No new collector is
            // opened after this point; reset starts the next frozen sequence.
            if (tree_flush && collect_valid && buf_leaf_count[collect_buf] != 0 && !leaf_fire) begin
                buf_real_count[collect_buf] <= buf_leaf_count[collect_buf];
                buf_source_seq[collect_buf] <= source_sequence_id;
                buf_tree_ord[collect_buf] <= next_tree_ordinal;
                for (pad_i=0; pad_i<16; pad_i=pad_i+1)
                    if (pad_i >= buf_leaf_count[collect_buf])
                        leaves[collect_buf*16 + pad_i] <= PAD_LEAF;
                buf_state[collect_buf] <= BS_READY_HASH;
                collect_valid <= 1'b0;
                next_tree_ordinal <= next_tree_ordinal + 16'd1;
                sequence_closing <= 1'b1;
            end

            // Select the oldest ready tree for hashing. Only one tree compute
            // context is active; M2 parallelizes parents inside that tree.
            if (!compute_active) begin
                chosen = -1;
                if (buf_state[0] == BS_READY_HASH)
                    chosen = 0;
                if (TREE_BUFFERS == 2 && buf_state[1] == BS_READY_HASH) begin
                    if (chosen < 0 || buf_tree_ord[1] < buf_tree_ord[chosen])
                        chosen = 1;
                end
                if (chosen >= 0) begin
                    compute_active <= 1'b1;
                    compute_buf <= chosen[0:0];
                    buf_state[chosen] <= BS_HASHING;
                    hash_level <= 3'd0;
                    wave_base <= 4'd0;
                    wave_inflight <= 1'b0;
                    wave_expected_mask <= 2'b0;
                    wave_done_mask <= 2'b0;
                end
            end

            if (wave_issue) begin
                wave_inflight <= 1'b1;
                wave_expected_mask <= need_engine1 ? 2'b11 : 2'b01;
                wave_done_mask <= 2'b00;
            end

            // Store completed parent hashes at their frozen deterministic indices.
            if (wave_inflight) begin
                done_now = wave_done_mask;
                if (sha0_digest_valid) begin
                    done_now[0] = 1'b1;
                    case (hash_level)
                        3'd0: level1[compute_buf*8 + wave_base] <= sha0_digest_data;
                        3'd1: level2[compute_buf*4 + wave_base] <= sha0_digest_data;
                        3'd2: level3[compute_buf*2 + wave_base] <= sha0_digest_data;
                        default: roots[compute_buf] <= sha0_digest_data;
                    endcase
                end
                if (sha1_digest_valid && wave_expected_mask[1]) begin
                    done_now[1] = 1'b1;
                    case (hash_level)
                        3'd0: level1[compute_buf*8 + wave_base + 1] <= sha1_digest_data;
                        3'd1: level2[compute_buf*4 + wave_base + 1] <= sha1_digest_data;
                        3'd2: level3[compute_buf*2 + wave_base + 1] <= sha1_digest_data;
                        default: ;
                    endcase
                end
                wave_done_mask <= done_now;

                if ((done_now & wave_expected_mask) == wave_expected_mask) begin
                    wave_inflight <= 1'b0;
                    wave_done_mask <= 2'b0;
                    if ((wave_base + (wave_expected_mask[1] ? 4'd2 : 4'd1)) >= parents_this_level) begin
                        if (hash_level == 3'd3) begin
                            compute_active <= 1'b0;
                            buf_state[compute_buf] <= BS_READY_PROOF;
                            hash_level <= 3'd0;
                            wave_base <= 4'd0;
                        end else begin
                            hash_level <= hash_level + 3'd1;
                            wave_base <= 4'd0;
                        end
                    end else begin
                        wave_base <= wave_base + (wave_expected_mask[1] ? 4'd2 : 4'd1);
                    end
                end
            end

            // Ordered proof retirement can overlap hashing of the next tree.
            if (!proof_active) begin
                chosen = -1;
                if (buf_state[0] == BS_READY_PROOF)
                    chosen = 0;
                if (TREE_BUFFERS == 2 && buf_state[1] == BS_READY_PROOF) begin
                    if (chosen < 0 || buf_tree_ord[1] < buf_tree_ord[chosen])
                        chosen = 1;
                end
                if (chosen >= 0) begin
                    proof_active <= 1'b1;
                    proof_buf <= chosen[0:0];
                    buf_state[chosen] <= BS_PROOFING;
                    root_phase <= 1'b1;
                    proof_leaf_reg <= 4'd0;
                    proof_level_reg <= 2'd0;
                end
            end

            if (root_valid && root_ready)
                root_phase <= 1'b0;

            if (proof_valid && proof_ready) begin
                if (proof_level_reg != 2'd3) begin
                    proof_level_reg <= proof_level_reg + 2'd1;
                end else if ((proof_leaf_reg + 4'd1) < buf_real_count[proof_buf]) begin
                    proof_leaf_reg <= proof_leaf_reg + 4'd1;
                    proof_level_reg <= 2'd0;
                end else begin
                    buf_state[proof_buf] <= BS_FREE;
                    buf_leaf_count[proof_buf] <= 5'd0;
                    buf_real_count[proof_buf] <= 5'd0;
                    proof_active <= 1'b0;
                    root_phase <= 1'b1;
                    proof_leaf_reg <= 4'd0;
                    proof_level_reg <= 2'd0;
                end
            end
        end
    end
endmodule
