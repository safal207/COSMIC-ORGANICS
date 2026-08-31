`timescale 1ns/1ps

// COSMIC-HW-21/v0.1 network-pyramid frontier.
//
// The exact HW-09 receipt and SHA-256 commitment contract is expanded through
// binary engine-count layers: 2, 4, 8, and 16 physical iterative cores.  This
// does not claim super-linear work.  It measures where added consumers stop
// reducing latency because the single receipt/assembler lane becomes serial.

module cosmic_hw21_network_pyramid #(
    parameter integer ENGINES = 2
) (
    input  wire         clk,
    input  wire         reset,
    input  wire         tick_valid,
    output wire         tick_ready,
    input  wire [511:0] stimulus_bus,
    input  wire         flush,
    output wire [127:0] phase_bus,
    output wire [63:0]  active_mask,
    output wire [63:0]  changed_mask,
    output wire [63:0]  dirty_mask,
    output wire         digest_valid,
    input  wire         digest_ready,
    output wire [255:0] digest_data,
    output wire [15:0]  digest_sequence,
    output wire [3:0]   fill_count_out,
    output wire         waiting_block_valid_out,
    output wire [15:0]  engine_busy_mask,
    output wire [15:0]  engine_digest_valid_mask,
    output wire [15:0]  engine_block_accept_mask,
    output wire         receipt_valid_out,
    output wire         receipt_ready_out,
    output wire [39:0]  receipt_data_out,
    output wire [2:0]   batch_occupancy_out,
    output wire         pending_observation_out
);
    wire receipt_valid;
    wire receipt_ready;
    wire [39:0] receipt_data;
    wire [2:0] batch_occupancy;
    wire pending_observation;
    wire batch_enqueue_pulse_unused;
    wire batch_dequeue_pulse_unused;

    cosmic_hw07_mesh64_receipt #(.SPARSE(1), .FIFO_DEPTH(4)) receipt_core (
        .clk(clk), .reset(reset),
        .tick_valid(tick_valid), .tick_ready(tick_ready),
        .stimulus_bus(stimulus_bus),
        .phase_bus(phase_bus), .active_mask(active_mask),
        .changed_mask(changed_mask), .dirty_mask(dirty_mask),
        .receipt_valid(receipt_valid), .receipt_ready(receipt_ready),
        .receipt_data(receipt_data), .batch_occupancy(batch_occupancy),
        .pending_observation(pending_observation),
        .batch_enqueue_pulse(batch_enqueue_pulse_unused),
        .batch_dequeue_pulse(batch_dequeue_pulse_unused)
    );

    assign receipt_valid_out = receipt_valid;
    assign receipt_ready_out = receipt_ready;
    assign receipt_data_out = receipt_data;
    assign batch_occupancy_out = batch_occupancy;
    assign pending_observation_out = pending_observation;

    reg [399:0] fill_receipts;
    reg [3:0] fill_count;
    reg [15:0] next_sequence;
    reg waiting_valid;
    reg [511:0] waiting_block;
    reg [15:0] waiting_sequence;

    wire [ENGINES-1:0] sha_block_ready;
    wire [ENGINES-1:0] sha_block_valid;
    wire [ENGINES-1:0] sha_digest_valid;
    wire [ENGINES-1:0] sha_digest_ready;
    wire [ENGINES-1:0] sha_busy;
    wire [ENGINES-1:0] sha_block_accept;
    wire [255:0] sha_digest_data [0:ENGINES-1];
    wire [6:0] sha_round_count_unused [0:ENGINES-1];
    reg [15:0] active_sequence [0:ENGINES-1];
    reg [15:0] next_retire_sequence;

    reg dispatch_found;
    reg [3:0] dispatch_idx;
    reg retire_found;
    reg [3:0] retire_idx;
    reg [255:0] retire_digest;
    integer dispatch_i;
    integer retire_i;
    integer reset_i;

    // Lowest-index selection is stable at every binary expansion layer.
    // The scientific variable is engine count; no average or weighted result
    // may hide a slow layer.
    always @* begin
        dispatch_found = 1'b0;
        dispatch_idx = 4'd0;
        for (dispatch_i = 0; dispatch_i < ENGINES; dispatch_i = dispatch_i + 1) begin
            if (!dispatch_found && sha_block_ready[dispatch_i]) begin
                dispatch_found = 1'b1;
                dispatch_idx = dispatch_i[3:0];
            end
        end
    end

    always @* begin
        retire_found = 1'b0;
        retire_idx = 4'd0;
        retire_digest = 256'd0;
        for (retire_i = 0; retire_i < ENGINES; retire_i = retire_i + 1) begin
            if (!retire_found && sha_digest_valid[retire_i] &&
                active_sequence[retire_i] == next_retire_sequence) begin
                retire_found = 1'b1;
                retire_idx = retire_i[3:0];
                retire_digest = sha_digest_data[retire_i];
            end
        end
    end

    assign digest_valid = retire_found;
    assign digest_data = retire_digest;
    assign digest_sequence = next_retire_sequence;

    genvar g;
    generate
        for (g = 0; g < 16; g = g + 1) begin : GEN_MASK
            if (g < ENGINES) begin : ACTIVE_MASK_BIT
                assign engine_busy_mask[g] = sha_busy[g];
                assign engine_digest_valid_mask[g] = sha_digest_valid[g];
                assign engine_block_accept_mask[g] = sha_block_accept[g];
            end else begin : ZERO_MASK_BIT
                assign engine_busy_mask[g] = 1'b0;
                assign engine_digest_valid_mask[g] = 1'b0;
                assign engine_block_accept_mask[g] = 1'b0;
            end
        end

        for (g = 0; g < ENGINES; g = g + 1) begin : GEN_SHA
            assign sha_block_valid[g] = waiting_valid && dispatch_found &&
                                        (dispatch_idx == g[3:0]);
            assign sha_block_accept[g] = sha_block_valid[g] && sha_block_ready[g];
            assign sha_digest_ready[g] = digest_valid && digest_ready &&
                                         (retire_idx == g[3:0]);
            cosmic_sha256_iterative sha (
                .clk(clk), .reset(reset),
                .block_valid(sha_block_valid[g]),
                .block_ready(sha_block_ready[g]),
                .block_data(waiting_block),
                .digest_valid(sha_digest_valid[g]),
                .digest_ready(sha_digest_ready[g]),
                .digest_data(sha_digest_data[g]),
                .round_count(sha_round_count_unused[g]),
                .busy(sha_busy[g])
            );
        end
    endgenerate

    wire receipt_fire = receipt_valid && receipt_ready;
    wire can_complete_direct = (fill_count != 4'd9) || !waiting_valid || dispatch_found;
    assign receipt_ready = can_complete_direct && !(flush && fill_count != 0);
    assign fill_count_out = fill_count;
    assign waiting_block_valid_out = waiting_valid;

    reg [399:0] slots_next;
    reg [15:0] domain_partial;
    reg [511:0] new_block;

    always @* begin
        slots_next = fill_receipts;
        if (receipt_fire)
            slots_next[399-(fill_count*40) -: 40] = receipt_data;
        domain_partial = 16'h4340 | {12'b0, fill_count};
        new_block = 512'd0;
        if (receipt_fire && fill_count == 4'd9)
            new_block = {16'h434f, next_sequence, slots_next, 8'h80, 8'h00, 64'd432};
        else if (flush && fill_count != 0)
            new_block = {domain_partial, next_sequence, fill_receipts, 8'h80, 8'h00, 64'd432};
    end

    always @(posedge clk) begin
        if (reset) begin
            fill_receipts <= 400'd0;
            fill_count <= 4'd0;
            next_sequence <= 16'd0;
            waiting_valid <= 1'b0;
            waiting_block <= 512'd0;
            waiting_sequence <= 16'd0;
            next_retire_sequence <= 16'd0;
            for (reset_i = 0; reset_i < ENGINES; reset_i = reset_i + 1)
                active_sequence[reset_i] <= 16'd0;
        end else begin
            if (waiting_valid && dispatch_found) begin
                waiting_valid <= 1'b0;
                active_sequence[dispatch_idx] <= waiting_sequence;
            end
            if (digest_valid && digest_ready)
                next_retire_sequence <= next_retire_sequence + 16'd1;
            if (receipt_fire) begin
                if (fill_count == 4'd9) begin
                    waiting_block <= new_block;
                    waiting_sequence <= next_sequence;
                    waiting_valid <= 1'b1;
                    next_sequence <= next_sequence + 16'd1;
                    fill_receipts <= 400'd0;
                    fill_count <= 4'd0;
                end else begin
                    fill_receipts <= slots_next;
                    fill_count <= fill_count + 4'd1;
                end
            end
            if (flush && fill_count != 0 && !waiting_valid) begin
                waiting_block <= new_block;
                waiting_sequence <= next_sequence;
                waiting_valid <= 1'b1;
                next_sequence <= next_sequence + 16'd1;
                fill_receipts <= 400'd0;
                fill_count <= 4'd0;
            end
        end
    end
endmodule

module cosmic_hw21_network_pyramid_x2 (
    input wire clk, input wire reset, input wire tick_valid, output wire tick_ready,
    input wire [511:0] stimulus_bus, input wire flush,
    output wire [127:0] phase_bus, output wire [63:0] active_mask,
    output wire [63:0] changed_mask, output wire [63:0] dirty_mask,
    output wire digest_valid, input wire digest_ready, output wire [255:0] digest_data,
    output wire [15:0] digest_sequence, output wire [3:0] fill_count_out,
    output wire waiting_block_valid_out, output wire [15:0] engine_busy_mask,
    output wire [15:0] engine_digest_valid_mask, output wire [15:0] engine_block_accept_mask,
    output wire receipt_valid_out, output wire receipt_ready_out, output wire [39:0] receipt_data_out,
    output wire [2:0] batch_occupancy_out, output wire pending_observation_out
);
    cosmic_hw21_network_pyramid #(.ENGINES(2)) core (.*);
endmodule

module cosmic_hw21_network_pyramid_x4 (
    input wire clk, input wire reset, input wire tick_valid, output wire tick_ready,
    input wire [511:0] stimulus_bus, input wire flush,
    output wire [127:0] phase_bus, output wire [63:0] active_mask,
    output wire [63:0] changed_mask, output wire [63:0] dirty_mask,
    output wire digest_valid, input wire digest_ready, output wire [255:0] digest_data,
    output wire [15:0] digest_sequence, output wire [3:0] fill_count_out,
    output wire waiting_block_valid_out, output wire [15:0] engine_busy_mask,
    output wire [15:0] engine_digest_valid_mask, output wire [15:0] engine_block_accept_mask,
    output wire receipt_valid_out, output wire receipt_ready_out, output wire [39:0] receipt_data_out,
    output wire [2:0] batch_occupancy_out, output wire pending_observation_out
);
    cosmic_hw21_network_pyramid #(.ENGINES(4)) core (.*);
endmodule

module cosmic_hw21_network_pyramid_x8 (
    input wire clk, input wire reset, input wire tick_valid, output wire tick_ready,
    input wire [511:0] stimulus_bus, input wire flush,
    output wire [127:0] phase_bus, output wire [63:0] active_mask,
    output wire [63:0] changed_mask, output wire [63:0] dirty_mask,
    output wire digest_valid, input wire digest_ready, output wire [255:0] digest_data,
    output wire [15:0] digest_sequence, output wire [3:0] fill_count_out,
    output wire waiting_block_valid_out, output wire [15:0] engine_busy_mask,
    output wire [15:0] engine_digest_valid_mask, output wire [15:0] engine_block_accept_mask,
    output wire receipt_valid_out, output wire receipt_ready_out, output wire [39:0] receipt_data_out,
    output wire [2:0] batch_occupancy_out, output wire pending_observation_out
);
    cosmic_hw21_network_pyramid #(.ENGINES(8)) core (.*);
endmodule

module cosmic_hw21_network_pyramid_x16 (
    input wire clk, input wire reset, input wire tick_valid, output wire tick_ready,
    input wire [511:0] stimulus_bus, input wire flush,
    output wire [127:0] phase_bus, output wire [63:0] active_mask,
    output wire [63:0] changed_mask, output wire [63:0] dirty_mask,
    output wire digest_valid, input wire digest_ready, output wire [255:0] digest_data,
    output wire [15:0] digest_sequence, output wire [3:0] fill_count_out,
    output wire waiting_block_valid_out, output wire [15:0] engine_busy_mask,
    output wire [15:0] engine_digest_valid_mask, output wire [15:0] engine_block_accept_mask,
    output wire receipt_valid_out, output wire receipt_ready_out, output wire [39:0] receipt_data_out,
    output wire [2:0] batch_occupancy_out, output wire pending_observation_out
);
    cosmic_hw21_network_pyramid #(.ENGINES(16)) core (.*);
endmodule
