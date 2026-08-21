# Installation Guide

## Install from GitHub (recommended)

```bash
pip install git+https://github.com/IBM/lineage-data-format.git
```

Pin to a specific release tag:

```bash
pip install git+https://github.com/IBM/lineage-data-format.git@v0.1.0
```

## Install from source (development)

```bash
git clone https://github.com/IBM/lineage-data-format.git
cd lineage-data-format

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

## Verify installation

```python
from ldf import json_to_lineage_format, lineage_format_to_json
print("LDF installed successfully")
```

Or from the CLI:

```bash
ldf --help
```

## Running tests

```bash
pytest
pytest --cov=ldf   # with coverage
```

## Requirements

- Python 3.9 or newer
- No external runtime dependencies

## Troubleshooting

### "externally-managed-environment" error on macOS/Linux

Use a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install git+https://github.com/IBM/lineage-data-format.git
```

### Verify the package is installed

```bash
pip show lineage-data-format
```
