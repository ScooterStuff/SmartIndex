from smartindex.minset import MinSetOptimiser
from smartindex.models import IndexCandidate


def _c(fields, qid):
    return IndexCandidate(fields=list(fields), covered_queries=[qid])


def test_prefix_absorption():
    opt = MinSetOptimiser()
    result = opt.optimise(
        [
            _c(["a"], 1),
            _c(["a", "b"], 2),
            _c(["a", "b", "c"], 3),
            _c(["d", "e"], 4),
        ]
    )
    keys = sorted(tuple(c.fields) for c in result)
    assert keys == [("a", "b", "c"), ("d", "e")]
    longest = next(c for c in result if c.fields == ["a", "b", "c"])
    # All three query IDs should now be covered by the surviving index.
    assert sorted(longest.covered_queries) == [1, 2, 3]


def test_non_prefix_kept():
    opt = MinSetOptimiser()
    result = opt.optimise([_c(["a", "c", "b"], 1), _c(["a", "b"], 2)])
    keys = sorted(tuple(c.fields) for c in result)
    assert keys == [("a", "b"), ("a", "c", "b")]


def test_no_short_prefix_removed_when_unrelated():
    opt = MinSetOptimiser()
    result = opt.optimise([_c(["b", "c"], 1), _c(["a", "b", "c"], 2)])
    keys = sorted(tuple(c.fields) for c in result)
    assert keys == [("a", "b", "c"), ("b", "c")]
