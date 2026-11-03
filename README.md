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
pip install git+https://github.com/IBM/lineage-data-format.git@v0.2.0
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
| `descendant_statistics` | `{has_leaf_children, is_every_child_leaf, number_of_leaf_descendants}` | Leaf statistics, written as the `ds=` node token |
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

# Legacy, fully expanded output (no alias compression)
ldf_expanded = json_to_lineage_format(backend_response, {'aliases': False})

# Drop every URL, and append a legend of the sections used
ldf_small = json_to_lineage_format(backend_response, {'no_urls': True, 'legend': True})

# Exclude fields from the output (applied to the input, before serialization)
ldf_slim = json_to_lineage_format(
    backend_response,
    {'exclude_fields': ['children', 'technology.id', 'hierarchical_path.type', 'is_*']},
)
```

#### `aliases`

A `bool` in the options dict, `True` by default. It removes repeated values from
the output (see [Alias compression](#alias-compression)). `False` writes the
expanded form of version 0.2.0. The decoder reads both forms. Command line:
`--no-aliases`.

#### `no_urls`

A `bool` in the options dict, `False` by default. It drops every URL: the `href`
field wherever it occurs (`children.href` and the hrefs inside catalog, project
and space assignments). It is the same as adding `"href"` to `exclude_fields`, and
no `URL` section is written. Command line: `--no-urls`; file helper:
`convert_json_file_to_lineage(..., no_urls=True)`.

#### `legend`

A `bool` in the options dict, `False` by default. It adds a `LEGEND` section as the
first section, with one `SECTION=expansion` line (e.g. `HP=Hierarchical path`) for
every abbreviated section present in the output. It only spells the names out; it
sits first so a reader knows the abbreviations before it meets them. The decoder
ignores it, so the round trip is unchanged. Command line:
`--legend`; file helper: `convert_json_file_to_lineage(..., legend=True)`.

#### `exclude_fields`

A list of `str` passed in the options dict. The default is an empty list, in which
case the output is identical to the output without the option.

| Entry | Effect |
|-------|--------|
| `"children"` | removes the field with that name at every nesting level (assets, edges, top level, nested objects) |
| `"technology.id"` | removes only that field; the path is relative to the asset/edge, arrays take no indices |
| `"technology"` | removing an object or array removes its whole content |
| `"is_*"`, `"*_assignments"` | wildcards, matched with `fnmatch` (case-sensitive) |
| unknown entry | ignored (logged at `DEBUG` level) |

Excluded data leaves no trace in the output: no empty separators, entries or
sections. For example, with `technology` excluded no `path=`, `T` or `TID` is
written, and with `hierarchical_path` excluded no `HP` section is written.
When only part of a record is removed, the remaining fields keep their meaning
through named forms that the decoder understands (`chc=`/`cha=`/`chh=` for
children, `i=`/`n=`/`t=` in `HP` segments, `n=name` / bare `id` in lookups).
A non-list value raises `TypeError`; removing an asset `id` or an edge
`source`/`target` raises `ValueError`.

### Command Line Interface

```bash
# Convert JSON to lineage format
ldf json-to-lineage input.json output.ldf

# Convert with compact format (minimal blank lines)
ldf json-to-lineage input.json output.ldf --compact

# Expanded output without alias compression
ldf json-to-lineage input.json output.ldf --no-aliases

# Drop every URL (same as --exclude href)
ldf json-to-lineage input.json output.ldf --no-urls

# Add a LEGEND section that spells out the section abbreviations
ldf json-to-lineage input.json output.ldf --legend

# Exclude fields (comma-separated and/or repeated; names, dotted paths, wildcards)
ldf json-to-lineage input.json output.ldf --exclude children,descendant_statistics,is_favorite,source_code_snippets

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
| `E` | Structural | Directed edges: `N1>N2`, grouped by source `N1>N2,N3`; an edge without a target (end edge) is just the source alias: `N7` |
| `EP` | Structural | Edge properties: `N1>N2 etype=direct` (end edge: `N7 etype=summary`), listed in `E` order; `*>* etype=X` / `* etype=Y` are the defaults |
| `NDEF` | Defaults | Node tokens shared by most nodes: `origin=design path=T1 flags=7` |
| `IKP` | Lookup | `identity_key` prefixes: `P1=<encoded prefix>` |
| `N` | Structural | Node definitions (see format below) |
| `T` | Lookup | Technology names: `T1=PostgreSQL` |
| `TID` | Lookup | Technology UUIDs: `T1=<uuid>` |
| `ID` | Lookup | Node UUIDs: `N1=<uuid>` |
| `URL` | Lookup | URL templates and prefixes: `U1=<template or prefix>`, used as `@U1` |
| `SRC` | Lookup | Source code ids shared by compact `SCS` entries: `S1=<source_code id>` |
| `NAME` | Lookup | Node display names: `N1=first_name` |
| `BT` | Lookup | Business terms: `BT1=<uuid>\|Term Name` |
| `BC` | Lookup | Business classifications: `BC1=<uuid>\|Name` |
| `DC` | Lookup | Data classes: `DC1=<uuid>\|Name` |
| `HP` | Per-node | Hierarchical path: `N1=id:name:type\|…` |
| `ATTR` | Per-node | Asset attributes: `N1=name:value\|…` |
| `SCS` | Per-node | Source code snippets: compact `N1=<id>@S1@41:1-44:38` or JSON `N1=[…]` |
| `CA` | Per-node | Catalog assignments (JSON): `N1=[…]` |
| `PA` | Per-node | Project assignments (JSON): `N1=[…]` |
| `SA` | Per-node | Space assignments (JSON): `N1=[…]` |
| `DSD` | Per-node | Data source definition asset: `N1=id:name` |
| `REF` | Lookup | Shared values of `HP` / `ATTR` / `DSD`: `R1=<value>`, used as `@R1` |
| `LEGEND` | Informational | Optional (`legend` / `--legend`), always first: one `SECTION=expansion` line per abbreviated section present (`GRAPH` and `START` are not listed). The decoder ignores it |

### Alias compression

With `aliases` on, repeated values are written once:

| Construct | Example | Meaning |
|---|---|---|
| `REF` + `@Rn` | `R1=TRANSFORMATION_TAG=TRANSFORMING`, entry `N1=@R1\|@R2` | a whole entry value or one `\|`-separated element is replaced by the reference; a reference may refer to other references. An `@…` that is not defined in `REF` is a literal |
| `*` entry | `HP:` `*=<value>`, `N3=<other>`, `N4=` | default value of `HP` / `DSD`. A node with its own entry keeps it; an empty entry (`N4=`) means none |
| `IKP` | `P1=uuid/dsd%5BDatabase%5D/`, node `ikp=P1 ik=Asset%201…` | `identity_key` = prefix + `ik` |
| `NDEF` | `origin=design flags=7` | tokens inherited by every node. A node's own token overrides it, an empty one (`origin=`) removes it; `flags=0` is written explicitly |
| `URL` + `@Un` | `U1=https://…/lineage_assets/{id}/children`, node token `ch=0,0,@U1` | `children.href` template; `{id}` is the node UUID from `ID`. In `CA` / `PA` / `SA` blobs a shared href prefix is written `@U2/rest`; a literal href that starts with `@` is written `@@…` |
| `SRC` + compact `SCS` | `S1=<source_code id>`, entry `N5=<snippet id>@S1@41:1-44:38` | `<snippet id>@<source alias>@<row>:<col>-<row>:<col>`; several snippets of one node are joined by `\|`. A node whose snippets do not fit this form keeps the JSON entry |
| grouped `E` | `N1>N2,N3` | all targets of one source on one line |
| default `EP` | `*>* etype=direct`, `* etype=summary` | type of edges with a target / of end edges; `N1>N2 etype=X` overrides it, `etype=` means no type |

The text is smaller, the data is the same: assets and the set of edges (with their
types) survive a roundtrip. The order of the edge list does not: sources keep their
first-occurrence order and targets keep their original order. A section is written
only when it saves space.

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
| `ch=count,has_any,href` | children summary; comma-separated to avoid conflicts with URLs. With `aliases` on `href` is `@Un`, a template from the `URL` section |
| `ds=a,b,n` | `descendant_statistics`: `has_leaf_children`, `is_every_child_leaf` (0/1) and `number_of_leaf_descendants`. Partial forms `dsl=`, `dse=`, `dsn=` are written when a field was excluded; `dsj=<json>` holds unusual values |

### Example Output

See [`examples/output_backend.ldf`](examples/output_backend.ldf) for the full LDF representation of [`examples/mock_backend_response.json`](examples/mock_backend_response.json).

## Features

- **Token-optimized**: Reduces token count by 4–6× compared to JSON
- **Bidirectional / lossless**: Round-trip fidelity for the backend schema fields (on `big_query_lineage.json` the restored assets equal the input exactly; `resource_key` is only present when the input had a value)
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
