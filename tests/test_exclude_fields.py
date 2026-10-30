"""
Tests for the static ``exclude_fields`` option of ``json_to_lineage_format``.

Exclusion is applied to the input graph BEFORE serialization, so an excluded
field must leave no trace in the LDF text (no empty separators, empty entries,
empty sections, header lines or lookup rows).

Two data sources are used:
  * small synthetic graphs (exact, hand-checked expectations), and
  * ``big_query_lineage.json`` from the repository root (real backend response;
    git-ignored via ``*.json``, so those tests are skipped when it is absent).
"""

import copy
import fnmatch
import json
import logging
import re
from pathlib import Path

import pytest  # type: ignore

from ldf import json_to_lineage_format, lineage_format_to_json  # type: ignore
from .test_converter import BACKEND_RESPONSE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ldf(graph, exclude=None, **opts):
    options = dict(opts)
    if exclude is not None:
        options["exclude_fields"] = exclude
    return json_to_lineage_format(graph, options or None)


def sections(text):
    """Split LDF text into {SECTION: [lines]} (blank lines dropped)."""
    result, current = {}, None
    for line in text.split("\n"):
        if re.fullmatch(r"[A-Z_]+:", line):
            current = line[:-1]
            result[current] = []
        elif line and current is not None:
            result[current].append(line)
    return result


def node_lines(text):
    return sections(text).get("N", [])


def kv_section(text, name):
    return dict(l.split("=", 1) for l in sections(text).get(name, []))


def graph():
    return copy.deepcopy(BACKEND_RESPONSE)


def one_asset_graph(**overrides):
    asset = copy.deepcopy(BACKEND_RESPONSE["assets_in_view"][0])
    asset.update(overrides)
    return {"assets_in_view": [asset], "edges_in_view": []}


def assert_no_traces(text):
    """Generic structural 'no leftovers' check on serialized LDF text."""
    secs = sections(text)
    # no empty sections: every header is followed by at least one line
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if re.fullmatch(r"[A-Z_]+:", line):
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            assert nxt and not re.fullmatch(r"[A-Z_]+:", nxt), f"empty section {line}"
    for line in secs.get("N", []):
        assert "  " not in line and not line.endswith(" "), f"blank token in {line!r}"
        assert not re.search(r"\b(tags|bt|bc|dc)=\[\]", line), line
        assert not re.search(r"\bch=(,|$| )", line), line
        assert not re.search(r" (rk|origin|ik|path|flags)=(?: |$)", line), line
    for name in ("T", "TID", "ID", "NAME", "BT", "BC", "DC", "HP", "ATTR", "DSD"):
        for line in secs.get(name, []):
            assert not re.fullmatch(r"\w+=", line), f"empty value in {name}: {line!r}"
    for line in secs.get("HP", []):
        value = line.split("=", 1)[1]
        assert not re.search(r"::|\|\||^\||\|$|:$|\|:|:\|", value), line
    for name in ("BT", "BC", "DC"):
        for line in secs.get(name, []):
            value = line.split("=", 1)[1]
            assert not value.endswith("|") and not value.startswith("|"), line
    for line in secs.get("DSD", []):
        value = line.split("=", 1)[1]
        assert not value.endswith(":") and not value.startswith(":"), line
    for line in secs.get("ATTR", []):
        value = line.split("=", 1)[1]
        assert value and "||" not in value and not value.startswith("|") and not value.endswith("|"), line


# ---------------------------------------------------------------------------
# Default behaviour: output identical to before
# ---------------------------------------------------------------------------

class TestDefaults:
    BASELINE = json_to_lineage_format(BACKEND_RESPONSE)

    @pytest.mark.parametrize("options", [
        None,
        {},
        {"compact": False},
        {"exclude_fields": []},
        {"exclude_fields": None},
        {"exclude_fields": ()},
    ])
    def test_default_output_identical(self, options):
        assert json_to_lineage_format(graph(), options) == self.BASELINE

    @pytest.mark.parametrize("exclude", [
        ["no_such_field"],
        ["technology.nope"],
        ["a.b.c.d"],
        ["IS_*"],                       # fnmatch here is case-sensitive
        ["hierarchical_path.0.type"],   # indexes are not part of the syntax
        ["assets_in_view.technology.id"],   # paths are relative to asset/edge
    ])
    def test_unmatched_entries_do_not_change_output(self, exclude):
        assert ldf(graph(), exclude) == self.BASELINE

    def test_unmatched_entries_do_not_change_compact_output(self):
        compact = json_to_lineage_format(graph(), {"compact": True})
        assert ldf(graph(), ["nope"], compact=True) == compact

    def test_default_is_empty_list_semantics_for_missing_optional_parts(self):
        """With nothing excluded, legacy defaults still apply (e.g. missing name -> '')."""
        g = one_asset_graph()
        del g["assets_in_view"][0]["name"]
        assert "NAME:\nN1=" in json_to_lineage_format(g)
        assert ldf(g, []) == json_to_lineage_format(g)

    def test_input_is_never_mutated(self):
        g = graph()
        before = copy.deepcopy(g)
        ldf(g, ["technology", "children.href", "hierarchical_path.type", "is_*", "*_assignments", "name"])
        assert g == before

    def test_exclusion_does_not_leak_between_calls(self):
        base = json_to_lineage_format(graph())
        ldf(graph(), ["technology", "children"])
        assert json_to_lineage_format(graph()) == base

    def test_golden_sections_with_nothing_excluded(self):
        secs = sections(ldf(graph(), []))
        assert list(secs) == [
            "GRAPH", "START", "E", "EP", "N", "T", "TID", "ID", "NAME",
            "BT", "BC", "DC", "HP", "ATTR", "SCS", "CA", "PA", "SA", "DSD",
        ]


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestValidation:
    @pytest.mark.parametrize("bad", ["children", 5, [1], ["ok", None], [["a"]]])
    def test_must_be_list_of_str(self, bad):
        with pytest.raises(TypeError):
            ldf(graph(), bad)

    @pytest.mark.parametrize("exclude", [["id"], ["source"], ["target"], ["i?"], ["sourc*"]])
    def test_required_identifiers_cannot_be_excluded(self, exclude):
        with pytest.raises(ValueError):
            ldf(graph(), exclude)

    def test_required_check_does_not_trigger_when_field_never_existed(self):
        """Edges without target in the INPUT are legal and must be left alone."""
        g = graph()
        del g["edges_in_view"][0]["target"]
        text = ldf(g, ["technology"])
        assert sections(text)["E"] == ["N1", "N2>N1"]         # target never existed -> bare "N1"
        assert sections(ldf(g, ["technology"]))["E"] == ["N1", "N2>N1"]

    def test_unknown_entries_logged_at_debug_level(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="ldf.converter"):
            ldf(graph(), ["does_not_exist", "technology.nope", "children"])
        messages = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("does_not_exist" in m for m in messages)
        assert any("technology.nope" in m for m in messages)
        assert not any("'children'" in m for m in messages)
        assert all(r.levelno == logging.DEBUG for r in caplog.records)

    def test_unknown_entries_do_not_raise_or_warn(self, caplog):
        with caplog.at_level(logging.INFO, logger="ldf.converter"):
            ldf(graph(), ["does_not_exist"])
        assert caplog.records == []


# ---------------------------------------------------------------------------
# Plain name: removed at every nesting level
# ---------------------------------------------------------------------------

class TestPlainName:
    def test_children_removed_from_every_node(self):
        text = ldf(graph(), ["children"])
        assert all(" ch=" not in l for l in node_lines(text))
        assert "gov_lineage" not in text   # href gone entirely
        assert_no_traces(text)

    def test_name_removed_at_every_level(self):
        text = ldf(graph(), ["name"])
        secs = sections(text)
        assert "NAME" not in secs
        # lookups lose their names, keep their ids
        assert secs["BT"] == ["BT1=8d3641e9-841f-40d0-aa0b-f5e8e8b97186"]
        assert secs["BC"] == ["BC1=e441721f-7369-4547-9aac-a278dfb74f05"]
        assert secs["DC"] == ["DC1=3652f859-397e-4fa3-80ac-86e11a5379c4"]
        assert "T" not in secs and "TID" in secs         # technology.name gone
        seg = r"i=[0-9a-f]{64}:t=\w+"
        assert all(re.fullmatch(rf"{seg}(\|{seg})*", v) for v in kv_section(text, "HP").values())
        assert "PostgreSQL" not in text.split("N:")[0] + secs["TID"][0]
        assert "Thomas" not in text                       # dsd name
        # inside the JSON blobs (catalog / project / space) as well
        assert "Very Enterprise Catalog" not in text
        assert "My Little Project" not in text
        assert "My Little Space" not in text
        assert "Home Loan" not in text and "Personal Information" not in text
        assert_no_traces(text)

    def test_name_removed_also_inside_json_blobs_but_not_other_keys(self):
        text = ldf(graph(), ["name"])
        ca = json.loads(kv_section(text, "CA")["N1"])
        assert "name" not in ca[0]["catalog"] and ca[0]["catalog"]["id"]
        assert ca[0]["data_quality"] == {"score": 83.5}
        assert "name" not in ca[0]["business_terms"][0]
        assert ca[0]["business_terms"][0]["restricted"] is True

    def test_type_removed_at_asset_hp_and_edge_level(self):
        text = ldf(graph(), ["type"])
        secs = sections(text)
        assert "EP" not in secs                                   # edge types were the only EP content
        assert all(re.match(r"^N\d+(?: |$)", l) for l in secs["N"])   # no ":Column"
        for value in kv_section(text, "HP").values():
            for seg in value.split("|"):
                assert seg.count(":") == 1                        # id:name only
        assert "Database" not in text and "Schema" not in text
        assert_no_traces(text)

    def test_href_removed_everywhere_it_exists(self):
        text = ldf(graph(), ["href"])
        assert all(re.search(r" ch=0,0(?: |$)", l) for l in node_lines(text))

    def test_id_like_keys_nested_can_be_removed_by_name_only_when_not_the_record_id(self):
        # 'restricted' only exists inside the JSON blobs
        text = ldf(graph(), ["restricted"])
        assert "restricted" not in text

    def test_deeply_nested_name_inside_blob(self):
        text = ldf(graph(), ["row", "column"])
        scs = json.loads(kv_section(text, "SCS")["N1"])
        # row/column were the only content of the positions -> positions disappear
        assert "start_position" not in scs[0] and "end_position" not in scs[0]
        assert "{}" not in kv_section(text, "SCS")["N1"]
        assert scs[0]["id"] and scs[0]["source_code"]["id"]

    def test_multiple_names(self):
        text = ldf(graph(), ["children", "technology", "hierarchical_path"])
        assert all(" ch=" not in l and "path=" not in l for l in node_lines(text))
        secs = sections(text)
        assert not {"T", "TID", "HP"} & set(secs)
        assert_no_traces(text)

    def test_graph_level_keys(self):
        text = ldf(graph(), ["graph_calculation_datetime"])
        assert "dt=" not in text and "ts=1721636182694" in text
        text = ldf(graph(), ["graph_calculation_timestamp"])
        assert "ts=" not in text and "dt=2024-07-22T08:16:22.694Z" in text
        text = ldf(graph(), ["graph_calculation_datetime", "graph_calculation_timestamp"])
        assert sections(text)["GRAPH"] == ["lineage_graph"]

    def test_name_matches_edge_field_too(self):
        g = graph()
        g["edges_in_view"][0]["extra"] = {"keep": 1}
        # 'type' hits edge.type but 'extra' is not serialised anyway; only assert EP
        text = ldf(g, ["type"])
        assert "EP" not in sections(text) and "etype" not in text


# ---------------------------------------------------------------------------
# Dotted path: only that field
# ---------------------------------------------------------------------------

class TestDottedPath:
    def test_technology_id_only(self):
        text = ldf(graph(), ["technology.id"])
        secs = sections(text)
        assert "TID" not in secs
        assert secs["T"] == ["T1=PostgreSQL"]
        assert all("path=T1" in l for l in node_lines(text))      # still referenced
        assert_no_traces(text)

    def test_technology_name_only(self):
        text = ldf(graph(), ["technology.name"])
        secs = sections(text)
        assert "T" not in secs
        assert secs["TID"] == ["T1=cc52d03280b7034c8e3653d2748ebd489a873ef4bbc89cb187fbfcabfbbf6873"]
        assert_no_traces(text)

    def test_technology_both_fields_removes_whole_technology(self):
        text = ldf(graph(), ["technology.id", "technology.name"])
        secs = sections(text)
        assert not {"T", "TID"} & set(secs)
        assert all("path=" not in l for l in node_lines(text))
        assert_no_traces(text)

    def test_hierarchical_path_type_removes_only_hp_type(self):
        text = ldf(graph(), ["hierarchical_path.type"])
        node_types = [l.split(" ")[0] for l in node_lines(text)]
        assert node_types == ["N1:Column", "N2:Column"]           # asset type untouched
        assert "etype=direct" in text and "etype=summary" in text  # edge type untouched
        for value in kv_section(text, "HP").values():
            segs = value.split("|")
            assert len(segs) == 3
            for seg in segs:
                assert seg.count(":") == 1
        assert "Database" not in text
        assert_no_traces(text)

    def test_hierarchical_path_name_leaves_no_empty_slot(self):
        text = ldf(graph(), ["hierarchical_path.name"])
        for value in kv_section(text, "HP").values():
            for seg in value.split("|"):
                assert "::" not in seg
                assert re.fullmatch(r"i=[0-9a-f]+:t=\w+", seg), seg
        assert_no_traces(text)
        restored = lineage_format_to_json(text)
        hp = restored["assets_in_view"][0]["hierarchical_path"]
        assert hp[0] == {"id": BACKEND_RESPONSE["assets_in_view"][0]["hierarchical_path"][0]["id"],
                         "type": "Database"}

    def test_hierarchical_path_id_only(self):
        text = ldf(graph(), ["hierarchical_path.id"])
        for value in kv_section(text, "HP").values():
            assert "i=" not in value
            for seg in value.split("|"):
                assert seg.startswith("n=")
        restored = lineage_format_to_json(text)
        assert restored["assets_in_view"][0]["hierarchical_path"][1] == {"name": "s1", "type": "Schema"}

    def test_hierarchical_path_type_and_name_leaves_ids_only(self):
        text = ldf(graph(), ["hierarchical_path.type", "hierarchical_path.name"])
        hp = kv_section(text, "HP")["N1"].split("|")
        assert hp == [s["id"] for s in BACKEND_RESPONSE["assets_in_view"][0]["hierarchical_path"]]
        assert_no_traces(text)

    def test_hierarchical_path_all_fields_removes_hp(self):
        text = ldf(graph(), ["hierarchical_path.id", "hierarchical_path.name", "hierarchical_path.type"])
        assert "HP" not in sections(text)
        assert_no_traces(text)

    @pytest.mark.parametrize("field,expected_ch", [
        ("count", None),
        ("has_any", None),
        ("href", "ch=0,0"),
    ])
    def test_children_subfields(self, field, expected_ch):
        text = ldf(graph(), [f"children.{field}"])
        first = node_lines(text)[0]
        if expected_ch:
            assert re.search(rf" {re.escape(expected_ch)}(?: |$)", first)
        else:
            assert " ch=," not in first
        assert_no_traces(text)
        restored = lineage_format_to_json(text)["assets_in_view"][0]["children"]
        assert field not in restored
        assert set(restored) == {"count", "has_any", "href"} - {field}

    def test_children_count_and_has_any_leaves_href_only(self):
        text = ldf(graph(), ["children.count", "children.has_any"])
        assert re.search(r" chh=https://", node_lines(text)[0])
        assert_no_traces(text)
        ch = lineage_format_to_json(text)["assets_in_view"][0]["children"]
        assert ch == {"href": BACKEND_RESPONSE["assets_in_view"][0]["children"]["href"]}

    def test_children_all_subfields_removes_children(self):
        text = ldf(graph(), ["children.count", "children.has_any", "children.href"])
        assert not re.search(r" ch[cha]?=", " ".join(node_lines(text)))
        assert_no_traces(text)

    def test_children_href_with_comma_is_percent_encoded_in_named_form(self):
        g = one_asset_graph(children={"count": 1, "has_any": True, "href": "http://x/a,b c"})
        text = ldf(g, ["children.count"])
        restored = lineage_format_to_json(text)["assets_in_view"][0]["children"]
        assert restored == {"has_any": True, "href": "http://x/a,b c"}

    def test_dotted_does_not_hit_same_name_elsewhere(self):
        # 'technology.name' must not remove asset.name, hp.name or bt.name
        text = ldf(graph(), ["technology.name"])
        secs = sections(text)
        assert secs["NAME"] == ["N1=first_name", "N2=eye_color"]
        assert secs["BT"] == ["BT1=8d3641e9-841f-40d0-aa0b-f5e8e8b97186|Personal Information"]
        assert "postgres" in kv_section(text, "HP")["N1"]

    def test_dotted_does_not_hit_same_name_at_other_depth(self):
        # 'catalog.id' is not reachable as 'catalog_assignments.catalog.id' ... but is a real path
        g = graph()
        text = ldf(g, ["catalog_assignments.catalog.id"])
        ca = json.loads(kv_section(text, "CA")["N1"])
        assert "id" not in ca[0]["catalog"] and ca[0]["catalog"]["name"] == "Very Enterprise Catalog"
        pa = json.loads(kv_section(text, "PA")["N1"])
        assert pa[0]["project"]["id"]                      # untouched

    def test_dotted_path_through_array_without_index(self):
        text = ldf(graph(), ["catalog_assignments.business_terms.restricted"])
        ca = json.loads(kv_section(text, "CA")["N1"])
        assert "restricted" not in ca[0]["business_terms"][0]
        assert ca[0]["business_classifications"][0]["restricted"] is True
        pa = json.loads(kv_section(text, "PA")["N1"])
        assert pa[0]["business_terms"][0]["restricted"] is True

    def test_dotted_path_with_index_is_unknown_and_ignored(self):
        base = ldf(graph(), [])
        assert ldf(graph(), ["hierarchical_path.0.type"]) == base
        assert ldf(graph(), ["hierarchical_path[0].type"]) == base
        assert ldf(graph(), ["hierarchical_path.*.type"]) == base   # '*' would need to be an array level

    def test_dotted_path_deep_in_blob(self):
        text = ldf(graph(), ["source_code_snippets.start_position.row"])
        scs = json.loads(kv_section(text, "SCS")["N1"])
        assert scs[0]["start_position"] == {"column": 55}
        assert scs[0]["end_position"] == {"row": 35, "column": 65}

    def test_dotted_path_must_match_whole_path(self):
        base = ldf(graph(), [])
        assert ldf(graph(), ["position.row"]) == base
        assert ldf(graph(), ["start_position.row"]) == base      # not relative to a nested object

    def test_dsd_subfields(self):
        t = ldf(graph(), ["data_source_definition_asset.name"])
        assert set(kv_section(t, "DSD").values()) == {"db4341e3-029c-45f4-b136-743ca2ad7c81"}
        r = lineage_format_to_json(t)["assets_in_view"][0]["data_source_definition_asset"]
        assert r == {"id": "db4341e3-029c-45f4-b136-743ca2ad7c81"}
        t = ldf(graph(), ["data_source_definition_asset.id"])
        assert set(kv_section(t, "DSD").values()) == {"n=Thomas%20the%20DSD%20asset"}
        r = lineage_format_to_json(t)["assets_in_view"][0]["data_source_definition_asset"]
        assert r == {"name": "Thomas the DSD asset"}
        t = ldf(graph(), ["data_source_definition_asset.id", "data_source_definition_asset.name"])
        assert "DSD" not in sections(t)

    @pytest.mark.parametrize("key,prefix", [
        ("business_terms", "BT"), ("business_classifications", "BC"), ("data_classes", "DC"),
    ])
    def test_lookup_subfields(self, key, prefix):
        t = ldf(graph(), [f"{key}.name"])
        assert all("|" not in v for v in kv_section(t, prefix).values())
        t = ldf(graph(), [f"{key}.id"])
        assert all(v.startswith("n=") for v in kv_section(t, prefix).values())
        r = lineage_format_to_json(t)["assets_in_view"][0][key]
        assert r == [{"name": BACKEND_RESPONSE["assets_in_view"][0][key][0]["name"]}]
        t = ldf(graph(), [f"{key}.id", f"{key}.name"])
        assert prefix not in sections(t)
        assert not re.search(rf" {prefix.lower()}=", " ".join(node_lines(t)))

    def test_attributes_subfields(self):
        t = ldf(graph(), ["attributes.value"])
        assert kv_section(t, "ATTR") == {"N1": "COLUMN_CONSTRAINT"}
        assert lineage_format_to_json(t)["assets_in_view"][0]["attributes"] == [{"name": "COLUMN_CONSTRAINT"}]
        t = ldf(graph(), ["attributes.name"])
        assert kv_section(t, "ATTR") == {"N1": "=primary%20key"}
        assert lineage_format_to_json(t)["assets_in_view"][0]["attributes"] == [{"name": "", "value": "primary key"}]
        t = ldf(graph(), ["attributes.name", "attributes.value"])
        assert "ATTR" not in sections(t)


# ---------------------------------------------------------------------------
# Removing an object / array removes all of its content
# ---------------------------------------------------------------------------

class TestWholeContainers:
    def test_technology_object(self):
        text = ldf(graph(), ["technology"])
        secs = sections(text)
        assert not {"T", "TID"} & set(secs)
        assert all("path=" not in l for l in node_lines(text))
        assert "cc52d03280b7" not in text                     # technology id
        assert not re.search(r"(?m)^(T|TID)[=:]", text)
        assert_no_traces(text)

    def test_hierarchical_path_array(self):
        text = ldf(graph(), ["hierarchical_path"])
        assert "HP" not in sections(text)
        assert "6b86b273ff34" not in text                     # root hierarchical_path id
        assert "Schema" not in text and ":Table" not in text
        assert_no_traces(text)

    @pytest.mark.parametrize("key,section", [
        ("source_code_snippets", "SCS"),
        ("catalog_assignments", "CA"),
        ("project_assignments", "PA"),
        ("space_assignments", "SA"),
        ("attributes", "ATTR"),
        ("data_source_definition_asset", "DSD"),
    ])
    def test_container_removes_section(self, key, section):
        text = ldf(graph(), [key])
        assert section not in sections(text)
        assert_no_traces(text)

    def test_lookup_arrays_remove_lookup_and_references(self):
        text = ldf(graph(), ["business_terms", "business_classifications", "data_classes"])
        secs = sections(text)
        assert not {"BT", "BC", "DC"} & set(secs)
        assert not re.search(r" (bt|bc|dc)=", " ".join(node_lines(text)))
        assert_no_traces(text)

    def test_nested_container_inside_blob_removes_all_content(self):
        text = ldf(graph(), ["source_code"])
        scs = json.loads(kv_section(text, "SCS")["N1"])
        assert "source_code" not in scs[0] and "740958c5" not in text

    def test_container_whose_children_are_all_excluded_disappears(self):
        text = ldf(graph(), ["source_code_snippets.source_code.id"])
        scs = json.loads(kv_section(text, "SCS")["N1"])
        assert "source_code" not in scs[0]                  # became empty -> removed, not {}
        assert "{}" not in kv_section(text, "SCS")["N1"]
        assert scs[0]["id"]                                 # siblings untouched

    def test_array_whose_items_are_all_excluded_disappears(self):
        g = one_asset_graph(attributes=[{"name": "A", "value": "1"}])
        text = ldf(g, ["name", "value"])
        assert "ATTR" not in sections(text)

    def test_snippet_that_becomes_empty_is_dropped_not_kept_as_empty_object(self):
        g = one_asset_graph(source_code_snippets=[{"id": "x"}, {"id": "y", "keep": 1}])
        text = ldf(g, ["source_code_snippets.id"])
        assert json.loads(kv_section(text, "SCS")["N1"]) == [{"keep": 1}]
        g = one_asset_graph(source_code_snippets=[{"id": "x"}, {"id": "y"}])
        assert "SCS" not in sections(ldf(g, ["source_code_snippets.id"]))

    def test_star_removes_the_top_level_lists_and_leaves_an_empty_graph(self):
        # '*' matches the top-level keys, i.e. whole assets_in_view / edges_in_view
        text = ldf(graph(), ["*"])
        assert lineage_format_to_json(text) == {"assets_in_view": [], "edges_in_view": []}

    def test_container_excluded_with_extra_dotted_entry_still_fine(self):
        t1 = ldf(graph(), ["technology"])
        t2 = ldf(graph(), ["technology", "technology.id"])
        assert t1 == t2


# ---------------------------------------------------------------------------
# Wildcards (fnmatch)
# ---------------------------------------------------------------------------

class TestWildcards:
    def test_is_star_removes_all_flags(self):
        g = graph()
        for k in ("is_deduced", "is_favorite"):
            g["assets_in_view"][0][k] = True
        assert "flags=" in ldf(g, [])
        text = ldf(g, ["is_*"])
        assert "flags=" not in text
        assert_no_traces(text)

    def test_flags_partial_wildcard(self):
        g = graph()
        a = g["assets_in_view"][0]
        a.update(is_deduced=True, is_transforming=True, is_operational=True, is_temporary=True, is_favorite=True)
        text = ldf(g, ["is_t*"])             # transforming + temporary (2 + 8) removed
        assert "flags=%d" % (1 + 4 + 16) in node_lines(text)[0]
        restored = lineage_format_to_json(text)["assets_in_view"][0]
        assert restored["is_deduced"] and restored["is_operational"] and restored["is_favorite"]
        assert not restored["is_transforming"] and not restored["is_temporary"]

    def test_star_assignments(self):
        text = ldf(graph(), ["*_assignments"])
        assert not {"CA", "PA", "SA"} & set(sections(text))
        assert "SCS" in sections(text)
        assert_no_traces(text)

    def test_star_assignments_also_matches_nested_keys_of_that_shape(self):
        g = one_asset_graph(catalog_assignments=[{"user_assignments": [{"u": 1}], "group_assignments": [], "k": 2}],)
        text = ldf(g, ["*_assignments"])
        assert "CA" not in sections(text)

    def test_wildcard_inside_blob(self):
        text = ldf(graph(), ["*_position"])
        scs = json.loads(kv_section(text, "SCS")["N1"])
        assert set(scs[0]) == {"id", "source_code", "lineage_version_timestamps"}

    def test_question_mark_and_bracket(self):
        base = ldf(graph(), [])
        assert ldf(graph(), ["tag?"]) != base or "tags=" not in ldf(graph(), ["tag?"])
        text = ldf(graph(), ["tag?"])
        assert "tags=" not in text
        text = ldf(graph(), ["[ot]*igin"])
        assert " origin=" not in text

    def test_wildcard_in_dotted_segments(self):
        text = ldf(graph(), ["hierarchical_path.*"])
        assert "HP" not in sections(text)
        text = ldf(graph(), ["technology.*"])
        assert not {"T", "TID"} & set(sections(text))
        text = ldf(graph(), ["children.*"])
        assert all(" ch" not in l for l in node_lines(text))
        text = ldf(graph(), ["h*.type"])
        assert not any(":Database" in l or ":Schema" in l for l in sections(text)["HP"])
        text = ldf(graph(), ["*.name"])
        secs = sections(text)
        assert "NAME" in secs                # asset.name is top-level, not 'x.name'
        assert "T" not in secs               # technology.name
        assert "Home Loan" not in "".join(secs.get("BC", []))
        assert all("n=" not in v for v in kv_section(text, "HP").values())

    def test_wildcard_is_case_sensitive(self):
        base = ldf(graph(), [])
        assert ldf(graph(), ["TECHNOLOGY"]) == base
        assert ldf(graph(), ["Is_*"]) == base

    def test_wildcard_matching_a_required_field_raises(self):
        for ex in (["i?"], ["so*ce"], ["tar*"]):
            with pytest.raises(ValueError):
                ldf(graph(), ex)

    def test_wildcard_that_matches_nothing_is_ignored(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="ldf.converter"):
            assert ldf(graph(), ["zzz*"]) == ldf(graph(), [])
        assert any("zzz*" in r.getMessage() for r in caplog.records)

    def test_wildcard_also_works_on_graph_level_keys(self):
        text = ldf(graph(), ["graph_calculation_*"])
        assert sections(text)["GRAPH"] == ["lineage_graph"]


# ---------------------------------------------------------------------------
# No traces in output
# ---------------------------------------------------------------------------

class TestNoTraces:
    def test_technology_excluded_no_tech_tokens_or_lookups(self):
        text = ldf(graph(), ["technology"])
        assert "path=" not in text and "\nT:" not in text and "\nTID:" not in text
        assert not re.search(r"(?m)^T\d+=", text)           # no technology lookup rows

    def test_hierarchical_path_excluded_no_hp_and_no_parent_index(self):
        text = ldf(graph(), ["hierarchical_path"])
        assert "\nHP:" not in text
        assert "6b86b273ff34" not in text      # root HP id appears nowhere

    def test_header_has_no_dt_ts_when_excluded(self):
        text = ldf(graph(), ["graph_calculation_datetime", "graph_calculation_timestamp"])
        assert text.startswith("GRAPH:\nlineage_graph\n\nSTART:")
        assert "dt=" not in text and "ts=" not in text

    def test_ep_removed_when_edge_type_excluded(self):
        text = ldf(graph(), ["type"])
        assert "EP:" not in text
        assert "E:\nN1>N2\nN2>N1" in text

    def test_ep_kept_for_edges_when_other_edge_fields_excluded(self):
        text = ldf(graph(), ["technology"])
        assert sections(text)["EP"] == ["N1>N2 etype=direct", "N2>N1 etype=summary"]

    def test_everything_optional_excluded_leaves_minimal_valid_document(self):
        everything = [
            "name", "type", "identity_key", "resource_key", "origin", "technology",
            "hierarchical_path", "children", "tags", "attributes", "source_code_snippets",
            "business_terms", "business_classifications", "data_classes", "*_assignments",
            "data_source_definition_asset", "is_*",
            "graph_calculation_datetime", "graph_calculation_timestamp",
        ]
        text = ldf(graph(), everything)
        secs = sections(text)
        assert set(secs) == {"GRAPH", "START", "E", "N", "ID"}
        assert secs["GRAPH"] == ["lineage_graph"]
        assert secs["N"] == ["N1", "N2"]
        assert_no_traces(text)
        restored = lineage_format_to_json(text)
        assert [a["id"] for a in restored["assets_in_view"]] == [a["id"] for a in BACKEND_RESPONSE["assets_in_view"]]
        assert len(restored["edges_in_view"]) == 2

    def test_no_blank_sections_with_every_single_name(self):
        names = ["name", "type", "technology", "hierarchical_path", "children", "tags", "attributes",
                 "origin", "resource_key", "data_source_definition_asset", "business_terms",
                 "business_classifications", "data_classes", "source_code_snippets",
                 "catalog_assignments", "project_assignments", "space_assignments", "is_deduced"]
        for name in names:
            assert_no_traces(ldf(graph(), [name]))

    def test_tags_excluded_no_empty_array(self):
        text = ldf(graph(), ["tags"])
        assert "tags=" not in text

    def test_compact_mode_has_no_blank_lines_and_no_traces(self):
        text = ldf(graph(), ["technology", "hierarchical_path", "children"], compact=True)
        assert "\n\n" not in text
        assert_no_traces(text)

    def test_normal_mode_has_exactly_one_blank_line_between_sections(self):
        text = ldf(graph(), ["technology", "hierarchical_path", "children"])
        assert "\n\n\n" not in text and not text.endswith("\n")

    def test_no_trailing_separators_on_bt_bc_dc_without_name(self):
        text = ldf(graph(), ["name"])
        for sec in ("BT", "BC", "DC"):
            for v in kv_section(text, sec).values():
                assert "|" not in v

    def test_node_line_has_no_double_spaces_with_type_excluded(self):
        text = ldf(graph(), ["type", "origin", "resource_key"])
        for l in node_lines(text):
            assert "  " not in l and not l.endswith(" ")
            assert re.match(r"^N\d+(?: \w+=.*)?$", l)

    def test_excluded_asset_name_leaves_no_name_row(self):
        text = ldf(graph(), ["name"])
        assert "NAME" not in sections(text)


# ---------------------------------------------------------------------------
# Decoder compatibility / round trip
# ---------------------------------------------------------------------------

class TestRoundTripWithExclusions:
    @staticmethod
    def _expected(exclude_top, asset):
        return {k: v for k, v in asset.items() if k not in exclude_top}

    def test_untouched_fields_survive_exactly(self):
        text = ldf(graph(), ["technology", "children", "hierarchical_path"])
        restored = lineage_format_to_json(text)
        for orig, got in zip(BACKEND_RESPONSE["assets_in_view"], restored["assets_in_view"]):
            for key in ("id", "name", "type", "resource_key", "origin", "tags", "attributes",
                        "business_terms", "business_classifications", "data_classes",
                        "catalog_assignments", "project_assignments", "space_assignments",
                        "source_code_snippets", "data_source_definition_asset",
                        "is_deduced", "is_transforming", "is_operational", "is_temporary", "is_favorite"):
                assert got[key] == orig[key], key

    def test_excluded_objects_are_absent_not_empty(self):
        restored = lineage_format_to_json(ldf(graph(), ["technology", "data_source_definition_asset"]))
        for a in restored["assets_in_view"]:
            assert "technology" not in a and "data_source_definition_asset" not in a

    def test_excluded_children_is_none_like_legacy_missing(self):
        restored = lineage_format_to_json(ldf(graph(), ["children"]))
        assert all(a["children"] is None for a in restored["assets_in_view"])

    def test_excluded_hp_decodes_to_empty_list(self):
        restored = lineage_format_to_json(ldf(graph(), ["hierarchical_path"]))
        assert all(a["hierarchical_path"] == [] for a in restored["assets_in_view"])

    def test_edges_and_header_survive(self):
        restored = lineage_format_to_json(ldf(graph(), ["technology", "name"]))
        assert restored["edges_in_view"] == BACKEND_RESPONSE["edges_in_view"]
        assert restored["graph_calculation_datetime"] == BACKEND_RESPONSE["graph_calculation_datetime"]
        assert restored["graph_calculation_timestamp"] == BACKEND_RESPONSE["graph_calculation_timestamp"]

    def test_edge_type_excluded(self):
        restored = lineage_format_to_json(ldf(graph(), ["type"]))
        assert all("type" not in e for e in restored["edges_in_view"])

    def test_header_excluded(self):
        restored = lineage_format_to_json(ldf(graph(), ["graph_calculation_*"]))
        assert "graph_calculation_datetime" not in restored and "graph_calculation_timestamp" not in restored

    def test_type_excluded_decodes_with_empty_type(self):
        restored = lineage_format_to_json(ldf(graph(), ["type"]))
        assert all(a["type"] == "" for a in restored["assets_in_view"])
        assert [a["name"] for a in restored["assets_in_view"]] == ["first_name", "eye_color"]

    def test_type_excluded_with_no_other_tokens(self):
        g = {"assets_in_view": [{"id": "a", "type": "T", "name": "n"}], "edges_in_view": []}
        text = ldf(g, ["type"])
        assert node_lines(text) == ["N1"]
        assert lineage_format_to_json(text)["assets_in_view"][0]["id"] == "a"

    def test_special_characters_still_round_trip_next_to_exclusions(self):
        g = one_asset_graph(name="a b|c=d,e[f]\ng%h", tags=["x y", "a,b"],
                            resource_key="DB/my schema/t", origin="user input")
        restored = lineage_format_to_json(ldf(g, ["technology", "children"]))["assets_in_view"][0]
        assert restored["name"] == "a b|c=d,e[f]\ng%h"
        assert restored["tags"] == ["x y", "a,b"]
        assert restored["resource_key"] == "DB/my schema/t"
        assert restored["origin"] == "user input"

    def test_exclusion_output_is_a_fixed_point(self):
        for ex in (["children.count"], ["hierarchical_path.name"], ["business_terms.id"],
                   ["data_source_definition_asset.id"], ["attributes.name"], ["type"], ["name"]):
            once = lineage_format_to_json(ldf(graph(), ex))
            twice = lineage_format_to_json(ldf(once, ex))
            assert twice == once, ex

    def test_gap_forms_with_special_characters(self):
        g = one_asset_graph(hierarchical_path=[{"id": "i1", "name": "My:Sch|ema=x y", "type": "T:y"}])
        for ex, want in ((["hierarchical_path.id"], {"name": "My:Sch|ema=x y", "type": "T:y"}),
                         (["hierarchical_path.name"], {"id": "i1", "type": "T:y"})):
            hp = lineage_format_to_json(ldf(g, ex))["assets_in_view"][0]["hierarchical_path"]
            assert hp == [want]

    def test_lookup_name_with_special_chars_and_id_excluded(self):
        g = one_asset_graph(business_terms=[{"id": "t1", "name": "Pers|onal Info=1"}])
        bt = lineage_format_to_json(ldf(g, ["business_terms.id"]))["assets_in_view"][0]["business_terms"]
        assert bt == [{"name": "Pers|onal Info=1"}]

    def test_dedup_of_lookups_still_works_after_exclusion(self):
        g = graph()
        text = ldf(g, ["business_terms.name"])
        assert kv_section(text, "BT") == {"BT1": "8d3641e9-841f-40d0-aa0b-f5e8e8b97186"}

    def test_two_different_ids_are_not_merged_when_names_excluded(self):
        g = one_asset_graph(business_terms=[{"id": "t1", "name": "Same"}, {"id": "t2", "name": "Same"}])
        text = ldf(g, ["business_terms.name"])
        assert kv_section(text, "BT") == {"BT1": "t1", "BT2": "t2"}

    def test_two_names_with_same_id_are_not_merged_when_nothing_excluded(self):
        g = one_asset_graph(business_terms=[{"id": "t1", "name": "A"}, {"id": "t1", "name": "B"}])
        text = ldf(g, [])
        assert len(kv_section(text, "BT")) == 2

    def test_technology_dedup_by_id_still_works_when_name_excluded(self):
        a = copy.deepcopy(BACKEND_RESPONSE["assets_in_view"][0])
        b = copy.deepcopy(BACKEND_RESPONSE["assets_in_view"][1])
        b["technology"] = {"id": "other", "name": "PostgreSQL"}
        g = {"assets_in_view": [a, b], "edges_in_view": []}
        text = ldf(g, ["technology.name"])
        assert len(kv_section(text, "TID")) == 2 and "T" not in sections(text)


# ---------------------------------------------------------------------------
# Token savings
# ---------------------------------------------------------------------------

class TestSize:
    def test_output_is_smaller_for_every_effective_exclusion(self):
        base = len(ldf(graph(), []))
        for ex in (["children"], ["technology"], ["hierarchical_path"], ["*_assignments"],
                   ["source_code_snippets"], ["attributes"], ["name"], ["type"]):
            assert len(ldf(graph(), ex)) < base, ex

    def test_more_exclusions_never_grow_the_output(self):
        a = len(ldf(graph(), ["children"]))
        b = len(ldf(graph(), ["children", "technology"]))
        c = len(ldf(graph(), ["children", "technology", "hierarchical_path"]))
        assert a >= b >= c

    def test_order_of_entries_and_duplicates_do_not_matter(self):
        assert ldf(graph(), ["children", "technology"]) == ldf(graph(), ["technology", "children", "children"])


# ---------------------------------------------------------------------------
# Real backend response: big_query_lineage.json
# ---------------------------------------------------------------------------

BIG = Path(__file__).resolve().parent.parent / "big_query_lineage.json"
needs_big = pytest.mark.skipif(not BIG.exists(), reason="big_query_lineage.json not present (git-ignored)")

# Fields the LDF format carries (descendant_statistics is not part of LDF).
CARRIED = {
    "id", "name", "type", "identity_key", "hierarchical_path", "children", "is_favorite", "tags",
    "technology", "attributes", "source_code_snippets", "business_terms", "business_classifications",
    "data_classes", "catalog_assignments", "project_assignments", "space_assignments",
    "is_deduced", "is_transforming", "is_operational", "is_temporary", "origin",
    "data_source_definition_asset", "resource_key",
}


def _load_big():
    with open(BIG, encoding="utf-8") as f:
        return json.load(f)


def _key_paths(node, prefix=()):
    if isinstance(node, dict):
        for k, v in node.items():
            yield prefix + (k,)
            yield from _key_paths(v, prefix + (k,))
    elif isinstance(node, list):
        for item in node:
            yield from _key_paths(item, prefix)


def _all_paths():
    if not BIG.exists():
        return []
    g = _load_big()
    found = set()
    for rec in g["assets_in_view"] + g["edges_in_view"]:
        found |= set(_key_paths(rec))
    return sorted(found)


_PATHS = _all_paths()
_NAMES = sorted({p[-1] for p in _PATHS} - {"id", "source", "target"})
_DOTTED = sorted({".".join(p) for p in _PATHS if len(p) > 1} - {"children.id"})
_GONE = object()


def reference_prune(node, path, patterns):
    """Independent re-implementation of the specified matching rules."""
    def hit(p):
        for pat in patterns:
            if len(pat) == 1 and fnmatch.fnmatchcase(p[-1], pat[0]):
                return True
            if len(pat) > 1 and len(pat) == len(p) and all(fnmatch.fnmatchcase(a, b) for a, b in zip(p, pat)):
                return True
        return False

    if isinstance(node, dict):
        out, removed = {}, False
        for k, v in node.items():
            p = path + (k,)
            if hit(p):
                removed = True
                continue
            c = reference_prune(v, p, patterns)
            if c is _GONE:
                removed = True
                continue
            out[k] = c
        return _GONE if removed and not out else out
    if isinstance(node, list):
        out, removed = [], False
        for item in node:
            c = reference_prune(item, path, patterns)
            if c is _GONE:
                removed = True
                continue
            out.append(c)
        return _GONE if removed and not out else out
    return node


def _empty(v):
    return v in (None, [], {}, False, "")


def subset_diff(expected, got, where="$"):
    """expected must be fully present in got; extras in got must be empty decoder defaults."""
    errs = []
    if isinstance(expected, dict) and isinstance(got, dict):
        for k in expected:
            if k not in got:
                errs.append(f"{where}.{k} missing")
            else:
                errs += subset_diff(expected[k], got[k], f"{where}.{k}")
        errs += [f"{where}.{k} unexpected {got[k]!r}" for k in got if k not in expected and not _empty(got[k])]
    elif isinstance(expected, list) and isinstance(got, list):
        if len(expected) != len(got):
            errs.append(f"{where} length {len(expected)} != {len(got)}")
        else:
            for i, (e, g_) in enumerate(zip(expected, got)):
                errs += subset_diff(e, g_, f"{where}[{i}]")
    elif expected != got:
        errs.append(f"{where}: {expected!r} != {got!r}")
    return errs


def expected_graph(g, exclude):
    pats = [tuple(x.split(".")) for x in exclude]
    assets = []
    for a in g["assets_in_view"]:
        e = reference_prune({k: v for k, v in a.items() if k in CARRIED}, (), pats)
        assets.append({} if e is _GONE else e)
    edges = []
    for e in g["edges_in_view"]:
        if "target" not in e:      # legacy decoder drops edges without target
            continue
        x = reference_prune(e, (), pats)
        edges.append({} if x is _GONE else x)
    return assets, edges


@pytest.fixture(scope="module")
def big():
    return _load_big()


@needs_big
class TestBigQueryLineage:
    # --- sanity of the data set itself -------------------------------------------------

    def test_dataset_shape(self, big):
        assert len(big["assets_in_view"]) == 31
        assert len(big["edges_in_view"]) == 50
        assert sum("target" not in e for e in big["edges_in_view"]) == 20   # real-world quirk we must tolerate

    # --- defaults ----------------------------------------------------------------------

    @pytest.mark.parametrize("options", [None, {}, {"exclude_fields": []}, {"exclude_fields": None},
                                         {"exclude_fields": ["not_there", "a.b", "IS_*"]}])
    def test_default_output_unchanged(self, big, options):
        assert json_to_lineage_format(big, options) == json_to_lineage_format(big)

    def test_default_round_trip_is_lossless_for_carried_fields(self, big):
        restored = lineage_format_to_json(json_to_lineage_format(big))
        assets, edges = expected_graph(big, [])
        for exp, got in zip(assets, restored["assets_in_view"]):
            assert subset_diff(exp, got) == []
        assert restored["edges_in_view"] == edges

    def test_edges_without_target_are_preserved_in_text(self, big):
        text = json_to_lineage_format(big, {"exclude_fields": ["technology"]})
        e_lines = sections(text)["E"]
        assert len(e_lines) == 50
        assert not any(">" in l and l.endswith(">") for l in e_lines)     # no dangling "N7>"
        assert len([l for l in e_lines if ">" not in l]) == 20            # end edges are bare "N7"

    def test_input_not_mutated(self, big):
        before = copy.deepcopy(big)
        json_to_lineage_format(big, {"exclude_fields": ["technology", "children.href", "is_*", "*_position"]})
        assert big == before

    # --- header ------------------------------------------------------------------------

    def test_header_lines(self, big):
        full = json_to_lineage_format(big)
        assert f"dt={big['graph_calculation_datetime']}" in full and f"ts={big['graph_calculation_timestamp']}" in full
        t = ldf(big, ["graph_calculation_datetime"])
        assert "dt=" not in t and f"ts={big['graph_calculation_timestamp']}" in t
        t = ldf(big, ["graph_calculation_timestamp"])
        assert "ts=" not in t and "dt=" in t
        t = ldf(big, ["graph_calculation_*"])
        assert sections(t)["GRAPH"] == ["lineage_graph"]

    # --- specific, hand-checkable behaviours -------------------------------------------

    def test_technology(self, big):
        t = ldf(big, ["technology"])
        assert "path=" not in t and not {"T", "TID"} & set(sections(t))
        assert "Microsoft SQL Server" not in t
        assert_no_traces(t)

    def test_hierarchical_path_type_only(self, big):
        t = ldf(big, ["hierarchical_path.type"])
        assert not any(":Database" in l or ":Schema" in l or ":Table" in l for l in sections(t)["HP"])
        for value in kv_section(t, "HP").values():
            assert all(seg.count(":") == 1 for seg in value.split("|"))
        types = {l.split(" ")[0].split(":", 1)[1] for l in node_lines(t)}
        assert types == {"Column", "CreateViewScript"}                    # asset types untouched
        assert "etype=direct" in t and "etype=summary" in t               # edge types untouched
        assert_no_traces(t)

    def test_children_subfields(self, big):
        t = ldf(big, ["children.count"])
        assert all((" cha=" in l and " chh=" in l) for l in node_lines(t))
        t = ldf(big, ["children.href"])
        assert all(re.search(r" ch=\d+,[01](?: |$)", l) for l in node_lines(t))
        t = ldf(big, ["children"])
        assert all(" ch" not in l for l in node_lines(t))
        assert_no_traces(t)

    def test_descendant_statistics_is_ignored_by_format_so_exclusion_is_noop(self, big):
        assert ldf(big, ["descendant_statistics"]) == json_to_lineage_format(big)
        assert ldf(big, ["number_of_leaf_descendants"]) == json_to_lineage_format(big)

    def test_wildcards(self, big):
        t = ldf(big, ["is_*"])
        assert "flags=" not in t
        t = ldf(big, ["*_assignments"])
        assert not {"CA", "PA", "SA"} & set(sections(t))
        t = ldf(big, ["*_position"])
        for v in kv_section(t, "SCS").values():
            assert "start_position" not in v and "end_position" not in v

    def test_source_code_snippets_container(self, big):
        t = ldf(big, ["source_code_snippets"])
        assert "SCS" not in sections(t)
        t = ldf(big, ["source_code_snippets.start_position.row"])
        scs = json.loads(next(iter(kv_section(t, "SCS").values())))
        assert scs[0]["start_position"] == {"column": 1}

    def test_removing_everything_optional_gives_minimal_graph(self, big):
        everything = sorted(CARRIED - {"id"}) + ["graph_calculation_datetime", "graph_calculation_timestamp"]
        t = ldf(big, everything)
        assert set(sections(t)) == {"GRAPH", "START", "E", "N", "ID"}   # 'type' also covers edge types
        assert_no_traces(t)
        restored = lineage_format_to_json(t)
        assert [a["id"] for a in restored["assets_in_view"]] == [a["id"] for a in big["assets_in_view"]]

    def test_required_fields_raise(self, big):
        for ex in (["id"], ["source"], ["i?"]):
            with pytest.raises(ValueError):
                ldf(big, ex)
        with pytest.raises(ValueError):
            ldf(big, ["target"])          # 30 edges do have a target

    def test_size_reduction(self, big):
        base = len(json_to_lineage_format(big))
        slim = len(ldf(big, ["descendant_statistics", "children", "technology", "hierarchical_path",
                            "data_source_definition_asset", "identity_key", "is_*", "*_assignments",
                            "source_code_snippets"]))
        assert slim < base * 0.6

    # --- exhaustive: every name, every dotted path, every single-entry exclusion -------

    @pytest.mark.parametrize("entry", _NAMES + _DOTTED)
    def test_every_single_entry(self, big, entry):
        self._check(big, [entry])

    @pytest.mark.parametrize("exclude", [
        ["is_*"], ["*_assignments"], ["*_position"], ["h*"], ["te*"], ["?ags"], ["number_of_*"],
        ["hierarchical_path.*"], ["children.*"], ["technology.*"], ["data_source_definition_asset.*"],
        ["attributes.*"], ["source_code_snippets.*"], ["source_code_snippets.*_position"],
        ["source_code_snippets.*_position.*"], ["h*.type"], ["*.name"], ["*.type"],
        ["technology", "hierarchical_path"],
        ["children.href", "hierarchical_path.type", "technology.id"],
        ["children.count", "children.has_any", "children.href"],
        ["technology.id", "technology.name", "hierarchical_path.id", "hierarchical_path.name"],
        ["name", "type", "origin"],
        ["name", "identity_key", "origin", "is_*", "*_assignments", "attributes"],
    ])
    def test_wildcards_and_combinations(self, big, exclude):
        self._check(big, exclude)

    def test_randomised_combinations(self, big):
        import random
        rng = random.Random(1234)
        pool = _NAMES + _DOTTED + ["is_*", "*_assignments", "*_position", "number_of_*", "nope", "a.b"]
        for _ in range(400):
            exclude = rng.sample(pool, rng.randint(1, 8))
            self._check(big, exclude, compact=rng.random() < 0.5)

    @staticmethod
    def _check(big, exclude, compact=False):
        label = f"exclude={exclude} compact={compact}"
        text = json_to_lineage_format(big, {"exclude_fields": exclude, "compact": compact})
        assert_no_traces(text)
        if compact:
            assert "\n\n" not in text
        restored = lineage_format_to_json(text)

        exp_assets, exp_edges = expected_graph(big, exclude)
        assert len(restored["assets_in_view"]) == len(exp_assets), label
        for i, (exp, got) in enumerate(zip(exp_assets, restored["assets_in_view"])):
            diffs = subset_diff(exp, got, f"asset[{i}]")
            assert diffs == [], f"{label}: {diffs[:3]}"
        assert len(restored["edges_in_view"]) == len(exp_edges), label
        for i, (exp, got) in enumerate(zip(exp_edges, restored["edges_in_view"])):
            assert subset_diff(exp, got, f"edge[{i}]") == [], label

        pats = [tuple(x.split(".")) for x in exclude]
        hit_dt = any(len(p) == 1 and fnmatch.fnmatchcase("graph_calculation_datetime", p[0]) for p in pats)
        hit_ts = any(len(p) == 1 and fnmatch.fnmatchcase("graph_calculation_timestamp", p[0]) for p in pats)
        assert ("dt=" in text) == (not hit_dt), label
        assert ("ts=" in text) == (not hit_ts), label

        # re-serialising the decoded graph with the same exclusions is a fixed point
        again = lineage_format_to_json(json_to_lineage_format(restored, {"exclude_fields": exclude, "compact": compact}))
        assert again == restored, label


# ---------------------------------------------------------------------------
# CLI / file-level API
# ---------------------------------------------------------------------------

class TestCli:
    def _run(self, argv, tmp_path, data=None):
        from ldf.cli import main
        src = tmp_path / "in.json"
        src.write_text(json.dumps(data if data is not None else BACKEND_RESPONSE))
        out = tmp_path / "out.ldf"
        import sys
        old = sys.argv
        sys.argv = ["ldf", "json-to-lineage", str(src), str(out), *argv]
        try:
            main()
        finally:
            sys.argv = old
        return out.read_text()

    def test_without_exclude_output_is_unchanged(self, tmp_path):
        assert self._run([], tmp_path) == json_to_lineage_format(BACKEND_RESPONSE)

    def test_comma_separated(self, tmp_path):
        text = self._run(["--exclude", "children,technology"], tmp_path)
        assert text == ldf(graph(), ["children", "technology"])

    def test_repeated_option_and_whitespace(self, tmp_path):
        text = self._run(["--exclude", "children, technology", "--exclude", "is_*"], tmp_path)
        assert text == ldf(graph(), ["children", "technology", "is_*"])

    def test_with_compact(self, tmp_path):
        text = self._run(["--compact", "--exclude", "children"], tmp_path)
        assert text == ldf(graph(), ["children"], compact=True)

    def test_requested_field_set(self, tmp_path):
        names = ["children", "descendant_statistics", "is_favorite", "source_code_snippets"]
        text = self._run(["--exclude", ",".join(names)], tmp_path)
        assert text == ldf(graph(), names)
        assert "SCS" not in sections(text)

    def test_required_field_error_exits_nonzero(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as exc:
            self._run(["--exclude", "id"], tmp_path)
        assert exc.value.code == 1
        assert "required" in capsys.readouterr().err

    def test_convert_json_file_to_lineage_accepts_exclude_fields(self, tmp_path):
        from ldf import convert_json_file_to_lineage  # type: ignore
        src, out = tmp_path / "a.json", tmp_path / "a.ldf"
        src.write_text(json.dumps(BACKEND_RESPONSE))
        convert_json_file_to_lineage(str(src), str(out), exclude_fields=["children"])
        assert out.read_text() == ldf(graph(), ["children"])


class TestEndEdges:
    """An edge without a target is an end edge: written as "N7", never "N7>"."""

    @staticmethod
    def _g():
        g = graph()
        del g["edges_in_view"][0]["target"]
        return g

    def test_end_edge_has_no_trailing_arrow_by_default(self):
        text = json_to_lineage_format(self._g())
        assert sections(text)["E"] == ["N1", "N2>N1"]
        assert "N1>" not in text.replace("N1>N", "")   # only real N1>Nx pairs may contain "N1>"

    def test_end_edge_type_is_written_with_bare_alias(self):
        g = self._g()
        text = json_to_lineage_format(g)
        assert sections(text)["EP"] == ["N1 etype=direct", "N2>N1 etype=summary"]

    def test_end_edge_without_type_not_in_ep(self):
        g = self._g()
        del g["edges_in_view"][0]["type"]
        text = json_to_lineage_format(g)
        assert sections(text)["EP"] == ["N2>N1 etype=summary"]

    def test_compact_mode(self):
        text = json_to_lineage_format(self._g(), {"compact": True})
        assert sections(text)["E"] == ["N1", "N2>N1"]

    def test_decoder_still_drops_end_edges_and_keeps_the_rest(self):
        restored = lineage_format_to_json(json_to_lineage_format(self._g()))
        assert [(e["source"], e["target"]) for e in restored["edges_in_view"]] == [
            (BACKEND_RESPONSE["edges_in_view"][1]["source"], BACKEND_RESPONSE["edges_in_view"][1]["target"])
        ]
        assert restored["edges_in_view"][0]["type"] == "summary"

    def test_decoder_reads_legacy_trailing_arrow(self):
        legacy = json_to_lineage_format(self._g()).replace("E:\nN1\n", "E:\nN1>\n")
        assert "N1>\n" in legacy
        restored = lineage_format_to_json(legacy)
        assert len(restored["edges_in_view"]) == 1

    def test_edges_with_target_unchanged(self):
        assert sections(json_to_lineage_format(graph()))["E"] == ["N1>N2", "N2>N1"]
