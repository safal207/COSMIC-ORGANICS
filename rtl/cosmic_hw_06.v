`timescale 1ns/1ps

// COSMIC-HW-06/v0.1 phase-1 RTL.
//
// 64 architectural processing elements arranged as an 8x8 von-Neumann mesh.
// A=2'b00, M=2'b01, C=2'b10. 2'b11 is reserved.
// Stimuli are signed integer hundredths. The transition comparison is written
// as an exact integer inequality equivalent to the frozen Python Grid2D law:
//
// drive = stimulus + coupling * (neighbor_mean - phase_value)
//
// Multiplying by 200*N avoids division and avoids an approximate 0.35 fixed
// point encoding:
//   drive_num = 2*N*stimulus_s100 + coupling100*delta_phase2
//   limit     = 2*N*threshold100
//
// Proof logic is intentionally absent in phase 1. It will be added only after
// dense/sparse semantic equivalence and sparse-work value are established.

module cosmic_hw06_mesh64 #(
    parameter integer SPARSE = 0
) (
    input  wire         clk,
    input  wire         reset,
    input  wire         tick_en,
    input  wire [511:0] stimulus_bus,
    output wire [127:0] phase_bus,
    output reg  [63:0]  active_mask,
    output reg  [63:0]  changed_mask,
    output reg  [63:0]  dirty_mask
);
    localparam [1:0] PHASE_A = 2'b00;
    localparam [1:0] PHASE_M = 2'b01;
    localparam [1:0] PHASE_C = 2'b10;

    reg [1:0] phase [0:63];
    reg [1:0] next_phase [0:63];
    reg signed [7:0] previous_stimulus [0:63];

    reg [63:0] active_comb;
    reg [63:0] changed_comb;
    reg [63:0] dirty_next_comb;

    integer i;
    integer row;
    integer col;
    integer neighbor_count;
    integer neighbor_sum2;
    integer self_value2;
    integer delta_phase2;
    integer coupling100;
    integer threshold100;
    integer stimulus_i;
    integer drive_num;
    integer limit;

    function integer phase_value2;
        input [1:0] value;
        begin
            case (value)
                PHASE_A: phase_value2 = 0;
                PHASE_M: phase_value2 = 1;
                PHASE_C: phase_value2 = 2;
                default: phase_value2 = 0;
            endcase
        end
    endfunction

    genvar g;
    generate
        for (g = 0; g < 64; g = g + 1) begin : FLATTEN_STATE
            assign phase_bus[g*2 +: 2] = phase[g];
        end
    endgenerate

    always @* begin
        active_comb = 64'b0;
        changed_comb = 64'b0;
        dirty_next_comb = 64'b0;

        for (i = 0; i < 64; i = i + 1) begin
            next_phase[i] = phase[i];
            stimulus_i = $signed(stimulus_bus[i*8 +: 8]);

            if (SPARSE == 0)
                active_comb[i] = 1'b1;
            else if (dirty_mask[i] || stimulus_i != previous_stimulus[i])
                active_comb[i] = 1'b1;

            if (active_comb[i]) begin
                row = i / 8;
                col = i % 8;
                neighbor_count = 0;
                neighbor_sum2 = 0;

                if (row > 0) begin
                    neighbor_count = neighbor_count + 1;
                    neighbor_sum2 = neighbor_sum2 + phase_value2(phase[i-8]);
                end
                if (row < 7) begin
                    neighbor_count = neighbor_count + 1;
                    neighbor_sum2 = neighbor_sum2 + phase_value2(phase[i+8]);
                end
                if (col > 0) begin
                    neighbor_count = neighbor_count + 1;
                    neighbor_sum2 = neighbor_sum2 + phase_value2(phase[i-1]);
                end
                if (col < 7) begin
                    neighbor_count = neighbor_count + 1;
                    neighbor_sum2 = neighbor_sum2 + phase_value2(phase[i+1]);
                end

                self_value2 = phase_value2(phase[i]);
                delta_phase2 = neighbor_sum2 - neighbor_count * self_value2;
                coupling100 = (((row + col) % 2) == 0) ? 75 : 50;

                if (phase[i] == PHASE_M)
                    threshold100 = 5;
                else if (((row + col) % 2) == 0)
                    threshold100 = 50;
                else
                    threshold100 = 35;

                drive_num = 2 * neighbor_count * stimulus_i
                          + coupling100 * delta_phase2;
                limit = 2 * neighbor_count * threshold100;

                if (drive_num >= limit) begin
                    case (phase[i])
                        PHASE_A: next_phase[i] = PHASE_M;
                        PHASE_M: next_phase[i] = PHASE_C;
                        PHASE_C: next_phase[i] = PHASE_C;
                        default: next_phase[i] = PHASE_A;
                    endcase
                end else if (drive_num <= -limit) begin
                    case (phase[i])
                        PHASE_A: next_phase[i] = PHASE_A;
                        PHASE_M: next_phase[i] = PHASE_A;
                        PHASE_C: next_phase[i] = PHASE_M;
                        default: next_phase[i] = PHASE_A;
                    endcase
                end

                if (next_phase[i] != phase[i])
                    changed_comb[i] = 1'b1;
            end
        end

        // Frozen dirty-frontier rule: a committed transition dirties the site
        // itself and its N/S/E/W neighbors for the next logical tick.
        if (SPARSE != 0) begin
            for (i = 0; i < 64; i = i + 1) begin
                if (changed_comb[i]) begin
                    row = i / 8;
                    col = i % 8;
                    dirty_next_comb[i] = 1'b1;
                    if (row > 0) dirty_next_comb[i-8] = 1'b1;
                    if (row < 7) dirty_next_comb[i+8] = 1'b1;
                    if (col > 0) dirty_next_comb[i-1] = 1'b1;
                    if (col < 7) dirty_next_comb[i+1] = 1'b1;
                end
            end
        end
    end

    always @(posedge clk) begin
        if (reset) begin
            active_mask <= 64'b0;
            changed_mask <= 64'b0;
            dirty_mask <= 64'b0;
            for (i = 0; i < 64; i = i + 1) begin
                phase[i] <= PHASE_A;
                previous_stimulus[i] <= 8'sd0;
            end
        end else if (tick_en) begin
            active_mask <= active_comb;
            changed_mask <= changed_comb;
            if (SPARSE != 0)
                dirty_mask <= dirty_next_comb;
            else
                dirty_mask <= 64'b0;
            for (i = 0; i < 64; i = i + 1) begin
                phase[i] <= next_phase[i];
                if (SPARSE != 0)
                    previous_stimulus[i] <= $signed(stimulus_bus[i*8 +: 8]);
            end
        end
    end
endmodule


module cosmic_hw06_dense_mesh64 (
    input  wire         clk,
    input  wire         reset,
    input  wire         tick_en,
    input  wire [511:0] stimulus_bus,
    output wire [127:0] phase_bus,
    output wire [63:0]  active_mask,
    output wire [63:0]  changed_mask,
    output wire [63:0]  dirty_mask
);
    cosmic_hw06_mesh64 #(.SPARSE(0)) core (
        .clk(clk), .reset(reset), .tick_en(tick_en),
        .stimulus_bus(stimulus_bus), .phase_bus(phase_bus),
        .active_mask(active_mask), .changed_mask(changed_mask),
        .dirty_mask(dirty_mask)
    );
endmodule


module cosmic_hw06_sparse_mesh64 (
    input  wire         clk,
    input  wire         reset,
    input  wire         tick_en,
    input  wire [511:0] stimulus_bus,
    output wire [127:0] phase_bus,
    output wire [63:0]  active_mask,
    output wire [63:0]  changed_mask,
    output wire [63:0]  dirty_mask
);
    cosmic_hw06_mesh64 #(.SPARSE(1)) core (
        .clk(clk), .reset(reset), .tick_en(tick_en),
        .stimulus_bus(stimulus_bus), .phase_bus(phase_bus),
        .active_mask(active_mask), .changed_mask(changed_mask),
        .dirty_mask(dirty_mask)
    );
endmodule
