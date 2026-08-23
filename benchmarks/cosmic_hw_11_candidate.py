from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import tempfile

from benchmarks.cosmic_hw_07_candidate import build_oracle, cell_counts_from_json, parse_ltp, require_tool, run_cmd
from benchmarks.cosmic_hw_08_candidate import expected_commitments
from benchmarks.cosmic_hw_10_candidate import (
    expected_merkle,
    make_tb as make_hw10_tb,
    prepare_mem,
    simulate_candidate as simulate_hw10_control,
    synthesize_candidate as synthesize_hw10_control,
)

BENCHMARK_ID = "COSMIC-HW-11-CANDIDATE"
PROTOCOL = "COSMIC-HW-11/v0.1"
SYSTEMS = {
    "B2_M1": (2, 1),
    "B1_M2": (1, 2),
    "B2_M2": (2, 2),
}
CONTROL_STALLS = {"0.01": 0, "0.05": 542, "0.20": 11184, "1.00": 13456, "stress": 80560}
CONTROL_PHYSICAL_CYCLES = 1027209
CONTROL_LEAF_TO_TREE_STALLS = 230795
CONTROL_MERKLE_BUSY = 852480
CONTROL_SYNTH = {"lut": 36907, "ff": 21380, "core_cells_excluding_io": 62125, "logic_depth_proxy": 266}


def make_candidate_tb(execution: dict, commitments: dict, merkle: dict, files: dict[str, Path], buffers: int, engines: int, system: str) -> str:
    tb = make_hw10_tb(execution, commitments, merkle, files)
    tb = tb.replace("module cosmic_hw10_tb;", "module cosmic_hw11_tb;")
    tb = tb.replace(
        "cosmic_hw10_sparse_receipt_sha256x2_merkle16 dut(",
        f"cosmic_hw11_merkle_frontier_core #(.TREE_BUFFERS({buffers}), .MERKLE_ENGINES({engines})) dut(",
    )
    tb = tb.replace(
        "wire merkle_parent_accept_pulse,root_emit_pulse,proof_emit_pulse;",
        "wire merkle_parent_accept_pulse,root_emit_pulse,proof_emit_pulse;\n"
        "wire inner_digest_valid_out,merkle_leaf_ready_out,buffer_wait_pulse_out;\n"
        "wire [1:0] merkle_sha_busy_mask_out,merkle_parent_accept_mask_out,buffer_occupied_mask_out;",
    )
    tb = tb.replace(
        ".merkle_parent_accept_pulse(merkle_parent_accept_pulse),.root_emit_pulse(root_emit_pulse),.proof_emit_pulse(proof_emit_pulse));",
        ".merkle_parent_accept_pulse(merkle_parent_accept_pulse),.root_emit_pulse(root_emit_pulse),.proof_emit_pulse(proof_emit_pulse),\n"
        " .inner_digest_valid_out(inner_digest_valid_out),.merkle_leaf_ready_out(merkle_leaf_ready_out),\n"
        " .merkle_sha_busy_mask_out(merkle_sha_busy_mask_out),.merkle_parent_accept_mask_out(merkle_parent_accept_mask_out),\n"
        " .buffer_occupied_mask_out(buffer_occupied_mask_out),.buffer_wait_pulse_out(buffer_wait_pulse_out));",
    )
    tb = tb.replace(
        "integer merkle_sha_busy_cycles=0,parent_accepts=0,leaf_busy0=0,leaf_busy1=0,max_leaf_count=0;",
        "integer merkle_sha_busy_cycles=0,merkle_sha_wall_cycles=0,parent_accepts=0,leaf_busy0=0,leaf_busy1=0,max_leaf_count=0;\n"
        "integer merkle_busy0=0,merkle_busy1=0,max_buffer_occupied=0;",
    )
    tb = tb.replace(
        "if(dut.inner_digest_valid && leaf_digest_ready && !dut.merkle_leaf_ready) leaf_to_tree_stalls=leaf_to_tree_stalls+1;",
        "if(inner_digest_valid_out && leaf_digest_ready && !merkle_leaf_ready_out) leaf_to_tree_stalls=leaf_to_tree_stalls+1;",
    )
    tb = tb.replace(
        "if(merkle_sha_busy_out) merkle_sha_busy_cycles=merkle_sha_busy_cycles+1;\n  if(merkle_parent_accept_pulse) parent_accepts=parent_accepts+1;",
        "if(|merkle_sha_busy_mask_out) merkle_sha_wall_cycles=merkle_sha_wall_cycles+1;\n"
        "  if(merkle_sha_busy_mask_out[0]) begin merkle_busy0=merkle_busy0+1; merkle_sha_busy_cycles=merkle_sha_busy_cycles+1; end\n"
        "  if(merkle_sha_busy_mask_out[1]) begin merkle_busy1=merkle_busy1+1; merkle_sha_busy_cycles=merkle_sha_busy_cycles+1; end\n"
        "  if(merkle_parent_accept_mask_out[0]) parent_accepts=parent_accepts+1;\n"
        "  if(merkle_parent_accept_mask_out[1]) parent_accepts=parent_accepts+1;\n"
        "  if(&buffer_occupied_mask_out) max_buffer_occupied=2; else if(|buffer_occupied_mask_out && max_buffer_occupied<1) max_buffer_occupied=1;",
    )
    tb = tb.replace(
        "if(!merkle_tree_busy_out && merkle_leaf_count_out!=0) begin",
        "if(merkle_leaf_count_out!=0) begin",
    )
    old_tail = "accepted_ticks,receipt_cursor,digest_cursor,root_cursor,proof_cursor,parent_accepts,checks,physical_cycles_total,leaf_to_tree_stalls,root_sink_stalls,proof_sink_stalls,merkle_sha_busy_cycles,leaf_busy0,leaf_busy1,max_leaf_count,stalls_g0,stalls_g1,stalls_g2,stalls_g3,stalls_g4);"
    new_tail = "accepted_ticks,receipt_cursor,digest_cursor,root_cursor,proof_cursor,parent_accepts,checks,physical_cycles_total,leaf_to_tree_stalls,root_sink_stalls,proof_sink_stalls,merkle_sha_busy_cycles,leaf_busy0,leaf_busy1,max_leaf_count,stalls_g0,stalls_g1,stalls_g2,stalls_g3,stalls_g4,merkle_sha_wall_cycles,merkle_busy0,merkle_busy1,max_buffer_occupied);"
    tb = tb.replace(
        'max_leaf_count=%0d stalls_g0=%0d stalls_g1=%0d stalls_g2=%0d stalls_g3=%0d stalls_g4=%0d",',
        'max_leaf_count=%0d stalls_g0=%0d stalls_g1=%0d stalls_g2=%0d stalls_g3=%0d stalls_g4=%0d merkle_sha_wall_cycles=%0d merkle_busy0=%0d merkle_busy1=%0d max_buffer_occupied=%0d",',
    )
    tb = tb.replace(old_tail, new_tail)
    if "merkle_sha_wall_cycles=%0d" not in tb:
        raise RuntimeError("failed to patch HW-10 TB for HW-11 metrics")
    return tb


def parse_candidate_sim(text: str) -> dict:
    base_pat = re.compile(
        r"COSMIC_HW10_SIM PASS sequences=(\d+) ticks=(\d+) receipts=(\d+) digests=(\d+) roots=(\d+) proofs=(\d+) parent_hashes=(\d+) checks=(\d+) "
        r"physical_cycles=(\d+) leaf_to_tree_stalls=(\d+) root_sink_stalls=(\d+) proof_sink_stalls=(\d+) merkle_sha_busy_cycles=(\d+) "
        r"leaf_busy0=(\d+) leaf_busy1=(\d+) max_leaf_count=(\d+) stalls_g0=(\d+) stalls_g1=(\d+) stalls_g2=(\d+) stalls_g3=(\d+) stalls_g4=(\d+) "
        r"merkle_sha_wall_cycles=(\d+) merkle_busy0=(\d+) merkle_busy1=(\d+) max_buffer_occupied=(\d+)"
    )
    m = base_pat.search(text)
    if not m:
        raise RuntimeError("COSMIC-HW-11 PASS marker not found\n" + text)
    v = list(map(int, m.groups()))
    return {
        "sequences": v[0],
        "accepted_ticks": v[1],
        "receipts_emitted": v[2],
        "leaf_digests_emitted": v[3],
        "roots_emitted": v[4],
        "proof_fragments_emitted": v[5],
        "parent_hashes": v[6],
        "checks": v[7],
        "physical_cycles": v[8],
        "leaf_to_tree_stalls": v[9],
        "root_sink_stalls": v[10],
        "proof_sink_stalls": v[11],
        "merkle_sha_busy_cycles_aggregate": v[12],
        "leaf_engine_busy_cycles": [v[13], v[14]],
        "max_collector_leaf_count": v[15],
        "backpressure_stalls": {"0.01": v[16], "0.05": v[17], "0.20": v[18], "1.00": v[19], "stress": v[20]},
        "merkle_sha_wall_busy_cycles": v[21],
        "merkle_engine_busy_cycles": [v[22], v[23]],
        "max_buffer_occupied": v[24],
    }


def simulate_frontier(root: Path, execution: dict, commitments: dict, merkle: dict, tmp: Path, system: str, buffers: int, engines: int) -> dict:
    files = prepare_mem(execution, commitments, merkle, tmp)
    tb = tmp / f"tb_hw11_{system}.v"
    tb.write_text(make_candidate_tb(execution, commitments, merkle, files, buffers, engines, system), encoding="utf-8")
    sim = tmp / f"sim_hw11_{system}.out"
    run_cmd([
        require_tool("iverilog"), "-g2012", "-s", "cosmic_hw11_tb", "-o", str(sim),
        str(root / "rtl" / "cosmic_hw_06.v"),
        str(root / "rtl" / "cosmic_hw_07_receipt.v"),
        str(root / "rtl" / "cosmic_hw_08_sha256.v"),
        str(root / "rtl" / "cosmic_hw_09_multi_sha.v"),
        str(root / "rtl" / "cosmic_hw_10_merkle.v"),
        str(root / "rtl" / "cosmic_hw_11_merkle_frontier.v"),
        str(tb),
    ])
    return parse_candidate_sim(run_cmd([require_tool("vvp"), str(sim)]))


def synthesize_frontier(yosys: str, root: Path, tmp: Path, system: str, buffers: int, engines: int) -> dict:
    top = "cosmic_hw11_merkle_frontier_core"
    sources = " ".join(str(root / "rtl" / name) for name in (
        "cosmic_hw_06.v",
        "cosmic_hw_07_receipt.v",
        "cosmic_hw_08_sha256.v",
        "cosmic_hw_09_multi_sha.v",
        "cosmic_hw_10_merkle.v",
        "cosmic_hw_11_merkle_frontier.v",
    ))
    json_path = tmp / f"hw11_{system}.json"
    hierarchy = f"hierarchy -check -top {top} -chparam TREE_BUFFERS {buffers} -chparam MERKLE_ENGINES {engines}"
    run_cmd([yosys, "-q", "-p", f"read_verilog -sv {sources}; {hierarchy}; flatten; synth_xilinx -family xc7 -top {top}; write_json {json_path}"])
    row = cell_counts_from_json(json_path, top)
    depth_text = run_cmd([yosys, "-p", f"read_verilog -sv {sources}; {hierarchy}; proc; memory_map; opt; flatten; opt; ltp -noff"])
    row["logic_depth_proxy"] = parse_ltp(depth_text)
    return row


def semantic_ok(sim: dict) -> bool:
    return (
        sim["sequences"] == 320
        and sim["accepted_ticks"] == 3840
        and sim["receipts_emitted"] == 41144
        and sim["leaf_digests_emitted"] == 4240
        and sim["roots_emitted"] == 444
        and sim["proof_fragments_emitted"] == 16960
        and sim["parent_hashes"] == 6660
        and sim["merkle_sha_busy_cycles_aggregate"] == 852480
    )


def eligible(sim: dict, syn: dict) -> bool:
    return (
        semantic_ok(sim)
        and sim["backpressure_stalls"]["0.01"] == 0
        and sim["backpressure_stalls"]["0.05"] <= 542
        and sim["physical_cycles"] <= 719046
        and sim["backpressure_stalls"]["stress"] <= 80560
        and syn["logic_depth_proxy"] <= 266
    )


def run() -> dict:
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "benchmarks" / "cosmic_hw_11_manifest.json").read_text())
    if manifest["experiment_id"] != PROTOCOL:
        raise RuntimeError("frozen HW-11 manifest mismatch")
    if not (root / "rtl" / "cosmic_hw_11_merkle_frontier.v").exists():
        raise RuntimeError("HW-11 candidate RTL missing")

    execution = build_oracle()
    commitments = expected_commitments(execution)
    merkle = expected_merkle(execution, commitments)
    yosys = require_tool("yosys")

    with tempfile.TemporaryDirectory(prefix="cosmic-hw-11-") as td:
        tmp = Path(td)
        control_sim = simulate_hw10_control(root, execution, commitments, merkle, tmp)
        if (
            control_sim["physical_cycles"] != CONTROL_PHYSICAL_CYCLES
            or control_sim["backpressure_stalls"] != CONTROL_STALLS
            or control_sim["leaf_to_tree_stalls"] != CONTROL_LEAF_TO_TREE_STALLS
            or control_sim["merkle_sha_busy_cycles"] != CONTROL_MERKLE_BUSY
        ):
            return {"benchmark_id": BENCHMARK_ID, "protocol": PROTOCOL, "decision": "CONTROL_FAILURE", "control_simulation": control_sim}
        control_syn = synthesize_hw10_control(yosys, root, tmp)
        if any(control_syn[k] != v for k, v in CONTROL_SYNTH.items()):
            return {"benchmark_id": BENCHMARK_ID, "protocol": PROTOCOL, "decision": "CONTROL_FAILURE", "control_synthesis": control_syn}

        results: dict[str, dict] = {}
        for system, (buffers, engines) in SYSTEMS.items():
            sim = simulate_frontier(root, execution, commitments, merkle, tmp, system, buffers, engines)
            if not semantic_ok(sim):
                return {"benchmark_id": BENCHMARK_ID, "protocol": PROTOCOL, "decision": "MERKLE_SEMANTIC_FAILURE", "system": system, "simulation": sim}
            syn = synthesize_frontier(yosys, root, tmp, system, buffers, engines)
            results[system] = {
                "tree_buffers": buffers,
                "merkle_sha_engines": engines,
                "simulation": sim,
                "synthesis": syn,
                "eligible": eligible(sim, syn),
                "root_match_fraction": 1.0,
                "proof_fragment_match_fraction": 1.0,
                "independently_verified_proof_fraction": 1.0,
            }

    eligible_names = [name for name, row in results.items() if row["eligible"]]
    selected = None
    if eligible_names:
        selected = min(
            eligible_names,
            key=lambda name: (
                results[name]["synthesis"]["core_cells_excluding_io"],
                results[name]["synthesis"]["ff"],
                results[name]["synthesis"]["lut"],
                results[name]["simulation"]["physical_cycles"],
                results[name]["synthesis"]["logic_depth_proxy"],
            ),
        )
        decision = "MERKLE_THROUGHPUT_VALUE_SUPPORTED"
    else:
        decision = "NO_ELIGIBLE_MERKLE_THROUGHPUT_IMPROVEMENT"

    def effect(name: str) -> dict:
        row = results[name]
        return {
            "physical_cycles_delta": row["simulation"]["physical_cycles"] - CONTROL_PHYSICAL_CYCLES,
            "physical_cycles_reduction_fraction": (CONTROL_PHYSICAL_CYCLES - row["simulation"]["physical_cycles"]) / CONTROL_PHYSICAL_CYCLES,
            "leaf_to_tree_stalls_delta": row["simulation"]["leaf_to_tree_stalls"] - CONTROL_LEAF_TO_TREE_STALLS,
            "stress_stalls_delta": row["simulation"]["backpressure_stalls"]["stress"] - CONTROL_STALLS["stress"],
            "core_cells_delta": row["synthesis"]["core_cells_excluding_io"] - CONTROL_SYNTH["core_cells_excluding_io"],
            "ff_delta": row["synthesis"]["ff"] - CONTROL_SYNTH["ff"],
            "lut_delta": row["synthesis"]["lut"] - CONTROL_SYNTH["lut"],
        }

    return {
        "benchmark_id": BENCHMARK_ID,
        "protocol": PROTOCOL,
        "decision": decision,
        "selected_handoff": selected,
        "control": {"system": "B1_M1_CONTROL", "simulation": control_sim, "synthesis": control_syn},
        "systems": results,
        "factorial_effects": {
            "buffer_only_B2_M1": effect("B2_M1"),
            "engine_only_B1_M2": effect("B1_M2"),
            "combined_B2_M2": effect("B2_M2"),
            "buffer_interaction_after_M2_physical_cycles": results["B2_M2"]["simulation"]["physical_cycles"] - results["B1_M2"]["simulation"]["physical_cycles"],
        },
        "eligibility_thresholds": manifest["eligibility"],
        "synthetic_combined_score_used": False,
        "claim_boundary": "Icarus functional simulation + Yosys Xilinx-7 structural mapping; conventional buffering/SHA-parallelism frontier only.",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    result = run()
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else result)


if __name__ == "__main__":
    main()
