# Lineage Definition Format (LDF)

A Python library for converting between JSON lineage data and a compact, token-optimized lineage definition format.

## Installation

```bash
pip install ldf
```

Or install from source:

```bash
git clone <repository-url>
cd lineage-data-format
pip install -e .
```

## Usage

### As a Library

```python
from ldf import (
    json_to_lineage_format,
    lineage_format_to_json,
    convert_json_file_to_lineage,
    convert_lineage_file_to_json,
)

# Convert in-memory data structures
lineage_graph = {
    'graph': 'graph-id',
    'start': 'N1',
    'edges': [['N1', 'N2'], ['N2', 'N3']],
    'nodes': {
        'N1': {
            'type': 'table',
            'path': 'T1/D1',
            'attributes': {'dq': 95, 'sla': 0}
        }
    },
    'dictionaries': {
        'T': {'T1': 'PostgreSQL'},
        'D': {'D1': 'production_db'},
        'ID': {'N1': 'uuid-1'},
        'NAME': {'N1': 'users_table'}
    }
}

# Convert to lineage format
ldf_text = json_to_lineage_format(lineage_graph)

# Convert back to JSON
json_data = lineage_format_to_json(ldf_text)

# Convert files directly
convert_json_file_to_lineage('input.json', 'output.ldf')
convert_lineage_file_to_json('input.ldf', 'output.json')
```

### Command Line Interface

```bash
# Convert JSON to lineage format
ldf json-to-lineage input.json output.ldf

# Convert with compact format (no extra whitespace)
ldf json-to-lineage input.json output.ldf --compact

# Convert lineage format to JSON
ldf lineage-to-json input.ldf output.json

# Specify JSON indentation
ldf lineage-to-json input.ldf output.json --indent 4
```

## Format Overview

The Lineage Definition Format is a compact text format designed to minimize token usage while maintaining readability. It uses:

- **Short aliases** for repeated values (N1, T1, D1, BT1)
- **Dictionary sections** to define aliases once and reference them multiple times
- **Compact node definitions** with inline attributes
- **Chain notation** for edges (N1>N2>N3)

### Example

```
GRAPH:
70080c2c-76a8-48b0-a3d1-8cdfa5bec747

START:
N1

E:
N1>N2>N3

N:
N1:table path=T1/D1 dq=95 sla=0 tags=[pii,critical] bt=[BT1]
N2:view path=T1/D1 dq=90 sla=1
N3:table path=T2/D2 dq=88 sla=0

T:
T1=PostgreSQL
T2=MySQL

D:
D1=production_db
D2=analytics_db

TID:
T1=tech-uuid-1
T2=tech-uuid-2

DID:
D1=db-uuid-1
D2=db-uuid-2

ID:
N1=node-uuid-1
N2=node-uuid-2
N3=node-uuid-3

NAME:
N1=users_table
N2=active_users_view
N3=user_analytics

BT:
BT1=bt-uuid-1|Personal Information
```

## Features

- **Token-optimized**: Reduces token count by 60-80% compared to verbose JSON
- **Bidirectional**: Lossless conversion between JSON and LDF formats
- **Type-safe**: Preserves all data types and structures
- **Extensible**: Supports custom attributes and metadata
- **CLI included**: Easy command-line conversion tools

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests (with pytest if installed)
pytest

# Or run tests without pytest
python3 run_tests.py

# Run tests with coverage (requires pytest)
pytest --cov=ldf
```

## License

See [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
