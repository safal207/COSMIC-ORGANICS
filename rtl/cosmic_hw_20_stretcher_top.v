`timescale 1ns/1ps

// COSMIC-HW-20/v0.1 "stretcher" candidate.
//
// Two physical iterative SHA-256 engines do the work.  The inherited HW-09
// one-block waiting register is the third, virtual carrier: it overlaps block
// assembly/queueing with the two hashes but does not pretend to be a third
// compute engine.  Receipt semantics and digest retirement remain unchanged.

module cosmic_hw20_stretcher_selftest (
    input  wire         clk,
    input  wire         reset,
    output wire [3:0]   state_debug,
    output wire [15:0]  accepted_tick_count_debug,
    output wire [31:0]  receipt_count_debug,
    output wire [15:0]  digest_count_debug,
    output wire [255:0] last_digest_debug,
    output wire [15:0]  error_flags_debug,
    output wire [3:0]   engine_busy_mask_debug,
    output wire [3:0]   engine_digest_valid_mask_debug,
    output wire [3:0]   engine_block_accept_mask_debug,
    output wire         waiting_block_valid_debug,
    output wire [3:0]   fill_count_debug
);
    localparam [3:0] ST_TICK_A_TO_M = 4'd0;
    localparam [3:0] ST_TICK_M_TO_C = 4'd1;
    localparam [3:0] ST_DRAIN_FULL  = 4'd2;
    localparam [3:0] ST_FLUSH       = 4'd3;
    localparam [3:0] ST_WAIT_FINAL  = 4'd4;
    localparam [3:0] ST_DONE        = 4'd5;

    reg [3:0] state;
    wire tick_valid = (state == ST_TICK_A_TO_M) ||
                      (state == ST_TICK_M_TO_C);
    wire tick_ready;
    wire tick_fire = tick_valid && tick_ready;
    wire flush = (state == ST_FLUSH);

    // Keep the same two authoritative +100 ticks as HW-16/HW-19.  Evolution
    // after the second tick has no execution authority; it only prevents a
    // board synthesis from replacing the 512-bit input with a constant.
    (* keep = "true" *) reg [511:0] stimulus_state;
    wire stimulus_lfsr_feedback = stimulus_state[511] ^ stimulus_state[509] ^
                                  stimulus_state[503] ^ stimulus_state[500];

    wire [127:0] phase_bus;
    wire [63:0] active_mask;
    wire [63:0] changed_mask;
    wire [63:0] dirty_mask;
    wire digest_valid;
    wire [255:0] digest_data;
    wire [15:0] digest_sequence;
    wire [3:0] fill_count;
    wire waiting_block_valid;
    wire [3:0] engine_busy_mask;
    wire [3:0] engine_digest_valid_mask;
    wire [3:0] engine_block_accept_mask;
    wire receipt_valid;
    wire receipt_ready;
    wire [39:0] receipt_data_unused;
    wire [2:0] batch_occupancy_unused;
    wire pending_observation_unused;

    (* keep_hierarchy = "yes" *)
    cosmic_hw09_sparse_receipt_sha256x2 processor (
        .clk(clk),
        .reset(reset),
        .tick_valid(tick_valid),
        .tick_ready(tick_ready),
        .stimulus_bus(stimulus_state),
        .flush(flush),
        .phase_bus(phase_bus),
        .active_mask(active_mask),
        .changed_mask(changed_mask),
        .dirty_mask(dirty_mask),
        .digest_valid(digest_valid),
        .digest_ready(1'b1),
        .digest_data(digest_data),
        .digest_sequence(digest_sequence),
        .fill_count_out(fill_count),
        .waiting_block_valid_out(waiting_block_valid),
        .engine_busy_mask(engine_busy_mask),
        .engine_digest_valid_mask(engine_digest_valid_mask),
        .engine_block_accept_mask(engine_block_accept_mask),
        .receipt_valid_out(receipt_valid),
        .receipt_ready_out(receipt_ready),
        .receipt_data_out(receipt_data_unused),
        .batch_occupancy_out(batch_occupancy_unused),
        .pending_observation_out(pending_observation_unused)
    );

    reg [15:0] accepted_tick_count;
    reg [31:0] receipt_count;
    reg [15:0] digest_count;
    reg [255:0] last_digest;
    reg [15:0] last_digest_sequence;
    reg [15:0] error_flags;

    wire engines_idle = (engine_busy_mask == 4'b0000) &&
                        (engine_digest_valid_mask == 4'b0000);

    assign state_debug = state;
    assign accepted_tick_count_debug = accepted_tick_count;
    assign receipt_count_debug = receipt_count;
    assign digest_count_debug = digest_count;
    assign last_digest_debug = last_digest;
    assign error_flags_debug = error_flags;
    assign engine_busy_mask_debug = engine_busy_mask;
    assign engine_digest_valid_mask_debug = engine_digest_valid_mask;
    assign engine_block_accept_mask_debug = engine_block_accept_mask;
    assign waiting_block_valid_debug = waiting_block_valid;
    assign fill_count_debug = fill_count;

    always @(posedge clk) begin
        if (reset) begin
            state <= ST_TICK_A_TO_M;
            stimulus_state <= {64{8'h64}};
            accepted_tick_count <= 16'd0;
            receipt_count <= 32'd0;
            digest_count <= 16'd0;
            last_digest <= 256'd0;
            last_digest_sequence <= 16'd0;
            error_flags <= 16'd0;
        end else begin
            if (state >= ST_DRAIN_FULL)
                stimulus_state <= {stimulus_state[510:0], stimulus_lfsr_feedback};

            if (tick_fire)
                accepted_tick_count <= accepted_tick_count + 16'd1;
            if (receipt_valid && receipt_ready)
                receipt_count <= receipt_count + 32'd1;
            if (digest_valid) begin
                if (digest_sequence != digest_count)
                    error_flags[5] <= 1'b1;
                digest_count <= digest_count + 16'd1;
                last_digest <= digest_data;
                last_digest_sequence <= digest_sequence;
            end

            case (state)
                ST_TICK_A_TO_M: if (tick_fire) state <= ST_TICK_M_TO_C;
                ST_TICK_M_TO_C: if (tick_fire) state <= ST_DRAIN_FULL;

                ST_DRAIN_FULL: begin
                    if (receipt_count == 32'd128 &&
                        digest_count == 16'd12 &&
                        fill_count == 4'd8 &&
                        !waiting_block_valid && engines_idle)
                        state <= ST_FLUSH;
                end

                ST_FLUSH: state <= ST_WAIT_FINAL;

                ST_WAIT_FINAL: begin
                    if (digest_count == 16'd13 &&
                        fill_count == 4'd0 &&
                        !waiting_block_valid && engines_idle) begin
                        if (accepted_tick_count != 16'd2)
                            error_flags[0] <= 1'b1;
                        if (receipt_count != 32'd128)
                            error_flags[1] <= 1'b1;
                        if (digest_count != 16'd13)
                            error_flags[2] <= 1'b1;
                        if (last_digest_sequence != 16'd12)
                            error_flags[3] <= 1'b1;
                        if (phase_bus != {64{2'b10}})
                            error_flags[4] <= 1'b1;
                        state <= ST_DONE;
                    end
                end

                default: state <= ST_DONE;
            endcase
        end
    end
endmodule


module cosmic_hw20_ulx3s_top (
    input  wire       clk_25mhz,
    input  wire       ftdi_txd,
    output wire       ftdi_rxd,
    output wire [7:0] led
);
    wire clk_10mhz;
    wire pll_locked;
    cosmic_hw16_pll_10mhz pll (
        .clkin(clk_25mhz),
        .clkout0(clk_10mhz),
        .locked(pll_locked)
    );

    reg [1:0] pll_lock_sync = 2'b00;
    reg [4:0] pll_stable_count = 5'd0;
    reg processor_reset = 1'b1;
    (* keep = "true" *) reg [1:0] ftdi_txd_sync = 2'b11;

    always @(posedge clk_10mhz or negedge pll_locked) begin
        if (!pll_locked) begin
            pll_lock_sync <= 2'b00;
            pll_stable_count <= 5'd0;
            processor_reset <= 1'b1;
            ftdi_txd_sync <= 2'b11;
        end else begin
            pll_lock_sync <= {pll_lock_sync[0], 1'b1};
            ftdi_txd_sync <= {ftdi_txd_sync[0], ftdi_txd};
            if (!pll_lock_sync[1]) begin
                pll_stable_count <= 5'd0;
                processor_reset <= 1'b1;
            end else if (pll_stable_count < 5'd16) begin
                pll_stable_count <= pll_stable_count + 5'd1;
                processor_reset <= 1'b1;
            end else begin
                processor_reset <= 1'b0;
            end
        end
    end

    wire [3:0] state;
    wire [15:0] accepted_ticks;
    wire [31:0] receipt_count;
    wire [15:0] digest_count;
    wire [255:0] last_digest;
    wire [15:0] error_flags;
    wire [3:0] busy_mask;
    wire [3:0] digest_valid_mask;
    wire [3:0] accept_mask;
    wire waiting_valid;
    wire [3:0] fill_count;

    cosmic_hw20_stretcher_selftest selftest (
        .clk(clk_10mhz),
        .reset(processor_reset),
        .state_debug(state),
        .accepted_tick_count_debug(accepted_ticks),
        .receipt_count_debug(receipt_count),
        .digest_count_debug(digest_count),
        .last_digest_debug(last_digest),
        .error_flags_debug(error_flags),
        .engine_busy_mask_debug(busy_mask),
        .engine_digest_valid_mask_debug(digest_valid_mask),
        .engine_block_accept_mask_debug(accept_mask),
        .waiting_block_valid_debug(waiting_valid),
        .fill_count_debug(fill_count)
    );

    // The candidate does not define a physical evidence protocol.  This pin is
    // only a live proof-of-preservation reduction, never a UART claim.
    wire digest_fold = ^last_digest;
    assign ftdi_rxd = (state == 4'd5) ? digest_fold : 1'b1;
    assign led = {
        digest_fold,
        busy_mask[1],
        busy_mask[0],
        (digest_count != 16'd0),
        (receipt_count != 32'd0),
        (error_flags != 16'd0),
        (state != 4'd5),
        pll_locked
    };
endmodule
