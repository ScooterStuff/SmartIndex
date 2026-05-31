"""Field-name encoder/decoder.

Long field names (e.g. ``MIFMP.LclRef``) are mapped to short symbols
(``a``, ``b``, ``c`` …) so the graph and trie stages stay compact and easy
to debug.  The same mapping is used to decode results back to MongoDB
field names.
"""

from __future__ import annotations

from string import ascii_lowercase
from typing import Iterable

from .models import Query, QueryField


class Encoder:
    def __init__(self) -> None:
        self.encode_map: dict[str, str] = {}  # original -> short
        self.decode_map: dict[str, str] = {}  # short    -> original
        self._counter = 0

    # ------------------------------------------------------------------ #

    def _next_symbol(self) -> str:
        # a, b, ..., z, aa, ab, ...
        n = self._counter
        self._counter += 1
        chars = []
        while True:
            chars.append(ascii_lowercase[n % 26])
            n = n // 26 - 1
            if n < 0:
                break
        return "".join(reversed(chars))

    def encode_field(self, name: str) -> str:
        if name not in self.encode_map:
            sym = self._next_symbol()
            self.encode_map[name] = sym
            self.decode_map[sym] = name
        return self.encode_map[name]

    def decode_field(self, sym: str) -> str:
        return self.decode_map.get(sym, sym)

    # ------------------------------------------------------------------ #

    def encode_queries(self, queries: Iterable[Query]) -> list[Query]:
        """Return new Query objects with field names replaced by short symbols."""
        out: list[Query] = []
        for q in queries:
            new_fields = [
                QueryField(
                    name=self.encode_field(f.name),
                    search_type=f.search_type,
                    range_criteria=f.range_criteria,
                    partial_condition=f.partial_condition,
                    selectivity=f.selectivity,
                )
                for f in q.fields
            ]
            out.append(
                Query(
                    query_id=q.query_id,
                    fields=new_fields,
                    partial_condition=q.partial_condition,
                    limit=q.limit,
                    sorting_logic=q.sorting_logic,
                )
            )
        return out

    def decode_index(self, index: Iterable[str]) -> list[str]:
        return [self.decode_field(s) for s in index]
