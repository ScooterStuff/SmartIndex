from pathlib import Path

from smartindex.csv_reader import CSVReader


def test_reads_test_query_csv():
    csv_path = Path(__file__).resolve().parents[1] / "test_query.csv"
    queries = CSVReader(str(csv_path)).read()
    assert queries, "expected at least one query"

    first = queries[0]
    assert [f.name for f in first.fields] == ["balance", "name", "string"]
    assert [f.search_type for f in first.fields] == ["R", "E", "E"]
    assert first.limit == 200


def test_or_expansion(tmp_path):
    csv = tmp_path / "q.csv"
    csv.write_text(
        "Search/Combination,ESR,Range Criteria,Partial,Sorting Logic,Limit\n"
        '"city, age [or] fav","E, [R,R]","age=20,fav=10","age/lt/120","","200"\n',
        encoding="utf-8",
    )
    queries = CSVReader(str(csv)).read()
    assert len(queries) == 2
    assert [f.name for f in queries[0].fields] == ["city", "age"]
    assert [f.name for f in queries[1].fields] == ["city", "fav"]
