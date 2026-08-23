from benchmarks.cosmic_hw_06_phase1 import build_expected, make_testbench


def test_cosmic_hw_06_phase1_frozen_work_oracle() -> None:
    rows, work = build_expected()
    assert len(rows) == 256
    assert sum(len(row["ticks"]) for row in rows) == 256 * 12

    expected_sparse = {
        "0.01": 2194,
        "0.05": 6542,
        "0.20": 22121,
        "1.00": 40960,
    }
    for density, sparse_evaluations in expected_sparse.items():
        assert work[density]["dense_pe_evaluations"] == 49152
        assert work[density]["sparse_pe_evaluations"] == sparse_evaluations

    assert work["0.01"]["pe_evaluation_reduction"] > 0.95
    assert work["0.05"]["pe_evaluation_reduction"] > 0.86
    assert work["0.20"]["pe_evaluation_reduction"] > 0.54
    assert work["1.00"]["pe_evaluation_reduction"] < 0.17


def test_cosmic_hw_06_generated_testbench_contains_all_ticks() -> None:
    rows, _ = build_expected()
    text = make_testbench(rows)
    assert text.count("drive_tick(") == 256 * 12 + 1  # task declaration + calls
    assert "COSMIC_HW06_PHASE1_SIM PASS" in text
