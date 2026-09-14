"""
Smoke tests — minimal round-trip checks that mirror the install-from-git CI job.
Run with: pytest tests/test_smoke.py
"""

import ldf
from ldf import (
    json_to_lineage_format,
    lineage_format_to_json,
    convert_json_file_to_lineage,
    convert_lineage_file_to_json,
)


def test_public_api_importable():
    """All four public functions and __version__ must be importable."""
    assert callable(json_to_lineage_format)
    assert callable(lineage_format_to_json)
    assert callable(convert_json_file_to_lineage)
    assert callable(convert_lineage_file_to_json)
    assert isinstance(ldf.__version__, str)


def test_round_trip_smoke():
    """Minimal round-trip: a single asset with a tag survives serialization."""
    graph = {
        "assets_in_view": [
            {
                "id": "a" * 64,
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
                "resource_key": "DB/col",
                "space_assignments": [],
                "tags": ["PII"],
            }
        ],
        "edges_in_view": [],
    }

    ldf_text = json_to_lineage_format(graph)
    restored = lineage_format_to_json(ldf_text)

    assert restored["assets_in_view"][0]["id"] == "a" * 64
    assert restored["assets_in_view"][0]["tags"] == ["PII"]
