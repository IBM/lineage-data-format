# Project Structure

## Directory Layout

```
lineage-data-format/
├── src/ldf/                          # Main package source
│   ├── __init__.py                   # Public API exports and version
│   ├── converter.py                  # Core serializer / deserializer
│   └── cli.py                        # Command-line interface
│
├── examples/                         # Usage examples and reference data
│   ├── mock_backend_response.json    # Sample backend LineageGraph JSON
│   └── output_backend.ldf            # LDF output for the sample above
│
├── tests/                            # Test suite
│   ├── __init__.py
│   ├── test_converter.py             # Comprehensive converter tests
│   ├── test_exclude_fields.py        # exclude_fields tests (aliases on and off)
│   ├── test_aliases.py               # Alias compression: encoder, decoder, real files
│   ├── test_urls.py                  # URL section: @Un templates and prefixes
│   ├── test_no_urls.py               # no_urls option: library, file helper, CLI
│   ├── test_scs.py                   # Compact SCS entries and SRC section
│   ├── test_descendant_statistics.py # ds= node token
│   └── test_legend.py                # legend option: library, file helper, CLI
│
├── .github/workflows/ci.yml          # GitHub Actions CI
├── pyproject.toml                    # Package configuration (hatchling)
├── CHANGELOG.md                      # Version history
├── README.md                         # Main documentation
├── INSTALL.md                        # Installation guide
└── LICENSE                           # Apache 2.0 license
```

## Public API

### `from ldf import ...`

| Function | Description |
|---|---|
| `json_to_lineage_format(graph, options)` | Convert backend `LineageGraph` dict → LDF string |
| `lineage_format_to_json(input_text)` | Convert LDF string → backend `LineageGraph` dict |
| `convert_json_file_to_lineage(input_path, output_path, compact, exclude_fields, aliases, no_urls, legend)` | File I/O wrapper |
| `convert_lineage_file_to_json(input_path, output_path, indent)` | File I/O wrapper |

`json_to_lineage_format` options: `compact`, `aliases` (default `True`), `no_urls`,
`legend`, `exclude_fields`. Every CLI flag (`--compact`, `--no-aliases`, `--no-urls`,
`--legend`, `--exclude`) only passes one of them on.

### `src/ldf/converter.py`

Core module. Both conversion directions cover the backend `LineageGraph` schema
(`assets_in_view`, `edges_in_view`, `graph_calculation_datetime`,
`graph_calculation_timestamp`). `resource_key` is restored only when the input had a value.

### `src/ldf/cli.py`

Command-line interface providing:

- `ldf json-to-lineage` — convert JSON file to LDF (`--compact`, `--no-aliases`, `--no-urls`, `--legend`, `--exclude`)
- `ldf lineage-to-json` — convert LDF file to JSON

## Development Workflow

```bash
# Create virtual environment and install with dev dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=ldf
```

## Package Distribution

```bash
# Build wheel and sdist
pip install build
python -m build
# Artefacts appear in dist/
```
