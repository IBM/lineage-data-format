# Installation Guide

## For Users

### Using pip (recommended)

```bash
pip install ldf
```

### From source

```bash
git clone <repository-url>
cd lineage-data-format
pip install .
```

## For Development

### Setup virtual environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

### Running tests

```bash
pytest
```

### Running the example

```bash
python examples/basic_usage.py
```

## Using the CLI

After installation, the `ldf` command will be available:

```bash
# Convert JSON to lineage format
ldf json-to-lineage input.json output.ldf

# Convert lineage format to JSON
ldf lineage-to-json input.ldf output.json
```

## Troubleshooting

### "externally-managed-environment" error

If you see this error on macOS/Linux, you need to use a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install ldf
```

### Import errors

Make sure the package is installed:

```bash
pip list | grep ldf
```

If not installed, run:

```bash
pip install -e .