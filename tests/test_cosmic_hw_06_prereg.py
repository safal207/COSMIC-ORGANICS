import json
from pathlib import Path


def test_cosmic_hw_06_prereg_boundary() -> None:
    manifest = json.loads(
        Path("benchmarks/cosmic_hw_06_manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["experiment_id"] == "COSMIC-HW-06/v0.1"
    assert manifest["lattice"]["width"] == 8
    assert manifest["lattice"]["height"] == 8
    assert manifest["lattice"]["phases"] == ["A", "M", "C"]
    assert manifest["minimum_vector_sequences"] >= 256
    assert (
        manifest["sparse_primary_gate"]["minimum_pe_evaluation_reduction"] == 0.50
    )
    assert manifest["timing_decisive"] is False
    assert manifest["synthetic_combined_score_allowed"] is False

    forbidden = (
        Path("rtl/cosmic_hw_06.v"),
        Path("rtl/cosmic_hw_06_tb.v"),
        Path("benchmarks/run_cosmic_hw_06.py"),
    )
    assert not any(path.exists() for path in forbidden), (
        "RTL candidate must remain absent on the frozen COSMIC-HW-06 prereg head"
    )
