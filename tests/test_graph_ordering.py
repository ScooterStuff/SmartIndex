from smartindex.graph_ordering import GraphOrderer
from smartindex.models import Query, QueryField


def test_equality_before_range():
    q = Query(
        query_id=1,
        fields=[
            QueryField("a", "R", selectivity=6.8),
            QueryField("b", "E", selectivity=3.0),
            QueryField("c", "E", selectivity=7.9),
        ],
    )
    order = GraphOrderer().order_fields(q)
    # range field must come last; higher-selectivity equality first.
    assert order[-1] == "a"
    assert order[:2] == ["c", "b"]


def test_sort_between_equality_and_range():
    q = Query(
        query_id=2,
        fields=[
            QueryField("r", "R", selectivity=5.0),
            QueryField("s", "S", selectivity=5.0),
            QueryField("e", "E", selectivity=5.0),
        ],
    )
    assert GraphOrderer().order_fields(q) == ["e", "s", "r"]
