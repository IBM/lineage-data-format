"""
Tests for URL aliasing (the ``URL`` section).

``children.href`` equal to ``<prefix><node id><suffix>`` is written as a
template with ``{id}`` and referenced from the node line as ``ch=n,h,@U1``.
``href`` values inside the CA / PA / SA blobs share prefixes of the same
section (``@U2/rest``; a literal leading "@" is written "@@"). Only with
``aliases=True``; the decoder reads both forms.
"""

import copy
import json
import re
from pathlib import Path

import pytest  # type: ignore

from ldf import json_to_lineage_format, lineage_format_to_json

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://api.example.com/gov_lineage/v2/lineage_assets/"


def asset(i, href=None, **extra):
    a = {"id": f"id-{i:04d}-aaaa-bbbb-cccc", "name": f"Asset {i}", "type": "Column"}
    if href is not None:
        a["children"] = {"count": 0, "has_any": False, "href": href}
    a.update(extra)
    return a


def graph(*assets):
    return {"assets_in_view": list(assets), "edges_in_view": []}


def ldf(g, aliases=True, exclude=None):
    opts = {"aliases": aliases}
    if exclude:
        opts["exclude_fields"] = exclude
    return json_to_lineage_format(g, opts)


def roundtrip(g, **kw):
    return lineage_format_to_json(ldf(g, **kw))


def sections(text):
    out, cur = {}, None
    for line in text.split("\n"):
        if re.fullmatch(r"[A-Z_]+:", line):
            cur = line[:-1]
            out[cur] = []
        elif cur and line:
            out[cur].append(line)
    return out


def templated_graph(n=6, base=BASE, suffix="/children"):
    return graph(*[asset(i, f"{base}id-{i:04d}-aaaa-bbbb-cccc{suffix}") for i in range(n)])


def hrefs(restored):
    return [a["children"]["href"] for a in restored["assets_in_view"]]


# --------------------------------------------------------------------------
# children.href
# --------------------------------------------------------------------------

class TestChildrenHref:
    def test_shared_template_is_written_once(self):
        g = templated_graph()
        text = ldf(g)
        assert sections(text)["URL"] == [f"U1={BASE}{{id}}/children"]
        assert text.count("lineage_assets") == 1
        assert "@U1" in text
        assert hrefs(lineage_format_to_json(text)) == hrefs(g)

    def test_roundtrip_is_lossless(self):
        g = templated_graph()
        assert roundtrip(g)["assets_in_view"] == roundtrip(g, aliases=False)["assets_in_view"]

    def test_two_templates(self):
        a = [asset(i, f"{BASE}id-{i:04d}-aaaa-bbbb-cccc/children") for i in range(4)]
        b = [asset(i, f"https://other.example.org/x/id-{i:04d}-aaaa-bbbb-cccc/more/children?v=1")
             for i in range(4, 8)]
        g = graph(*a, *b)
        text = ldf(g)
        url = sections(text)["URL"]
        assert len(url) == 2 and all("{id}" in u for u in url)
        assert hrefs(lineage_format_to_json(text)) == hrefs(g)

    def test_href_not_matching_any_template_stays_literal(self):
        g = templated_graph()
        g["assets_in_view"][2]["children"]["href"] = "https://elsewhere.example.org/other"
        text = ldf(g)
        assert "ch=0,0,https://elsewhere.example.org/other" in text
        assert "URL" in sections(text)
        assert hrefs(lineage_format_to_json(text)) == hrefs(g)

    def test_href_for_a_different_node_id_stays_literal(self):
        g = templated_graph()
        g["assets_in_view"][1]["children"]["href"] = f"{BASE}id-0004-aaaa-bbbb-cccc/children"
        assert hrefs(roundtrip(g)) == hrefs(g)

    def test_no_url_section_without_net_gain(self):
        a = asset(1, "http://x/id-0001-aaaa-bbbb-cccc")
        a["id"] = "i1"
        a["children"]["href"] = "http://x/i1"
        g = graph(a)
        text = ldf(g)
        assert "URL" not in sections(text)
        assert "@U" not in text
        assert hrefs(lineage_format_to_json(text)) == hrefs(g)

    def test_empty_href_is_not_aliased(self):
        g = graph(*[asset(i, "") for i in range(5)])
        text = ldf(g)
        assert "URL" not in sections(text)
        assert hrefs(lineage_format_to_json(text)) == [""] * 5

    @pytest.mark.parametrize("href", [
        "https://x.example.com/a,b",
        "https://x.example.com/a b",
        "https://x.example.com/a:b",
        "https://x.example.com/a=b%20c",
        "https://x.example.com/a\nb",
        "@leading-at",
        "@U1",
        "@U1/children",
    ])
    def test_awkward_literal_hrefs_roundtrip(self, href):
        g = templated_graph()
        g["assets_in_view"][3]["children"]["href"] = href
        assert hrefs(roundtrip(g)) == hrefs(g)
        if not re.search(r"\s", href):  # the legacy form never escaped whitespace
            assert hrefs(roundtrip(g, aliases=False)) == hrefs(g)

    def test_literal_at_href_is_written_in_named_token(self):
        g = graph(asset(1, "@U1"))
        text = ldf(g)
        assert "chh=@U1" in text
        assert hrefs(lineage_format_to_json(text)) == ["@U1"]

    def test_href_containing_template_text_with_colon_suffix(self):
        g = templated_graph()
        g["assets_in_view"][0]["children"]["href"] = f"{BASE}id-0000-aaaa-bbbb-cccc/children:"
        assert hrefs(roundtrip(g)) == hrefs(g)

    def test_no_aliases_keeps_legacy_form(self):
        g = templated_graph()
        text = ldf(g, aliases=False)
        assert "URL" not in sections(text)
        assert "@U" not in text
        assert text.count("lineage_assets") == 6
        assert re.search(r"ch=0,0,https://api\.example\.com/\S+/children", text)

    def test_excluded_children_href_leaves_no_url_section(self):
        text = ldf(templated_graph(), exclude=["children.href"])
        assert "URL" not in sections(text)
        assert "lineage_assets" not in text and "@U" not in text

    def test_named_form_when_count_is_excluded(self):
        g = templated_graph()
        restored = lineage_format_to_json(ldf(g, exclude=["children.count"]))
        assert hrefs(restored) == hrefs(g)

    def test_decoder_reads_hand_written_template(self):
        text = (
            "N:\nN1:Column ch=0,0,@U1\nN2:Column ch=3,1,@U2\nN3:Column ch=0,0,@U9\n\n"
            "ID:\nN1=aaa\nN2=bbb\nN3=ccc\n\n"
            "URL:\nU1=http://h/{id}/children\nU2=http://h/x/{id}"
        )
        got = hrefs(lineage_format_to_json(text))
        assert got == ["http://h/aaa/children", "http://h/x/bbb", "@U9"]

    def test_decoder_reads_legacy_form(self):
        text = "N:\nN1:Column ch=2,1,http://h/a:b/children\n\nID:\nN1=aaa"
        assert hrefs(lineage_format_to_json(text)) == ["http://h/a:b/children"]

    def test_url_section_follows_id(self):
        text = ldf(templated_graph())
        order = [m.group(1) for m in re.finditer(r"^([A-Z_]+):$", text, re.M)]
        assert order.index("URL") == order.index("ID") + 1

    def test_compact_mode(self):
        g = templated_graph()
        text = json_to_lineage_format(g, {"compact": True})
        assert "\n\n" not in text
        assert hrefs(lineage_format_to_json(text)) == hrefs(g)


# --------------------------------------------------------------------------
# href inside CA / PA / SA blobs
# --------------------------------------------------------------------------

def ca(href, deep=False):
    entry = {"id": "c1", "name": "cat", "href": href}
    if deep:
        entry["owner"] = {"name": "me", "links": [{"href": href + "/deep", "rel": "x"}]}
    return [entry]


class TestBlobHrefs:
    def assets(self, make, n=6):
        return graph(*[asset(i, **make(i)) for i in range(n)])

    def test_one_prefix_shared_by_ca_pa_sa(self):
        p = "https://api.example.com/v2/catalogs"
        g = self.assets(lambda i: {
            "catalog_assignments": ca(f"{p}/cat-{i}"),
            "project_assignments": ca(f"{p}/proj-{i}"),
            "space_assignments": ca(f"{p}/space-{i}", deep=True),
        })
        text = ldf(g)
        s = sections(text)
        assert s["URL"] == [f"U1={p}"]
        assert text.count("api.example.com") == 1
        assert '"href": "@U1/cat-0"' in text
        assert roundtrip(g)["assets_in_view"] == roundtrip(g, aliases=False)["assets_in_view"]
        assert roundtrip(g)["assets_in_view"][3]["space_assignments"] == g["assets_in_view"][3]["space_assignments"]

    def test_several_prefixes_and_children_templates_share_one_section(self):
        g = self.assets(lambda i: {
            "catalog_assignments": ca(f"https://a.example.com/v2/catalogs/cat-{i}"),
            "project_assignments": ca(f"https://b.example.com/v2/projects/proj-{i}"),
        })
        for i, a in enumerate(g["assets_in_view"]):
            a["children"] = {"count": 0, "has_any": False, "href": f"{BASE}{a['id']}/children"}
        text = ldf(g)
        url = sections(text)["URL"]
        assert len(url) == 3
        assert url[0].startswith("U1=") and "{id}" in url[0]
        assert not any("{id}" in u for u in url[1:])
        assert roundtrip(g)["assets_in_view"] == roundtrip(g, aliases=False)["assets_in_view"]
        assert [a["catalog_assignments"] for a in roundtrip(g)["assets_in_view"]] == \
            [a["catalog_assignments"] for a in g["assets_in_view"]]

    def test_longer_prefix_wins_when_it_pays_off(self):
        p = "https://api.example.com/v2/very/long/shared/prefix/catalogs"
        g = self.assets(lambda i: {"catalog_assignments": ca(f"{p}/cat-{i}")})
        url = sections(ldf(g))["URL"]
        assert url == [f"U1={p}"]

    def test_no_prefix_without_net_gain(self):
        g = self.assets(lambda i: {"catalog_assignments": ca(f"http://h{i}/c")}, n=3)
        text = ldf(g)
        assert "URL" not in sections(text)
        assert "@U" not in text
        assert roundtrip(g)["assets_in_view"][1]["catalog_assignments"] == ca("http://h1/c")

    def test_single_use_prefix_is_not_aliased(self):
        g = graph(asset(1, catalog_assignments=ca("https://api.example.com/v2/catalogs/only-one")))
        text = ldf(g)
        assert "URL" not in sections(text)
        assert "https://api.example.com/v2/catalogs/only-one" in text

    @pytest.mark.parametrize("literal", ["@leading", "@U1/x", "@@double", "@"])
    def test_literal_at_is_escaped(self, literal):
        p = "https://api.example.com/v2/catalogs"
        g = self.assets(lambda i: {"catalog_assignments": ca(f"{p}/cat-{i}")})
        g["assets_in_view"][2]["catalog_assignments"][0]["href"] = literal
        text = ldf(g)
        assert f'"href": "@{literal}"' in text
        assert roundtrip(g)["assets_in_view"][2]["catalog_assignments"][0]["href"] == literal
        assert roundtrip(g)["assets_in_view"][4]["catalog_assignments"] == g["assets_in_view"][4]["catalog_assignments"]

    def test_literal_at_escaped_even_without_url_section(self):
        g = graph(asset(1, catalog_assignments=ca("@x")))
        text = ldf(g)
        assert '"href": "@@x"' in text
        assert roundtrip(g)["assets_in_view"][0]["catalog_assignments"] == ca("@x")

    def test_only_href_keys_are_touched(self):
        p = "https://api.example.com/v2/catalogs"
        g = self.assets(lambda i: {"catalog_assignments": [{"href": f"{p}/c{i}", "url": f"{p}/u{i}",
                                                           "note": "@raw"}]})
        text = ldf(g)
        assert f'"url": "{p}/u0"' in text
        assert '"note": "@raw"' in text
        assert roundtrip(g)["assets_in_view"][0]["catalog_assignments"] == g["assets_in_view"][0]["catalog_assignments"]

    def test_non_string_href_is_untouched(self):
        g = graph(asset(1, catalog_assignments=[{"href": None}, {"href": 5}, {"href": ["a"]}]))
        assert roundtrip(g)["assets_in_view"][0]["catalog_assignments"] == \
            [{"href": None}, {"href": 5}, {"href": ["a"]}]

    def test_no_aliases_keeps_legacy_blobs(self):
        p = "https://api.example.com/v2/catalogs"
        g = self.assets(lambda i: {"catalog_assignments": ca(f"{p}/cat-{i}"), "project_assignments": ca("@x")})
        text = ldf(g, aliases=False)
        assert "URL" not in sections(text)
        assert text.count(p) == 6
        assert '"href": "@x"' in text
        assert roundtrip(g, aliases=False)["assets_in_view"] == roundtrip(g)["assets_in_view"]

    def test_excluded_href_leaves_no_url_section(self):
        p = "https://api.example.com/v2/catalogs"
        g = self.assets(lambda i: {"catalog_assignments": ca(f"{p}/cat-{i}")})
        text = ldf(g, exclude=["href"])
        assert "URL" not in sections(text) and "href" not in text

    def test_decoder_reads_hand_written_blob_aliases(self):
        text = (
            "N:\nN1:Column\n\nID:\nN1=aaa\n\n"
            'URL:\nU1=http://h/base\n\n'
            'CA:\nN1=[{"href": "@U1/x"}, {"href": "@@U1/y"}, {"href": "@U7/z"}, {"href": "plain"}]'
        )
        got = lineage_format_to_json(text)["assets_in_view"][0]["catalog_assignments"]
        assert [e["href"] for e in got] == ["http://h/base/x", "@U1/y", "@U7/z", "plain"]


# --------------------------------------------------------------------------
# real file
# --------------------------------------------------------------------------

class TestBigQueryLineage:
    def load(self):
        path = ROOT / "big_query_lineage.json"
        if not path.exists():
            pytest.skip("big_query_lineage.json not available")
        return json.loads(path.read_text())

    def test_roundtrip_and_single_template(self):
        g = self.load()
        text = ldf(g)
        assert len(sections(text)["URL"]) == 1
        assert text.count("lineage_assets") == 1
        restored = lineage_format_to_json(text)
        assert restored["assets_in_view"] == lineage_format_to_json(ldf(g, aliases=False))["assets_in_view"]
        assert [a["children"]["href"] for a in restored["assets_in_view"]] == \
            [a["children"]["href"] for a in g["assets_in_view"]]

    def test_input_is_not_mutated(self):
        g = self.load()
        before = copy.deepcopy(g)
        ldf(g)
        assert g == before
