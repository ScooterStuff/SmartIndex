"""Graph-based field ordering for a single query.

Each field of the query becomes a node.  For every ordered pair ``(u, v)``
an edge weight is computed that captures ESR priority and selectivity.
The final order is produced by ranking nodes on
``outgoing_weight - incoming_weight`` (descending).
"""

from __future__ import annotations

from .models import Query, QueryField

ESR_PRIORITY = {"E": 3, "S": 2, "R": 1}

# Tunables
ESR_WEIGHT = 10.0
SELECTIVITY_WEIGHT = 1.0
RANGE_PENALTY_EDGE = 5.0


def _esr_score(u: QueryField, v: QueryField) -> float:
    pu = ESR_PRIORITY.get(u.search_type, 0)
    pv = ESR_PRIORITY.get(v.search_type, 0)
    return ESR_WEIGHT * (pu - pv)


def _selectivity_score(u: QueryField, v: QueryField) -> float:
    return SELECTIVITY_WEIGHT * (u.selectivity - v.selectivity)


def _range_penalty(u: QueryField, v: QueryField) -> float:
    # Push range fields away from the front.
    if u.search_type == "R" and v.search_type != "R":
        return -RANGE_PENALTY_EDGE
    if v.search_type == "R" and u.search_type != "R":
        return RANGE_PENALTY_EDGE
    return 0.0


def edge_weight(u: QueryField, v: QueryField) -> float:
    """Strength of preferring ``u`` before ``v``."""
    return _esr_score(u, v) + _selectivity_score(u, v) + _range_penalty(u, v)


class GraphOrderer:
    """Produce an ordered field list (encoded names) for a query."""

    def order_fields(self, query: Query) -> list[str]:
        fields = query.fields
        n = len(fields)
        if n <= 1:
            return [f.name for f in fields]

        scores: dict[str, float] = {f.name: 0.0 for f in fields}
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                w = edge_weight(fields[i], fields[j])
                scores[fields[i].name] += w
                scores[fields[j].name] -= w

        # Sort by score desc; stable secondary by ESR then original order.
        original_index = {f.name: i for i, f in enumerate(fields)}
        return sorted(
            (f.name for f in fields),
            key=lambda name: (
                -scores[name],
                -ESR_PRIORITY.get(
                    next(f.search_type for f in fields if f.name == name), 0
                ),
                original_index[name],
            ),
        )
