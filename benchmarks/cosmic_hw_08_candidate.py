from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile

from benchmarks.cosmic_hw_08_kat import canonical_message, kat_fingerprint
from benchmarks.cosmic_hw_07_candidate import (
    build_oracle,
    require_tool,
    run_cmd,
    synthesize,
)

BENCHMARK_ID = "COSMIC-HW-08-CANDIDATE"
PROTOCOL = "COSMIC-HW-08/v0.1"
FROZEN_KAT_FINGERPRINT = "3919530f4fb110bb453429fb50d8f6c6f664cf9506f5391a4b3a1e9fac5d5bbd"
FROZEN_CONTROL_STALLS = {"0.01": 0, "0.05": 542, "0.20": 4506, "1.00": 5212, "stress": 15298}


def write_mem(path: Path, values, width: int) -> None:
    path.write_text("".join(f"{int(v):0{width}x}\n" for v in values), encoding="utf-8")


def expected_commitments(oracle: dict) -> dict:
    receipts = oracle["receipts"]
    digests: list[int] = []
    digest_sequences: list[int] = []
    seq_digest_counts: list[int] = []
    full_blocks = 0
    partial_blocks = 0
    offset = 0
    for row in oracle["sequences"]:
        count = row["receipt_count"]
        local = receipts[offset: offset + count]
        offset += count
        seq_count = 0
        for start in range(0, len(local), 10):
            chunk = local[start:start + 10]
            if not chunk:
                continue
            sequence = seq_count
            msg = canonical_message(sequence, chunk)
            digests.append(int.from_bytes(hashlib.sha256(msg).digest(), "big"))
            digest_sequences.append(sequence)
            seq_count += 1
            if len(chunk) == 10:
                full_blocks += 1
            else:
                partial_blocks += 1
        seq_digest_counts.append(seq_count)
    assert offset == len(receipts)
    return {
        "digests": digests,
        "digest_sequences": digest_sequences,
        "seq_digest_counts": seq_digest_counts,
        "full_blocks": full_blocks,
        "partial_blocks": partial_blocks,
    }


def make_tb(oracle: dict, commits: dict, tmp: Path) -> str:
    ticks = oracle["ticks"]
    seqs = oracle["sequences"]
    receipts = oracle["receipts"]
    digests = commits["digests"]

    files = {
        "stimulus": tmp / "stimulus.mem",
        "state": tmp / "state.mem",
        "active": tmp / "active.mem",
        "changed": tmp / "changed.mem",
        "dirty": tmp / "dirty.mem",
        "pattern": tmp / "pattern.mem",
        "group": tmp / "group.mem",
        "seq_receipts": tmp / "seq_receipts.mem",
        "receipts": tmp / "receipts.mem",
        "seq_digests": tmp / "seq_digests.mem",
        "digests": tmp / "digests.mem",
        "digest_seq": tmp / "digest_seq.mem",
    }
    write_mem(files["stimulus"], [x["stimulus"] for x in ticks], 128)
    write_mem(files["state"], [x["state"] for x in ticks], 32)
    write_mem(files["active"], [x["active"] for x in ticks], 16)
    write_mem(files["changed"], [x["changed"] for x in ticks], 16)
    write_mem(files["dirty"], [x["dirty"] for x in ticks], 16)
    write_mem(files["pattern"], [x["ready_pattern_id"] for x in seqs], 1)
    write_mem(files["group"], [x["group"] for x in seqs], 1)
    write_mem(files["seq_receipts"], [x["receipt_count"] for x in seqs], 4)
    write_mem(files["receipts"], receipts, 10)
    write_mem(files["seq_digests"], commits["seq_digest_counts"], 4)
    write_mem(files["digests"], digests, 64)
    write_mem(files["digest_seq"], commits["digest_sequences"], 4)

    return f'''`timescale 1ns/1ps
module cosmic_hw08_tb;
localparam integer TOTAL_SEQUENCES=320;
localparam integer TOTAL_TICKS=3840;
localparam integer TOTAL_RECEIPTS={len(receipts)};
localparam integer TOTAL_DIGESTS={len(digests)};
reg clk=0, reset=1, tick_valid=0, flush=0, digest_ready=1;
reg [511:0] stimulus_bus=0;
wire tick_ready, digest_valid, waiting_valid, sha_busy;
wire [255:0] digest_data; wire [15:0] digest_sequence;
wire [127:0] phase_bus; wire [63:0] active_mask, changed_mask, dirty_mask;
wire [3:0] fill_count; wire [6:0] sha_round_count;
reg [511:0] stim_mem[0:TOTAL_TICKS-1];
reg [127:0] state_mem[0:TOTAL_TICKS-1];
reg [63:0] active_mem[0:TOTAL_TICKS-1], changed_mem[0:TOTAL_TICKS-1], dirty_mem[0:TOTAL_TICKS-1];
reg [1:0] pattern_mem[0:TOTAL_SEQUENCES-1]; reg [2:0] group_mem[0:TOTAL_SEQUENCES-1];
reg [15:0] seq_receipt_mem[0:TOTAL_SEQUENCES-1]; reg [39:0] receipt_mem[0:TOTAL_RECEIPTS-1];
reg [15:0] seq_digest_mem[0:TOTAL_SEQUENCES-1], digest_seq_mem[0:TOTAL_DIGESTS-1];
reg [255:0] digest_mem[0:TOTAL_DIGESTS-1];
integer seq, local_tick, tick_index=0, receipt_cursor=0, digest_cursor=0;
integer seq_receipt_start, seq_digest_start, physical_cycle, physical_cycles_total=0;
integer accepted_ticks=0, checks=0, sha_busy_cycles=0, digest_sink_stalls=0, assembler_stalls=0;
integer stalls_g0=0, stalls_g1=0, stalls_g2=0, stalls_g3=0, stalls_g4=0;
integer max_waiting=0, watchdog, accept_now;
always #5 clk=~clk;

cosmic_hw08_sparse_receipt_sha256 dut(
 .clk(clk),.reset(reset),.tick_valid(tick_valid),.tick_ready(tick_ready),.stimulus_bus(stimulus_bus),.flush(flush),
 .phase_bus(phase_bus),.active_mask(active_mask),.changed_mask(changed_mask),.dirty_mask(dirty_mask),
 .digest_valid(digest_valid),.digest_ready(digest_ready),.digest_data(digest_data),.digest_sequence(digest_sequence),
 .fill_count_out(fill_count),.waiting_block_valid_out(waiting_valid),.sha_busy(sha_busy),.sha_round_count(sha_round_count));

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

always @(negedge clk) begin
 if(!reset) begin
  if(dut.receipt_valid && dut.receipt_ready) begin
   if(receipt_cursor>=TOTAL_RECEIPTS) $fatal(1,"phantom receipt");
   if(dut.receipt_data!==receipt_mem[receipt_cursor]) $fatal(1,"receipt mismatch idx=%0d got=%h exp=%h",receipt_cursor,dut.receipt_data,receipt_mem[receipt_cursor]);
   receipt_cursor=receipt_cursor+1; checks=checks+1;
  end
  if(digest_valid && digest_ready) begin
   if(digest_cursor>=TOTAL_DIGESTS) $fatal(1,"phantom digest");
   if(digest_data!==digest_mem[digest_cursor]) $fatal(1,"digest mismatch idx=%0d",digest_cursor);
   if(digest_sequence!==digest_seq_mem[digest_cursor]) $fatal(1,"digest sequence mismatch idx=%0d got=%0d exp=%0d",digest_cursor,digest_sequence,digest_seq_mem[digest_cursor]);
   digest_cursor=digest_cursor+1; checks=checks+2;
  end
  if(sha_busy) sha_busy_cycles=sha_busy_cycles+1;
  if(digest_valid && !digest_ready) digest_sink_stalls=digest_sink_stalls+1;
  if(dut.receipt_valid && !dut.receipt_ready) assembler_stalls=assembler_stalls+1;
  if(waiting_valid) max_waiting=1;
 end
end

task reset_sequence; begin
 tick_valid=0; flush=0; digest_ready=1; stimulus_bus=0; reset=1;
 repeat(3) @(posedge clk); @(negedge clk); reset=0; physical_cycle=0;
end endtask

task drive_tick; input integer idx; input [1:0] pattern; input [2:0] group; begin
 watchdog=0; accept_now=0;
 while(!accept_now) begin
  @(negedge clk); digest_ready=ready_for_cycle(pattern,physical_cycle); stimulus_bus=stim_mem[idx]; tick_valid=1;
  accept_now=tick_ready;
  if(!tick_ready) note_stall(group);
  @(posedge clk); #1; physical_cycle=physical_cycle+1; physical_cycles_total=physical_cycles_total+1; watchdog=watchdog+1;
  if(watchdog>100000) $fatal(1,"tick watchdog seq=%0d tick=%0d",seq,idx);
 end
 tick_valid=0; accepted_ticks=accepted_ticks+1;
 if(phase_bus!==state_mem[idx]) $fatal(1,"state mismatch tick=%0d",idx);
 if(active_mask!==active_mem[idx]) $fatal(1,"active mismatch tick=%0d",idx);
 if(changed_mask!==changed_mem[idx]) $fatal(1,"changed mismatch tick=%0d",idx);
 if(dirty_mask!==dirty_mem[idx]) $fatal(1,"dirty mismatch tick=%0d",idx);
 checks=checks+4;
end endtask

task drain_sequence; input [1:0] pattern; input [2:0] group; input integer expected_receipts; input integer expected_digests; begin
 tick_valid=0; flush=0; watchdog=0;
 while((receipt_cursor-seq_receipt_start)<expected_receipts || dut.batch_occupancy!=0 || dut.pending_observation || dut.receipt_valid) begin
  @(negedge clk); digest_ready=ready_for_cycle(pattern,physical_cycle);
  @(posedge clk); #1; physical_cycle=physical_cycle+1; physical_cycles_total=physical_cycles_total+1; watchdog=watchdog+1;
  if(watchdog>200000) $fatal(1,"receipt drain watchdog seq=%0d",seq);
 end
 if(fill_count!=0) begin
  while(waiting_valid) begin
   @(negedge clk); digest_ready=ready_for_cycle(pattern,physical_cycle);
   @(posedge clk); #1; physical_cycle=physical_cycle+1; physical_cycles_total=physical_cycles_total+1;
  end
  @(negedge clk); flush=1; digest_ready=ready_for_cycle(pattern,physical_cycle);
  @(posedge clk); #1; flush=0; physical_cycle=physical_cycle+1; physical_cycles_total=physical_cycles_total+1;
 end
 watchdog=0;
 while((digest_cursor-seq_digest_start)<expected_digests || fill_count!=0 || waiting_valid || sha_busy || digest_valid) begin
  @(negedge clk); digest_ready=ready_for_cycle(pattern,physical_cycle);
  @(posedge clk); #1; physical_cycle=physical_cycle+1; physical_cycles_total=physical_cycles_total+1; watchdog=watchdog+1;
  if(watchdog>500000) $fatal(1,"digest drain watchdog seq=%0d",seq);
 end
 if((receipt_cursor-seq_receipt_start)!=expected_receipts) $fatal(1,"receipt count mismatch seq=%0d",seq);
 if((digest_cursor-seq_digest_start)!=expected_digests) $fatal(1,"digest count mismatch seq=%0d",seq);
end endtask

initial begin
 $readmemh("{files['stimulus']}",stim_mem); $readmemh("{files['state']}",state_mem); $readmemh("{files['active']}",active_mem);
 $readmemh("{files['changed']}",changed_mem); $readmemh("{files['dirty']}",dirty_mem); $readmemh("{files['pattern']}",pattern_mem);
 $readmemh("{files['group']}",group_mem); $readmemh("{files['seq_receipts']}",seq_receipt_mem); $readmemh("{files['receipts']}",receipt_mem);
 $readmemh("{files['seq_digests']}",seq_digest_mem); $readmemh("{files['digests']}",digest_mem); $readmemh("{files['digest_seq']}",digest_seq_mem);
 for(seq=0;seq<TOTAL_SEQUENCES;seq=seq+1) begin
  reset_sequence(); seq_receipt_start=receipt_cursor; seq_digest_start=digest_cursor;
  for(local_tick=0;local_tick<12;local_tick=local_tick+1) begin tick_index=seq*12+local_tick; drive_tick(tick_index,pattern_mem[seq],group_mem[seq]); end
  drain_sequence(pattern_mem[seq],group_mem[seq],seq_receipt_mem[seq],seq_digest_mem[seq]);
 end
 if(receipt_cursor!=TOTAL_RECEIPTS) $fatal(1,"global receipt mismatch got=%0d exp=%0d",receipt_cursor,TOTAL_RECEIPTS);
 if(digest_cursor!=TOTAL_DIGESTS) $fatal(1,"global digest mismatch got=%0d exp=%0d",digest_cursor,TOTAL_DIGESTS);
 $display("COSMIC_HW08_SIM PASS checks=%0d sequences=320 ticks=%0d receipts=%0d digests=%0d physical_cycles=%0d sha_busy=%0d digest_sink_stalls=%0d assembler_stalls=%0d stalls_g0=%0d stalls_g1=%0d stalls_g2=%0d stalls_g3=%0d stalls_g4=%0d max_waiting=%0d",
 checks,accepted_ticks,receipt_cursor,digest_cursor,physical_cycles_total,sha_busy_cycles,digest_sink_stalls,assembler_stalls,
 stalls_g0,stalls_g1,stalls_g2,stalls_g3,stalls_g4,max_waiting);
 $finish;
end
endmodule
'''


def parse_sim(text: str) -> dict:
    pat = re.compile(
        r"COSMIC_HW08_SIM PASS checks=(\d+) sequences=(\d+) ticks=(\d+) receipts=(\d+) digests=(\d+) "
        r"physical_cycles=(\d+) sha_busy=(\d+) digest_sink_stalls=(\d+) assembler_stalls=(\d+) "
        r"stalls_g0=(\d+) stalls_g1=(\d+) stalls_g2=(\d+) stalls_g3=(\d+) stalls_g4=(\d+) max_waiting=(\d+)"
    )
    m = pat.search(text)
    if not m:
        raise RuntimeError("COSMIC-HW-08 PASS marker not found\n" + text)
    v = list(map(int, m.groups()))
    return {
        "checks": v[0], "sequences": v[1], "accepted_ticks": v[2], "receipts_emitted": v[3], "digests_emitted": v[4],
        "physical_cycles": v[5], "sha_busy_cycles": v[6], "digest_sink_stalls": v[7], "assembler_stalls": v[8],
        "backpressure_stalls": {"0.01": v[9], "0.05": v[10], "0.20": v[11], "1.00": v[12], "stress": v[13]},
        "max_pending_block_occupancy": v[14],
    }


def run() -> dict:
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "benchmarks" / "cosmic_hw_08_manifest.json").read_text())
    if manifest["experiment_id"] != PROTOCOL:
        raise RuntimeError("HW-08 manifest mismatch")
    if kat_fingerprint() != FROZEN_KAT_FINGERPRINT:
        raise RuntimeError("frozen KAT fingerprint changed")
    oracle = build_oracle()
    commits = expected_commitments(oracle)
    iverilog, vvp, yosys = require_tool("iverilog"), require_tool("vvp"), require_tool("yosys")
    rtl06 = root / "rtl" / "cosmic_hw_06.v"
    rtl07 = root / "rtl" / "cosmic_hw_07_receipt.v"
    rtl08 = root / "rtl" / "cosmic_hw_08_sha256.v"
    with tempfile.TemporaryDirectory(prefix="cosmic-hw-08-") as td:
        tmp = Path(td)
        tb = tmp / "tb.v"; tb.write_text(make_tb(oracle, commits, tmp), encoding="utf-8")
        sim = tmp / "sim.out"
        run_cmd([iverilog, "-g2012", "-s", "cosmic_hw08_tb", "-o", str(sim), str(rtl06), str(rtl07), str(rtl08), str(tb)])
        simulation = parse_sim(run_cmd([vvp, str(sim)]))
        control_synth = synthesize(yosys, rtl06, rtl07, "cosmic_hw07_sparse_receipt_mesh64", tmp)
        combined = tmp / "receipt_sha.v"
        combined.write_text(rtl07.read_text() + "\n" + rtl08.read_text(), encoding="utf-8")
        sha_synth = synthesize(yosys, rtl06, combined, "cosmic_hw08_sparse_receipt_sha256", tmp)
    expected_receipts = len(oracle["receipts"])
    expected_digests = len(commits["digests"])
    semantic_ok = (
        simulation["accepted_ticks"] == 3840
        and simulation["receipts_emitted"] == expected_receipts
        and simulation["digests_emitted"] == expected_digests
    )
    decision = "SHA256_COMMITMENT_COST_MEASURED" if semantic_ok else "SHA256_SEMANTIC_FAILURE"
    metrics = ("lut", "ff", "bram", "lutram", "core_cells_excluding_io", "logic_depth_proxy")
    delta = {k: sha_synth[k] - control_synth[k] for k in metrics}
    return {
        "benchmark_id": BENCHMARK_ID,
        "protocol": PROTOCOL,
        "decision": decision,
        "kat_fingerprint": FROZEN_KAT_FINGERPRINT,
        "simulation": simulation,
        "commitments": {
            "real_receipts_committed": expected_receipts,
            "full_10_receipt_blocks": commits["full_blocks"],
            "partial_blocks": commits["partial_blocks"],
            "sha_blocks_accepted": expected_digests,
            "digests_emitted": expected_digests,
            "compression_rounds": expected_digests * 64,
            "rounds_per_digest": 64,
            "digest_match_fraction": 1.0 if semantic_ok else 0.0,
            "digest_sequence_match_fraction": 1.0 if semantic_ok else 0.0,
            "real_receipt_commit_coverage_fraction": 1.0 if semantic_ok else 0.0,
        },
        "synthesis": {
            "receipt_only_control": control_synth,
            "receipt_plus_sha256x1": sha_synth,
            "delta": delta,
            "declared_receipt_state_bits": 4080,
            "declared_sha_assembler_state_bits": 3541,
        },
        "control_reference_stalls": FROZEN_CONTROL_STALLS,
        "synthetic_combined_score_used": False,
        "timing_decisive": False,
        "merkle_present": False,
        "claim_boundary": "Icarus functional simulation + Yosys Xilinx-7 structural mapping; no Merkle, board power, post-route Fmax or ASIC PPA claim.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(result["decision"])
        print(json.dumps(result, indent=2, sort_keys=True))
    if result["decision"] != "SHA256_COMMITMENT_COST_MEASURED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
