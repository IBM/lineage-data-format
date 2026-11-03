"""descendant_statistics survives the LDF round-trip (token ds / dsl,dse,dsn / dsj)."""

import json
from pathlib import Path

import pytest

from ldf import json_to_lineage_format, lineage_format_to_json

FULL = {"has_leaf_children": True, "is_every_child_leaf": False, "number_of_leaf_descendants": 7}


def asset(i, **extra):
    a = {"id": f"id-{i}", "name": f"n{i}", "type": "Column"}
    a.update(extra)
    return a


def graph(*assets):
    return {"assets_in_view": list(assets), "edges_in_view": []}


def roundtrip(g, aliases=True, exclude=None):
    opts = {"aliases": aliases}
    if exclude:
        opts["exclude_fields"] = exclude
    return lineage_format_to_json(json_to_lineage_format(g, opts))


def ds_of(restored):
    return [a.get("descendant_statistics", "<absent>") for a in restored["assets_in_view"]]


def node_lines(text):
    out, on = [], False
    for line in text.splitlines():
        if line == "N:":
            on = True
        elif on and not line.strip():
            break
        elif on:
            out.append(line)
    return out


@pytest.mark.parametrize("aliases", [True, False])
def test_full_value_round_trips(aliases):
    assert ds_of(roundtrip(graph(asset(1, descendant_statistics=FULL)), aliases)) == [FULL]


@pytest.mark.parametrize("aliases", [True, False])
def test_missing_field_is_not_invented(aliases):
    assert ds_of(roundtrip(graph(asset(1)), aliases)) == ["<absent>"]


def test_null_field_is_not_invented():
    assert ds_of(roundtrip(graph(asset(1, descendant_statistics=None)))) == ["<absent>"]


def test_mixed_present_and_absent():
    g = graph(asset(1, descendant_statistics=FULL), asset(2), asset(3, descendant_statistics=FULL))
    assert ds_of(roundtrip(g)) == [FULL, "<absent>", FULL]


def test_common_value_goes_to_ndef():
    zero = {"has_leaf_children": False, "is_every_child_leaf": False, "number_of_leaf_descendants": 0}
    g = graph(*[asset(i, descendant_statistics=zero) for i in range(6)])
    text = json_to_lineage_format(g)
    assert "ds=0,0,0" in text.split("NDEF:")[1].split("\n\n")[0]
    assert all(" ds=" not in l for l in node_lines(text))
    assert ds_of(roundtrip(g)) == [zero] * 6


def test_own_value_overrides_ndef():
    zero = {"has_leaf_children": False, "is_every_child_leaf": False, "number_of_leaf_descendants": 0}
    g = graph(*[asset(i, descendant_statistics=zero) for i in range(6)],
              asset(9, descendant_statistics=FULL))
    assert ds_of(roundtrip(g)) == [zero] * 6 + [FULL]


def test_node_without_field_next_to_ndef_default():
    zero = {"has_leaf_children": False, "is_every_child_leaf": False, "number_of_leaf_descendants": 0}
    g = graph(*[asset(i, descendant_statistics=zero) for i in range(6)], asset(9))
    assert ds_of(roundtrip(g)) == [zero] * 6 + ["<absent>"]


def test_exclude_whole_field_leaves_no_trace():
    g = graph(asset(1, descendant_statistics=FULL))
    text = json_to_lineage_format(g, {"exclude_fields": ["descendant_statistics"]})
    assert " ds" not in text
    assert ds_of(lineage_format_to_json(text)) == ["<absent>"]


@pytest.mark.parametrize("field", list(FULL))
def test_exclude_single_subfield(field):
    g = graph(asset(1, descendant_statistics=FULL))
    got = ds_of(roundtrip(g, exclude=[field]))
    assert got == [{k: v for k, v in FULL.items() if k != field}]


def test_exclude_middle_subfield_uses_named_tokens():
    g = graph(asset(1, descendant_statistics=FULL))
    text = json_to_lineage_format(g, {"exclude_fields": ["is_every_child_leaf"]})
    assert " dsl=1" in text and " dsn=7" in text
    assert " ds=" not in text


def test_unknown_key_falls_back_to_json_without_loss():
    odd = dict(FULL, extra="x y,z")
    assert ds_of(roundtrip(graph(asset(1, descendant_statistics=odd)))) == [odd]


def test_unexpected_value_types_fall_back_to_json_without_loss():
    odd = {"has_leaf_children": "yes", "is_every_child_leaf": None, "number_of_leaf_descendants": 1.5}
    assert ds_of(roundtrip(graph(asset(1, descendant_statistics=odd)))) == [odd]


def test_empty_dict_round_trips():
    assert ds_of(roundtrip(graph(asset(1, descendant_statistics={})))) == [{}]


def test_old_ldf_without_token_still_decodes():
    text = json_to_lineage_format(graph(asset(1)))
    assert "ds" not in " ".join(node_lines(text))
    assert ds_of(lineage_format_to_json(text)) == ["<absent>"]


def test_key_order_is_preserved():
    got = ds_of(roundtrip(graph(asset(1, descendant_statistics=FULL))))[0]
    assert list(got) == list(FULL)


BIG = Path(__file__).resolve().parent.parent / "big_query_lineage.json"


@pytest.mark.skipif(not BIG.exists(), reason="big_query_lineage.json not present")
@pytest.mark.parametrize("aliases", [True, False])
def test_big_query_descendant_statistics_round_trip(aliases):
    with open(BIG, encoding="utf-8") as f:
        g = json.load(f)
    restored = roundtrip(g, aliases)
    before = {a["id"]: a["descendant_statistics"] for a in g["assets_in_view"]}
    after = {a["id"]: a.get("descendant_statistics") for a in restored["assets_in_view"]}
    assert after == before
