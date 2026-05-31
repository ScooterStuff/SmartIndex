"""Core data models for SmartIndex."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class QueryField:
    """One field used inside a query."""

    name: str
    search_type: str  # "E" (equality), "S" (sort), or "R" (range)
    range_criteria: Optional[str] = None
    partial_condition: Optional[str] = None
    selectivity: float = 0.0

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"QF({self.name},{self.search_type},sel={self.selectivity:.2f})"


@dataclass
class Query:
    """One row from the CSV - one application query pattern."""

    query_id: int
    fields: list[QueryField]
    partial_condition: Optional[str] = None
    limit: Optional[int] = None
    sorting_logic: Optional[str] = None

    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]


@dataclass
class IndexCandidate:
    """A generated composite index in field order."""

    fields: list[str]
    covered_queries: list[int] = field(default_factory=list)
    partial_condition: Optional[str] = None
    reason: str = ""

    def key(self) -> tuple[str, ...]:
        return tuple(self.fields)
