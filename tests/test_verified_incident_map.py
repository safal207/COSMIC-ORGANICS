from __future__ import annotations

from demos.verified_incident_map import run_demo


def test_verified_incident_map_end_to_end() -> None:
    result = run_demo()

    assert result["status"] == "PASS"
    correctness = result["correctness"]
    assert all(correctness.values())

    application_result = result["result"]
    assert application_result["completed_transitions"] > 0
    assert application_result["audited_transitions"] == application_result["completed_transitions"]
    assert sum(application_result["final_phase_counts"].values()) == 256

    work = result["execution_work"]
    assert work["dense"]["node_evaluations"] == 24 * 256
    assert work["sparse"]["node_evaluations"] < work["dense"]["node_evaluations"]
    assert work["sparse_node_evaluation_reduction_fraction"] >= 0.50

    proof = result["proof_work"]
    assert proof["audited_transitions"] == application_result["completed_transitions"]
    assert proof["canonical_proof_payload_bytes"] > 0
    assert proof["hash_evaluations"] > 0

    evidence = result["evidence"]
    assert evidence["proof_canonical_bytes"] == proof["canonical_proof_payload_bytes"]
    assert len(evidence["proof_sha256"]) == 64
