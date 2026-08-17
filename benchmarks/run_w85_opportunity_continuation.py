"""Preregistered opportunity-seeking continuation for frozen MORPHOS-W8.5.

The first independent W8.5 confirmation was scientifically red because its
fresh sample contained zero W8.4 misses. That result was safe and exact but had
no causal opportunity to demonstrate incremental W8.5 rescue.

This continuation does not change W8.5. It evaluates complete, predeclared
fresh-seed batches in a fixed order and stops after the first complete batch
containing at least one W8.4 miss, or after the fixed maximum budget. Thus the
search for a causal opportunity cannot optionally stop on a desired rescue.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from benchmarks.probe_witness_multierasure import _adaptation
from benchmarks.probe_witness_persistent import _manifest
from benchmarks.run_multimirror import _m2_law, _s2_components
from benchmarks.run_w85_confirmation import _corpus

MANIFEST = Path(__file__).with_name("w85_opportunity_continuation_manifest.json")
REPO_ROOT = Path(__file__).resolve().parents[1]
MECHANISM = REPO_ROOT / "morphos" / "witness_multierasure.py"


def _git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def _adaptation_summary(protocol: dict, observed_rows: list[dict]) -> dict:
    base = _manifest()
    adaptation: dict[str, dict] = {}
    for row in observed_rows:
        size = f"{row['width']}x{row['height']}"
        if size in adaptation:
            continue
        config, hierarchy = _s2_components(base, row["width"], row["height"])
        adaptation[size] = _adaptation(
            config,
            hierarchy,
            _m2_law(base),
            row["width"] * row["height"],
            protocol,
        )
    return adaptation


def _controls_pass(rows: list[dict], adaptation: dict, gate: dict) -> bool:
    if not rows:
        return False
    return (
        all(
            row["w85_recovery_at_8"]
            >= gate["minimum_w85_recovery_at_8_every_observed_corpus"]
            for row in rows
        )
        and all(
            row["w85_recovery_at_12"]
            >= gate["minimum_w85_recovery_at_12_every_observed_corpus"]
            for row in rows
        )
        and sum(row["previous_w84_successes_regressed"] for row in rows)
        <= gate["maximum_previous_w84_successes_regressed"]
        and all(
            row["causal_drop_when_witness_corrupted"]
            >= gate[
                "minimum_causal_drop_when_witness_corrupted_every_observed_corpus"
            ]
            for row in rows
        )
        and all(
            row["primary_only_delta_vs_w84"]
            >= gate["minimum_primary_only_delta_vs_w84_every_observed_corpus"]
            for row in rows
        )
        and all(
            row["zero_drive_exact_w84"]
            == gate["zero_drive_exact_w84_every_observed_corpus"]
            for row in rows
        )
        and (
            all(
                item["passes"]
                and item["completion_events"] == gate["adaptation_completion_events"]
                and item["executable_closure_events"]
                == gate["adaptation_executable_closure_events"]
                and item["history_pair_decode_events"]
                == gate["adaptation_history_pair_decode_events"]
                and item["locality_pair_decode_events"]
                == gate["adaptation_locality_pair_decode_events"]
                and item["multi_erasure_decode_events"]
                == gate["adaptation_multi_erasure_decode_events"]
                for item in adaptation.values()
            )
            if gate["adaptation_every_size"]
            else True
        )
    )


def run_continuation() -> dict:
    protocol = json.loads(MANIFEST.read_text(encoding="utf-8"))
    actual_blob = _git_blob_sha(MECHANISM)
    expected_blob = protocol["frozen_mechanism_blob_sha"]
    if actual_blob != expected_blob:
        raise RuntimeError(
            "W8.5 mechanism changed relative to preregistered frozen blob: "
            f"expected {expected_blob}, got {actual_blob}"
        )

    observed_rows: list[dict] = []
    all_rescues: list[dict] = []
    batch_summaries: list[dict] = []
    opportunity_batch: str | None = None

    for batch_index, batch in enumerate(protocol["batches"], start=1):
        if batch_index > protocol["maximum_batches"]:
            break

        batch_rows: list[dict] = []
        batch_rescues: list[dict] = []
        for corpus in batch["corpora"]:
            row, rescues = _corpus(corpus, protocol)
            batch_rows.append(row)
            batch_rescues.extend(rescues)

        observed_rows.extend(batch_rows)
        all_rescues.extend(batch_rescues)
        batch_misses = sum(row["fresh_w84_misses"] for row in batch_rows)
        batch_summary = {
            "id": batch["id"],
            "families": batch["families"],
            "corpora": len(batch_rows),
            "trials": sum(row["trials"] for row in batch_rows),
            "fresh_w84_misses": batch_misses,
            "multi_erasure_rescues_of_w84_misses": sum(
                row["multi_erasure_rescues_of_w84_misses"] for row in batch_rows
            ),
            "multi_erasure_decode_trials": sum(
                row["multi_erasure_decode_trials"] for row in batch_rows
            ),
            "previous_w84_successes_regressed": sum(
                row["previous_w84_successes_regressed"] for row in batch_rows
            ),
            "minimum_w85_recovery_at_8": min(
                row["w85_recovery_at_8"] for row in batch_rows
            ),
            "minimum_w85_recovery_at_12": min(
                row["w85_recovery_at_12"] for row in batch_rows
            ),
        }
        batch_summaries.append(batch_summary)

        # Stopping is batch-level and depends only on whether the frozen
        # predecessor produced at least one miss, never on whether W8.5 rescued it.
        if batch_misses > 0:
            opportunity_batch = batch["id"]
            break

    adaptation = _adaptation_summary(protocol, observed_rows)
    gate = protocol["predeclared_gates"]
    controls_pass = _controls_pass(observed_rows, adaptation, gate)

    fresh_misses = sum(row["fresh_w84_misses"] for row in observed_rows)
    rescues = sum(
        row["multi_erasure_rescues_of_w84_misses"] for row in observed_rows
    )
    regressions = sum(
        row["previous_w84_successes_regressed"] for row in observed_rows
    )

    if not controls_pass:
        decision = "CONFIRMATION_FAIL"
        decision_reason = "one or more frozen recovery/control gates failed"
    elif opportunity_batch is None:
        decision = "INCONCLUSIVE_NO_OPPORTUNITY"
        decision_reason = (
            "maximum preregistered batch budget exhausted with zero W8.4 misses"
        )
    elif (
        fresh_misses
        >= gate["minimum_fresh_w84_misses_for_transfer_decision"]
        and rescues >= gate["minimum_multi_erasure_rescues_for_transfer_pass"]
    ):
        decision = "TRANSFER_PASS"
        decision_reason = (
            "a preregistered fresh W8.4 failure opportunity occurred and at least "
            "one miss was rescued specifically by W8.5 multi-erasure decoding"
        )
    else:
        decision = "CONFIRMATION_FAIL"
        decision_reason = (
            "a fresh W8.4 failure opportunity occurred but W8.5 did not satisfy "
            "the preregistered causal rescue condition"
        )

    nonperfect_or_active = [
        row
        for row in observed_rows
        if (
            row["w85_recovery_at_8"] < 1.0
            or row["w85_recovery_at_12"] < 1.0
            or row["fresh_w84_misses"] > 0
            or row["multi_erasure_decode_events"] > 0
        )
    ]

    summary = {
        "decision": decision,
        "decision_reason": decision_reason,
        "mechanism_blob_matches_frozen": actual_blob == expected_blob,
        "observed_batches": len(batch_summaries),
        "opportunity_batch": opportunity_batch,
        "observed_corpora": len(observed_rows),
        "observed_trials": sum(row["trials"] for row in observed_rows),
        "fresh_w84_misses": fresh_misses,
        "multi_erasure_rescues_of_w84_misses": rescues,
        "multi_erasure_decode_trials": sum(
            row["multi_erasure_decode_trials"] for row in observed_rows
        ),
        "multi_erasure_decode_events": sum(
            row["multi_erasure_decode_events"] for row in observed_rows
        ),
        "multi_erasure_added_targets": sum(
            row["multi_erasure_added_targets"] for row in observed_rows
        ),
        "previous_w84_successes_regressed": regressions,
        "minimum_w85_recovery_at_8": min(
            row["w85_recovery_at_8"] for row in observed_rows
        ),
        "minimum_w85_recovery_at_12": min(
            row["w85_recovery_at_12"] for row in observed_rows
        ),
        "minimum_causal_drop_when_witness_corrupted": min(
            row["causal_drop_when_witness_corrupted"] for row in observed_rows
        ),
        "minimum_primary_only_delta_vs_w84": min(
            row["primary_only_delta_vs_w84"] for row in observed_rows
        ),
        "all_zero_drive_exact_w84": all(
            row["zero_drive_exact_w84"] for row in observed_rows
        ),
        "recovery_and_controls_pass": controls_pass,
        "adaptation_by_size": adaptation,
    }

    return {
        "schema": protocol["schema"],
        "continuation_only_no_retuning": True,
        "frozen_w85_development_head": protocol["frozen_w85_development_head"],
        "source_inconclusive_confirmation_head": protocol[
            "source_inconclusive_confirmation_head"
        ],
        "stopping_rule": protocol["stopping_rule"],
        "maximum_batches": protocol["maximum_batches"],
        "maximum_additional_trials": protocol["maximum_additional_trials"],
        "criteria": gate,
        "batch_summaries": batch_summaries,
        "multi_erasure_rescues": all_rescues,
        "nonperfect_or_active_rows": nonperfect_or_active,
        "summary": summary,
        "decision": decision,
        "scope_boundary": protocol["scope_boundary"],
    }


def main() -> None:
    report = run_continuation()
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["decision"] == "CONFIRMATION_FAIL":
        raise SystemExit("MORPHOS-W8.5 opportunity continuation confirmation failed")


if __name__ == "__main__":
    main()
