from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
import tempfile
import time

from benchmarks.cosmic_hw_13_candidate import (
    looks_like_capacity_failure,
    parse_fmax,
    recursive_cell_counts,
    require_tool,
    run_cmd,
    summarize_ecp5_cells,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks" / "cosmic_hw_14_manifest.json"
HARNESS_PATH = ROOT / "rtl" / "cosmic_hw_14_profile_harnesses.v"
HW13_HARNESS_PATH = ROOT / "rtl" / "cosmic_hw_13_ecp5_harness.v"

HARNESS_TOPS = {
    "CORE_LITE_R40": "cosmic_hw14_core_lite_harness",
    "PROOF_EDGE_SHA1": "cosmic_hw14_proof_edge_harness",
    "FULL_PROOF_HMAC": "cosmic_hw14_full_proof_harness",
}

DEVICE_CAPACITY = {
    "comb": 83640,
    "ff": 83640,
    "mult": 156,
}
DEVICE_CAPACITY_DENSITY_FLAG = "--85k"


def load_manifest() -> dict:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest["experiment_id"] != "COSMIC-HW-14/v0.1":
        raise RuntimeError("HW-14 manifest mismatch")
    if manifest["parent"]["source_head"] != "773b68597b9136c12867ecc1a3a1749edcba1627":
        raise RuntimeError("HW-14 frozen parent moved")
    if manifest["placement_seeds"] != [1401, 1402, 1403, 1404, 1405]:
        raise RuntimeError("HW-14 seed set moved")
    density_flag = manifest.get("target", {}).get("density_flag")
    if density_flag != DEVICE_CAPACITY_DENSITY_FLAG:
        raise RuntimeError(
            "HW-14 DEVICE_CAPACITY supports only density_flag "
            f"{DEVICE_CAPACITY_DENSITY_FLAG!r}; got {density_flag!r}"
        )
    return manifest


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    payload = f"blob {len(data)}\0".encode("ascii") + data
    return hashlib.sha1(payload).hexdigest()


def profile_map(manifest: dict) -> dict[str, dict]:
    return {str(row["id"]): row for row in manifest["profiles"]}


def source_paths(profile: dict, *, harness: bool) -> list[Path]:
    paths = [ROOT / str(name) for name in profile["source_files"]]
    if profile["id"] == "FULL_PROOF_HMAC" and harness:
        paths.append(HW13_HARNESS_PATH)
    if harness:
        paths.append(HARNESS_PATH)
    return paths


def source_preservation_gate(manifest: dict) -> dict:
    if not HARNESS_PATH.exists():
        raise RuntimeError("HW-14 profile harness file missing")

    blob_checks: dict[str, dict] = {}
    for rel, expected in manifest["inherited_source_git_blobs"].items():
        path = ROOT / rel
        if not path.exists():
            raise RuntimeError(f"frozen inherited source missing: {rel}")
        actual = git_blob_sha(path)
        blob_checks[rel] = {"expected": expected, "actual": actual, "match": actual == expected}
        if actual != expected:
            raise RuntimeError(f"frozen inherited source changed: {rel} expected={expected} actual={actual}")

    text = HARNESS_PATH.read_text(encoding="utf-8")
    hw13_text = HW13_HARNESS_PATH.read_text(encoding="utf-8")
    required_tokens = [
        "module cosmic_hw14_core_lite_harness",
        "cosmic_hw07_mesh64_receipt #(.SPARSE(1), .FIFO_DEPTH(4)) profile",
        "module cosmic_hw14_proof_edge_harness",
        "cosmic_hw08_sparse_receipt_sha256 profile",
        "module cosmic_hw14_full_proof_harness",
        "cosmic_hw13_ecp5_harness profile_harness",
        "observation_word",
        "checksum",
    ]
    missing = [token for token in required_tokens if token not in text]
    if missing:
        raise RuntimeError(f"HW-14 harness preservation tokens missing: {missing}")
    if "cosmic_hw12_b1_m2_hmacx1 core" not in hw13_text:
        raise RuntimeError("frozen HW-13 harness no longer contains exact HW-12 core instance")

    return {
        "passed": True,
        "inherited_blob_checks": blob_checks,
        "exact_profile_instances": {
            "CORE_LITE_R40": True,
            "PROOF_EDGE_SHA1": True,
            "FULL_PROOF_HMAC": True,
        },
        "checksum_feedback_allowed": False,
        "expected_answer_rom_present": False,
    }


def make_smoke_tb(profile_id: str, top: str) -> str:
    if profile_id == "CORE_LITE_R40":
        stimulus = "dut.stimulus_state"
        accepted = "dut.accepted_ticks"
        ready_vector = "{3'b000,dut.receipt_ready}"
        ready_mask = "4'b0001"
    elif profile_id == "PROOF_EDGE_SHA1":
        stimulus = "dut.stimulus_state"
        accepted = "dut.accepted_ticks"
        ready_vector = "{3'b000,dut.digest_ready}"
        ready_mask = "4'b0001"
    elif profile_id == "FULL_PROOF_HMAC":
        stimulus = "dut.profile_harness.stimulus_state"
        accepted = "dut.profile_harness.accepted_ticks"
        ready_vector = "{dut.profile_harness.leaf_digest_ready,dut.profile_harness.root_ready,dut.profile_harness.proof_ready,dut.profile_harness.tag_ready}"
        ready_mask = "4'b1111"
    else:
        raise RuntimeError(f"unknown profile {profile_id}")

    return f'''`timescale 1ns/1ps
module cosmic_hw14_smoke_tb;
reg clk=0;
reg reset=1;
wire [7:0] status;
integer cycles=0;
integer status_changes=0;
integer stimulus_changes=0;
integer accepted_seen=0;
reg [7:0] last_status;
reg [511:0] last_stimulus;
reg [3:0] ready_seen_high=0;
reg [3:0] ready_seen_low=0;
wire [3:0] ready_vector={ready_vector};
always #5 clk=~clk;
{top} dut(.clk(clk),.reset(reset),.status(status));
initial begin
  repeat(4) @(posedge clk);
  @(negedge clk); reset=0;
  last_status=status;
  last_stimulus={stimulus};
  repeat(25000) begin
    @(posedge clk); #1; cycles=cycles+1;
    if(status!==last_status) begin status_changes=status_changes+1; last_status=status; end
    if({accepted}>0) accepted_seen=1;
    if({stimulus}!==last_stimulus) begin stimulus_changes=stimulus_changes+1; last_stimulus={stimulus}; end
    ready_seen_high=ready_seen_high | ready_vector;
    ready_seen_low=ready_seen_low | ~ready_vector;
  end
  if(!accepted_seen) $fatal(1,"no accepted tick observed");
  if(stimulus_changes<4) $fatal(1,"stimulus did not evolve");
  if(status_changes<8) $fatal(1,"observable status did not evolve");
  if((ready_seen_high & {ready_mask})!={ready_mask}) $fatal(1,"required ready path never asserted");
  if((ready_seen_low & {ready_mask})!={ready_mask}) $fatal(1,"required ready path never deasserted");
  $display("COSMIC_HW14_SMOKE PASS profile={profile_id} cycles=%0d accepted=%0d stimulus_changes=%0d status_changes=%0d status=%h",
    cycles,{accepted},stimulus_changes,status_changes,status);
  $finish;
end
endmodule
'''


def harness_smoke(profile: dict, tmp: Path) -> dict:
    profile_id = str(profile["id"])
    top = HARNESS_TOPS[profile_id]
    tb = tmp / f"smoke_{profile_id}.v"
    tb.write_text(make_smoke_tb(profile_id, top), encoding="utf-8")
    out = tmp / f"smoke_{profile_id}.out"
    sources = source_paths(profile, harness=True)
    cmd = [require_tool("iverilog"), "-g2012", "-s", "cosmic_hw14_smoke_tb", "-o", str(out)]
    cmd.extend(str(path) for path in sources)
    cmd.append(str(tb))
    run_cmd(cmd, timeout=300)
    text = run_cmd([require_tool("vvp"), str(out)], timeout=300).stdout
    match = re.search(
        rf"COSMIC_HW14_SMOKE PASS profile={re.escape(profile_id)} cycles=(\d+) accepted=(\d+) stimulus_changes=(\d+) status_changes=(\d+) status=([0-9a-fA-F]+)",
        text,
    )
    if not match:
        raise RuntimeError(f"HW-14 smoke PASS marker missing for {profile_id}\n{text}")
    return {
        "passed": True,
        "cycles": int(match.group(1)),
        "accepted_ticks": int(match.group(2)),
        "stimulus_changes": int(match.group(3)),
        "status_changes": int(match.group(4)),
        "final_status_hex": match.group(5).lower(),
    }


def hierarchy_script(profile: dict, top: str, *, parameterize: bool) -> str:
    commands: list[str] = []
    if parameterize:
        for name, value in profile.get("parameters", {}).items():
            commands.append(f"chparam -set {name} {value} {top}")
    commands.append(f"hierarchy -check -top {top}")
    return "; ".join(commands)


def synth_profile(profile: dict, tmp: Path, *, harness: bool) -> tuple[dict, Path]:
    profile_id = str(profile["id"])
    top = HARNESS_TOPS[profile_id] if harness else str(profile["top_module"])
    paths = source_paths(profile, harness=harness)
    netlist = tmp / f"{profile_id}_{'harness' if harness else 'core'}.json"
    hierarchy = hierarchy_script(profile, top, parameterize=not harness)
    sources = " ".join(str(path) for path in paths)
    script = (
        f"read_verilog -sv {sources}; {hierarchy}; flatten; "
        f"synth_ecp5 -top {top}; write_json {netlist}"
    )
    run_cmd([require_tool("yosys"), "-q", "-p", script], timeout=3600)
    counts = recursive_cell_counts(netlist, top)
    summary = summarize_ecp5_cells(counts)
    if summary["trellis_comb"] <= 0 or summary["trellis_ff"] <= 0:
        raise RuntimeError(f"zero-cell ECP5 synthesis report for {profile_id} harness={harness}")
    summary["top"] = top
    summary["sources"] = [str(path.relative_to(ROOT)) for path in paths]
    return summary, netlist


def preservation_ratio(candidate: int, control: int) -> float:
    if control == 0:
        return 1.0
    return candidate / control


def anti_pruning_gate(manifest: dict, core: dict, harness: dict) -> dict:
    gate = manifest["anti_pruning_gate"]
    ratios = {
        "comb": preservation_ratio(harness["trellis_comb"], core["trellis_comb"]),
        "ff": preservation_ratio(harness["trellis_ff"], core["trellis_ff"]),
        "mult": preservation_ratio(harness["mult18x18d"], core["mult18x18d"]),
    }
    passed = (
        ratios["comb"] >= float(gate["minimum_harness_comb_fraction_of_core"])
        and ratios["ff"] >= float(gate["minimum_harness_ff_fraction_of_core"])
        and ratios["mult"] >= float(gate["minimum_harness_multiplier_fraction_of_core"])
    )
    return {"passed": passed, "ratios": ratios, "thresholds": gate}


def parse_utilization(log: str, resource: str) -> dict | None:
    patterns = [
        rf"{re.escape(resource)}\s*:\s*([0-9,]+)\s*/\s*([0-9,]+)",
        rf"{re.escape(resource)}\s+([0-9,]+)\s*/\s*([0-9,]+)",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, log, flags=re.IGNORECASE)
        if matches:
            used_text, available_text = matches[-1]
            used = int(used_text.replace(",", ""))
            available = int(available_text.replace(",", ""))
            return {
                "used": used,
                "available": available,
                "fraction": used / available if available else None,
            }
    return None


def run_seed(manifest: dict, profile_id: str, tmp: Path, netlist: Path, seed: int) -> dict:
    profile_dir = tmp / profile_id
    profile_dir.mkdir(parents=True, exist_ok=True)
    config = profile_dir / f"seed_{seed}.config"
    bitstream = profile_dir / f"seed_{seed}.bit"
    log_path = profile_dir / f"seed_{seed}.log"
    target = manifest["target"]
    cmd = [
        require_tool("nextpnr-ecp5"),
        str(target["density_flag"]),
        "--package", str(target["package"]),
        "--speed", str(target["speed_grade"]),
        "--json", str(netlist),
        "--textcfg", str(config),
        "--freq", str(target["requested_clock_mhz"]),
        "--seed", str(seed),
        "--timing-allow-fail",
    ]
    start = time.monotonic()
    process = run_cmd(cmd, check=False, timeout=3600)
    runtime_seconds = time.monotonic() - start
    log_path.write_text(process.stdout, encoding="utf-8")

    routed = process.returncode == 0 and config.exists() and config.stat().st_size > 0
    packed = False
    pack_returncode: int | None = None
    pack_log_path: Path | None = None
    if routed:
        pack_log_path = profile_dir / f"seed_{seed}_ecppack.log"
        pack = run_cmd(
            [require_tool("ecppack"), str(config), str(bitstream)],
            check=False,
            timeout=300,
        )
        pack_returncode = pack.returncode
        pack_log_path.write_text(pack.stdout, encoding="utf-8")
        packed = pack.returncode == 0 and bitstream.exists() and bitstream.stat().st_size > 0

    fmax_mhz = parse_fmax(process.stdout)
    timing_pass = bool(routed and fmax_mhz is not None and fmax_mhz >= float(target["requested_clock_mhz"]))
    utilization = {
        "comb": parse_utilization(process.stdout, "TRELLIS_COMB"),
        "ff": parse_utilization(process.stdout, "TRELLIS_FF"),
        "mult": parse_utilization(process.stdout, "MULT18X18D"),
        "ebr": parse_utilization(process.stdout, "DP16KD"),
    }
    return {
        "seed": seed,
        "nextpnr_returncode": process.returncode,
        "runtime_seconds": runtime_seconds,
        "routed": routed,
        "packed": packed,
        "pack_returncode": pack_returncode,
        "fmax_mhz": fmax_mhz,
        "timing_10mhz_pass": timing_pass,
        "capacity_signal": looks_like_capacity_failure(process.stdout),
        "utilization": utilization,
        "log": str(log_path),
        "config": str(config) if config.exists() else None,
        "bitstream": str(bitstream) if bitstream.exists() else None,
        "pack_log": str(pack_log_path) if pack_log_path else None,
    }


def max_resource_fraction(synthesis: dict, seeds: list[dict], key: str) -> float:
    synth_key = {"comb": "trellis_comb", "ff": "trellis_ff", "mult": "mult18x18d"}[key]
    fractions = [synthesis[synth_key] / DEVICE_CAPACITY[key]]
    for row in seeds:
        value = row["utilization"].get(key)
        if value and value.get("fraction") is not None:
            fractions.append(float(value["fraction"]))
    return max(fractions)


def summarize_physical(manifest: dict, synthesis: dict, seeds: list[dict], preservation: dict) -> dict:
    gate = manifest["route_deployable_gate"]
    successful_routes = sum(bool(row["routed"]) for row in seeds)
    packed_bitstreams = sum(bool(row["packed"]) for row in seeds)
    timing_passes = sum(bool(row["timing_10mhz_pass"]) for row in seeds)
    fmax_values = [float(row["fmax_mhz"]) for row in seeds if row["routed"] and row["fmax_mhz"] is not None]
    route_deployable = (
        preservation["passed"]
        and successful_routes >= int(gate["minimum_successful_routes"])
        and packed_bitstreams >= int(gate["minimum_nonempty_bitstreams"])
        and timing_passes >= int(gate["minimum_10mhz_timing_passes"])
    )

    fractions = {
        key: max_resource_fraction(synthesis, seeds, key)
        for key in ("comb", "ff", "mult")
    }
    headroom_gate = manifest["board_handoff_headroom"]
    headroom_pass = (
        fractions["comb"] <= float(headroom_gate["maximum_comb_fraction"])
        and fractions["ff"] <= float(headroom_gate["maximum_ff_fraction"])
        and fractions["mult"] <= float(headroom_gate["maximum_multiplier_fraction"])
    )

    return {
        "successful_routes": successful_routes,
        "packed_bitstreams": packed_bitstreams,
        "timing_10mhz_passes": timing_passes,
        "fmax_mhz": {
            "values": fmax_values,
            "minimum": min(fmax_values) if fmax_values else None,
            "median": statistics.median(fmax_values) if fmax_values else None,
            "maximum": max(fmax_values) if fmax_values else None,
        },
        "maximum_resource_fractions": fractions,
        "route_deployable": route_deployable,
        "headroom_pass": headroom_pass,
        "board_handoff_eligible": route_deployable and headroom_pass,
        "capacity_signal_count": sum(bool(row["capacity_signal"]) for row in seeds),
    }


def choose_decision(manifest: dict, profiles: dict[str, dict]) -> tuple[str, str | None]:
    selected: str | None = None
    for profile_id in manifest["handoff_tier_order"]:
        if profiles[profile_id]["physical"]["board_handoff_eligible"]:
            selected = profile_id
            break

    if selected == "FULL_PROOF_HMAC":
        return "FULL_PROOF_BOARD_HANDOFF_SUPPORTED", selected
    if selected == "PROOF_EDGE_SHA1":
        return "PROOF_EDGE_BOARD_HANDOFF_SUPPORTED", selected
    if selected == "CORE_LITE_R40":
        return "CORE_LITE_BOARD_HANDOFF_SUPPORTED", selected
    if any(row["physical"]["route_deployable"] for row in profiles.values()):
        return "ROUTABLE_BUT_HEADROOM_NOT_SUPPORTED", None
    return "NO_PROFILE_ROUTE_DEPLOYABLE", None


def render_evidence_summary(result: dict) -> str:
    """Render the hosted result without interrupting its Markdown table."""

    lines = [
        "## COSMIC-HW-14 hosted evidence",
        "",
        f"decision=`{result['decision']}`",
        f"selected_board_handoff_profile=`{result['selected_board_handoff_profile']}`",
        "",
        "| Profile | Routes | Packs | 10 MHz | Comb | FF | Mult | Headroom | Board handoff |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    fmax_lines: list[str] = []
    for name in ("CORE_LITE_R40", "PROOF_EDGE_SHA1", "FULL_PROOF_HMAC"):
        row = result["profiles"][name]
        physical = row["physical"]
        synthesis = row["harness_synthesis"]
        fractions = physical["maximum_resource_fractions"]
        lines.append(
            f"| {name} | {physical['successful_routes']}/5 | "
            f"{physical['packed_bitstreams']}/5 | {physical['timing_10mhz_passes']}/5 | "
            f"{synthesis['trellis_comb']} ({fractions['comb'] * 100:.1f}%) | "
            f"{synthesis['trellis_ff']} ({fractions['ff'] * 100:.1f}%) | "
            f"{synthesis['mult18x18d']} ({fractions['mult'] * 100:.1f}%) | "
            f"{'PASS' if physical['headroom_pass'] else 'NO'} | "
            f"{'YES' if physical['board_handoff_eligible'] else 'NO'} |"
        )
        fmax = physical["fmax_mhz"]
        fmax_lines.append(
            f"{name} routed Fmax min/median/max: {fmax['minimum']} / "
            f"{fmax['median']} / {fmax['maximum']} MHz"
        )
    lines.extend(
        [
            "",
            *fmax_lines,
            "",
            "Boundary: identifies a route/pack/timing/headroom profile for a later "
            "board experiment only. No board execution or measured energy claim.",
        ]
    )
    return "\n".join(lines) + "\n"


def run(output_dir: Path) -> dict:
    manifest = load_manifest()
    profiles_by_id = profile_map(manifest)
    source_gate = source_preservation_gate(manifest)
    output_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, dict] = {}
    with tempfile.TemporaryDirectory(prefix="cosmic-hw14-") as temp_name:
        temp = Path(temp_name)
        for profile_id in [row["id"] for row in manifest["profiles"]]:
            profile = profiles_by_id[profile_id]
            smoke = harness_smoke(profile, temp)
            core_synthesis, _ = synth_profile(profile, temp, harness=False)
            harness_synthesis, harness_netlist = synth_profile(profile, temp, harness=True)
            preservation = anti_pruning_gate(manifest, core_synthesis, harness_synthesis)
            if not preservation["passed"]:
                raise RuntimeError(f"anti-pruning gate failed for {profile_id}: {preservation}")

            seeds = [
                run_seed(manifest, profile_id, output_dir, harness_netlist, int(seed))
                for seed in manifest["placement_seeds"]
            ]
            physical = summarize_physical(manifest, harness_synthesis, seeds, preservation)
            results[profile_id] = {
                "tier": int(profile["tier"]),
                "top_module": str(profile["top_module"]),
                "harness_top": HARNESS_TOPS[profile_id],
                "required_evidence": list(profile["required_evidence"]),
                "smoke": smoke,
                "core_synthesis": core_synthesis,
                "harness_synthesis": harness_synthesis,
                "anti_pruning": preservation,
                "seeds": seeds,
                "physical": physical,
            }

    full = results["FULL_PROOF_HMAC"]
    full_capacity_reproduced = (
        full["harness_synthesis"]["trellis_comb"] > DEVICE_CAPACITY["comb"]
        and full["harness_synthesis"]["mult18x18d"] > DEVICE_CAPACITY["mult"]
        and full["physical"]["successful_routes"] == 0
        and full["physical"]["capacity_signal_count"] == len(manifest["placement_seeds"])
    )
    if not full_capacity_reproduced:
        raise RuntimeError("known HW-13 FULL_PROOF_HMAC capacity control did not reproduce")

    decision, selected = choose_decision(manifest, results)
    if decision not in manifest["decision_classes"]:
        raise RuntimeError(f"decision outside frozen classes: {decision}")

    return {
        "benchmark_id": "COSMIC-HW-14-CANDIDATE",
        "protocol": "COSMIC-HW-14/v0.1",
        "parent_hw13_source_head": manifest["parent"]["source_head"],
        "target": manifest["target"],
        "placement_seeds": manifest["placement_seeds"],
        "source_preservation": source_gate,
        "inherited_semantic_gates_revalidated_by_workflow": [
            "HW-07 exact receipt semantics",
            "HW-08 standard SHA-256 commitment semantics",
            "HW-12 446-vector HMAC-SHA256 gate",
        ],
        "profiles": results,
        "full_profile_capacity_control_reproduced": full_capacity_reproduced,
        "decision": decision,
        "selected_board_handoff_profile": selected,
        "synthetic_combined_score_used": False,
        "claim_boundary": manifest["claim_boundary"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute the frozen COSMIC-HW-14 profile-fit frontier")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/tmp/cosmic-hw-14-evidence"),
        help="directory for seed logs/configs/bitstreams",
    )
    args = parser.parse_args()
    result = run(args.output_dir)
    if args.json:
        print(json.dumps(result, sort_keys=True, indent=2))
    else:
        print(
            f"COSMIC_HW14_RESULT decision={result['decision']} "
            f"selected={result['selected_board_handoff_profile']}"
        )


if __name__ == "__main__":
    main()
