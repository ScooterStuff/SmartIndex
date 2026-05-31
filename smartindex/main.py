"""SmartIndex command-line entry point.

Usage::

    python -m smartindex.main path/to/queries.csv
    python -m smartindex.main path/to/queries.csv --mongo-uri mongodb://localhost:27017 \\
        --db testdb --collection orders --test
"""

from __future__ import annotations

import argparse
import sys

from .csv_reader import CSVReader
from .encoder import Encoder
from .graph_ordering import GraphOrderer
from .index_generator import IndexGenerator
from .minset import MinSetOptimiser
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
    return p


def _connect(uri: str, db: str, coll: str):
    try:
        from pymongo import MongoClient
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("pymongo is required for --mongo-uri") from exc
    return MongoClient(uri)[db][coll]


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
                # Pick the first query this index covers for the explain run.
                qid = cand.covered_queries[0]
                source_query = next(q for q in encoded if q.query_id == qid)
                # Decode field names for the real query.
                decoded_query = source_query
                for f in decoded_query.fields:
                    f.name = encoder.decode_field(f.name)
                metrics[tuple(cand.fields)] = tester.explain_query(decoded_query)
        finally:
            for name in created:
                tester.drop_index(name)

    coll_name = args.collection or "collection"
    print(ReportGenerator(encoder).render(final, collection_name=coll_name, metrics=metrics))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run())
