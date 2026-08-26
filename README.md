# Lineage Definition Format (LDF)

[![CI](https://github.com/IBM/lineage-data-format/actions/workflows/ci.yml/badge.svg)](https://github.com/IBM/lineage-data-format/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)

A Python library for converting between the backend `LineageGraph` JSON schema and a compact, token-optimized lineage definition format.

## Installation

Install directly from GitHub:

```bash
pip install git+https://github.com/IBM/lineage-data-format.git
```

Pin to a specific release:

```bash
pip install git+https://github.com/IBM/lineage-data-format.git@v0.1.0
```

Install from source for development:

```bash
git clone https://github.com/IBM/lineage-data-format.git
cd lineage-data-format
pip install -e ".[dev]"
```

## Input Schema

Both `json_to_lineage_format` and `convert_json_file_to_lineage` expect the backend `LineageGraph` response format:

```json
{
  "assets_in_view": [ /* list of LineageAsset objects */ ],
  "edges_in_view":  [ /* list of FlowEdge objects */ ],
  "graph_calculation_datetime": "2024-07-22T08:16:22.694Z",
  "graph_calculation_timestamp": 1721636182694
}
```

### LineageAsset fields

| Field | Type | Notes |
|---|---|---|
| `id` | string | Asset UUID |
| `name` | string | Display name |
| `type` | string | e.g. `"Column"`, `"Table"` |
| `resource_key` | string | e.g. `"PostgreSQL/db/schema/table/col"` |
| `origin` | string | e.g. `"runtime"` |
| `technology` | `{id, name}` | Technology lookup |
| `hierarchical_path` | `[{id, name, type}]` | Ancestry path |
| `attributes` | `[{name, value}]` | Asset attributes |
| `tags` | `string[]` | Tag list |
| `business_terms` | `[{id, name}]` | |
| `business_classifications` | `[{id, name}]` | |
| `data_classes` | `[{id, name}]` | |
| `source_code_snippets` | array | Full snippet objects |
| `catalog_assignments` | array | Full assignment objects |
| `project_assignments` | array | Full assignment objects |
| `space_assignments` | array | Full assignment objects |
| `data_source_definition_asset` | `{id, name}` | |
| `children` | `{count, has_any, href}` | Child summary |
| `is_deduced` | bool | |
| `is_transforming` | bool | |
| `is_operational` | bool | |
| `is_temporary` | bool | |
| `is_favorite` | bool | |

### FlowEdge fields

| Field | Type | Notes |
|---|---|---|
| `source` | string | Source asset UUID |
| `target` | string | Target asset UUID |
| `type` | `"direct"` \| `"summary"` | Edge type |

## Usage

### As a Library

```python
from ldf import (
    json_to_lineage_format,
    lineage_format_to_json,
    convert_json_file_to_lineage,
    convert_lineage_file_to_json,
)

# Convert a backend LineageGraph dict to LDF string
ldf_text = json_to_lineage_format(backend_response)

# Convert LDF string back to backend LineageGraph dict
restored = lineage_format_to_json(ldf_text)

# Convert files directly
convert_json_file_to_lineage('input.json', 'output.ldf')
convert_lineage_file_to_json('input.ldf', 'output.json')

# Compact mode (single blank line between sections instead of two)
ldf_compact = json_to_lineage_format(backend_response, {'compact': True})
```

### Command Line Interface

```bash
# Convert JSON to lineage format
ldf json-to-lineage input.json output.ldf

# Convert with compact format (minimal blank lines)
ldf json-to-lineage input.json output.ldf --compact

# Convert lineage format back to JSON
ldf lineage-to-json input.ldf output.json

# Specify JSON indentation
ldf lineage-to-json input.ldf output.json --indent 4
```

## Format Overview

The Lineage Definition Format is a compact, plain-text format that defines repeated values once in named lookup sections and references them via short aliases throughout. All sections are optional except `GRAPH`, `START`, `E`, and `N`.

### Section Reference

| Section | Type | Content |
|---|---|---|
| `GRAPH` | Structural | Marker line + optional `dt=` / `ts=` meta |
| `START` | Structural | Alias of the first asset |
| `E` | Structural | Directed edges: `N1>N2` |
| `EP` | Structural | Edge properties: `N1>N2 etype=direct` |
| `N` | Structural | Node definitions (see format below) |
| `T` | Lookup | Technology names: `T1=PostgreSQL` |
| `TID` | Lookup | Technology UUIDs: `T1=<uuid>` |
| `ID` | Lookup | Node UUIDs: `N1=<uuid>` |
| `NAME` | Lookup | Node display names: `N1=first_name` |
| `BT` | Lookup | Business terms: `BT1=<uuid>\|Term Name` |
| `BC` | Lookup | Business classifications: `BC1=<uuid>\|Name` |
| `DC` | Lookup | Data classes: `DC1=<uuid>\|Name` |
| `HP` | Per-node | Hierarchical path: `N1=id:name:type\|…` |
| `ATTR` | Per-node | Asset attributes: `N1=name:value\|…` |
| `SCS` | Per-node | Source code snippets (JSON): `N1=[…]` |
| `CA` | Per-node | Catalog assignments (JSON): `N1=[…]` |
| `PA` | Per-node | Project assignments (JSON): `N1=[…]` |
| `SA` | Per-node | Space assignments (JSON): `N1=[…]` |
| `DSD` | Per-node | Data source definition asset: `N1=id:name` |

### Node Line Format

```
N1:Column rk=PostgreSQL/db/s1/t/col origin=runtime path=T1 tags=[PII] bt=[BT1] bc=[BC1] dc=[DC1] flags=0 ch=0,0,https://…/children
```

| Token | Meaning |
|---|---|
| `N1:Column` | alias:type |
| `rk=…` | `resource_key` |
| `origin=…` | `origin` |
| `path=T1` | technology alias (→ `T` / `TID` lookup) |
| `tags=[…]` | comma-separated tag list |
| `bt=[…]` | business term aliases |
| `bc=[…]` | business classification aliases |
| `dc=[…]` | data class aliases |
| `flags=N` | bitmask: bit0=`is_deduced`, bit1=`is_transforming`, bit2=`is_operational`, bit3=`is_temporary`, bit4=`is_favorite`; omitted when 0 |
| `ch=count,has_any,href` | children summary; comma-separated to avoid conflicts with URLs |

### Example Output

See [`examples/output_backend.ldf`](examples/output_backend.ldf) for the full LDF representation of [`examples/mock_backend_response.json`](examples/mock_backend_response.json).

## Features

- **Token-optimized**: Reduces token count by 4–6× compared to JSON
- **Bidirectional / lossless**: Full round-trip fidelity for all backend schema fields
- **Fully self-describing**: All lookup sections are embedded in the document
- **Human-readable**: Plain text, no binary encoding
- **CLI included**: Easy command-line conversion tools

## Development

```bash
# Create virtual environment and install dev dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=ldf
```

## License

See [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
