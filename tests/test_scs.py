"""Compact source_code_snippets (SCS) with a shared SRC section (aliases on)."""

import copy
import json
import re
import sys
from pathlib import Path

import pytest  # type: ignore

from ldf import (
    convert_json_file_to_lineage,
    convert_lineage_file_to_json,
    json_to_lineage_format,
    lineage_format_to_json,
)
from ldf.cli import main

ROOT = Path(__file__).resolve().parent.parent
H1 = "7d226931a55bac8e113c1557358a6411e41cc07ee2b3f3d16bbfb72a342dfbd4"
H2 = "9cb45f925a1e32da583f982f9d5553aa71cbce9e80196b033e71dedbac050432"


def snip(sid="s1", src="src1", start=(41, 1), end=(44, 38), **over):
    s = {
        "id": sid,
        "source_code": {"id": src},
        "start_position": {"row": start[0], "column": start[1]},
        "end_position": {"row": end[0], "column": end[1]},
        "lineage_version_timestamps": [],
    }
    s.update(over)
    return s


def graph(*snippet_lists):
    assets = []
    for i, snippets in enumerate(snippet_lists):
        a = {"id": f"id-{i}", "name": f"n{i}", "type": "Column"}
        if snippets is not None:
            a["source_code_snippets"] = snippets
        assets.append(a)
    return {"assets_in_view": assets, "edges_in_view": []}


def sections(text):
    out, cur = {}, None
    for line in text.split("\n"):
        if re.fullmatch(r"[A-Z_]+:", line):
            cur = line[:-1]
            out[cur] = []
        elif cur and line:
            out[cur].append(line)
    return out


def kv(text, name):
    return dict(line.split("=", 1) for line in sections(text).get(name, []))


def rt(g, **opts):
    return lineage_format_to_json(json_to_lineage_format(g, opts or None))


def scs_of(restored):
    return [a["source_code_snippets"] for a in restored["assets_in_view"]]


# --------------------------------------------------------------------------
# Format
# --------------------------------------------------------------------------

class TestCompactForm:
    def test_single_snippet_format(self):
        g = graph([snip(H2, H1)])
        text = json_to_lineage_format(g)
        assert sections(text)["SRC"] == [f"S1={H1}"]
        assert kv(text, "SCS") == {"N1": f"{H2}@S1@41:1-44:38"}
        assert "{" not in "".join(sections(text)["SCS"])
        assert scs_of(lineage_format_to_json(text)) == [[snip(H2, H1)]]

    def test_several_snippets_one_script_share_one_src_entry(self):
        sn = [snip("a", "scr", (1, 2), (3, 4)), snip("b", "scr", (5, 6), (7, 8)), snip("c", "scr", (0, 0), (0, 0))]
        g = graph(sn, [snip("d", "scr", (9, 9), (9, 10))])
        text = json_to_lineage_format(g)
        assert sections(text)["SRC"] == ["S1=scr"]
        assert kv(text, "SCS")["N1"] == "a@S1@1:2-3:4|b@S1@5:6-7:8|c@S1@0:0-0:0"
        assert scs_of(lineage_format_to_json(text)) == [sn, [snip("d", "scr", (9, 9), (9, 10))]]

    def test_several_scripts_get_several_aliases(self):
        g = graph([snip("a", "x1"), snip("b", "x2")], [snip("c", "x1")])
        text = json_to_lineage_format(g)
        assert sections(text)["SRC"] == ["S1=x1", "S2=x2"]
        assert kv(text, "SCS")["N2"] == "c@S1@41:1-44:38"
        assert rt(g)["assets_in_view"][0]["source_code_snippets"] == [snip("a", "x1"), snip("b", "x2")]

    def test_key_order_of_restored_snippet_matches_original(self):
        got = rt(graph([snip()]))["assets_in_view"][0]["source_code_snippets"][0]
        assert list(got) == list(snip())
        assert list(got["start_position"]) == ["row", "column"]

    def test_numbers_come_back_as_int(self):
        got = rt(graph([snip(start=(10, 20), end=(30, 40))]))["assets_in_view"][0]["source_code_snippets"][0]
        assert got["start_position"] == {"row": 10, "column": 20}
        assert isinstance(got["end_position"]["column"], int)

    def test_no_src_section_without_snippets(self):
        text = json_to_lineage_format(graph(None, []))
        assert "SRC" not in sections(text) and "SCS" not in sections(text)

    def test_is_shorter_than_json_form(self):
        g = graph([snip(H2, H1)])
        assert len(json_to_lineage_format(g)) < len(json_to_lineage_format(g, {"aliases": False}))


# --------------------------------------------------------------------------
# Fallback to JSON (nothing may be lost)
# --------------------------------------------------------------------------

class TestJsonFallback:
    @pytest.mark.parametrize("odd", [
        snip(lineage_version_timestamps=["2024-01-01T00:00:00Z"]),
        snip(extra="x"),
        snip(sid="has space"),
        snip(sid="a@b"),
        snip(sid="a|b"),
        snip(sid=""),
        snip(src="we@ird"),
        snip(src="pi|pe"),
        snip(src=""),
        snip(start=(-1, 0)),
        snip(source_code={"id": "x", "name": "y"}),
        snip(start_position={"row": 1, "column": 2, "extra": 3}),
        snip(start_position={"row": 1.5, "column": 2}),
        snip(start_position={"row": True, "column": 2}),
        snip(start_position={"row": "1", "column": 2}),
        snip(sid=123),
        snip(lineage_version_timestamps=None),
    ])
    def test_unusual_snippet_round_trips_as_json(self, odd):
        g = graph([odd])
        text = json_to_lineage_format(g)
        assert "SRC" not in sections(text)
        assert kv(text, "SCS")["N1"].startswith("[")
        assert scs_of(lineage_format_to_json(text)) == [[odd]]

    def test_missing_key_falls_back(self):
        s = snip()
        del s["end_position"]
        assert scs_of(rt(graph([s]))) == [[s]]

    def test_one_odd_snippet_makes_whole_node_entry_json(self):
        good, odd = snip("a", "scr"), snip("b", "scr", lineage_version_timestamps=["t"])
        g = graph([good, odd], [snip("c", "scr")])
        text = json_to_lineage_format(g)
        scs = kv(text, "SCS")
        assert scs["N1"].startswith("[")
        assert scs["N2"] == "c@S1@41:1-44:38"
        assert scs_of(lineage_format_to_json(text)) == [[good, odd], [snip("c", "scr")]]

    def test_non_list_value_is_kept(self):
        g = graph([{"weird": 1}])
        assert scs_of(rt(g)) == [[{"weird": 1}]]

    def test_unicode_and_newline_in_json_fallback(self):
        # json.dumps escapes the newline, so the value survives unchanged
        # and the entry stays on one physical line.
        odd = snip(note="zażółć\ngęślą")
        text = json_to_lineage_format(graph([odd]))
        assert len(kv(text, "SCS")["N1"].splitlines()) == 1
        assert scs_of(lineage_format_to_json(text)) == [[odd]]


# --------------------------------------------------------------------------
# Compatibility
# --------------------------------------------------------------------------

class TestCompatibility:
    def test_no_aliases_keeps_legacy_json(self):
        g = graph([snip(H2, H1)])
        text = json_to_lineage_format(g, {"aliases": False})
        assert "SRC" not in sections(text)
        assert json.loads(kv(text, "SCS")["N1"]) == [snip(H2, H1)]
        assert scs_of(lineage_format_to_json(text)) == [[snip(H2, H1)]]

    def test_decoder_reads_legacy_json_even_with_aliases_on(self):
        legacy = "GRAPH:\nlineage_graph\n\nSTART:\nN1\n\nE:\nN1\n\nN:\nN1:Column\n\nID:\nN1=a\n\nNAME:\nN1=x\n\n" \
                 f"SCS:\nN1={json.dumps([snip()])}"
        assert scs_of(lineage_format_to_json(legacy)) == [[snip()]]

    def test_unknown_src_alias_is_kept_literally(self):
        text = "GRAPH:\nlineage_graph\n\nSTART:\nN1\n\nE:\nN1\n\nN:\nN1:Column\n\nID:\nN1=a\n\nNAME:\nN1=x\n\n" \
               "SCS:\nN1=sid@S9@1:2-3:4"
        got = scs_of(lineage_format_to_json(text))[0][0]
        assert got["source_code"] == {"id": "S9"}

    def test_malformed_compact_entry_raises_clear_error(self):
        text = "GRAPH:\nlineage_graph\n\nSTART:\nN1\n\nE:\nN1\n\nN:\nN1:Column\n\nID:\nN1=a\n\nNAME:\nN1=x\n\n" \
               "SCS:\nN1=garbage"
        with pytest.raises(ValueError, match="Invalid SCS entry"):
            lineage_format_to_json(text)

    def test_compact_mode(self):
        g = graph([snip(H2, H1)])
        text = json_to_lineage_format(g, {"compact": True})
        assert scs_of(lineage_format_to_json(text)) == [[snip(H2, H1)]]

    def test_input_is_not_mutated(self):
        g = graph([snip(H2, H1)])
        before = copy.deepcopy(g)
        json_to_lineage_format(g)
        assert g == before


# --------------------------------------------------------------------------
# exclude_fields interplay
# --------------------------------------------------------------------------

class TestExclude:
    @pytest.mark.parametrize("field", ["id", "source_code", "source_code.id", "start_position",
                                       "end_position", "start_position.row", "end_position.column",
                                       "lineage_version_timestamps"])
    def test_excluding_a_snippet_key_stays_lossless_for_the_rest(self, field):
        g = graph([snip(H2, H1)])
        text = json_to_lineage_format(g, {"exclude_fields": [f"source_code_snippets.{field}"]})
        got = scs_of(lineage_format_to_json(text))[0]
        want = copy.deepcopy(snip(H2, H1))
        node = want
        parts = field.split(".")
        for p in parts[:-1]:
            node = node[p]
        node.pop(parts[-1])
        want = {k: v for k, v in want.items() if v != {}}
        assert got == [want] or got == [] and not want

    def test_excluding_whole_field_removes_sections(self):
        text = json_to_lineage_format(graph([snip()]), {"exclude_fields": ["source_code_snippets"]})
        assert "SCS" not in sections(text) and "SRC" not in sections(text)

    def test_other_exclusions_do_not_break_compact_form(self):
        text = json_to_lineage_format(graph([snip(H2, H1)]), {"exclude_fields": ["name"]})
        assert kv(text, "SCS")["N1"] == f"{H2}@S1@41:1-44:38"


# --------------------------------------------------------------------------
# Library file helpers and CLI
# --------------------------------------------------------------------------

class TestFilesAndCli:
    def test_file_helpers_round_trip(self, tmp_path):
        src, out, back = tmp_path / "in.json", tmp_path / "o.ldf", tmp_path / "b.json"
        g = graph([snip(H2, H1)])
        src.write_text(json.dumps(g), encoding="utf-8")
        convert_json_file_to_lineage(str(src), str(out))
        assert "SRC:" in out.read_text(encoding="utf-8")
        convert_lineage_file_to_json(str(out), str(back))
        assert scs_of(json.loads(back.read_text(encoding="utf-8"))) == [[snip(H2, H1)]]

    def test_cli_default_is_compact_and_no_aliases_is_legacy(self, tmp_path, monkeypatch):
        src, a, b = tmp_path / "in.json", tmp_path / "a.ldf", tmp_path / "b.ldf"
        src.write_text(json.dumps(graph([snip(H2, H1)])), encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["ldf", "json-to-lineage", str(src), str(a)])
        main()
        monkeypatch.setattr(sys, "argv", ["ldf", "json-to-lineage", str(src), str(b), "--no-aliases"])
        main()
        assert "SRC:" in a.read_text(encoding="utf-8")
        assert "SRC:" not in b.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Real data
# --------------------------------------------------------------------------

BIG = ROOT / "big_query_lineage.json"


@pytest.mark.skipif(not BIG.exists(), reason="big_query_lineage.json not present")
@pytest.mark.parametrize("aliases", [True, False])
def test_big_query_scs_round_trip(aliases):
    with open(BIG, encoding="utf-8") as f:
        g = json.load(f)
    restored = rt(g, aliases=aliases)
    before = {a["id"]: a["source_code_snippets"] for a in g["assets_in_view"]}
    after = {a["id"]: a["source_code_snippets"] for a in restored["assets_in_view"]}
    assert after == before
    text = json_to_lineage_format(g, {"aliases": aliases})
    assert ("SRC" in sections(text)) is aliases
