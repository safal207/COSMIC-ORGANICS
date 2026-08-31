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

from benchmarks.cosmic_hw_13_candidate import require_tool
from tools.cosmic_hw_16_uart_verify import expected_digests


MANIFEST_PATH = ROOT / "benchmarks" / "cosmic_hw_22_causal_manifest.json"
VECTOR_PATH = ROOT / "benchmarks" / "cosmic_hw_16_vectors.json"
EXPECTED_PARENT_HEAD = "a4446fc93cc4ab4fdf4dc56021e76f1c8e85b30b"
EXPECTED_PARENT_TREE = "21e5a9470a6b4a532a75a754b71b56c31f7b2b23"
EXPECTED_VECTOR_BLOB = "8df1f55db8acb76e2bb621d44053e3966cbabb45"
EXPECTED_VECTOR_FILE_SHA256 = "da4d98738969c4d1d1c93e3fcfb33efbe9603d35042aada422668482fd25a5a8"
EXPECTED_VECTOR_FINGERPRINT = "ab85d716d0e384b3a7d5194656a63509786e17eba4954527727687413c1735a7"

CONTROL_POLICY = "CONTROL_DELAYED_FLUSH"
EAGER_POLICY = "EAGER_HELD_FLUSH"
POLICIES = (CONTROL_POLICY, EAGER_POLICY)
LAYERS = tuple(range(1, 9))

SOURCES = [
    ROOT / "rtl" / "cosmic_hw_06.v",
    ROOT / "rtl" / "cosmic_hw_07_receipt.v",
    ROOT / "rtl" / "cosmic_hw_08_sha256.v",
    ROOT / "rtl" / "cosmic_hw_21_network_pyramid.v",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def vector_fingerprint(digests: list[bytes]) -> str:
    framed = b"".join(sequence.to_bytes(2, "big") + digest for sequence, digest in enumerate(digests))
    return hashlib.sha256(framed).hexdigest()


def closed_form_cycles(engines: int, policy: str) -> int:
    if engines not in LAYERS:
        raise ValueError(f"HW-22 engine count outside preregistered range: {engines}")
    reuse_deficit = max(0, 65 - 10 * engines)
    if policy == CONTROL_POLICY:
        return 257 + (11 // engines) * reuse_deficit
    if policy == EAGER_POLICY:
        return 198 + (12 // engines) * reuse_deficit + int(engines <= 6)
    raise ValueError(f"unknown HW-22 policy: {policy}")


def model_timeline(engines: int, policy: str) -> dict[str, Any]:
    """Clock-exact max-plus recurrence for the frozen 128-receipt workload."""
    if engines not in LAYERS:
        raise ValueError(f"HW-22 engine count outside preregistered range: {engines}")
    if policy not in POLICIES:
        raise ValueError(f"unknown HW-22 policy: {policy}")

    engine_reusable = [0] * engines
    previous_retire = 0
    block_ready = 12
    blocks: list[dict[str, int]] = []

    for sequence in range(12):
        accept = max(block_ready + 1, min(engine_reusable))
        engine = next(
            index for index, reusable in enumerate(engine_reusable) if reusable <= accept
        )
        retire = max(accept + 65, previous_retire + 1)
        blocks.append(
            {
                "sequence": sequence,
                "block_ready_cycle": block_ready,
                "accept_cycle": accept,
                "retire_cycle": retire,
                "engine": engine,
            }
        )
        engine_reusable[engine] = retire
        previous_retire = retire
        if sequence < 11:
            block_ready = max(block_ready + 10, accept)

    last_receipt_cycle = blocks[-1]["block_ready_cycle"] + 8
    if policy == CONTROL_POLICY:
        first_flush_cycle = blocks[-1]["retire_cycle"] + 2
        partial_ready_cycle = first_flush_cycle
    else:
        first_flush_cycle = last_receipt_cycle + 1
        partial_ready_cycle = max(first_flush_cycle, blocks[-1]["accept_cycle"] + 1)

    partial_accept = max(partial_ready_cycle + 1, min(engine_reusable))
    partial_engine = next(
        index
        for index, reusable in enumerate(engine_reusable)
        if reusable <= partial_accept
    )
    partial_retire = max(partial_accept + 65, previous_retire + 1)
    blocks.append(
        {
            "sequence": 12,
            "block_ready_cycle": partial_ready_cycle,
            "accept_cycle": partial_accept,
            "retire_cycle": partial_retire,
            "engine": partial_engine,
        }
    )
    completion_cycle = partial_retire + 1
    if completion_cycle != closed_form_cycles(engines, policy):
        raise AssertionError(
            f"HW-22 recurrence/closed-form disagreement: E={engines} policy={policy} "
            f"recurrence={completion_cycle} closed={closed_form_cycles(engines, policy)}"
        )
    return {
        "engines": engines,
        "policy": policy,
        "blocks": blocks,
        "last_receipt_cycle": last_receipt_cycle,
        "first_flush_cycle": first_flush_cycle,
        "partial_ready_cycle": partial_ready_cycle,
        "partial_accept_cycle": partial_accept,
        "completion_cycle": completion_cycle,
    }


def load_manifest() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest["experiment_id"] != "COSMIC-HW-22/v0.1":
        raise RuntimeError("HW-22 experiment identity moved")
    if manifest["protocol"] != "COSMIC-HW-22-CAUSAL-FLUSH/v0.1":
        raise RuntimeError("HW-22 protocol moved")
    parent = manifest["parent"]
    if parent["source_head"] != EXPECTED_PARENT_HEAD:
        raise RuntimeError("HW-22 parent head moved")
    if parent["source_tree"] != EXPECTED_PARENT_TREE:
        raise RuntimeError("HW-22 parent tree moved")
    if parent["physical_execution_state"] != "NOT_RUN":
        raise RuntimeError("HW-22 parent physical state must remain NOT_RUN")
    if tuple(manifest["causal_experiment"]["engine_counts"]) != LAYERS:
        raise RuntimeError("HW-22 engine-count range moved")
    if tuple(manifest["causal_experiment"]["policies"]) != POLICIES:
        raise RuntimeError("HW-22 policy pair moved")
    if manifest["oracle"]["vector_blob_sha1"] != EXPECTED_VECTOR_BLOB:
        raise RuntimeError("HW-22 frozen oracle blob moved")
    if manifest["oracle"]["vector_file_sha256"] != EXPECTED_VECTOR_FILE_SHA256:
        raise RuntimeError("HW-22 frozen oracle file digest moved")
    if manifest["oracle"]["vector_fingerprint_sha256"] != EXPECTED_VECTOR_FINGERPRINT:
        raise RuntimeError("HW-22 oracle fingerprint moved")
    if manifest["claim_boundary"]["competitive_claim_allowed"] is not False:
        raise RuntimeError("HW-22 may not make a competitive claim")
    if manifest["claim_boundary"]["physical_execution_state"] != "NOT_RUN":
        raise RuntimeError("HW-22 physical execution must start NOT_RUN")

    expected = manifest["model"]["preregistered_compute_cycles"]
    for engines in LAYERS:
        for policy in POLICIES:
            actual = closed_form_cycles(engines, policy)
            if expected[policy][str(engines)] != actual:
                raise RuntimeError(
                    f"HW-22 preregistration moved: E={engines} policy={policy}"
                )
    for relative, expected_blob in manifest["inherited_source_blobs"].items():
        actual_blob = git_blob_sha(ROOT / relative)
        if actual_blob != expected_blob:
            raise RuntimeError(
                f"HW-22 inherited source moved: {relative} "
                f"expected={expected_blob} actual={actual_blob}"
            )
    return manifest


def load_oracle(manifest: dict[str, Any]) -> list[bytes]:
    vector = json.loads(VECTOR_PATH.read_text(encoding="utf-8"))
    frozen = [bytes.fromhex(value) for value in vector["commitment_digests"]]
    generated = expected_digests()
    if len(frozen) != 13 or vector["digest_count"] != 13:
        raise RuntimeError("HW-22 oracle must contain exactly 13 digests")
    if frozen != generated:
        raise RuntimeError("HW-22 independent generator disagrees with frozen digest vector")
    if git_blob_sha(VECTOR_PATH) != EXPECTED_VECTOR_BLOB:
        raise RuntimeError("HW-22 oracle git blob mismatch")
    if file_sha256(VECTOR_PATH) != EXPECTED_VECTOR_FILE_SHA256:
        raise RuntimeError("HW-22 oracle file SHA-256 mismatch")
    fingerprint = vector_fingerprint(frozen)
    if fingerprint != EXPECTED_VECTOR_FINGERPRINT:
        raise RuntimeError("HW-22 ordered digest-vector fingerprint mismatch")
    if manifest["oracle"]["expected_digest_count"] != len(frozen):
        raise RuntimeError("HW-22 manifest oracle count mismatch")
    return frozen


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


def require_expected_head() -> str:
    expected = os.environ.get("COSMIC_HW22_EXPECTED_HEAD", "")
    if re.fullmatch(r"[0-9a-f]{40}", expected) is None:
        raise RuntimeError(
            "HW-22 exact-head execution requires COSMIC_HW22_EXPECTED_HEAD as 40 lowercase hex characters"
        )
    return expected


def git_identity(expected_head: str) -> dict[str, Any]:
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
    if identity["head"] != expected_head:
        raise RuntimeError(
            f"HW-22 checkout does not match expected head: {identity['head']} != {expected_head}"
        )
    return identity


def verify_bounded_scope(manifest: dict[str, Any], head: str) -> dict[str, Any]:
    parent = manifest["parent"]["source_head"]
    run(["git", "merge-base", "--is-ancestor", parent, head])
    output = run(
        ["git", "diff", "--name-status", "--no-renames", f"{parent}..{head}"]
    ).strip()
    observed = []
    for line in output.splitlines():
        fields = line.split("\t")
        if len(fields) != 2:
            raise RuntimeError(f"HW-22 malformed candidate diff row: {line!r}")
        observed.append({"status": fields[0], "path": fields[1]})
    expected_paths = set(manifest["candidate_paths"])
    observed_paths = {row["path"] for row in observed}
    if observed_paths != expected_paths:
        raise RuntimeError(
            f"HW-22 candidate scope moved: expected={sorted(expected_paths)} "
            f"observed={sorted(observed_paths)}"
        )
    if any(row["status"] != "A" for row in observed):
        raise RuntimeError(f"HW-22 candidate paths must all be newly added: {observed}")
    return {
        "parent_is_ancestor": True,
        "parent_head": parent,
        "candidate_head": head,
        "expected_candidate_paths": sorted(expected_paths),
        "observed_name_status": observed,
        "exact_candidate_scope_match": True,
    }


def make_testbench(engines: int, policy: str, digests: list[bytes]) -> str:
    if engines not in LAYERS:
        raise ValueError(f"HW-22 engine count outside preregistered range: {engines}")
    if policy not in POLICIES:
        raise ValueError(f"unknown HW-22 policy: {policy}")
    if len(digests) != 13:
        raise ValueError("HW-22 testbench requires all 13 oracle digests")
    eager = 1 if policy == EAGER_POLICY else 0
    oracle_cases = "\n".join(
        f"          16'd{sequence}: if (digest_data !== 256'h{digest.hex()}) "
        f"$fatal(1, \"digest mismatch sequence={sequence}\");"
        for sequence, digest in enumerate(digests)
    )
    return f'''`timescale 1ns/1ps
module cosmic_hw22_causal_transition_tb;
  localparam integer ENGINES = {engines};
  localparam integer EAGER_HELD_FLUSH = {eager};
  reg clk = 1'b0;
  reg reset = 1'b1;
  reg [3:0] state = 4'd0;
  wire tick_valid = (state == 4'd0) || (state == 4'd1);
  wire tick_ready;
  wire tick_fire = tick_valid && tick_ready;
  wire [127:0] phase_bus;
  wire [63:0] active_mask, changed_mask, dirty_mask;
  wire digest_valid;
  wire digest_ready = 1'b1;
  wire digest_fire = digest_valid && digest_ready;
  wire [255:0] digest_data;
  wire [15:0] digest_sequence;
  wire [3:0] fill_count;
  wire waiting_valid;
  wire [15:0] busy_mask, digest_valid_mask, accept_mask;
  wire receipt_valid, receipt_ready;
  wire receipt_fire = receipt_valid && receipt_ready;
  wire [39:0] receipt_data;
  wire [2:0] batch_occupancy;
  wire pending_observation;
  reg [15:0] accepted_ticks = 0;
  reg [31:0] receipt_count = 0;
  reg [15:0] digest_count = 0;
  reg [15:0] error_flags = 0;
  wire producer_end_seen = receipt_count == 128 && fill_count == 8 &&
                           batch_occupancy == 0 && !pending_observation &&
                           !receipt_valid;
  wire flush = EAGER_HELD_FLUSH ?
               ((state == 4'd3) || ((state == 4'd2) && producer_end_seen)) :
               (state == 4'd3);
  integer cycles = 0;
  integer completion_cycle = -1;
  integer aggregate_busy_cycles = 0;
  integer maximum_busy_engines = 0;
  integer waiting_at_full_fanout_cycles = 0;
  integer receipt_stall_cycles = 0;
  integer last_receipt_cycle = -1;
  integer first_flush_cycle = -1;
  integer last_flush_cycle = -1;
  integer flush_sample_cycles = 0;
  integer flush_build_count = 0;
  integer partial_ready_cycle = -1;
  integer retired_at_first_flush = -1;
  integer waiting_at_first_flush = -1;
  integer producer_quiescent_at_first_flush = -1;
  integer matched_digest_count = 0;
  integer quiet_guard_cycles = 0;
  integer quiet_guard_violations = 0;
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
    .digest_valid(digest_valid), .digest_ready(digest_ready),
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

      for (i = 0; i < 16; i = i + 1) begin
        if (accept_mask[i]) begin
          accepts[i] = accepts[i] + 1;
          $display("COSMIC_HW22_ACCEPT_EVENT=%0d,%0d,%0d", dut.waiting_sequence, cycles, i);
        end
      end

      if (tick_fire)
        accepted_ticks <= accepted_ticks + 16'd1;
      if (receipt_fire) begin
        if (receipt_count == 127) begin
          last_receipt_cycle = cycles;
          $display("COSMIC_HW22_LAST_RECEIPT_EVENT=%0d", cycles);
        end
        receipt_count <= receipt_count + 32'd1;
      end

      if (flush) begin
        if (first_flush_cycle < 0) begin
          first_flush_cycle = cycles;
          retired_at_first_flush = digest_count;
          waiting_at_first_flush = waiting_valid;
          producer_quiescent_at_first_flush = producer_end_seen;
          $display("COSMIC_HW22_FIRST_FLUSH_EVENT=%0d,%0d,%0d,%0d", cycles,
                   digest_count, waiting_valid, producer_end_seen);
        end
        last_flush_cycle = cycles;
        flush_sample_cycles = flush_sample_cycles + 1;
      end
      if (flush && fill_count != 0 && !waiting_valid) begin
        flush_build_count = flush_build_count + 1;
        partial_ready_cycle = cycles;
        $display("COSMIC_HW22_PARTIAL_READY_EVENT=%0d", cycles);
      end

      if (digest_fire) begin
        if (digest_sequence !== digest_count)
          $fatal(1, "digest sequence mismatch expected=%0d actual=%0d", digest_count,
                 digest_sequence);
        case (digest_sequence)
{oracle_cases}
          default: $fatal(1, "unexpected digest sequence=%0d", digest_sequence);
        endcase
        matched_digest_count = matched_digest_count + 1;
        $display("COSMIC_HW22_DIGEST_EVENT=%0d,%0d,%064x", digest_sequence, cycles,
                 digest_data);
        digest_count <= digest_count + 16'd1;
      end

      case (state)
        4'd0: if (tick_fire) state <= 4'd1;
        4'd1: if (tick_fire) state <= 4'd2;
        4'd2: begin
          if (EAGER_HELD_FLUSH) begin
            if (producer_end_seen)
              state <= 4'd3;
          end else if (receipt_count == 128 && digest_count == 12 &&
                       fill_count == 8 && !waiting_valid &&
                       busy_mask == 0 && digest_valid_mask == 0) begin
            state <= 4'd3;
          end
        end
        4'd3: begin
          if (EAGER_HELD_FLUSH) begin
            if (accept_mask != 0 && dut.waiting_sequence == 12)
              state <= 4'd4;
          end else begin
            state <= 4'd4;
          end
        end
        4'd4: if (digest_count == 13 && fill_count == 0 && !waiting_valid &&
                    busy_mask == 0 && digest_valid_mask == 0) begin
                if (accepted_ticks != 2) error_flags[0] <= 1'b1;
                if (receipt_count != 128) error_flags[1] <= 1'b1;
                if (phase_bus != {{64{{2'b10}}}}) error_flags[2] <= 1'b1;
                completion_cycle = cycles;
                state <= 4'd5;
              end
        4'd5: begin
          quiet_guard_cycles = quiet_guard_cycles + 1;
          if (digest_fire || receipt_fire || accept_mask != 0) begin
            quiet_guard_violations = quiet_guard_violations + 1;
            $fatal(1, "event observed in post-completion quiet guard");
          end
          if (quiet_guard_cycles == 16)
            state <= 4'd6;
        end
        default: state <= 4'd6;
      endcase
    end
  end

  initial begin
    for (i = 0; i < 16; i = i + 1) accepts[i] = 0;
    repeat (8) @(posedge clk);
    @(negedge clk); reset = 1'b0;
    wait(state == 4'd6);
    #1;
    used_engines = 0;
    accept_total = 0;
    for (i = 0; i < 16; i = i + 1) begin
      if (accepts[i] != 0) used_engines = used_engines + 1;
      accept_total = accept_total + accepts[i];
    end
    if (error_flags != 0) $fatal(1, "error flags=%h", error_flags);
    if (matched_digest_count != 13)
      $fatal(1, "matched digest count=%0d", matched_digest_count);
    if (aggregate_busy_cycles != 832)
      $fatal(1, "aggregate SHA work mismatch=%0d", aggregate_busy_cycles);
    if (accept_total != 13)
      $fatal(1, "accepted block mismatch=%0d", accept_total);
    if (flush_build_count != 1)
      $fatal(1, "partial flush build count=%0d", flush_build_count);
    if (quiet_guard_cycles != 16 || quiet_guard_violations != 0)
      $fatal(1, "quiet guard failure cycles=%0d violations=%0d",
             quiet_guard_cycles, quiet_guard_violations);
    $display("COSMIC_HW22_LAYER=%0d", ENGINES);
    $display("COSMIC_HW22_POLICY={policy}");
    $display("COSMIC_HW22_COMPUTE_CYCLES=%0d", completion_cycle);
    $display("COSMIC_HW22_AGGREGATE_BUSY_CYCLES=%0d", aggregate_busy_cycles);
    $display("COSMIC_HW22_MAXIMUM_BUSY_ENGINES=%0d", maximum_busy_engines);
    $display("COSMIC_HW22_USED_ENGINES=%0d", used_engines);
    $display("COSMIC_HW22_WAITING_AT_FULL_FANOUT_CYCLES=%0d",
             waiting_at_full_fanout_cycles);
    $display("COSMIC_HW22_RECEIPT_STALL_CYCLES=%0d", receipt_stall_cycles);
    $display("COSMIC_HW22_RECEIPT_COUNT=%0d", receipt_count);
    $display("COSMIC_HW22_DIGEST_COUNT=%0d", digest_count);
    $display("COSMIC_HW22_MATCHED_DIGEST_COUNT=%0d", matched_digest_count);
    $display("COSMIC_HW22_LAST_RECEIPT_CYCLE=%0d", last_receipt_cycle);
    $display("COSMIC_HW22_FIRST_FLUSH_CYCLE=%0d", first_flush_cycle);
    $display("COSMIC_HW22_LAST_FLUSH_CYCLE=%0d", last_flush_cycle);
    $display("COSMIC_HW22_FLUSH_SAMPLE_CYCLES=%0d", flush_sample_cycles);
    $display("COSMIC_HW22_FLUSH_BUILD_COUNT=%0d", flush_build_count);
    $display("COSMIC_HW22_PARTIAL_READY_CYCLE=%0d", partial_ready_cycle);
    $display("COSMIC_HW22_RETIRED_AT_FIRST_FLUSH=%0d", retired_at_first_flush);
    $display("COSMIC_HW22_WAITING_AT_FIRST_FLUSH=%0d", waiting_at_first_flush);
    $display("COSMIC_HW22_PRODUCER_QUIESCENT_AT_FIRST_FLUSH=%0d",
             producer_quiescent_at_first_flush);
    $display("COSMIC_HW22_QUIET_GUARD_CYCLES=%0d", quiet_guard_cycles);
    $display("COSMIC_HW22_QUIET_GUARD_VIOLATIONS=%0d", quiet_guard_violations);
    $display("COSMIC_HW22_ENGINE_ACCEPTS=%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",
      accepts[0],accepts[1],accepts[2],accepts[3],accepts[4],accepts[5],accepts[6],accepts[7],
      accepts[8],accepts[9],accepts[10],accepts[11],accepts[12],accepts[13],accepts[14],accepts[15]);
    $display("COSMIC_HW22_ALL_DIGEST_ORACLE_MATCH=1");
    $finish;
  end

  initial begin
    repeat (200000) @(posedge clk);
    $fatal(1, "HW-22 causal-transition simulation watchdog expired");
  end
endmodule
'''


def marker(output: str, name: str) -> str:
    values = re.findall(rf"^{re.escape(name)}=(.+)$", output, flags=re.MULTILINE)
    if len(values) != 1:
        raise RuntimeError(
            f"HW-22 marker must occur exactly once: {name} count={len(values)}\n{output}"
        )
    return values[0].strip()


def event_rows(output: str, name: str, fields: int) -> list[list[str]]:
    values = re.findall(rf"^{re.escape(name)}=(.+)$", output, flags=re.MULTILINE)
    rows = [value.strip().split(",") for value in values]
    if any(len(row) != fields for row in rows):
        raise RuntimeError(f"HW-22 malformed event marker: {name}")
    return rows


def simulate_policy(
    tmp: Path,
    log_dir: Path,
    engines: int,
    policy: str,
    manifest: dict[str, Any],
    digests: list[bytes],
) -> dict[str, Any]:
    slug = "late" if policy == CONTROL_POLICY else "eager"
    tb = tmp / f"cosmic_hw22_x{engines}_{slug}_tb.v"
    tb.write_text(make_testbench(engines, policy, digests), encoding="utf-8")
    image = tmp / f"cosmic_hw22_x{engines}_{slug}.out"
    run(
        [
            require_tool("iverilog"),
            "-g2012",
            "-s",
            "cosmic_hw22_causal_transition_tb",
            "-o",
            str(image),
            *(str(path) for path in SOURCES),
            str(tb),
        ]
    )
    output = run([require_tool("vvp"), str(image)])
    log_path = log_dir / f"x{engines}-{slug}.log"
    log_path.write_text(output, encoding="utf-8")

    accept_events = [
        {"sequence": int(row[0]), "cycle": int(row[1]), "engine": int(row[2])}
        for row in event_rows(output, "COSMIC_HW22_ACCEPT_EVENT", 3)
    ]
    digest_events = [
        {"sequence": int(row[0]), "cycle": int(row[1]), "digest": row[2].lower()}
        for row in event_rows(output, "COSMIC_HW22_DIGEST_EVENT", 3)
    ]
    timeline = model_timeline(engines, policy)
    expected_cycles = manifest["model"]["preregistered_compute_cycles"][policy][str(engines)]
    cycles = int(marker(output, "COSMIC_HW22_COMPUTE_CYCLES"))
    aggregate_work = int(marker(output, "COSMIC_HW22_AGGREGATE_BUSY_CYCLES"))
    accepts = [int(value) for value in marker(output, "COSMIC_HW22_ENGINE_ACCEPTS").split(",")]

    if cycles != expected_cycles or cycles != timeline["completion_cycle"]:
        raise RuntimeError(
            f"HW-22 prediction error E={engines} policy={policy}: "
            f"observed={cycles} expected={expected_cycles}"
        )
    if [event["sequence"] for event in accept_events] != list(range(13)):
        raise RuntimeError(f"HW-22 accept sequence mismatch E={engines} policy={policy}")
    if [event["sequence"] for event in digest_events] != list(range(13)):
        raise RuntimeError(f"HW-22 retirement sequence mismatch E={engines} policy={policy}")
    if [event["digest"] for event in digest_events] != [digest.hex() for digest in digests]:
        raise RuntimeError(f"HW-22 full digest oracle mismatch E={engines} policy={policy}")
    if [event["cycle"] for event in accept_events] != [
        block["accept_cycle"] for block in timeline["blocks"]
    ]:
        raise RuntimeError(f"HW-22 accept timeline mismatch E={engines} policy={policy}")
    if [event["cycle"] for event in digest_events] != [
        block["retire_cycle"] for block in timeline["blocks"]
    ]:
        raise RuntimeError(f"HW-22 retire timeline mismatch E={engines} policy={policy}")
    if aggregate_work != manifest["workload"]["aggregate_sha_busy_cycles"]:
        raise RuntimeError(f"HW-22 work-conservation mismatch E={engines} policy={policy}")
    if sum(accepts) != 13 or len(accept_events) != 13 or len(digest_events) != 13:
        raise RuntimeError(f"HW-22 event cardinality mismatch E={engines} policy={policy}")

    first_flush = int(marker(output, "COSMIC_HW22_FIRST_FLUSH_CYCLE"))
    last_receipt = int(marker(output, "COSMIC_HW22_LAST_RECEIPT_CYCLE"))
    partial_ready = int(marker(output, "COSMIC_HW22_PARTIAL_READY_CYCLE"))
    if first_flush != timeline["first_flush_cycle"]:
        raise RuntimeError(f"HW-22 first-flush timeline mismatch E={engines} policy={policy}")
    if last_receipt != timeline["last_receipt_cycle"]:
        raise RuntimeError(f"HW-22 last-receipt timeline mismatch E={engines} policy={policy}")
    if partial_ready != timeline["partial_ready_cycle"]:
        raise RuntimeError(f"HW-22 partial-ready timeline mismatch E={engines} policy={policy}")

    retired_at_first_flush = int(marker(output, "COSMIC_HW22_RETIRED_AT_FIRST_FLUSH"))
    producer_quiescent = int(
        marker(output, "COSMIC_HW22_PRODUCER_QUIESCENT_AT_FIRST_FLUSH")
    )
    waiting_at_first_flush = int(marker(output, "COSMIC_HW22_WAITING_AT_FIRST_FLUSH"))
    if producer_quiescent != 1:
        raise RuntimeError(f"HW-22 flush before source quiescence E={engines} policy={policy}")
    if policy == EAGER_POLICY and retired_at_first_flush >= 12:
        raise RuntimeError(f"HW-22 eager intervention occurred after drain E={engines}")
    if policy == EAGER_POLICY and engines in (3, 5) and waiting_at_first_flush != 1:
        raise RuntimeError(f"HW-22 lost-pulse collision not exercised E={engines}")

    return {
        "engines": engines,
        "policy": policy,
        "compute_cycles": cycles,
        "predicted_compute_cycles": expected_cycles,
        "prediction_error_cycles": cycles - expected_cycles,
        "receipt_count": int(marker(output, "COSMIC_HW22_RECEIPT_COUNT")),
        "digest_count": int(marker(output, "COSMIC_HW22_DIGEST_COUNT")),
        "matched_digest_count": int(marker(output, "COSMIC_HW22_MATCHED_DIGEST_COUNT")),
        "first_mismatch_sequence": None,
        "all_digest_oracle_match": marker(output, "COSMIC_HW22_ALL_DIGEST_ORACLE_MATCH") == "1",
        "aggregate_sha_busy_cycles": aggregate_work,
        "accept_count": sum(accepts),
        "per_engine_blocks_accepted": accepts[:engines],
        "maximum_busy_engines": int(marker(output, "COSMIC_HW22_MAXIMUM_BUSY_ENGINES")),
        "used_engines": int(marker(output, "COSMIC_HW22_USED_ENGINES")),
        "waiting_at_full_fanout_cycles": int(
            marker(output, "COSMIC_HW22_WAITING_AT_FULL_FANOUT_CYCLES")
        ),
        "receipt_stall_cycles": int(marker(output, "COSMIC_HW22_RECEIPT_STALL_CYCLES")),
        "accept_sequence_vector": [event["sequence"] for event in accept_events],
        "digest_sequence_vector": [event["sequence"] for event in digest_events],
        "event_trace": {
            "accepts": accept_events,
            "digests": digest_events,
            "last_receipt_cycle": last_receipt,
            "first_flush_cycle": first_flush,
            "last_flush_cycle": int(marker(output, "COSMIC_HW22_LAST_FLUSH_CYCLE")),
            "partial_ready_cycle": partial_ready,
            "partial_accept_cycle": accept_events[-1]["cycle"],
        },
        "flush": {
            "sample_cycles": int(marker(output, "COSMIC_HW22_FLUSH_SAMPLE_CYCLES")),
            "build_count": int(marker(output, "COSMIC_HW22_FLUSH_BUILD_COUNT")),
            "retired_digests_at_first_sample": retired_at_first_flush,
            "waiting_valid_at_first_sample": bool(waiting_at_first_flush),
            "producer_quiescent_at_first_sample": bool(producer_quiescent),
        },
        "quiet_guard": {
            "cycles": int(marker(output, "COSMIC_HW22_QUIET_GUARD_CYCLES")),
            "violations": int(marker(output, "COSMIC_HW22_QUIET_GUARD_VIOLATIONS")),
        },
        "raw_log": str(log_path.relative_to(log_dir.parent)),
    }


def workflow_identity() -> dict[str, Any]:
    return {
        "execution_context": "GITHUB_ACTIONS"
        if os.environ.get("GITHUB_ACTIONS") == "true"
        else "LOCAL",
        "repository": os.environ.get("GITHUB_REPOSITORY"),
        "event_name": os.environ.get("GITHUB_EVENT_NAME"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF"),
        "workflow_sha": os.environ.get("GITHUB_WORKFLOW_SHA"),
    }


def workflow_identity_is_bound(identity: dict[str, Any]) -> bool:
    if identity["execution_context"] == "LOCAL":
        return True
    return all(
        identity[key]
        for key in (
            "repository",
            "event_name",
            "run_id",
            "run_attempt",
            "workflow_ref",
            "workflow_sha",
        )
    )


def write_evidence_manifest(
    output_dir: Path,
    evidence_paths: list[Path],
    *,
    completed_at: str,
    parent: dict[str, Any],
    expected_head: str,
    initial_identity: dict[str, Any],
    final_identity: dict[str, Any],
    scope_identity: dict[str, Any],
    workflow: dict[str, Any],
) -> None:
    relative_paths = [path.relative_to(output_dir) for path in evidence_paths]
    names = [path.as_posix() for path in relative_paths]
    if len(names) != len(set(names)):
        raise RuntimeError("HW-22 duplicate evidence path")
    if any(path.is_absolute() or ".." in path.parts for path in relative_paths):
        raise RuntimeError("HW-22 unsafe evidence path")
    files = []
    for path, relative in sorted(zip(evidence_paths, relative_paths), key=lambda pair: pair[1].as_posix()):
        if not path.is_file():
            raise RuntimeError(f"HW-22 evidence file missing: {path}")
        files.append(
            {
                "path": relative.as_posix(),
                "role": "machine_result" if path.name.endswith("result.json") else "raw_simulator_log",
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    manifest = {
        "experiment_id": "COSMIC-HW-22/v0.1",
        "completed_at": completed_at,
        "repository": parent["repository"],
        "parent": {
            "head": parent["source_head"],
            "tree": parent["source_tree"],
            "pull_request": parent["pull_request"],
            "workflow_run_id": parent["workflow_run_id"],
            "artifact_id": parent["artifact_id"],
            "artifact_sha256": parent["artifact_sha256"],
        },
        "source_identity": {
            "expected_head": expected_head,
            "initial": initial_identity,
            "final_after_result_write": final_identity,
        },
        "candidate_scope": scope_identity,
        "workflow_identity": workflow,
        "self_hash_excluded": True,
        "files": files,
    }
    (output_dir / "evidence_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def execute(output_dir: Path) -> dict[str, Any]:
    expected_head = require_expected_head()
    manifest = load_manifest()
    digests = load_oracle(manifest)
    initial = git_identity(expected_head)
    if not initial["clean"]:
        raise RuntimeError(f"HW-22 source worktree must be clean: {initial['status']}")
    scope = verify_bounded_scope(manifest, initial["head"])
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RuntimeError(f"HW-22 output directory must be empty: {output_dir}")
    log_dir = output_dir / "runs"
    log_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="cosmic-hw22-causal-") as directory:
        tmp = Path(directory)
        runs = [
            simulate_policy(tmp, log_dir, engines, policy, manifest, digests)
            for engines in LAYERS
            for policy in POLICIES
        ]

    comparisons = []
    for engines in LAYERS:
        control = next(
            row for row in runs if row["engines"] == engines and row["policy"] == CONTROL_POLICY
        )
        eager = next(
            row for row in runs if row["engines"] == engines and row["policy"] == EAGER_POLICY
        )
        cycles_removed = control["compute_cycles"] - eager["compute_cycles"]
        if cycles_removed < 0:
            raise RuntimeError(f"HW-22 eager policy regressed E={engines}")
        comparisons.append(
            {
                "engines": engines,
                "only_changed_variable": "end-of-stream flush policy",
                "control_compute_cycles": control["compute_cycles"],
                "eager_compute_cycles": eager["compute_cycles"],
                "cycles_removed": cycles_removed,
                "latency_reduction_fraction": cycles_removed / control["compute_cycles"],
                "speed_ratio_control_over_eager": control["compute_cycles"] / eager["compute_cycles"],
                "same_full_digest_oracle": control["all_digest_oracle_match"]
                and eager["all_digest_oracle_match"],
                "same_aggregate_work": control["aggregate_sha_busy_cycles"]
                == eager["aggregate_sha_busy_cycles"]
                == 832,
            }
        )

    best = min(
        (row for row in runs if row["policy"] == EAGER_POLICY),
        key=lambda row: (row["compute_cycles"], row["engines"]),
    )
    clock_mhz = 20.25
    modeled_latency_ns = best["compute_cycles"] * 1000.0 / clock_mhz
    cpu_mean_ns = manifest["cpu_context"]["mean_ns_per_operation"]
    workflow = workflow_identity()
    toolchain = {
        "python": sys.version.split()[0],
        "iverilog": run([require_tool("iverilog"), "-V"]).splitlines()[0],
        "vvp": run([require_tool("vvp"), "-V"]).splitlines()[0],
    }
    final = git_identity(expected_head)
    source_stable = (
        final["clean"]
        and final["head"] == initial["head"] == expected_head
        and final["tree"] == initial["tree"]
    )
    eager_runs = [row for row in runs if row["policy"] == EAGER_POLICY]
    checks = {
        "external_expected_head_bound": initial["head"] == expected_head,
        "source_identity_stable": source_stable,
        "parent_identity_frozen": manifest["parent"]["source_head"] == EXPECTED_PARENT_HEAD
        and manifest["parent"]["source_tree"] == EXPECTED_PARENT_TREE,
        "parent_is_ancestor": scope["parent_is_ancestor"],
        "candidate_scope_exact": scope["exact_candidate_scope_match"],
        "workflow_identity_bound": workflow_identity_is_bound(workflow),
        "oracle_generator_matches_frozen_vector": len(digests) == 13
        and vector_fingerprint(digests) == EXPECTED_VECTOR_FINGERPRINT,
        "sixteen_policy_layer_runs_present": len(runs) == 16
        and {(row["engines"], row["policy"]) for row in runs}
        == {(engines, policy) for engines in LAYERS for policy in POLICIES},
        "all_13_digests_match_every_run": all(
            row["digest_count"] == 13
            and row["matched_digest_count"] == 13
            and row["all_digest_oracle_match"]
            for row in runs
        ),
        "accept_and_retire_sequences_exact": all(
            row["accept_count"] == 13
            and row["accept_sequence_vector"] == list(range(13))
            and row["digest_sequence_vector"] == list(range(13))
            for row in runs
        ),
        "max_plus_predictions_exact": all(
            row["prediction_error_cycles"] == 0
            and row["compute_cycles"] == row["predicted_compute_cycles"]
            for row in runs
        ),
        "receipt_cardinality_exact": all(row["receipt_count"] == 128 for row in runs),
        "work_conservation_832_every_run": all(
            row["aggregate_sha_busy_cycles"] == 832 for row in runs
        ),
        "producer_quiescent_before_flush": all(
            row["flush"]["producer_quiescent_at_first_sample"] for row in runs
        ),
        "eager_flush_precedes_full_digest_drain": all(
            row["flush"]["retired_digests_at_first_sample"] < 12 for row in eager_runs
        ),
        "held_flush_survives_waiting_block_collision": all(
            row["flush"]["waiting_valid_at_first_sample"]
            for row in eager_runs
            if row["engines"] in (3, 5)
        ),
        "single_partial_block_built_every_run": all(
            row["flush"]["build_count"] == 1 for row in runs
        ),
        "post_completion_quiet_guard": all(
            row["quiet_guard"] == {"cycles": 16, "violations": 0} for row in runs
        ),
        "only_flush_policy_changes_within_each_pair": len(comparisons) == 8
        and all(
            row["only_changed_variable"] == "end-of-stream flush policy"
            and row["same_full_digest_oracle"]
            and row["same_aggregate_work"]
            for row in comparisons
        ),
        "physical_claim_boundary_preserved": manifest["claim_boundary"][
            "competitive_claim_allowed"
        ]
        is False
        and manifest["claim_boundary"]["physical_execution_state"] == "NOT_RUN",
    }
    required_checks = {
        name: "PASS" if observed else "FAIL" for name, observed in checks.items()
    }
    passed = bool(required_checks) and all(value == "PASS" for value in required_checks.values())
    completed_at = utc_now()

    result = {
        "experiment_id": manifest["experiment_id"],
        "protocol": manifest["protocol"],
        "completed_at": completed_at,
        "source_identity": {
            "expected_head": expected_head,
            "initial": initial,
            "final": final,
        },
        "candidate_scope": scope,
        "workflow_identity": workflow,
        "parent": manifest["parent"],
        "toolchain": toolchain,
        "oracle": {
            **manifest["oracle"],
            "expected_digests": [digest.hex() for digest in digests],
            "generator_matches_frozen_vector": True,
        },
        "model": manifest["model"],
        "runs": runs,
        "comparisons": comparisons,
        "best_simulated_point": {
            "engines": best["engines"],
            "compute_cycles": best["compute_cycles"],
            "modeled_clock_mhz": clock_mhz,
            "modeled_latency_ns": modeled_latency_ns,
            "modeled_operations_per_second": 1.0e9 / modeled_latency_ns,
            "measured_cpu_mean_ns": cpu_mean_ns,
            "modeled_fpga_to_measured_cpu_latency_ratio": modeled_latency_ns / cpu_mean_ns,
            "physical_measurement": False,
        },
        "required_checks": required_checks,
        "execution_states": {
            "rtl_simulation": "PASS",
            "synthesis": "NOT_RUN",
            "place_and_route": "NOT_RUN",
            "physical_board": "NOT_RUN",
            "power": "NOT_RUN",
        },
        "decision": "EARLY_HELD_FLUSH_CAUSAL_REDUCTION_SUPPORTED_SIMULATION_ONLY"
        if passed
        else "CONTROL_FAILURE",
        "passed": passed,
        "competitive_claim_allowed": False,
        "claim_boundary": manifest["claim_boundary"]["statement"],
    }
    result_path = output_dir / "cosmic_hw_22_causal_transition_result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    evidence_paths = [result_path, *sorted(log_dir.glob("*.log"))]
    if len(evidence_paths) != 17:
        raise RuntimeError(f"HW-22 evidence cardinality mismatch: {len(evidence_paths)}")
    post_result_identity = git_identity(expected_head)
    if (
        not post_result_identity["clean"]
        or post_result_identity["head"] != final["head"]
        or post_result_identity["tree"] != final["tree"]
    ):
        raise RuntimeError(
            f"HW-22 source identity moved while writing result: "
            f"final={final} post_result={post_result_identity}"
        )
    write_evidence_manifest(
        output_dir,
        evidence_paths,
        completed_at=completed_at,
        parent=manifest["parent"],
        expected_head=expected_head,
        initial_identity=initial,
        final_identity=post_result_identity,
        scope_identity=scope,
        workflow=workflow,
    )
    terminal_identity = git_identity(expected_head)
    if (
        not terminal_identity["clean"]
        or terminal_identity["head"] != post_result_identity["head"]
        or terminal_identity["tree"] != post_result_identity["tree"]
    ):
        raise RuntimeError(
            f"HW-22 source identity moved while writing evidence manifest: "
            f"post_result={post_result_identity} terminal={terminal_identity}"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure the HW-22 causal state-time transition for delayed versus eager held flush."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("build/cosmic-hw-22-causal-transition"),
    )
    args = parser.parse_args()
    output_path = args.output_dir / "cosmic_hw_22_causal_transition_result.json"
    try:
        result = execute(args.output_dir)
    except (FileNotFoundError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        result = {
            "experiment_id": "COSMIC-HW-22/v0.1",
            "completed_at": utc_now(),
            "decision": "CONTROL_FAILURE",
            "passed": False,
            "competitive_claim_allowed": False,
            "execution_states": {
                "rtl_simulation": "FAIL",
                "synthesis": "NOT_RUN",
                "place_and_route": "NOT_RUN",
                "physical_board": "NOT_RUN",
                "power": "NOT_RUN",
            },
            "error": str(error),
        }
        args.output_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
