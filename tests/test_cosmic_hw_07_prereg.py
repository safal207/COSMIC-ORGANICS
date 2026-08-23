import json
from pathlib import Path

from benchmarks.cosmic_hw_07_stress import (
    CLASSES,
    READY_PATTERNS,
    build_stress_sequences,
    receipt_ready,
    validate_stress_corpus,
)


def test_cosmic_hw_07_manifest_and_candidate_absence() -> None:
    manifest = json.loads(
        Path("benchmarks/cosmic_hw_07_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["experiment_id"] == "COSMIC-HW-07/v0.1"
    assert manifest["parent_hardware_head"] == (
        "5b3b4c8c77ffdbe17ad573951cca59a1c15aeb44"
    )
    assert manifest["receipt"]["width_bits"] == 40
    assert manifest["receipt"]["output_lanes"] == 1
    assert manifest["receipt"]["batch_fifo_depth"] == 4
    assert manifest["receipt"]["batch_snapshot_bits_excluding_queue_control"] == 848
    assert manifest["receipt"]["cryptographic_commitment_generated_in_hw"] is False
    assert manifest["functional_gates"]["missing_receipts"] == 0
    assert manifest["functional_gates"]["duplicate_receipts"] == 0
    assert manifest["functional_gates"]["phantom_receipts"] == 0
    assert manifest["synthetic_combined_score_allowed"] is False
    assert manifest["timing_decisive"] is False
    assert manifest["physical_sha_merkle_deferred"] is True

    forbidden = (
        Path("rtl/cosmic_hw_07_receipt.v"),
        Path("benchmarks/run_cosmic_hw_07.py"),
    )
    assert not any(path.exists() for path in forbidden), (
        "HW-07 receipt candidate must remain absent on prereg head"
    )


def test_cosmic_hw_07_stress_corpus_is_frozen_and_complete() -> None:
    summary = validate_stress_corpus()
    assert summary["sequences"] == 64
    assert summary["ticks"] == 768
    assert summary["maximum_batch"] == 64
    assert summary["zero_transition_ticks"] > 0
    assert summary["consecutive_heavy_pairs"] > 0
    assert summary["total_transitions"] > 0
    assert summary["directions"] == [
        ["A", "M"],
        ["C", "M"],
        ["M", "A"],
        ["M", "C"],
    ]
    assert summary["fingerprint"].startswith("sha256:")
    assert len(summary["fingerprint"]) == len("sha256:") + 64

    sequences = build_stress_sequences()
    assert {sequence.stress_class for sequence in sequences} == set(CLASSES)
    assert {sequence.ready_pattern for sequence in sequences} == set(READY_PATTERNS)


def test_cosmic_hw_07_ready_patterns_are_exact() -> None:
    assert [receipt_ready("always_ready", c) for c in range(8)] == [True] * 8
    assert [receipt_ready("three_ready_one_blocked", c) for c in range(8)] == [
        True, True, True, False, True, True, True, False
    ]
    assert [receipt_ready("alternating_ready_blocked", c) for c in range(8)] == [
        True, False, True, False, True, False, True, False
    ]
    assert [receipt_ready("eight_cycle_block_bursts", c) for c in range(16)] == [
        False, False, False, False, False, False, False, False,
        True, True, True, True, True, True, True, True,
    ]
