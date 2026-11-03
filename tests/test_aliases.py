"""
Tests for the alias-compression mechanisms of the LDF format.

The decoder reads hand-written documents that use the new constructs (REF,
IKP, NDEF, "*" defaults, grouped E, default EP). The encoder writes them when
the ``aliases`` option is on (default); ``aliases=False`` / ``--no-aliases``
gives the legacy, fully expanded text.
"""

import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest  # type: ignore

from ldf import json_to_lineage_format, lineage_format_to_json

ROOT = Path(__file__).resolve().parent.parent


def edge_key(e):
    return (e.get("source"), e.get("target"), e.get("type"))


def doc(*blocks):
    return "\n\n".join(blocks)


BASE_ID_NAME = """ID:
N1=id1
N2=id2
N3=id3

NAME:
N1=one
N2=two
N3=three"""


def edge_set(graph):
    return sorted(json.dumps(e, sort_keys=True) for e in graph["edges_in_view"])


def assert_same_graph(a, b):
    """Same assets in the same order, same set of edges (list order may differ)."""
    assert a["assets_in_view"] == b["assets_in_view"]
    assert edge_set(a) == edge_set(b)


def many_assets(n=12):
    """Nodes sharing ik prefix, origin, path, flags, hierarchical path, DSD and
    repeated attributes (in different order), like a real backend response."""
    tech = {"id": "tech-1", "name": "Microsoft SQL Server"}
    dsd = {"id": "dsd-1", "name": "my dsd"}
    hp = [{"id": "h1", "name": "Database", "type": "Database"}]
    shared = [
        {"name": "TRANSFORMATION_TAG", "value": "TRANSFORMING"},
        {"name": "OBJECT_SOURCE_TYPE", "value": "DEDUCTION"},
        {"name": "DEDUCTION_ORIGIN", "value": "Microsoft SQL Server'<6,17>AST_SELECTION'"},
    ]
    assets = []
    for i in range(n):
        attrs = shared[i % 3:] + shared[:i % 3]
        assets.append({
            "id": f"id-{i}", "name": f"Asset {i}", "type": "Block",
            "origin": "design", "technology": tech,
            "identity_key": f"uuid-1/my dsd[Database]/Asset {i}[Block]",
            "is_deduced": True, "is_transforming": True, "is_operational": True,
            "hierarchical_path": hp, "data_source_definition_asset": dsd,
            "attributes": attrs + [{"name": "Block TYPE", "value": "Block"}],
        })
    edges = [{"source": f"id-{i}", "target": f"id-{i + 1}", "type": "direct"} for i in range(n - 1)]
    edges += [{"source": f"id-{i}", "target": f"id-{i + 2}", "type": "direct"} for i in range(n - 2)]
    edges += [{"source": f"id-{i}", "type": "summary"} for i in range(n)]
    return {"assets_in_view": assets, "edges_in_view": edges}


class TestEncoder:
    GRAPH = many_assets()

    def packed(self, **opts):
        return json_to_lineage_format(copy.deepcopy(self.GRAPH), {"aliases": True, **opts})

    def legacy(self, **opts):
        return json_to_lineage_format(copy.deepcopy(self.GRAPH), {"aliases": False, **opts})

    def test_default_is_aliases_on(self):
        assert json_to_lineage_format(copy.deepcopy(self.GRAPH)) == self.packed()

    def test_aliases_off_is_legacy_text(self):
        text = self.legacy()
        for section in ("REF:", "IKP:", "NDEF:"):
            assert section not in text
        assert "etype=direct" in text and "=origin" not in text
        assert re.search(r"^N1>N2$", text, re.M)

    @pytest.mark.parametrize("compact", [False, True])
    def test_roundtrip_matches_legacy_roundtrip(self, compact):
        packed = lineage_format_to_json(self.packed(compact=compact))
        legacy = lineage_format_to_json(self.legacy(compact=compact))
        assert_same_graph(packed, legacy)

    def test_packed_is_much_smaller(self):
        assert len(self.packed()) < len(self.legacy()) * 0.6

    def test_repeated_values_are_written_once(self):
        text = self.packed()
        assert text.count("saas") == 0
        assert text.count("TRANSFORMING") == 1
        assert text.count("Microsoft") <= 2
        assert text.count("etype=direct") == 1
        assert text.count("origin=design") == 1       # in NDEF only
        assert text.count("uuid-1/my%20dsd") == 1     # in IKP only

    def test_sections_present(self):
        text = self.packed()
        for section in ("NDEF:", "IKP:", "REF:"):
            assert section in text
        assert re.search(r"^HP:\n\*=", text, re.M)
        assert re.search(r"^DSD:\n\*=", text, re.M)

    def test_edges_grouped_by_source_and_end_edges_bare(self):
        text = self.packed()
        e = text.split("E:\n", 1)[1].split("\n\n", 1)[0].split("\n")
        assert e[0] == "N1>N2,N3"
        assert len([l for l in e if l == "N1"]) == 1
        assert "*>* etype=direct" in text and "* etype=summary" in text

    def test_ndef_override_and_removal(self):
        g = copy.deepcopy(self.GRAPH)
        g["assets_in_view"][0]["origin"] = "runtime"        # differs from default
        del g["assets_in_view"][1]["origin"]                  # lacks the default token
        g["assets_in_view"][2]["is_deduced"] = False
        g["assets_in_view"][2]["is_transforming"] = False
        g["assets_in_view"][2]["is_operational"] = False      # flags 0, default is 7
        restored = lineage_format_to_json(json_to_lineage_format(g))
        assert_same_graph(restored, lineage_format_to_json(json_to_lineage_format(g, {"aliases": False})))
        a = restored["assets_in_view"]
        assert a[0]["origin"] == "runtime"
        legacy = lineage_format_to_json(json_to_lineage_format(g, {"aliases": False}))
        assert a[1].get("origin") == legacy["assets_in_view"][1].get("origin") != "design"
        assert not a[2]["is_deduced"] and not a[2]["is_operational"]

    def test_node_without_hp_and_dsd_when_others_have_them(self):
        g = copy.deepcopy(self.GRAPH)
        del g["assets_in_view"][3]["hierarchical_path"]
        del g["assets_in_view"][4]["data_source_definition_asset"]
        g["assets_in_view"][5]["hierarchical_path"] = [{"id": "h9", "name": "Other", "type": "Schema"}]
        restored = lineage_format_to_json(json_to_lineage_format(g))
        a = restored["assets_in_view"]
        legacy = lineage_format_to_json(json_to_lineage_format(g, {"aliases": False}))["assets_in_view"]
        assert a[3].get("hierarchical_path") == legacy[3].get("hierarchical_path") != self.GRAPH["assets_in_view"][0]["hierarchical_path"]
        assert a[4].get("data_source_definition_asset") == legacy[4].get("data_source_definition_asset")
        assert a[4].get("data_source_definition_asset") != self.GRAPH["assets_in_view"][0]["data_source_definition_asset"]
        assert a[5]["hierarchical_path"][0]["id"] == "h9"
        assert a[0]["hierarchical_path"] == self.GRAPH["assets_in_view"][0]["hierarchical_path"]

    def test_repeated_edges_between_same_pair_keep_types(self):
        g = copy.deepcopy(self.GRAPH)
        g["edges_in_view"] += [
            {"source": "id-0", "target": "id-1", "type": "summary"},
            {"source": "id-0", "target": "id-1"},
            {"source": "id-0", "target": "id-1", "type": "direct"},
        ]
        restored = lineage_format_to_json(json_to_lineage_format(g))
        assert edge_set(restored) == sorted(json.dumps(e, sort_keys=True) for e in g["edges_in_view"])

    def test_edge_with_unknown_id_survives(self):
        g = copy.deepcopy(self.GRAPH)
        g["edges_in_view"].append({"source": "id-0", "target": "ghost", "type": "direct"})
        restored = lineage_format_to_json(json_to_lineage_format(g))
        assert {"source": "id-0", "target": "ghost", "type": "direct"} in restored["edges_in_view"]

    def test_literal_at_values_are_not_taken_for_references(self):
        g = copy.deepcopy(self.GRAPH)
        for a in g["assets_in_view"]:
            a["attributes"].append({"name": "X", "value": "@R1"})
            a["attributes"].append({"name": "Y", "value": "@R2|@R3"})
        restored = lineage_format_to_json(json_to_lineage_format(g))
        assert_same_graph(restored, lineage_format_to_json(json_to_lineage_format(g, {"aliases": False})))

    def test_values_with_special_characters(self):
        g = copy.deepcopy(self.GRAPH)
        for a in g["assets_in_view"]:
            a["attributes"].append({"name": "Q", "value": "a|b=c d%e\nf:g"})
            a["tags"] = ["x y", "a,b"]
            a["resource_key"] = "rk with space"
        restored = lineage_format_to_json(json_to_lineage_format(g))
        assert_same_graph(restored, lineage_format_to_json(json_to_lineage_format(g, {"aliases": False})))

    def test_single_node_and_empty_graph(self):
        for g in ({"assets_in_view": [], "edges_in_view": []},
                  {"assets_in_view": [self.GRAPH["assets_in_view"][0]], "edges_in_view": []}):
            packed = lineage_format_to_json(json_to_lineage_format(g))
            legacy = lineage_format_to_json(json_to_lineage_format(g, {"aliases": False}))
            assert_same_graph(packed, legacy)

    def test_graph_without_repetition_gets_no_extra_sections(self):
        g = {"assets_in_view": [
            {"id": "a", "name": "A", "type": "T1", "origin": "o1", "identity_key": "k1"},
            {"id": "b", "name": "B", "type": "T2", "origin": "o2", "identity_key": "k2"},
        ], "edges_in_view": [{"source": "a", "target": "b", "type": "direct"}]}
        text = json_to_lineage_format(g)
        for section in ("REF:", "IKP:", "NDEF:"):
            assert section not in text

    def test_decoding_is_stable(self):
        once = lineage_format_to_json(self.packed())
        twice = lineage_format_to_json(json_to_lineage_format(once))
        assert_same_graph(once, twice)


@pytest.mark.parametrize("name", ["out.json", "big_query_lineage.json"])
class TestRealFiles:
    def load(self, name):
        path = ROOT / name
        if not path.exists():
            pytest.skip(f"{name} not available")
        return json.loads(path.read_text())

    def test_roundtrip_and_size(self, name):
        g = self.load(name)
        packed = json_to_lineage_format(g)
        legacy = json_to_lineage_format(g, {"aliases": False})
        assert_same_graph(lineage_format_to_json(packed), lineage_format_to_json(legacy))
        assert len(packed) < len(legacy) * 0.6

    def test_each_edge_keeps_its_type(self, name):
        g = self.load(name)
        restored = lineage_format_to_json(json_to_lineage_format(g))
        wanted = sorted(json.dumps({k: e[k] for k in ("source", "target", "type") if k in e}, sort_keys=True)
                        for e in g["edges_in_view"])
        got = sorted(json.dumps({k: e[k] for k in ("source", "target", "type") if k in e}, sort_keys=True)
                     for e in restored["edges_in_view"])
        assert got == wanted


class TestDecodeGroupedEdges:
    def test_grouped_edges_keep_target_order_and_default_types(self):
        text = doc(
            "GRAPH:\nlineage_graph",
            "START:\nN1",
            "E:\nN1>N2,N3\nN3",
            "EP:\n*>* etype=direct\n* etype=summary",
            "N:\nN1:Column\nN2:Column\nN3:Column",
            BASE_ID_NAME,
        )
        edges = lineage_format_to_json(text)["edges_in_view"]
        assert [edge_key(e) for e in edges] == [
            ("id1", "id2", "direct"),
            ("id1", "id3", "direct"),
            ("id3", None, "summary"),
        ]
        assert "target" not in edges[2]

    def test_explicit_entry_overrides_default_and_empty_means_no_type(self):
        text = doc(
            "GRAPH:\nlineage_graph",
            "START:\nN1",
            "E:\nN1>N2,N3",
            "EP:\n*>* etype=direct\nN1>N3 etype=",
            "N:\nN1:Column\nN2:Column\nN3:Column",
            BASE_ID_NAME,
        )
        edges = lineage_format_to_json(text)["edges_in_view"]
        assert edges[0]["type"] == "direct"
        assert "type" not in edges[1]

    def test_several_edges_between_same_pair_keep_own_types(self):
        text = doc(
            "GRAPH:\nlineage_graph",
            "START:\nN1",
            "E:\nN1>N2,N2",
            "EP:\nN1>N2 etype=direct\nN1>N2 etype=summary",
            "N:\nN1:Column\nN2:Column",
            "ID:\nN1=id1\nN2=id2",
        )
        edges = lineage_format_to_json(text)["edges_in_view"]
        assert [e["type"] for e in edges] == ["direct", "summary"]

    def test_legacy_edges_still_decode(self):
        text = doc(
            "GRAPH:\nlineage_graph",
            "START:\nN1",
            "E:\nN1>N2\nN2>N1\nN2>",
            "EP:\nN1>N2 etype=direct\nN2>N1 etype=summary",
            "N:\nN1:Column\nN2:Column",
            "ID:\nN1=id1\nN2=id2",
        )
        edges = lineage_format_to_json(text)["edges_in_view"]
        assert [edge_key(e) for e in edges] == [
            ("id1", "id2", "direct"),
            ("id2", "id1", "summary"),
            ("id2", None, None),
        ]


class TestDecodeNodeDefaults:
    TEXT = doc(
        "GRAPH:\nlineage_graph",
        "START:\nN1",
        "E:\nN1>N2",
        "N:\nN1:Column\nN2:Column origin= flags=3\nN3:Column flags=0 origin=runtime",
        "NDEF:\norigin=design path=T1 flags=7",
        "T:\nT1=Microsoft%20SQL",
        "TID:\nT1=tid1",
        BASE_ID_NAME,
    )

    def assets(self):
        return {a["id"]: a for a in lineage_format_to_json(self.TEXT)["assets_in_view"]}

    def test_node_inherits_defaults(self):
        a = self.assets()["id1"]
        assert a["origin"] == "design"
        assert a["technology"] == {"id": "tid1", "name": "Microsoft%20SQL"}
        assert (a["is_deduced"], a["is_transforming"], a["is_operational"]) == (True, True, True)

    def test_empty_token_removes_inherited_value_and_flags_override(self):
        a = self.assets()["id2"]
        assert a["origin"] is None
        assert (a["is_deduced"], a["is_transforming"], a["is_operational"]) == (True, True, False)
        # origin= only removes origin; the other defaults are still inherited
        assert a["technology"]["id"] == "tid1"

    def test_explicit_value_overrides_default(self):
        a = self.assets()["id3"]
        assert a["origin"] == "runtime"
        assert (a["is_deduced"], a["is_transforming"], a["is_operational"]) == (False, False, False)


class TestDecodeRefAndStarDefaults:
    TEXT = doc(
        "GRAPH:\nlineage_graph",
        "START:\nN1",
        "E:\nN1>N2",
        "N:\nN1:Column\nN2:Column\nN3:Column",
        BASE_ID_NAME,
        "REF:\nR1=dbid:my_db:Database\nR2=TRANSFORMATION_TAG=TRANSFORMING\nR3=dbid:my_db",
        "HP:\n*=@R1\nN2=@R1|n2:Asset%202:Block\nN3=",
        "ATTR:\nN1=@R2|Column TYPE=Column\nN2=Column TYPE=Column|@R2\nN3=@R9",
        "DSD:\n*=@R3\nN3=",
    )

    def assets(self):
        return {a["id"]: a for a in lineage_format_to_json(self.TEXT)["assets_in_view"]}

    def test_star_default_hp_and_ref(self):
        a = self.assets()
        assert a["id1"]["hierarchical_path"] == [{"id": "dbid", "name": "my_db", "type": "Database"}]
        assert a["id2"]["hierarchical_path"] == [
            {"id": "dbid", "name": "my_db", "type": "Database"},
            {"id": "n2", "name": "Asset 2", "type": "Block"},
        ]

    def test_empty_entry_beats_star_default(self):
        a = self.assets()["id3"]
        assert a["hierarchical_path"] == []
        assert "data_source_definition_asset" not in a

    def test_star_default_dsd(self):
        a = self.assets()["id1"]
        assert a["data_source_definition_asset"] == {"id": "dbid", "name": "my_db"}

    def test_attr_refs_keep_order(self):
        a = self.assets()
        assert a["id1"]["attributes"] == [
            {"name": "TRANSFORMATION_TAG", "value": "TRANSFORMING"},
            {"name": "Column TYPE", "value": "Column"},
        ]
        assert [x["name"] for x in a["id2"]["attributes"]] == ["Column TYPE", "TRANSFORMATION_TAG"]

    def test_literal_that_looks_like_reference_is_not_expanded(self):
        # "@R9" is not defined in REF, so it is a plain attribute name.
        assert self.assets()["id3"]["attributes"] == [{"name": "@R9"}]


class TestDecodeIdentityKeyPrefix:
    TEXT = doc(
        "GRAPH:\nlineage_graph",
        "START:\nN1",
        "E:\nN1>N2",
        "N:\nN1:Column ikp=P1 ik=Asset%201%5BInput%5D/COL%5BColumn%5D\nN2:Column ik=plain%20key\nN3:Column ikp=P1",
        BASE_ID_NAME,
        "IKP:\nP1=uuid/my%20db%5BDatabase%5D/",
    )

    def test_prefix_plus_suffix(self):
        a = {x["id"]: x for x in lineage_format_to_json(self.TEXT)["assets_in_view"]}
        assert a["id1"]["identity_key"] == "uuid/my db[Database]/Asset 1[Input]/COL[Column]"

    def test_plain_ik_and_prefix_only(self):
        a = {x["id"]: x for x in lineage_format_to_json(self.TEXT)["assets_in_view"]}
        assert a["id2"]["identity_key"] == "plain key"
        assert a["id3"]["identity_key"] == "uuid/my db[Database]/"


class TestCli:
    GRAPH = '{"assets_in_view": [{"id": "a", "name": "A", "type": "Column"}], "edges_in_view": []}'

    def run(self, tmp_path, *extra):
        src, out = tmp_path / "in.json", tmp_path / "out.ldf"
        src.write_text(self.GRAPH, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-m", "ldf.cli", "json-to-lineage", str(src), str(out), *extra],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        return out.read_text(encoding="utf-8")

    def test_no_aliases_flag_is_accepted(self, tmp_path):
        assert self.run(tmp_path, "--no-aliases") == self.run(tmp_path)
