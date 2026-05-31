"""Kendall-Tau Explorer (optional validation layer).

Generates permutations of a candidate index that are within a small
Kendall-Tau distance of the theoretically derived order, scores each
one against MongoDB, and returns the best-performing alternative.

This is an *optional* validator – the main pipeline is complete without
it. Use it when you want to double-check that the graph-derived order
also performs best on the live database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import permutations
from typing import Callable, Iterable, Optional

from .models import IndexCandidate, Query


# --------------------------------------------------------------------- #
# Kendall-Tau distance


def kendall_tau_distance(a: list[str], b: list[str]) -> int:
    """Number of pairwise order disagreements between two permutations.

    Both lists must contain the same elements. Distance is 0 for
    identical inputs, 1 for an adjacent swap, and ``n*(n-1)/2`` for the
    full reversal of a list of length ``n``.
    """
    if len(a) != len(b):
        raise ValueError("permutations must be the same length")
    pos = {x: i for i, x in enumerate(b)}
    if len(pos) != len(a):
        raise ValueError("permutations must contain unique elements")
    n = len(a)
    disagreements = 0
    for i in range(n):
        for j in range(i + 1, n):
            if pos[a[i]] > pos[a[j]]:
                disagreements += 1
    return disagreements


def permutations_within_distance(
    base: list[str], max_distance: int, *, max_permutations: int = 100
) -> list[list[str]]:
    """Enumerate permutations of ``base`` whose KT distance is in
    ``[1, max_distance]``.

    For small indexes (n ≤ 8) this enumerates all ``n!`` permutations
    and filters; for larger inputs it falls back to repeated adjacent
    swaps which keeps the search space bounded.
    """
    if max_distance <= 0 or len(base) < 2:
        return []

    n = len(base)
    if n <= 8:
        seen: set[tuple[str, ...]] = set()
        out: list[list[str]] = []
        base_tuple = tuple(base)
        for perm in permutations(base):
            if perm == base_tuple:
                continue
            if perm in seen:
                continue
            d = kendall_tau_distance(base, list(perm))
            if 1 <= d <= max_distance:
                seen.add(perm)
                out.append(list(perm))
                if len(out) >= max_permutations:
                    break
        return out

    # n > 8: BFS by adjacent swaps so we stay close to ``base``.
    frontier: list[list[str]] = [list(base)]
    visited: set[tuple[str, ...]] = {tuple(base)}
    out: list[list[str]] = []
    for _ in range(max_distance):
        next_frontier: list[list[str]] = []
        for perm in frontier:
            for i in range(n - 1):
                swapped = perm.copy()
                swapped[i], swapped[i + 1] = swapped[i + 1], swapped[i]
                key = tuple(swapped)
                if key in visited:
                    continue
                visited.add(key)
                next_frontier.append(swapped)
                out.append(swapped)
                if len(out) >= max_permutations:
                    return out
        frontier = next_frontier
        if not frontier:
            break
    return out


# --------------------------------------------------------------------- #
# Result and explorer


@dataclass
class KendallTauResult:
    original_index: list[str]
    best_index: list[str]
    distance: int
    original_score: float
    best_score: float
    metric: str
    permutations_tested: int
    improvement: float = 0.0
    scores: dict[tuple[str, ...], float] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return self.original_index != self.best_index


# Scorer signature: (index_fields, queries) -> numeric score (lower = better)
ScoreFn = Callable[[list[str], list[Query]], float]


class KendallTauExplorer:
    """Test permutations near the theoretical order."""

    def __init__(
        self,
        scorer: ScoreFn,
        *,
        max_distance: int = 3,
        max_permutations: int = 100,
        metric: str = "totalKeysExamined",
    ) -> None:
        self.scorer = scorer
        self.max_distance = max_distance
        self.max_permutations = max_permutations
        self.metric = metric

    def explore(
        self,
        candidate: IndexCandidate,
        queries: list[Query],
    ) -> KendallTauResult:
        original = list(candidate.fields)
        original_score = self.scorer(original, queries)

        best_index = original
        best_score = original_score
        best_distance = 0
        scores: dict[tuple[str, ...], float] = {tuple(original): original_score}

        perms = permutations_within_distance(
            original,
            max_distance=self.max_distance,
            max_permutations=self.max_permutations,
        )
        for perm in perms:
            score = self.scorer(perm, queries)
            scores[tuple(perm)] = score
            if score < best_score:
                best_score = score
                best_index = perm
                best_distance = kendall_tau_distance(original, perm)

        return KendallTauResult(
            original_index=original,
            best_index=best_index,
            distance=best_distance,
            original_score=original_score,
            best_score=best_score,
            metric=self.metric,
            permutations_tested=len(perms),
            improvement=original_score - best_score,
            scores=scores,
        )


# --------------------------------------------------------------------- #
# Default MongoDB-backed scorer


def make_explain_scorer(
    collection,
    *,
    metric: str = "totalKeysExamined",
    runs: int = 3,
) -> ScoreFn:
    """Return a scorer that creates the index, runs each query, drops
    the index, and reports the median value of ``metric``.

    The collection must be a real :class:`pymongo.collection.Collection`.
    """
    from .mongo_tester import MongoTester

    tester = MongoTester(collection)

    def _score(fields: list[str], queries: Iterable[Query]) -> float:
        cand = IndexCandidate(fields=list(fields))
        name: Optional[str] = None
        samples: list[float] = []
        try:
            name = tester.create_index(cand)
            for q in queries:
                for _ in range(runs):
                    info = tester.explain_query(q)
                    val = info.get(metric)
                    if isinstance(val, (int, float)):
                        samples.append(float(val))
        finally:
            if name:
                tester.drop_index(name)
        if not samples:
            return float("inf")
        samples.sort()
        return samples[len(samples) // 2]

    return _score
