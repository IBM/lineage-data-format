"""resource_key: the decoder only emits the key when the input had a value."""

import json
from pathlib import Path

import pytest  # type: ignore

from ldf import json_to_lineage_format, lineage_format_to_json

ROOT = Path(__file__).resolve().parent.parent
BIG = ROOT / "big_query_lineage.json"


def graph(*assets):
    return {"assets_in_view": list(assets), "edges_in_view": []}


def roundtrip(g, aliases=True):
    return lineage_format_to_json(json_to_lineage_format(g, {"aliases": aliases}))


@pytest.mark.parametrize("aliases", [True, False])
class TestResourceKey:
    def test_missing_key_stays_missing(self, aliases):
        a = roundtrip(graph({"id": "a", "name": "x", "type": "Column"}), aliases)["assets_in_view"][0]
        assert "resource_key" not in a

    def test_value_is_kept(self, aliases):
        a = roundtrip(graph({"id": "a", "name": "x", "type": "Column", "resource_key": "DB/s/t/c"}), aliases)
        assert a["assets_in_view"][0]["resource_key"] == "DB/s/t/c"

    def test_mixed_assets(self, aliases):
        r = roundtrip(graph(
            {"id": "a", "name": "x", "type": "Column", "resource_key": "DB/a"},
            {"id": "b", "name": "y", "type": "Column"},
        ), aliases)["assets_in_view"]
        assert r[0]["resource_key"] == "DB/a"
        assert "resource_key" not in r[1]

    def test_excluded_resource_key_is_absent(self, aliases):
        g = graph({"id": "a", "name": "x", "type": "Column", "resource_key": "DB/a"})
        text = json_to_lineage_format(g, {"aliases": aliases, "exclude_fields": ["resource_key"]})
        assert "resource_key" not in lineage_format_to_json(text)["assets_in_view"][0]


@pytest.mark.skipif(not BIG.exists(), reason="big_query_lineage.json not present")
@pytest.mark.parametrize("aliases", [True, False])
def test_big_query_assets_are_strictly_equal_after_roundtrip(aliases):
    data = json.loads(BIG.read_text(encoding="utf-8"))
    assert roundtrip(data, aliases)["assets_in_view"] == data["assets_in_view"]
