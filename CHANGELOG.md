# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] — 2024-07-22

### Added

- Initial release of the Lineage Definition Format (LDF) Python library
- Full support for the backend `LineageGraph` API schema:
  - `assets_in_view` with all `LineageAsset` fields
  - `edges_in_view` with `FlowEdge.type` (`direct` / `summary`)
  - `graph_calculation_datetime` and `graph_calculation_timestamp`
- **New LDF sections** for complete backend schema coverage:
  - `EP` — edge properties (type per edge)
  - `BC` — business classifications lookup
  - `DC` — data classes lookup
  - `HP` — hierarchical path per node
  - `ATTR` — asset attributes per node
  - `SCS` — source code snippets per node (JSON blob)
  - `CA` / `PA` / `SA` — catalog / project / space assignments per node (JSON blob)
  - `DSD` — data source definition asset per node
- `identity_key` field serialized as `ik=` token in `N:` lines
- Boolean flags (`is_deduced`, `is_transforming`, `is_operational`, `is_temporary`, `is_favorite`) packed as bitmask `flags=N` in `N:` lines
- `children` summary (`count`, `has_any`, `href`) as `ch=count,has_any,href` in `N:` lines
- Technology deduplication by `id` (not name) to prevent UUID loss
- **Lossless percent-encoding** (`pct_encode` / `pct_decode`) covering all structural characters:
  - `%`, `\n`, `\r`, space, `,`, `[`, `]`, `|`, `=`, `:`
  - Applied to: tags, `node_type`, asset `name`, `resource_key`, `origin`, `identity_key`, HP name/type, ATTR values
- `pip install git+https://github.com/IBM/lineage-data-format.git` support
- GitHub Actions CI on Python 3.9, 3.11, 3.13
- 64 tests covering round-trip losslessness for all schema fields and edge cases

### Fixed

- Tags containing commas, spaces, brackets or `%` were silently corrupted
- `node_type` containing spaces was truncated at the first space
- Asset `name` containing newlines was split across `NAME:` section lines
- `ATTR` values containing `:` were truncated at the first colon
- `HP` name/type containing `:` or `|` were parsed incorrectly
- `resource_key` and `origin` containing spaces broke the N: line token parser
- Technology deduplication used `name` instead of `id` — two technologies with the same name but different IDs were merged into one
- `identity_key` field was not serialized or deserialized

[0.1.0]: https://github.com/IBM/lineage-data-format/releases/tag/v0.1.0
