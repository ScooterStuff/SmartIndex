"""CSV reader: parse query-pattern CSV into Query objects."""

from __future__ import annotations

import csv
import re
from typing import Iterable, Optional

from .models import Query, QueryField


def _norm(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = value.strip()
    if v == "" or v.lower() == "none":
        return None
    return v


def _split_csv_list(raw: str) -> list[str]:
    """Split a comma-separated list while respecting [..] groupings."""
    items: list[str] = []
    buf = ""
    depth = 0
    for ch in raw:
        if ch == "[":
            depth += 1
            buf += ch
        elif ch == "]":
            depth -= 1
            buf += ch
        elif ch == "," and depth == 0:
            items.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        items.append(buf.strip())
    return items


def _parse_range_criteria(raw: Optional[str]) -> dict[str, str]:
    """Parse "balance=5000,age=10" or "date eq 10" into {field: criteria}."""
    out: dict[str, str] = {}
    if not raw:
        return out
    for token in _split_csv_list(raw):
        token = token.strip()
        if not token:
            continue
        m = re.match(r"^([A-Za-z_][\w\.]*)\s*(=|eq|gte|lte|gt|lt)\s*(.+)$", token)
        if m:
            field_name, op, val = m.groups()
            out[field_name] = f"{op} {val}".strip()
        else:
            out[token] = token
    return out


class CSVReader:
    """Read SmartIndex CSV input.

    Expected columns (case/space tolerant):
        Search/Combination, ESR, Range Criteria, Partial, Sorting Logic, Limit
    """

    REQUIRED = {"search/combination", "esr"}

    def __init__(self, csv_path: str):
        self.csv_path = csv_path

    def read(self) -> list[Query]:
        with open(self.csv_path, "r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            normalised: list[dict[str, str]] = []
            for row in reader:
                normalised.append(
                    {(k or "").strip().lower(): (v or "") for k, v in row.items()}
                )

        if not normalised:
            return []

        missing = self.REQUIRED - set(normalised[0].keys())
        if missing:
            raise ValueError(f"CSV missing required columns: {sorted(missing)}")

        queries: list[Query] = []
        next_id = 1
        for row in normalised:
            for q in self._parse_row(row, start_id=next_id):
                queries.append(q)
                next_id = q.query_id + 1
        return queries

    # ------------------------------------------------------------------ #

    def _parse_row(self, row: dict[str, str], start_id: int) -> Iterable[Query]:
        combo_raw = row.get("search/combination", "").strip()
        esr_raw = row.get("esr", "").strip()
        if not combo_raw or not esr_raw:
            return []

        range_map = _parse_range_criteria(_norm(row.get("range criteria")))
        partial = _norm(row.get("partial"))
        sorting = _norm(row.get("sorting logic"))
        limit_raw = _norm(row.get("limit"))
        try:
            limit = int(limit_raw) if limit_raw else None
        except ValueError:
            limit = None

        # Expand `[or]` alternations into separate queries.
        combo_variants = self._expand_or(combo_raw)
        esr_variants = self._expand_or(esr_raw)
        if len(combo_variants) != len(esr_variants):
            # Fall back to single variant if structure mismatches.
            combo_variants = [combo_raw.replace("[or]", ",")]
            esr_variants = [esr_raw.replace("[or]", ",")]

        out: list[Query] = []
        qid = start_id
        for combo, esr in zip(combo_variants, esr_variants):
            fields_raw = [f.strip() for f in _split_csv_list(combo) if f.strip()]
            esr_tokens = [e.strip().upper() for e in _split_csv_list(esr) if e.strip()]
            if len(fields_raw) != len(esr_tokens):
                continue
            qfields: list[QueryField] = []
            for name, st in zip(fields_raw, esr_tokens):
                if st not in {"E", "S", "R"}:
                    st = "E"
                qfields.append(
                    QueryField(
                        name=name,
                        search_type=st,
                        range_criteria=range_map.get(name),
                        partial_condition=partial,
                    )
                )
            out.append(
                Query(
                    query_id=qid,
                    fields=qfields,
                    partial_condition=partial,
                    limit=limit,
                    sorting_logic=sorting,
                )
            )
            qid += 1
        return out

    @staticmethod
    def _expand_or(raw: str) -> list[str]:
        """Expand `[or]` blocks and `[a,b]` alternation groups.

        Examples
        --------
        "city, age [or] fav"  -> ["city, age", "city, fav"]
        "E, [R,R]"            -> ["E, R", "E, R"]
        """
        # Handle bracket groups by treating each comma-separated item inside
        # `[...]` as a distinct alternative occupying one slot.
        if "[or]" in raw:
            # Split tokens, then expand the token containing "<a> [or] <b>".
            tokens = _split_csv_list(raw)
            variants: list[list[str]] = [[]]
            for tok in tokens:
                if "[or]" in tok:
                    options = [o.strip() for o in tok.split("[or]")]
                    new_variants: list[list[str]] = []
                    for v in variants:
                        for opt in options:
                            new_variants.append(v + [opt])
                    variants = new_variants
                else:
                    for v in variants:
                        v.append(tok)
            return [", ".join(v) for v in variants]

        if "[" in raw and "]" in raw:
            tokens = _split_csv_list(raw)
            variants: list[list[str]] = [[]]
            for tok in tokens:
                m = re.match(r"^\[(.+)\]$", tok)
                if m:
                    options = [o.strip() for o in m.group(1).split(",")]
                    new_variants = []
                    for v in variants:
                        for opt in options:
                            new_variants.append(v + [opt])
                    variants = new_variants
                else:
                    for v in variants:
                        v.append(tok)
            return [", ".join(v) for v in variants]

        return [raw]
