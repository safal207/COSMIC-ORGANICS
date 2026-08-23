from __future__ import annotations

import json
from pathlib import Path

from benchmarks.cosmic_hw_07_candidate import pack_receipt
from benchmarks.cosmic_hw_07_stress import corpus_fingerprint, validate_stress_corpus

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_manifest_and_stress_boundary_unchanged() -> None:
    manifest = json.loads((ROOT / "benchmarks" / "cosmic_hw_07_manifest.json").read_text())
    assert manifest["experiment_id"] == "COSMIC-HW-07/v0.1"
    assert manifest["parent_hardware_head"] == "5b3b4c8c77ffdbe17ad573951cca59a1c15aeb44"
    assert manifest["receipt"]["width_bits"] == 40
    assert manifest["receipt"]["batch_fifo_depth"] == 4
    assert manifest["receipt"]["batch_snapshot_bits_excluding_queue_control"] == 848
    assert manifest["receipt"]["output_lanes"] == 1
    assert manifest["receipt"]["output_handshake"] == "valid_ready"
    assert manifest["functional_gates"]["sparse_low_activity_minimum_pe_evaluation_reduction"] == 0.50
    assert manifest["synthetic_combined_score_allowed"] is False
    assert manifest["timing_decisive"] is False

    summary = validate_stress_corpus()
    assert summary["sequences"] == 64
    assert summary["ticks"] == 768
    assert summary["maximum_batch"] == 64
    assert summary["total_transitions"] == 16848
    assert summary["consecutive_heavy_pairs"] == 247
    assert summary["zero_transition_ticks"] == 417
    assert corpus_fingerprint() == "sha256:be033839531356f0695b6c270b8d22a2abb8f388dd1ecb9c4b93644c9b291110"


def test_receipt_bit_layout_is_exactly_frozen_40_bits() -> None:
    packed = pack_receipt(
        logical_tick=0x1234,
        site=0x2A,
        phase_before="M",
        phase_after="C",
        stimulus_s100=-80,
        ordinal=0x15,
    )
    assert packed.bit_length() <= 40
    assert (packed >> 24) & 0xFFFF == 0x1234
    assert (packed >> 18) & 0x3F == 0x2A
    assert (packed >> 16) & 0x3 == 1
    assert (packed >> 14) & 0x3 == 2
    assert (packed >> 6) & 0xFF == ((-80) & 0xFF)
    assert packed & 0x3F == 0x15


def test_receipt_rtl_is_observer_wrapper_over_frozen_hw06_core() -> None:
    rtl = (ROOT / "rtl" / "cosmic_hw_07_receipt.v").read_text()
    assert "module cosmic_hw07_dense_receipt_mesh64" in rtl
    assert "module cosmic_hw07_sparse_receipt_mesh64" in rtl
    assert "cosmic_hw06_mesh64 #(.SPARSE(SPARSE)) core" in rtl
    assert "assign core_tick_en = tick_valid && tick_ready;" in rtl
    assert "assign tick_ready = (reserved_count < FIFO_DEPTH);" in rtl
    assert "parameter integer FIFO_DEPTH = 4" in rtl
    assert "output wire [39:0]  receipt_data" in rtl
    assert "fifo_changed" in rtl
    assert "selected_site_comb" in rtl

    # The HW-07 observer must not contain a second copy of the transition-law
    # threshold/coupling implementation.  That authority remains in HW-06.
    assert "coupling100" not in rtl
    assert "threshold100" not in rtl
    assert "drive_num" not in rtl
