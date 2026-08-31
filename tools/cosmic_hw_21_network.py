from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
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


MANIFEST_PATH = ROOT / "benchmarks" / "cosmic_hw_21_network_manifest.json"
RTL_PATH = ROOT / "rtl" / "cosmic_hw_21_network_pyramid.v"
EXPECTED_PARENT_HEAD = "70a3b2177737a37ce0a64f7a75310432ad286044"
EXPECTED_PARENT_TREE = "1bb030ce6cb0e2e47218b929d18d4af308c20b45"
EXPECTED_LAST_DIGEST = "c31bff9259318b3309bdb0fdd5282ce58366d6d8d1b9c636080eb6482a230ab2"
LAYERS = (2, 4, 8, 16)

SOURCES = [
    ROOT / "rtl" / "cosmic_hw_06.v",
    ROOT / "rtl" / "cosmic_hw_07_receipt.v",
    ROOT / "rtl" / "cosmic_hw_08_sha256.v",
    RTL_PATH,
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def load_manifest() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest["experiment_id"] != "COSMIC-HW-21/v0.1":
        raise RuntimeError("HW-21 experiment identity moved")
    if manifest["protocol"] != "COSMIC-HW-21-NETWORK-PYRAMID/v0.1":
        raise RuntimeError("HW-21 protocol moved")
    parent = manifest["parent"]
    if parent["source_head"] != EXPECTED_PARENT_HEAD:
        raise RuntimeError("HW-21 parent head moved")
    if parent["source_tree"] != EXPECTED_PARENT_TREE:
        raise RuntimeError("HW-21 parent tree moved")
    if parent["physical_hil_state"] != "NOT_RUN":
        raise RuntimeError("HW-21 physical state must start NOT_RUN")
    if tuple(manifest["network_pyramid"]["layers"]) != LAYERS:
        raise RuntimeError("HW-21 pyramid layers moved")
    if manifest["network_pyramid"]["superlinear_speedup_claim_allowed"] is not False:
        raise RuntimeError("HW-21 may not preregister superlinear speedup")
    if manifest["workload"]["last_digest"] != EXPECTED_LAST_DIGEST:
        raise RuntimeError("HW-21 digest oracle moved")
    for relative, expected in manifest["inherited_source_blobs"].items():
        actual = git_blob_sha(ROOT / relative)
        if actual != expected:
            raise RuntimeError(
                f"HW-21 inherited source moved: {relative} expected={expected} actual={actual}"
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
    expected = os.environ.get("COSMIC_HW21_EXPECTED_HEAD")
    if expected and identity["head"] != expected:
        raise RuntimeError(
            f"HW-21 checkout does not match workflow head: {identity['head']} != {expected}"
        )
    return identity


def make_testbench(engines: int) -> str:
    return f'''`timescale 1ns/1ps
module cosmic_hw21_network_tb;
  localparam integer ENGINES = {engines};
  reg clk = 1'b0;
  reg reset = 1'b1;
  reg [3:0] state = 4'd0;
  wire tick_valid = (state == 4'd0) || (state == 4'd1);
  wire tick_ready;
  wire tick_fire = tick_valid && tick_ready;
  wire flush = (state == 4'd3);
  wire [127:0] phase_bus;
  wire [63:0] active_mask, changed_mask, dirty_mask;
  wire digest_valid;
  wire [255:0] digest_data;
  wire [15:0] digest_sequence;
  wire [3:0] fill_count;
  wire waiting_valid;
  wire [15:0] busy_mask, digest_valid_mask, accept_mask;
  wire receipt_valid, receipt_ready;
  wire [39:0] receipt_data;
  wire [2:0] batch_occupancy;
  wire pending_observation;
  reg [15:0] accepted_ticks = 0;
  reg [31:0] receipt_count = 0;
  reg [15:0] digest_count = 0;
  reg [255:0] last_digest = 0;
  reg [15:0] last_sequence = 0;
  reg [15:0] error_flags = 0;
  integer cycles = 0;
  integer aggregate_busy_cycles = 0;
  integer maximum_busy_engines = 0;
  integer waiting_at_full_fanout_cycles = 0;
  integer receipt_stall_cycles = 0;
  integer accepts [0:15];
  integer busy_now;
  integer used_engines;
  integer accept_total;
  integer i;

  always #50 clk = ~clk;

  cosmic_hw21_network_pyramid #(.ENGINES(ENGINES)) dut (
    .clk(clk), .reset(reset), .tick_valid(tick_valid), .tick_ready(tick_ready),
    .stimulus_bus({{64{{8'h64}}}}), .flush(flush),
    .phase_bus(phase_bus), .active_mask(active_mask),
    .changed_mask(changed_mask), .dirty_mask(dirty_mask),
    .digest_valid(digest_valid), .digest_ready(1'b1),
    .digest_data(digest_data), .digest_sequence(digest_sequence),
    .fill_count_out(fill_count), .waiting_block_valid_out(waiting_valid),
    .engine_busy_mask(busy_mask), .engine_digest_valid_mask(digest_valid_mask),
    .engine_block_accept_mask(accept_mask),
    .receipt_valid_out(receipt_valid), .receipt_ready_out(receipt_ready),
    .receipt_data_out(receipt_data), .batch_occupancy_out(batch_occupancy),
    .pending_observation_out(pending_observation)
  );

  function integer pop16;
    input [15:0] value;
    integer p;
    begin
      pop16 = 0;
      for (p = 0; p < 16; p = p + 1)
        pop16 = pop16 + value[p];
    end
  endfunction

  always @(posedge clk) begin
    if (!reset) begin
      cycles = cycles + 1;
      busy_now = pop16(busy_mask);
      aggregate_busy_cycles = aggregate_busy_cycles + busy_now;
      if (busy_now > maximum_busy_engines)
        maximum_busy_engines = busy_now;
      if (busy_now == ENGINES && waiting_valid)
        waiting_at_full_fanout_cycles = waiting_at_full_fanout_cycles + 1;
      if (receipt_valid && !receipt_ready)
        receipt_stall_cycles = receipt_stall_cycles + 1;
      for (i = 0; i < 16; i = i + 1)
        if (accept_mask[i]) accepts[i] = accepts[i] + 1;

      if (tick_fire)
        accepted_ticks <= accepted_ticks + 16'd1;
      if (receipt_valid && receipt_ready)
        receipt_count <= receipt_count + 32'd1;
      if (digest_valid) begin
        if (digest_sequence != digest_count)
          error_flags[5] <= 1'b1;
        digest_count <= digest_count + 16'd1;
        last_digest <= digest_data;
        last_sequence <= digest_sequence;
      end

      case (state)
        4'd0: if (tick_fire) state <= 4'd1;
        4'd1: if (tick_fire) state <= 4'd2;
        4'd2: if (receipt_count == 128 && digest_count == 12 &&
                    fill_count == 8 && !waiting_valid &&
                    busy_mask == 0 && digest_valid_mask == 0)
                state <= 4'd3;
        4'd3: state <= 4'd4;
        4'd4: if (digest_count == 13 && fill_count == 0 && !waiting_valid &&
                    busy_mask == 0 && digest_valid_mask == 0) begin
                if (accepted_ticks != 2) error_flags[0] <= 1'b1;
                if (receipt_count != 128) error_flags[1] <= 1'b1;
                if (last_sequence != 12) error_flags[3] <= 1'b1;
                if (phase_bus != {{64{{2'b10}}}}) error_flags[4] <= 1'b1;
                state <= 4'd5;
              end
        default: state <= 4'd5;
      endcase
    end
  end

  initial begin
    for (i = 0; i < 16; i = i + 1) accepts[i] = 0;
    repeat (8) @(posedge clk);
    @(negedge clk); reset = 1'b0;
    wait(state == 4'd5);
    #1;
    used_engines = 0;
    accept_total = 0;
    for (i = 0; i < 16; i = i + 1) begin
      if (accepts[i] != 0) used_engines = used_engines + 1;
      accept_total = accept_total + accepts[i];
    end
    if (error_flags != 0) $fatal(1, "error flags=%h", error_flags);
    if (last_digest != 256'hc31bff9259318b3309bdb0fdd5282ce58366d6d8d1b9c636080eb6482a230ab2)
      $fatal(1, "last digest mismatch");
    if (aggregate_busy_cycles != 832)
      $fatal(1, "aggregate SHA work mismatch=%0d", aggregate_busy_cycles);
    if (accept_total != 13)
      $fatal(1, "accepted block mismatch=%0d", accept_total);
    $display("COSMIC_HW21_LAYER=%0d", ENGINES);
    $display("COSMIC_HW21_COMPUTE_CYCLES=%0d", cycles);
    $display("COSMIC_HW21_AGGREGATE_BUSY_CYCLES=%0d", aggregate_busy_cycles);
    $display("COSMIC_HW21_MAXIMUM_BUSY_ENGINES=%0d", maximum_busy_engines);
    $display("COSMIC_HW21_USED_ENGINES=%0d", used_engines);
    $display("COSMIC_HW21_WAITING_AT_FULL_FANOUT_CYCLES=%0d", waiting_at_full_fanout_cycles);
    $display("COSMIC_HW21_RECEIPT_STALL_CYCLES=%0d", receipt_stall_cycles);
    $display("COSMIC_HW21_ENGINE_ACCEPTS=%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",
      accepts[0],accepts[1],accepts[2],accepts[3],accepts[4],accepts[5],accepts[6],accepts[7],
      accepts[8],accepts[9],accepts[10],accepts[11],accepts[12],accepts[13],accepts[14],accepts[15]);
    $display("COSMIC_HW21_LAST_DIGEST=%064x", last_digest);
    $finish;
  end

  initial begin
    repeat (200000) @(posedge clk);
    $fatal(1, "HW-21 network simulation watchdog expired");
  end
endmodule
'''


def marker(output: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}=(.+)$", output, flags=re.MULTILINE)
    if match is None:
        raise RuntimeError(f"HW-21 marker missing: {name}\n{output}")
    return match.group(1).strip()


def simulate_layer(tmp: Path, engines: int, manifest: dict[str, Any]) -> dict[str, Any]:
    tb = tmp / f"cosmic_hw21_x{engines}_tb.v"
    tb.write_text(make_testbench(engines), encoding="utf-8")
    image = tmp / f"cosmic_hw21_x{engines}.out"
    run([
        require_tool("iverilog"), "-g2012", "-s", "cosmic_hw21_network_tb",
        "-o", str(image), *(str(path) for path in SOURCES), str(tb),
    ])
    output = run([require_tool("vvp"), str(image)])
    cycles = int(marker(output, "COSMIC_HW21_COMPUTE_CYCLES"))
    aggregate_work = int(marker(output, "COSMIC_HW21_AGGREGATE_BUSY_CYCLES"))
    accepts = [int(value) for value in marker(output, "COSMIC_HW21_ENGINE_ACCEPTS").split(",")]
    digest = marker(output, "COSMIC_HW21_LAST_DIGEST").lower()
    if digest != EXPECTED_LAST_DIGEST:
        raise RuntimeError(f"HW-21 x{engines} digest mismatch")
    if aggregate_work != manifest["workload"]["aggregate_sha_busy_cycles"]:
        raise RuntimeError(f"HW-21 x{engines} work conservation mismatch")
    if sum(accepts) != manifest["workload"]["sha256_digests"]:
        raise RuntimeError(f"HW-21 x{engines} dispatch count mismatch")
    x1_cycles = manifest["parent"]["x1_compute_cycles"]
    speedup = x1_cycles / cycles
    if speedup > engines:
        raise RuntimeError(f"HW-21 x{engines} impossible superlinear speedup")
    cpu_ns = manifest["cpu_reference"]["mean_ns_per_operation"]
    modeled = {}
    for mhz in manifest["cpu_reference"]["clock_points_mhz"]:
        latency_ns = cycles * 1000.0 / mhz
        modeled[str(mhz)] = {
            "clock_mhz": mhz,
            "ns_per_operation": latency_ns,
            "operations_per_second": 1.0e9 / latency_ns,
            "modeled_fpga_to_measured_cpu_latency_ratio": latency_ns / cpu_ns,
            "physical_measurement": False,
        }
    return {
        "engines": engines,
        "compute_cycles": cycles,
        "speedup_vs_x1": speedup,
        "parallel_efficiency_vs_x1": speedup / engines,
        "aggregate_sha_busy_cycles": aggregate_work,
        "maximum_busy_engines": int(marker(output, "COSMIC_HW21_MAXIMUM_BUSY_ENGINES")),
        "used_engines": int(marker(output, "COSMIC_HW21_USED_ENGINES")),
        "waiting_at_full_fanout_cycles": int(marker(output, "COSMIC_HW21_WAITING_AT_FULL_FANOUT_CYCLES")),
        "receipt_stall_cycles": int(marker(output, "COSMIC_HW21_RECEIPT_STALL_CYCLES")),
        "per_engine_blocks_accepted": accepts[:engines],
        "last_digest": digest,
        "oracle_match": True,
        "modeled_points": modeled,
        "simulator_output": output.strip().splitlines(),
    }


def synthesize_layer(tmp: Path, engines: int) -> dict[str, Any]:
    top = f"cosmic_hw21_network_pyramid_x{engines}"
    netlist = tmp / f"cosmic_hw21_x{engines}.json"
    script = (
        "read_verilog -sv " + " ".join(str(path) for path in SOURCES)
        + f"; synth_ecp5 -nodsp -top {top}; write_json {netlist}"
    )
    run_cmd([require_tool("yosys"), "-q", "-p", script], timeout=3600)
    counts = recursive_cell_counts(netlist, top)
    summary = summarize_ecp5_cells(counts)
    summary.update({"top": top, "mapping": "NODSP", "cell_types": counts})
    if summary["mult18x18d"] != 0:
        raise RuntimeError(f"HW-21 x{engines} inferred DSP cells")
    return summary


def execute(output_dir: Path) -> dict[str, Any]:
    manifest = load_manifest()
    initial = git_identity()
    if not initial["clean"]:
        raise RuntimeError(f"HW-21 source worktree must be clean: {initial['status']}")
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cosmic-hw21-network-") as directory:
        tmp = Path(directory)
        layers = [simulate_layer(tmp, engines, manifest) for engines in LAYERS]
        if layers[0]["compute_cycles"] != manifest["gates"]["x2_must_reproduce_cycles"]:
            raise RuntimeError("HW-21 x2 did not reproduce exact HW-20 cycles")
        cycles = [row["compute_cycles"] for row in layers]
        if any(right > left for left, right in zip(cycles, cycles[1:])):
            raise RuntimeError(f"HW-21 non-monotonic scaling: {cycles}")
        synthesis = {
            "x2": synthesize_layer(tmp, 2),
            "x4": synthesize_layer(tmp, 4),
        }

    final = git_identity()
    if not final["clean"] or final["head"] != initial["head"] or final["tree"] != initial["tree"]:
        raise RuntimeError(f"HW-21 source identity moved: initial={initial} final={final}")

    x2_comb = synthesis["x2"]["trellis_comb"]
    x4_comb = synthesis["x4"]["trellis_comb"]
    marginal_per_engine = (x4_comb - x2_comb) / 2.0
    estimates = {
        "x8": x4_comb + 4 * marginal_per_engine,
        "x16": x4_comb + 12 * marginal_per_engine,
    }
    capacity = manifest["gates"]["trellis_comb_capacity"]
    x4_fits = x4_comb <= capacity
    cpu_parity = any(
        row["compute_cycles"] <= manifest["cpu_reference"]["cpu_mean_parity_max_cycles_at_20_25mhz"]
        for row in layers
    )
    decision = (
        "NETWORK_PYRAMID_CPU_PARITY_MODELED_PHYSICAL_NOT_RUN"
        if cpu_parity
        else "NETWORK_PYRAMID_SPEEDUP_SUPPORTED_SINGLE_BOARD_CAPACITY_LIMIT"
    )
    marginal = []
    previous_cycles = manifest["parent"]["x1_compute_cycles"]
    previous_engines = 1
    for row in layers:
        marginal.append({
            "from_engines": previous_engines,
            "to_engines": row["engines"],
            "cycles_removed": previous_cycles - row["compute_cycles"],
            "fractional_latency_reduction": (previous_cycles - row["compute_cycles"]) / previous_cycles,
        })
        previous_cycles = row["compute_cycles"]
        previous_engines = row["engines"]

    result = {
        "experiment_id": manifest["experiment_id"],
        "protocol": manifest["protocol"],
        "completed_at": utc_now(),
        "source_identity": {"initial": initial, "final": final},
        "parent": manifest["parent"],
        "workload": manifest["workload"],
        "layers": layers,
        "marginal_scaling": marginal,
        "synthesis": synthesis,
        "capacity": {
            "trellis_comb_capacity": capacity,
            "x2_used": x2_comb,
            "x4_used": x4_comb,
            "x4_fits_single_ecp5_85f": x4_fits,
            "linear_marginal_trellis_comb_per_added_engine": marginal_per_engine,
            "x8_linear_estimate": estimates["x8"],
            "x16_linear_estimate": estimates["x16"],
            "x8_x16_are_synthesis_measurements": False,
        },
        "cpu_reference": manifest["cpu_reference"],
        "cpu_mean_parity_modeled": cpu_parity,
        "single_receipt_lane_saturation_observed": layers[-1]["parallel_efficiency_vs_x1"] < layers[0]["parallel_efficiency_vs_x1"],
        "superlinear_speedup_claim_allowed": False,
        "physical_board_executed": False,
        "physical_execution_state": "NOT_RUN",
        "decision": decision,
        "passed": True,
        "competitive_claim_allowed": False,
        "claim_boundary": manifest["claim_boundary"],
    }
    (output_dir / "cosmic_hw_21_network_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure the HW-21 1+1=N SHA network-pyramid frontier."
    )
    parser.add_argument("--output-dir", type=Path, default=Path("build/cosmic-hw-21-network"))
    args = parser.parse_args()
    output_path = args.output_dir / "cosmic_hw_21_network_result.json"
    try:
        result = execute(args.output_dir)
        returncode = 0
    except (FileNotFoundError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        result = {
            "experiment_id": "COSMIC-HW-21/v0.1",
            "completed_at": utc_now(),
            "decision": "CONTROL_FAILURE",
            "passed": False,
            "competitive_claim_allowed": False,
            "physical_board_executed": False,
            "physical_execution_state": "NOT_RUN",
            "error": str(error),
        }
        args.output_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
