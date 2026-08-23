from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks" / "cosmic_hw_13_manifest.json"

RTL_SOURCES = [
    ROOT / "rtl" / "cosmic_hw_06.v",
    ROOT / "rtl" / "cosmic_hw_07_receipt.v",
    ROOT / "rtl" / "cosmic_hw_08_sha256.v",
    ROOT / "rtl" / "cosmic_hw_09_multi_sha.v",
    ROOT / "rtl" / "cosmic_hw_10_merkle.v",
    ROOT / "rtl" / "cosmic_hw_11_merkle_frontier.v",
    ROOT / "rtl" / "cosmic_hw_12_hmac.v",
    ROOT / "rtl" / "cosmic_hw_12_hmac_safe.v",
    ROOT / "rtl" / "cosmic_hw_12_integrated.v",
]
HARNESS = ROOT / "rtl" / "cosmic_hw_13_ecp5_harness.v"
CORE_TOP = "cosmic_hw12_b1_m2_hmacx1"
HARNESS_TOP = "cosmic_hw13_ecp5_harness"


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"required tool missing: {name}")
    return path


def run_cmd(cmd: list[str], *, check: bool = True, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if check and proc.returncode != 0:
        raise RuntimeError(f"command failed rc={proc.returncode}: {' '.join(cmd)}\n{proc.stdout}")
    return proc


def load_manifest() -> dict:
    m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if m["experiment_id"] != "COSMIC-HW-13/v0.1":
        raise RuntimeError("HW-13 manifest mismatch")
    if m["parent_hw12_source_head"] != "7bad7ba095c65221e057696df40fcd6c53dee2b8":
        raise RuntimeError("HW-13 parent head moved")
    return m


def source_preservation_gate() -> dict:
    if not HARNESS.exists():
        raise RuntimeError("HW-13 harness missing")
    text = HARNESS.read_text(encoding="utf-8")
    required_tokens = [
        f"{CORE_TOP} core",
        ".stimulus_bus(stimulus_state)",
        ".leaf_digest_ready(leaf_digest_ready)",
        ".root_ready(root_ready)",
        ".proof_ready(proof_ready)",
        ".tag_ready(tag_ready)",
        ".proof_sibling_digest(proof_sibling_digest)",
        ".tag_data(tag_data)",
        "observation_word",
        "checksum",
    ]
    missing = [token for token in required_tokens if token not in text]
    if missing:
        raise RuntimeError(f"harness preservation tokens missing: {missing}")
    for path in RTL_SOURCES:
        if not path.exists():
            raise RuntimeError(f"frozen RTL source missing: {path}")
    return {"exact_core_instance": True, "required_source_files": [str(p.relative_to(ROOT)) for p in RTL_SOURCES]}


def make_smoke_tb() -> str:
    return r'''`timescale 1ns/1ps
module cosmic_hw13_harness_tb;
reg clk=0;
reg reset=1;
wire [7:0] status;
integer cycles=0;
integer status_changes=0;
integer accepted_seen=0;
integer stimulus_changes=0;
reg [7:0] last_status;
reg [511:0] last_stimulus;
integer leaf_ready_hi=0,leaf_ready_lo=0,root_ready_hi=0,root_ready_lo=0;
integer proof_ready_hi=0,proof_ready_lo=0,tag_ready_hi=0,tag_ready_lo=0;
always #5 clk=~clk;
cosmic_hw13_ecp5_harness dut(.clk(clk),.reset(reset),.status(status));
initial begin
  repeat(4) @(posedge clk);
  @(negedge clk); reset=0;
  last_status=status;
  last_stimulus=dut.stimulus_state;
  repeat(20000) begin
    @(posedge clk); #1; cycles=cycles+1;
    if(status!==last_status) begin status_changes=status_changes+1; last_status=status; end
    if(dut.accepted_ticks>0) accepted_seen=1;
    if(dut.stimulus_state!==last_stimulus) begin stimulus_changes=stimulus_changes+1; last_stimulus=dut.stimulus_state; end
    if(dut.leaf_digest_ready) leaf_ready_hi=1; else leaf_ready_lo=1;
    if(dut.root_ready) root_ready_hi=1; else root_ready_lo=1;
    if(dut.proof_ready) proof_ready_hi=1; else proof_ready_lo=1;
    if(dut.tag_ready) tag_ready_hi=1; else tag_ready_lo=1;
  end
  if(!accepted_seen) $fatal(1,"no accepted tick observed");
  if(stimulus_changes<4) $fatal(1,"stimulus not dynamically evolving");
  if(status_changes<8) $fatal(1,"observable checksum/status did not evolve");
  if(!(leaf_ready_hi&&leaf_ready_lo&&root_ready_hi&&root_ready_lo&&proof_ready_hi&&proof_ready_lo&&tag_ready_hi&&tag_ready_lo))
    $fatal(1,"one or more sink-ready paths did not toggle");
  $display("COSMIC_HW13_HARNESS_SMOKE PASS cycles=%0d accepted=%0d stimulus_changes=%0d status_changes=%0d checksum=%h",
    cycles,dut.accepted_ticks,stimulus_changes,status_changes,dut.checksum);
  $finish;
end
endmodule
'''


def harness_smoke(tmp: Path) -> dict:
    tb = tmp / "hw13_smoke_tb.v"
    tb.write_text(make_smoke_tb(), encoding="utf-8")
    out = tmp / "hw13_smoke.out"
    cmd = [require_tool("iverilog"), "-g2012", "-s", "cosmic_hw13_harness_tb", "-o", str(out)]
    cmd.extend(str(p) for p in RTL_SOURCES)
    cmd.extend([str(HARNESS), str(tb)])
    run_cmd(cmd)
    text = run_cmd([require_tool("vvp"), str(out)]).stdout
    m = re.search(r"COSMIC_HW13_HARNESS_SMOKE PASS cycles=(\d+) accepted=(\d+) stimulus_changes=(\d+) status_changes=(\d+) checksum=([0-9a-fA-F]+)", text)
    if not m:
        raise RuntimeError("HW-13 harness smoke PASS marker missing\n" + text)
    return {
        "cycles": int(m.group(1)),
        "accepted_ticks": int(m.group(2)),
        "stimulus_changes": int(m.group(3)),
        "status_changes": int(m.group(4)),
        "final_checksum_hex": m.group(5).lower(),
    }


def recursive_cell_counts(netlist: Path, top: str) -> dict[str, int]:
    data = json.loads(netlist.read_text(encoding="utf-8"))
    modules = data.get("modules", {})
    if top not in modules:
        raise RuntimeError(f"top module {top} missing from netlist")

    memo: dict[str, dict[str, int]] = {}
    visiting: set[str] = set()

    def count_module(name: str) -> dict[str, int]:
        if name in memo:
            return dict(memo[name])
        if name in visiting:
            raise RuntimeError(f"recursive hierarchy detected at {name}")
        visiting.add(name)
        counts: dict[str, int] = {}
        for cell in modules[name].get("cells", {}).values():
            typ = cell["type"]
            if typ in modules:
                child = count_module(typ)
                for k, v in child.items():
                    counts[k] = counts.get(k, 0) + v
            else:
                counts[typ] = counts.get(typ, 0) + 1
        visiting.remove(name)
        memo[name] = dict(counts)
        return counts

    return count_module(top)


def summarize_ecp5_cells(counts: dict[str, int]) -> dict:
    return {
        "trellis_comb": counts.get("TRELLIS_COMB", 0),
        "trellis_ff": counts.get("TRELLIS_FF", 0),
        "ebr_dp16kd": counts.get("DP16KD", 0),
        "mult18x18d": counts.get("MULT18X18D", 0),
        "total_leaf_cells": sum(counts.values()),
        "cell_types": dict(sorted(counts.items())),
    }


def synth_ecp5(tmp: Path, top: str, include_harness: bool) -> tuple[dict, Path, str]:
    yosys = require_tool("yosys")
    netlist = tmp / f"{top}.json"
    sources = RTL_SOURCES + ([HARNESS] if include_harness else [])
    script = f"read_verilog -sv {' '.join(str(p) for p in sources)}; hierarchy -check -top {top}; synth_ecp5 -top {top}; write_json {netlist}"
    proc = run_cmd([yosys, "-p", script])
    counts = recursive_cell_counts(netlist, top)
    return summarize_ecp5_cells(counts), netlist, proc.stdout


def anti_pruning_gate(m: dict, core: dict, harness: dict) -> dict:
    a = m["anti_pruning_gate"]
    ratios = {
        "trellis_comb": harness["trellis_comb"] / max(core["trellis_comb"], 1),
        "trellis_ff": harness["trellis_ff"] / max(core["trellis_ff"], 1),
        "mult18x18d": harness["mult18x18d"] / max(core["mult18x18d"], 1),
    }
    passed = (
        ratios["trellis_comb"] >= a["min_harness_lut_fraction_of_core_only"]
        and ratios["trellis_ff"] >= a["min_harness_ff_fraction_of_core_only"]
        and ratios["mult18x18d"] >= a["min_harness_multiplier_fraction_of_core_only"]
    )
    return {"passed": passed, "ratios": ratios, "thresholds": a}


def parse_fmax(log: str) -> float | None:
    matches = re.findall(r"Max frequency for clock ['\"]?([^:'\"]+)['\"]?:\s*([0-9]+(?:\.[0-9]+)?)\s*MHz", log)
    if not matches:
        return None
    for name, value in matches:
        if "clk" in name.lower():
            return float(value)
    return float(matches[0][1])


def looks_like_capacity_failure(log: str) -> bool:
    low = log.lower()
    needles = [
        "does not fit",
        "overused",
        "failed to pack",
        "no bels remaining",
        "too many",
        "cannot place",
        "resource utilisation exceeded",
        "resource utilization exceeded",
    ]
    return any(x in low for x in needles)


def run_seed(m: dict, tmp: Path, harness_json: Path, seed: int) -> dict:
    config = tmp / f"hw13_seed_{seed}.config"
    bit = tmp / f"hw13_seed_{seed}.bit"
    log_path = tmp / f"hw13_seed_{seed}.log"
    cmd = [
        require_tool("nextpnr-ecp5"),
        "--85k", "--package", "CABGA381", "--speed", "8",
        "--json", str(harness_json), "--textcfg", str(config),
        "--freq", "10", "--seed", str(seed), "--timing-allow-fail",
    ]
    start = time.monotonic()
    proc = run_cmd(cmd, check=False, timeout=3600)
    runtime = time.monotonic() - start
    log_path.write_text(proc.stdout, encoding="utf-8")
    routed = proc.returncode == 0 and config.exists() and config.stat().st_size > 0
    packed = False
    pack_rc = None
    pack_log = ""
    if routed:
        pack = run_cmd([require_tool("ecppack"), str(config), str(bit)], check=False, timeout=300)
        pack_rc = pack.returncode
        pack_log = pack.stdout
        packed = pack.returncode == 0 and bit.exists() and bit.stat().st_size > 0
    fmax = parse_fmax(proc.stdout)
    timing_pass = bool(fmax is not None and fmax >= float(m["target"]["requested_clock_mhz"]))
    return {
        "seed": seed,
        "nextpnr_returncode": proc.returncode,
        "routed": routed,
        "packed": packed,
        "fmax_mhz": fmax,
        "meets_10mhz": timing_pass,
        "capacity_failure_signal": looks_like_capacity_failure(proc.stdout),
        "runtime_seconds": round(runtime, 3),
        "config_bytes": config.stat().st_size if config.exists() else 0,
        "bitstream_bytes": bit.stat().st_size if bit.exists() else 0,
        "log_tail": "\n".join(proc.stdout.splitlines()[-40:]),
        "pack_returncode": pack_rc,
        "pack_log_tail": "\n".join(pack_log.splitlines()[-20:]),
    }


def decide(m: dict, preservation: dict, smoke: dict, anti: dict, seeds: list[dict]) -> str:
    if not preservation.get("exact_core_instance") or smoke["accepted_ticks"] <= 0:
        return "HARNESS_PRESERVATION_FAILURE"
    if not anti["passed"]:
        return "HARNESS_PRESERVATION_FAILURE"
    routed = sum(1 for s in seeds if s["routed"] and s["packed"])
    timing = sum(1 for s in seeds if s["routed"] and s["packed"] and s["meets_10mhz"])
    capacity_signals = sum(1 for s in seeds if s["capacity_failure_signal"])
    if routed == 0 and capacity_signals >= 1:
        return "DEVICE_CAPACITY_NOT_SUPPORTED"
    if routed < m["placement"]["required_successful_routes"]:
        return "PLACE_ROUTE_FAILED"
    if timing < m["placement"]["required_10mhz_passes"]:
        return "ECP5_10MHZ_TIMING_NOT_SUPPORTED"
    return "ECP5_POST_ROUTE_FEASIBILITY_SUPPORTED"


def run() -> dict:
    m = load_manifest()
    preservation = source_preservation_gate()
    with tempfile.TemporaryDirectory(prefix="cosmic-hw13-") as td:
        tmp = Path(td)
        smoke = harness_smoke(tmp)
        core_syn, _, _ = synth_ecp5(tmp, CORE_TOP, False)
        harness_syn, harness_json, _ = synth_ecp5(tmp, HARNESS_TOP, True)
        anti = anti_pruning_gate(m, core_syn, harness_syn)

        if not anti["passed"]:
            seeds: list[dict] = []
        else:
            seeds = [run_seed(m, tmp, harness_json, int(seed)) for seed in m["placement"]["seeds"]]

    fmax_values = [s["fmax_mhz"] for s in seeds if s["routed"] and s["packed"] and s["fmax_mhz"] is not None]
    physical_summary = {
        "successful_routes_and_packs": sum(1 for s in seeds if s["routed"] and s["packed"]),
        "timing_10mhz_passes": sum(1 for s in seeds if s["routed"] and s["packed"] and s["meets_10mhz"]),
        "fmax_min_mhz": min(fmax_values) if fmax_values else None,
        "fmax_median_mhz": statistics.median(fmax_values) if fmax_values else None,
        "fmax_max_mhz": max(fmax_values) if fmax_values else None,
    }
    return {
        "benchmark_id": "COSMIC-HW-13-CANDIDATE",
        "protocol": "COSMIC-HW-13/v0.1",
        "parent_hw12_source_head": m["parent_hw12_source_head"],
        "target": m["target"],
        "preservation": preservation,
        "harness_smoke": smoke,
        "core_only_ecp5_synthesis": core_syn,
        "harness_ecp5_synthesis": harness_syn,
        "anti_pruning": anti,
        "seeds": seeds,
        "physical_summary": physical_summary,
        "decision": decide(m, preservation, smoke, anti, seeds),
        "synthetic_combined_score_used": False,
        "claim_boundary": m["claim_boundary"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
