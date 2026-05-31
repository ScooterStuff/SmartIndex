"""Trie-based MinSet optimiser.

Removes any candidate index that is an exact leftmost prefix of a longer
candidate index.  Non-prefix overlaps (different field order) are kept,
because MongoDB cannot serve them from the longer index.
"""

from __future__ import annotations

from .models import IndexCandidate


class _Node:
    __slots__ = ("children", "candidate")

    def __init__(self) -> None:
        self.children: dict[str, "_Node"] = {}
        self.candidate: IndexCandidate | None = None


class MinSetOptimiser:
    def optimise(self, candidates: list[IndexCandidate]) -> list[IndexCandidate]:
        if not candidates:
            return []

        # Insert every candidate into the trie.
        root = _Node()
        # Sort by length asc so when duplicates collide we preserve the earliest.
        for cand in sorted(candidates, key=lambda c: len(c.fields)):
            node = root
            for f in cand.fields:
                node = node.children.setdefault(f, _Node())
            if node.candidate is None:
                node.candidate = cand
            else:
                # Merge coverage if same path was inserted twice.
                for qid in cand.covered_queries:
                    if qid not in node.candidate.covered_queries:
                        node.candidate.covered_queries.append(qid)

        # Walk trie: keep candidates only at leaf-most positions on each path,
        # propagating coverage upward so dropped prefixes aren't forgotten.
        kept: list[IndexCandidate] = []
        self._collect(root, kept)
        # Sort output for deterministic display.
        kept.sort(key=lambda c: c.fields)
        return kept

    def _collect(self, node: _Node, out: list[IndexCandidate]) -> None:
        if not node.children:
            if node.candidate is not None:
                out.append(node.candidate)
            return

        # First, recurse into children to gather their kept candidates.
        child_kept_before = len(out)
        for child in node.children.values():
            self._collect(child, out)

        if node.candidate is not None:
            # This prefix is covered by every kept descendant ⇒ propagate
            # query coverage and drop the shorter index.
            descendants = out[child_kept_before:]
            if descendants:
                for d in descendants:
                    for qid in node.candidate.covered_queries:
                        if qid not in d.covered_queries:
                            d.covered_queries.append(qid)
                    if not d.reason.endswith("(absorbs prefix)"):
                        d.reason = (d.reason + " (absorbs prefix)").strip()
            else:
                out.append(node.candidate)
