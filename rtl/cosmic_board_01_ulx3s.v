`timescale 1ns/1ps

// COSMIC-BOARD-01A/v0.1 ULX3S-85F static candidate.
//
// The selected processor is instantiated unchanged. This board wrapper owns
// only clock/reset, the frozen 64-tick LFSR workload, finite digest
// backpressure, protocol framing, UART serialization, and status LEDs.
// No UART/checksum/status signal feeds A/M/C transition or SHA authority.

module cosmic_board_01_uart_tx #(
    parameter integer CLKS_PER_BIT = 87
) (
    input  wire       clk,
    input  wire       reset,
    input  wire       data_valid,
    output wire       data_ready,
    input  wire [7:0] data,
    output reg        tx,
    output reg        busy
);
    reg [9:0] bits;
    reg [3:0] bit_index;
    reg [15:0] baud_count;

    assign data_ready = !busy;

    always @(posedge clk) begin
        if (reset) begin
            bits <= 10'h3ff;
            bit_index <= 4'd0;
            baud_count <= 16'd0;
            tx <= 1'b1;
            busy <= 1'b0;
        end else if (!busy) begin
            tx <= 1'b1;
            baud_count <= 16'd0;
            bit_index <= 4'd0;
            if (data_valid) begin
                // LSB first: start, data[0:7], stop.
                bits <= {1'b1, data, 1'b0};
                tx <= 1'b0;
                busy <= 1'b1;
            end
        end else if (baud_count == CLKS_PER_BIT - 1) begin
            baud_count <= 16'd0;
            if (bit_index == 4'd9) begin
                tx <= 1'b1;
                busy <= 1'b0;
            end else begin
                bit_index <= bit_index + 4'd1;
                tx <= bits[bit_index + 4'd1];
            end
        end else begin
            baud_count <= baud_count + 16'd1;
        end
    end
endmodule


module cosmic_board_01_ulx3s #(
    parameter integer SIMULATION = 0,
    parameter integer UART_CLKS_PER_BIT = 87,
    parameter integer QUIET_CYCLES = 512
) (
    input  wire       clk_25mhz,
    input  wire       ftdi_txd,
    input  wire       btn_reset_start,
    output wire       ftdi_rxd,
    output wire [7:0] led
);
    localparam [1:0] OWNER_START  = 2'd1;
    localparam [1:0] OWNER_DIGEST = 2'd2;
    localparam [1:0] OWNER_END    = 2'd3;

    localparam [7:0] FRAME_START  = 8'h01;
    localparam [7:0] FRAME_DIGEST = 8'h20;
    localparam [7:0] FRAME_END    = 8'h7f;

    localparam [511:0] INITIAL_STIMULUS =
        512'h1f123bb5a55a0f0fc33ca5a56969f00fd15ea5e5c001d00dcafe5eed12345678_89abcdef0123456776543210fedcba98a5a55a5ac3c33c3cf0f00f0f55aa55aa;

    wire core_clk;
    wire pll_locked;

    generate
        if (SIMULATION != 0) begin : g_sim_clock
            assign core_clk = clk_25mhz;
            assign pll_locked = 1'b1;
        end else begin : g_real_clock
            cosmic_board_01_pll pll (
                .clkin(clk_25mhz),
                .clkout0(core_clk),
                .locked(pll_locked)
            );
        end
    endgenerate

    // PLL lock and the explicit board button both hold the design in reset.
    reg [3:0] reset_pipe;
    always @(posedge core_clk or negedge pll_locked) begin
        if (!pll_locked)
            reset_pipe <= 4'hf;
        else if (btn_reset_start)
            reset_pipe <= 4'hf;
        else
            reset_pipe <= {reset_pipe[2:0], 1'b0};
    end
    wire reset = reset_pipe[3];

    reg [511:0] stimulus_state;
    reg [15:0] accepted_ticks;
    reg tick_valid;
    wire tick_ready;
    wire tick_fire = tick_valid && tick_ready;
    reg flush;

    wire [127:0] phase_bus;
    wire [63:0] active_mask;
    wire [63:0] changed_mask;
    wire [63:0] dirty_mask;
    wire digest_valid;
    wire digest_ready;
    wire [255:0] digest_data;
    wire [15:0] digest_sequence;
    wire [3:0] fill_count_out;
    wire waiting_block_valid_out;
    wire sha_busy;
    wire [6:0] sha_round_count;

    (* keep_hierarchy = "yes" *)
    cosmic_hw08_sparse_receipt_sha256 profile (
        .clk(core_clk),
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
        .fill_count_out(fill_count_out),
        .waiting_block_valid_out(waiting_block_valid_out),
        .sha_busy(sha_busy),
        .sha_round_count(sha_round_count)
    );

    reg pending_digest_valid;
    reg [255:0] pending_digest_data;
    reg [15:0] pending_digest_sequence;
    reg [15:0] digest_count;
    reg [31:0] receipt_count;
    reg [3:0] final_partial_count;

    assign digest_ready = !pending_digest_valid;
    wire digest_fire = digest_valid && digest_ready;

    // Frame engine: 2 sync bytes, 4 body header bytes, payload, CRC16.
    reg frame_active;
    reg [1:0] frame_owner;
    reg [7:0] frame_type;
    reg [7:0] frame_payload_len;
    reg [15:0] frame_record_sequence;
    reg [391:0] frame_payload_shift;
    reg [8:0] frame_byte_index;
    reg [15:0] frame_crc;
    reg frame_done;

    reg [15:0] next_record_sequence;
    reg start_pending;
    reg end_pending;
    reg run_started;
    reg end_frame_accepted;
    reg done;
    reg error;

    wire frame_request_ready = !frame_active;
    reg frame_request_valid;
    reg [1:0] frame_request_owner;
    reg [7:0] frame_request_type;
    reg [7:0] frame_request_len;
    reg [391:0] frame_request_payload;
    wire frame_request_fire = frame_request_valid && frame_request_ready;

    always @* begin
        frame_request_valid = 1'b0;
        frame_request_owner = 2'b0;
        frame_request_type = 8'b0;
        frame_request_len = 8'b0;
        frame_request_payload = 392'b0;

        if (start_pending) begin
            frame_request_valid = 1'b1;
            frame_request_owner = OWNER_START;
            frame_request_type = FRAME_START;
            frame_request_len = 8'd12;
            frame_request_payload = {
                16'h0001, 32'h50455331, 16'h0040, 32'h4c353132,
                296'b0
            };
        end else if (pending_digest_valid) begin
            frame_request_valid = 1'b1;
            frame_request_owner = OWNER_DIGEST;
            frame_request_type = FRAME_DIGEST;
            frame_request_len = 8'd34;
            frame_request_payload = {
                pending_digest_sequence, pending_digest_data, 120'b0
            };
        end else if (end_pending) begin
            frame_request_valid = 1'b1;
            frame_request_owner = OWNER_END;
            frame_request_type = FRAME_END;
            frame_request_len = 8'd49;
            frame_request_payload = {
                8'ha5,
                accepted_ticks,
                receipt_count,
                digest_count,
                phase_bus,
                active_mask,
                changed_mask,
                dirty_mask
            };
        end
    end

    function [15:0] crc16_byte;
        input [15:0] crc_in;
        input [7:0] data_in;
        reg [15:0] value;
        integer n;
        begin
            value = crc_in ^ {data_in, 8'b0};
            for (n = 0; n < 8; n = n + 1) begin
                if (value[15])
                    value = (value << 1) ^ 16'h1021;
                else
                    value = value << 1;
            end
            crc16_byte = value;
        end
    endfunction

    reg [7:0] uart_byte_data;
    wire uart_byte_valid = frame_active;
    wire uart_byte_ready;
    wire uart_byte_fire = uart_byte_valid && uart_byte_ready;
    wire uart_busy;

    always @* begin
        if (frame_byte_index == 0)
            uart_byte_data = 8'h43;
        else if (frame_byte_index == 1)
            uart_byte_data = 8'h4f;
        else if (frame_byte_index == 2)
            uart_byte_data = frame_type;
        else if (frame_byte_index == 3)
            uart_byte_data = frame_payload_len;
        else if (frame_byte_index == 4)
            uart_byte_data = frame_record_sequence[15:8];
        else if (frame_byte_index == 5)
            uart_byte_data = frame_record_sequence[7:0];
        else if (frame_byte_index < 6 + frame_payload_len)
            uart_byte_data = frame_payload_shift[391:384];
        else if (frame_byte_index == 6 + frame_payload_len)
            uart_byte_data = frame_crc[15:8];
        else
            uart_byte_data = frame_crc[7:0];
    end

    cosmic_board_01_uart_tx #(
        .CLKS_PER_BIT(UART_CLKS_PER_BIT)
    ) uart_tx (
        .clk(core_clk),
        .reset(reset),
        .data_valid(uart_byte_valid),
        .data_ready(uart_byte_ready),
        .data(uart_byte_data),
        .tx(ftdi_rxd),
        .busy(uart_busy)
    );

    wire body_byte = (frame_byte_index >= 2) &&
                     (frame_byte_index < 6 + frame_payload_len);
    wire payload_byte = (frame_byte_index >= 6) &&
                        (frame_byte_index < 6 + frame_payload_len);
    wire final_frame_byte =
        frame_byte_index == (7 + frame_payload_len);

    always @(posedge core_clk) begin
        if (reset) begin
            frame_active <= 1'b0;
            frame_owner <= 2'b0;
            frame_type <= 8'b0;
            frame_payload_len <= 8'b0;
            frame_record_sequence <= 16'b0;
            frame_payload_shift <= 392'b0;
            frame_byte_index <= 9'b0;
            frame_crc <= 16'hffff;
            frame_done <= 1'b0;
        end else begin
            frame_done <= 1'b0;
            if (!frame_active && frame_request_fire) begin
                frame_active <= 1'b1;
                frame_owner <= frame_request_owner;
                frame_type <= frame_request_type;
                frame_payload_len <= frame_request_len;
                frame_record_sequence <= next_record_sequence;
                frame_payload_shift <= frame_request_payload;
                frame_byte_index <= 9'b0;
                frame_crc <= 16'hffff;
            end else if (uart_byte_fire) begin
                if (body_byte)
                    frame_crc <= crc16_byte(frame_crc, uart_byte_data);
                if (payload_byte)
                    frame_payload_shift <= {frame_payload_shift[383:0], 8'b0};

                if (final_frame_byte) begin
                    frame_active <= 1'b0;
                    frame_done <= 1'b1;
                end else begin
                    frame_byte_index <= frame_byte_index + 9'd1;
                end
            end
        end
    end

    reg [9:0] quiet_count;
    reg [9:0] final_quiet_count;
    reg [3:0] last_fill_count;
    reg flush_issued;
    reg [31:0] watchdog;
    reg ftdi_txd_sample;

    wire lfsr_feedback = stimulus_state[511] ^ stimulus_state[509] ^
                         stimulus_state[503] ^ stimulus_state[500];

    wire pipeline_quiet =
        !frame_active && !pending_digest_valid && !digest_valid &&
        !waiting_block_valid_out && !sha_busy;

    always @(posedge core_clk) begin
        if (reset) begin
            stimulus_state <= INITIAL_STIMULUS;
            accepted_ticks <= 16'd0;
            tick_valid <= 1'b0;
            flush <= 1'b0;
            pending_digest_valid <= 1'b0;
            pending_digest_data <= 256'b0;
            pending_digest_sequence <= 16'b0;
            digest_count <= 16'd0;
            receipt_count <= 32'd0;
            final_partial_count <= 4'd0;
            next_record_sequence <= 16'd0;
            start_pending <= 1'b1;
            end_pending <= 1'b0;
            run_started <= 1'b0;
            end_frame_accepted <= 1'b0;
            done <= 1'b0;
            error <= 1'b0;
            quiet_count <= 10'd0;
            final_quiet_count <= 10'd0;
            last_fill_count <= 4'd0;
            flush_issued <= 1'b0;
            watchdog <= 32'd0;
            ftdi_txd_sample <= 1'b1;
        end else begin
            flush <= 1'b0;
            watchdog <= watchdog + 32'd1;
            ftdi_txd_sample <= ftdi_txd;

            if (frame_request_fire) begin
                next_record_sequence <= next_record_sequence + 16'd1;
                case (frame_request_owner)
                    OWNER_START: start_pending <= 1'b0;
                    OWNER_DIGEST: pending_digest_valid <= 1'b0;
                    OWNER_END: end_pending <= 1'b0;
                    default: error <= 1'b1;
                endcase
            end

            if (frame_done) begin
                case (frame_owner)
                    OWNER_START: run_started <= 1'b1;
                    OWNER_END: end_frame_accepted <= 1'b1;
                    default: begin end
                endcase
            end

            if (end_frame_accepted && !uart_busy && !frame_active)
                done <= 1'b1;

            if (digest_fire) begin
                if (digest_sequence != digest_count)
                    error <= 1'b1;
                pending_digest_valid <= 1'b1;
                pending_digest_data <= digest_data;
                pending_digest_sequence <= digest_sequence;
                digest_count <= digest_count + 16'd1;
            end

            if (run_started && accepted_ticks < 16'd64) begin
                if (!tick_valid)
                    tick_valid <= 1'b1;
                if (tick_fire) begin
                    tick_valid <= 1'b0;
                    accepted_ticks <= accepted_ticks + 16'd1;
                    stimulus_state <= {stimulus_state[510:0], lfsr_feedback};
                end
            end else begin
                tick_valid <= 1'b0;
            end

            last_fill_count <= fill_count_out;

            if (!flush_issued && accepted_ticks == 16'd64 &&
                pipeline_quiet && fill_count_out == last_fill_count) begin
                if (quiet_count < QUIET_CYCLES)
                    quiet_count <= quiet_count + 10'd1;
                if (quiet_count == QUIET_CYCLES - 1) begin
                    if (fill_count_out == 0) begin
                        error <= 1'b1;
                    end else begin
                        final_partial_count <= fill_count_out;
                        receipt_count <= (digest_count * 10) + fill_count_out;
                        flush <= 1'b1;
                        flush_issued <= 1'b1;
                    end
                    quiet_count <= 10'd0;
                end
            end else begin
                quiet_count <= 10'd0;
            end

            if (flush_issued && !end_pending && !end_frame_accepted &&
                pipeline_quiet && fill_count_out == 0) begin
                if (final_quiet_count < 10'd32)
                    final_quiet_count <= final_quiet_count + 10'd1;
                if (final_quiet_count == 10'd31) begin
                    end_pending <= 1'b1;
                    final_quiet_count <= 10'd0;
                end
            end else begin
                final_quiet_count <= 10'd0;
            end

            // More than four minutes at 10 MHz indicates a stuck controller.
            if (watchdog == 32'h8fffffff)
                error <= 1'b1;
        end
    end

    // Status is observational only. ftdi_txd is sampled solely to keep the
    // declared board input physically present; it has no processor authority.
    assign led[0] = pll_locked;
    assign led[1] = !reset;
    assign led[2] = run_started && !flush_issued;
    assign led[3] = flush_issued;
    assign led[4] = pending_digest_valid || digest_valid || sha_busy;
    assign led[5] = done;
    assign led[6] = error;
    assign led[7] = uart_busy ^ ~ftdi_txd_sample;
endmodule
