from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks" / "cosmic_hw_19_manifest.json"
CPU_SOURCE = ROOT / "benchmarks" / "cosmic_hw_19_cpu.cpp"
EXPECTED_PARENT_HEAD = "eca0160cf87e988c9b2f7fe54dfa629fc4fea898"
EXPECTED_LAST_DIGEST = "c31bff9259318b3309bdb0fdd5282ce58366d6d8d1b9c636080eb6482a230ab2"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def load_manifest() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest["experiment_id"] != "COSMIC-HW-19/v0.1":
        raise RuntimeError("HW-19 experiment identity moved")
    if manifest["protocol"] != "COSMIC-HW-19-NO-PURCHASE/v0.1":
        raise RuntimeError("HW-19 protocol moved")
    if manifest["parent"]["source_head"] != EXPECTED_PARENT_HEAD:
        raise RuntimeError("HW-19 parent head moved")
    if manifest["workload"]["last_digest"] != EXPECTED_LAST_DIGEST:
        raise RuntimeError("HW-19 workload oracle moved")
    if manifest["parent"]["physical_hil_state"] != "NOT_RUN":
        raise RuntimeError("HW-19 physical state must start NOT_RUN")
    for relative, expected in manifest["inherited_source_blobs"].items():
        if git_blob_sha(ROOT / relative) != expected:
            raise RuntimeError(f"HW-19 inherited source moved: {relative}")
    return manifest


def run(command: list[str], *, cwd: Path = ROOT, timeout: int = 600) -> str:
    process = subprocess.run(
        command,
        cwd=cwd,
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


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"required tool not found: {name}")
    return path


def git_identity() -> dict[str, Any]:
    def git(*args: str) -> str:
        return run(["git", *args]).strip()

    status = git("status", "--porcelain=v1", "--untracked-files=all")
    return {
        "head": git("rev-parse", "HEAD"),
        "tree": git("rev-parse", "HEAD^{tree}"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "clean": not bool(status),
        "status": status.splitlines(),
    }


def cycle_testbench() -> str:
    return r"""`timescale 1ns/1ps
module cosmic_hw19_cycle_tb;
  reg clk = 1'b0;
  reg reset = 1'b1;
  wire uart_tx;
  wire [7:0] status_led;
  wire complete;
  wire [15:0] accepted_ticks;
  wire [31:0] receipt_count;
  wire [15:0] digest_count;
  wire [255:0] last_digest;
  wire [15:0] error_flags;
  integer cycles = 0;

  always #50 clk = ~clk;
  always @(posedge clk) if (!reset) cycles = cycles + 1;

  cosmic_hw16_selftest_logic dut (
    .clk(clk), .reset(reset), .uart_tx(uart_tx), .status_led(status_led),
    .self_test_complete(complete), .accepted_tick_count_debug(accepted_ticks),
    .receipt_count_debug(receipt_count), .digest_count_debug(digest_count),
    .last_digest_debug(last_digest), .error_flags_debug(error_flags)
  );

  initial begin
    repeat (8) @(posedge clk);
    @(negedge clk); reset = 1'b0;
    wait(dut.state == 4'd5);
    if (accepted_ticks != 16'd2) $fatal(1, "accepted tick mismatch");
    if (receipt_count != 32'd128) $fatal(1, "receipt count mismatch");
    if (digest_count != 16'd13) $fatal(1, "digest count mismatch");
    if (last_digest != 256'hc31bff9259318b3309bdb0fdd5282ce58366d6d8d1b9c636080eb6482a230ab2)
      $fatal(1, "last digest mismatch");
    if (error_flags != 16'd0) $fatal(1, "error flags set");
    $display("COSMIC_HW19_COMPUTE_CYCLES=%0d", cycles);
    $display("COSMIC_HW19_LAST_DIGEST=%064x", last_digest);
    $finish;
  end

  initial begin
    repeat (200000) @(posedge clk);
    $fatal(1, "HW-19 simulation watchdog expired");
  end
endmodule
"""


def simulate_hardware_model(tmp: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    tb = tmp / "cosmic_hw19_cycle_tb.v"
    tb.write_text(cycle_testbench(), encoding="utf-8")
    image = tmp / "cosmic_hw19_cycle_tb.out"
    sources = [
        ROOT / "rtl" / "cosmic_hw_06.v",
        ROOT / "rtl" / "cosmic_hw_07_receipt.v",
        ROOT / "rtl" / "cosmic_hw_08_sha256.v",
        ROOT / "rtl" / "cosmic_hw_16_ulx3s_top.v",
    ]
    run(
        [
            require_tool("iverilog"),
            "-g2012",
            "-s",
            "cosmic_hw19_cycle_tb",
            "-o",
            str(image),
            *(str(path) for path in sources),
            str(tb),
        ]
    )
    output = run([require_tool("vvp"), str(image)])
    cycles_line = next(
        (line for line in output.splitlines() if line.startswith("COSMIC_HW19_COMPUTE_CYCLES=")),
        None,
    )
    digest_line = next(
        (line for line in output.splitlines() if line.startswith("COSMIC_HW19_LAST_DIGEST=")),
        None,
    )
    if cycles_line is None or digest_line is None:
        raise RuntimeError(f"HW-19 simulation markers missing:\n{output}")
    cycles = int(cycles_line.split("=", 1)[1])
    digest = digest_line.split("=", 1)[1].lower()
    if cycles <= 0 or digest != EXPECTED_LAST_DIGEST:
        raise RuntimeError("HW-19 simulated hardware oracle mismatch")

    clocks = {
        "configured_10mhz": float(manifest["hardware_model"]["configured_clock_mhz"]),
        "routed_fmax_20_25mhz": float(
            manifest["hardware_model"]["canonical_seed_routed_fmax_mhz"]
        ),
    }
    modeled: dict[str, Any] = {}
    for label, mhz in clocks.items():
        ns_per_operation = cycles * 1000.0 / mhz
        modeled[label] = {
            "clock_mhz": mhz,
            "ns_per_operation": ns_per_operation,
            "operations_per_second": 1.0e9 / ns_per_operation,
            "physical_measurement": False,
        }
    return {
        "oracle_match": True,
        "compute_cycles": cycles,
        "last_digest": digest,
        "modeled_points": modeled,
        "physical_board_executed": False,
        "physical_execution_state": "NOT_RUN",
        "simulator_output": output.strip().splitlines(),
    }


def cpu_model() -> str:
    cpuinfo = Path("/proc/cpuinfo")
    if not cpuinfo.exists():
        return "unknown"
    for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.lower().startswith("model name"):
            return line.split(":", 1)[1].strip()
    return "unknown"


def measure_cpu(tmp: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    compiler = require_tool("g++")
    executable = tmp / "cosmic_hw_19_cpu"
    flags = list(manifest["cpu_baseline"]["compiler_flags"])
    command = [compiler, *flags, str(CPU_SOURCE), "-lcrypto", "-o", str(executable)]
    compiler_output = run(command)
    config = manifest["cpu_baseline"]
    raw = run(
        [
            str(executable),
            str(config["timed_iterations_per_sample"]),
            str(config["samples"]),
            str(config["warmup_iterations"]),
            str(config["single_operation_latency_samples"]),
        ],
        timeout=1200,
    )
    result = json.loads(raw)
    if result.get("oracle_match") is not True or result.get("last_digest") != EXPECTED_LAST_DIGEST:
        raise RuntimeError("HW-19 CPU oracle mismatch")
    result["threads"] = 1
    result["cpu_model"] = cpu_model()
    result["platform"] = platform.platform()
    result["python"] = sys.version
    result["compiler"] = run([compiler, "--version"]).splitlines()[0]
    result["compiler_command"] = command
    result["compiler_output"] = compiler_output.strip()
    try:
        result["affinity"] = sorted(os.sched_getaffinity(0))
    except AttributeError:
        result["affinity"] = None
    return result


def build_result() -> dict[str, Any]:
    manifest = load_manifest()
    initial_identity = git_identity()
    if not initial_identity["clean"]:
        raise RuntimeError(f"HW-19 source worktree must be clean: {initial_identity['status']}")
    with tempfile.TemporaryDirectory(prefix="cosmic-hw19-") as directory:
        tmp = Path(directory)
        hardware = simulate_hardware_model(tmp, manifest)
        cpu = measure_cpu(tmp, manifest)
    final_identity = git_identity()
    if (
        not final_identity["clean"]
        or final_identity["head"] != initial_identity["head"]
        or final_identity["tree"] != initial_identity["tree"]
    ):
        raise RuntimeError(
            f"HW-19 source identity moved during collection: "
            f"initial={initial_identity}, final={final_identity}"
        )

    comparisons: dict[str, Any] = {}
    cpu_ns = float(cpu["mean_ns_per_operation"])
    for label, point in hardware["modeled_points"].items():
        comparisons[label] = {
            "modeled_fpga_to_measured_cpu_latency_ratio": (
                float(point["ns_per_operation"]) / cpu_ns
            ),
            "basis": "modeled FPGA latency divided by host-specific measured CPU latency",
            "competitive_claim_allowed": False,
        }
    return {
        "experiment_id": manifest["experiment_id"],
        "protocol": manifest["protocol"],
        "completed_at": utc_now(),
        "parent": manifest["parent"],
        "source_identity": {
            "expected_parent_head": EXPECTED_PARENT_HEAD,
            "initial": initial_identity,
            "final": final_identity,
        },
        "workload": manifest["workload"],
        "cpu_measurement": cpu,
        "fpga_model": hardware,
        "comparisons": comparisons,
        "physical_board_executed": False,
        "physical_execution_state": "NOT_RUN",
        "decision": "CPU_BASELINE_MEASURED_FPGA_MODELED_PHYSICAL_NOT_RUN",
        "passed": True,
        "competitive_claim_allowed": False,
        "claim_boundary": manifest["claim_boundary"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure the HW-19 CPU baseline and derive the non-physical RTL cycle model."
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = build_result()
        returncode = 0
    except (FileNotFoundError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        result = {
            "experiment_id": "COSMIC-HW-19/v0.1",
            "completed_at": utc_now(),
            "decision": "CONTROL_FAILURE",
            "passed": False,
            "competitive_claim_allowed": False,
            "physical_board_executed": False,
            "error": str(error),
        }
        returncode = 1
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
