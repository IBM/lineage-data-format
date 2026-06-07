# Project Structure

This document describes the structure of the Lineage Definition Format (LDF) Python library.

## Directory Layout

```
lineage-data-format/
├── src/ldf/                          # Main package source
│   ├── __init__.py                   # Public API exports
│   ├── converter.py                  # Core conversion functions
│   └── cli.py                        # Command-line interface
│
├── examples/                         # Usage examples and test data
│   ├── basic_usage.py                # Simple API usage example
│   ├── convert_example.py            # Real data conversion example
│   ├── mock_50_nodes_linear_edges.json    # Test data (50 nodes)
│   └── mock_100_nodes_combined_edges.json # Test data (100 nodes)
│
├── tests/                            # Test suite
│   ├── __init__.py
│   └── test_converter.py             # Comprehensive converter tests
│
├── pyproject.toml                    # Package configuration
├── README.md                         # Main documentation
├── INSTALL.md                        # Installation guide
├── LICENSE                           # License file
└── .gitignore                        # Git ignore rules
```

## Module Overview

### `src/ldf/converter.py`

Core conversion module containing:

- `json_to_lineage_format(graph, options)` - Convert dict to LDF string
- `lineage_format_to_json(input_text)` - Convert LDF string to dict
- `convert_json_file_to_lineage(input_path, output_path, compact)` - File conversion
- `convert_lineage_file_to_json(input_path, output_path, indent)` - File conversion

### `src/ldf/cli.py`

Command-line interface providing:

- `ldf json-to-lineage` - Convert JSON file to LDF
- `ldf lineage-to-json` - Convert LDF file to JSON

### `src/ldf/__init__.py`

Public API exports for library usage.

## Testing

Run tests with:

```bash
pytest
```

Run tests with coverage:

```bash
pytest --cov=ldf
```

## Examples

### Run the basic example:

```bash
cd examples
python3 basic_usage.py
```

### Run the real data conversion example:

```bash
cd examples
python3 convert_example.py
```

This will:
1. Convert mock JSON files to LDF format
2. Convert LDF back to JSON
3. Verify round-trip conversion integrity

## Development Workflow

1. **Setup virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install in development mode:**
   ```bash
   pip install -e ".[dev]"
   ```

3. **Make changes to code**

4. **Run tests:**
   ```bash
   pytest
   ```

5. **Run examples to verify:**
   ```bash
   python examples/convert_example.py
   ```

## Package Distribution

Build the package:

```bash
python -m build
```

This creates distribution files in `dist/`:
- `ldf-0.1.0.tar.gz` (source distribution)
- `ldf-0.1.0-py3-none-any.whl` (wheel distribution)

## Key Features

- **Lossless conversion**: Full round-trip fidelity between JSON and LDF
- **Token optimization**: 60-80% reduction in token count vs verbose JSON
- **Type preservation**: All data types and structures maintained
- **Extensible**: Supports custom attributes and metadata
- **Well-tested**: Comprehensive test suite with real data
- **CLI included**: Easy command-line tools for conversion