`timescale 1ns/1ps

// COSMIC-HW-13/v0.1 physical harness.
// This module deliberately does not reimplement any frozen processor/proof
// logic. It instantiates the exact HW-12 core and replaces benchmark-wide I/O
// with finite dynamic on-chip stimulus/control plus a narrow observable fold.
// The checksum/status path is observation-only and never feeds the core.
module cosmic_hw13_ecp5_harness (
    input  wire       clk,
    input  wire       reset,
    output wire [7:0] status
);
    reg [511:0] stimulus_state;
    reg [31:0] cycle_counter;
    reg [15:0] source_sequence_id;
    reg tick_valid;
    reg [63:0] checksum;
    reg [31:0] accepted_ticks;

    wire tick_ready;
    wire tick_fire = tick_valid && tick_ready;

    // Every original wide input remains time-varying. Sink-ready patterns are
    // deterministic but distinct, so no single constant-ready simplification
    // can erase all observer/backpressure paths.
    wire flush = (cycle_counter[11:0] == 12'h7ff);
    wire tree_flush = (cycle_counter[12:0] == 13'h1fff);
    wire leaf_digest_ready = ~(cycle_counter[3] & cycle_counter[1]);
    wire root_ready = ~(cycle_counter[4] & ~cycle_counter[1]);
    wire proof_ready = ~(cycle_counter[5] & cycle_counter[2]);
    wire tag_ready = ~(cycle_counter[6] & ~cycle_counter[2]);

    wire [127:0] phase_bus;
    wire [63:0] active_mask;
    wire [63:0] changed_mask;
    wire [63:0] dirty_mask;

    wire leaf_digest_valid;
    wire [255:0] leaf_digest_data;
    wire [15:0] leaf_digest_sequence;

    wire root_valid;
    wire [255:0] root_data;
    wire [15:0] root_source_sequence;
    wire [15:0] root_tree_ordinal;
    wire [4:0] root_real_leaf_count;

    wire proof_valid;
    wire [15:0] proof_source_sequence;
    wire [15:0] proof_tree_ordinal;
    wire [3:0] proof_leaf_ordinal;
    wire [1:0] proof_level;
    wire proof_sibling_is_left;
    wire [255:0] proof_sibling_digest;

    wire tag_valid;
    wire [255:0] tag_data;
    wire [15:0] tag_source_sequence;
    wire [15:0] tag_tree_ordinal;
    wire [4:0] tag_real_leaf_count;

    wire receipt_valid_out;
    wire receipt_ready_out;
    wire [39:0] receipt_data_out;
    wire [2:0] batch_occupancy_out;
    wire pending_observation_out;
    wire [3:0] leaf_engine_busy_mask;
    wire [3:0] leaf_engine_digest_valid_mask;
    wire [3:0] leaf_engine_block_accept_mask;

    wire [4:0] merkle_leaf_count_out;
    wire merkle_tree_busy_out;
    wire merkle_sha_busy_out;
    wire [7:0] merkle_sha_round_count_out;
    wire merkle_parent_accept_pulse;
    wire root_emit_pulse;
    wire proof_emit_pulse;
    wire inner_digest_valid_out;
    wire merkle_leaf_ready_out;
    wire [1:0] merkle_sha_busy_mask_out;
    wire [1:0] merkle_parent_accept_mask_out;
    wire [1:0] buffer_occupied_mask_out;
    wire buffer_wait_pulse_out;

    wire hmac_busy_out;
    wire hmac_compression_busy_out;
    wire [6:0] hmac_compression_round_count_out;
    wire hmac_compression_accept_pulse_out;
    wire [2:0] hmac_compression_count_out;
    wire hmac_pending_valid_out;
    wire hmac_message_accept_pulse_out;

    // Exact frozen HW-12 core. Keep hierarchy for auditability; functional
    // connectivity is what prevents pruning, not this attribute alone.
    (* keep_hierarchy = "yes" *)
    cosmic_hw12_b1_m2_hmacx1 core (
        .clk(clk), .reset(reset),
        .tick_valid(tick_valid), .tick_ready(tick_ready),
        .stimulus_bus(stimulus_state), .flush(flush),
        .source_sequence_id(source_sequence_id), .tree_flush(tree_flush),

        .phase_bus(phase_bus), .active_mask(active_mask),
        .changed_mask(changed_mask), .dirty_mask(dirty_mask),

        .leaf_digest_valid(leaf_digest_valid), .leaf_digest_ready(leaf_digest_ready),
        .leaf_digest_data(leaf_digest_data), .leaf_digest_sequence(leaf_digest_sequence),

        .root_valid(root_valid), .root_ready(root_ready), .root_data(root_data),
        .root_source_sequence(root_source_sequence), .root_tree_ordinal(root_tree_ordinal),
        .root_real_leaf_count(root_real_leaf_count),

        .proof_valid(proof_valid), .proof_ready(proof_ready),
        .proof_source_sequence(proof_source_sequence), .proof_tree_ordinal(proof_tree_ordinal),
        .proof_leaf_ordinal(proof_leaf_ordinal), .proof_level(proof_level),
        .proof_sibling_is_left(proof_sibling_is_left),
        .proof_sibling_digest(proof_sibling_digest),

        .tag_valid(tag_valid), .tag_ready(tag_ready), .tag_data(tag_data),
        .tag_source_sequence(tag_source_sequence), .tag_tree_ordinal(tag_tree_ordinal),
        .tag_real_leaf_count(tag_real_leaf_count),

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
        .root_emit_pulse(root_emit_pulse), .proof_emit_pulse(proof_emit_pulse),
        .inner_digest_valid_out(inner_digest_valid_out),
        .merkle_leaf_ready_out(merkle_leaf_ready_out),
        .merkle_sha_busy_mask_out(merkle_sha_busy_mask_out),
        .merkle_parent_accept_mask_out(merkle_parent_accept_mask_out),
        .buffer_occupied_mask_out(buffer_occupied_mask_out),
        .buffer_wait_pulse_out(buffer_wait_pulse_out),

        .hmac_busy_out(hmac_busy_out),
        .hmac_compression_busy_out(hmac_compression_busy_out),
        .hmac_compression_round_count_out(hmac_compression_round_count_out),
        .hmac_compression_accept_pulse_out(hmac_compression_accept_pulse_out),
        .hmac_compression_count_out(hmac_compression_count_out),
        .hmac_pending_valid_out(hmac_pending_valid_out),
        .hmac_message_accept_pulse_out(hmac_message_accept_pulse_out)
    );

    // Fold every major output class into a 64-bit event word. Reduction XORs
    // keep every bit of the wide cryptographic/state buses semantically live.
    wire [63:0] observation_word = {
        ^phase_bus,
        ^active_mask,
        ^changed_mask,
        ^dirty_mask,
        receipt_valid_out,
        receipt_ready_out,
        ^receipt_data_out,
        ^batch_occupancy_out,
        pending_observation_out,
        ^leaf_engine_busy_mask,
        ^leaf_engine_digest_valid_mask,
        ^leaf_engine_block_accept_mask,
        leaf_digest_valid,
        ^leaf_digest_data,
        ^leaf_digest_sequence,
        root_valid,
        ^root_data,
        ^root_source_sequence,
        ^root_tree_ordinal,
        ^root_real_leaf_count,
        proof_valid,
        ^proof_source_sequence,
        ^proof_tree_ordinal,
        ^proof_leaf_ordinal,
        ^proof_level,
        proof_sibling_is_left,
        ^proof_sibling_digest,
        tag_valid,
        ^tag_data,
        ^tag_source_sequence,
        ^tag_tree_ordinal,
        ^tag_real_leaf_count,
        ^merkle_leaf_count_out,
        merkle_tree_busy_out,
        merkle_sha_busy_out,
        ^merkle_sha_round_count_out,
        merkle_parent_accept_pulse,
        root_emit_pulse,
        proof_emit_pulse,
        inner_digest_valid_out,
        merkle_leaf_ready_out,
        ^merkle_sha_busy_mask_out,
        ^merkle_parent_accept_mask_out,
        ^buffer_occupied_mask_out,
        buffer_wait_pulse_out,
        hmac_busy_out,
        hmac_compression_busy_out,
        ^hmac_compression_round_count_out,
        hmac_compression_accept_pulse_out,
        ^hmac_compression_count_out,
        hmac_pending_valid_out,
        hmac_message_accept_pulse_out,
        tick_ready,
        tick_valid,
        flush,
        tree_flush,
        leaf_digest_ready,
        root_ready,
        proof_ready,
        tag_ready,
        ^source_sequence_id,
        ^accepted_ticks,
        ^cycle_counter
    };

    wire lfsr_feedback = stimulus_state[511] ^ stimulus_state[509] ^
                         stimulus_state[503] ^ stimulus_state[500];

    always @(posedge clk) begin
        if (reset) begin
            stimulus_state <= 512'h1f123bb5a55a0f0fc33ca5a56969f00fd15ea5e5c001d00dcafe5eed12345678_89abcdef0123456776543210fedcba98a5a55a5ac3c33c3cf0f00f0f55aa55aa;
            cycle_counter <= 32'd0;
            source_sequence_id <= 16'd0;
            tick_valid <= 1'b0;
            checksum <= 64'hc013_1300_f00d_5eed;
            accepted_ticks <= 32'd0;
        end else begin
            cycle_counter <= cycle_counter + 32'd1;

            // Pending tick is held until accepted. A new tick is offered on
            // deterministic nonconstant cycles after the previous one retires.
            if (tick_fire) begin
                tick_valid <= 1'b0;
                accepted_ticks <= accepted_ticks + 32'd1;
                stimulus_state <= {stimulus_state[510:0], lfsr_feedback};
            end else if (!tick_valid && (cycle_counter[1:0] != 2'b11)) begin
                tick_valid <= 1'b1;
            end

            if (tree_flush)
                source_sequence_id <= source_sequence_id + 16'd1;

            // Rotate before XOR so every checksum bit eventually affects the
            // externally visible low byte. This register has no core feedback.
            checksum <= {checksum[62:0], checksum[63]} ^ observation_word ^
                        stimulus_state[63:0] ^ stimulus_state[255:192] ^
                        stimulus_state[511:448];
        end
    end

    assign status = checksum[7:0] ^ accepted_ticks[7:0] ^ cycle_counter[15:8];
endmodule
