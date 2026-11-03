# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [0.4.0] - 2026-11-03

### Added

- `no_urls` option (`--no-urls` on the CLI, `no_urls` argument of
  `convert_json_file_to_lineage`): drops every `href`, including those inside the
  catalog / project / space assignments. Same as excluding `href`.
- `legend` option (`--legend`, `legend` argument of `convert_json_file_to_lineage`):
  adds a `LEGEND` section as the first section, with one `SECTION=expansion` line
  (e.g. `HP=Hierarchical path`) per abbreviated section present (`GRAPH` and `START`
  are not listed). The decoder ignores it. Off by default.
- `URL` section with `@Un` references (aliases on): `children.href` is stored as a
  template with `{id}` (node token `ch=0,0,@U1`), and shared href prefixes in the
  `CA` / `PA` / `SA` blobs as `@U2/rest`.
- `SRC` section and compact `SCS` entries (aliases on): `N5=<snippet id>@S1@41:1-44:38`
  with the `source_code` id written once in `SRC`. Nodes with unusual snippets keep the
  JSON entry.
- `descendant_statistics` is now stored as the `ds=` node token (`dsl=`, `dse=`, `dsn=`
  when partly excluded, `dsj=` for unusual values). Before, it was silently lost in a
  round trip.

### Fixed

- The decoder no longer adds `resource_key: null` to assets that had no `resource_key`;
  the key is restored only when it has a value.

### Changed

- **The default output is different again**: with `aliases` on, `children.href` and
  `source_code_snippets` use the forms above (e.g. 9767 → 5861 bytes on
  `big_query_lineage.json`). The decoder still reads the older forms; `aliases=False` /
  `--no-aliases` output is unchanged.

---

## [0.3.0] - 2026-11-03

### Added

- Alias compression, on by default (`aliases` option; `--no-aliases` on the CLI;
  `aliases` argument of `convert_json_file_to_lineage`). New constructs:
  `REF` section with `@Rn` references in `HP` / `ATTR` / `DSD`, `*` default entry in
  `HP` / `DSD`, `IKP` section with `ikp=` node token, `NDEF` section with default node
  tokens, `E` grouped by source (`N1>N2,N3`), default `EP` lines (`*>* etype=…`,
  `* etype=…`).
- The decoder reads all of the above and the older, expanded form.

### Changed

- **The default output is different.** Documents written with the default options are
  smaller (e.g. 30% / 43% of the previous size on `out.json` / `big_query_lineage.json`)
  and need a reader from this version. Use `aliases=False` / `--no-aliases` for the
  0.2.0 form.
- The order of the edge list is not preserved with `aliases` on. The set of edges and
  their types is.

---

## [0.2.0] - 2026-11-02

### Added

- `exclude_fields` option of `json_to_lineage_format` (list of field names, dotted
  paths and `fnmatch` wildcards) that removes fields from the input before
  serialization, so the output has no empty separators, entries or sections.
  With an empty list the output is the same as without the option.
- `--exclude` option of `ldf json-to-lineage` and an `exclude_fields` argument of
  `convert_json_file_to_lineage`.
- The decoder reads the alternative forms written when only part of a record is
  excluded (`chc=`/`cha=`/`chh=`, `i=`/`n=`/`t=` in `HP`, `n=` / bare id in
  `BT`/`BC`/`DC`/`DSD`, attributes without name or value, node head without type).

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

---

## [0.1.1] - 2026-09-14

### Fixed

- Correct package license metadata from Apache-2.0 to BSD-3-Clause.

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

[0.4.0]: https://github.com/IBM/lineage-data-format/releases/tag/v0.4.0

[0.2.0]: https://github.com/IBM/lineage-data-format/releases/tag/v0.2.0
[0.1.1]: https://github.com/IBM/lineage-data-format/releases/tag/v0.1.1
[0.1.0]: https://github.com/IBM/lineage-data-format/releases/tag/v0.1.0
