`timescale 1ns/1ps

// COSMIC-HW-12/v0.1 integrated candidate.
// Exact HW-11 B1_M2 Merkle/proof pipeline plus one finite HMAC-SHA256 root
// authentication observer. The only coupling is ordinary valid/ready
// backpressure at the already-authoritative root retirement boundary.
module cosmic_hw12_b1_m2_hmacx1 (
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
    output wire [255:0] proof_sibling_digest,

    output wire         tag_valid,
    input  wire         tag_ready,
    output wire [255:0] tag_data,
    output wire [15:0]  tag_source_sequence,
    output wire [15:0]  tag_tree_ordinal,
    output wire [4:0]   tag_real_leaf_count,

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
    output wire [1:0]   buffer_occupied_mask_out,
    output wire         buffer_wait_pulse_out,

    output wire         hmac_busy_out,
    output wire         hmac_compression_busy_out,
    output wire [6:0]   hmac_compression_round_count_out,
    output wire         hmac_compression_accept_pulse_out,
    output wire [2:0]   hmac_compression_count_out,
    output wire         hmac_pending_valid_out,
    output wire         hmac_message_accept_pulse_out
);
    localparam [255:0] TEST_KEY = 256'h04ff8909facf51a6f8942238fc5c65bd65b9ed816fe0c10bc179476c0911eb42;
    localparam [511:0] TEST_KEY_BLOCK = {TEST_KEY,256'b0};

    wire inner_root_valid;
    wire inner_root_ready;
    wire [255:0] inner_root_data;
    wire [15:0] inner_root_source_sequence;
    wire [15:0] inner_root_tree_ordinal;
    wire [4:0] inner_root_real_leaf_count;
    wire inner_root_emit_pulse;

    reg pending_valid;
    reg [255:0] pending_root;
    reg [15:0] pending_source_sequence;
    reg [15:0] pending_tree_ordinal;
    reg [4:0] pending_real_leaf_count;

    wire hmac_message_ready;
    wire hmac_tag_valid;
    wire [255:0] hmac_tag_data;
    wire hmac_busy;
    wire hmac_compression_busy;
    wire [6:0] hmac_compression_round_count;
    wire hmac_compression_accept_pulse;
    wire [2:0] hmac_compression_count;

    reg [15:0] active_source_sequence;
    reg [15:0] active_tree_ordinal;
    reg [4:0] active_real_leaf_count;

    wire pending_fire = pending_valid && hmac_message_ready;
    wire pending_can_accept = !pending_valid || hmac_message_ready;
    assign inner_root_ready = root_ready && pending_can_accept;
    wire root_fire = inner_root_valid && inner_root_ready;

    assign root_valid = inner_root_valid;
    assign root_data = inner_root_data;
    assign root_source_sequence = inner_root_source_sequence;
    assign root_tree_ordinal = inner_root_tree_ordinal;
    assign root_real_leaf_count = inner_root_real_leaf_count;
    assign root_emit_pulse = root_fire;

    assign tag_valid = hmac_tag_valid;
    assign tag_data = hmac_tag_data;
    assign tag_source_sequence = active_source_sequence;
    assign tag_tree_ordinal = active_tree_ordinal;
    assign tag_real_leaf_count = active_real_leaf_count;

    assign hmac_busy_out = hmac_busy;
    assign hmac_compression_busy_out = hmac_compression_busy;
    assign hmac_compression_round_count_out = hmac_compression_round_count;
    assign hmac_compression_accept_pulse_out = hmac_compression_accept_pulse;
    assign hmac_compression_count_out = hmac_compression_count;
    assign hmac_pending_valid_out = pending_valid;
    assign hmac_message_accept_pulse_out = pending_fire;

    wire [439:0] hmac_message_data = {
        32'h434f3132,
        pending_source_sequence,
        pending_tree_ordinal,
        3'b000, pending_real_leaf_count,
        pending_root,
        112'b0
    };

    cosmic_hmac_sha256_shortmsg_safe hmac (
        .clk(clk), .reset(reset),
        .message_valid(pending_valid), .message_ready(hmac_message_ready),
        .key_block(TEST_KEY_BLOCK),
        .message_data(hmac_message_data), .message_len(6'd41),
        .tag_valid(hmac_tag_valid), .tag_ready(tag_ready), .tag_data(hmac_tag_data),
        .busy(hmac_busy), .compression_count(hmac_compression_count),
        .compression_busy(hmac_compression_busy),
        .compression_round_count(hmac_compression_round_count),
        .compression_accept_pulse(hmac_compression_accept_pulse)
    );

    cosmic_hw11_merkle_frontier_core #(
        .TREE_BUFFERS(1), .MERKLE_ENGINES(2)
    ) merkle (
        .clk(clk), .reset(reset),
        .tick_valid(tick_valid), .tick_ready(tick_ready),
        .stimulus_bus(stimulus_bus), .flush(flush),
        .source_sequence_id(source_sequence_id), .tree_flush(tree_flush),
        .phase_bus(phase_bus), .active_mask(active_mask),
        .changed_mask(changed_mask), .dirty_mask(dirty_mask),
        .leaf_digest_valid(leaf_digest_valid), .leaf_digest_ready(leaf_digest_ready),
        .leaf_digest_data(leaf_digest_data), .leaf_digest_sequence(leaf_digest_sequence),
        .root_valid(inner_root_valid), .root_ready(inner_root_ready),
        .root_data(inner_root_data), .root_source_sequence(inner_root_source_sequence),
        .root_tree_ordinal(inner_root_tree_ordinal), .root_real_leaf_count(inner_root_real_leaf_count),
        .proof_valid(proof_valid), .proof_ready(proof_ready),
        .proof_source_sequence(proof_source_sequence), .proof_tree_ordinal(proof_tree_ordinal),
        .proof_leaf_ordinal(proof_leaf_ordinal), .proof_level(proof_level),
        .proof_sibling_is_left(proof_sibling_is_left), .proof_sibling_digest(proof_sibling_digest),
        .receipt_valid_out(receipt_valid_out), .receipt_ready_out(receipt_ready_out),
        .receipt_data_out(receipt_data_out), .batch_occupancy_out(batch_occupancy_out),
        .pending_observation_out(pending_observation_out),
        .leaf_engine_busy_mask(leaf_engine_busy_mask),
        .leaf_engine_digest_valid_mask(leaf_engine_digest_valid_mask),
        .leaf_engine_block_accept_mask(leaf_engine_block_accept_mask),
        .merkle_leaf_count_out(merkle_leaf_count_out),
        .merkle_tree_busy_out(merkle_tree_busy_out),
        .merkle_sha_busy_out(merkle_sha_busy_out),
        .merkle_sha_round_count_out(merkle_sha_round_count_out),
        .merkle_parent_accept_pulse(merkle_parent_accept_pulse),
        .root_emit_pulse(inner_root_emit_pulse), .proof_emit_pulse(proof_emit_pulse),
        .inner_digest_valid_out(inner_digest_valid_out),
        .merkle_leaf_ready_out(merkle_leaf_ready_out),
        .merkle_sha_busy_mask_out(merkle_sha_busy_mask_out),
        .merkle_parent_accept_mask_out(merkle_parent_accept_mask_out),
        .buffer_occupied_mask_out(buffer_occupied_mask_out),
        .buffer_wait_pulse_out(buffer_wait_pulse_out)
    );

    always @(posedge clk) begin
        if (reset) begin
            pending_valid <= 1'b0;
            pending_root <= 256'b0;
            pending_source_sequence <= 16'b0;
            pending_tree_ordinal <= 16'b0;
            pending_real_leaf_count <= 5'b0;
            active_source_sequence <= 16'b0;
            active_tree_ordinal <= 16'b0;
            active_real_leaf_count <= 5'b0;
        end else begin
            if (pending_fire) begin
                pending_valid <= 1'b0;
                active_source_sequence <= pending_source_sequence;
                active_tree_ordinal <= pending_tree_ordinal;
                active_real_leaf_count <= pending_real_leaf_count;
            end

            // Same-cycle pending dispatch + next-root capture is intentional:
            // the HMAC samples the old pending record at this edge, then the
            // finite slot is refilled with the new root for a future accept.
            if (root_fire) begin
                pending_valid <= 1'b1;
                pending_root <= inner_root_data;
                pending_source_sequence <= inner_root_source_sequence;
                pending_tree_ordinal <= inner_root_tree_ordinal;
                pending_real_leaf_count <= inner_root_real_leaf_count;
            end
        end
    end
endmodule
