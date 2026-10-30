# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Changed

- An edge without a `target` (end edge) is written as `N7` instead of `N7>` in `E` and `EP`.
  This saves one character per occurrence and one token per end edge that has a type
  (in `EP`; in `E` the `>` and the newline are a single token, so nothing is saved there).
  The decoder still accepts the old `N7>` form.

### Fixed

- The decoder no longer drops end edges (edges without a `target`). They are returned as an
  edge with only `source` (and `type`, when present in `EP`), both from `N7` and from the old `N7>`.
- Edge types in `EP` are matched to edges in order, per `source>target` pair. Several edges
  between the same pair (e.g. a `direct` and a `summary` edge) keep their own type instead of
  all taking the last one. Known limit: an untyped edge written before a typed edge on the same
  pair comes back with the type on the first of the two.

### Added

- `exclude_fields` option of `json_to_lineage_format` (list of field names, dotted
  paths and `fnmatch` wildcards) that removes fields from the input before
  serialization, so the output has no empty separators, entries or sections.
  The default (empty list) leaves the output unchanged.
- The decoder reads the alternative forms written when only part of a record is
  excluded (`chc=`/`cha=`/`chh=`, `i=`/`n=`/`t=` in `HP`, `n=` / bare id in
  `BT`/`BC`/`DC`/`DSD`, attributes without name or value, node head without type).

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

## [0.1.1] - 2026-09-14

### Fixed

- Correct package license metadata from Apache-2.0 to BSD-3-Clause.