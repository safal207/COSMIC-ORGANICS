`timescale 1ns/1ps

// COSMIC-BOARD-01A/v0.1
//
// Board integration only. The selected processor profile is instantiated
// unchanged. The board engine runs one deterministic 64-tick workload and
// emits lossless digest frames followed by a finite summary frame. Serial and
// LED paths are observation-only and never feed transition authority.

module cosmic_board_01_uart_tx #(
    parameter integer DIVISOR = 87
) (
    input  wire       clk,
    input  wire       reset,
    input  wire       byte_valid,
    output wire       byte_ready,
    input  wire [7:0] byte_data,
    output wire       tx
);
    reg [9:0] shift_reg;
    reg [15:0] divisor_count;
    reg [3:0] bit_count;
    reg busy;

    assign byte_ready = !busy;
    assign tx = busy ? shift_reg[0] : 1'b1;

    always @(posedge clk) begin
        if (reset) begin
            shift_reg <= 10'h3ff;
            divisor_count <= 16'd0;
            bit_count <= 4'd0;
            busy <= 1'b0;
        end else begin
            if (byte_valid && byte_ready) begin
                // Start bit, eight data bits LSB first, stop bit.
                shift_reg <= {1'b1, byte_data, 1'b0};
                divisor_count <= DIVISOR - 1;
                bit_count <= 4'd0;
                busy <= 1'b1;
            end else if (busy) begin
                if (divisor_count == 0) begin
                    if (bit_count == 4'd9) begin
                        busy <= 1'b0;
                        shift_reg <= 10'h3ff;
                    end else begin
                        shift_reg <= {1'b1, shift_reg[9:1]};
                        divisor_count <= DIVISOR - 1;
                        bit_count <= bit_count + 4'd1;
                    end
                end else begin
                    divisor_count <= divisor_count - 16'd1;
                end
            end
        end
    end
endmodule


module cosmic_board_01_engine #(
    parameter integer QUIET_CYCLES = 64
) (
    input  wire         clk,
    input  wire         reset,
    output wire         byte_valid,
    input  wire         byte_ready,
    output reg  [7:0]   byte_data,
    output reg          done,
    output wire [7:0]   status,
    output wire [15:0]  accepted_ticks_out,
    output wire [31:0]  receipt_count_out,
    output wire [15:0]  digest_count_out,
    output wire [127:0] final_phase_out,
    output wire [63:0]  final_active_out,
    output wire [63:0]  final_changed_out,
    output wire [63:0]  final_dirty_out
);
    localparam [2:0] ST_RUN        = 3'd0;
    localparam [2:0] ST_OBSERVE    = 3'd1;
    localparam [2:0] ST_DRAIN_PRE  = 3'd2;
    localparam [2:0] ST_FLUSH      = 3'd3;
    localparam [2:0] ST_DRAIN_POST = 3'd4;
    localparam [2:0] ST_SUMMARY    = 3'd5;
    localparam [2:0] ST_DONE       = 3'd6;

    localparam [1:0] TX_NONE    = 2'd0;
    localparam [1:0] TX_DIGEST  = 2'd1;
    localparam [1:0] TX_SUMMARY = 2'd2;

    localparam [511:0] INITIAL_STIMULUS =
        512'h1f123bb5a55a0f0fc33ca5a56969f00fd15ea5e5c001d00dcafe5eed12345678_89abcdef0123456776543210fedcba98a5a55a5ac3c33c3cf0f00f0f55aa55aa;

    reg [2:0] state;
    reg tick_valid;
    reg [511:0] stimulus_state;
    reg [15:0] accepted_ticks;
    reg [31:0] receipt_count;
    reg [15:0] digest_count;
    reg [15:0] quiet_count;
    reg [3:0] last_fill_count;
    reg sequence_error;

    reg [127:0] final_phase;
    reg [63:0] final_active;
    reg [63:0] final_changed;
    reg [63:0] final_dirty;

    reg [1:0] tx_kind;
    reg [6:0] tx_index;
    reg [15:0] digest_sequence_hold;
    reg [255:0] digest_data_hold;

    wire tick_ready;
    wire tick_fire = tick_valid && tick_ready;
    wire flush = (state == ST_FLUSH);

    wire [127:0] phase_bus;
    wire [63:0] active_mask;
    wire [63:0] changed_mask;
    wire [63:0] dirty_mask;
    wire digest_valid;
    wire digest_ready;
    wire [255:0] digest_data;
    wire [15:0] digest_sequence;
    wire [3:0] fill_count;
    wire waiting_block_valid;
    wire sha_busy;
    wire [6:0] sha_round_count;

    // This is the exact frozen HW-15 selected profile. No board signal enters
    // its transition law other than the deterministic stimulus and reset/clock.
    (* keep_hierarchy = "yes" *)
    cosmic_hw08_sparse_receipt_sha256 profile (
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
        .digest_ready(digest_ready),
        .digest_data(digest_data),
        .digest_sequence(digest_sequence),
        .fill_count_out(fill_count),
        .waiting_block_valid_out(waiting_block_valid),
        .sha_busy(sha_busy),
        .sha_round_count(sha_round_count)
    );

    assign digest_ready = (tx_kind == TX_NONE) &&
                          (state != ST_SUMMARY) && (state != ST_DONE);
    wire digest_fire = digest_valid && digest_ready;
    assign byte_valid = (tx_kind != TX_NONE);
    wire byte_fire = byte_valid && byte_ready;

    wire lfsr_feedback = stimulus_state[511] ^ stimulus_state[509] ^
                         stimulus_state[503] ^ stimulus_state[500];

    wire terminal_ok = !sequence_error;
    wire [7:0] terminal_status = terminal_ok ? 8'ha5 : 8'he1;

    function [6:0] popcount64;
        input [63:0] value;
        integer i;
        begin
            popcount64 = 7'd0;
            for (i = 0; i < 64; i = i + 1)
                popcount64 = popcount64 + value[i];
        end
    endfunction

    function [7:0] digest_frame_checksum;
        input [15:0] sequence_value;
        input [255:0] digest_value;
        integer i;
        reg [7:0] checksum;
        begin
            checksum = 8'h01 ^ 8'h00 ^ 8'h22 ^
                       sequence_value[15:8] ^ sequence_value[7:0];
            for (i = 0; i < 32; i = i + 1)
                checksum = checksum ^ digest_value[255-(i*8) -: 8];
            digest_frame_checksum = checksum;
        end
    endfunction

    function [7:0] summary_frame_checksum;
        input [15:0] ticks_value;
        input [127:0] phase_value;
        input [63:0] active_value;
        input [63:0] changed_value;
        input [63:0] dirty_value;
        input [31:0] receipts_value;
        input [15:0] digests_value;
        input [7:0] final_status_value;
        integer i;
        reg [7:0] checksum;
        begin
            checksum = 8'h02 ^ 8'h00 ^ 8'h33 ^ 8'h01 ^ 8'h01 ^
                       ticks_value[15:8] ^ ticks_value[7:0];
            for (i = 0; i < 16; i = i + 1)
                checksum = checksum ^ phase_value[127-(i*8) -: 8];
            for (i = 0; i < 8; i = i + 1) begin
                checksum = checksum ^ active_value[63-(i*8) -: 8];
                checksum = checksum ^ changed_value[63-(i*8) -: 8];
                checksum = checksum ^ dirty_value[63-(i*8) -: 8];
            end
            checksum = checksum ^ receipts_value[31:24] ^
                       receipts_value[23:16] ^ receipts_value[15:8] ^
                       receipts_value[7:0] ^ digests_value[15:8] ^
                       digests_value[7:0] ^ final_status_value;
            summary_frame_checksum = checksum;
        end
    endfunction

    always @* begin
        byte_data = 8'h00;
        if (tx_kind == TX_DIGEST) begin
            case (tx_index)
                7'd0: byte_data = 8'h43; // C
                7'd1: byte_data = 8'h44; // D
                7'd2: byte_data = 8'h01;
                7'd3: byte_data = 8'h00;
                7'd4: byte_data = 8'h22; // 34-byte payload
                7'd5: byte_data = digest_sequence_hold[15:8];
                7'd6: byte_data = digest_sequence_hold[7:0];
                7'd39: byte_data = digest_frame_checksum(
                    digest_sequence_hold, digest_data_hold
                );
                default: begin
                    if (tx_index >= 7'd7 && tx_index <= 7'd38)
                        byte_data = digest_data_hold[
                            255-((tx_index-7)*8) -: 8
                        ];
                end
            endcase
        end else if (tx_kind == TX_SUMMARY) begin
            case (tx_index)
                7'd0: byte_data = 8'h43; // C
                7'd1: byte_data = 8'h44; // D
                7'd2: byte_data = 8'h02;
                7'd3: byte_data = 8'h00;
                7'd4: byte_data = 8'h33; // 51-byte payload
                7'd5: byte_data = 8'h01; // protocol version
                7'd6: byte_data = 8'h01; // PROOF_EDGE_SHA1_NODSP
                7'd7: byte_data = accepted_ticks[15:8];
                7'd8: byte_data = accepted_ticks[7:0];
                7'd49: byte_data = receipt_count[31:24];
                7'd50: byte_data = receipt_count[23:16];
                7'd51: byte_data = receipt_count[15:8];
                7'd52: byte_data = receipt_count[7:0];
                7'd53: byte_data = digest_count[15:8];
                7'd54: byte_data = digest_count[7:0];
                7'd55: byte_data = terminal_status;
                7'd56: byte_data = summary_frame_checksum(
                    accepted_ticks, final_phase, final_active,
                    final_changed, final_dirty, receipt_count,
                    digest_count, terminal_status
                );
                default: begin
                    if (tx_index >= 7'd9 && tx_index <= 7'd24)
                        byte_data = final_phase[127-((tx_index-9)*8) -: 8];
                    else if (tx_index >= 7'd25 && tx_index <= 7'd32)
                        byte_data = final_active[63-((tx_index-25)*8) -: 8];
                    else if (tx_index >= 7'd33 && tx_index <= 7'd40)
                        byte_data = final_changed[63-((tx_index-33)*8) -: 8];
                    else if (tx_index >= 7'd41 && tx_index <= 7'd48)
                        byte_data = final_dirty[63-((tx_index-41)*8) -: 8];
                end
            endcase
        end
    end

    wire public_pipeline_idle =
        !waiting_block_valid && !sha_busy && !digest_valid &&
        (tx_kind == TX_NONE) && byte_ready;

    always @(posedge clk) begin
        if (reset) begin
            state <= ST_RUN;
            tick_valid <= 1'b0;
            stimulus_state <= INITIAL_STIMULUS;
            accepted_ticks <= 16'd0;
            receipt_count <= 32'd0;
            digest_count <= 16'd0;
            quiet_count <= 16'd0;
            last_fill_count <= 4'd0;
            sequence_error <= 1'b0;
            final_phase <= 128'd0;
            final_active <= 64'd0;
            final_changed <= 64'd0;
            final_dirty <= 64'd0;
            tx_kind <= TX_NONE;
            tx_index <= 7'd0;
            digest_sequence_hold <= 16'd0;
            digest_data_hold <= 256'd0;
            done <= 1'b0;
        end else begin
            // Retire one byte from the current frame.
            if (byte_fire) begin
                if ((tx_kind == TX_DIGEST && tx_index == 7'd39) ||
                    (tx_kind == TX_SUMMARY && tx_index == 7'd56)) begin
                    tx_kind <= TX_NONE;
                    tx_index <= 7'd0;
                end else begin
                    tx_index <= tx_index + 7'd1;
                end
            end

            // A digest is buffered as one finite UART frame. Backpressure from
            // this single slot propagates only through the selected profile's
            // already-authoritative valid/ready boundary.
            if (digest_fire) begin
                if (digest_sequence != digest_count)
                    sequence_error <= 1'b1;
                digest_sequence_hold <= digest_sequence;
                digest_data_hold <= digest_data;
                digest_count <= digest_count + 16'd1;
                tx_kind <= TX_DIGEST;
                tx_index <= 7'd0;
            end

            case (state)
                ST_RUN: begin
                    quiet_count <= 16'd0;
                    if (accepted_ticks < 16'd64) begin
                        if (!tick_valid)
                            tick_valid <= 1'b1;
                        if (tick_fire) begin
                            tick_valid <= 1'b0;
                            accepted_ticks <= accepted_ticks + 16'd1;
                            stimulus_state <= {
                                stimulus_state[510:0], lfsr_feedback
                            };
                            state <= ST_OBSERVE;
                        end
                    end else begin
                        tick_valid <= 1'b0;
                        last_fill_count <= fill_count;
                        state <= ST_DRAIN_PRE;
                    end
                end

                ST_OBSERVE: begin
                    tick_valid <= 1'b0;
                    receipt_count <= receipt_count + popcount64(changed_mask);
                    if (accepted_ticks == 16'd64) begin
                        final_phase <= phase_bus;
                        final_active <= active_mask;
                        final_changed <= changed_mask;
                        final_dirty <= dirty_mask;
                        last_fill_count <= fill_count;
                        quiet_count <= 16'd0;
                        state <= ST_DRAIN_PRE;
                    end else begin
                        state <= ST_RUN;
                    end
                end

                ST_DRAIN_PRE: begin
                    tick_valid <= 1'b0;
                    if (!public_pipeline_idle) begin
                        quiet_count <= 16'd0;
                        last_fill_count <= fill_count;
                    end else if (fill_count != last_fill_count) begin
                        quiet_count <= 16'd0;
                        last_fill_count <= fill_count;
                    end else if (quiet_count >= QUIET_CYCLES-1) begin
                        quiet_count <= 16'd0;
                        if (fill_count != 0)
                            state <= ST_FLUSH;
                        else
                            state <= ST_DRAIN_POST;
                    end else begin
                        quiet_count <= quiet_count + 16'd1;
                    end
                end

                ST_FLUSH: begin
                    // `flush` is high for the complete cycle ending at this
                    // edge, then the post-flush drain begins.
                    tick_valid <= 1'b0;
                    quiet_count <= 16'd0;
                    last_fill_count <= fill_count;
                    state <= ST_DRAIN_POST;
                end

                ST_DRAIN_POST: begin
                    tick_valid <= 1'b0;
                    if (!public_pipeline_idle || fill_count != 0) begin
                        quiet_count <= 16'd0;
                        last_fill_count <= fill_count;
                    end else if (quiet_count >= QUIET_CYCLES-1) begin
                        quiet_count <= 16'd0;
                        tx_kind <= TX_SUMMARY;
                        tx_index <= 7'd0;
                        state <= ST_SUMMARY;
                    end else begin
                        quiet_count <= quiet_count + 16'd1;
                    end
                end

                ST_SUMMARY: begin
                    tick_valid <= 1'b0;
                    if (byte_fire && tx_index == 7'd56) begin
                        done <= 1'b1;
                        state <= ST_DONE;
                    end
                end

                default: begin
                    tick_valid <= 1'b0;
                    done <= 1'b1;
                    state <= ST_DONE;
                end
            endcase
        end
    end

    assign status = {
        done,
        sequence_error,
        (tx_kind != TX_NONE),
        sha_busy,
        waiting_block_valid,
        fill_count[2:0]
    };
    assign accepted_ticks_out = accepted_ticks;
    assign receipt_count_out = receipt_count;
    assign digest_count_out = digest_count;
    assign final_phase_out = final_phase;
    assign final_active_out = final_active;
    assign final_changed_out = final_changed;
    assign final_dirty_out = final_dirty;
endmodule


module cosmic_board_01_ulx3s (
    input  wire       clk_25mhz,
    input  wire       btn_reset_start,
    input  wire       ftdi_txd,
    output wire       ftdi_rxd,
    output wire [7:0] led
);
    wire clk_10mhz;
    wire pll_locked;
    cosmic_board_01_pll pll (
        .clkin(clk_25mhz),
        .clkout0(clk_10mhz),
        .locked(pll_locked)
    );

    reg button_meta;
    reg button_sync;
    reg ftdi_meta;
    reg ftdi_sync;
    reg [3:0] lock_history;

    always @(posedge clk_10mhz) begin
        button_meta <= btn_reset_start;
        button_sync <= button_meta;
        ftdi_meta <= ftdi_txd;
        ftdi_sync <= ftdi_meta;
        if (!pll_locked || button_sync)
            lock_history <= 4'b0000;
        else
            lock_history <= {lock_history[2:0], 1'b1};
    end

    wire core_reset = !lock_history[3];
    wire byte_valid;
    wire byte_ready;
    wire [7:0] byte_data;
    wire engine_done;
    wire [7:0] engine_status;

    (* keep_hierarchy = "yes" *)
    cosmic_board_01_engine engine (
        .clk(clk_10mhz),
        .reset(core_reset),
        .byte_valid(byte_valid),
        .byte_ready(byte_ready),
        .byte_data(byte_data),
        .done(engine_done),
        .status(engine_status),
        .accepted_ticks_out(),
        .receipt_count_out(),
        .digest_count_out(),
        .final_phase_out(),
        .final_active_out(),
        .final_changed_out(),
        .final_dirty_out()
    );

    cosmic_board_01_uart_tx #(.DIVISOR(87)) uart (
        .clk(clk_10mhz),
        .reset(core_reset),
        .byte_valid(byte_valid),
        .byte_ready(byte_ready),
        .byte_data(byte_data),
        .tx(ftdi_rxd)
    );

    // The synchronized host-RX input is visible only in a diagnostic LED bit;
    // it cannot alter workload, transition, receipt, digest, or transcript.
    assign led = engine_status ^ {ftdi_sync, 7'b0};
endmodule
