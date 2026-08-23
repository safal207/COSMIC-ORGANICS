`timescale 1ns/1ps

// COSMIC-HW-07/v0.1 transition-receipt observer.
//
// This module deliberately wraps the already validated COSMIC-HW-06 mesh
// instead of re-implementing the A/M/C transition law.  The receipt path has
// no signal feeding back into the transition decision or sparse dirty-frontier
// computation.  Its only authority over execution is the preregistered
// valid/ready backpressure applied BEFORE an authoritative tick commit.
//
// Frozen receipt layout, MSB -> LSB:
//   [39:24] logical_tick
//   [23:18] site_id
//   [17:16] phase_before
//   [15:14] phase_after
//   [13:6]  signed stimulus_s100 bits
//   [5:0]   ordinal_in_batch
//
// A committed non-empty tick is stored as one 848-bit transition snapshot:
// tick(16) + changed_mask(64) + pre_state(128) + post_state(128) + stimulus(512).
// The finite queue contains four such batches.  Serialization is one receipt
// per cycle in ascending site order.  Empty transition ticks release their
// pre-commit reservation without entering the queue.

module cosmic_hw07_mesh64_receipt #(
    parameter integer SPARSE = 0,
    parameter integer FIFO_DEPTH = 4
) (
    input  wire         clk,
    input  wire         reset,
    input  wire         tick_valid,
    output wire         tick_ready,
    input  wire [511:0] stimulus_bus,

    output wire [127:0] phase_bus,
    output wire [63:0]  active_mask,
    output wire [63:0]  changed_mask,
    output wire [63:0]  dirty_mask,

    output wire         receipt_valid,
    input  wire         receipt_ready,
    output wire [39:0]  receipt_data,

    output wire [2:0]   batch_occupancy,
    output wire         pending_observation,
    output reg          batch_enqueue_pulse,
    output reg          batch_dequeue_pulse
);
    wire core_tick_en;
    wire [127:0] core_phase_bus;
    wire [63:0] core_active_mask;
    wire [63:0] core_changed_mask;
    wire [63:0] core_dirty_mask;

    // One accepted tick remains pending for one physical cycle so that the
    // wrapper can observe the registered post-commit state and changed mask.
    reg          pending_valid;
    reg [15:0]   pending_tick;
    reg [127:0]  pending_pre_phase;
    reg [511:0]  pending_stimulus;
    reg [15:0]   logical_tick;

    // Four-entry frozen batch FIFO.  The arrays below are exactly the
    // preregistered 848 snapshot bits per stored transition batch.
    reg [15:0]  fifo_tick    [0:FIFO_DEPTH-1];
    reg [63:0]  fifo_changed [0:FIFO_DEPTH-1];
    reg [127:0] fifo_pre     [0:FIFO_DEPTH-1];
    reg [127:0] fifo_post    [0:FIFO_DEPTH-1];
    reg [511:0] fifo_stim    [0:FIFO_DEPTH-1];

    reg [1:0] wr_ptr;
    reg [1:0] rd_ptr;
    reg [2:0] fifo_count;
    reg [5:0] head_ordinal;

    reg       selected_found_comb;
    reg [5:0] selected_site_comb;
    reg [63:0] selected_bit_comb;
    integer k;

    wire [2:0] reserved_count;
    wire enqueue_batch;
    wire receipt_fire;
    wire last_receipt;
    wire [1:0] receipt_phase_before;
    wire [1:0] receipt_phase_after;
    wire [7:0] receipt_stimulus_bits;

    assign reserved_count = fifo_count + (pending_valid ? 3'd1 : 3'd0);
    assign batch_occupancy = reserved_count;
    assign pending_observation = pending_valid;

    // The pre-commit reservation rule is intentionally conservative.  A tick
    // is accepted only while one complete batch slot is available for it.
    assign tick_ready = (reserved_count < FIFO_DEPTH);
    assign core_tick_en = tick_valid && tick_ready;

    cosmic_hw06_mesh64 #(.SPARSE(SPARSE)) core (
        .clk(clk),
        .reset(reset),
        .tick_en(core_tick_en),
        .stimulus_bus(stimulus_bus),
        .phase_bus(core_phase_bus),
        .active_mask(core_active_mask),
        .changed_mask(core_changed_mask),
        .dirty_mask(core_dirty_mask)
    );

    assign phase_bus = core_phase_bus;
    assign active_mask = core_active_mask;
    assign changed_mask = core_changed_mask;
    assign dirty_mask = core_dirty_mask;

    // Ascending-site selector over the current head batch.
    always @* begin
        selected_found_comb = 1'b0;
        selected_site_comb = 6'd0;
        selected_bit_comb = 64'b0;
        if (fifo_count != 0) begin
            for (k = 0; k < 64; k = k + 1) begin
                if (!selected_found_comb && fifo_changed[rd_ptr][k]) begin
                    selected_found_comb = 1'b1;
                    selected_site_comb = k[5:0];
                    selected_bit_comb = (64'b1 << k);
                end
            end
        end
    end

    assign receipt_valid = (fifo_count != 0) && selected_found_comb;
    assign receipt_phase_before =
        (fifo_pre[rd_ptr] >> (selected_site_comb * 2)) & 2'b11;
    assign receipt_phase_after =
        (fifo_post[rd_ptr] >> (selected_site_comb * 2)) & 2'b11;
    assign receipt_stimulus_bits =
        (fifo_stim[rd_ptr] >> (selected_site_comb * 8)) & 8'hff;
    assign receipt_data = {
        fifo_tick[rd_ptr],
        selected_site_comb,
        receipt_phase_before,
        receipt_phase_after,
        receipt_stimulus_bits,
        head_ordinal
    };

    assign enqueue_batch = pending_valid && (core_changed_mask != 64'b0);
    assign receipt_fire = receipt_valid && receipt_ready;
    assign last_receipt = receipt_valid &&
                          (fifo_changed[rd_ptr] == selected_bit_comb);

    always @(posedge clk) begin
        if (reset) begin
            pending_valid <= 1'b0;
            pending_tick <= 16'b0;
            pending_pre_phase <= 128'b0;
            pending_stimulus <= 512'b0;
            logical_tick <= 16'b0;

            wr_ptr <= 2'b0;
            rd_ptr <= 2'b0;
            fifo_count <= 3'b0;
            head_ordinal <= 6'b0;
            batch_enqueue_pulse <= 1'b0;
            batch_dequeue_pulse <= 1'b0;

            for (k = 0; k < FIFO_DEPTH; k = k + 1) begin
                fifo_tick[k] <= 16'b0;
                fifo_changed[k] <= 64'b0;
                fifo_pre[k] <= 128'b0;
                fifo_post[k] <= 128'b0;
                fifo_stim[k] <= 512'b0;
            end
        end else begin
            batch_enqueue_pulse <= 1'b0;
            batch_dequeue_pulse <= 1'b0;

            // Finalize the previously accepted tick strictly from the
            // authoritative registered HW-06 result now visible at the wrapper.
            if (enqueue_batch) begin
                fifo_tick[wr_ptr] <= pending_tick;
                fifo_changed[wr_ptr] <= core_changed_mask;
                fifo_pre[wr_ptr] <= pending_pre_phase;
                fifo_post[wr_ptr] <= core_phase_bus;
                fifo_stim[wr_ptr] <= pending_stimulus;
                wr_ptr <= wr_ptr + 2'd1;
                batch_enqueue_pulse <= 1'b1;
            end

            // Consume at most one receipt per physical cycle.
            if (receipt_fire) begin
                if (last_receipt) begin
                    fifo_changed[rd_ptr] <= 64'b0;
                    rd_ptr <= rd_ptr + 2'd1;
                    head_ordinal <= 6'b0;
                    batch_dequeue_pulse <= 1'b1;
                end else begin
                    fifo_changed[rd_ptr] <= fifo_changed[rd_ptr] & ~selected_bit_comb;
                    head_ordinal <= head_ordinal + 6'd1;
                end
            end

            // Count stored non-empty batches.  A pending observation is a
            // reservation and is accounted separately in reserved_count.
            case ({enqueue_batch, (receipt_fire && last_receipt)})
                2'b10: fifo_count <= fifo_count + 3'd1;
                2'b01: fifo_count <= fifo_count - 3'd1;
                default: fifo_count <= fifo_count;
            endcase

            // Capture the next accepted logical tick.  If no tick is accepted,
            // the previous pending observation has just been finalized/released.
            if (core_tick_en) begin
                pending_valid <= 1'b1;
                pending_tick <= logical_tick + 16'd1;
                pending_pre_phase <= core_phase_bus;
                pending_stimulus <= stimulus_bus;
                logical_tick <= logical_tick + 16'd1;
            end else begin
                pending_valid <= 1'b0;
            end
        end
    end
endmodule


module cosmic_hw07_dense_receipt_mesh64 (
    input  wire         clk,
    input  wire         reset,
    input  wire         tick_valid,
    output wire         tick_ready,
    input  wire [511:0] stimulus_bus,
    output wire [127:0] phase_bus,
    output wire [63:0]  active_mask,
    output wire [63:0]  changed_mask,
    output wire [63:0]  dirty_mask,
    output wire         receipt_valid,
    input  wire         receipt_ready,
    output wire [39:0]  receipt_data,
    output wire [2:0]   batch_occupancy,
    output wire         pending_observation,
    output wire         batch_enqueue_pulse,
    output wire         batch_dequeue_pulse
);
    cosmic_hw07_mesh64_receipt #(.SPARSE(0), .FIFO_DEPTH(4)) core (
        .clk(clk), .reset(reset),
        .tick_valid(tick_valid), .tick_ready(tick_ready),
        .stimulus_bus(stimulus_bus),
        .phase_bus(phase_bus), .active_mask(active_mask),
        .changed_mask(changed_mask), .dirty_mask(dirty_mask),
        .receipt_valid(receipt_valid), .receipt_ready(receipt_ready),
        .receipt_data(receipt_data), .batch_occupancy(batch_occupancy),
        .pending_observation(pending_observation),
        .batch_enqueue_pulse(batch_enqueue_pulse),
        .batch_dequeue_pulse(batch_dequeue_pulse)
    );
endmodule


module cosmic_hw07_sparse_receipt_mesh64 (
    input  wire         clk,
    input  wire         reset,
    input  wire         tick_valid,
    output wire         tick_ready,
    input  wire [511:0] stimulus_bus,
    output wire [127:0] phase_bus,
    output wire [63:0]  active_mask,
    output wire [63:0]  changed_mask,
    output wire [63:0]  dirty_mask,
    output wire         receipt_valid,
    input  wire         receipt_ready,
    output wire [39:0]  receipt_data,
    output wire [2:0]   batch_occupancy,
    output wire         pending_observation,
    output wire         batch_enqueue_pulse,
    output wire         batch_dequeue_pulse
);
    cosmic_hw07_mesh64_receipt #(.SPARSE(1), .FIFO_DEPTH(4)) core (
        .clk(clk), .reset(reset),
        .tick_valid(tick_valid), .tick_ready(tick_ready),
        .stimulus_bus(stimulus_bus),
        .phase_bus(phase_bus), .active_mask(active_mask),
        .changed_mask(changed_mask), .dirty_mask(dirty_mask),
        .receipt_valid(receipt_valid), .receipt_ready(receipt_ready),
        .receipt_data(receipt_data), .batch_occupancy(batch_occupancy),
        .pending_observation(pending_observation),
        .batch_enqueue_pulse(batch_enqueue_pulse),
        .batch_dequeue_pulse(batch_dequeue_pulse)
    );
endmodule
