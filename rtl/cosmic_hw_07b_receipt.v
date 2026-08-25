`timescale 1ns/1ps

// COSMIC-HW-07B/v0.1 receipt microarchitecture frontier.
//
// Semantic contract is identical to frozen COSMIC-HW-07:
// - sparse HW-06 execution core remains authoritative;
// - 40-bit receipt fields and ascending-site order are unchanged;
// - one valid/ready output lane;
// - finite pre-commit batch reservation; no drop/infinite buffering.
//
// Candidate-only changes:
// 1) deterministic hierarchical 8-row x 8-column selector;
// 2) FIFO_DEPTH is frozen per candidate at 4, 2, or 1.
//
// The selector first chooses the lowest non-empty 8-bit row mask, then the
// lowest set column within that row. Phase/stimulus selection is likewise
// split into a fixed row slice and fixed column selection, rather than one
// flat 64-site variable mux.

module cosmic_hw07b_sparse_hier_receipt #(
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

    reg          pending_valid;
    reg [15:0]   pending_tick;
    reg [127:0]  pending_pre_phase;
    reg [511:0]  pending_stimulus;
    reg [15:0]   logical_tick;

    reg [15:0]   fifo_tick    [0:FIFO_DEPTH-1];
    reg [63:0]   fifo_changed [0:FIFO_DEPTH-1];
    reg [127:0]  fifo_pre     [0:FIFO_DEPTH-1];
    reg [127:0]  fifo_post    [0:FIFO_DEPTH-1];
    reg [511:0]  fifo_stim    [0:FIFO_DEPTH-1];

    reg [1:0] wr_ptr;
    reg [1:0] rd_ptr;
    reg [2:0] fifo_count;
    reg [5:0] head_ordinal;

    reg       selected_found_comb;
    reg [2:0] selected_row_comb;
    reg [2:0] selected_col_comb;
    reg [5:0] selected_site_comb;
    reg [63:0] selected_bit_comb;
    reg [7:0] selected_row_mask_comb;
    reg [15:0] selected_pre_row_comb;
    reg [15:0] selected_post_row_comb;
    reg [63:0] selected_stim_row_comb;
    reg [1:0] selected_pre_phase_comb;
    reg [1:0] selected_post_phase_comb;
    reg [7:0] selected_stimulus_comb;

    integer k;

    wire [2:0] reserved_count;
    wire enqueue_batch;
    wire receipt_fire;
    wire last_receipt;

    function [1:0] advance_ptr;
        input [1:0] ptr;
        begin
            if (FIFO_DEPTH <= 1)
                advance_ptr = 2'd0;
            else if (FIFO_DEPTH == 2)
                advance_ptr = (ptr == 2'd0) ? 2'd1 : 2'd0;
            else
                advance_ptr = ptr + 2'd1;
        end
    endfunction

    assign reserved_count = fifo_count + (pending_valid ? 3'd1 : 3'd0);
    assign batch_occupancy = reserved_count;
    assign pending_observation = pending_valid;
    assign tick_ready = (reserved_count < FIFO_DEPTH);
    assign core_tick_en = tick_valid && tick_ready;

    cosmic_hw06_mesh64 #(.SPARSE(1)) core (
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

    // Level 1: fixed eight-row priority encoder.
    always @* begin
        selected_found_comb = 1'b0;
        selected_row_comb = 3'd0;
        if (fifo_count != 0) begin
            if      (|fifo_changed[rd_ptr][7:0])   begin selected_found_comb=1'b1; selected_row_comb=3'd0; end
            else if (|fifo_changed[rd_ptr][15:8])  begin selected_found_comb=1'b1; selected_row_comb=3'd1; end
            else if (|fifo_changed[rd_ptr][23:16]) begin selected_found_comb=1'b1; selected_row_comb=3'd2; end
            else if (|fifo_changed[rd_ptr][31:24]) begin selected_found_comb=1'b1; selected_row_comb=3'd3; end
            else if (|fifo_changed[rd_ptr][39:32]) begin selected_found_comb=1'b1; selected_row_comb=3'd4; end
            else if (|fifo_changed[rd_ptr][47:40]) begin selected_found_comb=1'b1; selected_row_comb=3'd5; end
            else if (|fifo_changed[rd_ptr][55:48]) begin selected_found_comb=1'b1; selected_row_comb=3'd6; end
            else if (|fifo_changed[rd_ptr][63:56]) begin selected_found_comb=1'b1; selected_row_comb=3'd7; end
        end
    end

    // Fixed row slicing for remaining mask and payload fields.
    always @* begin
        selected_row_mask_comb = 8'b0;
        selected_pre_row_comb = 16'b0;
        selected_post_row_comb = 16'b0;
        selected_stim_row_comb = 64'b0;
        case (selected_row_comb)
            3'd0: begin selected_row_mask_comb=fifo_changed[rd_ptr][7:0];   selected_pre_row_comb=fifo_pre[rd_ptr][15:0];   selected_post_row_comb=fifo_post[rd_ptr][15:0];   selected_stim_row_comb=fifo_stim[rd_ptr][63:0]; end
            3'd1: begin selected_row_mask_comb=fifo_changed[rd_ptr][15:8];  selected_pre_row_comb=fifo_pre[rd_ptr][31:16];  selected_post_row_comb=fifo_post[rd_ptr][31:16];  selected_stim_row_comb=fifo_stim[rd_ptr][127:64]; end
            3'd2: begin selected_row_mask_comb=fifo_changed[rd_ptr][23:16]; selected_pre_row_comb=fifo_pre[rd_ptr][47:32];  selected_post_row_comb=fifo_post[rd_ptr][47:32];  selected_stim_row_comb=fifo_stim[rd_ptr][191:128]; end
            3'd3: begin selected_row_mask_comb=fifo_changed[rd_ptr][31:24]; selected_pre_row_comb=fifo_pre[rd_ptr][63:48];  selected_post_row_comb=fifo_post[rd_ptr][63:48];  selected_stim_row_comb=fifo_stim[rd_ptr][255:192]; end
            3'd4: begin selected_row_mask_comb=fifo_changed[rd_ptr][39:32]; selected_pre_row_comb=fifo_pre[rd_ptr][79:64];  selected_post_row_comb=fifo_post[rd_ptr][79:64];  selected_stim_row_comb=fifo_stim[rd_ptr][319:256]; end
            3'd5: begin selected_row_mask_comb=fifo_changed[rd_ptr][47:40]; selected_pre_row_comb=fifo_pre[rd_ptr][95:80];  selected_post_row_comb=fifo_post[rd_ptr][95:80];  selected_stim_row_comb=fifo_stim[rd_ptr][383:320]; end
            3'd6: begin selected_row_mask_comb=fifo_changed[rd_ptr][55:48]; selected_pre_row_comb=fifo_pre[rd_ptr][111:96]; selected_post_row_comb=fifo_post[rd_ptr][111:96]; selected_stim_row_comb=fifo_stim[rd_ptr][447:384]; end
            3'd7: begin selected_row_mask_comb=fifo_changed[rd_ptr][63:56]; selected_pre_row_comb=fifo_pre[rd_ptr][127:112];selected_post_row_comb=fifo_post[rd_ptr][127:112];selected_stim_row_comb=fifo_stim[rd_ptr][511:448]; end
        endcase
    end

    // Level 2: fixed eight-column priority encoder within selected row.
    always @* begin
        selected_col_comb = 3'd0;
        if      (selected_row_mask_comb[0]) selected_col_comb=3'd0;
        else if (selected_row_mask_comb[1]) selected_col_comb=3'd1;
        else if (selected_row_mask_comb[2]) selected_col_comb=3'd2;
        else if (selected_row_mask_comb[3]) selected_col_comb=3'd3;
        else if (selected_row_mask_comb[4]) selected_col_comb=3'd4;
        else if (selected_row_mask_comb[5]) selected_col_comb=3'd5;
        else if (selected_row_mask_comb[6]) selected_col_comb=3'd6;
        else if (selected_row_mask_comb[7]) selected_col_comb=3'd7;
    end

    // Fixed column selection from the already narrowed row payload.
    always @* begin
        selected_pre_phase_comb = 2'b0;
        selected_post_phase_comb = 2'b0;
        selected_stimulus_comb = 8'b0;
        case (selected_col_comb)
            3'd0: begin selected_pre_phase_comb=selected_pre_row_comb[1:0];   selected_post_phase_comb=selected_post_row_comb[1:0];   selected_stimulus_comb=selected_stim_row_comb[7:0]; end
            3'd1: begin selected_pre_phase_comb=selected_pre_row_comb[3:2];   selected_post_phase_comb=selected_post_row_comb[3:2];   selected_stimulus_comb=selected_stim_row_comb[15:8]; end
            3'd2: begin selected_pre_phase_comb=selected_pre_row_comb[5:4];   selected_post_phase_comb=selected_post_row_comb[5:4];   selected_stimulus_comb=selected_stim_row_comb[23:16]; end
            3'd3: begin selected_pre_phase_comb=selected_pre_row_comb[7:6];   selected_post_phase_comb=selected_post_row_comb[7:6];   selected_stimulus_comb=selected_stim_row_comb[31:24]; end
            3'd4: begin selected_pre_phase_comb=selected_pre_row_comb[9:8];   selected_post_phase_comb=selected_post_row_comb[9:8];   selected_stimulus_comb=selected_stim_row_comb[39:32]; end
            3'd5: begin selected_pre_phase_comb=selected_pre_row_comb[11:10]; selected_post_phase_comb=selected_post_row_comb[11:10]; selected_stimulus_comb=selected_stim_row_comb[47:40]; end
            3'd6: begin selected_pre_phase_comb=selected_pre_row_comb[13:12]; selected_post_phase_comb=selected_post_row_comb[13:12]; selected_stimulus_comb=selected_stim_row_comb[55:48]; end
            3'd7: begin selected_pre_phase_comb=selected_pre_row_comb[15:14]; selected_post_phase_comb=selected_post_row_comb[15:14]; selected_stimulus_comb=selected_stim_row_comb[63:56]; end
        endcase
    end

    always @* begin
        selected_site_comb = {selected_row_comb, selected_col_comb};
        selected_bit_comb = 64'b1 << selected_site_comb;
    end

    assign receipt_valid = (fifo_count != 0) && selected_found_comb;
    assign receipt_data = {
        fifo_tick[rd_ptr],
        selected_site_comb,
        selected_pre_phase_comb,
        selected_post_phase_comb,
        selected_stimulus_comb,
        head_ordinal
    };

    assign enqueue_batch = pending_valid && (core_changed_mask != 64'b0);
    assign receipt_fire = receipt_valid && receipt_ready;
    assign last_receipt = receipt_valid && (fifo_changed[rd_ptr] == selected_bit_comb);

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

            if (enqueue_batch) begin
                fifo_tick[wr_ptr] <= pending_tick;
                fifo_changed[wr_ptr] <= core_changed_mask;
                fifo_pre[wr_ptr] <= pending_pre_phase;
                fifo_post[wr_ptr] <= core_phase_bus;
                fifo_stim[wr_ptr] <= pending_stimulus;
                wr_ptr <= advance_ptr(wr_ptr);
                batch_enqueue_pulse <= 1'b1;
            end

            if (receipt_fire) begin
                if (last_receipt) begin
                    fifo_changed[rd_ptr] <= 64'b0;
                    rd_ptr <= advance_ptr(rd_ptr);
                    head_ordinal <= 6'b0;
                    batch_dequeue_pulse <= 1'b1;
                end else begin
                    fifo_changed[rd_ptr] <= fifo_changed[rd_ptr] & ~selected_bit_comb;
                    head_ordinal <= head_ordinal + 6'd1;
                end
            end

            case ({enqueue_batch, (receipt_fire && last_receipt)})
                2'b10: fifo_count <= fifo_count + 3'd1;
                2'b01: fifo_count <= fifo_count - 3'd1;
                default: fifo_count <= fifo_count;
            endcase

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

module cosmic_hw07b_sparse_f4_hier (
    input wire clk, input wire reset, input wire tick_valid, output wire tick_ready,
    input wire [511:0] stimulus_bus, output wire [127:0] phase_bus,
    output wire [63:0] active_mask, output wire [63:0] changed_mask, output wire [63:0] dirty_mask,
    output wire receipt_valid, input wire receipt_ready, output wire [39:0] receipt_data,
    output wire [2:0] batch_occupancy, output wire pending_observation,
    output wire batch_enqueue_pulse, output wire batch_dequeue_pulse
);
    cosmic_hw07b_sparse_hier_receipt #(.FIFO_DEPTH(4)) core(.*);
endmodule

module cosmic_hw07b_sparse_f2_hier (
    input wire clk, input wire reset, input wire tick_valid, output wire tick_ready,
    input wire [511:0] stimulus_bus, output wire [127:0] phase_bus,
    output wire [63:0] active_mask, output wire [63:0] changed_mask, output wire [63:0] dirty_mask,
    output wire receipt_valid, input wire receipt_ready, output wire [39:0] receipt_data,
    output wire [2:0] batch_occupancy, output wire pending_observation,
    output wire batch_enqueue_pulse, output wire batch_dequeue_pulse
);
    cosmic_hw07b_sparse_hier_receipt #(.FIFO_DEPTH(2)) core(.*);
endmodule

module cosmic_hw07b_sparse_f1_hier (
    input wire clk, input wire reset, input wire tick_valid, output wire tick_ready,
    input wire [511:0] stimulus_bus, output wire [127:0] phase_bus,
    output wire [63:0] active_mask, output wire [63:0] changed_mask, output wire [63:0] dirty_mask,
    output wire receipt_valid, input wire receipt_ready, output wire [39:0] receipt_data,
    output wire [2:0] batch_occupancy, output wire pending_observation,
    output wire batch_enqueue_pulse, output wire batch_dequeue_pulse
);
    cosmic_hw07b_sparse_hier_receipt #(.FIFO_DEPTH(1)) core(.*);
endmodule
