`timescale 1ns/1ps

// COSMIC-HW-14/v0.1 physical profile harnesses.
//
// Each harness has the same compact external boundary: clk, reset, status[7:0].
// The validated profile module is instantiated rather than reimplemented.
// Dynamic finite stimulus/control state keeps the execution and output paths
// live. The rolling checksum is observation-only and never feeds a profile.

module cosmic_hw14_core_lite_harness (
    input  wire       clk,
    input  wire       reset,
    output wire [7:0] status
);
    reg [511:0] stimulus_state;
    reg [31:0] cycle_counter;
    reg tick_valid;
    reg [63:0] checksum;
    reg [31:0] accepted_ticks;

    wire tick_ready;
    wire tick_fire = tick_valid && tick_ready;
    wire receipt_ready = ~(cycle_counter[4] & cycle_counter[1]);

    wire [127:0] phase_bus;
    wire [63:0] active_mask;
    wire [63:0] changed_mask;
    wire [63:0] dirty_mask;
    wire receipt_valid;
    wire [39:0] receipt_data;
    wire [2:0] batch_occupancy;
    wire pending_observation;
    wire batch_enqueue_pulse;
    wire batch_dequeue_pulse;

    (* keep_hierarchy = "yes" *)
    cosmic_hw07_mesh64_receipt #(.SPARSE(1), .FIFO_DEPTH(4)) profile (
        .clk(clk), .reset(reset),
        .tick_valid(tick_valid), .tick_ready(tick_ready),
        .stimulus_bus(stimulus_state),
        .phase_bus(phase_bus), .active_mask(active_mask),
        .changed_mask(changed_mask), .dirty_mask(dirty_mask),
        .receipt_valid(receipt_valid), .receipt_ready(receipt_ready),
        .receipt_data(receipt_data), .batch_occupancy(batch_occupancy),
        .pending_observation(pending_observation),
        .batch_enqueue_pulse(batch_enqueue_pulse),
        .batch_dequeue_pulse(batch_dequeue_pulse)
    );

    wire [63:0] observation_word =
        phase_bus[63:0] ^ phase_bus[127:64] ^
        active_mask ^ changed_mask ^ dirty_mask ^
        {24'b0, receipt_data} ^
        {32'b0, accepted_ticks} ^
        {32'b0, cycle_counter} ^
        {54'b0, batch_occupancy, pending_observation,
         batch_enqueue_pulse, batch_dequeue_pulse,
         receipt_valid, receipt_ready, tick_ready, tick_valid};

    wire lfsr_feedback = stimulus_state[511] ^ stimulus_state[509] ^
                         stimulus_state[503] ^ stimulus_state[500];

    always @(posedge clk) begin
        if (reset) begin
            stimulus_state <= 512'h1f123bb5a55a0f0fc33ca5a56969f00fd15ea5e5c001d00dcafe5eed12345678_89abcdef0123456776543210fedcba98a5a55a5ac3c33c3cf0f00f0f55aa55aa;
            cycle_counter <= 32'd0;
            tick_valid <= 1'b0;
            checksum <= 64'hc014_0001_c0de_0040;
            accepted_ticks <= 32'd0;
        end else begin
            cycle_counter <= cycle_counter + 32'd1;
            if (tick_fire) begin
                tick_valid <= 1'b0;
                accepted_ticks <= accepted_ticks + 32'd1;
                stimulus_state <= {stimulus_state[510:0], lfsr_feedback};
            end else if (!tick_valid && (cycle_counter[1:0] != 2'b11)) begin
                tick_valid <= 1'b1;
            end
            checksum <= {checksum[62:0], checksum[63]} ^ observation_word ^
                        stimulus_state[63:0] ^ stimulus_state[255:192] ^
                        stimulus_state[511:448];
        end
    end

    assign status = checksum[7:0] ^ accepted_ticks[7:0] ^ cycle_counter[15:8];
endmodule


module cosmic_hw14_proof_edge_harness (
    input  wire       clk,
    input  wire       reset,
    output wire [7:0] status
);
    reg [511:0] stimulus_state;
    reg [31:0] cycle_counter;
    reg tick_valid;
    reg [63:0] checksum;
    reg [31:0] accepted_ticks;

    wire tick_ready;
    wire tick_fire = tick_valid && tick_ready;
    wire flush = (cycle_counter[11:0] == 12'h7ff);
    wire digest_ready = ~(cycle_counter[5] & cycle_counter[2]);

    wire [127:0] phase_bus;
    wire [63:0] active_mask;
    wire [63:0] changed_mask;
    wire [63:0] dirty_mask;
    wire digest_valid;
    wire [255:0] digest_data;
    wire [15:0] digest_sequence;
    wire [3:0] fill_count_out;
    wire waiting_block_valid_out;
    wire sha_busy;
    wire [6:0] sha_round_count;

    (* keep_hierarchy = "yes" *)
    cosmic_hw08_sparse_receipt_sha256 profile (
        .clk(clk), .reset(reset),
        .tick_valid(tick_valid), .tick_ready(tick_ready),
        .stimulus_bus(stimulus_state), .flush(flush),
        .phase_bus(phase_bus), .active_mask(active_mask),
        .changed_mask(changed_mask), .dirty_mask(dirty_mask),
        .digest_valid(digest_valid), .digest_ready(digest_ready),
        .digest_data(digest_data), .digest_sequence(digest_sequence),
        .fill_count_out(fill_count_out),
        .waiting_block_valid_out(waiting_block_valid_out),
        .sha_busy(sha_busy), .sha_round_count(sha_round_count)
    );

    wire [63:0] observation_word =
        phase_bus[63:0] ^ phase_bus[127:64] ^
        active_mask ^ changed_mask ^ dirty_mask ^
        digest_data[63:0] ^ digest_data[127:64] ^
        digest_data[191:128] ^ digest_data[255:192] ^
        {48'b0, digest_sequence} ^
        {32'b0, accepted_ticks} ^
        {32'b0, cycle_counter} ^
        {46'b0, fill_count_out, waiting_block_valid_out, sha_busy,
         sha_round_count, digest_valid, digest_ready,
         tick_ready, tick_valid, flush};

    wire lfsr_feedback = stimulus_state[511] ^ stimulus_state[509] ^
                         stimulus_state[503] ^ stimulus_state[500];

    always @(posedge clk) begin
        if (reset) begin
            stimulus_state <= 512'h2e234cc6b66b1f1fd44db6b67a7af11fe26fb6f6d112e11edb0f6ffe23456789_9abcdef01234567887654321fedcba09b6b66b6bd4d44d4df1f11f1f66bb66bb;
            cycle_counter <= 32'd0;
            tick_valid <= 1'b0;
            checksum <= 64'hc014_0002_5a25_0001;
            accepted_ticks <= 32'd0;
        end else begin
            cycle_counter <= cycle_counter + 32'd1;
            if (tick_fire) begin
                tick_valid <= 1'b0;
                accepted_ticks <= accepted_ticks + 32'd1;
                stimulus_state <= {stimulus_state[510:0], lfsr_feedback};
            end else if (!tick_valid && (cycle_counter[1:0] != 2'b11)) begin
                tick_valid <= 1'b1;
            end
            checksum <= {checksum[62:0], checksum[63]} ^ observation_word ^
                        stimulus_state[63:0] ^ stimulus_state[255:192] ^
                        stimulus_state[511:448];
        end
    end

    assign status = checksum[7:0] ^ accepted_ticks[7:0] ^ cycle_counter[15:8];
endmodule


module cosmic_hw14_full_proof_harness (
    input  wire       clk,
    input  wire       reset,
    output wire [7:0] status
);
    // Reuse the exact already validated HW-13 compact harness. That harness
    // directly instantiates the frozen HW-12 FULL_PROOF_HMAC profile, keeps all
    // wide inputs dynamic, and folds every major output class into a checksum.
    wire [7:0] inner_status;
    reg [31:0] cycle_counter;
    reg [63:0] wrapper_checksum;

    (* keep_hierarchy = "yes" *)
    cosmic_hw13_ecp5_harness profile_harness (
        .clk(clk), .reset(reset), .status(inner_status)
    );

    always @(posedge clk) begin
        if (reset) begin
            cycle_counter <= 32'd0;
            wrapper_checksum <= 64'hc014_0003_f011_f00d;
        end else begin
            cycle_counter <= cycle_counter + 32'd1;
            wrapper_checksum <= {wrapper_checksum[62:0], wrapper_checksum[63]} ^
                                {56'b0, inner_status} ^
                                {32'b0, cycle_counter};
        end
    end

    assign status = inner_status ^ wrapper_checksum[7:0] ^ cycle_counter[15:8];
endmodule
