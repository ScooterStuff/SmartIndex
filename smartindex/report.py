"""Human-readable report for SmartIndex recommendations."""

from __future__ import annotations

from typing import Iterable, Optional

from .encoder import Encoder
from .models import IndexCandidate


class ReportGenerator:
    def __init__(self, encoder: Encoder):
        self.encoder = encoder

    # ------------------------------------------------------------------ #

    def render(
        self,
        indexes: list[IndexCandidate],
        *,
        collection_name: str = "collection",
        metrics: Optional[dict[tuple[str, ...], dict]] = None,
    ) -> str:
        lines: list[str] = []
        lines.append("=" * 72)
        lines.append(f"SmartIndex recommendations ({len(indexes)} index(es))")
        lines.append("=" * 72)
        for i, cand in enumerate(indexes, 1):
            decoded = self.encoder.decode_index(cand.fields)
            lines.append("")
            lines.append(f"[{i}] {self._mongo_create(collection_name, decoded, cand)}")
            lines.append(f"    encoded fields : {cand.fields}")
            lines.append(f"    queries covered: {sorted(cand.covered_queries)}")
            if cand.partial_condition:
                lines.append(f"    partial        : {cand.partial_condition}")
            if cand.reason:
                lines.append(f"    reason         : {cand.reason}")
            if metrics and tuple(cand.fields) in metrics:
                m = metrics[tuple(cand.fields)]
                lines.append("    perf:")
                for k, v in m.items():
                    lines.append(f"        {k}: {v}")
        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #

    @staticmethod
    def _mongo_create(
        collection_name: str,
        decoded_fields: Iterable[str],
        cand: IndexCandidate,
    ) -> str:
        body = ", ".join(f'"{f}": 1' for f in decoded_fields)
        opts = ""
        if cand.partial_condition:
            opts = f', {{ name: "si_{"_".join(cand.fields)}" }}'
        return f"db.{collection_name}.createIndex({{ {body} }}{opts})"
