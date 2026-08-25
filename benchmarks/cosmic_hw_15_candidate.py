from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import statistics
import subprocess
import tempfile
import time

from benchmarks.cosmic_hw_14_candidate import (
    git_blob_sha,
    looks_like_capacity_failure,
    make_smoke_tb,
    parse_fmax,
    parse_utilization,
    recursive_cell_counts,
    require_tool,
    run_cmd,
    summarize_ecp5_cells,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks" / "cosmic_hw_15_manifest.json"


INSTANCE_TOKENS = {
    "CORE_LITE_R40_NODSP": (
        "cosmic_hw07_mesh64_receipt #(.SPARSE(1), .FIFO_DEPTH(4)) profile"
    ),
    "PROOF_EDGE_SHA1_NODSP": "cosmic_hw08_sparse_receipt_sha256 profile",
}


def load_manifest() -> dict:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest["experiment_id"] != "COSMIC-HW-15/v0.1":
        raise RuntimeError("HW-15 manifest mismatch")
    if manifest["parent"]["source_head"] != "292b94bd3e1c58355439c9212a7af5fa08c08a99":
        raise RuntimeError("HW-15 parent head moved")
    if manifest["target"]["density_flag"] != "--85k":
        raise RuntimeError("HW-15 frozen capacity constants require target density --85k")
    if manifest["placement_seeds"] != [1501, 1502, 1503, 1504, 1505]:
        raise RuntimeError("HW-15 placement seeds moved")
    if manifest["mapping_intervention"]["candidate_flag"] != "-nodsp":
        raise RuntimeError("HW-15 mapping intervention moved")
    return manifest


def profile_map(manifest: dict) -> dict[str, dict]:
    return {str(row["id"]): row for row in manifest["profiles"]}


def source_paths(profile: dict, *, harness: bool) -> list[Path]:
    paths = [ROOT / str(relative) for relative in profile["source_files"]]
    if harness:
        paths.append(ROOT / str(profile["harness_source"]))
    return paths


def _instance_block(text: str, token: str) -> str:
    start = text.find(token)
    if start < 0:
        return ""
    end = text.find(");", start)
    if end < 0:
        return ""
    return text[start : end + 2]


def source_preservation_gate(manifest: dict) -> dict:
    blob_checks: dict[str, dict] = {}
    for relative, expected in manifest["inherited_source_git_blobs"].items():
        path = ROOT / relative
        if not path.exists():
            raise RuntimeError(f"frozen inherited source missing: {relative}")
        actual = git_blob_sha(path)
        match = actual == expected
        blob_checks[relative] = {
            "expected": expected,
            "actual": actual,
            "match": match,
        }

    harness_path = ROOT / "rtl" / "cosmic_hw_14_profile_harnesses.v"
    harness_text = harness_path.read_text(encoding="utf-8")
    instance_matches = {
        profile_id: token in harness_text
        for profile_id, token in INSTANCE_TOKENS.items()
    }
    instance_blocks = {
        profile_id: _instance_block(harness_text, token)
        for profile_id, token in INSTANCE_TOKENS.items()
    }
    checksum_feedback = {
        profile_id: "checksum" in block.lower()
        for profile_id, block in instance_blocks.items()
    }
    rom_tokens = [
        token
        for token in ("$readmemh", "$readmemb", "expected_answer_rom")
        if token in harness_text
    ]
    checksum_observation_present = (
        "observation_word" in harness_text and "checksum" in harness_text
    )

    passed = (
        all(row["match"] for row in blob_checks.values())
        and all(instance_matches.values())
        and all(bool(block) for block in instance_blocks.values())
        and not any(checksum_feedback.values())
        and not rom_tokens
        and checksum_observation_present
    )
    result = {
        "passed": passed,
        "inherited_blob_checks": blob_checks,
        "exact_profile_instances": instance_matches,
        "checksum_feedback_detected": checksum_feedback,
        "expected_answer_rom_tokens": rom_tokens,
        "checksum_observation_present": checksum_observation_present,
    }
    if not passed:
        raise RuntimeError(f"HW-15 source preservation failed: {result}")
    return result


def harness_smoke(profile: dict, tmp: Path) -> dict:
    control_id = str(profile["control_id"])
    top = str(profile["harness_top"])
    tb = tmp / f"smoke_{profile['id']}.v"
    tb.write_text(make_smoke_tb(control_id, top), encoding="utf-8")
    output = tmp / f"smoke_{profile['id']}.out"
    command = [
        require_tool("iverilog"),
        "-g2012",
        "-s",
        "cosmic_hw14_smoke_tb",
        "-o",
        str(output),
    ]
    command.extend(str(path) for path in source_paths(profile, harness=True))
    command.append(str(tb))
    run_cmd(command, timeout=300)
    text = run_cmd([require_tool("vvp"), str(output)], timeout=300).stdout
    match = re.search(
        rf"COSMIC_HW14_SMOKE PASS profile={re.escape(control_id)} "
        r"cycles=(\d+) accepted=(\d+) stimulus_changes=(\d+) "
        r"status_changes=(\d+) status=([0-9a-fA-F]+)",
        text,
    )
    if not match:
        raise RuntimeError(f"HW-15 inherited smoke marker missing for {profile['id']}\n{text}")
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


def synth_profile(
    profile: dict,
    tmp: Path,
    *,
    harness: bool,
    nodsp: bool,
) -> tuple[dict, Path]:
    profile_id = str(profile["id"])
    top = str(profile["harness_top"] if harness else profile["top_module"])
    paths = source_paths(profile, harness=harness)
    suffix = "nodsp" if nodsp else "auto"
    role = "harness" if harness else "core"
    netlist = tmp / f"{profile_id}_{role}_{suffix}.json"
    hierarchy = hierarchy_script(profile, top, parameterize=not harness)
    sources = " ".join(str(path) for path in paths)
    mapping_flag = " -nodsp" if nodsp else ""
    script = (
        f"read_verilog -sv {sources}; {hierarchy}; flatten; "
        f"synth_ecp5{mapping_flag} -top {top}; write_json {netlist}"
    )
    run_cmd([require_tool("yosys"), "-q", "-p", script], timeout=3600)
    counts = recursive_cell_counts(netlist, top)
    summary = summarize_ecp5_cells(counts)
    if summary["trellis_comb"] <= 0 or summary["trellis_ff"] <= 0:
        raise RuntimeError(
            f"zero-cell ECP5 synthesis for {profile_id} role={role} nodsp={nodsp}"
        )
    summary.update(
        {
            "top": top,
            "role": role,
            "mapping": "NODSP" if nodsp else "AUTO_DSP",
            "sources": [str(path.relative_to(ROOT)) for path in paths],
        }
    )
    return summary, netlist


def reproduce_auto_control(profile: dict, harness_summary: dict) -> dict:
    expected = dict(profile["auto_dsp_control_yosys"])
    observed = {
        "trellis_comb": int(harness_summary["trellis_comb"]),
        "trellis_ff": int(harness_summary["trellis_ff"]),
        "mult18x18d": int(harness_summary["mult18x18d"]),
    }
    passed = observed == expected
    result = {"passed": passed, "expected": expected, "observed": observed}
    if not passed:
        raise RuntimeError(f"AUTO_DSP control did not reproduce for {profile['id']}: {result}")
    return result


def _ratio(candidate: int, control: int) -> float:
    if control == 0:
        return 1.0
    return candidate / control


def anti_pruning_gate(manifest: dict, core: dict, harness: dict) -> dict:
    gate = manifest["anti_pruning_gate"]
    ratios = {
        "comb": _ratio(harness["trellis_comb"], core["trellis_comb"]),
        "ff": _ratio(harness["trellis_ff"], core["trellis_ff"]),
        "mult": _ratio(harness["mult18x18d"], core["mult18x18d"]),
    }
    passed = (
        ratios["comb"] >= float(gate["minimum_harness_comb_fraction_of_core"])
        and ratios["ff"] >= float(gate["minimum_harness_ff_fraction_of_core"])
        and core["mult18x18d"] == 0
        and harness["mult18x18d"] == 0
    )
    result = {"passed": passed, "ratios": ratios, "thresholds": gate}
    if not passed:
        raise RuntimeError(f"NODSP anti-pruning failed: {result}")
    return result


def structural_delta(control: dict, candidate: dict) -> dict:
    result: dict[str, dict] = {}
    for key in ("trellis_comb", "trellis_ff", "ebr_dp16kd", "mult18x18d"):
        baseline = int(control[key])
        value = int(candidate[key])
        result[key] = {
            "control": baseline,
            "candidate": value,
            "absolute": value - baseline,
            "fraction": ((value - baseline) / baseline) if baseline else None,
        }
    return result


def run_seed(
    manifest: dict,
    profile_id: str,
    output_dir: Path,
    netlist: Path,
    seed: int,
) -> dict:
    profile_dir = output_dir / profile_id
    profile_dir.mkdir(parents=True, exist_ok=True)
    config = profile_dir / f"seed_{seed}.config"
    bitstream = profile_dir / f"seed_{seed}.bit"
    log_path = profile_dir / f"seed_{seed}.log"
    pack_log_path = profile_dir / f"seed_{seed}_ecppack.log"
    target = manifest["target"]
    command = [
        require_tool("nextpnr-ecp5"),
        str(target["density_flag"]),
        "--package",
        str(target["package"]),
        "--speed",
        str(target["speed_grade"]),
        "--json",
        str(netlist),
        "--textcfg",
        str(config),
        "--freq",
        str(target["requested_clock_mhz"]),
        "--seed",
        str(seed),
        "--timing-allow-fail",
    ]
    start = time.monotonic()
    timed_out = False
    try:
        process = run_cmd(command, check=False, timeout=900)
        returncode: int | None = process.returncode
        log = process.stdout
    except subprocess.TimeoutExpired as error:
        timed_out = True
        returncode = None
        raw = error.stdout or ""
        log = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
    runtime_seconds = time.monotonic() - start
    log_path.write_text(log, encoding="utf-8")

    routed = (
        not timed_out
        and returncode == 0
        and config.exists()
        and config.stat().st_size > 0
    )
    packed = False
    pack_returncode: int | None = None
    pack_log = ""
    if routed:
        pack = run_cmd(
            [require_tool("ecppack"), str(config), str(bitstream)],
            check=False,
            timeout=300,
        )
        pack_returncode = pack.returncode
        pack_log = pack.stdout
        pack_log_path.write_text(pack_log, encoding="utf-8")
        packed = (
            pack.returncode == 0
            and bitstream.exists()
            and bitstream.stat().st_size > 0
        )

    fmax_mhz = parse_fmax(log)
    timing_pass = bool(
        routed
        and fmax_mhz is not None
        and fmax_mhz >= float(target["requested_clock_mhz"])
    )
    utilization = {
        "comb": parse_utilization(log, "TRELLIS_COMB"),
        "ff": parse_utilization(log, "TRELLIS_FF"),
        "mult": parse_utilization(log, "MULT18X18D"),
        "ebr": parse_utilization(log, "DP16KD"),
    }
    return {
        "seed": seed,
        "timed_out": timed_out,
        "nextpnr_returncode": returncode,
        "runtime_seconds": round(runtime_seconds, 3),
        "routed": routed,
        "packed": packed,
        "pack_returncode": pack_returncode,
        "fmax_mhz": fmax_mhz,
        "timing_10mhz_pass": timing_pass,
        "capacity_signal": looks_like_capacity_failure(log),
        "utilization": utilization,
        "config_bytes": config.stat().st_size if config.exists() else 0,
        "bitstream_bytes": bitstream.stat().st_size if bitstream.exists() else 0,
        "log": str(log_path),
        "config": str(config) if config.exists() else None,
        "bitstream": str(bitstream) if bitstream.exists() else None,
        "pack_log": str(pack_log_path) if pack_log_path.exists() else None,
        "log_tail": "\n".join(log.splitlines()[-40:]),
        "pack_log_tail": "\n".join(pack_log.splitlines()[-20:]),
    }


def _max_fraction(
    manifest: dict,
    synthesis: dict,
    seeds: list[dict],
    resource: str,
) -> float:
    capacity_key = {
        "comb": "trellis_comb",
        "ff": "trellis_ff",
    }[resource]
    capacity = int(manifest["device_capacity"][capacity_key])
    synthesis_key = capacity_key
    fractions = [int(synthesis[synthesis_key]) / capacity]
    for seed in seeds:
        row = seed["utilization"].get(resource)
        if row and row.get("fraction") is not None:
            fractions.append(float(row["fraction"]))
    return max(fractions)


def summarize_physical(
    manifest: dict,
    synthesis: dict,
    seeds: list[dict],
    anti_pruning: dict,
) -> dict:
    route_gate = manifest["route_deployable_gate"]
    successful_routes = sum(bool(row["routed"]) for row in seeds)
    packed_bitstreams = sum(bool(row["packed"]) for row in seeds)
    timing_passes = sum(bool(row["timing_10mhz_pass"]) for row in seeds)
    fmax_values = [
        float(row["fmax_mhz"])
        for row in seeds
        if row["routed"] and row["fmax_mhz"] is not None
    ]
    route_deployable = (
        anti_pruning["passed"]
        and synthesis["mult18x18d"] == 0
        and successful_routes >= int(route_gate["minimum_successful_routes"])
        and packed_bitstreams >= int(route_gate["minimum_nonempty_bitstreams"])
        and timing_passes >= int(route_gate["minimum_10mhz_timing_passes"])
    )

    fractions = {
        "comb": _max_fraction(manifest, synthesis, seeds, "comb"),
        "ff": _max_fraction(manifest, synthesis, seeds, "ff"),
        "mult": 0.0 if synthesis["mult18x18d"] == 0 else (
            int(synthesis["mult18x18d"])
            / int(manifest["device_capacity"]["mult18x18d"])
        ),
    }
    headroom = manifest["board_handoff_headroom"]
    headroom_pass = (
        fractions["comb"] <= float(headroom["maximum_comb_fraction"])
        and fractions["ff"] <= float(headroom["maximum_ff_fraction"])
        and fractions["mult"] == float(headroom["required_mult18x18d_fraction"])
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
        "timeout_count": sum(bool(row["timed_out"]) for row in seeds),
    }


def choose_decision(manifest: dict, profiles: dict[str, dict]) -> tuple[str, str | None]:
    selected: str | None = None
    for profile_id in manifest["handoff_tier_order"]:
        if profiles[profile_id]["physical"]["board_handoff_eligible"]:
            selected = profile_id
            break

    if selected == "PROOF_EDGE_SHA1_NODSP":
        return "PROOF_EDGE_NODSP_BOARD_HANDOFF_SUPPORTED", selected
    if selected == "CORE_LITE_R40_NODSP":
        return "CORE_LITE_NODSP_BOARD_HANDOFF_SUPPORTED", selected
    if any(row["physical"]["route_deployable"] for row in profiles.values()):
        return "NODSP_ROUTABLE_BUT_HEADROOM_NOT_SUPPORTED", None
    return "NO_NODSP_PROFILE_ROUTE_DEPLOYABLE", None


def run(output_dir: Path) -> dict:
    manifest = load_manifest()
    profiles = profile_map(manifest)
    preservation = source_preservation_gate(manifest)
    output_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, dict] = {}
    with tempfile.TemporaryDirectory(prefix="cosmic-hw15-") as temp_name:
        tmp = Path(temp_name)
        for profile_id in [row["id"] for row in manifest["profiles"]]:
            profile = profiles[profile_id]
            smoke = harness_smoke(profile, tmp)

            auto_core, _ = synth_profile(profile, tmp, harness=False, nodsp=False)
            auto_harness, _ = synth_profile(profile, tmp, harness=True, nodsp=False)
            control = reproduce_auto_control(profile, auto_harness)

            nodsp_core, _ = synth_profile(profile, tmp, harness=False, nodsp=True)
            nodsp_harness, nodsp_netlist = synth_profile(
                profile, tmp, harness=True, nodsp=True
            )
            if nodsp_core["mult18x18d"] != 0 or nodsp_harness["mult18x18d"] != 0:
                raise RuntimeError(
                    f"NODSP mapping retained hard multipliers for {profile_id}: "
                    f"core={nodsp_core['mult18x18d']} harness={nodsp_harness['mult18x18d']}"
                )
            anti = anti_pruning_gate(manifest, nodsp_core, nodsp_harness)

            seeds = [
                run_seed(manifest, profile_id, output_dir, nodsp_netlist, int(seed))
                for seed in manifest["placement_seeds"]
            ]
            physical = summarize_physical(manifest, nodsp_harness, seeds, anti)
            results[profile_id] = {
                "tier": int(profile["tier"]),
                "control_id": str(profile["control_id"]),
                "top_module": str(profile["top_module"]),
                "harness_top": str(profile["harness_top"]),
                "required_evidence": list(profile["required_evidence"]),
                "smoke": smoke,
                "auto_dsp_control": {
                    "reproduction": control,
                    "core_synthesis": auto_core,
                    "harness_synthesis": auto_harness,
                },
                "nodsp_candidate": {
                    "core_synthesis": nodsp_core,
                    "harness_synthesis": nodsp_harness,
                    "structural_delta_vs_auto_harness": structural_delta(
                        auto_harness, nodsp_harness
                    ),
                },
                "anti_pruning": anti,
                "seeds": seeds,
                "physical": physical,
            }

    decision, selected = choose_decision(manifest, results)
    if decision not in manifest["decision_classes"]:
        raise RuntimeError(f"HW-15 decision outside frozen classes: {decision}")

    return {
        "benchmark_id": "COSMIC-HW-15-CANDIDATE",
        "protocol": "COSMIC-HW-15/v0.1",
        "parent_hw14_source_head": manifest["parent"]["source_head"],
        "target": manifest["target"],
        "placement_seeds": manifest["placement_seeds"],
        "mapping_intervention": manifest["mapping_intervention"],
        "source_preservation": preservation,
        "inherited_semantic_gates_revalidated_by_workflow": [
            "HW-07 exact receipt semantics",
            "HW-08 standard SHA-256 commitment semantics",
        ],
        "profiles": results,
        "frozen_full_profile_control": manifest["frozen_full_profile_control"],
        "decision": decision,
        "selected_board_handoff_profile": selected,
        "synthetic_combined_score_used": False,
        "claim_boundary": manifest["claim_boundary"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Execute the frozen COSMIC-HW-15 DSP-free mapping frontier"
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/tmp/cosmic-hw-15-evidence"),
    )
    args = parser.parse_args()
    result = run(args.output_dir)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            f"COSMIC_HW15_RESULT decision={result['decision']} "
            f"selected={result['selected_board_handoff_profile']}"
        )


if __name__ == "__main__":
    main()
