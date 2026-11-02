"""
Tests for the alias-compression mechanisms of the LDF format.

Stage 1: the decoder reads hand-written documents that use the new
constructs (REF, IKP, NDEF, "*" defaults, grouped E, default EP) and the
``aliases`` option / ``--no-aliases`` flag exist. The encoder does not write
the new constructs yet, so ``aliases`` must not change its output.
"""

import copy
import subprocess
import sys

from ldf import json_to_lineage_format, lineage_format_to_json


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


class TestEncoderUnchanged:
    GRAPH = {
        "assets_in_view": [
            {"id": "a", "name": "A", "type": "Column", "origin": "design",
             "identity_key": "x/y[Database]/A[Column]"},
            {"id": "b", "name": "B", "type": "Column", "origin": "design",
             "identity_key": "x/y[Database]/B[Column]"},
        ],
        "edges_in_view": [{"source": "a", "target": "b", "type": "direct"}],
    }

    def test_aliases_option_does_not_change_output_yet(self):
        default = json_to_lineage_format(copy.deepcopy(self.GRAPH))
        on = json_to_lineage_format(copy.deepcopy(self.GRAPH), {"aliases": True})
        off = json_to_lineage_format(copy.deepcopy(self.GRAPH), {"aliases": False})
        assert default == on == off


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
