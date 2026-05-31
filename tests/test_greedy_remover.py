from smartindex.greedy_remover import GreedyRemover
from smartindex.models import IndexCandidate


def _cand(fields):
    return IndexCandidate(fields=list(fields), covered_queries=[1])


def test_remover_strips_trailing_field_when_cheap():
    # Score depends only on the *first* field of each index, so trailing
    # fields are effectively free to drop.
    def scorer(indexes, _queries):
        return float(sum(len(idx[0]) for idx in indexes))

    final = GreedyRemover(scorer, max_allowed_degradation=0.0).optimise(
        [_cand(["a", "b", "c"]), _cand(["d", "e"])], queries=[]
    )
    fields = sorted(tuple(f) for f in final.final_indexes)
    assert fields == [("a",), ("d",)]
    assert final.degradation <= 0.0
    assert len(final.removed_fields) == 3  # c, b, e


def test_remover_respects_min_length():
    def scorer(indexes, _queries):
        return 0.0  # everything is "free"

    final = GreedyRemover(scorer, min_index_length=2).optimise(
        [_cand(["a", "b", "c"])], queries=[]
    )
    assert final.final_indexes == [["a", "b"]]


def test_remover_rejects_removal_above_threshold():
    # Removing any field doubles the cost.
    def scorer(indexes, _queries):
        n_fields = sum(len(idx) for idx in indexes)
        return 1000.0 / max(n_fields, 1)

    final = GreedyRemover(scorer, max_allowed_degradation=0.05).optimise(
        [_cand(["a", "b", "c"])], queries=[]
    )
    assert final.final_indexes == [["a", "b", "c"]]
    assert final.removed_fields == []


def test_remover_first_field_protected_by_default():
    def scorer(indexes, _queries):
        return 0.0

    final = GreedyRemover(scorer, max_allowed_degradation=1.0).optimise(
        [_cand(["a"])], queries=[]
    )
    # Single-field index can't be shortened with default min_index_length=1.
    assert final.final_indexes == [["a"]]


def test_remover_records_metric_name():
    def scorer(_indexes, _queries):
        return 1.0

    final = GreedyRemover(scorer, metric="executionTimeMillis").optimise(
        [_cand(["a", "b"])], queries=[]
    )
    assert final.metric == "executionTimeMillis"
