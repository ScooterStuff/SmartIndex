"""Turn ordered query field lists into deduplicated IndexCandidates."""

from __future__ import annotations

from .graph_ordering import GraphOrderer
from .models import IndexCandidate, Query


class IndexGenerator:
    def __init__(self, orderer: GraphOrderer | None = None) -> None:
        self.orderer = orderer or GraphOrderer()

    def generate(self, queries: list[Query]) -> list[IndexCandidate]:
        by_key: dict[tuple[str, ...], IndexCandidate] = {}
        for q in queries:
            ordered = self.orderer.order_fields(q)
            key = tuple(ordered)
            if not key:
                continue
            cand = by_key.get(key)
            if cand is None:
                cand = IndexCandidate(
                    fields=list(ordered),
                    covered_queries=[q.query_id],
                    partial_condition=q.partial_condition,
                    reason=self._reason(q),
                )
                by_key[key] = cand
            else:
                if q.query_id not in cand.covered_queries:
                    cand.covered_queries.append(q.query_id)
                # Keep the most specific partial condition if any.
                if not cand.partial_condition and q.partial_condition:
                    cand.partial_condition = q.partial_condition
        return list(by_key.values())

    @staticmethod
    def _reason(q: Query) -> str:
        parts = []
        for f in q.fields:
            parts.append(f"{f.name}({f.search_type},sel={f.selectivity:.2f})")
        return "ESR + selectivity ordering of " + ", ".join(parts)
