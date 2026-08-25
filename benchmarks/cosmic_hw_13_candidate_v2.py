from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks import cosmic_hw_13_candidate as base


BENCHMARK_ID = "COSMIC-HW-13-CANDIDATE"


def synth_ecp5_flat(tmp: Path, top: str, include_harness: bool) -> tuple[dict, Path, str]:
    """Synthesize through an explicitly flattened ECP5 design.

    The first HW-13 hosted attempt produced a valid harness smoke result but the
    recursive JSON counter saw an empty top module for both core and harness.
    This replacement changes measurement plumbing only: it explicitly flattens
    before `synth_ecp5 -noflatten`, then refuses to interpret a zero-cell report.
    The frozen RTL, target, seeds, timing threshold and decision rules are
    unchanged.
    """

    yosys = base.require_tool("yosys")
    netlist = tmp / f"{top}_flat.json"
    sources = base.RTL_SOURCES + ([base.HARNESS] if include_harness else [])
    source_text = " ".join(str(path) for path in sources)
    script = (
        f"read_verilog -sv {source_text}; "
        f"hierarchy -check -top {top}; "
        "flatten; clean -purge; "
        f"synth_ecp5 -noflatten -top {top}; "
        "clean -purge; "
        f"stat -top {top}; write_json {netlist}"
    )
    proc = base.run_cmd([yosys, "-p", script])
    counts = base.recursive_cell_counts(netlist, top)
    summary = base.summarize_ecp5_cells(counts)
    summary["measurement_method"] = "explicit_flatten+synth_ecp5_noflatten+recursive_json"

    # A zero-cell report is not a scientific negative result. It is an invalid
    # measurement and must stop before anti-pruning or physical classification.
    if summary["total_leaf_cells"] <= 0:
        raise RuntimeError(
            f"invalid zero-cell ECP5 synthesis report for top={top}\n"
            + "\n".join(proc.stdout.splitlines()[-160:])
        )
    if summary["trellis_comb"] <= 0 or summary["trellis_ff"] <= 0:
        raise RuntimeError(
            f"incomplete ECP5 primitive accounting for top={top}: {summary}\n"
            + "\n".join(proc.stdout.splitlines()[-160:])
        )
    return summary, netlist, proc.stdout


def run() -> dict:
    original = base.synth_ecp5
    try:
        base.synth_ecp5 = synth_ecp5_flat
        result = base.run()
    finally:
        base.synth_ecp5 = original

    result["measurement_correction"] = {
        "scope": "ECP5 synthesis accounting only",
        "first_run_decision": "HARNESS_PRESERVATION_FAILURE",
        "first_run_reason": "both recursive synthesis summaries were zero-cell",
        "rtl_changed": False,
        "target_changed": False,
        "seeds_changed": False,
        "thresholds_changed": False,
        "fail_closed_on_zero_cell_report": True,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            "COSMIC_HW13_V2 "
            f"decision={result['decision']} "
            f"routes={result['physical_summary']['successful_routes_and_packs']} "
            f"timing_passes={result['physical_summary']['timing_10mhz_passes']}"
        )


if __name__ == "__main__":
    main()
