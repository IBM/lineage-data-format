"""
Lineage Definition Format (LDF) - Token-optimized graph serialization.

This library provides functions to convert between JSON lineage data
and a compact lineage definition format.
"""

from .converter import (
    json_to_lineage_format,
    lineage_format_to_json,
    convert_json_file_to_lineage,
    convert_lineage_file_to_json,
)

__version__ = "0.1.0"

__all__ = [
    "json_to_lineage_format",
    "lineage_format_to_json",
    "convert_json_file_to_lineage",
    "convert_lineage_file_to_json",
]

# Made with Bob
