"""no_urls: drop every URL, via the library API (options / file helper) and the CLI."""

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

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://api.example.com/gov_lineage/v2/lineage_assets/"


def asset(i, **extra):
    a = {
        "id": f"id-{i:04d}-aaaa-bbbb-cccc",
        "name": f"Asset {i}",
        "type": "Column",
        "children": {"count": 2, "has_any": True, "href": f"{BASE}id-{i:04d}-aaaa-bbbb-cccc/children"},
        "catalog_assignments": [{"id": "c1", "href": f"https://api.example.com/v2/catalogs/cat-{i}"}],
        "project_assignments": [{"id": "p1", "href": f"https://api.example.com/v2/catalogs/proj-{i}"}],
        "space_assignments": [
            {"id": "s1", "owner": {"links": [{"href": f"https://api.example.com/v2/catalogs/sp-{i}", "rel": "x"}]}}
        ],
    }
    a.update(extra)
    return a


def graph(n=6, **extra):
    return {"assets_in_view": [asset(i, **extra) for i in range(n)], "edges_in_view": []}


def sections(text):
    out, cur = {}, None
    for line in text.split("\n"):
        if re.fullmatch(r"[A-Z_]+:", line):
            cur = line[:-1]
            out[cur] = []
        elif cur and line:
            out[cur].append(line)
    return out


def walk(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k, v
            yield from walk(v)
    elif isinstance(node, list):
        for item in node:
            yield from walk(item)


# --------------------------------------------------------------------------
# Library API: json_to_lineage_format(options)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("aliases", [True, False])
class TestLibraryOption:
    def test_no_url_left_in_text(self, aliases):
        text = json_to_lineage_format(graph(), {"no_urls": True, "aliases": aliases})
        assert "api.example.com" not in text
        assert "https" not in text
        assert "href" not in text
        assert "URL" not in sections(text)

    def test_children_keep_count_and_has_any(self, aliases):
        text = json_to_lineage_format(graph(), {"no_urls": True, "aliases": aliases})
        restored = lineage_format_to_json(text)
        for a in restored["assets_in_view"]:
            assert a["children"] == {"count": 2, "has_any": True}

    def test_hrefs_gone_from_blobs_but_rest_kept(self, aliases):
        text = json_to_lineage_format(graph(), {"no_urls": True, "aliases": aliases})
        a = lineage_format_to_json(text)["assets_in_view"][0]
        assert a["catalog_assignments"] == [{"id": "c1"}]
        assert a["project_assignments"] == [{"id": "p1"}]
        assert a["space_assignments"] == [{"id": "s1", "owner": {"links": [{"rel": "x"}]}}]

    def test_restored_graph_has_no_href_anywhere(self, aliases):
        restored = lineage_format_to_json(json_to_lineage_format(graph(), {"no_urls": True, "aliases": aliases}))
        assert "href" not in {k for k, _ in walk(restored)}

    def test_equals_exclude_href(self, aliases):
        g = graph()
        assert json_to_lineage_format(g, {"no_urls": True, "aliases": aliases}) == \
            json_to_lineage_format(g, {"exclude_fields": ["href"], "aliases": aliases})

    def test_input_graph_is_not_mutated(self, aliases):
        g = graph()
        before = copy.deepcopy(g)
        json_to_lineage_format(g, {"no_urls": True, "aliases": aliases})
        assert g == before


class TestLibraryDefaultsAndCombinations:
    def test_false_or_missing_leaves_output_unchanged(self):
        g = graph()
        base = json_to_lineage_format(g)
        assert json_to_lineage_format(g, {"no_urls": False}) == base
        assert json_to_lineage_format(g, {}) == base
        assert json_to_lineage_format(g, None) == base
        assert "URL" in sections(base)

    def test_combined_with_exclude_fields(self):
        g = graph()
        text = json_to_lineage_format(g, {"no_urls": True, "exclude_fields": ["catalog_assignments", "children.count"]})
        restored = lineage_format_to_json(text)["assets_in_view"][0]
        assert restored["children"] == {"has_any": True}
        assert "catalog_assignments" not in text.replace("CA:", "") and "CA" not in sections(text)
        assert "href" not in {k for k, _ in walk(restored)}

    def test_href_already_in_exclude_fields_is_fine(self):
        g = graph()
        assert json_to_lineage_format(g, {"no_urls": True, "exclude_fields": ["href"]}) == \
            json_to_lineage_format(g, {"no_urls": True})

    def test_exclude_fields_list_is_not_mutated(self):
        excl = ["children.count"]
        json_to_lineage_format(graph(), {"no_urls": True, "exclude_fields": excl})
        assert excl == ["children.count"]

    def test_compact_mode(self):
        text = json_to_lineage_format(graph(), {"no_urls": True, "compact": True})
        assert "https" not in text
        assert lineage_format_to_json(text)["assets_in_view"][0]["children"] == {"count": 2, "has_any": True}

    def test_graph_without_any_url_is_unchanged(self):
        g = {"assets_in_view": [{"id": "a", "name": "A", "type": "Column"}], "edges_in_view": []}
        assert json_to_lineage_format(g, {"no_urls": True}) == json_to_lineage_format(g)

    def test_no_traces_of_empty_children_slot(self):
        g = {"assets_in_view": [{"id": "a", "name": "A", "type": "Column",
                                 "children": {"href": "http://x/a"}}], "edges_in_view": []}
        text = json_to_lineage_format(g, {"no_urls": True})
        restored = lineage_format_to_json(text)["assets_in_view"][0]
        assert "children" not in restored or restored["children"] in ({}, None)
        assert "http" not in text

    def test_bad_exclude_fields_type_still_rejected(self):
        with pytest.raises(TypeError):
            json_to_lineage_format(graph(), {"no_urls": True, "exclude_fields": "children"})


# --------------------------------------------------------------------------
# Library API: file helper
# --------------------------------------------------------------------------

class TestFileHelper:
    def test_convert_json_file_to_lineage_no_urls(self, tmp_path):
        src, out = tmp_path / "in.json", tmp_path / "out.ldf"
        src.write_text(json.dumps(graph()), encoding="utf-8")
        convert_json_file_to_lineage(str(src), str(out), no_urls=True)
        text = out.read_text(encoding="utf-8")
        assert "https" not in text and "URL" not in sections(text)

    def test_default_keeps_urls(self, tmp_path):
        src, out = tmp_path / "in.json", tmp_path / "out.ldf"
        src.write_text(json.dumps(graph()), encoding="utf-8")
        convert_json_file_to_lineage(str(src), str(out))
        assert "api.example.com" in out.read_text(encoding="utf-8")

    def test_combined_with_exclude_and_no_aliases(self, tmp_path):
        src, out, back = tmp_path / "in.json", tmp_path / "out.ldf", tmp_path / "back.json"
        src.write_text(json.dumps(graph()), encoding="utf-8")
        convert_json_file_to_lineage(
            str(src), str(out), exclude_fields=["children.count"], aliases=False, no_urls=True
        )
        convert_lineage_file_to_json(str(out), str(back))
        a = json.loads(back.read_text(encoding="utf-8"))["assets_in_view"][0]
        assert a["children"] == {"has_any": True}
        assert "href" not in {k for k, _ in walk(a)}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

class TestCli:
    def run(self, monkeypatch, *argv):
        monkeypatch.setattr(sys, "argv", ["ldf", *argv])
        main()

    def test_flag_removes_urls(self, tmp_path, monkeypatch):
        src, out = tmp_path / "in.json", tmp_path / "out.ldf"
        src.write_text(json.dumps(graph()), encoding="utf-8")
        self.run(monkeypatch, "json-to-lineage", str(src), str(out), "--no-urls")
        text = out.read_text(encoding="utf-8")
        assert "https" not in text and "URL" not in sections(text)

    def test_without_flag_keeps_urls(self, tmp_path, monkeypatch):
        src, out = tmp_path / "in.json", tmp_path / "out.ldf"
        src.write_text(json.dumps(graph()), encoding="utf-8")
        self.run(monkeypatch, "json-to-lineage", str(src), str(out))
        assert "api.example.com" in out.read_text(encoding="utf-8")

    def test_cli_matches_library_and_exclude_href(self, tmp_path, monkeypatch):
        g = graph()
        src, a, b = tmp_path / "in.json", tmp_path / "a.ldf", tmp_path / "b.ldf"
        src.write_text(json.dumps(g), encoding="utf-8")
        self.run(monkeypatch, "json-to-lineage", str(src), str(a), "--no-urls")
        self.run(monkeypatch, "json-to-lineage", str(src), str(b), "--exclude", "href")
        text = a.read_text(encoding="utf-8")
        assert text == b.read_text(encoding="utf-8")
        assert text == json_to_lineage_format(g, {"no_urls": True})

    def test_combined_with_exclude_and_compact(self, tmp_path, monkeypatch):
        src, out = tmp_path / "in.json", tmp_path / "out.ldf"
        src.write_text(json.dumps(graph()), encoding="utf-8")
        self.run(monkeypatch, "json-to-lineage", str(src), str(out), "--no-urls", "--compact",
                 "--exclude", "children.count")
        text = out.read_text(encoding="utf-8")
        assert "https" not in text
        assert lineage_format_to_json(text)["assets_in_view"][0]["children"] == {"has_any": True}

    def test_installed_entry_point_help_lists_flag(self):
        res = subprocess.run([sys.executable, "-m", "ldf.cli", "json-to-lineage", "--help"],
                             capture_output=True, text=True, cwd=ROOT)
        assert "--no-urls" in res.stdout


# --------------------------------------------------------------------------
# Real data
# --------------------------------------------------------------------------

BIG = ROOT / "big_query_lineage.json"


@pytest.mark.skipif(not BIG.exists(), reason="big_query_lineage.json not present")
class TestBigQueryLineage:
    def test_no_urls_removes_all_and_is_smaller(self):
        with open(BIG, encoding="utf-8") as f:
            g = json.load(f)
        with_urls = json_to_lineage_format(g)
        text = json_to_lineage_format(g, {"no_urls": True})
        assert "gov_lineage" not in text and "URL" not in sections(text)
        assert len(text) < len(with_urls)
        restored = lineage_format_to_json(text)
        assert "href" not in {k for k, _ in walk(restored)}
        for orig, got in zip(g["assets_in_view"], restored["assets_in_view"]):
            assert got["children"] == {k: v for k, v in orig["children"].items() if k != "href"}
