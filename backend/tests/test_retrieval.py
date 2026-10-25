from app.retrieval import compute_rrf


def test_rrf_rewards_agreement():
    dense = [{"chunk_id": "a"}, {"chunk_id": "b"}, {"chunk_id": "c"}]
    sparse = [{"chunk_id": "b"}, {"chunk_id": "d"}]
    fused = compute_rrf(dense, sparse)
    assert fused[0]["chunk_id"] == "b"  # ranked in both lists
    assert {d["chunk_id"] for d in fused} == {"a", "b", "c", "d"}
    assert fused[0]["rrf_score"] == 1 / 62 + 1 / 61


def test_rrf_empty():
    assert compute_rrf([], []) == []
