"""Optional MongoDB .explain() based tester for generated indexes."""

from __future__ import annotations

from typing import Any, Optional

from .models import IndexCandidate, Query


class MongoTester:
    """Create indexes, run representative queries, collect metrics.

    The tester is optional; it requires ``pymongo`` and a running MongoDB.
    """

    def __init__(self, collection) -> None:
        self.collection = collection

    # ------------------------------------------------------------------ #

    def create_index(self, candidate: IndexCandidate) -> str:
        keys = [(f, 1) for f in candidate.fields]
        kwargs: dict[str, Any] = {"name": "si_" + "_".join(candidate.fields)}
        if candidate.partial_condition:
            pf = self._partial_filter(candidate.partial_condition)
            if pf:
                kwargs["partialFilterExpression"] = pf
        return self.collection.create_index(keys, **kwargs)

    def drop_index(self, name: str) -> None:
        try:
            self.collection.drop_index(name)
        except Exception:  # pragma: no cover
            pass

    # ------------------------------------------------------------------ #

    def explain_query(self, query: Query) -> dict[str, Any]:
        mongo_filter = self._build_filter(query)
        cursor = self.collection.find(mongo_filter)
        if query.limit:
            cursor = cursor.limit(query.limit)
        plan = cursor.explain()
        exec_stats = plan.get("executionStats", {})
        winning = (
            plan.get("queryPlanner", {}).get("winningPlan", {})
        )
        return {
            "filter": mongo_filter,
            "executionTimeMillis": exec_stats.get("executionTimeMillis"),
            "totalKeysExamined": exec_stats.get("totalKeysExamined"),
            "totalDocsExamined": exec_stats.get("totalDocsExamined"),
            "indexName": self._extract_index_name(winning),
            "winningPlanStage": winning.get("stage"),
        }

    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_filter(query: Query) -> dict[str, Any]:
        mongo_filter: dict[str, Any] = {}
        for f in query.fields:
            if f.search_type == "E":
                mongo_filter[f.name] = {"$exists": True}
            elif f.search_type == "R":
                mongo_filter[f.name] = {"$gte": 0}
            # "S" handled via sort; ignored in filter.
        return mongo_filter

    @staticmethod
    def _partial_filter(raw: str) -> Optional[dict[str, Any]]:
        # Best-effort parse of "field/op/value" tokens; unknown forms are skipped.
        out: dict[str, Any] = {}
        for tok in raw.split(","):
            parts = tok.strip().split("/")
            if len(parts) != 3:
                continue
            field, op, val = parts
            op_map = {
                "gt": "$gt",
                "gte": "$gte",
                "lt": "$lt",
                "lte": "$lte",
                "eq": "$eq",
                "ne": "$ne",
            }
            mop = op_map.get(op.lower())
            if not mop:
                continue
            try:
                cast: Any = float(val)
                if cast.is_integer():
                    cast = int(cast)
            except ValueError:
                cast = val
            out[field] = {mop: cast}
        return out or None

    @staticmethod
    def _extract_index_name(stage: dict[str, Any]) -> Optional[str]:
        if not stage:
            return None
        if "indexName" in stage:
            return stage["indexName"]
        for child_key in ("inputStage", "inputStages"):
            child = stage.get(child_key)
            if isinstance(child, dict):
                name = MongoTester._extract_index_name(child)
                if name:
                    return name
            elif isinstance(child, list):
                for c in child:
                    name = MongoTester._extract_index_name(c)
                    if name:
                        return name
        return None
