#!/usr/bin/env python3
"""Focused verifier for the COSMIC ORGANICS research release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_OUTPUT = ROOT / "artifacts" / "release" / "verified-incident-map.json"
DEFAULT_FPGA_OUTPUT = ROOT / "artifacts" / "release" / "hw13-ecp5.json"

FOCUSED_TESTS = [
    "tests/test_cosmic_kernel.py",
    "tests/test_sparse_scheduler.py",
    "tests/test_dag_parent_commit.py",
    "tests/test_verified_incident_map.py",
]

EXPECTED_DEMO = {
    "status": "PASS",
    "map": {
        "width": 16,
        "height": 16,
        "cells": 256,
        "logical_ticks": 24,
    },
    "result": {
        "completed_transitions": 40,
        "audited_transitions": 40,
        "final_phase_counts": {"A": 256, "M": 0, "C": 0},
    },
    "execution_work": {
        "dense_node_evaluations": 6144,
        "sparse_node_evaluations": 164,
        "reduction_fraction": 0.9733072916666666,
    },
    "evidence": {
        "proof_canonical_bytes": 77666,
        "proof_sha256": "d9e93b9827115fd96b9bd16869e4f3d97d59b50298f67804e40949e4faed393b",
    },
}


class VerificationError(RuntimeError):
    """Raised when a release gate does not match frozen evidence."""


def run_command(
    command: list[str],
    *,
    timeout: int = 1800,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(command), flush=True)
    return subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=capture,
        timeout=timeout,
    )


def require_tools(names: list[str], mode: str) -> None:
    missing = [name for name in names if shutil.which(name) is None]
    if missing:
        joined = ", ".join(missing)
        raise VerificationError(
            f"{mode} was requested but required tools are missing: {joined}. "
            "Install them or rerun without that optional flag."
        )


def verify_software_tests(extended: bool) -> None:
    try:
        import pytest  # noqa: F401
    except ImportError as exc:
        raise VerificationError(
            "pytest is required. Install it with: python -m pip install pytest"
        ) from exc

    run_command([sys.executable, "-m", "pytest", "-q", *FOCUSED_TESTS])

    if extended:
        run_command(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests",
                "--ignore-glob=tests/test_cosmic_hw_*",
            ],
            timeout=3600,
        )


def require_equal(label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise VerificationError(
            f"{label} changed: expected={expected!r}, actual={actual!r}"
        )


def verify_demo(output_path: Path) -> dict[str, Any]:
    from demos.verified_incident_map import run_demo

    result = run_demo()

    require_equal("demo status", result.get("status"), EXPECTED_DEMO["status"])

    map_data = result.get("map", {})
    for key, expected in EXPECTED_DEMO["map"].items():
        require_equal(f"map.{key}", map_data.get(key), expected)

    result_data = result.get("result", {})
    for key, expected in EXPECTED_DEMO["result"].items():
        require_equal(f"result.{key}", result_data.get(key), expected)

    correctness = result.get("correctness", {})
    required_true = [
        "per_tick_dense_sparse_equal",
        "final_state_equal",
        "transition_count_equal",
        "transition_replay_equal",
        "dense_proof_valid",
        "sparse_proof_valid",
        "proof_representation_equal",
        "mutated_transition_claim_rejected",
    ]
    for key in required_true:
        require_equal(f"correctness.{key}", correctness.get(key), True)

    work = result.get("execution_work", {})
    dense = work.get("dense", {})
    sparse = work.get("sparse", {})
    require_equal(
        "execution_work.dense.node_evaluations",
        dense.get("node_evaluations"),
        EXPECTED_DEMO["execution_work"]["dense_node_evaluations"],
    )
    require_equal(
        "execution_work.sparse.node_evaluations",
        sparse.get("node_evaluations"),
        EXPECTED_DEMO["execution_work"]["sparse_node_evaluations"],
    )
    reduction = float(work.get("sparse_node_evaluation_reduction_fraction", -1.0))
    expected_reduction = EXPECTED_DEMO["execution_work"]["reduction_fraction"]
    if abs(reduction - expected_reduction) > 1e-12:
        raise VerificationError(
            "demo node-evaluation reduction changed: "
            f"expected={expected_reduction} actual={reduction}"
        )

    evidence = result.get("evidence", {})
    for key, expected in EXPECTED_DEMO["evidence"].items():
        require_equal(f"evidence.{key}", evidence.get(key), expected)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    try:
        display_path = output_path.relative_to(ROOT)
    except ValueError:
        display_path = output_path
    print(
        "SOFTWARE_DEMO PASS "
        f"transitions={result_data['completed_transitions']} "
        f"sparse_reduction={reduction:.6%} "
        f"artifact={display_path}",
        flush=True,
    )
    return result


def verify_rtl_smoke() -> None:
    require_tools(["iverilog", "vvp"], "RTL smoke")
    completed = run_command(
        [sys.executable, "benchmarks/run_cosmic_hw_12_hmac_kat.py"],
        timeout=1200,
        capture=True,
    )
    output = completed.stdout + completed.stderr
    marker = "COSMIC_HW12_HMAC_KAT PASS vectors=446 compressions=1784 frozen_roots=444"
    if marker not in output:
        raise VerificationError("RTL HMAC KAT PASS marker was not found")
    print(marker, flush=True)


def verify_fpga(output_path: Path) -> None:
    require_tools(
        ["yosys", "iverilog", "vvp", "nextpnr-ecp5", "ecppack"],
        "FPGA reproduction",
    )
    completed = run_command(
        [
            sys.executable,
            "benchmarks/cosmic_hw_13_candidate_v2.py",
            "--json",
        ],
        timeout=10800,
        capture=True,
    )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise VerificationError(
            "HW-13 runner did not emit valid JSON. stderr:\n" + completed.stderr[-4000:]
        ) from exc

    require_equal(
        "frozen HW-13 decision",
        result.get("decision"),
        "DEVICE_CAPACITY_NOT_SUPPORTED",
    )

    physical = result.get("physical_summary", {})
    require_equal(
        "physical_summary.successful_routes_and_packs",
        physical.get("successful_routes_and_packs"),
        0,
    )
    require_equal(
        "physical_summary.timing_10mhz_passes",
        physical.get("timing_10mhz_passes"),
        0,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    try:
        display_path = output_path.relative_to(ROOT)
    except ValueError:
        display_path = output_path
    print(
        "FPGA_REPRODUCTION PASS "
        "decision=DEVICE_CAPACITY_NOT_SUPPORTED "
        f"artifact={display_path}",
        flush=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify the focused COSMIC ORGANICS research release."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path for the verified incident-demo JSON artifact.",
    )
    parser.add_argument(
        "--extended-software",
        action="store_true",
        help="Also run the broader software-only pytest suite.",
    )
    parser.add_argument(
        "--rtl-smoke",
        action="store_true",
        help="Run the 446-vector HMAC-SHA256 RTL KAT; requires Icarus Verilog.",
    )
    parser.add_argument(
        "--fpga",
        action="store_true",
        help="Reproduce the frozen ECP5-85F capacity result; requires the open FPGA toolchain.",
    )
    parser.add_argument(
        "--fpga-output",
        type=Path,
        default=DEFAULT_FPGA_OUTPUT,
        help="Path for the optional HW-13 JSON artifact.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        verify_software_tests(args.extended_software)
        verify_demo(args.output)
        if args.rtl_smoke:
            verify_rtl_smoke()
        if args.fpga:
            verify_fpga(args.fpga_output)
    except (VerificationError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(f"RELEASE_VERIFICATION FAIL: {exc}", file=sys.stderr)
        return 1

    print("COSMIC_RELEASE_VERIFY PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
