"""Greedy Remover (optional optimisation layer).

Repeatedly drops the trailing field of one index from the current set,
re-scores the workload, and keeps the removal only if performance stays
within an acceptable degradation threshold. Stops when no further
removal is acceptable.

This is an *optional* optimiser – run it after MinSet when you want to
trade a small, bounded performance loss for fewer / shorter indexes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from .models import IndexCandidate, Query


# Scorer for a *whole* index set (lower = better).
SetScoreFn = Callable[[list[list[str]], list[Query]], float]


@dataclass
class GreedyRemovalResult:
    final_indexes: list[list[str]]
    removed_fields: list[tuple[str, list[str]]] = field(default_factory=list)
    original_score: float = 0.0
    final_score: float = 0.0
    metric: str = "totalKeysExamined"
    iterations: int = 0

    @property
    def degradation(self) -> float:
        if self.original_score <= 0:
            return 0.0
        return (self.final_score - self.original_score) / self.original_score


class GreedyRemover:
    """Greedy trailing-field remover with a degradation budget."""

    def __init__(
        self,
        scorer: SetScoreFn,
        *,
        max_allowed_degradation: float = 0.10,
        min_index_length: int = 1,
        metric: str = "totalKeysExamined",
        allow_remove_first_field: bool = False,
    ) -> None:
        self.scorer = scorer
        self.max_allowed_degradation = max_allowed_degradation
        self.min_index_length = max(1, min_index_length)
        self.metric = metric
        self.allow_remove_first_field = allow_remove_first_field

    def optimise(
        self,
        candidates: list[IndexCandidate],
        queries: list[Query],
    ) -> GreedyRemovalResult:
        current: list[list[str]] = [list(c.fields) for c in candidates]
        original_score = self.scorer(current, queries)
        budget = original_score * (1 + self.max_allowed_degradation)

        removed: list[tuple[str, list[str]]] = []
        iterations = 0

        while True:
            iterations += 1
            best_set: Optional[list[list[str]]] = None
            best_score: Optional[float] = None
            best_removed: Optional[tuple[str, list[str]]] = None

            for idx, fields in enumerate(current):
                min_len = (
                    1 if self.allow_remove_first_field else self.min_index_length
                )
                if len(fields) <= min_len:
                    continue
                trial = [list(f) for f in current]
                dropped = trial[idx].pop()  # trailing field
                # Drop empty entries and exact duplicates that may have
                # appeared after shortening.
                trial = _dedupe_keep_order([t for t in trial if t])

                score = self.scorer(trial, queries)
                if score > budget:
                    continue
                if best_score is None or score < best_score:
                    best_set = trial
                    best_score = score
                    best_removed = (dropped, list(fields))

            if best_set is None:
                break
            current = best_set
            removed.append(best_removed)  # type: ignore[arg-type]
            # Tighten budget against the *original* score, not the new one –
            # the spec compares against the starting performance.

        final_score = self.scorer(current, queries)
        return GreedyRemovalResult(
            final_indexes=current,
            removed_fields=removed,
            original_score=original_score,
            final_score=final_score,
            metric=self.metric,
            iterations=iterations,
        )


def _dedupe_keep_order(items: list[list[str]]) -> list[list[str]]:
    seen: set[tuple[str, ...]] = set()
    out: list[list[str]] = []
    for it in items:
        key = tuple(it)
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


# --------------------------------------------------------------------- #
# MongoDB-backed set scorer


def make_explain_set_scorer(
    collection,
    *,
    metric: str = "totalKeysExamined",
    runs: int = 3,
    warmup: int = 1,
) -> SetScoreFn:
    """Return a fair scorer for an entire index set.

    For each scoring call: (1) create every index in the set, (2) warm
    up, (3) run each query ``runs`` times, (4) drop every index again,
    (5) return the median ``metric`` across all measurements. Same
    methodology, same workload, same database state for every call.
    """
    from .mongo_tester import MongoTester

    tester = MongoTester(collection)

    def _score(indexes: list[list[str]], queries: Iterable[Query]) -> float:
        created: list[str] = []
        samples: list[float] = []
        try:
            for fields in indexes:
                if not fields:
                    continue
                name = tester.create_index(IndexCandidate(fields=list(fields)))
                created.append(name)
            queries = list(queries)
            # Warm-up runs – discarded.
            for _ in range(max(0, warmup)):
                for q in queries:
                    tester.explain_query(q)
            for _ in range(runs):
                for q in queries:
                    info = tester.explain_query(q)
                    val = info.get(metric)
                    if isinstance(val, (int, float)):
                        samples.append(float(val))
        finally:
            for name in created:
                tester.drop_index(name)
        if not samples:
            return float("inf")
        samples.sort()
        return samples[len(samples) // 2]

    return _score
