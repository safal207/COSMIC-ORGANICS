`timescale 1ns/1ps

// COSMIC-HW-16/v0.1 ULX3S board wrapper.
//
// Scientific boundary:
// - The exact frozen cosmic_hw08_sparse_receipt_sha256 processor is instantiated.
// - No expected digest or expected frame is present in RTL.
// - The self-test, counters, UART and LEDs are observation/control plumbing only.
// - The proof output cannot feed A/M/C transition authority; only the inherited
//   valid/ready backpressure path remains.

module cosmic_hw16_uart_tx #(
    parameter integer CLOCK_HZ = 10_000_000,
    parameter integer BAUD = 115_200,
    parameter integer DIVISOR = 87
) (
    input  wire       clk,
    input  wire       reset,
    input  wire       data_valid,
    output wire       data_ready,
    input  wire [7:0] data,
    output wire       tx,
    output reg        busy
);
    reg [15:0] baud_counter;
    reg [3:0]  bit_index;
    reg [9:0]  shift_reg;

    assign data_ready = !busy;
    assign tx = busy ? shift_reg[0] : 1'b1;

    always @(posedge clk) begin
        if (reset) begin
            baud_counter <= 16'd0;
            bit_index <= 4'd0;
            shift_reg <= 10'h3ff;
            busy <= 1'b0;
        end else begin
            if (!busy) begin
                if (data_valid) begin
                    // LSB first: start(0), data[0..7], stop(1).
                    shift_reg <= {1'b1, data, 1'b0};
                    baud_counter <= DIVISOR - 1;
                    bit_index <= 4'd0;
                    busy <= 1'b1;
                end
            end else if (baud_counter != 0) begin
                baud_counter <= baud_counter - 16'd1;
            end else if (bit_index == 4'd9) begin
                busy <= 1'b0;
                shift_reg <= 10'h3ff;
            end else begin
                shift_reg <= {1'b1, shift_reg[9:1]};
                baud_counter <= DIVISOR - 1;
                bit_index <= bit_index + 4'd1;
            end
        end
    end
endmodule


module cosmic_hw16_selftest_logic (
    input  wire         clk,
    input  wire         reset,
    output wire         uart_tx,
    output wire [7:0]   status_led,
    output wire         self_test_complete,
    output wire [15:0]  accepted_tick_count_debug,
    output wire [31:0]  receipt_count_debug,
    output wire [15:0]  digest_count_debug,
    output wire [255:0] last_digest_debug,
    output wire [15:0]  error_flags_debug
);
    localparam [3:0] ST_TICK_A_TO_M = 4'd0;
    localparam [3:0] ST_TICK_M_TO_C = 4'd1;
    localparam [3:0] ST_DRAIN_FULL  = 4'd2;
    localparam [3:0] ST_FLUSH       = 4'd3;
    localparam [3:0] ST_WAIT_FINAL  = 4'd4;
    localparam [3:0] ST_CHECKSUM    = 4'd5;
    localparam [3:0] ST_BUILD_FRAME = 4'd6;
    localparam [3:0] ST_CRC         = 4'd7;
    localparam [3:0] ST_UART        = 4'd8;
    localparam [3:0] ST_UART_DRAIN  = 4'd9;
    localparam [3:0] ST_DONE        = 4'd10;

    localparam [7:0] PROFILE_ID = 8'd2;
    localparam [15:0] EXPECTED_TICKS = 16'd2;
    localparam [31:0] EXPECTED_RECEIPTS = 32'd128;
    localparam [15:0] EXPECTED_DIGESTS = 16'd13;
    localparam [15:0] EXPECTED_LAST_SEQUENCE = 16'd12;

    reg [3:0] state;
    reg [23:0] heartbeat_counter;

    wire tick_valid = (state == ST_TICK_A_TO_M) ||
                      (state == ST_TICK_M_TO_C);
    wire tick_ready;
    wire tick_fire = tick_valid && tick_ready;

    // The two authoritative self-test ticks both observe +100 s100 at every
    // site. After the second tick, this retained register evolves as a finite
    // LFSR forever. That does not change the two-tick oracle because tick_valid
    // is then low, but it prevents synthesis from replacing the exact 512-bit
    // processor input with a compile-time constant.
    (* keep = "true" *) reg [511:0] stimulus_state;
    wire stimulus_lfsr_feedback = stimulus_state[511] ^ stimulus_state[509] ^
                                  stimulus_state[503] ^ stimulus_state[500];
    wire [511:0] stimulus_bus = stimulus_state;
    wire flush = (state == ST_FLUSH);

    wire [127:0] phase_bus;
    wire [63:0] active_mask;
    wire [63:0] changed_mask;
    wire [63:0] dirty_mask;

    wire digest_valid;
    wire [255:0] digest_data;
    wire [15:0] digest_sequence;
    wire [3:0] fill_count;
    wire waiting_block_valid;
    wire sha_busy;
    wire [6:0] sha_round_count;
    wire digest_fire = digest_valid;

    (* keep_hierarchy = "yes" *)
    cosmic_hw08_sparse_receipt_sha256 processor (
        .clk(clk),
        .reset(reset),
        .tick_valid(tick_valid),
        .tick_ready(tick_ready),
        .stimulus_bus(stimulus_bus),
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
        .sha_busy(sha_busy),
        .sha_round_count(sha_round_count)
    );

    function [6:0] popcount64;
        input [63:0] value;
        integer p;
        begin
            popcount64 = 7'd0;
            for (p = 0; p < 64; p = p + 1)
                popcount64 = popcount64 + value[p];
        end
    endfunction

    function [31:0] rotate_left_5;
        input [31:0] value;
        begin
            rotate_left_5 = {value[26:0], value[31:27]};
        end
    endfunction

    function [31:0] crc32_byte;
        input [31:0] crc_in;
        input [7:0] byte_in;
        reg [31:0] c;
        integer bit_no;
        begin
            c = crc_in ^ {24'b0, byte_in};
            for (bit_no = 0; bit_no < 8; bit_no = bit_no + 1) begin
                if (c[0])
                    c = (c >> 1) ^ 32'hedb88320;
                else
                    c = c >> 1;
            end
            crc32_byte = c;
        end
    endfunction

    reg accepted_d1;
    reg [15:0] accepted_tick_count;
    reg [31:0] receipt_count;
    reg [15:0] digest_count;
    reg [255:0] last_digest;
    reg [15:0] last_digest_sequence;
    reg [15:0] error_flags;

    reg [31:0] phase_checksum;
    reg [5:0] checksum_index;

    reg [7:0] frame_mem [0:59];
    reg [5:0] crc_index;
    reg [31:0] crc_state;
    wire [31:0] crc_next = crc32_byte(crc_state, frame_mem[crc_index]);
    wire [31:0] crc_final = crc_next ^ 32'hffffffff;

    reg [5:0] tx_index;
    wire uart_data_valid = (state == ST_UART);
    wire uart_data_ready;
    wire [7:0] uart_data = frame_mem[tx_index];
    wire uart_busy;
    reg uart_frame_emitted;
    reg complete_reg;

    cosmic_hw16_uart_tx uart (
        .clk(clk),
        .reset(reset),
        .data_valid(uart_data_valid),
        .data_ready(uart_data_ready),
        .data(uart_data),
        .tx(uart_tx),
        .busy(uart_busy)
    );

    wire running = (state != ST_DONE);
    assign status_led[0] = !reset;
    assign status_led[1] = running;
    assign status_led[2] = complete_reg;
    assign status_led[3] = uart_frame_emitted;
    assign status_led[4] = (error_flags != 16'b0);
    assign status_led[5] = (receipt_count != 32'b0);
    assign status_led[6] = (digest_count != 16'b0);
    assign status_led[7] = heartbeat_counter[23];

    assign self_test_complete = complete_reg;
    assign accepted_tick_count_debug = accepted_tick_count;
    assign receipt_count_debug = receipt_count;
    assign digest_count_debug = digest_count;
    assign last_digest_debug = last_digest;
    assign error_flags_debug = error_flags;

    integer b;
    always @(posedge clk) begin
        if (reset) begin
            state <= ST_TICK_A_TO_M;
            heartbeat_counter <= 24'b0;
            stimulus_state <= {64{8'h64}};
            accepted_d1 <= 1'b0;
            accepted_tick_count <= 16'b0;
            receipt_count <= 32'b0;
            digest_count <= 16'b0;
            last_digest <= 256'b0;
            last_digest_sequence <= 16'b0;
            error_flags <= 16'b0;
            phase_checksum <= 32'hc016a5a5;
            checksum_index <= 6'b0;
            crc_index <= 6'b0;
            crc_state <= 32'hffffffff;
            tx_index <= 6'b0;
            uart_frame_emitted <= 1'b0;
            complete_reg <= 1'b0;
            for (b = 0; b < 60; b = b + 1)
                frame_mem[b] <= 8'b0;
        end else begin
            heartbeat_counter <= heartbeat_counter + 24'd1;

            // Start dynamic evolution only after the second authoritative tick
            // has sampled the frozen +100 self-test stimulus.
            if (state >= ST_DRAIN_FULL)
                stimulus_state <= {stimulus_state[510:0], stimulus_lfsr_feedback};

            if (accepted_d1)
                receipt_count <= receipt_count + popcount64(changed_mask);
            accepted_d1 <= tick_fire;

            if (tick_fire)
                accepted_tick_count <= accepted_tick_count + 16'd1;

            if (digest_fire) begin
                if (digest_sequence != digest_count)
                    error_flags[5] <= 1'b1;
                digest_count <= digest_count + 16'd1;
                last_digest <= digest_data;
                last_digest_sequence <= digest_sequence;
            end

            case (state)
                ST_TICK_A_TO_M: begin
                    if (tick_fire)
                        state <= ST_TICK_M_TO_C;
                end

                ST_TICK_M_TO_C: begin
                    if (tick_fire)
                        state <= ST_DRAIN_FULL;
                end

                ST_DRAIN_FULL: begin
                    if (receipt_count == EXPECTED_RECEIPTS &&
                        digest_count == 16'd12 &&
                        fill_count == 4'd8 &&
                        !waiting_block_valid && !sha_busy)
                        state <= ST_FLUSH;
                end

                ST_FLUSH: begin
                    state <= ST_WAIT_FINAL;
                end

                ST_WAIT_FINAL: begin
                    if (digest_count == EXPECTED_DIGESTS &&
                        fill_count == 4'd0 &&
                        !waiting_block_valid && !sha_busy) begin
                        if (accepted_tick_count != EXPECTED_TICKS)
                            error_flags[0] <= 1'b1;
                        if (receipt_count != EXPECTED_RECEIPTS)
                            error_flags[1] <= 1'b1;
                        if (digest_count != EXPECTED_DIGESTS)
                            error_flags[2] <= 1'b1;
                        if (last_digest_sequence != EXPECTED_LAST_SEQUENCE)
                            error_flags[3] <= 1'b1;
                        if (phase_bus != {64{2'b10}})
                            error_flags[4] <= 1'b1;
                        phase_checksum <= 32'hc016a5a5;
                        checksum_index <= 6'd0;
                        state <= ST_CHECKSUM;
                    end
                end

                ST_CHECKSUM: begin
                    phase_checksum <= rotate_left_5(phase_checksum) ^
                                      {24'b0, checksum_index, phase_bus[checksum_index*2 +: 2]};
                    if (checksum_index == 6'd63)
                        state <= ST_BUILD_FRAME;
                    else
                        checksum_index <= checksum_index + 6'd1;
                end

                ST_BUILD_FRAME: begin
                    frame_mem[0] <= 8'h43;
                    frame_mem[1] <= 8'h4f;
                    frame_mem[2] <= 8'h31;
                    frame_mem[3] <= 8'h36;
                    frame_mem[4] <= 8'd1;
                    frame_mem[5] <= PROFILE_ID;
                    frame_mem[6] <= 8'd0;
                    frame_mem[7] <= 8'd0;
                    frame_mem[8] <= accepted_tick_count[7:0];
                    frame_mem[9] <= accepted_tick_count[15:8];
                    frame_mem[10] <= receipt_count[7:0];
                    frame_mem[11] <= receipt_count[15:8];
                    frame_mem[12] <= receipt_count[23:16];
                    frame_mem[13] <= receipt_count[31:24];
                    frame_mem[14] <= digest_count[7:0];
                    frame_mem[15] <= digest_count[15:8];
                    frame_mem[16] <= phase_checksum[7:0];
                    frame_mem[17] <= phase_checksum[15:8];
                    frame_mem[18] <= phase_checksum[23:16];
                    frame_mem[19] <= phase_checksum[31:24];
                    frame_mem[20] <= last_digest_sequence[7:0];
                    frame_mem[21] <= last_digest_sequence[15:8];
                    frame_mem[22] <= last_digest[255:248];
                    frame_mem[23] <= last_digest[247:240];
                    frame_mem[24] <= last_digest[239:232];
                    frame_mem[25] <= last_digest[231:224];
                    frame_mem[26] <= last_digest[223:216];
                    frame_mem[27] <= last_digest[215:208];
                    frame_mem[28] <= last_digest[207:200];
                    frame_mem[29] <= last_digest[199:192];
                    frame_mem[30] <= last_digest[191:184];
                    frame_mem[31] <= last_digest[183:176];
                    frame_mem[32] <= last_digest[175:168];
                    frame_mem[33] <= last_digest[167:160];
                    frame_mem[34] <= last_digest[159:152];
                    frame_mem[35] <= last_digest[151:144];
                    frame_mem[36] <= last_digest[143:136];
                    frame_mem[37] <= last_digest[135:128];
                    frame_mem[38] <= last_digest[127:120];
                    frame_mem[39] <= last_digest[119:112];
                    frame_mem[40] <= last_digest[111:104];
                    frame_mem[41] <= last_digest[103:96];
                    frame_mem[42] <= last_digest[95:88];
                    frame_mem[43] <= last_digest[87:80];
                    frame_mem[44] <= last_digest[79:72];
                    frame_mem[45] <= last_digest[71:64];
                    frame_mem[46] <= last_digest[63:56];
                    frame_mem[47] <= last_digest[55:48];
                    frame_mem[48] <= last_digest[47:40];
                    frame_mem[49] <= last_digest[39:32];
                    frame_mem[50] <= last_digest[31:24];
                    frame_mem[51] <= last_digest[23:16];
                    frame_mem[52] <= last_digest[15:8];
                    frame_mem[53] <= last_digest[7:0];
                    frame_mem[54] <= error_flags[7:0];
                    frame_mem[55] <= error_flags[15:8];
                    crc_state <= 32'hffffffff;
                    crc_index <= 6'd0;
                    state <= ST_CRC;
                end

                ST_CRC: begin
                    crc_state <= crc_next;
                    if (crc_index == 6'd55) begin
                        frame_mem[56] <= crc_final[7:0];
                        frame_mem[57] <= crc_final[15:8];
                        frame_mem[58] <= crc_final[23:16];
                        frame_mem[59] <= crc_final[31:24];
                        tx_index <= 6'd0;
                        state <= ST_UART;
                    end else begin
                        crc_index <= crc_index + 6'd1;
                    end
                end

                ST_UART: begin
                    if (uart_data_valid && uart_data_ready) begin
                        if (tx_index == 6'd59)
                            state <= ST_UART_DRAIN;
                        else
                            tx_index <= tx_index + 6'd1;
                    end
                end

                ST_UART_DRAIN: begin
                    if (!uart_busy) begin
                        uart_frame_emitted <= 1'b1;
                        complete_reg <= 1'b1;
                        state <= ST_DONE;
                    end
                end

                default: begin
                    state <= ST_DONE;
                end
            endcase
        end
    end
endmodule


module cosmic_hw16_ulx3s_top (
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

    // Preserve the pinned FTDI receive pin without granting it execution
    // authority in HW-16/v0.1. A later protocol experiment may consume it.
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

    wire [7:0] logic_led;
    wire self_test_complete_unused;
    wire [15:0] accepted_tick_count_unused;
    wire [31:0] receipt_count_unused;
    wire [15:0] digest_count_unused;
    wire [255:0] last_digest_unused;
    wire [15:0] error_flags_unused;

    cosmic_hw16_selftest_logic board_logic (
        .clk(clk_10mhz),
        .reset(processor_reset),
        .uart_tx(ftdi_rxd),
        .status_led(logic_led),
        .self_test_complete(self_test_complete_unused),
        .accepted_tick_count_debug(accepted_tick_count_unused),
        .receipt_count_debug(receipt_count_unused),
        .digest_count_debug(digest_count_unused),
        .last_digest_debug(last_digest_unused),
        .error_flags_debug(error_flags_unused)
    );

    assign led = {logic_led[7:1], pll_locked};
endmodule
