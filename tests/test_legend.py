"""legend: optional LEGEND section (first, spells out abbreviations), via the library API (options / file helper) and the CLI."""

import copy
import json
import re
import subprocess
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
from ldf.converter import _SECTION_LEGEND

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://api.example.com/gov_lineage/v2/lineage_assets/"


def asset(i):
    return {
        "id": f"id-{i:04d}-aaaa-bbbb-cccc",
        "name": f"Asset {i}",
        "type": "Column",
        "children": {"count": 2, "has_any": True, "href": f"{BASE}id-{i:04d}-aaaa-bbbb-cccc/children"},
        "catalog_assignments": [{"id": "c1", "href": f"https://api.example.com/v2/catalogs/cat-{i}"}],
    }


def graph(n=6):
    return {
        "assets_in_view": [asset(i) for i in range(n)],
        "edges_in_view": [
            {"source": f"id-{i:04d}-aaaa-bbbb-cccc", "target": f"id-{i + 1:04d}-aaaa-bbbb-cccc"}
            for i in range(n - 1)
        ],
    }


def sections(text):
    out, cur = {}, None
    for line in text.split("\n"):
        if re.fullmatch(r"[A-Z_]+:", line):
            cur = line[:-1]
            out[cur] = []
        elif cur and line:
            out[cur].append(line)
    return out


def legend_names(text):
    return [line.split("=", 1)[0] for line in sections(text)["LEGEND"]]


# --------------------------------------------------------------------------
# Library API: json_to_lineage_format(options)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("aliases", [True, False])
@pytest.mark.parametrize("compact", [True, False])
class TestLibraryOption:
    def test_legend_is_first_section(self, aliases, compact):
        text = json_to_lineage_format(graph(), {"legend": True, "aliases": aliases, "compact": compact})
        assert text.startswith("LEGEND:\n")
        assert list(sections(text))[0] == "LEGEND"

    def test_legend_lists_exactly_the_used_abbreviations(self, aliases, compact):
        opts = {"aliases": aliases, "compact": compact}
        plain = json_to_lineage_format(graph(), opts)
        text = json_to_lineage_format(graph(), {**opts, "legend": True})
        used = [name for name in sections(plain) if name in _SECTION_LEGEND]
        assert legend_names(text) == used
        assert "GRAPH" not in legend_names(text) and "START" not in legend_names(text)

    def test_legend_lines_follow_the_format_rules(self, aliases, compact):
        text = json_to_lineage_format(graph(), {"legend": True, "aliases": aliases, "compact": compact})
        for line in sections(text)["LEGEND"]:
            name, desc = line.split("=", 1)
            assert desc == _SECTION_LEGEND[name]
            assert not line.endswith(":")

    def test_rest_of_output_is_unchanged(self, aliases, compact):
        opts = {"aliases": aliases, "compact": compact}
        plain = json_to_lineage_format(graph(), opts)
        text = json_to_lineage_format(graph(), {**opts, "legend": True})
        sep = "\n" if compact else "\n\n"
        head, rest = text.split(sep + "GRAPH:", 1)
        assert "GRAPH:" + rest == plain
        assert head.startswith("LEGEND:\n")

    def test_round_trip_ignores_legend(self, aliases, compact):
        opts = {"aliases": aliases, "compact": compact}
        plain = json_to_lineage_format(graph(), opts)
        text = json_to_lineage_format(graph(), {**opts, "legend": True})
        assert lineage_format_to_json(text) == lineage_format_to_json(plain)


class TestLibraryDefaultsAndCombinations:
    def test_default_has_no_legend(self):
        g = graph()
        base = json_to_lineage_format(g)
        assert "LEGEND" not in sections(base)
        assert json_to_lineage_format(g, {"legend": False}) == base
        assert json_to_lineage_format(g, {}) == base
        assert json_to_lineage_format(g, None) == base

    def test_only_used_sections_are_described(self):
        text = json_to_lineage_format(graph(), {"legend": True, "no_urls": True})
        assert "URL" not in legend_names(text)
        assert "CA" in legend_names(text)

    def test_url_section_described_when_present(self):
        text = json_to_lineage_format(graph(), {"legend": True})
        assert "URL" in legend_names(text)

    def test_no_aliases_legend_has_no_alias_only_sections(self):
        text = json_to_lineage_format(graph(), {"legend": True, "aliases": False})
        assert not {"URL", "SRC", "REF", "NDEF", "IKP"} & set(legend_names(text))

    def test_scs_and_src_described_when_snippets_present(self):
        g = graph()
        for a in g["assets_in_view"]:
            a["source_code_snippets"] = [{
                "id": f"s-{a['id']}",
                "source_code": {"id": "script-1"},
                "start_position": {"row": 1, "column": 2},
                "end_position": {"row": 3, "column": 4},
                "lineage_version_timestamps": [],
            }]
        text = json_to_lineage_format(g, {"legend": True})
        assert {"SCS", "SRC"} <= set(legend_names(text))
        assert lineage_format_to_json(text)["assets_in_view"][0]["source_code_snippets"] == \
            g["assets_in_view"][0]["source_code_snippets"]

    def test_combined_with_exclude_fields(self):
        text = json_to_lineage_format(graph(), {"legend": True, "exclude_fields": ["catalog_assignments"]})
        assert "CA" not in legend_names(text)

    def test_input_graph_is_not_mutated(self):
        g = graph()
        before = copy.deepcopy(g)
        json_to_lineage_format(g, {"legend": True})
        assert g == before

    def test_every_legend_text_is_header_safe(self):
        for name, desc in _SECTION_LEGEND.items():
            assert "\n" not in desc and not desc.endswith(":") and desc.strip() == desc and desc

    def test_legend_covers_every_written_section(self):
        # every section the encoder can write has a description
        text = json_to_lineage_format(graph(), {"legend": True})
        assert set(legend_names(text)) <= set(_SECTION_LEGEND)


# --------------------------------------------------------------------------
# Library API: file helper
# --------------------------------------------------------------------------

class TestFileHelper:
    def test_legend_written(self, tmp_path):
        src, out = tmp_path / "in.json", tmp_path / "out.ldf"
        src.write_text(json.dumps(graph()), encoding="utf-8")
        convert_json_file_to_lineage(str(src), str(out), legend=True)
        assert "LEGEND" in sections(out.read_text(encoding="utf-8"))

    def test_default_has_no_legend(self, tmp_path):
        src, out = tmp_path / "in.json", tmp_path / "out.ldf"
        src.write_text(json.dumps(graph()), encoding="utf-8")
        convert_json_file_to_lineage(str(src), str(out))
        assert "LEGEND" not in sections(out.read_text(encoding="utf-8"))

    def test_round_trip_through_files(self, tmp_path):
        src, out, back = tmp_path / "in.json", tmp_path / "out.ldf", tmp_path / "back.json"
        src.write_text(json.dumps(graph()), encoding="utf-8")
        convert_json_file_to_lineage(str(src), str(out), legend=True, compact=True, no_urls=True)
        convert_lineage_file_to_json(str(out), str(back))
        expected = lineage_format_to_json(json_to_lineage_format(graph(), {"no_urls": True}))
        assert json.loads(back.read_text(encoding="utf-8")) == expected


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

class TestCli:
    def run(self, monkeypatch, *argv):
        monkeypatch.setattr(sys, "argv", ["ldf", *argv])
        main()

    def test_flag_adds_legend(self, tmp_path, monkeypatch):
        src, out = tmp_path / "in.json", tmp_path / "out.ldf"
        src.write_text(json.dumps(graph()), encoding="utf-8")
        self.run(monkeypatch, "json-to-lineage", str(src), str(out), "--legend")
        assert out.read_text(encoding="utf-8") == json_to_lineage_format(graph(), {"legend": True})

    def test_without_flag_no_legend(self, tmp_path, monkeypatch):
        src, out = tmp_path / "in.json", tmp_path / "out.ldf"
        src.write_text(json.dumps(graph()), encoding="utf-8")
        self.run(monkeypatch, "json-to-lineage", str(src), str(out))
        assert "LEGEND" not in sections(out.read_text(encoding="utf-8"))

    def test_combined_flags_and_back(self, tmp_path, monkeypatch):
        src, out, back = tmp_path / "in.json", tmp_path / "out.ldf", tmp_path / "back.json"
        src.write_text(json.dumps(graph()), encoding="utf-8")
        self.run(monkeypatch, "json-to-lineage", str(src), str(out), "--legend", "--no-aliases", "--compact")
        self.run(monkeypatch, "lineage-to-json", str(out), str(back))
        text = out.read_text(encoding="utf-8")
        assert "LEGEND" in sections(text) and "URL" not in legend_names(text)
        assert json.loads(back.read_text(encoding="utf-8")) == \
            lineage_format_to_json(json_to_lineage_format(graph(), {"aliases": False}))

    def test_help_lists_flag(self):
        res = subprocess.run([sys.executable, "-m", "ldf.cli", "json-to-lineage", "--help"],
                             capture_output=True, text=True, cwd=ROOT)
        assert "--legend" in res.stdout


# --------------------------------------------------------------------------
# Real data
# --------------------------------------------------------------------------

BIG = ROOT / "big_query_lineage.json"


@pytest.mark.skipif(not BIG.exists(), reason="big_query_lineage.json not present")
class TestRealData:
    @pytest.mark.parametrize("aliases", [True, False])
    def test_round_trip_unchanged_by_legend(self, aliases):
        data = json.loads(BIG.read_text(encoding="utf-8"))
        plain = json_to_lineage_format(data, {"aliases": aliases})
        text = json_to_lineage_format(data, {"aliases": aliases, "legend": True})
        assert lineage_format_to_json(text) == lineage_format_to_json(plain)
        assert legend_names(text) == [n for n in sections(plain) if n in _SECTION_LEGEND]
