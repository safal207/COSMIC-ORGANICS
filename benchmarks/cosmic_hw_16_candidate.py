from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
import tempfile
import time

from benchmarks.cosmic_hw_13_candidate import (
    looks_like_capacity_failure,
    recursive_cell_counts,
    require_tool,
    run_cmd,
    summarize_ecp5_cells,
)
from benchmarks.cosmic_hw_14_candidate import git_blob_sha, parse_utilization
from tools.cosmic_hw_16_uart_verify import verify_frame

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks" / "cosmic_hw_16_manifest.json"
VECTORS_PATH = ROOT / "benchmarks" / "cosmic_hw_16_vectors.json"
TOP_PATH = ROOT / "rtl" / "cosmic_hw_16_ulx3s_top.v"
PLL_PATH = ROOT / "rtl" / "cosmic_hw_16_pll_10mhz.v"
CONSTRAINTS_PATH = ROOT / "constraints" / "cosmic_hw_16_ulx3s_v20.lpf"
TOP_MODULE = "cosmic_hw16_ulx3s_top"
CORE_MODULE = "cosmic_hw08_sparse_receipt_sha256"

PROCESSOR_SOURCES = [
    ROOT / "rtl" / "cosmic_hw_06.v",
    ROOT / "rtl" / "cosmic_hw_07_receipt.v",
    ROOT / "rtl" / "cosmic_hw_08_sha256.v",
]


def load_manifest() -> dict:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest["experiment_id"] != "COSMIC-HW-16/v0.1":
        raise RuntimeError("HW-16 manifest mismatch")
    if manifest["tracking_issue"] != 115:
        raise RuntimeError("HW-16 tracking issue moved")
    if manifest["parent"]["source_head"] != "0bbc07d85556a861c9595b869b1f8922e419f0a1":
        raise RuntimeError("HW-16 parent head moved")
    if manifest["parent"]["selected_profile"] != "PROOF_EDGE_SHA1_NODSP":
        raise RuntimeError("HW-16 selected profile moved")
    if manifest["placement_seeds"] != [1601, 1602, 1603, 1604, 1605]:
        raise RuntimeError("HW-16 placement seeds moved")
    board = manifest["board"]
    if board["density_flag"] != "--85k" or board["package"] != "CABGA381":
        raise RuntimeError("HW-16 board capacity boundary moved")
    return manifest


def preservation_gate(manifest: dict) -> dict:
    blob_checks: dict[str, dict] = {}
    for relative, expected in manifest["inherited_source_git_blobs"].items():
        path = ROOT / relative
        actual = git_blob_sha(path)
        blob_checks[relative] = {
            "expected": expected,
            "actual": actual,
            "match": actual == expected,
        }
    top_text = TOP_PATH.read_text(encoding="utf-8")
    pll_text = PLL_PATH.read_text(encoding="utf-8")
    constraints_text = CONSTRAINTS_PATH.read_text(encoding="utf-8")
    required_top_tokens = [
        "module cosmic_hw16_ulx3s_top",
        "module cosmic_hw16_selftest_logic",
        "cosmic_hw08_sparse_receipt_sha256 processor",
        "cosmic_hw16_pll_10mhz pll",
        "cosmic_hw16_uart_tx uart",
        "assign led = {logic_led[7:1], pll_locked};",
    ]
    missing_top = [token for token in required_top_tokens if token not in top_text]
    forbidden = [
        token
        for token in (
            "$readmemh",
            "$readmemb",
            "expected_digest",
            "expected_answer_rom",
            "c31bff9259318b3309bdb0fdd5282ce58366d6d8d1b9c636080eb6482a230ab2",
        )
        if token.lower() in top_text.lower()
    ]
    required_pll = [
        ".CLKI_DIV(5)",
        ".CLKOP_DIV(60)",
        ".CLKOP_CPHASE(30)",
        ".CLKOP_FPHASE(0)",
        ".CLKFB_DIV(2)",
        '.FEEDBK_PATH("CLKOP")',
    ]
    missing_pll = [token for token in required_pll if token not in pll_text]
    missing_constraints = [
        token
        for token in manifest["upstream_constraints"]["required_tokens"]
        if token not in constraints_text
    ]
    passed = (
        all(row["match"] for row in blob_checks.values())
        and not missing_top
        and not forbidden
        and not missing_pll
        and not missing_constraints
    )
    result = {
        "passed": passed,
        "inherited_blob_checks": blob_checks,
        "missing_top_tokens": missing_top,
        "forbidden_rtl_tokens": forbidden,
        "missing_pll_tokens": missing_pll,
        "missing_constraint_tokens": missing_constraints,
        "expected_answer_feedback": False,
    }
    if not passed:
        raise RuntimeError(f"HW-16 preservation gate failed: {result}")
    return result


def make_uart_tb() -> str:
    return r'''`timescale 1ns/1ps
module cosmic_hw16_tb;
  localparam integer BAUD_DIV = 87;
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
  reg [7:0] captured [0:59];
  integer byte_index;
  integer bit_index;
  integer print_index;

  always #50 clk = ~clk;

  cosmic_hw16_selftest_logic dut (
      .clk(clk),
      .reset(reset),
      .uart_tx(uart_tx),
      .status_led(status_led),
      .self_test_complete(complete),
      .accepted_tick_count_debug(accepted_ticks),
      .receipt_count_debug(receipt_count),
      .digest_count_debug(digest_count),
      .last_digest_debug(last_digest),
      .error_flags_debug(error_flags)
  );

  initial begin
    repeat (8) @(posedge clk);
    @(negedge clk); reset = 1'b0;
  end

  initial begin
    wait(reset == 1'b0);
    for (byte_index = 0; byte_index < 60; byte_index = byte_index + 1) begin
      @(negedge uart_tx);
      #(BAUD_DIV * 50);
      if (uart_tx !== 1'b0)
        $fatal(1, "UART start-bit sample failed byte=%0d", byte_index);
      for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1) begin
        #(BAUD_DIV * 100);
        captured[byte_index][bit_index] = uart_tx;
      end
      #(BAUD_DIV * 100);
      if (uart_tx !== 1'b1)
        $fatal(1, "UART stop-bit sample failed byte=%0d", byte_index);
    end
    wait(complete == 1'b1);
    if (accepted_ticks != 16'd2) $fatal(1, "accepted tick count mismatch");
    if (receipt_count != 32'd128) $fatal(1, "receipt count mismatch");
    if (digest_count != 16'd13) $fatal(1, "digest count mismatch");
    if (error_flags != 16'd0) $fatal(1, "self-test error flags=%h", error_flags);
    $write("COSMIC_HW16_UART_FRAME=");
    for (print_index = 0; print_index < 60; print_index = print_index + 1)
      $write("%02x", captured[print_index]);
    $write("\n");
    $display("COSMIC_HW16_SELFTEST PASS accepted=%0d receipts=%0d digests=%0d last_digest=%064x",
      accepted_ticks, receipt_count, digest_count, last_digest);
    $finish;
  end

  initial begin
    repeat (200000) @(posedge clk);
    $fatal(1, "HW-16 simulation watchdog expired");
  end
endmodule
'''


def simulate_uart(tmp: Path) -> dict:
    tb = tmp / "cosmic_hw16_tb.v"
    tb.write_text(make_uart_tb(), encoding="utf-8")
    output = tmp / "cosmic_hw16_tb.out"
    command = [
        require_tool("iverilog"),
        "-g2012",
        "-s",
        "cosmic_hw16_tb",
        "-o",
        str(output),
        *(str(path) for path in PROCESSOR_SOURCES),
        str(TOP_PATH),
        str(tb),
    ]
    run_cmd(command, timeout=600)
    text = run_cmd([require_tool("vvp"), str(output)], timeout=600).stdout
    marker = re.search(r"COSMIC_HW16_UART_FRAME=([0-9a-fA-F]{120})", text)
    if marker is None or "COSMIC_HW16_SELFTEST PASS" not in text:
        raise RuntimeError(f"HW-16 UART simulation marker missing\n{text}")
    frame = bytes.fromhex(marker.group(1))
    verification = verify_frame(frame)
    if verification["passed"] is not True:
        raise RuntimeError(f"HW-16 UART oracle mismatch: {verification}")
    return {
        "passed": True,
        "frame_hex": frame.hex(),
        "frame_sha256": hashlib.sha256(frame).hexdigest(),
        "verification": verification,
        "simulator_output_tail": "\n".join(text.splitlines()[-20:]),
    }


def synthesize(tmp: Path, *, board: bool) -> tuple[dict, Path]:
    top = TOP_MODULE if board else CORE_MODULE
    netlist = tmp / ("cosmic_hw16_board.json" if board else "cosmic_hw16_core.json")
    sources = [*PROCESSOR_SOURCES]
    if board:
        sources.extend((PLL_PATH, TOP_PATH))
    source_text = " ".join(str(path) for path in sources)
    if board:
        script = (
            f"read_verilog -sv {source_text}; "
            f"synth_ecp5 -nodsp -top {top}; write_json {netlist}"
        )
    else:
        script = (
            f"read_verilog -sv {source_text}; hierarchy -check -top {top}; flatten; "
            f"synth_ecp5 -nodsp -top {top}; write_json {netlist}"
        )
    run_cmd([require_tool("yosys"), "-q", "-p", script], timeout=3600)
    counts = recursive_cell_counts(netlist, top)
    summary = summarize_ecp5_cells(counts)
    summary["top"] = top
    summary["mapping"] = "NODSP"
    summary["cell_types"] = counts
    if summary["mult18x18d"] != 0:
        raise RuntimeError(f"HW-16 inferred DSP cells: {summary}")
    if summary["trellis_comb"] <= 0 or summary["trellis_ff"] <= 0:
        raise RuntimeError(f"HW-16 zero-cell synthesis: {summary}")
    if board and counts.get("EHXPLLL", 0) != 1:
        raise RuntimeError(f"HW-16 expected exactly one EHXPLLL: {counts.get('EHXPLLL', 0)}")
    return summary, netlist


def anti_pruning(core: dict, board: dict) -> dict:
    ratios = {
        "comb": board["trellis_comb"] / core["trellis_comb"],
        "ff": board["trellis_ff"] / core["trellis_ff"],
    }
    passed = ratios["comb"] >= 0.98 and ratios["ff"] >= 0.98
    result = {"passed": passed, "ratios": ratios, "minimum": 0.98}
    if not passed:
        raise RuntimeError(f"HW-16 anti-pruning failed: {result}")
    return result


def parse_clock_reports(log: str) -> list[dict]:
    reports: list[dict] = []
    pattern = re.compile(
        r"Max frequency for clock '([^']+)':\s*([0-9.]+) MHz\s*\((PASS|FAIL) at\s*([0-9.]+) MHz\)",
        flags=re.IGNORECASE,
    )
    for name, maximum, verdict, target in pattern.findall(log):
        reports.append(
            {
                "clock": name,
                "maximum_mhz": float(maximum),
                "target_mhz": float(target),
                "passed": verdict.upper() == "PASS",
            }
        )
    return reports


def clock_gate(reports: list[dict], target: float) -> bool:
    return any(abs(row["target_mhz"] - target) < 0.05 and row["passed"] for row in reports)


def run_seed(manifest: dict, output_dir: Path, netlist: Path, seed: int) -> dict:
    seed_dir = output_dir / f"seed_{seed}"
    seed_dir.mkdir(parents=True, exist_ok=True)
    config = seed_dir / "cosmic_hw16_ulx3s.config"
    bitstream = seed_dir / "cosmic_hw16_ulx3s.bit"
    route_log = seed_dir / "nextpnr.log"
    pack_log = seed_dir / "ecppack.log"
    board = manifest["board"]
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
        process = run_cmd(command, check=False, timeout=1200)
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
        and config.exists()
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
            pack.returncode == 0
            and bitstream.exists()
            and bitstream.stat().st_size > 0
        )

    reports = parse_clock_reports(log)
    input_clock_pass = clock_gate(reports, 25.0)
    processor_clock_pass = clock_gate(reports, 10.0)
    utilization = {
        "comb": parse_utilization(log, "TRELLIS_COMB"),
        "ff": parse_utilization(log, "TRELLIS_FF"),
        "mult": parse_utilization(log, "MULT18X18D"),
        "ebr": parse_utilization(log, "DP16KD"),
    }
    return {
        "seed": seed,
        "timed_out": timed_out,
        "returncode": returncode,
        "runtime_seconds": round(runtime, 3),
        "routed": routed,
        "packed": packed,
        "pack_returncode": pack_returncode,
        "input_25mhz_timing_pass": input_clock_pass,
        "processor_10mhz_timing_pass": processor_clock_pass,
        "clock_reports": reports,
        "capacity_signal": looks_like_capacity_failure(log),
        "utilization": utilization,
        "config_bytes": config.stat().st_size if config.exists() else 0,
        "bitstream_bytes": bitstream.stat().st_size if bitstream.exists() else 0,
        "bitstream_sha256": (
            hashlib.sha256(bitstream.read_bytes()).hexdigest() if packed else None
        ),
        "config": str(config) if config.exists() else None,
        "bitstream": str(bitstream) if bitstream.exists() else None,
        "route_log": str(route_log),
        "pack_log": str(pack_log) if pack_log.exists() else None,
        "route_log_tail": "\n".join(log.splitlines()[-60:]),
        "pack_log_tail": "\n".join(pack_text.splitlines()[-20:]),
    }


def maximum_fraction(board_summary: dict, seeds: list[dict], resource: str) -> float:
    capacity = 83640
    key = "trellis_comb" if resource == "comb" else "trellis_ff"
    values = [board_summary[key] / capacity]
    for seed in seeds:
        row = seed["utilization"].get(resource)
        if row and row.get("fraction") is not None:
            values.append(float(row["fraction"]))
    return max(values)


def interpret(manifest: dict, board_summary: dict, seeds: list[dict]) -> dict:
    gate = manifest["route_gate"]
    routes = sum(row["routed"] for row in seeds)
    packs = sum(row["packed"] for row in seeds)
    input_passes = sum(row["input_25mhz_timing_pass"] for row in seeds)
    processor_passes = sum(row["processor_10mhz_timing_pass"] for row in seeds)
    comb_fraction = maximum_fraction(board_summary, seeds, "comb")
    ff_fraction = maximum_fraction(board_summary, seeds, "ff")
    zero_dsp = board_summary["mult18x18d"] == int(gate["required_mult18x18d"])
    ready = (
        routes >= int(gate["minimum_routes"])
        and packs >= int(gate["minimum_nonempty_bitstreams"])
        and input_passes >= int(gate["minimum_25mhz_input_timing_passes"])
        and processor_passes >= int(gate["minimum_10mhz_processor_timing_passes"])
        and comb_fraction <= float(gate["maximum_comb_fraction"])
        and ff_fraction <= float(gate["maximum_ff_fraction"])
        and zero_dsp
    )
    decision = (
        "ULX3S_PROOF_EDGE_BITSTREAM_READY"
        if ready
        else "ULX3S_ROUTE_OR_TIMING_NOT_SUPPORTED"
    )
    successful = [row for row in seeds if row["packed"]]
    canonical = min(successful, key=lambda row: row["seed"]) if successful else None
    all_fmax = [
        row["maximum_mhz"]
        for seed in seeds
        for row in seed["clock_reports"]
        if abs(row["target_mhz"] - 10.0) < 0.05
    ]
    return {
        "decision": decision,
        "bitstream_ready": ready,
        "routes": routes,
        "packs": packs,
        "input_25mhz_timing_passes": input_passes,
        "processor_10mhz_timing_passes": processor_passes,
        "maximum_comb_fraction": comb_fraction,
        "maximum_ff_fraction": ff_fraction,
        "zero_dsp": zero_dsp,
        "processor_clock_fmax_mhz": {
            "values": all_fmax,
            "minimum": min(all_fmax) if all_fmax else None,
            "median": statistics.median(all_fmax) if all_fmax else None,
            "maximum": max(all_fmax) if all_fmax else None,
        },
        "canonical_seed": canonical["seed"] if canonical else None,
        "canonical_bitstream": canonical["bitstream"] if canonical else None,
        "canonical_bitstream_sha256": (
            canonical["bitstream_sha256"] if canonical else None
        ),
        "canonical_bitstream_bytes": (
            canonical["bitstream_bytes"] if canonical else 0
        ),
    }


def execute(output_dir: Path) -> dict:
    manifest = load_manifest()
    vectors = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    if vectors["experiment_id"] != "COSMIC-HW-16/v0.1":
        raise RuntimeError("HW-16 vector contract mismatch")
    expected_frame = bytes.fromhex(vectors["uart"]["frame_hex"])
    oracle_self_check = verify_frame(expected_frame)
    if oracle_self_check["passed"] is not True:
        raise RuntimeError("HW-16 oracle self-check failed")

    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cosmic-hw16-") as temporary:
        tmp = Path(temporary)
        preservation = preservation_gate(manifest)
        simulation = simulate_uart(tmp)
        core_summary, _ = synthesize(tmp, board=False)
        board_summary, board_netlist = synthesize(tmp, board=True)
        pruning = anti_pruning(core_summary, board_summary)
        seeds = [
            run_seed(manifest, output_dir, board_netlist, seed)
            for seed in manifest["placement_seeds"]
        ]

    physical = interpret(manifest, board_summary, seeds)
    result = {
        "benchmark_id": "COSMIC-HW-16-CANDIDATE",
        "protocol": "COSMIC-HW-16/v0.1",
        "source_head_boundary": "research/cosmic-hw-16-frozen-prereg@1803acfe25ae6a8c6b1867d4436ac219a3d4b231",
        "parent_hw15_source_head": manifest["parent"]["source_head"],
        "board": manifest["board"],
        "preservation": preservation,
        "oracle_self_check": oracle_self_check,
        "simulation": simulation,
        "synthesis": {"core": core_summary, "board": board_summary},
        "anti_pruning": pruning,
        "seeds": seeds,
        "physical": physical,
        "decision": physical["decision"],
        "physical_board_executed": False,
        "claim_boundary": manifest["claim_boundary"],
    }
    (output_dir / "cosmic_hw_16_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/cosmic-hw-16")
    args = parser.parse_args()
    result = execute(Path(args.output_dir))
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.json:
        print(rendered)
    else:
        physical = result["physical"]
        print(f"decision={result['decision']}")
        print(
            "route/pack/input25/proc10="
            f"{physical['routes']}/5 {physical['packs']}/5 "
            f"{physical['input_25mhz_timing_passes']}/5 "
            f"{physical['processor_10mhz_timing_passes']}/5"
        )
        print(f"canonical_bitstream_sha256={physical['canonical_bitstream_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
