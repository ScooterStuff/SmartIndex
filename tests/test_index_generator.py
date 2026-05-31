"""Tests for the full index-construction pipeline.

Covers:
  * GraphOrderer + IndexGenerator producing one candidate per query
  * Deduplication / coverage merging across queries
  * MinSetOptimiser absorbing exact prefixes
  * Non-prefix indexes being preserved
  * End-to-end run from CSV to final indexes
"""

from pathlib import Path

from smartindex.csv_reader import CSVReader
from smartindex.encoder import Encoder
from smartindex.graph_ordering import GraphOrderer
from smartindex.index_generator import IndexGenerator
from smartindex.minset import MinSetOptimiser
from smartindex.models import Query, QueryField
from smartindex.selectivity_calculator import SelectivityCalculator


def _q(qid, *fs, **kw):
    fields = [QueryField(name, st, selectivity=sel) for name, st, sel in fs]
    return Query(query_id=qid, fields=fields, **kw)


# --------------------------------------------------------------------- #
# IndexGenerator behaviour

def test_generator_produces_one_candidate_per_unique_order():
    queries = [
        _q(1, ("a", "E", 5.0), ("b", "R", 3.0)),
        _q(2, ("a", "E", 5.0), ("b", "R", 3.0)),  # duplicate
        _q(3, ("c", "E", 4.0), ("d", "R", 2.0)),
    ]
    candidates = IndexGenerator().generate(queries)

    keys = sorted(tuple(c.fields) for c in candidates)
    assert keys == [("a", "b"), ("c", "d")]

    ab = next(c for c in candidates if c.fields == ["a", "b"])
    assert sorted(ab.covered_queries) == [1, 2]


def test_generator_respects_esr_order():
    # Range field provided first; generator must move it to the end.
    q = _q(1, ("r", "R", 8.0), ("e", "E", 1.0))
    [cand] = IndexGenerator().generate([q])
    assert cand.fields == ["e", "r"]


def test_generator_orders_equality_by_selectivity():
    q = _q(1, ("low", "E", 1.0), ("hi", "E", 9.0), ("mid", "E", 5.0))
    [cand] = IndexGenerator().generate([q])
    assert cand.fields == ["hi", "mid", "low"]


def test_generator_preserves_partial_condition():
    q = _q(1, ("a", "E", 5.0), partial_condition="a/gt/0")
    [cand] = IndexGenerator().generate([q])
    assert cand.partial_condition == "a/gt/0"


# --------------------------------------------------------------------- #
# MinSet absorption interacting with the generator

def test_pipeline_absorbs_prefix_indexes():
    queries = [
        _q(1, ("a", "E", 9.0)),
        _q(2, ("a", "E", 9.0), ("b", "E", 5.0)),
        _q(3, ("a", "E", 9.0), ("b", "E", 5.0), ("c", "R", 2.0)),
    ]
    final = MinSetOptimiser().optimise(IndexGenerator().generate(queries))

    assert len(final) == 1
    assert final[0].fields == ["a", "b", "c"]
    assert sorted(final[0].covered_queries) == [1, 2, 3]


def test_pipeline_keeps_divergent_orderings():
    # Same fields, different ESR types ⇒ different generated orderings ⇒
    # neither index is a prefix of the other and both must be kept.
    queries = [
        _q(1, ("a", "E", 5.0), ("b", "R", 5.0)),  # → [a, b]
        _q(2, ("a", "R", 5.0), ("b", "E", 5.0)),  # → [b, a]
    ]
    final = MinSetOptimiser().optimise(IndexGenerator().generate(queries))
    keys = sorted(tuple(c.fields) for c in final)
    assert keys == [("a", "b"), ("b", "a")]


# --------------------------------------------------------------------- #
# End-to-end through the CSV pipeline

def test_end_to_end_test_query_csv():
    csv_path = Path(__file__).resolve().parents[1] / "test_query.csv"
    queries = CSVReader(str(csv_path)).read()

    encoder = Encoder()
    encoded = encoder.encode_queries(queries)
    SelectivityCalculator().annotate(encoded)

    candidates = IndexGenerator().generate(encoded)
    final = MinSetOptimiser().optimise(candidates)

    # Every produced index is non-empty and every covered query exists.
    assert final, "expected at least one index"
    qids = {q.query_id for q in encoded}
    covered: set[int] = set()
    for cand in final:
        assert cand.fields, "index must have at least one field"
        covered.update(cand.covered_queries)

    # Every input query must be covered by at least one recommended index.
    assert covered == qids

    # ESR rule: in every index, no Equality field appears after a Range field.
    field_type = {f.name: f.search_type for q in encoded for f in q.fields}
    for cand in final:
        seen_range = False
        for fname in cand.fields:
            st = field_type.get(fname)
            if st == "R":
                seen_range = True
            elif st == "E" and seen_range:
                raise AssertionError(
                    f"Equality field {fname!r} appears after a Range field in {cand.fields}"
                )


def test_end_to_end_decodes_field_names():
    csv_path = Path(__file__).resolve().parents[1] / "test_query.csv"
    queries = CSVReader(str(csv_path)).read()
    original_names = {f.name for q in queries for f in q.fields}

    encoder = Encoder()
    encoded = encoder.encode_queries(queries)
    SelectivityCalculator().annotate(encoded)
    final = MinSetOptimiser().optimise(IndexGenerator().generate(encoded))

    for cand in final:
        decoded = encoder.decode_index(cand.fields)
        assert all(name in original_names for name in decoded)
