from smartindex.encoder import Encoder
from smartindex.models import Query, QueryField


def test_encode_decode_roundtrip():
    q = Query(
        query_id=1,
        fields=[QueryField("MIFMP.LclRef", "E"), QueryField("MIFMP.CreDteNtv", "R")],
    )
    enc = Encoder()
    [encoded] = enc.encode_queries([q])
    syms = [f.name for f in encoded.fields]
    assert syms == ["a", "b"]
    assert enc.decode_index(syms) == ["MIFMP.LclRef", "MIFMP.CreDteNtv"]
