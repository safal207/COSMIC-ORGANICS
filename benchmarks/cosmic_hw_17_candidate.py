from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import time
from typing import Any

from benchmarks.cosmic_hw_13_candidate import (
    looks_like_capacity_failure,
    require_tool,
    run_cmd,
)
from benchmarks.cosmic_hw_14_candidate import parse_utilization
from benchmarks.cosmic_hw_16_candidate import (
    CONSTRAINTS_PATH,
    anti_pruning,
    input_clock_constraint_gate,
    load_manifest as load_hw16_manifest,
    parse_clock_reports,
    preservation_gate,
    simulate_uart,
    synthesize,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks" / "cosmic_hw_17_manifest.json"
EXPECTED_SEEDS = [1601, 1602, 1603, 1604, 1605]
CAPACITY = 83640


def load_manifest() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest["benchmark_id"] != "COSMIC-HW-17-PREREG":
        raise RuntimeError("HW-17 benchmark identity moved")
    if manifest["protocol"] != "COSMIC-HW-17/v0.1":
        raise RuntimeError("HW-17 protocol moved")
    if manifest["issue_number"] != 118:
        raise RuntimeError("HW-17 tracking issue moved")
    if manifest["parent"]["source_head"] != "1bb067bb7b325405eca703a16536eea79495410e":
        raise RuntimeError("HW-17 parent head moved")
    if manifest["seeds"] != EXPECTED_SEEDS:
        raise RuntimeError("HW-17 seeds moved")
    intervention = manifest["intervention"]
    if intervention["candidate_timeout_seconds"] != 2400:
        raise RuntimeError("HW-17 candidate timeout moved")
    if intervention["control_timeout_seconds"] != 1200:
        raise RuntimeError("HW-17 control timeout moved")
    if intervention["only_admitted_change"] != "per_seed_nextpnr_timeout_seconds":
        raise RuntimeError("HW-17 intervention moved")
    return manifest


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prepare(output_dir: Path) -> dict[str, Any]:
    manifest = load_manifest()
    hw16 = load_hw16_manifest()
    output_dir.mkdir(parents=True, exist_ok=True)

    preservation = preservation_gate(hw16)
    simulation = simulate_uart(output_dir)
    core_summary, _ = synthesize(output_dir, board=False)
    board_summary, board_netlist = synthesize(output_dir, board=True)
    pruning = anti_pruning(core_summary, board_summary)

    expected = manifest["parent"]["synthesis"]
    observed = {
        "trellis_comb": board_summary["trellis_comb"],
        "trellis_ff": board_summary["trellis_ff"],
        "mult18x18d": board_summary["mult18x18d"],
        "ehxplll": board_summary["cell_types"].get("EHXPLLL", 0),
    }
    if observed != expected:
        raise RuntimeError(f"HW-17 parent synthesis reproduction failed: {observed} != {expected}")
    if simulation["frame_sha256"] != manifest["frozen_oracle"]["frame_sha256"]:
        raise RuntimeError("HW-17 UART oracle fingerprint moved")

    netlist_sha256 = sha256_file(board_netlist)
    destination = output_dir / "cosmic_hw_17_board.json"
    if board_netlist.resolve() != destination.resolve():
        destination.write_bytes(board_netlist.read_bytes())
    if sha256_file(destination) != netlist_sha256:
        raise RuntimeError("HW-17 netlist copy mismatch")

    result = {
        "benchmark_id": "COSMIC-HW-17-PREPARE",
        "protocol": manifest["protocol"],
        "source_head": os.environ.get("COSMIC_SOURCE_HEAD") or os.environ.get("GITHUB_SHA"),
        "parent_source_head": manifest["parent"]["source_head"],
        "candidate_timeout_seconds": manifest["intervention"]["candidate_timeout_seconds"],
        "seeds": manifest["seeds"],
        "preservation": preservation,
        "simulation": simulation,
        "synthesis": {"core": core_summary, "board": board_summary},
        "anti_pruning": pruning,
        "board_netlist": destination.name,
        "board_netlist_sha256": netlist_sha256,
        "control_reproduction_passed": True,
    }
    write_json(output_dir / "cosmic_hw_17_prepare.json", result)
    return result


def clock_gate(reports: list[dict[str, Any]], target: float) -> bool:
    return any(abs(float(row["target_mhz"]) - target) < 0.05 and bool(row["passed"]) for row in reports)


def run_seed(
    prepared_dir: Path,
    output_dir: Path,
    seed: int,
) -> dict[str, Any]:
    manifest = load_manifest()
    if seed not in EXPECTED_SEEDS:
        raise RuntimeError(f"HW-17 unexpected seed: {seed}")

    prepare_summary = json.loads(
        (prepared_dir / "cosmic_hw_17_prepare.json").read_text(encoding="utf-8")
    )
    netlist = prepared_dir / prepare_summary["board_netlist"]
    if not netlist.is_file():
        raise RuntimeError("HW-17 prepared netlist missing")
    actual_netlist_sha = sha256_file(netlist)
    if actual_netlist_sha != prepare_summary["board_netlist_sha256"]:
        raise RuntimeError("HW-17 prepared netlist fingerprint mismatch")

    output_dir.mkdir(parents=True, exist_ok=True)
    config = output_dir / "cosmic_hw17_ulx3s.config"
    bitstream = output_dir / "cosmic_hw17_ulx3s.bit"
    route_log = output_dir / "nextpnr.log"
    pack_log = output_dir / "ecppack.log"
    board = manifest["board"]
    timeout_seconds = int(manifest["intervention"]["candidate_timeout_seconds"])
    command = [
        require_tool("nextpnr-ecp5"),
        str(board["density_flag"]),
        "--package",
        str(board["package"]),
        "--speed",
        str(board["speed_grade"]),
        "--json",
        str(netlist),
        "--lpf",
        str(CONSTRAINTS_PATH),
        "--textcfg",
        str(config),
        "--freq",
        str(board["processor_clock_mhz"]),
        "--seed",
        str(seed),
        "--timing-allow-fail",
    ]

    start = time.monotonic()
    timed_out = False
    try:
        process = run_cmd(command, check=False, timeout=timeout_seconds)
        returncode: int | None = process.returncode
        log = process.stdout
    except subprocess.TimeoutExpired as error:
        timed_out = True
        returncode = None
        raw = error.stdout or ""
        log = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
    runtime = time.monotonic() - start
    route_log.write_text(log, encoding="utf-8")

    routed = (
        not timed_out
        and returncode == 0
        and config.is_file()
        and config.stat().st_size > 0
    )
    packed = False
    pack_returncode: int | None = None
    pack_text = ""
    if routed:
        pack = run_cmd(
            [
                require_tool("ecppack"),
                "--idcode",
                "0x41113043",
                str(config),
                str(bitstream),
            ],
            check=False,
            timeout=300,
        )
        pack_returncode = pack.returncode
        pack_text = pack.stdout
        pack_log.write_text(pack_text, encoding="utf-8")
        packed = (
            pack_returncode == 0
            and bitstream.is_file()
            and bitstream.stat().st_size > 0
        )

    reports = parse_clock_reports(log)
    input_constraint = input_clock_constraint_gate(log)
    input_pass = routed and bool(input_constraint["passed"])
    processor_pass = routed and clock_gate(reports, 10.0)
    capacity_signal = looks_like_capacity_failure(log)
    utilization = {
        "comb": parse_utilization(log, "TRELLIS_COMB"),
        "ff": parse_utilization(log, "TRELLIS_FF"),
        "mult": parse_utilization(log, "MULT18X18D"),
        "ebr": parse_utilization(log, "DP16KD"),
    }
    fully_qualified = (
        routed
        and packed
        and input_pass
        and processor_pass
        and not capacity_signal
        and bitstream.is_file()
        and bitstream.stat().st_size > 0
    )
    if timed_out or not routed:
        runtime_bucket = "NOT_COMPLETED_WITHIN_2400"
    elif runtime <= 1200:
        runtime_bucket = "PARENT_BUDGET_0_1200"
    else:
        runtime_bucket = "EXTENDED_BUDGET_1200_2400"

    result = {
        "benchmark_id": "COSMIC-HW-17-SEED",
        "protocol": manifest["protocol"],
        "source_head": os.environ.get("COSMIC_SOURCE_HEAD") or os.environ.get("GITHUB_SHA"),
        "parent_source_head": manifest["parent"]["source_head"],
        "seed": seed,
        "attempt": 1,
        "timeout_seconds": timeout_seconds,
        "timed_out": timed_out,
        "returncode": returncode,
        "runtime_seconds": round(runtime, 3),
        "runtime_bucket": runtime_bucket,
        "routed": routed,
        "packed": packed,
        "pack_returncode": pack_returncode,
        "input_25mhz_timing_pass": input_pass,
        "input_25mhz_constraint_evidence": input_constraint,
        "processor_10mhz_timing_pass": processor_pass,
        "clock_reports": reports,
        "capacity_signal": capacity_signal,
        "fully_qualified": fully_qualified,
        "utilization": utilization,
        "config_bytes": config.stat().st_size if config.is_file() else 0,
        "bitstream_bytes": bitstream.stat().st_size if bitstream.is_file() else 0,
        "bitstream_sha256": sha256_file(bitstream) if packed else None,
        "board_netlist_sha256": actual_netlist_sha,
        "config": str(config) if config.is_file() else None,
        "bitstream": str(bitstream) if bitstream.is_file() else None,
        "route_log": str(route_log),
        "pack_log": str(pack_log) if pack_log.is_file() else None,
        "route_log_tail": "\n".join(log.splitlines()[-80:]),
        "pack_log_tail": "\n".join(pack_text.splitlines()[-20:]),
    }
    write_json(output_dir / f"cosmic_hw_17_seed_{seed}.json", result)
    return result


def recursive_json_files(path: Path, pattern: str) -> list[Path]:
    return sorted(path.rglob(pattern))


def resource_fraction(
    board_summary: dict[str, Any],
    seeds: list[dict[str, Any]],
    resource: str,
) -> float:
    key = "trellis_comb" if resource == "comb" else "trellis_ff"
    values = [float(board_summary[key]) / CAPACITY]
    for seed in seeds:
        row = seed["utilization"].get(resource)
        if row and row.get("fraction") is not None:
            values.append(float(row["fraction"]))
    return max(values)


def aggregate(prepared_dir: Path, seeds_dir: Path, output_dir: Path) -> dict[str, Any]:
    manifest = load_manifest()
    prepare_summary = json.loads(
        (prepared_dir / "cosmic_hw_17_prepare.json").read_text(encoding="utf-8")
    )
    seed_files = recursive_json_files(seeds_dir, "cosmic_hw_17_seed_*.json")
    seeds = [json.loads(path.read_text(encoding="utf-8")) for path in seed_files]
    observed_seeds = sorted(int(row["seed"]) for row in seeds)
    if observed_seeds != EXPECTED_SEEDS or len(seeds) != 5:
        raise RuntimeError(f"HW-17 requires exactly five unique seed records: {observed_seeds}")
    if any(int(row["attempt"]) != 1 for row in seeds):
        raise RuntimeError("HW-17 seed retry detected")

    expected_netlist_sha = prepare_summary["board_netlist_sha256"]
    if any(row["board_netlist_sha256"] != expected_netlist_sha for row in seeds):
        raise RuntimeError("HW-17 seed netlist fingerprints diverged")
    expected_head = prepare_summary.get("source_head")
    if expected_head and any(row.get("source_head") != expected_head for row in seeds):
        raise RuntimeError("HW-17 seed source heads diverged")

    board_summary = prepare_summary["synthesis"]["board"]
    fully_qualified = [row for row in seeds if row["fully_qualified"]]
    comb_fraction = resource_fraction(board_summary, seeds, "comb")
    ff_fraction = resource_fraction(board_summary, seeds, "ff")
    zero_dsp = board_summary["mult18x18d"] == 0
    ready = (
        prepare_summary["control_reproduction_passed"] is True
        and prepare_summary["preservation"]["passed"] is True
        and prepare_summary["simulation"]["passed"] is True
        and prepare_summary["anti_pruning"]["passed"] is True
        and len(fully_qualified) >= int(manifest["handoff_gate"]["minimum_fully_qualified_seeds"])
        and comb_fraction <= float(manifest["handoff_gate"]["maximum_comb_fraction"])
        and ff_fraction <= float(manifest["handoff_gate"]["maximum_ff_fraction"])
        and zero_dsp
    )
    decision = (
        "ULX3S_EXTENDED_BUDGET_BITSTREAM_READY"
        if ready
        else "NO_EXTENDED_BUDGET_BOARD_HANDOFF"
    )

    parent_timeouts = set(int(seed) for seed in manifest["parent"]["timed_out_seeds"])
    parent_successes = set(int(seed) for seed in manifest["parent"]["fully_qualified_seeds"])
    completed_after_parent_budget = [
        row["seed"]
        for row in fully_qualified
        if row["seed"] in parent_timeouts and float(row["runtime_seconds"]) > 1200
    ]
    completed_parent_timeout_within_1200 = [
        row["seed"]
        for row in fully_qualified
        if row["seed"] in parent_timeouts and float(row["runtime_seconds"]) <= 1200
    ]
    parent_successes_now_failed = [
        seed for seed in sorted(parent_successes) if seed not in {row["seed"] for row in fully_qualified}
    ]
    if completed_after_parent_budget:
        diagnosis = "TIMEOUT_CENSORING_OBSERVED"
    elif completed_parent_timeout_within_1200 or parent_successes_now_failed:
        diagnosis = "ROUTE_RUNTIME_VARIABILITY_OBSERVED"
    else:
        diagnosis = "PARENT_COMPLETION_PATTERN_REPRODUCED"

    canonical = min(fully_qualified, key=lambda row: int(row["seed"])) if fully_qualified else None
    fmax_values = [
        float(report["maximum_mhz"])
        for seed in fully_qualified
        for report in seed["clock_reports"]
        if abs(float(report["target_mhz"]) - 10.0) < 0.05
    ]
    result = {
        "benchmark_id": "COSMIC-HW-17-CANDIDATE",
        "protocol": manifest["protocol"],
        "source_head": expected_head,
        "parent_source_head": manifest["parent"]["source_head"],
        "parent_decision": manifest["parent"]["decision"],
        "intervention": manifest["intervention"],
        "prepare": prepare_summary,
        "seeds": seeds,
        "physical": {
            "fully_qualified_seed_count": len(fully_qualified),
            "fully_qualified_seeds": [row["seed"] for row in fully_qualified],
            "minimum_fully_qualified_seeds": manifest["handoff_gate"]["minimum_fully_qualified_seeds"],
            "maximum_comb_fraction": comb_fraction,
            "maximum_ff_fraction": ff_fraction,
            "zero_dsp": zero_dsp,
            "route_count": sum(bool(row["routed"]) for row in seeds),
            "pack_count": sum(bool(row["packed"]) for row in seeds),
            "input_25mhz_pass_count": sum(bool(row["input_25mhz_timing_pass"]) for row in seeds),
            "processor_10mhz_pass_count": sum(bool(row["processor_10mhz_timing_pass"]) for row in seeds),
            "timeout_count": sum(bool(row["timed_out"]) for row in seeds),
            "processor_fmax_mhz": {
                "values": fmax_values,
                "minimum": min(fmax_values) if fmax_values else None,
                "median": statistics.median(fmax_values) if fmax_values else None,
                "maximum": max(fmax_values) if fmax_values else None,
            },
            "canonical_seed": canonical["seed"] if canonical else None,
            "canonical_bitstream_sha256": canonical["bitstream_sha256"] if canonical else None,
            "canonical_bitstream_bytes": canonical["bitstream_bytes"] if canonical else 0,
        },
        "diagnosis": {
            "class": diagnosis,
            "completed_after_parent_budget": completed_after_parent_budget,
            "completed_parent_timeout_within_1200": completed_parent_timeout_within_1200,
            "parent_successes_now_failed": parent_successes_now_failed,
        },
        "decision": decision,
        "board_bitstream_ready": ready,
        "physical_board_executed": False,
        "synthetic_combined_score_used": False,
        "claim_boundary": manifest["claim_boundary"],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "cosmic_hw_17_result.json", result)
    if canonical:
        matching = [
            path
            for path in seeds_dir.rglob("cosmic_hw17_ulx3s.bit")
            if f"seed-{canonical['seed']}" in str(path.parent) or f"seed_{canonical['seed']}" in str(path.parent)
        ]
        if matching:
            destination = output_dir / "cosmic_hw_17_canonical.bit"
            destination.write_bytes(matching[0].read_bytes())
            if sha256_file(destination) != canonical["bitstream_sha256"]:
                raise RuntimeError("HW-17 canonical bitstream copy mismatch")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--output-dir", required=True)

    seed_parser = subparsers.add_parser("seed")
    seed_parser.add_argument("--prepared-dir", required=True)
    seed_parser.add_argument("--output-dir", required=True)
    seed_parser.add_argument("--seed", type=int, required=True)

    aggregate_parser = subparsers.add_parser("aggregate")
    aggregate_parser.add_argument("--prepared-dir", required=True)
    aggregate_parser.add_argument("--seeds-dir", required=True)
    aggregate_parser.add_argument("--output-dir", required=True)

    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(Path(args.output_dir))
    elif args.command == "seed":
        result = run_seed(Path(args.prepared_dir), Path(args.output_dir), args.seed)
    else:
        result = aggregate(Path(args.prepared_dir), Path(args.seeds_dir), Path(args.output_dir))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
