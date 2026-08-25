from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import tempfile

from benchmarks.cosmic_hw_07_candidate import (
    build_oracle,
    cell_counts_from_json,
    parse_ltp,
    require_tool,
    run_cmd,
)
from benchmarks.cosmic_hw_08_candidate import expected_commitments, write_mem
from benchmarks.cosmic_hw_09_candidate import (
    prepare_mem as prepare_hw09_mem,
    simulate_candidate as simulate_hw09_candidate,
    synthesize_multi as synthesize_hw09_multi,
)
from benchmarks.cosmic_hw_10_oracle import build_tree, proof_fragments

BENCHMARK_ID = "COSMIC-HW-10-CANDIDATE"
PROTOCOL = "COSMIC-HW-10/v0.1"
FROZEN_X2_STALLS = {"0.01": 0, "0.05": 542, "0.20": 11184, "1.00": 13456, "stress": 28675}


def expected_merkle(execution: dict, commitments: dict) -> dict:
    digests = [int(x).to_bytes(32, "big") for x in commitments["digests"]]
    seq_counts = [int(x) for x in commitments["seq_digest_counts"]]
    cursor = 0
    roots: list[dict[str, int]] = []
    proofs: list[dict[str, int]] = []
    seq_root_counts: list[int] = []
    seq_proof_counts: list[int] = []

    for source_sequence, count in enumerate(seq_counts):
        seq_digests = digests[cursor : cursor + count]
        cursor += count
        tree_ordinal = 0
        roots_before = len(roots)
        proofs_before = len(proofs)
        for start in range(0, count, 16):
            chunk = seq_digests[start : start + 16]
            tree = build_tree(source_sequence, tree_ordinal, chunk)
            roots.append(
                {
                    "source_sequence": source_sequence,
                    "tree_ordinal": tree_ordinal,
                    "real_leaf_count": tree.real_leaf_count,
                    "root": int.from_bytes(tree.root, "big"),
                }
            )
            for leaf_ordinal in range(tree.real_leaf_count):
                for fragment in proof_fragments(tree, leaf_ordinal):
                    proofs.append(
                        {
                            "source_sequence": int(fragment["source_sequence"]),
                            "tree_ordinal": int(fragment["tree_ordinal"]),
                            "leaf_ordinal": int(fragment["leaf_ordinal"]),
                            "level": int(fragment["level"]),
                            "sibling_is_left": int(bool(fragment["sibling_is_left"])),
                            "sibling": int(str(fragment["sibling_hex"]), 16),
                        }
                    )
            tree_ordinal += 1
        seq_root_counts.append(len(roots) - roots_before)
        seq_proof_counts.append(len(proofs) - proofs_before)

    if cursor != len(digests):
        raise RuntimeError("HW-10 digest cursor mismatch")
    if len(roots) != 444 or len(proofs) != 16960:
        raise RuntimeError(f"frozen Merkle count mismatch roots={len(roots)} proofs={len(proofs)}")
    return {
        "roots": roots,
        "proofs": proofs,
        "seq_root_counts": seq_root_counts,
        "seq_proof_counts": seq_proof_counts,
    }


def prepare_mem(execution: dict, commitments: dict, merkle: dict, tmp: Path) -> dict[str, Path]:
    files = prepare_hw09_mem(execution, commitments, tmp)
    extra = {
        "seq_roots": tmp / "seq_roots.mem",
        "seq_proofs": tmp / "seq_proofs.mem",
        "root_data": tmp / "root_data.mem",
        "root_seq": tmp / "root_seq.mem",
        "root_tree": tmp / "root_tree.mem",
        "root_real": tmp / "root_real.mem",
        "proof_seq": tmp / "proof_seq.mem",
        "proof_tree": tmp / "proof_tree.mem",
        "proof_leaf": tmp / "proof_leaf.mem",
        "proof_level": tmp / "proof_level.mem",
        "proof_left": tmp / "proof_left.mem",
        "proof_sibling": tmp / "proof_sibling.mem",
    }
    write_mem(extra["seq_roots"], merkle["seq_root_counts"], 4)
    write_mem(extra["seq_proofs"], merkle["seq_proof_counts"], 8)
    write_mem(extra["root_data"], [x["root"] for x in merkle["roots"]], 64)
    write_mem(extra["root_seq"], [x["source_sequence"] for x in merkle["roots"]], 4)
    write_mem(extra["root_tree"], [x["tree_ordinal"] for x in merkle["roots"]], 4)
    write_mem(extra["root_real"], [x["real_leaf_count"] for x in merkle["roots"]], 2)
    write_mem(extra["proof_seq"], [x["source_sequence"] for x in merkle["proofs"]], 4)
    write_mem(extra["proof_tree"], [x["tree_ordinal"] for x in merkle["proofs"]], 4)
    write_mem(extra["proof_leaf"], [x["leaf_ordinal"] for x in merkle["proofs"]], 1)
    write_mem(extra["proof_level"], [x["level"] for x in merkle["proofs"]], 1)
    write_mem(extra["proof_left"], [x["sibling_is_left"] for x in merkle["proofs"]], 1)
    write_mem(extra["proof_sibling"], [x["sibling"] for x in merkle["proofs"]], 64)
    files.update(extra)
    return files


def make_tb(execution: dict, commitments: dict, merkle: dict, files: dict[str, Path]) -> str:
    return f'''`timescale 1ns/1ps
module cosmic_hw10_tb;
localparam integer TOTAL_SEQUENCES=320;
localparam integer TOTAL_TICKS=3840;
localparam integer TOTAL_RECEIPTS=41144;
localparam integer TOTAL_DIGESTS=4240;
localparam integer TOTAL_ROOTS=444;
localparam integer TOTAL_PROOFS=16960;
reg clk=0, reset=1, tick_valid=0, flush=0, tree_flush=0;
reg leaf_digest_ready=1, root_ready=1, proof_ready=1;
reg [511:0] stimulus_bus=0;
reg [15:0] source_sequence_id=0;
wire tick_ready;
wire [127:0] phase_bus; wire [63:0] active_mask,changed_mask,dirty_mask;
wire leaf_digest_valid; wire [255:0] leaf_digest_data; wire [15:0] leaf_digest_sequence;
wire root_valid; wire [255:0] root_data; wire [15:0] root_source_sequence,root_tree_ordinal; wire [4:0] root_real_leaf_count;
wire proof_valid; wire [15:0] proof_source_sequence,proof_tree_ordinal; wire [3:0] proof_leaf_ordinal; wire [1:0] proof_level;
wire proof_sibling_is_left; wire [255:0] proof_sibling_digest;
wire receipt_valid_out,receipt_ready_out,pending_observation_out; wire [39:0] receipt_data_out; wire [2:0] batch_occupancy_out;
wire [3:0] leaf_engine_busy_mask,leaf_engine_digest_valid_mask,leaf_engine_block_accept_mask;
wire [4:0] merkle_leaf_count_out; wire merkle_tree_busy_out,merkle_sha_busy_out; wire [7:0] merkle_sha_round_count_out;
wire merkle_parent_accept_pulse,root_emit_pulse,proof_emit_pulse;

reg [511:0] stim_mem[0:TOTAL_TICKS-1]; reg [127:0] state_mem[0:TOTAL_TICKS-1];
reg [63:0] active_mem[0:TOTAL_TICKS-1],changed_mem[0:TOTAL_TICKS-1],dirty_mem[0:TOTAL_TICKS-1];
reg [1:0] pattern_mem[0:TOTAL_SEQUENCES-1]; reg [2:0] group_mem[0:TOTAL_SEQUENCES-1];
reg [15:0] seq_receipt_mem[0:TOTAL_SEQUENCES-1],seq_digest_mem[0:TOTAL_SEQUENCES-1];
reg [15:0] seq_root_mem[0:TOTAL_SEQUENCES-1]; reg [31:0] seq_proof_mem[0:TOTAL_SEQUENCES-1];
reg [39:0] receipt_mem[0:TOTAL_RECEIPTS-1]; reg [255:0] digest_mem[0:TOTAL_DIGESTS-1]; reg [15:0] digest_seq_mem[0:TOTAL_DIGESTS-1];
reg [255:0] root_mem[0:TOTAL_ROOTS-1]; reg [15:0] root_seq_mem[0:TOTAL_ROOTS-1],root_tree_mem[0:TOTAL_ROOTS-1]; reg [7:0] root_real_mem[0:TOTAL_ROOTS-1];
reg [15:0] proof_seq_mem[0:TOTAL_PROOFS-1],proof_tree_mem[0:TOTAL_PROOFS-1]; reg [3:0] proof_leaf_mem[0:TOTAL_PROOFS-1],proof_level_mem[0:TOTAL_PROOFS-1];
reg proof_left_mem[0:TOTAL_PROOFS-1]; reg [255:0] proof_sibling_mem[0:TOTAL_PROOFS-1];

integer seq,local_tick,tick_index;
integer receipt_cursor=0,digest_cursor=0,root_cursor=0,proof_cursor=0;
integer seq_receipt_start,seq_digest_start,seq_root_start,seq_proof_start;
integer physical_cycle,physical_cycles_total=0,accepted_ticks=0,checks=0,watchdog,accept_now;
integer stalls_g0=0,stalls_g1=0,stalls_g2=0,stalls_g3=0,stalls_g4=0;
integer leaf_to_tree_stalls=0,root_sink_stalls=0,proof_sink_stalls=0;
integer merkle_sha_busy_cycles=0,parent_accepts=0,leaf_busy0=0,leaf_busy1=0,max_leaf_count=0;
always #5 clk=~clk;

cosmic_hw10_sparse_receipt_sha256x2_merkle16 dut(
 .clk(clk),.reset(reset),.tick_valid(tick_valid),.tick_ready(tick_ready),.stimulus_bus(stimulus_bus),.flush(flush),
 .source_sequence_id(source_sequence_id),.tree_flush(tree_flush),
 .phase_bus(phase_bus),.active_mask(active_mask),.changed_mask(changed_mask),.dirty_mask(dirty_mask),
 .leaf_digest_valid(leaf_digest_valid),.leaf_digest_ready(leaf_digest_ready),.leaf_digest_data(leaf_digest_data),.leaf_digest_sequence(leaf_digest_sequence),
 .root_valid(root_valid),.root_ready(root_ready),.root_data(root_data),.root_source_sequence(root_source_sequence),.root_tree_ordinal(root_tree_ordinal),.root_real_leaf_count(root_real_leaf_count),
 .proof_valid(proof_valid),.proof_ready(proof_ready),.proof_source_sequence(proof_source_sequence),.proof_tree_ordinal(proof_tree_ordinal),
 .proof_leaf_ordinal(proof_leaf_ordinal),.proof_level(proof_level),.proof_sibling_is_left(proof_sibling_is_left),.proof_sibling_digest(proof_sibling_digest),
 .receipt_valid_out(receipt_valid_out),.receipt_ready_out(receipt_ready_out),.receipt_data_out(receipt_data_out),.batch_occupancy_out(batch_occupancy_out),.pending_observation_out(pending_observation_out),
 .leaf_engine_busy_mask(leaf_engine_busy_mask),.leaf_engine_digest_valid_mask(leaf_engine_digest_valid_mask),.leaf_engine_block_accept_mask(leaf_engine_block_accept_mask),
 .merkle_leaf_count_out(merkle_leaf_count_out),.merkle_tree_busy_out(merkle_tree_busy_out),.merkle_sha_busy_out(merkle_sha_busy_out),.merkle_sha_round_count_out(merkle_sha_round_count_out),
 .merkle_parent_accept_pulse(merkle_parent_accept_pulse),.root_emit_pulse(root_emit_pulse),.proof_emit_pulse(proof_emit_pulse));

function ready_for_cycle; input [1:0] pattern; input integer cycle; begin
 case(pattern)
  2'd0: ready_for_cycle=1'b1;
  2'd1: ready_for_cycle=((cycle%4)!=3);
  2'd2: ready_for_cycle=((cycle%2)==0);
  2'd3: ready_for_cycle=((cycle%16)>=8);
  default: ready_for_cycle=1'b0;
 endcase
end endfunction

task note_stall; input [2:0] group; begin
 case(group)
  3'd0: stalls_g0=stalls_g0+1; 3'd1: stalls_g1=stalls_g1+1; 3'd2: stalls_g2=stalls_g2+1;
  3'd3: stalls_g3=stalls_g3+1; default: stalls_g4=stalls_g4+1;
 endcase
end endtask

task set_ready; input [1:0] pattern; begin
 leaf_digest_ready=ready_for_cycle(pattern,physical_cycle);
 root_ready=ready_for_cycle(pattern,physical_cycle);
 proof_ready=ready_for_cycle(pattern,physical_cycle);
end endtask

always @(posedge clk) begin
 if(!reset) begin
  if(receipt_valid_out && receipt_ready_out) begin
   if(receipt_cursor>=TOTAL_RECEIPTS) $fatal(1,"phantom receipt");
   if(receipt_data_out!==receipt_mem[receipt_cursor]) $fatal(1,"receipt mismatch idx=%0d got=%h exp=%h",receipt_cursor,receipt_data_out,receipt_mem[receipt_cursor]);
   receipt_cursor=receipt_cursor+1; checks=checks+1;
  end
  if(leaf_digest_valid && leaf_digest_ready) begin
   if(digest_cursor>=TOTAL_DIGESTS) $fatal(1,"phantom leaf digest");
   if(leaf_digest_data!==digest_mem[digest_cursor]) $fatal(1,"leaf digest mismatch idx=%0d",digest_cursor);
   if(leaf_digest_sequence!==digest_seq_mem[digest_cursor]) $fatal(1,"leaf digest sequence mismatch idx=%0d got=%0d exp=%0d",digest_cursor,leaf_digest_sequence,digest_seq_mem[digest_cursor]);
   digest_cursor=digest_cursor+1; checks=checks+2;
  end
  if(root_valid && root_ready) begin
   if(root_cursor>=TOTAL_ROOTS) $fatal(1,"phantom root");
   if(root_data!==root_mem[root_cursor]) $fatal(1,"root mismatch idx=%0d got=%064h exp=%064h",root_cursor,root_data,root_mem[root_cursor]);
   if(root_source_sequence!==root_seq_mem[root_cursor]) $fatal(1,"root source mismatch idx=%0d",root_cursor);
   if(root_tree_ordinal!==root_tree_mem[root_cursor]) $fatal(1,"root tree mismatch idx=%0d",root_cursor);
   if(root_real_leaf_count!==root_real_mem[root_cursor][4:0]) $fatal(1,"root real count mismatch idx=%0d",root_cursor);
   root_cursor=root_cursor+1; checks=checks+4;
  end
  if(proof_valid && proof_ready) begin
   if(proof_cursor>=TOTAL_PROOFS) $fatal(1,"phantom proof");
   if(proof_source_sequence!==proof_seq_mem[proof_cursor]) $fatal(1,"proof source mismatch idx=%0d",proof_cursor);
   if(proof_tree_ordinal!==proof_tree_mem[proof_cursor]) $fatal(1,"proof tree mismatch idx=%0d",proof_cursor);
   if(proof_leaf_ordinal!==proof_leaf_mem[proof_cursor]) $fatal(1,"proof leaf mismatch idx=%0d",proof_cursor);
   if(proof_level!==proof_level_mem[proof_cursor][1:0]) $fatal(1,"proof level mismatch idx=%0d",proof_cursor);
   if(proof_sibling_is_left!==proof_left_mem[proof_cursor]) $fatal(1,"proof side mismatch idx=%0d",proof_cursor);
   if(proof_sibling_digest!==proof_sibling_mem[proof_cursor]) $fatal(1,"proof sibling mismatch idx=%0d",proof_cursor);
   proof_cursor=proof_cursor+1; checks=checks+6;
  end
  if(dut.inner_digest_valid && leaf_digest_ready && !dut.merkle_leaf_ready) leaf_to_tree_stalls=leaf_to_tree_stalls+1;
  if(root_valid && !root_ready) root_sink_stalls=root_sink_stalls+1;
  if(proof_valid && !proof_ready) proof_sink_stalls=proof_sink_stalls+1;
  if(merkle_sha_busy_out) merkle_sha_busy_cycles=merkle_sha_busy_cycles+1;
  if(merkle_parent_accept_pulse) parent_accepts=parent_accepts+1;
  if(leaf_engine_busy_mask[0]) leaf_busy0=leaf_busy0+1;
  if(leaf_engine_busy_mask[1]) leaf_busy1=leaf_busy1+1;
  if(merkle_leaf_count_out>max_leaf_count) max_leaf_count=merkle_leaf_count_out;
 end
end

task reset_sequence; input integer seq_id; begin
 tick_valid=0; flush=0; tree_flush=0; stimulus_bus=0; leaf_digest_ready=1; root_ready=1; proof_ready=1; reset=1; source_sequence_id=seq_id;
 repeat(3) @(posedge clk); @(negedge clk); reset=0; physical_cycle=0;
end endtask

task advance_cycle; input [1:0] pattern; begin
 @(negedge clk); set_ready(pattern);
 @(posedge clk); #1; physical_cycle=physical_cycle+1; physical_cycles_total=physical_cycles_total+1;
end endtask

task drive_tick; input integer idx; input [1:0] pattern; input [2:0] group; begin
 watchdog=0; accept_now=0;
 while(!accept_now) begin
  @(negedge clk); set_ready(pattern); stimulus_bus=stim_mem[idx]; tick_valid=1;
  accept_now=tick_ready; if(!tick_ready) note_stall(group);
  @(posedge clk); #1; physical_cycle=physical_cycle+1; physical_cycles_total=physical_cycles_total+1; watchdog=watchdog+1;
  if(watchdog>500000) $fatal(1,"tick watchdog seq=%0d tick=%0d",seq,idx);
 end
 tick_valid=0; accepted_ticks=accepted_ticks+1;
 if(phase_bus!==state_mem[idx]) $fatal(1,"state mismatch tick=%0d",idx);
 if(active_mask!==active_mem[idx]) $fatal(1,"active mismatch tick=%0d",idx);
 if(changed_mask!==changed_mem[idx]) $fatal(1,"changed mismatch tick=%0d",idx);
 if(dirty_mask!==dirty_mem[idx]) $fatal(1,"dirty mismatch tick=%0d",idx);
 checks=checks+4;
end endtask

task finish_sequence; input [1:0] pattern; input integer exp_receipts; input integer exp_digests; input integer exp_roots; input integer exp_proofs; begin
 watchdog=0; tick_valid=0; flush=0; tree_flush=0;
 // Drain transition receipts first.
 while((receipt_cursor-seq_receipt_start)<exp_receipts || batch_occupancy_out!=0 || pending_observation_out || receipt_valid_out) begin
  advance_cycle(pattern); watchdog=watchdog+1; if(watchdog>1000000) $fatal(1,"receipt drain watchdog seq=%0d",seq);
 end
 // Close the final partial 10-receipt commitment, matching HW-09.
 if(dut.fill_count_unused!=0) begin
  while(dut.waiting_unused) advance_cycle(pattern);
  @(negedge clk); set_ready(pattern); flush=1;
  @(posedge clk); #1; physical_cycle=physical_cycle+1; physical_cycles_total=physical_cycles_total+1;
  @(negedge clk); flush=0;
 end
 // Allow all expected leaf commitments to retire through the frozen external
 // ready pattern AND the finite Merkle collector.
 watchdog=0;
 while((digest_cursor-seq_digest_start)<exp_digests) begin
  advance_cycle(pattern); watchdog=watchdog+1; if(watchdog>3000000) $fatal(1,"leaf digest watchdog seq=%0d",seq);
 end
 // Close the final partial Merkle-16 group after the final leaf handshake.
 if(!merkle_tree_busy_out && merkle_leaf_count_out!=0) begin
  @(negedge clk); set_ready(pattern); tree_flush=1;
  @(posedge clk); #1; physical_cycle=physical_cycle+1; physical_cycles_total=physical_cycles_total+1;
  @(negedge clk); tree_flush=0;
 end
 // Drain root + all inclusion fragments before this source-sequence reset.
 watchdog=0;
 while((root_cursor-seq_root_start)<exp_roots || (proof_cursor-seq_proof_start)<exp_proofs || merkle_tree_busy_out || merkle_leaf_count_out!=0 || leaf_engine_busy_mask!=0 || leaf_engine_digest_valid_mask!=0) begin
  advance_cycle(pattern); watchdog=watchdog+1; if(watchdog>5000000) $fatal(1,"Merkle drain watchdog seq=%0d",seq);
 end
 if((receipt_cursor-seq_receipt_start)!=exp_receipts) $fatal(1,"seq receipt count mismatch seq=%0d",seq);
 if((digest_cursor-seq_digest_start)!=exp_digests) $fatal(1,"seq digest count mismatch seq=%0d",seq);
 if((root_cursor-seq_root_start)!=exp_roots) $fatal(1,"seq root count mismatch seq=%0d",seq);
 if((proof_cursor-seq_proof_start)!=exp_proofs) $fatal(1,"seq proof count mismatch seq=%0d",seq);
end endtask

initial begin
 $readmemh("{files['stimulus']}",stim_mem); $readmemh("{files['state']}",state_mem); $readmemh("{files['active']}",active_mem);
 $readmemh("{files['changed']}",changed_mem); $readmemh("{files['dirty']}",dirty_mem); $readmemh("{files['pattern']}",pattern_mem); $readmemh("{files['group']}",group_mem);
 $readmemh("{files['seq_receipts']}",seq_receipt_mem); $readmemh("{files['seq_digests']}",seq_digest_mem); $readmemh("{files['seq_roots']}",seq_root_mem); $readmemh("{files['seq_proofs']}",seq_proof_mem);
 $readmemh("{files['receipts']}",receipt_mem); $readmemh("{files['digests']}",digest_mem); $readmemh("{files['digest_seq']}",digest_seq_mem);
 $readmemh("{files['root_data']}",root_mem); $readmemh("{files['root_seq']}",root_seq_mem); $readmemh("{files['root_tree']}",root_tree_mem); $readmemh("{files['root_real']}",root_real_mem);
 $readmemh("{files['proof_seq']}",proof_seq_mem); $readmemh("{files['proof_tree']}",proof_tree_mem); $readmemh("{files['proof_leaf']}",proof_leaf_mem); $readmemh("{files['proof_level']}",proof_level_mem); $readmemh("{files['proof_left']}",proof_left_mem); $readmemh("{files['proof_sibling']}",proof_sibling_mem);
 for(seq=0;seq<TOTAL_SEQUENCES;seq=seq+1) begin
  reset_sequence(seq); seq_receipt_start=receipt_cursor; seq_digest_start=digest_cursor; seq_root_start=root_cursor; seq_proof_start=proof_cursor;
  for(local_tick=0;local_tick<12;local_tick=local_tick+1) begin tick_index=seq*12+local_tick; drive_tick(tick_index,pattern_mem[seq],group_mem[seq]); end
  finish_sequence(pattern_mem[seq],seq_receipt_mem[seq],seq_digest_mem[seq],seq_root_mem[seq],seq_proof_mem[seq]);
 end
 if(receipt_cursor!=TOTAL_RECEIPTS) $fatal(1,"global receipt count mismatch");
 if(digest_cursor!=TOTAL_DIGESTS) $fatal(1,"global digest count mismatch");
 if(root_cursor!=TOTAL_ROOTS) $fatal(1,"global root count mismatch");
 if(proof_cursor!=TOTAL_PROOFS) $fatal(1,"global proof count mismatch");
 if(parent_accepts!=6660) $fatal(1,"parent hash count mismatch got=%0d exp=6660",parent_accepts);
 if(merkle_sha_busy_cycles!=852480) $fatal(1,"Merkle busy-cycle mismatch got=%0d exp=852480",merkle_sha_busy_cycles);
 $display("COSMIC_HW10_SIM PASS sequences=320 ticks=%0d receipts=%0d digests=%0d roots=%0d proofs=%0d parent_hashes=%0d checks=%0d physical_cycles=%0d leaf_to_tree_stalls=%0d root_sink_stalls=%0d proof_sink_stalls=%0d merkle_sha_busy_cycles=%0d leaf_busy0=%0d leaf_busy1=%0d max_leaf_count=%0d stalls_g0=%0d stalls_g1=%0d stalls_g2=%0d stalls_g3=%0d stalls_g4=%0d",
 accepted_ticks,receipt_cursor,digest_cursor,root_cursor,proof_cursor,parent_accepts,checks,physical_cycles_total,leaf_to_tree_stalls,root_sink_stalls,proof_sink_stalls,merkle_sha_busy_cycles,leaf_busy0,leaf_busy1,max_leaf_count,stalls_g0,stalls_g1,stalls_g2,stalls_g3,stalls_g4);
 $finish;
end
endmodule
'''


def parse_sim(text: str) -> dict:
    pat = re.compile(
        r"COSMIC_HW10_SIM PASS sequences=(\d+) ticks=(\d+) receipts=(\d+) digests=(\d+) roots=(\d+) proofs=(\d+) parent_hashes=(\d+) checks=(\d+) "
        r"physical_cycles=(\d+) leaf_to_tree_stalls=(\d+) root_sink_stalls=(\d+) proof_sink_stalls=(\d+) merkle_sha_busy_cycles=(\d+) "
        r"leaf_busy0=(\d+) leaf_busy1=(\d+) max_leaf_count=(\d+) stalls_g0=(\d+) stalls_g1=(\d+) stalls_g2=(\d+) stalls_g3=(\d+) stalls_g4=(\d+)"
    )
    m = pat.search(text)
    if not m:
        raise RuntimeError("COSMIC-HW-10 PASS marker not found\n" + text)
    v = list(map(int, m.groups()))
    return {
        "sequences": v[0], "accepted_ticks": v[1], "receipts_emitted": v[2], "leaf_digests_emitted": v[3],
        "roots_emitted": v[4], "proof_fragments_emitted": v[5], "parent_hashes": v[6], "checks": v[7],
        "physical_cycles": v[8], "leaf_to_tree_stalls": v[9], "root_sink_stalls": v[10], "proof_sink_stalls": v[11],
        "merkle_sha_busy_cycles": v[12], "leaf_engine_busy_cycles": [v[13], v[14]], "max_tree_buffer_occupancy": v[15],
        "backpressure_stalls": {"0.01": v[16], "0.05": v[17], "0.20": v[18], "1.00": v[19], "stress": v[20]},
    }


def simulate_candidate(root: Path, execution: dict, commitments: dict, merkle: dict, tmp: Path) -> dict:
    files = prepare_mem(execution, commitments, merkle, tmp)
    tb = tmp / "tb_hw10.v"
    tb.write_text(make_tb(execution, commitments, merkle, files), encoding="utf-8")
    sim = tmp / "sim_hw10.out"
    run_cmd([
        require_tool("iverilog"), "-g2012", "-s", "cosmic_hw10_tb", "-o", str(sim),
        str(root / "rtl" / "cosmic_hw_06.v"), str(root / "rtl" / "cosmic_hw_07_receipt.v"),
        str(root / "rtl" / "cosmic_hw_08_sha256.v"), str(root / "rtl" / "cosmic_hw_09_multi_sha.v"),
        str(root / "rtl" / "cosmic_hw_10_merkle.v"), str(tb),
    ])
    return parse_sim(run_cmd([require_tool("vvp"), str(sim)]))


def synthesize_candidate(yosys: str, root: Path, tmp: Path) -> dict:
    top = "cosmic_hw10_sparse_receipt_sha256x2_merkle16"
    sources = " ".join(str(root / "rtl" / name) for name in (
        "cosmic_hw_06.v", "cosmic_hw_07_receipt.v", "cosmic_hw_08_sha256.v", "cosmic_hw_09_multi_sha.v", "cosmic_hw_10_merkle.v"
    ))
    json_path = tmp / "hw10.json"
    run_cmd([yosys, "-q", "-p", f"read_verilog -sv {sources}; hierarchy -check -top {top}; flatten; synth_xilinx -family xc7 -top {top}; write_json {json_path}"])
    row = cell_counts_from_json(json_path, top)
    depth_text = run_cmd([yosys, "-p", f"read_verilog -sv {sources}; hierarchy -check -top {top}; proc; memory_map; opt; flatten; opt; ltp -noff"])
    row["logic_depth_proxy"] = parse_ltp(depth_text)
    return row


def run() -> dict:
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "benchmarks" / "cosmic_hw_10_manifest.json").read_text())
    if manifest["experiment_id"] != PROTOCOL:
        raise RuntimeError("frozen HW-10 manifest mismatch")
    if not (root / "rtl" / "cosmic_hw_10_merkle.v").exists():
        raise RuntimeError("HW-10 candidate RTL missing")

    execution = build_oracle()
    commitments = expected_commitments(execution)
    merkle = expected_merkle(execution, commitments)
    yosys = require_tool("yosys")

    with tempfile.TemporaryDirectory(prefix="cosmic-hw-10-") as td:
        tmp = Path(td)
        control_sim = simulate_hw09_candidate(root, execution, commitments, 2, "cosmic_hw09_sparse_receipt_sha256x2", tmp)
        if control_sim["backpressure_stalls"] != FROZEN_X2_STALLS or control_sim["physical_cycles"] != 148926:
            return {"benchmark_id": BENCHMARK_ID, "protocol": PROTOCOL, "decision": "CONTROL_FAILURE", "control_simulation": control_sim}
        control_synth = synthesize_hw09_multi(yosys, root, "cosmic_hw09_sparse_receipt_sha256x2", tmp)
        candidate_sim = simulate_candidate(root, execution, commitments, merkle, tmp)
        if (
            candidate_sim["sequences"] != 320 or candidate_sim["accepted_ticks"] != 3840
            or candidate_sim["receipts_emitted"] != 41144 or candidate_sim["leaf_digests_emitted"] != 4240
            or candidate_sim["roots_emitted"] != 444 or candidate_sim["proof_fragments_emitted"] != 16960
            or candidate_sim["parent_hashes"] != 6660 or candidate_sim["merkle_sha_busy_cycles"] != 852480
        ):
            return {"benchmark_id": BENCHMARK_ID, "protocol": PROTOCOL, "decision": "MERKLE_SEMANTIC_FAILURE", "simulation": candidate_sim}
        candidate_synth = synthesize_candidate(yosys, root, tmp)

    def delta(key: str) -> dict:
        a = control_synth[key]
        b = candidate_synth[key]
        return {"absolute": b-a, "fraction": ((b-a)/a if a else None)}

    return {
        "benchmark_id": BENCHMARK_ID,
        "protocol": PROTOCOL,
        "decision": "MERKLE_INCLUSION_COST_MEASURED",
        "control": {"simulation": control_sim, "synthesis": control_synth},
        "candidate": {
            "simulation": candidate_sim,
            "synthesis": candidate_synth,
            "root_match_fraction": 1.0,
            "proof_fragment_match_fraction": 1.0,
            "independently_verified_proof_fraction": 1.0,
            "real_leaves": 4240,
            "padding_leaves": 2864,
            "tree_count": 444,
            "parent_hashes": 6660,
            "parent_compression_blocks": 13320,
            "parent_sha_rounds": 852480,
            "declared_merkle_node_storage_bits": 7936,
            "declared_merkle_sha_state_bits": 3346,
            "declared_proof_serializer_index_bits": 6,
        },
        "structural_delta": {key: delta(key) for key in ("lut", "ff", "core_cells_excluding_io", "logic_depth_proxy")},
        "synthetic_combined_score_used": False,
        "claim_boundary": "Icarus functional simulation + Yosys Xilinx-7 structural mapping; Merkle-16 root and inclusion-path cost only.",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    result = run()
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else result)


if __name__ == "__main__":
    main()
