"""
Tests for the LDF converter module — backend LineageGraph schema.
"""

import json
import os
import copy
import tempfile
import pytest  # type: ignore
from ldf import (  # type: ignore
    json_to_lineage_format,
    lineage_format_to_json,
    convert_json_file_to_lineage,
    convert_lineage_file_to_json,
)


# ---------------------------------------------------------------------------
# Shared fixture: two-asset backend response (matches user-provided example)
# ---------------------------------------------------------------------------

BACKEND_RESPONSE = {
    "assets_in_view": [
        {
            "attributes": [
                {"name": "COLUMN_CONSTRAINT", "value": "primary key"}
            ],
            "source_code_snippets": [
                {
                    "id": "a2f4c68decfb9715785acb36589fa619b95b3a49ae3c0c4ab9514545ea3e4acf",
                    "source_code": {
                        "id": "740958c5683c8365f56e21d37bcaf67b2bf351669b45fa8f08a8e361eeea8b90"
                    },
                    "start_position": {"row": 25, "column": 55},
                    "end_position": {"row": 35, "column": 65},
                    "lineage_version_timestamps": ["2024-01-01T00:00:00Z"],
                }
            ],
            "business_classifications": [
                {"id": "e441721f-7369-4547-9aac-a278dfb74f05", "name": "Home Loan"}
            ],
            "business_terms": [
                {"id": "8d3641e9-841f-40d0-aa0b-f5e8e8b97186", "name": "Personal Information"}
            ],
            "catalog_assignments": [
                {
                    "catalog": {
                        "id": "33194072-e58e-476c-b094-412fd6e658d8",
                        "name": "Very Enterprise Catalog",
                    },
                    "data_quality": {"score": 83.5},
                    "user_assignments": [],
                    "user_group_assignments": [],
                    "tags": ["PII"],
                    "business_classifications": [
                        {
                            "id": "e441721f-7369-4547-9aac-a278dfb74f05",
                            "name": "Home Loan",
                            "restricted": True,
                        }
                    ],
                    "business_terms": [
                        {
                            "id": "8d3641e9-841f-40d0-aa0b-f5e8e8b97186",
                            "name": "Personal Information",
                            "restricted": True,
                        }
                    ],
                    "data_classes": [
                        {
                            "id": "3652f859-397e-4fa3-80ac-86e11a5379c4",
                            "name": "First Name",
                            "restricted": True,
                        }
                    ],
                    "service_level_agreement_assignments": [],
                    "cams_asset_id": "7a5d09ce-05a6-4f64-8a29-e9dee5f3a5b3",
                }
            ],
            "children": {
                "count": 0,
                "has_any": False,
                "href": "https://something.ibm.com/gov_lineage/v2/lineage_assets/d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35/children",
            },
            "hierarchical_path": [
                {
                    "id": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
                    "name": "postgres",
                    "type": "Database",
                },
                {
                    "id": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
                    "name": "s1",
                    "type": "Schema",
                },
                {
                    "id": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
                    "name": "table1",
                    "type": "Table",
                },
            ],
            "data_classes": [
                {"id": "3652f859-397e-4fa3-80ac-86e11a5379c4", "name": "First Name"}
            ],
            "data_source_definition_asset": {
                "id": "db4341e3-029c-45f4-b136-743ca2ad7c81",
                "name": "Thomas the DSD asset",
            },
            "id": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
            "is_deduced": False,
            "is_transforming": False,
            "is_operational": False,
            "is_temporary": False,
            "is_favorite": False,
            "name": "first_name",
            "origin": "runtime",
            "project_assignments": [
                {
                    "project": {
                        "id": "ed99846a-2194-4826-9be5-0a805c811238",
                        "name": "My Little Project",
                    },
                    "data_quality": {"score": 83.5},
                    "user_assignments": [],
                    "user_group_assignments": [],
                    "tags": ["PII"],
                    "business_classifications": [
                        {
                            "id": "e441721f-7369-4547-9aac-a278dfb74f05",
                            "name": "Home Loan",
                            "restricted": True,
                        }
                    ],
                    "business_terms": [
                        {
                            "id": "8d3641e9-841f-40d0-aa0b-f5e8e8b97186",
                            "name": "Personal Information",
                            "restricted": True,
                        }
                    ],
                    "data_classes": [
                        {
                            "id": "3652f859-397e-4fa3-80ac-86e11a5379c4",
                            "name": "First Name",
                            "restricted": True,
                        }
                    ],
                    "service_level_agreement_assignments": [],
                    "cams_asset_id": "c4ce19e0-8ad4-42a6-9472-6290c92c8f0c",
                }
            ],
            "space_assignments": [
                {
                    "space": {
                        "id": "fb78846a-2194-4826-9be5-0a805c811238",
                        "name": "My Little Space",
                    },
                    "data_quality": {"score": 83.5},
                    "user_assignments": [],
                    "user_group_assignments": [],
                    "tags": ["PII"],
                    "business_classifications": [
                        {
                            "id": "e441721f-7369-4547-9aac-a278dfb74f05",
                            "name": "Home Loan",
                            "restricted": True,
                        }
                    ],
                    "business_terms": [
                        {
                            "id": "8d3641e9-841f-40d0-aa0b-f5e8e8b97186",
                            "name": "Personal Information",
                            "restricted": True,
                        }
                    ],
                    "data_classes": [
                        {
                            "id": "3652f859-397e-4fa3-80ac-86e11a5379c4",
                            "name": "First Name",
                            "restricted": True,
                        }
                    ],
                    "service_level_agreement_assignments": [],
                    "cams_asset_id": "c4ce19e0-8ad4-42a6-9472-6290c92c8f0c",
                }
            ],
            "resource_key": "PostgreSQL/postgres/s1/table1/first_name",
            "tags": ["PII"],
            "technology": {
                "id": "cc52d03280b7034c8e3653d2748ebd489a873ef4bbc89cb187fbfcabfbbf6873",
                "name": "PostgreSQL",
            },
            "type": "Column",
        },
        {
            "attributes": [],
            "source_code_snippets": [
                {
                    "id": "a2f4c68decfb9715785acb36589fa619b95b3a49ae3c0c4ab9514545ea3e4acf",
                    "source_code": {
                        "id": "740958c5683c8365f56e21d37bcaf67b2bf351669b45fa8f08a8e361eeea8b90"
                    },
                    "start_position": {"row": 25, "column": 55},
                    "end_position": {"row": 35, "column": 65},
                    "lineage_version_timestamps": ["2024-01-01T00:00:00Z"],
                }
            ],
            "business_classifications": [],
            "business_terms": [],
            "catalog_assignments": [],
            "children": {
                "count": 0,
                "has_any": False,
                "href": "https://something.ibm.com/gov_lineage/v2/lineage_assets/7e2f10223b4c01303e05c16055f9a865917108ce41084d08d86b4b7356693aad/children",
            },
            "hierarchical_path": [
                {
                    "id": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
                    "name": "postgres",
                    "type": "Database",
                },
                {
                    "id": "7e2f10223b4c01303e05c16055f9a865917108ce41084d08d86b4b7356693aad",
                    "name": "s1",
                    "type": "Schema",
                },
                {
                    "id": "7e2f10223b4c01303e05c16055f9a865917108ce41084d08d86b4b7356693aad",
                    "name": "table1",
                    "type": "Table",
                },
            ],
            "data_classes": [],
            "data_source_definition_asset": {
                "id": "db4341e3-029c-45f4-b136-743ca2ad7c81",
                "name": "Thomas the DSD asset",
            },
            "id": "7e2f10223b4c01303e05c16055f9a865917108ce41084d08d86b4b7356693aad",
            "is_deduced": False,
            "is_transforming": False,
            "is_operational": False,
            "is_temporary": False,
            "is_favorite": False,
            "name": "eye_color",
            "origin": "runtime",
            "project_assignments": [],
            "space_assignments": [],
            "resource_key": "PostgreSQL/postgres/s1/table1/eye_color",
            "tags": [],
            "technology": {
                "id": "cc52d03280b7034c8e3653d2748ebd489a873ef4bbc89cb187fbfcabfbbf6873",
                "name": "PostgreSQL",
            },
            "type": "Column",
        },
    ],
    "edges_in_view": [
        {
            "source": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
            "target": "7e2f10223b4c01303e05c16055f9a865917108ce41084d08d86b4b7356693aad",
            "type": "direct",
        },
        {
            "source": "7e2f10223b4c01303e05c16055f9a865917108ce41084d08d86b4b7356693aad",
            "target": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
            "type": "summary",
        },
    ],
    "graph_calculation_datetime": "2024-07-22T08:16:22.694Z",
    "graph_calculation_timestamp": 1721636182694,
}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def round_trip(graph):
    """Serialise graph to LDF and back."""
    ldf = json_to_lineage_format(graph)
    return lineage_format_to_json(ldf)


# ---------------------------------------------------------------------------
# TestSerialiser — basic structural checks
# ---------------------------------------------------------------------------

class TestSerialiser:
    """Check that json_to_lineage_format emits all required sections."""

    def test_required_sections_present(self):
        ldf = json_to_lineage_format(BACKEND_RESPONSE)
        for section in ("GRAPH:", "START:", "E:", "EP:", "N:", "T:", "TID:", "ID:", "NAME:"):
            assert section in ldf, f"Missing section {section}"

    def test_new_sections_emitted(self):
        ldf = json_to_lineage_format(BACKEND_RESPONSE)
        for section in ("BT:", "BC:", "DC:", "HP:", "ATTR:", "SCS:", "CA:", "PA:", "SA:", "DSD:"):
            assert section in ldf, f"Missing section {section}"

    def test_graph_meta_lines(self):
        ldf = json_to_lineage_format(BACKEND_RESPONSE)
        assert "dt=2024-07-22T08:16:22.694Z" in ldf
        assert "ts=1721636182694" in ldf

    def test_edge_types_in_ep(self):
        ldf = json_to_lineage_format(BACKEND_RESPONSE)
        assert "etype=direct" in ldf
        assert "etype=summary" in ldf

    def test_node_lines_contain_rk_and_origin(self):
        ldf = json_to_lineage_format(BACKEND_RESPONSE)
        assert "rk=PostgreSQL/postgres/s1/table1/first_name" in ldf
        assert "origin=runtime" in ldf

    def test_compact_shorter_than_normal(self):
        normal = json_to_lineage_format(BACKEND_RESPONSE)
        compact = json_to_lineage_format(BACKEND_RESPONSE, {"compact": True})
        assert len(compact) < len(normal)


# ---------------------------------------------------------------------------
# TestDeserialiser — structural checks on parsed output
# ---------------------------------------------------------------------------

class TestDeserialiser:
    """Check that lineage_format_to_json reconstructs the correct structure."""

    def test_output_keys(self):
        result = round_trip(BACKEND_RESPONSE)
        assert "assets_in_view" in result
        assert "edges_in_view" in result
        assert "graph_calculation_datetime" in result
        assert "graph_calculation_timestamp" in result

    def test_graph_meta_values(self):
        result = round_trip(BACKEND_RESPONSE)
        assert result["graph_calculation_datetime"] == "2024-07-22T08:16:22.694Z"
        assert result["graph_calculation_timestamp"] == 1721636182694

    def test_asset_count(self):
        result = round_trip(BACKEND_RESPONSE)
        assert len(result["assets_in_view"]) == 2

    def test_edge_count_and_types(self):
        result = round_trip(BACKEND_RESPONSE)
        assert len(result["edges_in_view"]) == 2
        types = {e["type"] for e in result["edges_in_view"]}
        assert types == {"direct", "summary"}


# ---------------------------------------------------------------------------
# TestRoundTrip — field-by-field losslessness
# ---------------------------------------------------------------------------

class TestRoundTrip:
    """Full round-trip equality for every field in the backend schema."""

    @pytest.fixture
    def restored(self):
        return round_trip(BACKEND_RESPONSE)

    def test_asset_ids(self, restored):
        original_ids = {a["id"] for a in BACKEND_RESPONSE["assets_in_view"]}
        restored_ids = {a["id"] for a in restored["assets_in_view"]}
        assert original_ids == restored_ids

    def test_asset_names(self, restored):
        orig = {a["id"]: a["name"] for a in BACKEND_RESPONSE["assets_in_view"]}
        rest = {a["id"]: a["name"] for a in restored["assets_in_view"]}
        assert orig == rest

    def test_asset_types(self, restored):
        orig = {a["id"]: a["type"] for a in BACKEND_RESPONSE["assets_in_view"]}
        rest = {a["id"]: a["type"] for a in restored["assets_in_view"]}
        assert orig == rest

    def test_resource_key(self, restored):
        orig = {a["id"]: a.get("resource_key") for a in BACKEND_RESPONSE["assets_in_view"]}
        rest = {a["id"]: a.get("resource_key") for a in restored["assets_in_view"]}
        assert orig == rest

    def test_origin(self, restored):
        for a_orig, a_rest in zip(
            sorted(BACKEND_RESPONSE["assets_in_view"], key=lambda x: x["id"]),
            sorted(restored["assets_in_view"], key=lambda x: x["id"]),
        ):
            assert a_orig["origin"] == a_rest["origin"]

    def test_technology(self, restored):
        orig_map = {a["id"]: a.get("technology") for a in BACKEND_RESPONSE["assets_in_view"]}
        rest_map = {a["id"]: a.get("technology") for a in restored["assets_in_view"]}
        assert orig_map == rest_map

    def test_tags(self, restored):
        orig_map = {a["id"]: sorted(a.get("tags") or []) for a in BACKEND_RESPONSE["assets_in_view"]}
        rest_map = {a["id"]: sorted(a.get("tags") or []) for a in restored["assets_in_view"]}
        assert orig_map == rest_map

    def test_boolean_flags(self, restored):
        flags = ("is_deduced", "is_transforming", "is_operational", "is_temporary", "is_favorite")
        for a_orig in BACKEND_RESPONSE["assets_in_view"]:
            a_rest = next(a for a in restored["assets_in_view"] if a["id"] == a_orig["id"])
            for flag in flags:
                assert a_orig[flag] == a_rest[flag], f"Flag {flag} mismatch for {a_orig['id']}"

    def test_children(self, restored):
        for a_orig in BACKEND_RESPONSE["assets_in_view"]:
            a_rest = next(a for a in restored["assets_in_view"] if a["id"] == a_orig["id"])
            ch_orig = a_orig["children"]
            ch_rest = a_rest["children"]
            assert ch_orig["count"] == ch_rest["count"]
            assert ch_orig["has_any"] == ch_rest["has_any"]
            assert ch_orig["href"] == ch_rest["href"]

    def test_hierarchical_path(self, restored):
        for a_orig in BACKEND_RESPONSE["assets_in_view"]:
            a_rest = next(a for a in restored["assets_in_view"] if a["id"] == a_orig["id"])
            assert a_orig["hierarchical_path"] == a_rest["hierarchical_path"], (
                f"hierarchical_path mismatch for {a_orig['id']}"
            )

    def test_attributes(self, restored):
        for a_orig in BACKEND_RESPONSE["assets_in_view"]:
            a_rest = next(a for a in restored["assets_in_view"] if a["id"] == a_orig["id"])
            assert a_orig["attributes"] == a_rest["attributes"]

    def test_business_terms(self, restored):
        for a_orig in BACKEND_RESPONSE["assets_in_view"]:
            a_rest = next(a for a in restored["assets_in_view"] if a["id"] == a_orig["id"])
            assert a_orig["business_terms"] == a_rest["business_terms"]

    def test_business_classifications(self, restored):
        for a_orig in BACKEND_RESPONSE["assets_in_view"]:
            a_rest = next(a for a in restored["assets_in_view"] if a["id"] == a_orig["id"])
            assert a_orig["business_classifications"] == a_rest["business_classifications"]

    def test_data_classes(self, restored):
        for a_orig in BACKEND_RESPONSE["assets_in_view"]:
            a_rest = next(a for a in restored["assets_in_view"] if a["id"] == a_orig["id"])
            assert a_orig["data_classes"] == a_rest["data_classes"]

    def test_data_source_definition_asset(self, restored):
        for a_orig in BACKEND_RESPONSE["assets_in_view"]:
            a_rest = next(a for a in restored["assets_in_view"] if a["id"] == a_orig["id"])
            assert a_orig.get("data_source_definition_asset") == a_rest.get(
                "data_source_definition_asset"
            )

    def test_source_code_snippets(self, restored):
        for a_orig in BACKEND_RESPONSE["assets_in_view"]:
            a_rest = next(a for a in restored["assets_in_view"] if a["id"] == a_orig["id"])
            assert a_orig["source_code_snippets"] == a_rest["source_code_snippets"]

    def test_catalog_assignments(self, restored):
        for a_orig in BACKEND_RESPONSE["assets_in_view"]:
            a_rest = next(a for a in restored["assets_in_view"] if a["id"] == a_orig["id"])
            assert a_orig["catalog_assignments"] == a_rest["catalog_assignments"]

    def test_project_assignments(self, restored):
        for a_orig in BACKEND_RESPONSE["assets_in_view"]:
            a_rest = next(a for a in restored["assets_in_view"] if a["id"] == a_orig["id"])
            assert a_orig["project_assignments"] == a_rest["project_assignments"]

    def test_space_assignments(self, restored):
        for a_orig in BACKEND_RESPONSE["assets_in_view"]:
            a_rest = next(a for a in restored["assets_in_view"] if a["id"] == a_orig["id"])
            assert a_orig["space_assignments"] == a_rest["space_assignments"]

    def test_edges_source_target(self, restored):
        orig_pairs = {(e["source"], e["target"]) for e in BACKEND_RESPONSE["edges_in_view"]}
        rest_pairs = {(e["source"], e["target"]) for e in restored["edges_in_view"]}
        assert orig_pairs == rest_pairs

    def test_edges_type(self, restored):
        orig_map = {
            (e["source"], e["target"]): e.get("type")
            for e in BACKEND_RESPONSE["edges_in_view"]
        }
        rest_map = {
            (e["source"], e["target"]): e.get("type")
            for e in restored["edges_in_view"]
        }
        assert orig_map == rest_map


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_assets(self):
        graph = {"assets_in_view": [], "edges_in_view": []}
        result = round_trip(graph)
        assert result["assets_in_view"] == []
        assert result["edges_in_view"] == []

    def test_flags_all_true(self):
        graph = copy.deepcopy(BACKEND_RESPONSE)
        asset = graph["assets_in_view"][0]
        asset["is_deduced"] = True
        asset["is_transforming"] = True
        asset["is_operational"] = True
        asset["is_temporary"] = True
        asset["is_favorite"] = True
        # Remove second asset to simplify
        graph["assets_in_view"] = [asset]
        graph["edges_in_view"] = []
        result = round_trip(graph)
        r = result["assets_in_view"][0]
        assert r["is_deduced"] is True
        assert r["is_transforming"] is True
        assert r["is_operational"] is True
        assert r["is_temporary"] is True
        assert r["is_favorite"] is True

    def test_no_technology(self):
        graph = copy.deepcopy(BACKEND_RESPONSE)
        del graph["assets_in_view"][0]["technology"]
        graph["assets_in_view"] = [graph["assets_in_view"][0]]
        graph["edges_in_view"] = []
        result = round_trip(graph)
        assert result["assets_in_view"][0].get("technology") is None

    def test_children_href_with_colons_preserved(self):
        """children.href contains URL with colons — must survive round-trip."""
        result = round_trip(BACKEND_RESPONSE)
        for a_orig in BACKEND_RESPONSE["assets_in_view"]:
            a_rest = next(a for a in result["assets_in_view"] if a["id"] == a_orig["id"])
            assert a_orig["children"]["href"] == a_rest["children"]["href"]

    def test_compact_round_trip(self):
        ldf_compact = json_to_lineage_format(BACKEND_RESPONSE, {"compact": True})
        result = lineage_format_to_json(ldf_compact)
        assert len(result["assets_in_view"]) == 2
        assert len(result["edges_in_view"]) == 2

    def test_no_graph_meta(self):
        graph = {"assets_in_view": [], "edges_in_view": []}
        result = round_trip(graph)
        assert "graph_calculation_datetime" not in result
        assert "graph_calculation_timestamp" not in result


# ---------------------------------------------------------------------------
# TestLosslessnessEdgeCases — covers all 7 bugs found in the audit
# ---------------------------------------------------------------------------

def _single_asset(overrides: dict) -> dict:
    """Build a minimal backend graph with one asset, applying overrides."""
    base = {
        "id": "aaaa0000000000000000000000000000000000000000000000000000000000000000",
        "name": "test_col",
        "type": "Column",
        "attributes": [],
        "source_code_snippets": [],
        "business_classifications": [],
        "business_terms": [],
        "catalog_assignments": [],
        "children": {"count": 0, "has_any": False, "href": ""},
        "hierarchical_path": [],
        "data_classes": [],
        "is_deduced": False,
        "is_transforming": False,
        "is_operational": False,
        "is_temporary": False,
        "is_favorite": False,
        "identity_key": None,
        "origin": "runtime",
        "project_assignments": [],
        "resource_key": "DB/schema/table/col",
        "space_assignments": [],
        "tags": [],
        "technology": {
            "id": "tech0000000000000000000000000000000000000000000000000000000000000001",
            "name": "PostgreSQL",
        },
    }
    base.update(overrides)
    return {"assets_in_view": [base], "edges_in_view": []}


class TestLosslessnessEdgeCases:
    """Regression tests for bugs found in the losslessness audit."""

    # ------------------------------------------------------------------
    # Bug 1 — ATTR value containing ":"
    # ------------------------------------------------------------------
    def test_attr_value_with_colon(self):
        """ATTR value containing ':' must round-trip unchanged (Bug 1)."""
        graph = _single_asset({
            "attributes": [
                {"name": "DATA_TYPE", "value": "http://www.w3.org/2001/XMLSchema#string"},
                {"name": "COLUMN_CONSTRAINT", "value": "primary key"},
            ]
        })
        result = round_trip(graph)
        attrs = result["assets_in_view"][0]["attributes"]
        assert attrs[0] == {"name": "DATA_TYPE", "value": "http://www.w3.org/2001/XMLSchema#string"}
        assert attrs[1] == {"name": "COLUMN_CONSTRAINT", "value": "primary key"}

    def test_attr_value_with_pipe(self):
        """ATTR value containing '|' must round-trip unchanged (Bug 1 + Bug 5 adjacent)."""
        graph = _single_asset({
            "attributes": [{"name": "ENUM_VALUES", "value": "A|B|C"}]
        })
        result = round_trip(graph)
        assert result["assets_in_view"][0]["attributes"] == [
            {"name": "ENUM_VALUES", "value": "A|B|C"}
        ]

    def test_attr_value_with_equals(self):
        """ATTR value containing '=' must round-trip unchanged."""
        graph = _single_asset({
            "attributes": [{"name": "EXPR", "value": "x=1"}]
        })
        result = round_trip(graph)
        assert result["assets_in_view"][0]["attributes"] == [{"name": "EXPR", "value": "x=1"}]

    def test_attr_value_with_percent(self):
        """ATTR value containing '%' (percent-encoding trigger) must round-trip."""
        graph = _single_asset({
            "attributes": [{"name": "PATTERN", "value": "50%discount"}]
        })
        result = round_trip(graph)
        assert result["assets_in_view"][0]["attributes"] == [
            {"name": "PATTERN", "value": "50%discount"}
        ]

    # ------------------------------------------------------------------
    # Bug 2 — HP name/type containing ":"
    # ------------------------------------------------------------------
    def test_hp_name_with_colon(self):
        """hierarchical_path entry with ':' in name must round-trip (Bug 2)."""
        graph = _single_asset({
            "hierarchical_path": [
                {"id": "aabbcc0000000000000000000000000000000000000000000000000000000000", "name": "My:Schema", "type": "Schema"},
                {"id": "aabbcc1111111111111111111111111111111111111111111111111111111111", "name": "normal_table", "type": "Table"},
            ]
        })
        result = round_trip(graph)
        hp = result["assets_in_view"][0]["hierarchical_path"]
        assert hp[0]["name"] == "My:Schema"
        assert hp[0]["type"] == "Schema"
        assert hp[1]["name"] == "normal_table"

    def test_hp_type_with_colon(self):
        """hierarchical_path entry with ':' in type must round-trip (Bug 2)."""
        graph = _single_asset({
            "hierarchical_path": [
                {"id": "aabbcc0000000000000000000000000000000000000000000000000000000000", "name": "mydb", "type": "sub:type"},
            ]
        })
        result = round_trip(graph)
        hp = result["assets_in_view"][0]["hierarchical_path"]
        assert hp[0]["type"] == "sub:type"
        assert hp[0]["name"] == "mydb"

    # ------------------------------------------------------------------
    # Bug 3/5 — HP name/type containing "|"
    # ------------------------------------------------------------------
    def test_hp_name_with_pipe(self):
        """hierarchical_path name containing '|' must round-trip (Bug 5)."""
        graph = _single_asset({
            "hierarchical_path": [
                {"id": "aabbcc0000000000000000000000000000000000000000000000000000000000", "name": "A|B", "type": "Schema"},
            ]
        })
        result = round_trip(graph)
        hp = result["assets_in_view"][0]["hierarchical_path"]
        assert hp[0]["name"] == "A|B"

    # ------------------------------------------------------------------
    # Bug 4 — rk and origin containing spaces
    # ------------------------------------------------------------------
    def test_resource_key_with_space(self):
        """resource_key containing spaces must round-trip unchanged (Bug 4)."""
        graph = _single_asset({"resource_key": "My Schema/My Table/my col"})
        result = round_trip(graph)
        assert result["assets_in_view"][0]["resource_key"] == "My Schema/My Table/my col"

    def test_origin_with_space(self):
        """origin containing spaces must round-trip unchanged (Bug 4)."""
        graph = _single_asset({"origin": "user defined"})
        result = round_trip(graph)
        assert result["assets_in_view"][0]["origin"] == "user defined"

    def test_resource_key_with_percent(self):
        """resource_key containing '%' must round-trip unchanged."""
        graph = _single_asset({"resource_key": "DB/50%table"})
        result = round_trip(graph)
        assert result["assets_in_view"][0]["resource_key"] == "DB/50%table"

    # ------------------------------------------------------------------
    # Bug 6 — identity_key missing from serialization
    # ------------------------------------------------------------------
    def test_identity_key_round_trip(self):
        """identity_key must be serialized and restored (Bug 6)."""
        graph = _single_asset({"identity_key": "my-identity-key-value"})
        result = round_trip(graph)
        assert result["assets_in_view"][0]["identity_key"] == "my-identity-key-value"

    def test_identity_key_none(self):
        """identity_key=None must produce identity_key=None after round-trip."""
        graph = _single_asset({"identity_key": None})
        result = round_trip(graph)
        assert result["assets_in_view"][0]["identity_key"] is None

    def test_identity_key_with_special_chars(self):
        """identity_key containing spaces and = must round-trip."""
        graph = _single_asset({"identity_key": "key with space=value"})
        result = round_trip(graph)
        assert result["assets_in_view"][0]["identity_key"] == "key with space=value"

    # ------------------------------------------------------------------
    # Bug 7 — technology deduplication by id not name
    # ------------------------------------------------------------------
    def test_two_techs_same_name_different_id(self):
        """Two technologies with identical names but different ids must each
        get their own alias and preserve both ids (Bug 7)."""
        base_asset = {
            "id": "asset_id_1111111111111111111111111111111111111111111111111111111111",
            "name": "col_a",
            "type": "Column",
            "attributes": [],
            "source_code_snippets": [],
            "business_classifications": [],
            "business_terms": [],
            "catalog_assignments": [],
            "children": {"count": 0, "has_any": False, "href": ""},
            "hierarchical_path": [],
            "data_classes": [],
            "is_deduced": False,
            "is_transforming": False,
            "is_operational": False,
            "is_temporary": False,
            "is_favorite": False,
            "identity_key": None,
            "origin": "runtime",
            "project_assignments": [],
            "resource_key": "DB/col_a",
            "space_assignments": [],
            "tags": [],
        }
        asset1 = {**base_asset, "id": "a" * 64, "name": "col_a", "resource_key": "DB/col_a",
                  "technology": {"id": "tech_id_AAA", "name": "PostgreSQL"}}
        asset2 = {**base_asset, "id": "b" * 64, "name": "col_b", "resource_key": "DB/col_b",
                  "technology": {"id": "tech_id_BBB", "name": "PostgreSQL"}}  # same name, different id

        graph = {"assets_in_view": [asset1, asset2], "edges_in_view": []}
        result = round_trip(graph)

        r1 = next(a for a in result["assets_in_view"] if a["id"] == "a" * 64)
        r2 = next(a for a in result["assets_in_view"] if a["id"] == "b" * 64)
        assert r1["technology"]["id"] == "tech_id_AAA"
        assert r2["technology"]["id"] == "tech_id_BBB"

    # ------------------------------------------------------------------
    # Combined: all special chars in one go
    # ------------------------------------------------------------------
    def test_combined_special_chars_round_trip(self):
        """All special characters (: | = % space) in relevant fields simultaneously."""
        graph = _single_asset({
            "attributes": [
                {"name": "URL", "value": "http://ex.com/path?a=1&b=2|c=3"},
                {"name": "PCT", "value": "50%off"},
            ],
            "hierarchical_path": [
                {"id": "abc0" * 16, "name": "schema:v2", "type": "sub:Schema"},
                {"id": "def0" * 16, "name": "table|one", "type": "Table"},
            ],
            "resource_key": "DB/my schema/my table",
            "origin": "user input",
            "identity_key": "ik=special|value",
        })
        result = round_trip(graph)
        a = result["assets_in_view"][0]
        assert a["attributes"][0]["value"] == "http://ex.com/path?a=1&b=2|c=3"
        assert a["attributes"][1]["value"] == "50%off"
        assert a["hierarchical_path"][0]["name"] == "schema:v2"
        assert a["hierarchical_path"][0]["type"] == "sub:Schema"
        assert a["hierarchical_path"][1]["name"] == "table|one"
        assert a["resource_key"] == "DB/my schema/my table"
        assert a["origin"] == "user input"
        assert a["identity_key"] == "ik=special|value"


# ---------------------------------------------------------------------------
# TestTagsAndTypeEncoding — covers Problems 1/2/3 found in second audit
# ---------------------------------------------------------------------------

class TestTagsAndTypeEncoding:
    """Regression tests for tag, type and name encoding bugs found in second audit."""

    # ------------------------------------------------------------------
    # Problem 1 — tag containing comma
    # ------------------------------------------------------------------
    def test_tag_with_comma(self):
        """Tag containing ',' must not be split into multiple tags."""
        graph = _single_asset({"tags": ["normal", "tag,with,comma"]})
        result = round_trip(graph)
        assert result["assets_in_view"][0]["tags"] == ["normal", "tag,with,comma"]

    # ------------------------------------------------------------------
    # Problem 1+D — tag containing space
    # ------------------------------------------------------------------
    def test_tag_with_space(self):
        """Tag containing space must not corrupt the N: line token parsing."""
        graph = _single_asset({"tags": ["PII", "tag with space", "another"]})
        result = round_trip(graph)
        assert result["assets_in_view"][0]["tags"] == ["PII", "tag with space", "another"]

    # ------------------------------------------------------------------
    # Problem B — tag containing square brackets
    # ------------------------------------------------------------------
    def test_tag_with_brackets(self):
        """Tag containing '[' or ']' must survive strip('[]') in parser."""
        graph = _single_asset({"tags": ["tag[bracket]", "normal"]})
        result = round_trip(graph)
        assert result["assets_in_view"][0]["tags"] == ["tag[bracket]", "normal"]

    def test_tag_with_percent(self):
        """Tag containing '%' must survive percent-encoding round-trip."""
        graph = _single_asset({"tags": ["50%off", "100%"]})
        result = round_trip(graph)
        assert result["assets_in_view"][0]["tags"] == ["50%off", "100%"]

    def test_tags_all_special_chars_combined(self):
        """Tags combining comma, space, brackets, percent must all round-trip."""
        tags = [
            "PII",
            "tag with space",
            "tag,with,comma",
            "tag[bracket]",
            "50%off",
            "a=b",
            "x|y",
        ]
        graph = _single_asset({"tags": tags})
        result = round_trip(graph)
        assert result["assets_in_view"][0]["tags"] == tags

    # ------------------------------------------------------------------
    # Problem 2 — node type containing space
    # ------------------------------------------------------------------
    def test_type_with_space(self):
        """Asset type containing space must round-trip unchanged."""
        graph = _single_asset({"type": "My Type"})
        result = round_trip(graph)
        assert result["assets_in_view"][0]["type"] == "My Type"

    def test_type_with_special_chars(self):
        """Asset type with comma, percent, brackets must round-trip."""
        graph = _single_asset({"type": "Type[v2],50%"})
        result = round_trip(graph)
        assert result["assets_in_view"][0]["type"] == "Type[v2],50%"

    # ------------------------------------------------------------------
    # Problem 3 — asset name containing newline
    # ------------------------------------------------------------------
    def test_name_with_newline(self):
        """Asset name containing newline must not be split across NAME: section lines."""
        graph = _single_asset({"name": "name\nwith\nnewline"})
        result = round_trip(graph)
        assert result["assets_in_view"][0]["name"] == "name\nwith\nnewline"

    def test_name_with_equals(self):
        """Asset name containing '=' must round-trip (parse_dict uses find('='))."""
        graph = _single_asset({"name": "col=alias"})
        result = round_trip(graph)
        assert result["assets_in_view"][0]["name"] == "col=alias"

    def test_name_with_all_special_chars(self):
        """Asset name with all structural chars must round-trip."""
        name = "n=a,m[e] w|ith\nall%chars"
        graph = _single_asset({"name": name})
        result = round_trip(graph)
        assert result["assets_in_view"][0]["name"] == name

    # ------------------------------------------------------------------
    # Combined: type+name+tags all special at once
    # ------------------------------------------------------------------
    def test_combined_tags_type_name(self):
        """Type with space, name with newline, tags with commas — simultaneously."""
        graph = _single_asset({
            "type": "Custom Type",
            "name": "my\ncol",
            "tags": ["tag,a", "tag b", "tag[c]", "50%"],
        })
        result = round_trip(graph)
        a = result["assets_in_view"][0]
        assert a["type"] == "Custom Type"
        assert a["name"] == "my\ncol"
        assert a["tags"] == ["tag,a", "tag b", "tag[c]", "50%"]


# ---------------------------------------------------------------------------
# TestFileConversion
# ---------------------------------------------------------------------------

class TestFileConversion:
    def test_json_file_to_ldf_and_back(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            in_json = os.path.join(tmpdir, "input.json")
            out_ldf = os.path.join(tmpdir, "output.ldf")
            out_json = os.path.join(tmpdir, "restored.json")

            with open(in_json, "w", encoding="utf-8") as f:
                json.dump(BACKEND_RESPONSE, f)

            convert_json_file_to_lineage(in_json, out_ldf)
            assert os.path.exists(out_ldf)
            with open(out_ldf) as f:
                content = f.read()
            assert "GRAPH:" in content
            assert "N:" in content

            convert_lineage_file_to_json(out_ldf, out_json)
            assert os.path.exists(out_json)
            with open(out_json) as f:
                restored = json.load(f)

            assert len(restored["assets_in_view"]) == 2
            assert len(restored["edges_in_view"]) == 2
            assert restored["graph_calculation_timestamp"] == 1721636182694

# Made with Bob
