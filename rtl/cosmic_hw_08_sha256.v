`timescale 1ns/1ps

// COSMIC-HW-08/v0.1
// Conventional iterative SHA-256 + finite 10-receipt commitment assembler.
// Scientific boundary: this observer never feeds digest/receipt content into
// A/M/C transition authority. Backpressure is the only execution coupling.

module cosmic_sha256_iterative (
    input  wire         clk,
    input  wire         reset,
    input  wire         block_valid,
    output wire         block_ready,
    input  wire [511:0] block_data,
    output reg          digest_valid,
    input  wire         digest_ready,
    output reg  [255:0] digest_data,
    output reg  [6:0]   round_count,
    output reg          busy
);
    reg [31:0] a,b,c,d,e,f,g,h;
    reg [31:0] w [0:63];
    reg [6:0] round_idx;
    integer i;

    wire digest_fire = digest_valid && digest_ready;
    assign block_ready = !busy && (!digest_valid || digest_ready);

    function [31:0] rotr;
        input [31:0] x;
        input integer n;
        begin rotr = (x >> n) | (x << (32-n)); end
    endfunction
    function [31:0] ch;
        input [31:0] x,y,z;
        begin ch = (x & y) ^ (~x & z); end
    endfunction
    function [31:0] maj;
        input [31:0] x,y,z;
        begin maj = (x & y) ^ (x & z) ^ (y & z); end
    endfunction
    function [31:0] bsig0;
        input [31:0] x;
        begin bsig0 = rotr(x,2) ^ rotr(x,13) ^ rotr(x,22); end
    endfunction
    function [31:0] bsig1;
        input [31:0] x;
        begin bsig1 = rotr(x,6) ^ rotr(x,11) ^ rotr(x,25); end
    endfunction
    function [31:0] ssig0;
        input [31:0] x;
        begin ssig0 = rotr(x,7) ^ rotr(x,18) ^ (x >> 3); end
    endfunction
    function [31:0] ssig1;
        input [31:0] x;
        begin ssig1 = rotr(x,17) ^ rotr(x,19) ^ (x >> 10); end
    endfunction
    function [31:0] kval;
        input [5:0] idx;
        begin
            case (idx)
              0: kval=32'h428a2f98; 1: kval=32'h71374491; 2: kval=32'hb5c0fbcf; 3: kval=32'he9b5dba5;
              4: kval=32'h3956c25b; 5: kval=32'h59f111f1; 6: kval=32'h923f82a4; 7: kval=32'hab1c5ed5;
              8: kval=32'hd807aa98; 9: kval=32'h12835b01; 10:kval=32'h243185be; 11:kval=32'h550c7dc3;
              12:kval=32'h72be5d74; 13:kval=32'h80deb1fe; 14:kval=32'h9bdc06a7; 15:kval=32'hc19bf174;
              16:kval=32'he49b69c1; 17:kval=32'hefbe4786; 18:kval=32'h0fc19dc6; 19:kval=32'h240ca1cc;
              20:kval=32'h2de92c6f; 21:kval=32'h4a7484aa; 22:kval=32'h5cb0a9dc; 23:kval=32'h76f988da;
              24:kval=32'h983e5152; 25:kval=32'ha831c66d; 26:kval=32'hb00327c8; 27:kval=32'hbf597fc7;
              28:kval=32'hc6e00bf3; 29:kval=32'hd5a79147; 30:kval=32'h06ca6351; 31:kval=32'h14292967;
              32:kval=32'h27b70a85; 33:kval=32'h2e1b2138; 34:kval=32'h4d2c6dfc; 35:kval=32'h53380d13;
              36:kval=32'h650a7354; 37:kval=32'h766a0abb; 38:kval=32'h81c2c92e; 39:kval=32'h92722c85;
              40:kval=32'ha2bfe8a1; 41:kval=32'ha81a664b; 42:kval=32'hc24b8b70; 43:kval=32'hc76c51a3;
              44:kval=32'hd192e819; 45:kval=32'hd6990624; 46:kval=32'hf40e3585; 47:kval=32'h106aa070;
              48:kval=32'h19a4c116; 49:kval=32'h1e376c08; 50:kval=32'h2748774c; 51:kval=32'h34b0bcb5;
              52:kval=32'h391c0cb3; 53:kval=32'h4ed8aa4a; 54:kval=32'h5b9cca4f; 55:kval=32'h682e6ff3;
              56:kval=32'h748f82ee; 57:kval=32'h78a5636f; 58:kval=32'h84c87814; 59:kval=32'h8cc70208;
              60:kval=32'h90befffa; 61:kval=32'ha4506ceb; 62:kval=32'hbef9a3f7; default:kval=32'hc67178f2;
            endcase
        end
    endfunction

    reg [31:0] t1,t2,wn;
    always @* begin
        if (round_idx < 16)
            wn = w[round_idx];
        else
            wn = ssig1(w[round_idx-2]) + w[round_idx-7] + ssig0(w[round_idx-15]) + w[round_idx-16];
        t1 = h + bsig1(e) + ch(e,f,g) + kval(round_idx[5:0]) + wn;
        t2 = bsig0(a) + maj(a,b,c);
    end

    always @(posedge clk) begin
        if (reset) begin
            a<=0; b<=0; c<=0; d<=0; e<=0; f<=0; g<=0; h<=0;
            round_idx<=0; round_count<=0; busy<=0; digest_valid<=0; digest_data<=0;
            for (i=0;i<64;i=i+1) w[i]<=0;
        end else begin
            if (digest_fire) digest_valid <= 1'b0;

            if (block_valid && block_ready) begin
                for (i=0;i<16;i=i+1)
                    w[i] <= block_data[511-(i*32) -: 32];
                for (i=16;i<64;i=i+1) w[i] <= 32'b0;
                a<=32'h6a09e667; b<=32'hbb67ae85; c<=32'h3c6ef372; d<=32'ha54ff53a;
                e<=32'h510e527f; f<=32'h9b05688c; g<=32'h1f83d9ab; h<=32'h5be0cd19;
                round_idx<=0; round_count<=0; busy<=1'b1;
            end else if (busy) begin
                if (round_idx >= 16) w[round_idx] <= wn;
                h<=g; g<=f; f<=e; e<=d+t1; d<=c; c<=b; b<=a; a<=t1+t2;
                round_count <= round_count + 7'd1;
                if (round_idx == 7'd63) begin
                    busy <= 1'b0;
                    digest_data <= {
                        32'h6a09e667 + (t1+t2),
                        32'hbb67ae85 + a,
                        32'h3c6ef372 + b,
                        32'ha54ff53a + c,
                        32'h510e527f + (d+t1),
                        32'h9b05688c + e,
                        32'h1f83d9ab + f,
                        32'h5be0cd19 + g
                    };
                    digest_valid <= 1'b1;
                end else begin
                    round_idx <= round_idx + 7'd1;
                end
            end
        end
    end
endmodule


module cosmic_hw08_sparse_receipt_sha256 (
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
    output wire         sha_busy,
    output wire [6:0]   sha_round_count
);
    wire receipt_valid;
    wire receipt_ready;
    wire [39:0] receipt_data;
    wire [2:0] batch_occupancy;
    wire pending_observation;
    wire batch_enqueue_pulse, batch_dequeue_pulse;

    cosmic_hw07_mesh64_receipt #(.SPARSE(1), .FIFO_DEPTH(4)) receipt_core (
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

    reg [399:0] fill_receipts;
    reg [3:0] fill_count;
    reg [15:0] next_sequence;

    reg waiting_valid;
    reg [511:0] waiting_block;
    reg [15:0] waiting_sequence;

    wire sha_block_ready;
    wire sha_digest_valid;
    wire [255:0] sha_digest_data;
    reg [15:0] active_sequence;

    wire receipt_fire = receipt_valid && receipt_ready;
    wire can_complete_direct = (fill_count != 4'd9) || !waiting_valid || sha_block_ready;
    assign receipt_ready = can_complete_direct && !(flush && fill_count != 0);

    assign fill_count_out = fill_count;
    assign waiting_block_valid_out = waiting_valid;
    assign digest_valid = sha_digest_valid;
    assign digest_data = sha_digest_data;
    assign digest_sequence = active_sequence;

    cosmic_sha256_iterative sha (
        .clk(clk), .reset(reset),
        .block_valid(waiting_valid), .block_ready(sha_block_ready),
        .block_data(waiting_block),
        .digest_valid(sha_digest_valid), .digest_ready(digest_ready),
        .digest_data(sha_digest_data),
        .round_count(sha_round_count), .busy(sha_busy)
    );

    reg [399:0] slots_next;
    reg [15:0] domain_partial;
    reg [511:0] new_block;
    integer j;

    always @* begin
        slots_next = fill_receipts;
        if (receipt_fire)
            slots_next[399-(fill_count*40) -: 40] = receipt_data;
        domain_partial = 16'h4340 | {12'b0, fill_count};
        new_block = 512'b0;
        if (receipt_fire && fill_count == 4'd9)
            new_block = {16'h434f, next_sequence, slots_next, 8'h80, 8'h00, 64'd432};
        else if (flush && fill_count != 0)
            new_block = {domain_partial, next_sequence, fill_receipts, 8'h80, 8'h00, 64'd432};
    end

    always @(posedge clk) begin
        if (reset) begin
            fill_receipts <= 400'b0;
            fill_count <= 4'd0;
            next_sequence <= 16'd0;
            waiting_valid <= 1'b0;
            waiting_block <= 512'b0;
            waiting_sequence <= 16'd0;
            active_sequence <= 16'd0;
        end else begin
            // Launch the waiting block into the single SHA engine.
            if (waiting_valid && sha_block_ready) begin
                waiting_valid <= 1'b0;
                active_sequence <= waiting_sequence;
            end

            // Full 10-receipt commitment.
            if (receipt_fire) begin
                if (fill_count == 4'd9) begin
                    waiting_block <= new_block;
                    waiting_sequence <= next_sequence;
                    waiting_valid <= 1'b1;
                    next_sequence <= next_sequence + 16'd1;
                    fill_receipts <= 400'b0;
                    fill_count <= 4'd0;
                end else begin
                    fill_receipts <= slots_next;
                    fill_count <= fill_count + 4'd1;
                end
            end

            // Explicit drain emits one final padded partial commitment.
            if (flush && fill_count != 0 && !waiting_valid) begin
                waiting_block <= new_block;
                waiting_sequence <= next_sequence;
                waiting_valid <= 1'b1;
                next_sequence <= next_sequence + 16'd1;
                fill_receipts <= 400'b0;
                fill_count <= 4'd0;
            end
        end
    end
endmodule
