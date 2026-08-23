from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import tempfile

from benchmarks.cosmic_hw_07_candidate import build_oracle, cell_counts_from_json, parse_ltp, require_tool, run_cmd
from benchmarks.cosmic_hw_08_candidate import expected_commitments, write_mem
from benchmarks.cosmic_hw_10_candidate import expected_merkle, prepare_mem
from benchmarks.cosmic_hw_11_candidate import make_candidate_tb as make_hw11_tb, parse_candidate_sim as parse_hw11_sim, simulate_frontier, synthesize_frontier
from benchmarks.cosmic_hw_12_oracle import frozen_pairs

BENCHMARK_ID = "COSMIC-HW-12-CANDIDATE"
PROTOCOL = "COSMIC-HW-12/v0.1"
CONTROL_SIM = {
    "physical_cycles": 624253,
    "leaf_to_tree_stalls": 124682,
    "backpressure_stalls": {"0.01": 0, "0.05": 542, "0.20": 11184, "1.00": 13456, "stress": 56985},
}
CONTROL_SYNTH = {"lut": 48437, "ff": 24287, "core_cells_excluding_io": 75967, "logic_depth_proxy": 266}


def must_replace(text: str, old: str, new: str) -> str:
    if old not in text:
        raise RuntimeError("HW-12 TB patch anchor missing:\n" + old[:180])
    return text.replace(old, new, 1)


def prepare_hmac_mem(execution: dict, commitments: dict, merkle: dict, pairs: list[dict[str, object]], tmp: Path) -> dict[str, Path]:
    files = prepare_mem(execution, commitments, merkle, tmp)
    extra = {
        "tag_data": tmp / "tag_data.mem",
        "tag_seq": tmp / "tag_seq.mem",
        "tag_tree": tmp / "tag_tree.mem",
        "tag_real": tmp / "tag_real.mem",
    }
    write_mem(extra["tag_data"], [int(str(x["tag_hex"]), 16) for x in pairs], 64)
    write_mem(extra["tag_seq"], [int(x["source_sequence"]) for x in pairs], 4)
    write_mem(extra["tag_tree"], [int(x["tree_ordinal"]) for x in pairs], 4)
    write_mem(extra["tag_real"], [int(x["real_leaf_count"]) for x in pairs], 2)
    files.update(extra)
    return files


def make_tb(execution: dict, commitments: dict, merkle: dict, pairs: list[dict[str, object]], files: dict[str, Path]) -> str:
    tb = make_hw11_tb(execution, commitments, merkle, files, 1, 2, "B1_M2")
    tb = must_replace(tb, "module cosmic_hw11_tb;", "module cosmic_hw12_tb;")
    tb = must_replace(
        tb,
        "cosmic_hw11_merkle_frontier_core #(.TREE_BUFFERS(1), .MERKLE_ENGINES(2)) dut(",
        "cosmic_hw12_b1_m2_hmacx1 dut(",
    )
    tb = must_replace(
        tb,
        "reg leaf_digest_ready=1, root_ready=1, proof_ready=1;",
        "reg leaf_digest_ready=1, root_ready=1, proof_ready=1, tag_ready=1;",
    )
    tb = must_replace(
        tb,
        "wire [1:0] merkle_sha_busy_mask_out,merkle_parent_accept_mask_out,buffer_occupied_mask_out;",
        "wire [1:0] merkle_sha_busy_mask_out,merkle_parent_accept_mask_out,buffer_occupied_mask_out;\n"
        "wire tag_valid; wire [255:0] tag_data; wire [15:0] tag_source_sequence,tag_tree_ordinal; wire [4:0] tag_real_leaf_count;\n"
        "wire hmac_busy_out,hmac_compression_busy_out,hmac_compression_accept_pulse_out,hmac_pending_valid_out,hmac_message_accept_pulse_out;\n"
        "wire [6:0] hmac_compression_round_count_out; wire [2:0] hmac_compression_count_out;",
    )
    tb = must_replace(
        tb,
        " .buffer_occupied_mask_out(buffer_occupied_mask_out),.buffer_wait_pulse_out(buffer_wait_pulse_out));",
        " .buffer_occupied_mask_out(buffer_occupied_mask_out),.buffer_wait_pulse_out(buffer_wait_pulse_out),\n"
        " .tag_valid(tag_valid),.tag_ready(tag_ready),.tag_data(tag_data),.tag_source_sequence(tag_source_sequence),.tag_tree_ordinal(tag_tree_ordinal),.tag_real_leaf_count(tag_real_leaf_count),\n"
        " .hmac_busy_out(hmac_busy_out),.hmac_compression_busy_out(hmac_compression_busy_out),.hmac_compression_round_count_out(hmac_compression_round_count_out),\n"
        " .hmac_compression_accept_pulse_out(hmac_compression_accept_pulse_out),.hmac_compression_count_out(hmac_compression_count_out),\n"
        " .hmac_pending_valid_out(hmac_pending_valid_out),.hmac_message_accept_pulse_out(hmac_message_accept_pulse_out));",
    )
    tb = must_replace(
        tb,
        "reg proof_left_mem[0:TOTAL_PROOFS-1]; reg [255:0] proof_sibling_mem[0:TOTAL_PROOFS-1];",
        "reg proof_left_mem[0:TOTAL_PROOFS-1]; reg [255:0] proof_sibling_mem[0:TOTAL_PROOFS-1];\n"
        "reg [255:0] tag_mem[0:TOTAL_ROOTS-1]; reg [15:0] tag_seq_mem[0:TOTAL_ROOTS-1],tag_tree_mem[0:TOTAL_ROOTS-1]; reg [7:0] tag_real_mem[0:TOTAL_ROOTS-1];",
    )
    tb = must_replace(
        tb,
        "integer receipt_cursor=0,digest_cursor=0,root_cursor=0,proof_cursor=0;",
        "integer receipt_cursor=0,digest_cursor=0,root_cursor=0,proof_cursor=0,tag_cursor=0;",
    )
    tb = must_replace(
        tb,
        "integer seq_receipt_start,seq_digest_start,seq_root_start,seq_proof_start;",
        "integer seq_receipt_start,seq_digest_start,seq_root_start,seq_proof_start,seq_tag_start;",
    )
    tb = must_replace(
        tb,
        "integer merkle_busy0=0,merkle_busy1=0,max_buffer_occupied=0;",
        "integer merkle_busy0=0,merkle_busy1=0,max_buffer_occupied=0;\n"
        "integer hmac_busy_cycles=0,hmac_compress_busy_cycles=0,hmac_compression_accepts=0,hmac_message_accepts=0;\n"
        "integer root_to_hmac_stalls=0,tag_sink_stalls=0,max_hmac_pending=0;",
    )
    tb = must_replace(
        tb,
        " proof_ready=ready_for_cycle(pattern,physical_cycle);\nend endtask",
        " proof_ready=ready_for_cycle(pattern,physical_cycle);\n tag_ready=ready_for_cycle(pattern,physical_cycle);\nend endtask",
    )
    proof_check_end = "   proof_cursor=proof_cursor+1; checks=checks+6;\n  end"
    tb = must_replace(
        tb,
        proof_check_end,
        proof_check_end + "\n"
        "  if(tag_valid && tag_ready) begin\n"
        "   if(tag_cursor>=TOTAL_ROOTS) $fatal(1,\"phantom HMAC tag\");\n"
        "   if(tag_data!==tag_mem[tag_cursor]) $fatal(1,\"HMAC tag mismatch idx=%0d got=%064h exp=%064h\",tag_cursor,tag_data,tag_mem[tag_cursor]);\n"
        "   if(tag_source_sequence!==tag_seq_mem[tag_cursor]) $fatal(1,\"HMAC source mismatch idx=%0d\",tag_cursor);\n"
        "   if(tag_tree_ordinal!==tag_tree_mem[tag_cursor]) $fatal(1,\"HMAC tree mismatch idx=%0d\",tag_cursor);\n"
        "   if(tag_real_leaf_count!==tag_real_mem[tag_cursor][4:0]) $fatal(1,\"HMAC leaf-count mismatch idx=%0d\",tag_cursor);\n"
        "   tag_cursor=tag_cursor+1; checks=checks+4;\n"
        "  end",
    )
    tb = must_replace(
        tb,
        "  if(root_valid && !root_ready) root_sink_stalls=root_sink_stalls+1;",
        "  if(root_valid && !root_ready) root_sink_stalls=root_sink_stalls+1;\n"
        "  if(dut.inner_root_valid && root_ready && !dut.pending_can_accept) root_to_hmac_stalls=root_to_hmac_stalls+1;\n"
        "  if(tag_valid && !tag_ready) tag_sink_stalls=tag_sink_stalls+1;\n"
        "  if(hmac_busy_out) hmac_busy_cycles=hmac_busy_cycles+1;\n"
        "  if(hmac_compression_busy_out) hmac_compress_busy_cycles=hmac_compress_busy_cycles+1;\n"
        "  if(hmac_compression_accept_pulse_out) hmac_compression_accepts=hmac_compression_accepts+1;\n"
        "  if(hmac_message_accept_pulse_out) hmac_message_accepts=hmac_message_accepts+1;\n"
        "  if(hmac_pending_valid_out) max_hmac_pending=1;",
    )
    tb = must_replace(
        tb,
        " tick_valid=0; flush=0; tree_flush=0; stimulus_bus=0; leaf_digest_ready=1; root_ready=1; proof_ready=1; reset=1; source_sequence_id=seq_id;",
        " tick_valid=0; flush=0; tree_flush=0; stimulus_bus=0; leaf_digest_ready=1; root_ready=1; proof_ready=1; tag_ready=1; reset=1; source_sequence_id=seq_id;",
    )
    tb = tb.replace("dut.fill_count_unused", "dut.merkle.fill_count_unused")
    tb = tb.replace("dut.waiting_unused", "dut.merkle.waiting_unused")
    tb = must_replace(
        tb,
        "while((root_cursor-seq_root_start)<exp_roots || (proof_cursor-seq_proof_start)<exp_proofs || merkle_tree_busy_out || merkle_leaf_count_out!=0 || leaf_engine_busy_mask!=0 || leaf_engine_digest_valid_mask!=0) begin",
        "while((root_cursor-seq_root_start)<exp_roots || (proof_cursor-seq_proof_start)<exp_proofs || (tag_cursor-seq_tag_start)<exp_roots || merkle_tree_busy_out || merkle_leaf_count_out!=0 || leaf_engine_busy_mask!=0 || leaf_engine_digest_valid_mask!=0 || hmac_pending_valid_out || hmac_busy_out || tag_valid) begin",
    )
    tb = must_replace(
        tb,
        " if((proof_cursor-seq_proof_start)!=exp_proofs) $fatal(1,\"seq proof count mismatch seq=%0d\",seq);",
        " if((proof_cursor-seq_proof_start)!=exp_proofs) $fatal(1,\"seq proof count mismatch seq=%0d\",seq);\n"
        " if((tag_cursor-seq_tag_start)!=exp_roots) $fatal(1,\"seq HMAC tag count mismatch seq=%0d\",seq);",
    )
    tb = must_replace(
        tb,
        f' $readmemh("{files["proof_seq"]}",proof_seq_mem); $readmemh("{files["proof_tree"]}",proof_tree_mem); $readmemh("{files["proof_leaf"]}",proof_leaf_mem); $readmemh("{files["proof_level"]}",proof_level_mem); $readmemh("{files["proof_left"]}",proof_left_mem); $readmemh("{files["proof_sibling"]}",proof_sibling_mem);',
        f' $readmemh("{files["proof_seq"]}",proof_seq_mem); $readmemh("{files["proof_tree"]}",proof_tree_mem); $readmemh("{files["proof_leaf"]}",proof_leaf_mem); $readmemh("{files["proof_level"]}",proof_level_mem); $readmemh("{files["proof_left"]}",proof_left_mem); $readmemh("{files["proof_sibling"]}",proof_sibling_mem);\n'
        f' $readmemh("{files["tag_data"]}",tag_mem); $readmemh("{files["tag_seq"]}",tag_seq_mem); $readmemh("{files["tag_tree"]}",tag_tree_mem); $readmemh("{files["tag_real"]}",tag_real_mem);',
    )
    tb = must_replace(
        tb,
        "  reset_sequence(seq); seq_receipt_start=receipt_cursor; seq_digest_start=digest_cursor; seq_root_start=root_cursor; seq_proof_start=proof_cursor;",
        "  reset_sequence(seq); seq_receipt_start=receipt_cursor; seq_digest_start=digest_cursor; seq_root_start=root_cursor; seq_proof_start=proof_cursor; seq_tag_start=tag_cursor;",
    )
    tb = must_replace(
        tb,
        " if(proof_cursor!=TOTAL_PROOFS) $fatal(1,\"global proof count mismatch\");",
        " if(proof_cursor!=TOTAL_PROOFS) $fatal(1,\"global proof count mismatch\");\n"
        " if(tag_cursor!=TOTAL_ROOTS) $fatal(1,\"global HMAC tag count mismatch got=%0d\",tag_cursor);\n"
        " if(hmac_message_accepts!=TOTAL_ROOTS) $fatal(1,\"HMAC message accept mismatch got=%0d exp=%0d\",hmac_message_accepts,TOTAL_ROOTS);\n"
        " if(hmac_compression_accepts!=TOTAL_ROOTS*4) $fatal(1,\"HMAC compression accept mismatch got=%0d exp=%0d\",hmac_compression_accepts,TOTAL_ROOTS*4);",
    )
    tb = must_replace(
        tb,
        " $finish;\nend\nendmodule",
        " $display(\"COSMIC_HW12_HMAC_SIM PASS tags=%0d hmac_busy_cycles=%0d compress_busy_cycles=%0d compression_accepts=%0d message_accepts=%0d root_to_hmac_stalls=%0d tag_sink_stalls=%0d max_pending=%0d\",tag_cursor,hmac_busy_cycles,hmac_compress_busy_cycles,hmac_compression_accepts,hmac_message_accepts,root_to_hmac_stalls,tag_sink_stalls,max_hmac_pending);\n"
        " $finish;\nend\nendmodule",
    )
    return tb


def parse_sim(text: str) -> dict:
    base = parse_hw11_sim(text)
    m = re.search(
        r"COSMIC_HW12_HMAC_SIM PASS tags=(\d+) hmac_busy_cycles=(\d+) compress_busy_cycles=(\d+) compression_accepts=(\d+) message_accepts=(\d+) root_to_hmac_stalls=(\d+) tag_sink_stalls=(\d+) max_pending=(\d+)",
        text,
    )
    if not m:
        raise RuntimeError("HW-12 HMAC simulation marker missing\n" + text)
    v = list(map(int, m.groups()))
    base.update({
        "hmac_tags_emitted": v[0],
        "hmac_busy_cycles": v[1],
        "hmac_compression_busy_cycles": v[2],
        "hmac_compression_accepts": v[3],
        "hmac_message_accepts": v[4],
        "root_to_hmac_stalls": v[5],
        "tag_sink_stalls": v[6],
        "max_hmac_pending": v[7],
    })
    return base


def simulate_candidate(root: Path, execution: dict, commitments: dict, merkle: dict, pairs: list[dict[str, object]], tmp: Path) -> dict:
    files = prepare_hmac_mem(execution, commitments, merkle, pairs, tmp)
    tb = tmp / "tb_hw12.v"
    tb.write_text(make_tb(execution, commitments, merkle, pairs, files), encoding="utf-8")
    sim = tmp / "sim_hw12.out"
    run_cmd([
        require_tool("iverilog"), "-g2012", "-s", "cosmic_hw12_tb", "-o", str(sim),
        str(root / "rtl" / "cosmic_hw_06.v"),
        str(root / "rtl" / "cosmic_hw_07_receipt.v"),
        str(root / "rtl" / "cosmic_hw_08_sha256.v"),
        str(root / "rtl" / "cosmic_hw_09_multi_sha.v"),
        str(root / "rtl" / "cosmic_hw_10_merkle.v"),
        str(root / "rtl" / "cosmic_hw_11_merkle_frontier.v"),
        str(root / "rtl" / "cosmic_hw_12_hmac.v"),
        str(root / "rtl" / "cosmic_hw_12_hmac_safe.v"),
        str(root / "rtl" / "cosmic_hw_12_integrated.v"),
        str(tb),
    ])
    return parse_sim(run_cmd([require_tool("vvp"), str(sim)]))


def synthesize_candidate(yosys: str, root: Path, tmp: Path) -> dict:
    top = "cosmic_hw12_b1_m2_hmacx1"
    sources = " ".join(str(root / "rtl" / name) for name in (
        "cosmic_hw_06.v",
        "cosmic_hw_07_receipt.v",
        "cosmic_hw_08_sha256.v",
        "cosmic_hw_09_multi_sha.v",
        "cosmic_hw_10_merkle.v",
        "cosmic_hw_11_merkle_frontier.v",
        "cosmic_hw_12_hmac.v",
        "cosmic_hw_12_hmac_safe.v",
        "cosmic_hw_12_integrated.v",
    ))
    json_path = tmp / "hw12.json"
    run_cmd([yosys, "-q", "-p", f"read_verilog -sv {sources}; hierarchy -check -top {top}; flatten; synth_xilinx -family xc7 -top {top}; write_json {json_path}"])
    row = cell_counts_from_json(json_path, top)
    depth_text = run_cmd([yosys, "-p", f"read_verilog -sv {sources}; hierarchy -check -top {top}; proc; memory_map; opt; flatten; opt; ltp -noff"])
    row["logic_depth_proxy"] = parse_ltp(depth_text)
    return row


def run() -> dict:
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "benchmarks" / "cosmic_hw_12_manifest.json").read_text())
    if manifest["experiment_id"] != PROTOCOL:
        raise RuntimeError("frozen HW-12 manifest mismatch")
    if manifest["frozen_oracle"]["fingerprint"] != "3b3f577479cf42343196ce1245024c38f3a3209ff18bd2e157ce761e60096885":
        raise RuntimeError("HW-12 frozen oracle fingerprint mismatch")

    execution = build_oracle()
    commitments = expected_commitments(execution)
    merkle = expected_merkle(execution, commitments)
    pairs = frozen_pairs()
    if len(pairs) != 444:
        raise RuntimeError("HW-12 frozen tag count mismatch")
    yosys = require_tool("yosys")

    with tempfile.TemporaryDirectory(prefix="cosmic-hw-12-") as td:
        tmp = Path(td)
        control_sim = simulate_frontier(root, execution, commitments, merkle, tmp, "B1_M2", 1, 2)
        if (
            control_sim["physical_cycles"] != CONTROL_SIM["physical_cycles"]
            or control_sim["leaf_to_tree_stalls"] != CONTROL_SIM["leaf_to_tree_stalls"]
            or control_sim["backpressure_stalls"] != CONTROL_SIM["backpressure_stalls"]
        ):
            return {"benchmark_id": BENCHMARK_ID, "protocol": PROTOCOL, "decision": "CONTROL_FAILURE", "control_simulation": control_sim}
        control_syn = synthesize_frontier(yosys, root, tmp, "B1_M2", 1, 2)
        if any(control_syn[k] != v for k, v in CONTROL_SYNTH.items()):
            return {"benchmark_id": BENCHMARK_ID, "protocol": PROTOCOL, "decision": "CONTROL_FAILURE", "control_synthesis": control_syn}

        candidate_sim = simulate_candidate(root, execution, commitments, merkle, pairs, tmp)
        semantic_ok = (
            candidate_sim["sequences"] == 320
            and candidate_sim["accepted_ticks"] == 3840
            and candidate_sim["receipts_emitted"] == 41144
            and candidate_sim["leaf_digests_emitted"] == 4240
            and candidate_sim["roots_emitted"] == 444
            and candidate_sim["proof_fragments_emitted"] == 16960
            and candidate_sim["parent_hashes"] == 6660
            and candidate_sim["merkle_sha_busy_cycles_aggregate"] == 852480
            and candidate_sim["hmac_tags_emitted"] == 444
            and candidate_sim["hmac_message_accepts"] == 444
            and candidate_sim["hmac_compression_accepts"] == 1776
            and candidate_sim["hmac_compression_busy_cycles"] == 113664
        )
        if not semantic_ok:
            return {"benchmark_id": BENCHMARK_ID, "protocol": PROTOCOL, "decision": "HMAC_SEMANTIC_FAILURE", "simulation": candidate_sim}
        candidate_syn = synthesize_candidate(yosys, root, tmp)

    def delta(key: str) -> dict[str, float | int | None]:
        a = control_syn[key]
        b = candidate_syn[key]
        return {"absolute": b-a, "fraction": ((b-a)/a if a else None)}

    return {
        "benchmark_id": BENCHMARK_ID,
        "protocol": PROTOCOL,
        "decision": "HMAC_ROOT_AUTH_COST_MEASURED",
        "control": {"system": "B1_M2", "simulation": control_sim, "synthesis": control_syn},
        "candidate": {
            "simulation": candidate_sim,
            "synthesis": candidate_syn,
            "hmac_tag_match_fraction": 1.0,
            "root_to_tag_association_match_fraction": 1.0,
            "inherited_root_match_fraction": 1.0,
            "inherited_proof_fragment_match_fraction": 1.0,
            "independently_verified_proof_fraction": 1.0,
            "authenticated_roots": 444,
            "hmac_compression_blocks": 1776,
            "hmac_compression_rounds": 113664,
            "declared_hmac_compression_state_bits": 2832,
            "declared_hmac_controller_state_bits": 1991,
            "declared_pending_root_state_bits": 294,
            "declared_active_tag_metadata_bits": 37,
            "declared_hmac_added_state_bits_total": 5154,
        },
        "structural_delta": {key: delta(key) for key in ("lut", "ff", "core_cells_excluding_io", "logic_depth_proxy")},
        "throughput_delta": {
            "physical_cycles_absolute": candidate_sim["physical_cycles"] - control_sim["physical_cycles"],
            "physical_cycles_fraction": (candidate_sim["physical_cycles"] - control_sim["physical_cycles"]) / control_sim["physical_cycles"],
            "leaf_to_tree_stalls_absolute": candidate_sim["leaf_to_tree_stalls"] - control_sim["leaf_to_tree_stalls"],
            "stress_tick_stalls_absolute": candidate_sim["backpressure_stalls"]["stress"] - control_sim["backpressure_stalls"]["stress"],
        },
        "synthetic_combined_score_used": False,
        "claim_boundary": "Standard HMAC-SHA256 root-authentication cost under a public deterministic test key; Icarus + Yosys Xilinx-7 structural mapping only.",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    result = run()
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else result)


if __name__ == "__main__":
    main()
