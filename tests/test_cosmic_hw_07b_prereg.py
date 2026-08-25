from __future__ import annotations

import json
from pathlib import Path

from benchmarks.cosmic_hw_07_stress import validate_stress_corpus

ROOT = Path(__file__).resolve().parents[1]


def manifest() -> dict:
    return json.loads((ROOT / "benchmarks" / "cosmic_hw_07b_manifest.json").read_text())


def test_hw07b_manifest_freezes_parent_and_control_evidence() -> None:
    m = manifest()
    assert m["experiment_id"] == "COSMIC-HW-07B/v0.1"
    assert m["parent_hw07_head"] == "1e71648e1a2f375d7eeb3147a301a81dc8bc2399"
    assert m["parent_hw07_decision"] == "SPARSE_PLUS_RECEIPT_PARETO_SUPPORTED"
    assert m["stress_fingerprint"] == "sha256:be033839531356f0695b6c270b8d22a2abb8f388dd1ecb9c4b93644c9b291110"

    control = m["frozen_control"]["official_hw07"]
    assert control["receipts"] == 41144
    assert control["accepted_ticks"] == 3840
    assert control["checks"] == 136368
    assert control["batch_fifo_writes"] == 2181
    assert control["batch_fifo_reads"] == 2181
    assert control["physical_cycles"] == 52610
    assert control["serializer_active_cycles"] == 51203
    assert control["backpressure_stalls"] == {
        "0.01": 0,
        "0.05": 542,
        "0.20": 4506,
        "1.00": 5212,
        "stress": 15298,
    }
    assert control["sparse_receipt_mapping"] == {
        "lut": 8698,
        "ff": 4386,
        "core_cells_excluding_io": 16903,
        "logic_depth_proxy": 266,
    }


def test_hw07b_candidate_set_selector_and_handoff_are_frozen() -> None:
    m = manifest()
    systems = {row["name"]: row for row in m["systems"]}
    assert systems == {
        "CONTROL_F4_FLAT": {
            "name": "CONTROL_F4_FLAT",
            "fifo_depth": 4,
            "selector": "flat_64_site_priority",
        },
        "CANDIDATE_F4_HIER": {
            "name": "CANDIDATE_F4_HIER",
            "fifo_depth": 4,
            "selector": "hierarchical_8x8_priority",
        },
        "CANDIDATE_F2_HIER": {
            "name": "CANDIDATE_F2_HIER",
            "fifo_depth": 2,
            "selector": "hierarchical_8x8_priority",
        },
        "CANDIDATE_F1_HIER": {
            "name": "CANDIDATE_F1_HIER",
            "fifo_depth": 1,
            "selector": "hierarchical_8x8_priority",
        },
    }

    selector = m["hierarchical_selector"]
    assert selector["rows"] == 8
    assert selector["columns"] == 8
    assert selector["row_selection"] == "lowest_nonempty_row"
    assert selector["column_selection"] == "lowest_set_column_within_selected_row"
    assert selector["global_order_must_remain"] == "ascending_site_id"
    assert selector["receipt_fields_may_change"] is False

    gates = m["functional_gates"]
    assert gates["f4_hier_stalls_must_exactly_match_control"] is True
    assert gates["sparse_low_activity_minimum_pe_evaluation_reduction"] == 0.50

    handoff = m["hw08_handoff"]
    assert handoff["eligibility"]["backpressure_stalls_0.01_max"] == 0
    assert handoff["eligibility"]["backpressure_stalls_0.05_max"] == 542
    assert handoff["eligibility"]["logic_depth_proxy_max"] == 266
    assert handoff["selection_order"] == [
        "minimum_core_cells_excluding_io",
        "minimum_ff",
        "minimum_lut",
        "minimum_logic_depth_proxy",
    ]
    assert handoff["fallback"] == "CONTROL_F4_FLAT"
    assert m["synthetic_combined_score_allowed"] is False
    assert m["timing_decisive"] is False
    assert m["sha_merkle_deferred"] is True


def test_frozen_stress_corpus_and_candidate_absence() -> None:
    summary = validate_stress_corpus()
    assert summary["fingerprint"] == "sha256:be033839531356f0695b6c270b8d22a2abb8f388dd1ecb9c4b93644c9b291110"
    assert summary["sequences"] == 64
    assert summary["ticks"] == 768
    assert summary["maximum_batch"] == 64
    assert summary["total_transitions"] == 16848
    assert summary["consecutive_heavy_pairs"] == 247
    assert summary["zero_transition_ticks"] == 417

    # Scientific boundary: no HW-07B candidate implementation may exist at
    # preregistration time.
    assert not (ROOT / "rtl" / "cosmic_hw_07b_receipt.v").exists()
    assert not (ROOT / "benchmarks" / "cosmic_hw_07b_candidate.py").exists()
