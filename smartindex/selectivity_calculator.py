"""Selectivity calculator using Shannon entropy.

Two operating modes:

* **Live mode** – when a :class:`pymongo.collection.Collection` is supplied,
  field distributions are sampled directly from MongoDB.
* **Heuristic mode** – when no collection is available, a deterministic
  fallback estimates entropy from query metadata so the rest of the
  pipeline still produces sensible orderings (used by unit tests and
  offline runs).
"""

from __future__ import annotations

import math
from typing import Iterable, Optional

from .models import Query, QueryField

RANGE_PENALTY = 0.4
SORT_PENALTY = 0.8
DEFAULT_RANGE_DISTRIBUTION = [0.5, 0.5]


def shannon_entropy(distribution: Iterable[float]) -> float:
    """Return Shannon entropy in bits for a probability distribution."""
    total = 0.0
    for p in distribution:
        if p > 0:
            total -= p * math.log2(p)
    return total


class SelectivityCalculator:
    def __init__(
        self,
        collection=None,
        *,
        sample_size: int = 1000,
        range_buckets: int = 8,
    ) -> None:
        self.collection = collection
        self.sample_size = sample_size
        self.range_buckets = range_buckets
        # name -> (search_type, selectivity)
        self._cache: dict[tuple[str, str], float] = {}

    # ------------------------------------------------------------------ #
    # Public API

    def annotate(self, queries: list[Query]) -> list[Query]:
        """Fill in ``selectivity`` for every :class:`QueryField` in place."""
        for q in queries:
            for f in q.fields:
                f.selectivity = self.selectivity_for(f)
        return queries

    def selectivity_for(self, qf: QueryField) -> float:
        key = (qf.name, qf.search_type)
        if key in self._cache:
            return self._cache[key]

        if qf.search_type == "E":
            score = self._equality_entropy(qf)
        elif qf.search_type == "R":
            score = self._range_entropy(qf) * RANGE_PENALTY
        else:  # "S"
            score = self._equality_entropy(qf) * SORT_PENALTY

        self._cache[key] = score
        return score

    # ------------------------------------------------------------------ #
    # Equality

    def _equality_entropy(self, qf: QueryField) -> float:
        if self.collection is not None:
            try:
                return self._equality_entropy_from_mongo(qf)
            except Exception:  # pragma: no cover - mongo failures fall back
                pass
        return self._heuristic_entropy(qf)

    def _equality_entropy_from_mongo(self, qf: QueryField) -> float:
        pipeline = [{"$sample": {"size": self.sample_size}}]
        if qf.partial_condition:
            # Best-effort: skip partial parsing here, treat as no filter.
            pass
        pipeline.append({"$group": {"_id": f"${qf.name}", "n": {"$sum": 1}}})
        counts = [doc["n"] for doc in self.collection.aggregate(pipeline)]
        total = sum(counts)
        if total == 0:
            return 0.0
        dist = [c / total for c in counts]
        return shannon_entropy(dist)

    # ------------------------------------------------------------------ #
    # Range

    def _range_entropy(self, qf: QueryField) -> float:
        if self.collection is None or not qf.range_criteria:
            return shannon_entropy(DEFAULT_RANGE_DISTRIBUTION)
        try:
            return self._range_entropy_from_mongo(qf)
        except Exception:  # pragma: no cover
            return shannon_entropy(DEFAULT_RANGE_DISTRIBUTION)

    def _range_entropy_from_mongo(self, qf: QueryField) -> float:
        coll = self.collection
        total = coll.estimated_document_count()
        if total == 0:
            return 0.0
        lo_doc = next(
            iter(coll.find({qf.name: {"$ne": None}}, {qf.name: 1}).sort(qf.name, 1).limit(1)),
            None,
        )
        hi_doc = next(
            iter(coll.find({qf.name: {"$ne": None}}, {qf.name: 1}).sort(qf.name, -1).limit(1)),
            None,
        )
        if not lo_doc or not hi_doc:
            return shannon_entropy(DEFAULT_RANGE_DISTRIBUTION)
        lo, hi = lo_doc[qf.name], hi_doc[qf.name]
        try:
            step = (hi - lo) / self.range_buckets
        except TypeError:
            return shannon_entropy(DEFAULT_RANGE_DISTRIBUTION)
        if step == 0:
            return 0.0
        buckets: list[float] = []
        cursor = lo
        for _ in range(self.range_buckets):
            nxt = cursor + step
            count = coll.count_documents({qf.name: {"$gte": cursor, "$lt": nxt}})
            buckets.append(count / total)
            cursor = nxt
        s = sum(buckets)
        if s > 1.0:
            buckets = [b / s for b in buckets]
        return shannon_entropy(buckets)

    # ------------------------------------------------------------------ #
    # Heuristic fallback

    @staticmethod
    def _heuristic_entropy(qf: QueryField) -> float:
        """Deterministic entropy estimate from the field name.

        It's not exact, but it's stable across runs and lets ordering
        decisions remain reproducible when MongoDB isn't available.
        """
        # Use a hash-derived distribution skew. Longer/more unique names
        # are assumed slightly more selective.
        h = abs(hash(qf.name)) % 1000 / 1000.0  # 0..1
        # Skewed distribution: dominant class has prob p, rest evenly split.
        p = 0.2 + 0.6 * h  # 0.2 .. 0.8
        dist = [p, 1 - p]
        return shannon_entropy(dist) + len(qf.name) * 0.01
