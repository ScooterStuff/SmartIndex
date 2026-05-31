"""SmartIndex command-line entry point.

Usage::

    python -m smartindex.main path/to/queries.csv
    python -m smartindex.main path/to/queries.csv --mongo-uri mongodb://localhost:27017 \\
        --db testdb --collection orders --test
    python -m smartindex.main path/to/queries.csv ... --test \\
        -kt --kt-distance 2 -gr --gr-degradation 0.1
"""

from __future__ import annotations

import argparse
import sys

from .csv_reader import CSVReader
from .encoder import Encoder
from .graph_ordering import GraphOrderer
from .index_generator import IndexGenerator
from .minset import MinSetOptimiser
from .models import IndexCandidate, Query, QueryField
from .report import ReportGenerator
from .selectivity_calculator import SelectivityCalculator


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="smartindex",
        description="Recommend MongoDB composite indexes from a query CSV.",
    )
    p.add_argument("csv_path", help="Path to the query CSV")
    p.add_argument("--mongo-uri", default=None, help="Optional MongoDB connection URI")
    p.add_argument("--db", default=None, help="MongoDB database name")
    p.add_argument("--collection", default=None, help="MongoDB collection name")
    p.add_argument(
        "--test",
        action="store_true",
        help="Create recommended indexes and run .explain() metrics",
    )
    # Optional add-on validators - opt-in, off by default.
    p.add_argument(
        "-kt",
        "--kendall-tau",
        action="store_true",
        help="(optional) validate field order via Kendall-Tau exploration",
    )
    p.add_argument("--kt-distance", type=int, default=2,
                   help="Max Kendall-Tau distance to explore (default: 2)")
    p.add_argument("--kt-max-perms", type=int, default=50,
                   help="Max permutations to test per index (default: 50)")
    p.add_argument(
        "-gr",
        "--greedy-remove",
        action="store_true",
        help="(optional) greedy trailing-field removal with degradation budget",
    )
    p.add_argument("--gr-degradation", type=float, default=0.10,
                   help="Greedy remover max allowed degradation (default: 0.10)")
    p.add_argument("--gr-min-length", type=int, default=1,
                   help="Greedy remover min index length (default: 1)")
    return p


def _connect(uri: str, db: str, coll: str):
    try:
        from pymongo import MongoClient
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("pymongo is required for --mongo-uri") from exc
    return MongoClient(uri)[db][coll]


def _decode_query(q: Query, encoder: Encoder) -> Query:
    return Query(
        query_id=q.query_id,
        fields=[
            QueryField(
                name=encoder.decode_field(f.name),
                search_type=f.search_type,
                range_criteria=f.range_criteria,
                partial_condition=f.partial_condition,
                selectivity=f.selectivity,
            )
            for f in q.fields
        ],
        partial_condition=q.partial_condition,
        limit=q.limit,
        sorting_logic=q.sorting_logic,
    )


def _representative_queries(
    finals: list[IndexCandidate], encoded: list[Query], encoder: Encoder
) -> list[Query]:
    by_id = {q.query_id: q for q in encoded}
    out: list[Query] = []
    seen: set[int] = set()
    for cand in finals:
        for qid in cand.covered_queries:
            if qid in seen:
                continue
            q = by_id.get(qid)
            if not q:
                continue
            seen.add(qid)
            out.append(_decode_query(q, encoder))
            break
    return out


def run(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    collection = None
    if args.mongo_uri and args.db and args.collection:
        collection = _connect(args.mongo_uri, args.db, args.collection)

    queries = CSVReader(args.csv_path).read()
    if not queries:
        print("No queries parsed from CSV.", file=sys.stderr)
        return 1

    encoder = Encoder()
    encoded = encoder.encode_queries(queries)

    SelectivityCalculator(collection=collection).annotate(encoded)
    candidates = IndexGenerator(GraphOrderer()).generate(encoded)
    final = MinSetOptimiser().optimise(candidates)

    metrics = None
    if args.test and collection is not None:
        from .mongo_tester import MongoTester

        tester = MongoTester(collection)
        metrics = {}
        created: list[str] = []
        try:
            for cand in final:
                created.append(tester.create_index(cand))
            for cand in final:
                qid = cand.covered_queries[0]
                source_query = next(q for q in encoded if q.query_id == qid)
                decoded_query = _decode_query(source_query, encoder)
                metrics[tuple(cand.fields)] = tester.explain_query(decoded_query)
        finally:
            for name in created:
                tester.drop_index(name)

    # ---------------------------------------------------------------- #
    # Optional add-on validators
    if (args.kendall_tau or args.greedy_remove) and collection is None:
        print(
            "Add-on validators require --mongo-uri/--db/--collection; skipping.",
            file=sys.stderr,
        )

    if args.kendall_tau and collection is not None:
        from .kendall_tau_explorer import KendallTauExplorer, make_explain_scorer

        scorer = make_explain_scorer(collection)
        explorer = KendallTauExplorer(
            scorer,
            max_distance=args.kt_distance,
            max_permutations=args.kt_max_perms,
        )
        rep_queries = _representative_queries(final, encoded, encoder)
        improved = 0
        for cand, rq in zip(final, rep_queries):
            decoded_cand = IndexCandidate(
                fields=encoder.decode_index(cand.fields),
                covered_queries=list(cand.covered_queries),
                partial_condition=cand.partial_condition,
                reason=cand.reason,
            )
            res = explorer.explore(decoded_cand, [rq])
            if res.changed:
                cand.fields = [encoder.encode_field(n) for n in res.best_index]
                cand.reason += f" (KT improved by {res.improvement:.0f})"
                improved += 1
        print(
            f"Kendall-Tau explorer: {len(final)} index(es) validated, "
            f"{improved} reordered."
        )

    if args.greedy_remove and collection is not None:
        from .greedy_remover import GreedyRemover, make_explain_set_scorer

        rep_queries = _representative_queries(final, encoded, encoder)
        decoded_candidates = [
            IndexCandidate(
                fields=encoder.decode_index(c.fields),
                covered_queries=list(c.covered_queries),
                partial_condition=c.partial_condition,
                reason=c.reason,
            )
            for c in final
        ]
        scorer = make_explain_set_scorer(collection)
        remover = GreedyRemover(
            scorer,
            max_allowed_degradation=args.gr_degradation,
            min_index_length=args.gr_min_length,
        )
        result = remover.optimise(decoded_candidates, rep_queries)
        print(
            f"Greedy remover: {len(decoded_candidates)} -> "
            f"{len(result.final_indexes)} index(es), "
            f"degradation {result.degradation*100:+.1f}%"
        )
        new_final: list[IndexCandidate] = []
        for fields in result.final_indexes:
            encoded_fields = [encoder.encode_field(n) for n in fields]
            matched = next(
                (
                    c
                    for c in final
                    if c.fields[: len(encoded_fields)] == encoded_fields
                ),
                None,
            )
            new_final.append(
                IndexCandidate(
                    fields=encoded_fields,
                    covered_queries=list(matched.covered_queries) if matched else [],
                    partial_condition=matched.partial_condition if matched else None,
                    reason=(matched.reason if matched else "") + " (greedy-trimmed)",
                )
            )
        final = new_final

    coll_name = args.collection or "collection"
    print(
        ReportGenerator(encoder).render(
            final, collection_name=coll_name, metrics=metrics
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run())
