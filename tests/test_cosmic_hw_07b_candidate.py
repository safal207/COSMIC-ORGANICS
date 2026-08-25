from __future__ import annotations

from pathlib import Path

from benchmarks.cosmic_hw_07b_candidate import PARETO_KEYS, SYSTEMS, dominates

ROOT=Path(__file__).resolve().parents[1]


def test_candidate_systems_are_exactly_the_preregistered_frontier() -> None:
    assert SYSTEMS == {
        "CONTROL_F4_FLAT": {"top":"cosmic_hw07_sparse_receipt_mesh64","depth":4,"selector":"flat_64_site_priority"},
        "CANDIDATE_F4_HIER": {"top":"cosmic_hw07b_sparse_f4_hier","depth":4,"selector":"hierarchical_8x8_priority"},
        "CANDIDATE_F2_HIER": {"top":"cosmic_hw07b_sparse_f2_hier","depth":2,"selector":"hierarchical_8x8_priority"},
        "CANDIDATE_F1_HIER": {"top":"cosmic_hw07b_sparse_f1_hier","depth":1,"selector":"hierarchical_8x8_priority"},
    }


def test_hierarchical_rtl_preserves_authority_boundary_and_fixed_selector_shape() -> None:
    rtl=(ROOT/"rtl"/"cosmic_hw_07b_receipt.v").read_text()
    assert "cosmic_hw06_mesh64 #(.SPARSE(1)) core" in rtl
    assert "assign core_tick_en = tick_valid && tick_ready;" in rtl
    assert "assign tick_ready = (reserved_count < FIFO_DEPTH);" in rtl
    assert "cosmic_hw07b_sparse_f4_hier" in rtl
    assert "cosmic_hw07b_sparse_f2_hier" in rtl
    assert "cosmic_hw07b_sparse_f1_hier" in rtl

    # Frozen 8x8 hierarchy must be visible as fixed row slices, not a renamed
    # second copy of the old flat 64-site transition selector.
    for slice_text in (
        "fifo_changed[rd_ptr][7:0]",
        "fifo_changed[rd_ptr][15:8]",
        "fifo_changed[rd_ptr][23:16]",
        "fifo_changed[rd_ptr][31:24]",
        "fifo_changed[rd_ptr][39:32]",
        "fifo_changed[rd_ptr][47:40]",
        "fifo_changed[rd_ptr][55:48]",
        "fifo_changed[rd_ptr][63:56]",
    ):
        assert slice_text in rtl

    # Transition authority remains entirely in frozen HW-06.
    assert "coupling100" not in rtl
    assert "threshold100" not in rtl
    assert "drive_num" not in rtl


def test_pareto_dominance_is_componentwise_and_has_no_weighted_score() -> None:
    a={key:10 for key in PARETO_KEYS}
    b={key:10 for key in PARETO_KEYS}
    b["lut"]=11
    assert dominates(a,b)
    assert not dominates(b,a)
    assert not dominates(a,a)

    # A tradeoff is non-dominating in both directions.
    c=dict(a); c["lut"]=9; c["ff"]=11
    assert not dominates(a,c)
    assert not dominates(c,a)
