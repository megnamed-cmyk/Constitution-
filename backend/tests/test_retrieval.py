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


from app.retrieval import assess_grounding


def _c(reranker=None, rrf=0.01):
    return {"chunk_id": "x", "rrf_score": rrf, "reranker_score": reranker}


def test_grounding_with_reranker_scores():
    assert assess_grounding([_c(0.80), _c(0.05)]) == "grounded"  # one strong match is enough
    assert assess_grounding([_c(0.45)]) == "grounded"            # cutoffs are inclusive
    assert assess_grounding([_c(0.30), _c(0.20)]) == "weak"
    assert assess_grounding([_c(0.10), _c(0.00)]) == "none"      # e.g. the 0.000 demo source


def test_grounding_empty():
    assert assess_grounding([]) == "none"


def test_grounding_without_reranker_uses_search_agreement():
    both_lists = compute_rrf([{"chunk_id": "a"}], [{"chunk_id": "a"}])  # found by dense AND keyword
    one_list = compute_rrf([{"chunk_id": "a"}], [])                     # dense only
    assert assess_grounding(both_lists) == "grounded"
    assert assess_grounding(one_list) == "weak"
    # worst case for agreement still beats the best single-list score, at the max pool size
    worst_both = compute_rrf([{"chunk_id": f"d{i}"} for i in range(50)], [{"chunk_id": f"s{i}"} for i in range(49)] + [{"chunk_id": "d49"}])
    assert assess_grounding([d for d in worst_both if d["chunk_id"] == "d49"]) == "grounded"
