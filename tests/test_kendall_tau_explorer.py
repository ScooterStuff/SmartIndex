from smartindex.kendall_tau_explorer import (
    KendallTauExplorer,
    kendall_tau_distance,
    permutations_within_distance,
)
from smartindex.models import IndexCandidate


# --------------------------------------------------------------------- #
# Distance metric

def test_distance_identical_is_zero():
    assert kendall_tau_distance(["a", "b", "c"], ["a", "b", "c"]) == 0


def test_distance_adjacent_swap_is_one():
    assert kendall_tau_distance(["a", "b", "c"], ["b", "a", "c"]) == 1


def test_distance_full_reverse_is_max():
    a = ["a", "b", "c", "d"]
    assert kendall_tau_distance(a, list(reversed(a))) == 6  # n*(n-1)/2


# --------------------------------------------------------------------- #
# Permutation generation

def test_permutations_respect_max_distance():
    base = ["a", "b", "c", "d"]
    perms = permutations_within_distance(base, max_distance=2)
    assert base not in perms  # excludes the identity
    for p in perms:
        d = kendall_tau_distance(base, p)
        assert 1 <= d <= 2


def test_permutations_respects_max_count():
    base = ["a", "b", "c", "d", "e"]
    perms = permutations_within_distance(base, max_distance=4, max_permutations=10)
    assert len(perms) == 10


# --------------------------------------------------------------------- #
# Explorer

def test_explorer_returns_original_when_nothing_better():
    scores = {
        ("a", "b", "c"): 100.0,
        ("b", "a", "c"): 200.0,
        ("a", "c", "b"): 300.0,
    }

    def scorer(fields, _queries):
        return scores.get(tuple(fields), 999.0)

    cand = IndexCandidate(fields=["a", "b", "c"], covered_queries=[1])
    res = KendallTauExplorer(scorer, max_distance=1).explore(cand, [])
    assert res.best_index == ["a", "b", "c"]
    assert not res.changed
    assert res.improvement == 0.0


def test_explorer_finds_better_permutation():
    scores = {
        ("a", "b", "c"): 100.0,
        ("b", "a", "c"): 40.0,   # winner, distance 1
        ("a", "c", "b"): 80.0,
    }

    def scorer(fields, _queries):
        return scores.get(tuple(fields), 999.0)

    cand = IndexCandidate(fields=["a", "b", "c"], covered_queries=[1])
    res = KendallTauExplorer(scorer, max_distance=1).explore(cand, [])
    assert res.best_index == ["b", "a", "c"]
    assert res.distance == 1
    assert res.improvement == 60.0
    assert res.changed
