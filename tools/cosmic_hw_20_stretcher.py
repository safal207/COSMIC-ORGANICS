from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.cosmic_hw_13_candidate import (
    recursive_cell_counts,
    require_tool,
    run_cmd,
    summarize_ecp5_cells,
)
from benchmarks.cosmic_hw_16_candidate import run_seed
from tools.cosmic_hw_19_compare import (
    load_manifest as load_hw19_manifest,
    simulate_hardware_model as simulate_hw19,
)


MANIFEST_PATH = ROOT / "benchmarks" / "cosmic_hw_20_manifest.json"
TOP_PATH = ROOT / "rtl" / "cosmic_hw_20_stretcher_top.v"
PLL_PATH = ROOT / "rtl" / "cosmic_hw_16_pll_10mhz.v"
EXPECTED_PARENT_HEAD = "b70abe70614a0d98cadb2887eb6ee1b5e6d27838"
EXPECTED_PARENT_TREE = "183f145516bfb2d969d6db1ebf38e1d03b41c878"
EXPECTED_LAST_DIGEST = "c31bff9259318b3309bdb0fdd5282ce58366d6d8d1b9c636080eb6482a230ab2"

PROCESSOR_SOURCES = [
    ROOT / "rtl" / "cosmic_hw_06.v",
    ROOT / "rtl" / "cosmic_hw_07_receipt.v",
    ROOT / "rtl" / "cosmic_hw_08_sha256.v",
    ROOT / "rtl" / "cosmic_hw_09_multi_sha.v",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def load_manifest() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest["experiment_id"] != "COSMIC-HW-20/v0.1":
        raise RuntimeError("HW-20 experiment identity moved")
    if manifest["protocol"] != "COSMIC-HW-20-STRETCHER/v0.1":
        raise RuntimeError("HW-20 protocol moved")
    parent = manifest["parent"]
    if parent["source_head"] != EXPECTED_PARENT_HEAD:
        raise RuntimeError("HW-20 parent head moved")
    if parent["source_tree"] != EXPECTED_PARENT_TREE:
        raise RuntimeError("HW-20 parent tree moved")
    if parent["physical_hil_state"] != "NOT_RUN":
        raise RuntimeError("HW-20 physical state must start NOT_RUN")
    if manifest["workload"]["last_digest"] != EXPECTED_LAST_DIGEST:
        raise RuntimeError("HW-20 digest oracle moved")
    architecture = manifest["stretcher_architecture"]
    if architecture["physical_sha256_engines"] != 2:
        raise RuntimeError("HW-20 must have exactly two physical SHA engines")
    if architecture["virtual_third_slot_is_compute_engine"] is not False:
        raise RuntimeError("HW-20 waiting slot may not be labeled a compute engine")
    for relative, expected in manifest["inherited_source_blobs"].items():
        actual = git_blob_sha(ROOT / relative)
        if actual != expected:
            raise RuntimeError(
                f"HW-20 inherited source moved: {relative} expected={expected} actual={actual}"
            )
    return manifest


def run(command: list[str], *, timeout: int = 600) -> str:
    process = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
    )
    if process.returncode != 0:
        raise RuntimeError(
            f"command failed ({process.returncode}): {' '.join(command)}\n{process.stdout}"
        )
    return process.stdout


def git_identity() -> dict[str, Any]:
    def git(*args: str) -> str:
        return run(["git", *args]).strip()

    status = git("status", "--porcelain=v1", "--untracked-files=all")
    identity = {
        "head": git("rev-parse", "HEAD"),
        "tree": git("rev-parse", "HEAD^{tree}"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "clean": not bool(status),
        "status": status.splitlines(),
    }
    expected = os.environ.get("COSMIC_HW20_EXPECTED_HEAD")
    if expected and identity["head"] != expected:
        raise RuntimeError(
            f"HW-20 checkout does not match workflow head: {identity['head']} != {expected}"
        )
    return identity


def cycle_testbench() -> str:
    return r'''`timescale 1ns/1ps
module cosmic_hw20_cycle_tb;
  reg clk = 1'b0;
  reg reset = 1'b1;
  wire [3:0] state;
  wire [15:0] accepted_ticks;
  wire [31:0] receipt_count;
  wire [15:0] digest_count;
  wire [255:0] last_digest;
  wire [15:0] error_flags;
  wire [3:0] busy_mask;
  wire [3:0] digest_valid_mask;
  wire [3:0] accept_mask;
  wire waiting_valid;
  wire [3:0] fill_count;
  integer cycles = 0;
  integer both_busy_cycles = 0;
  integer queued_behind_busy_cycles = 0;
  integer engine0_accepts = 0;
  integer engine1_accepts = 0;

  always #50 clk = ~clk;
  always @(posedge clk) begin
    if (!reset) begin
      cycles = cycles + 1;
      if (busy_mask[1:0] == 2'b11)
        both_busy_cycles = both_busy_cycles + 1;
      if (busy_mask[1:0] == 2'b11 && waiting_valid)
        queued_behind_busy_cycles = queued_behind_busy_cycles + 1;
      if (accept_mask[0]) engine0_accepts = engine0_accepts + 1;
      if (accept_mask[1]) engine1_accepts = engine1_accepts + 1;
    end
  end

  cosmic_hw20_stretcher_selftest dut (
    .clk(clk), .reset(reset), .state_debug(state),
    .accepted_tick_count_debug(accepted_ticks),
    .receipt_count_debug(receipt_count), .digest_count_debug(digest_count),
    .last_digest_debug(last_digest), .error_flags_debug(error_flags),
    .engine_busy_mask_debug(busy_mask),
    .engine_digest_valid_mask_debug(digest_valid_mask),
    .engine_block_accept_mask_debug(accept_mask),
    .waiting_block_valid_debug(waiting_valid), .fill_count_debug(fill_count)
  );

  initial begin
    repeat (8) @(posedge clk);
    @(negedge clk); reset = 1'b0;
    wait(state == 4'd5);
    #1;
    if (accepted_ticks != 16'd2) $fatal(1, "accepted tick mismatch");
    if (receipt_count != 32'd128) $fatal(1, "receipt count mismatch");
    if (digest_count != 16'd13) $fatal(1, "digest count mismatch");
    if (last_digest != 256'hc31bff9259318b3309bdb0fdd5282ce58366d6d8d1b9c636080eb6482a230ab2)
      $fatal(1, "last digest mismatch");
    if (error_flags != 16'd0) $fatal(1, "error flags set: %h", error_flags);
    if (engine0_accepts + engine1_accepts != 13)
      $fatal(1, "block accept total mismatch");
    if (engine0_accepts == 0 || engine1_accepts == 0)
      $fatal(1, "both physical engines were not used");
    if (queued_behind_busy_cycles == 0)
      $fatal(1, "virtual third slot never overlapped two busy engines");
    $display("COSMIC_HW20_COMPUTE_CYCLES=%0d", cycles);
    $display("COSMIC_HW20_BOTH_BUSY_CYCLES=%0d", both_busy_cycles);
    $display("COSMIC_HW20_QUEUED_BEHIND_BUSY_CYCLES=%0d", queued_behind_busy_cycles);
    $display("COSMIC_HW20_ENGINE_ACCEPTS=%0d,%0d", engine0_accepts, engine1_accepts);
    $display("COSMIC_HW20_LAST_DIGEST=%064x", last_digest);
    $finish;
  end

  initial begin
    repeat (200000) @(posedge clk);
    $fatal(1, "HW-20 simulation watchdog expired");
  end
endmodule
'''


def marker_value(output: str, name: str) -> str:
    prefix = name + "="
    line = next((row for row in output.splitlines() if row.startswith(prefix)), None)
    if line is None:
        raise RuntimeError(f"HW-20 simulation marker missing: {name}\n{output}")
    return line.split("=", 1)[1].strip()


def simulate_candidate(tmp: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    tb = tmp / "cosmic_hw20_cycle_tb.v"
    tb.write_text(cycle_testbench(), encoding="utf-8")
    image = tmp / "cosmic_hw20_cycle_tb.out"
    run(
        [
            require_tool("iverilog"),
            "-g2012",
            "-s",
            "cosmic_hw20_cycle_tb",
            "-o",
            str(image),
            *(str(path) for path in PROCESSOR_SOURCES),
            str(TOP_PATH),
            str(tb),
        ]
    )
    output = run([require_tool("vvp"), str(image)])
    cycles = int(marker_value(output, "COSMIC_HW20_COMPUTE_CYCLES"))
    both_busy = int(marker_value(output, "COSMIC_HW20_BOTH_BUSY_CYCLES"))
    queued = int(marker_value(output, "COSMIC_HW20_QUEUED_BEHIND_BUSY_CYCLES"))
    accepts = [
        int(value)
        for value in marker_value(output, "COSMIC_HW20_ENGINE_ACCEPTS").split(",")
    ]
    digest = marker_value(output, "COSMIC_HW20_LAST_DIGEST").lower()
    control_cycles = int(manifest["cycle_gates"]["single_sha_control_cycles"])
    speedup = control_cycles / cycles
    lower_bound = int(
        manifest["cycle_gates"]["two_engine_sha_round_lower_bound_cycles"]
    )
    if digest != EXPECTED_LAST_DIGEST:
        raise RuntimeError("HW-20 candidate digest mismatch")
    if cycles < lower_bound:
        raise RuntimeError("HW-20 cycles violate the two-engine work lower bound")
    if cycles >= control_cycles:
        raise RuntimeError("HW-20 did not improve the exact x1 control")
    if speedup > float(manifest["cycle_gates"]["maximum_honest_speedup"]):
        raise RuntimeError("HW-20 reports more than two-engine work conservation permits")
    if len(accepts) != 2 or sum(accepts) != 13 or min(accepts) == 0:
        raise RuntimeError(f"HW-20 physical engine dispatch mismatch: {accepts}")
    if both_busy <= 0 or queued <= 0:
        raise RuntimeError("HW-20 stretcher overlap was not observed")

    modeled: dict[str, Any] = {}
    cpu_ns = float(manifest["cpu_reference"]["mean_ns_per_operation"])
    for mhz in manifest["cpu_reference"]["clock_points_mhz"]:
        ns_per_operation = cycles * 1000.0 / float(mhz)
        modeled[str(mhz)] = {
            "clock_mhz": float(mhz),
            "ns_per_operation": ns_per_operation,
            "operations_per_second": 1.0e9 / ns_per_operation,
            "modeled_fpga_to_measured_cpu_latency_ratio": ns_per_operation / cpu_ns,
            "physical_measurement": False,
        }
    return {
        "oracle_match": True,
        "compute_cycles": cycles,
        "single_sha_control_cycles": control_cycles,
        "cycle_speedup": speedup,
        "last_digest": digest,
        "both_engines_busy_cycles": both_busy,
        "both_engines_busy_with_waiting_block_cycles": queued,
        "per_engine_blocks_accepted": accepts,
        "virtual_third_slot_compute_engines": 0,
        "modeled_points": modeled,
        "simulator_output": output.strip().splitlines(),
    }


def synthesize(tmp: Path, *, board: bool) -> tuple[dict[str, Any], Path]:
    top = "cosmic_hw20_ulx3s_top" if board else "cosmic_hw09_sparse_receipt_sha256x2"
    netlist = tmp / ("cosmic_hw20_board.json" if board else "cosmic_hw20_core.json")
    sources = [*PROCESSOR_SOURCES]
    if board:
        sources.extend((PLL_PATH, TOP_PATH))
    script = (
        "read_verilog -sv "
        + " ".join(str(path) for path in sources)
        + f"; synth_ecp5 -nodsp -top {top}; write_json {netlist}"
    )
    run_cmd([require_tool("yosys"), "-q", "-p", script], timeout=3600)
    counts = recursive_cell_counts(netlist, top)
    summary = summarize_ecp5_cells(counts)
    summary.update({"top": top, "mapping": "NODSP", "cell_types": counts})
    if summary["mult18x18d"] != 0:
        raise RuntimeError(f"HW-20 inferred DSP cells: {summary}")
    if summary["trellis_comb"] <= 0 or summary["trellis_ff"] <= 0:
        raise RuntimeError(f"HW-20 zero-cell synthesis: {summary}")
    if board and counts.get("EHXPLLL", 0) != 1:
        raise RuntimeError("HW-20 board synthesis did not preserve exactly one PLL")
    return summary, netlist


def classify(
    manifest: dict[str, Any],
    simulation: dict[str, Any],
    board_synthesis: dict[str, Any],
    route: dict[str, Any] | None,
) -> str:
    capacity = int(manifest["board"]["trellis_comb_capacity"])
    if int(board_synthesis["trellis_comb"]) > capacity:
        return "ECP5_CAPACITY_FAILURE"
    if route is not None and not (
        route["routed"]
        and route["packed"]
        and route["input_25mhz_timing_pass"]
        and route["processor_10mhz_timing_pass"]
    ):
        return "ECP5_ROUTE_OR_TIMING_NOT_SUPPORTED"
    parity_cycles = int(
        manifest["cpu_reference"]["cpu_mean_parity_max_cycles_at_20_25mhz"]
    )
    if simulation["compute_cycles"] <= parity_cycles:
        return "STRETCHER_CPU_PARITY_MODELED_PHYSICAL_NOT_RUN"
    return "STRETCHER_VALUE_SUPPORTED_CPU_PARITY_NOT_REACHED"


def execute(output_dir: Path, *, route_requested: bool) -> dict[str, Any]:
    manifest = load_manifest()
    initial_identity = git_identity()
    if not initial_identity["clean"]:
        raise RuntimeError(f"HW-20 source worktree must be clean: {initial_identity['status']}")
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cosmic-hw20-") as directory:
        tmp = Path(directory)
        hw19 = simulate_hw19(tmp, load_hw19_manifest())
        if hw19["compute_cycles"] != manifest["parent"]["single_sha_compute_cycles"]:
            raise RuntimeError("HW-20 exact x1 control did not reproduce")
        simulation = simulate_candidate(tmp, manifest)
        core_synthesis, _ = synthesize(tmp, board=False)
        board_synthesis, board_netlist = synthesize(tmp, board=True)
        capacity_ok = board_synthesis["trellis_comb"] <= int(
            manifest["board"]["trellis_comb_capacity"]
        )
        route = None
        if route_requested and capacity_ok:
            route = run_seed(
                manifest,
                output_dir,
                board_netlist,
                int(manifest["board"]["placement_seed"]),
            )

    final_identity = git_identity()
    if (
        not final_identity["clean"]
        or final_identity["head"] != initial_identity["head"]
        or final_identity["tree"] != initial_identity["tree"]
    ):
        raise RuntimeError(
            f"HW-20 source identity moved during execution: initial={initial_identity} final={final_identity}"
        )
    decision = classify(manifest, simulation, board_synthesis, route)
    cpu_parity = simulation["compute_cycles"] <= int(
        manifest["cpu_reference"]["cpu_mean_parity_max_cycles_at_20_25mhz"]
    )
    return {
        "experiment_id": manifest["experiment_id"],
        "protocol": manifest["protocol"],
        "completed_at": utc_now(),
        "source_identity": {"initial": initial_identity, "final": final_identity},
        "parent": manifest["parent"],
        "workload": manifest["workload"],
        "simulation": simulation,
        "synthesis": {"core_x2": core_synthesis, "board_x2": board_synthesis},
        "capacity": {
            "trellis_comb_used": board_synthesis["trellis_comb"],
            "trellis_comb_capacity": manifest["board"]["trellis_comb_capacity"],
            "fraction": board_synthesis["trellis_comb"]
            / manifest["board"]["trellis_comb_capacity"],
            "fits_synthesis_count": capacity_ok,
        },
        "route_requested": route_requested,
        "route": route,
        "cpu_reference": manifest["cpu_reference"],
        "cpu_mean_parity_modeled": cpu_parity,
        "physical_board_executed": False,
        "physical_execution_state": "NOT_RUN",
        "virtual_third_slot_is_compute_engine": False,
        "decision": decision,
        "passed": True,
        "competitive_claim_allowed": False,
        "claim_boundary": manifest["claim_boundary"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the HW-20 two-engine plus waiting-slot stretcher candidate."
    )
    parser.add_argument("--output-dir", type=Path, default=Path("build/cosmic-hw-20"))
    parser.add_argument("--route", action="store_true", help="also route and pack one ECP5-85F seed")
    args = parser.parse_args()
    output_path = args.output_dir / "cosmic_hw_20_result.json"
    try:
        result = execute(args.output_dir, route_requested=args.route)
        returncode = 0
    except (FileNotFoundError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        result = {
            "experiment_id": "COSMIC-HW-20/v0.1",
            "completed_at": utc_now(),
            "decision": "CONTROL_FAILURE",
            "passed": False,
            "competitive_claim_allowed": False,
            "physical_board_executed": False,
            "physical_execution_state": "NOT_RUN",
            "error": str(error),
        }
        returncode = 1
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    output_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
