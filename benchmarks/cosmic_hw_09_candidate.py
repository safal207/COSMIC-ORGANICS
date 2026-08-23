from __future__ import annotations

import argparse
from collections import Counter
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
from benchmarks.cosmic_hw_08_candidate import (
    expected_commitments,
    run as run_hw08_control,
    write_mem,
)

BENCHMARK_ID = "COSMIC-HW-09-CANDIDATE"
PROTOCOL = "COSMIC-HW-09/v0.1"
FROZEN_X1_STALLS = {"0.01": 0, "0.05": 542, "0.20": 22914, "1.00": 26966, "stress": 57563}
PRIMARY_GROUPS = ("0.20", "1.00", "stress")
MIN_REDUCTION = 0.50


def prepare_mem(oracle: dict, commits: dict, tmp: Path) -> dict[str, Path]:
    ticks = oracle["ticks"]
    seqs = oracle["sequences"]
    receipts = oracle["receipts"]
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
    write_mem(files["digests"], commits["digests"], 64)
    write_mem(files["digest_seq"], commits["digest_sequences"], 4)
    return files


def make_tb(oracle: dict, commits: dict, files: dict[str, Path], top: str, engines: int) -> str:
    receipts = oracle["receipts"]
    digests = commits["digests"]
    return f'''`timescale 1ns/1ps
module cosmic_hw09_tb;
localparam integer TOTAL_SEQUENCES=320;
localparam integer TOTAL_TICKS=3840;
localparam integer TOTAL_RECEIPTS={len(receipts)};
localparam integer TOTAL_DIGESTS={len(digests)};
localparam integer ENGINES={engines};
reg clk=0, reset=1, tick_valid=0, flush=0, digest_ready=1;
reg [511:0] stimulus_bus=0;
wire tick_ready, digest_valid, waiting_valid, receipt_valid_out, receipt_ready_out, pending_observation_out;
wire [255:0] digest_data; wire [15:0] digest_sequence; wire [39:0] receipt_data_out;
wire [127:0] phase_bus; wire [63:0] active_mask, changed_mask, dirty_mask;
wire [3:0] fill_count, engine_busy_mask, engine_digest_valid_mask, engine_block_accept_mask;
wire [2:0] batch_occupancy_out;
reg [511:0] stim_mem[0:TOTAL_TICKS-1];
reg [127:0] state_mem[0:TOTAL_TICKS-1];
reg [63:0] active_mem[0:TOTAL_TICKS-1], changed_mem[0:TOTAL_TICKS-1], dirty_mem[0:TOTAL_TICKS-1];
reg [1:0] pattern_mem[0:TOTAL_SEQUENCES-1]; reg [2:0] group_mem[0:TOTAL_SEQUENCES-1];
reg [15:0] seq_receipt_mem[0:TOTAL_SEQUENCES-1]; reg [39:0] receipt_mem[0:TOTAL_RECEIPTS-1];
reg [15:0] seq_digest_mem[0:TOTAL_SEQUENCES-1], digest_seq_mem[0:TOTAL_DIGESTS-1];
reg [255:0] digest_mem[0:TOTAL_DIGESTS-1];
integer seq, local_tick, tick_index=0, receipt_cursor=0, digest_cursor=0;
integer seq_receipt_start, seq_digest_start, physical_cycle, physical_cycles_total=0;
integer accepted_ticks=0, checks=0, digest_sink_stalls=0, assembler_stalls=0;
integer stalls_g0=0, stalls_g1=0, stalls_g2=0, stalls_g3=0, stalls_g4=0;
integer busy0=0,busy1=0,busy2=0,busy3=0,acc0=0,acc1=0,acc2=0,acc3=0;
integer max_busy=0,max_digest_occ=0,watchdog,accept_now,busy_now,digest_occ_now;
always #5 clk=~clk;

{top} dut(
 .clk(clk),.reset(reset),.tick_valid(tick_valid),.tick_ready(tick_ready),.stimulus_bus(stimulus_bus),.flush(flush),
 .phase_bus(phase_bus),.active_mask(active_mask),.changed_mask(changed_mask),.dirty_mask(dirty_mask),
 .digest_valid(digest_valid),.digest_ready(digest_ready),.digest_data(digest_data),.digest_sequence(digest_sequence),
 .fill_count_out(fill_count),.waiting_block_valid_out(waiting_valid),
 .engine_busy_mask(engine_busy_mask),.engine_digest_valid_mask(engine_digest_valid_mask),.engine_block_accept_mask(engine_block_accept_mask),
 .receipt_valid_out(receipt_valid_out),.receipt_ready_out(receipt_ready_out),.receipt_data_out(receipt_data_out),
 .batch_occupancy_out(batch_occupancy_out),.pending_observation_out(pending_observation_out));

function ready_for_cycle; input [1:0] pattern; input integer cycle; begin
 case(pattern)
  2'd0: ready_for_cycle=1'b1;
  2'd1: ready_for_cycle=((cycle%4)!=3);
  2'd2: ready_for_cycle=((cycle%2)==0);
  2'd3: ready_for_cycle=((cycle%16)>=8);
  default: ready_for_cycle=1'b0;
 endcase
end endfunction

function integer pop4; input [3:0] v; begin pop4=v[0]+v[1]+v[2]+v[3]; end endfunction

task note_stall; input [2:0] group; begin
 case(group)
  3'd0: stalls_g0=stalls_g0+1; 3'd1: stalls_g1=stalls_g1+1; 3'd2: stalls_g2=stalls_g2+1;
  3'd3: stalls_g3=stalls_g3+1; default: stalls_g4=stalls_g4+1;
 endcase
end endtask

// Sample handshakes at the active edge, before DUT nonblocking state updates.
// This matches the frozen HW-07 receipt harness and avoids post-edge ready drift.
always @(posedge clk) begin
 if(!reset) begin
  if(receipt_valid_out && receipt_ready_out) begin
   if(receipt_cursor>=TOTAL_RECEIPTS) $fatal(1,"phantom receipt");
   if(receipt_data_out!==receipt_mem[receipt_cursor]) $fatal(1,"receipt mismatch idx=%0d got=%h exp=%h",receipt_cursor,receipt_data_out,receipt_mem[receipt_cursor]);
   receipt_cursor=receipt_cursor+1; checks=checks+1;
  end
  if(digest_valid && digest_ready) begin
   if(digest_cursor>=TOTAL_DIGESTS) $fatal(1,"phantom digest");
   if(digest_data!==digest_mem[digest_cursor]) $fatal(1,"digest mismatch idx=%0d got=%064h exp=%064h",digest_cursor,digest_data,digest_mem[digest_cursor]);
   if(digest_sequence!==digest_seq_mem[digest_cursor]) $fatal(1,"digest sequence mismatch idx=%0d got=%0d exp=%0d",digest_cursor,digest_sequence,digest_seq_mem[digest_cursor]);
   digest_cursor=digest_cursor+1; checks=checks+2;
  end
  if(digest_valid && !digest_ready) digest_sink_stalls=digest_sink_stalls+1;
  if(receipt_valid_out && !receipt_ready_out) assembler_stalls=assembler_stalls+1;
  if(engine_busy_mask[0]) busy0=busy0+1; if(engine_busy_mask[1]) busy1=busy1+1;
  if(engine_busy_mask[2]) busy2=busy2+1; if(engine_busy_mask[3]) busy3=busy3+1;
  if(engine_block_accept_mask[0]) acc0=acc0+1; if(engine_block_accept_mask[1]) acc1=acc1+1;
  if(engine_block_accept_mask[2]) acc2=acc2+1; if(engine_block_accept_mask[3]) acc3=acc3+1;
  busy_now=pop4(engine_busy_mask); if(busy_now>max_busy) max_busy=busy_now;
  digest_occ_now=pop4(engine_digest_valid_mask); if(digest_occ_now>max_digest_occ) max_digest_occ=digest_occ_now;
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
  accept_now=tick_ready; if(!tick_ready) note_stall(group);
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
 while((receipt_cursor-seq_receipt_start)<expected_receipts || batch_occupancy_out!=0 || pending_observation_out || receipt_valid_out) begin
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
 while((digest_cursor-seq_digest_start)<expected_digests || fill_count!=0 || waiting_valid || engine_busy_mask!=0 || engine_digest_valid_mask!=0 || digest_valid) begin
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
 if((acc0+acc1+acc2+acc3)!=TOTAL_DIGESTS) $fatal(1,"block accept mismatch got=%0d exp=%0d",acc0+acc1+acc2+acc3,TOTAL_DIGESTS);
 $display("COSMIC_HW09_SIM PASS engines=%0d checks=%0d sequences=320 ticks=%0d receipts=%0d digests=%0d physical_cycles=%0d digest_sink_stalls=%0d assembler_stalls=%0d stalls_g0=%0d stalls_g1=%0d stalls_g2=%0d stalls_g3=%0d stalls_g4=%0d busy0=%0d busy1=%0d busy2=%0d busy3=%0d acc0=%0d acc1=%0d acc2=%0d acc3=%0d max_busy=%0d max_digest_occ=%0d",
 ENGINES,checks,accepted_ticks,receipt_cursor,digest_cursor,physical_cycles_total,digest_sink_stalls,assembler_stalls,
 stalls_g0,stalls_g1,stalls_g2,stalls_g3,stalls_g4,busy0,busy1,busy2,busy3,acc0,acc1,acc2,acc3,max_busy,max_digest_occ);
 $finish;
end
endmodule
'''


def parse_sim(text: str) -> dict:
    pat = re.compile(
        r"COSMIC_HW09_SIM PASS engines=(\d+) checks=(\d+) sequences=(\d+) ticks=(\d+) receipts=(\d+) digests=(\d+) "
        r"physical_cycles=(\d+) digest_sink_stalls=(\d+) assembler_stalls=(\d+) "
        r"stalls_g0=(\d+) stalls_g1=(\d+) stalls_g2=(\d+) stalls_g3=(\d+) stalls_g4=(\d+) "
        r"busy0=(\d+) busy1=(\d+) busy2=(\d+) busy3=(\d+) acc0=(\d+) acc1=(\d+) acc2=(\d+) acc3=(\d+) "
        r"max_busy=(\d+) max_digest_occ=(\d+)"
    )
    m = pat.search(text)
    if not m:
        raise RuntimeError("COSMIC-HW-09 PASS marker not found\n" + text)
    v = list(map(int, m.groups()))
    return {
        "engines": v[0], "checks": v[1], "sequences": v[2], "accepted_ticks": v[3],
        "receipts_emitted": v[4], "digests_emitted": v[5], "physical_cycles": v[6],
        "digest_sink_stalls": v[7], "assembler_stalls": v[8],
        "backpressure_stalls": {"0.01": v[9], "0.05": v[10], "0.20": v[11], "1.00": v[12], "stress": v[13]},
        "per_engine_busy_cycles": [v[14], v[15], v[16], v[17]],
        "per_engine_blocks_accepted": [v[18], v[19], v[20], v[21]],
        "max_simultaneous_busy_engines": v[22],
        "max_completed_digest_occupancy": v[23],
    }


def synthesize_multi(yosys: str, root: Path, top: str, tmp: Path) -> dict:
    rtl06 = root / "rtl" / "cosmic_hw_06.v"
    rtl07 = root / "rtl" / "cosmic_hw_07_receipt.v"
    rtl08 = root / "rtl" / "cosmic_hw_08_sha256.v"
    rtl09 = root / "rtl" / "cosmic_hw_09_multi_sha.v"
    json_path = tmp / f"{top}.json"
    read = f"read_verilog -sv {rtl06} {rtl07} {rtl08} {rtl09}; hierarchy -check -top {top}; flatten; "
    run_cmd([yosys, "-q", "-p", read + f"synth_xilinx -family xc7 -top {top}; write_json {json_path}"])
    row = cell_counts_from_json(json_path, top)
    depth_text = run_cmd([
        yosys, "-p",
        f"read_verilog -sv {rtl06} {rtl07} {rtl08} {rtl09}; hierarchy -check -top {top}; proc; memory_map; opt; flatten; opt; ltp -noff",
    ])
    row["logic_depth_proxy"] = parse_ltp(depth_text)
    return row


def simulate_candidate(root: Path, oracle: dict, commits: dict, engines: int, top: str, tmp: Path) -> dict:
    files = prepare_mem(oracle, commits, tmp)
    tb = tmp / f"tb_x{engines}.v"
    tb.write_text(make_tb(oracle, commits, files, top, engines), encoding="utf-8")
    sim = tmp / f"sim_x{engines}.out"
    run_cmd([
        require_tool("iverilog"), "-g2012", "-s", "cosmic_hw09_tb", "-o", str(sim),
        str(root / "rtl" / "cosmic_hw_06.v"),
        str(root / "rtl" / "cosmic_hw_07_receipt.v"),
        str(root / "rtl" / "cosmic_hw_08_sha256.v"),
        str(root / "rtl" / "cosmic_hw_09_multi_sha.v"), str(tb),
    ])
    return parse_sim(run_cmd([require_tool("vvp"), str(sim)]))


def candidate_eligible(sim: dict) -> bool:
    s = sim["backpressure_stalls"]
    if s["0.01"] != 0 or s["0.05"] > 542:
        return False
    for group in PRIMARY_GROUPS:
        reduction = (FROZEN_X1_STALLS[group] - s[group]) / FROZEN_X1_STALLS[group]
        if reduction < MIN_REDUCTION:
            return False
    return True


def pareto_front(systems: dict) -> list[str]:
    metrics = ("lut", "ff", "core_cells_excluding_io", "logic_depth_proxy")
    groups = ("0.01", "0.05", "0.20", "1.00", "stress")

    def vec(name: str) -> tuple[int, ...]:
        row = systems[name]
        return tuple(row["synthesis"][m] for m in metrics) + tuple(row["simulation"]["backpressure_stalls"][g] for g in groups)

    out = []
    for name in systems:
        a = vec(name)
        dominated = False
        for other in systems:
            if other == name:
                continue
            b = vec(other)
            if all(x <= y for x, y in zip(b, a)) and any(x < y for x, y in zip(b, a)):
                dominated = True
                break
        if not dominated:
            out.append(name)
    return out


def run() -> dict:
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "benchmarks" / "cosmic_hw_09_manifest.json").read_text())
    if manifest["experiment_id"] != PROTOCOL:
        raise RuntimeError("frozen HW-09 manifest mismatch")
    if not (root / "rtl" / "cosmic_hw_09_multi_sha.v").exists():
        raise RuntimeError("HW-09 candidate RTL missing")

    # Exact frozen x1 implementation is rerun as the primary control.
    control = run_hw08_control()
    if control["decision"] != "SHA256_COMMITMENT_COST_MEASURED":
        return {"benchmark_id": BENCHMARK_ID, "protocol": PROTOCOL, "decision": "CONTROL_FAILURE", "control": control}
    if control["simulation"]["backpressure_stalls"] != FROZEN_X1_STALLS:
        return {"benchmark_id": BENCHMARK_ID, "protocol": PROTOCOL, "decision": "CONTROL_FAILURE", "control": control}

    oracle = build_oracle()
    commits = expected_commitments(oracle)
    yosys = require_tool("yosys")
    tops = {2: "cosmic_hw09_sparse_receipt_sha256x2", 4: "cosmic_hw09_sparse_receipt_sha256x4"}

    systems = {
        "SHA256x1_CONTROL": {
            "simulation": control["simulation"],
            "synthesis": control["synthesis"]["receipt_plus_sha256x1"],
            "declared_sha_assembler_dispatcher_state_bits": 3541,
        }
    }

    with tempfile.TemporaryDirectory(prefix="cosmic-hw-09-") as td:
        tmp = Path(td)
        for engines in (2, 4):
            sim = simulate_candidate(root, oracle, commits, engines, tops[engines], tmp)
            if sim["sequences"] != 320 or sim["accepted_ticks"] != 3840 or sim["receipts_emitted"] != 41144 or sim["digests_emitted"] != 4240:
                return {"benchmark_id": BENCHMARK_ID, "protocol": PROTOCOL, "decision": "MULTI_SHA_SEMANTIC_FAILURE", "engines": engines, "simulation": sim}
            synth = synthesize_multi(yosys, root, tops[engines], tmp)
            systems[f"SHA256x{engines}"] = {
                "simulation": sim,
                "synthesis": synth,
                "declared_sha_assembler_dispatcher_state_bits": 965 + 2592 * engines,
            }

    eligible = [name for name in ("SHA256x2", "SHA256x4") if candidate_eligible(systems[name]["simulation"])]
    selection = None
    if eligible:
        selection = min(
            eligible,
            key=lambda name: (
                systems[name]["synthesis"]["core_cells_excluding_io"],
                systems[name]["synthesis"]["ff"],
                systems[name]["synthesis"]["lut"],
                systems[name]["synthesis"]["logic_depth_proxy"],
            ),
        )

    reductions = {}
    for name in ("SHA256x2", "SHA256x4"):
        reductions[name] = {
            group: (FROZEN_X1_STALLS[group] - systems[name]["simulation"]["backpressure_stalls"][group]) / FROZEN_X1_STALLS[group]
            if FROZEN_X1_STALLS[group] else (1.0 if systems[name]["simulation"]["backpressure_stalls"][group] == 0 else float("-inf"))
            for group in FROZEN_X1_STALLS
        }

    return {
        "benchmark_id": BENCHMARK_ID,
        "protocol": PROTOCOL,
        "decision": "SHA_THROUGHPUT_VALUE_SUPPORTED" if eligible else "NO_VALID_SHA_THROUGHPUT_IMPROVEMENT",
        "systems": systems,
        "stall_reduction_fraction_vs_x1": reductions,
        "eligible_candidates": eligible,
        "selected_for_future_merkle": selection,
        "pareto_front": pareto_front(systems),
        "synthetic_combined_score_used": False,
        "merkle_present": False,
        "claim_boundary": "Icarus functional simulation + Yosys Xilinx-7 structural mapping; conventional SHA parallelism only.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run()
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else result)


if __name__ == "__main__":
    main()
