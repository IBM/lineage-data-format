"""
Converter module for lineage data format.
Provides functions to convert between JSON and lineage format.
"""

import json
import logging
from collections import Counter
from fnmatch import fnmatchcase
from typing import Dict, List, Any, Optional, Set, Tuple

logger = logging.getLogger(__name__)

_REMOVED = object()
_RECORD_LISTS = ("assets_in_view", "edges_in_view")  # paths are relative to each record
# Marks a field that was removed by exclude_fields (distinct from any real value).
_ABSENT = object()


def _matching_patterns(path: Tuple[str, ...], patterns: List[Tuple[str, ...]]) -> List[int]:
    """Indexes of exclude patterns matching the key path ``path``.

    A pattern without a dot matches the last key of the path (any depth).
    A dotted pattern must match the whole path, segment by segment. The path
    is relative to the asset / edge ("technology.id"). Arrays are transparent:
    they do not add a path segment. Segments use fnmatch syntax.
    """
    found = []
    for i, pattern in enumerate(patterns):
        if len(pattern) == 1:
            ok = fnmatchcase(path[-1], pattern[0])
        else:
            ok = len(pattern) == len(path) and all(
                fnmatchcase(p, s) for p, s in zip(path, pattern)
            )
        if ok:
            found.append(i)
    return found


def _prune_node(
    node: Any,
    path: Tuple[str, ...],
    patterns: List[Tuple[str, ...]],
    hits: Set[int],
) -> Any:
    """Return a pruned copy of ``node`` (input is never mutated).

    Returns ``_REMOVED`` when pruning left a dict/list empty, so that no empty
    containers remain in the output.
    """
    if isinstance(node, dict):
        out: Dict[str, Any] = {}
        removed_any = False
        for key, value in node.items():
            child_path = path + (str(key),)
            matched = _matching_patterns(child_path, patterns)
            # Always descend (even into removed values) so that every pattern
            # which matches something is recorded as a hit.
            pruned = _prune_node(value, child_path, patterns, hits)
            if matched:
                hits.update(matched)
                removed_any = True
                continue
            if pruned is _REMOVED:
                removed_any = True
                continue
            out[key] = pruned
        return _REMOVED if removed_any and not out else out
    if isinstance(node, list):
        items = []
        removed_any = False
        for item in node:
            pruned = _prune_node(item, path, patterns, hits)
            if pruned is _REMOVED:
                removed_any = True
                continue
            items.append(pruned)
        return _REMOVED if removed_any and not items else items
    return node


def _apply_exclusions(graph: Dict[str, Any], exclude_fields: List[str]) -> Tuple[Dict[str, Any], bool]:
    """Return ``(pruned copy of graph, whether any field was removed)``.

    The input graph is never mutated.
    """
    if isinstance(exclude_fields, str) or not all(isinstance(p, str) for p in exclude_fields):
        raise TypeError("exclude_fields must be a list of str")

    patterns = [tuple(p.split(".")) for p in exclude_fields]
    hits: Set[int] = set()

    result: Dict[str, Any] = {}
    for key, value in graph.items():
        matched = _matching_patterns((key,), patterns)
        if key in _RECORD_LISTS and isinstance(value, list):
            records = []
            for record in value:
                pruned = _prune_node(record, (), patterns, hits)
                records.append({} if pruned is _REMOVED else pruned)
            pruned_value: Any = records
        else:
            pruned_value = _prune_node(value, (key,), patterns, hits)
        if matched:
            hits.update(matched)
            continue
        if pruned_value is not _REMOVED:
            result[key] = pruned_value

    # Fields the serializer cannot do without. Only a field that was present in
    # the input and removed by exclude_fields is an error: edges without a
    # "target" (e.g. "summary" edges) are valid input and are left untouched.
    for list_key, required_fields in (
        ("assets_in_view", ("id",)),
        ("edges_in_view", ("source", "target")),
    ):
        originals = graph.get(list_key)
        pruned_records = result.get(list_key)
        if not isinstance(originals, list) or pruned_records is None:
            continue
        for i, (orig, pruned) in enumerate(zip(originals, pruned_records)):
            for required in required_fields:
                if required in orig and required not in pruned:
                    raise ValueError(
                        f"exclude_fields cannot remove required field '{required}' "
                        f"(from {list_key}[{i}])"
                    )

    for i in range(len(patterns)):
        if i not in hits:
            logger.debug("exclude_fields entry %r matched no field; ignoring", exclude_fields[i])

    return result, bool(hits)

# ---------------------------------------------------------------------------
# Alias compression helpers (used when options["aliases"] is on)
# ---------------------------------------------------------------------------

# Node-line tokens that may get a default value in the NDEF section.
_NDEF_KEYS = ("rk", "origin", "path", "tags", "bt", "bc", "dc", "flags",
              "ch", "chc", "cha", "chh")


def _choose_ik_prefixes(
    iks: List[Optional[str]],
    max_prefixes: int = 16,
) -> Tuple[List[str], List[Optional[str]]]:
    """Pick shared identity_key prefixes (cut after a "/") greedily by net gain.

    ``iks`` are already percent-encoded; "/" is never encoded, so a cut after
    it never splits an escape sequence. Returns (used prefixes, per-node
    prefix or None). A node uses the longest chosen prefix it starts with.
    """
    users: Dict[str, List[int]] = {}
    for i, ik in enumerate(iks):
        if not ik:
            continue
        pos = ik.find("/")
        while pos != -1:
            users.setdefault(ik[:pos + 1], []).append(i)
            pos = ik.find("/", pos + 1)
    users = {p: u for p, u in users.items() if len(u) >= 2}

    cur = [0] * len(iks)  # length of the prefix a node currently uses
    assigned: List[Optional[str]] = [None] * len(iks)
    chosen: List[str] = []
    for n in range(1, max_prefixes + 1):
        key_len = len(f"P{n}")
        best: Optional[str] = None
        best_gain = 0
        for p, us in users.items():
            if p in chosen:
                continue
            length = len(p)
            gain = -(key_len + 1 + length + 1)  # the "P1=<prefix>" line
            for i in us:
                if length > cur[i]:
                    gain += length - cur[i]
                    if assigned[i] is None:
                        gain -= len(" ikp=") + key_len
            if gain > best_gain:
                best, best_gain = p, gain
        if best is None:
            break
        chosen.append(best)
        for i in users[best]:
            if len(best) > cur[i]:
                cur[i] = len(best)
                assigned[i] = best
    in_use = set(assigned)
    return [p for p in chosen if p in in_use], assigned


def _choose_node_defaults(node_tokens: List[List[Tuple[str, str]]]) -> List[Tuple[str, str]]:
    """Most common value of each node-line token, kept only when writing it
    once in NDEF (and an empty "key=" on nodes that lack it) is shorter than
    repeating it on every node."""
    maps = [dict(tokens) for tokens in node_tokens]
    n = len(maps)
    defaults: List[Tuple[str, str]] = []
    total = 0
    for key in _NDEF_KEYS:
        values = [m[key] for m in maps if key in m]
        # An empty value cannot be told apart from the "key=" removal token and
        # a value with a space would break the space-separated NDEF line.
        if not values or any(v == "" or " " in v for v in values):
            continue
        value, count = Counter(values).most_common(1)[0]
        absent = n - len(values)
        token_len = len(key) + len(value) + 2  # " key=value"
        gain = count * token_len - absent * (len(key) + 2) - token_len
        if gain > 0:
            defaults.append((key, value))
            total += gain
    return defaults if total > len("NDEF:") + 3 else []


def _apply_default(entries: Dict[str, str], all_aliases: List[str]) -> Dict[str, str]:
    """Replace the most common per-node value by a "*" entry. Nodes with
    another value keep it; nodes without an entry get an explicit empty one."""
    counter = Counter(v for v in entries.values() if v)
    if not counter:
        return entries
    value, count = counter.most_common(1)[0]
    if count < 2:
        return entries
    saved = sum(len(a) + len(value) + 2 for a in all_aliases if entries.get(a) == value)
    cost = len("*=") + len(value) + 1 + sum(len(a) + 2 for a in all_aliases if a not in entries)
    if saved <= cost:
        return entries
    out: Dict[str, str] = {"*": value}
    for a in all_aliases:
        v = entries.get(a)
        if v != value:
            out[a] = v if v is not None else ""
    return out


def _build_ref_pool(
    sections: Dict[str, Dict[str, str]],
) -> Tuple[Dict[str, Dict[str, str]], Dict[str, str]]:
    """Move repeated values of per-node sections into a shared REF pool.

    A repeated whole entry value, or a repeated "|"-separated element, is
    replaced by "@Rn". The definition of a multi-element value refers to its
    element aliases, which the decoder expands recursively.
    """
    values: Counter = Counter()
    reserved: Set[str] = set()
    for entries in sections.values():
        for v in entries.values():
            if not v:
                continue
            values[v] += 1
            for el in v.split("|"):
                if el.startswith("@"):
                    reserved.add(el)

    ref_of: Dict[str, str] = {}
    idx = [0]

    def new_key() -> str:
        # A literal element that already looks like "@Rn" must never be
        # confused with a reference, so such keys are skipped.
        while True:
            idx[0] += 1
            key = f"R{idx[0]}"
            if f"@{key}" not in reserved:
                return key

    def worth(count: int, length: int) -> bool:
        key_len = len(str(idx[0] + 1)) + 1
        return count * (length - (key_len + 1)) - (key_len + 1 + length + 1) > 0

    # 1. whole entry values that repeat
    for v, c in sorted(values.items(), key=lambda kv: -kv[1] * len(kv[0])):
        if c >= 2 and worth(c, len(v)):
            ref_of[v] = new_key()
    wholes = list(ref_of)

    # 2. single elements that repeat (a multi-element whole is defined once)
    elements: Counter = Counter()
    for entries in sections.values():
        for v in entries.values():
            if v and v not in ref_of:
                for el in v.split("|"):
                    if el:
                        elements[el] += 1
    for v in wholes:
        if "|" in v:
            for el in v.split("|"):
                if el:
                    elements[el] += 1
    for el, c in sorted(elements.items(), key=lambda kv: -kv[1] * len(kv[0])):
        if el not in ref_of and c >= 2 and worth(c, len(el)):
            ref_of[el] = new_key()

    def by_element(v: str) -> str:
        return "|".join("@" + ref_of[el] if el in ref_of else el for el in v.split("|"))

    def sub(v: str) -> str:
        if not v:
            return v
        return "@" + ref_of[v] if v in ref_of else by_element(v)

    defs = {key: (by_element(v) if "|" in v else v) for v, key in ref_of.items()}
    defs = dict(sorted(defs.items(), key=lambda kv: int(kv[0][1:])))
    new_sections = {name: {a: sub(v) for a, v in entries.items()}
                    for name, entries in sections.items()}
    return new_sections, defs


def _encode_edges(
    edges_raw: List[Dict[str, Any]],
    alias_map: Dict[str, str],
) -> Tuple[List[str], List[str]]:
    """E and EP lines with edges grouped by source ("N1>N2,N3") and default
    edge types. Sources keep first-occurrence order and targets keep their
    original order, so the set of edges and their types survive a roundtrip
    (the order of the list across sources does not)."""
    order: List[Any] = []
    seen: Set[str] = set()
    targets: Dict[str, List[Tuple[str, str]]] = {}
    ends: Dict[str, List[str]] = {}
    solo: Dict[int, Tuple[str, str, str]] = {}
    for i, edge in enumerate(edges_raw):
        src_raw = edge.get("source", "")
        tgt_raw = edge.get("target", "")
        etype = edge.get("type") or ""
        if src_raw in alias_map and (not tgt_raw or tgt_raw in alias_map):
            src = alias_map[src_raw]
            if src not in seen:
                seen.add(src)
                order.append(src)
            if tgt_raw:
                targets.setdefault(src, []).append((alias_map[tgt_raw], etype))
            else:
                ends.setdefault(src, []).append(etype)
        else:
            # Unknown ids are written as a separate line, as in the legacy form.
            order.append(i)
            solo[i] = (alias_map.get(src_raw, src_raw), alias_map.get(tgt_raw, tgt_raw), etype)

    e_lines: List[str] = []
    emitted: List[Tuple[str, bool, str]] = []  # (pair, has_target, type) in E order
    for key in order:
        if isinstance(key, int):
            src, tgt, etype = solo[key]
            pair = f"{src}>{tgt}" if tgt else src
            e_lines.append(pair)
            emitted.append((pair, bool(tgt), etype))
            continue
        group = targets.get(key)
        if group:
            e_lines.append(f"{key}>{','.join(t for t, _ in group)}")
            for t, et in group:
                emitted.append((f"{key}>{t}", True, et))
        for et in ends.get(key, []):
            e_lines.append(key)
            emitted.append((key, False, et))

    default_line = {True: "*>*", False: "*"}
    default_lines: List[str] = []
    explicit: Set[int] = set()
    for kind in (True, False):
        idxs = [i for i, (_, k, _) in enumerate(emitted) if k == kind]
        if not idxs:
            continue
        candidates = [""] + sorted({emitted[i][2] for i in idxs} - {""})
        best: Optional[Tuple[int, str, List[int]]] = None
        for cand in candidates:
            # The decoder hands a pair's explicit entries out in E order, so
            # every edge up to the pair's last non-default one needs its own.
            last: Dict[str, int] = {}
            for i in idxs:
                if emitted[i][2] != cand:
                    last[emitted[i][0]] = i
            incl = [i for i in idxs if emitted[i][0] in last and i <= last[emitted[i][0]]]
            cost = sum(len(emitted[i][0]) + len(" etype=") + len(emitted[i][2]) + 1 for i in incl)
            if cand:
                cost += len(default_line[kind]) + len(" etype=") + len(cand) + 1
            if best is None or cost < best[0]:
                best = (cost, cand, incl)
        assert best is not None
        if best[1]:
            default_lines.append(f"{default_line[kind]} etype={best[1]}")
        explicit.update(best[2])

    ep_lines = default_lines + [f"{emitted[i][0]} etype={emitted[i][2]}" for i in sorted(explicit)]
    return e_lines, ep_lines




def json_to_lineage_format(graph: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> str:
    """
    Convert a backend LineageGraph dict to lineage format string.

    Args:
        graph: Dictionary in backend LineageGraph format with keys:
            - assets_in_view: List of asset dicts (LineageAsset)
            - edges_in_view: List of edge dicts (FlowEdge)
            - graph_calculation_datetime: ISO datetime string (optional)
            - graph_calculation_timestamp: Unix timestamp (optional)
        options: Optional dict with:
            - 'compact': boolean flag
            - 'aliases': boolean flag (default True). Enables the alias
              mechanisms that remove repeated values from the output (see
              .planning/ldf-aliases-plan.md). False keeps the legacy,
              fully expanded form. The decoder reads both forms.
            - 'exclude_fields': list of str, fields removed from the input
              before serialization (default: empty, output unchanged).
              A name without a dot ("children") removes that field at every
              nesting level. A dotted path ("technology.id",
              "hierarchical_path.type") removes only that field, relative to
              an asset / edge / the graph root; arrays take no index.
              Removing an object or array removes its whole content.
              fnmatch wildcards are supported ("is_*", "*_assignments").
              Unknown entries are ignored (debug log). The asset ``id`` and
              edge ``source`` / ``target`` cannot be excluded (ValueError).

    Returns:
        String in lineage format
    """
    compact = options.get("compact", False) if options else False
    aliases = options.get("aliases", True) if options else True
    exclude_fields = options.get("exclude_fields") if options else None
    # True only when some field was actually removed (see opt() below); an
    # empty list or a list matching nothing keeps the output byte-identical.
    excluding = False
    if exclude_fields:
        pruned_graph, excluding = _apply_exclusions(graph, exclude_fields)
        if excluding:
            graph = pruned_graph
    # In compact mode: no blank lines between sections, but entries still
    # use newlines so the line-based parser can read them back correctly.
    nl = "\n"
    section_break = "\n" if compact else "\n\n"

    assets: List[Dict[str, Any]] = graph.get("assets_in_view", [])
    edges_raw: List[Dict[str, Any]] = graph.get("edges_in_view", [])
    dt = graph.get("graph_calculation_datetime")
    ts = graph.get("graph_calculation_timestamp")

    # ------------------------------------------------------------------ helpers

    def pct_encode(s: str) -> str:
        """Percent-encode characters that are structural in LDF tokens.
        Handles all characters that would break inline parsing:
          %  → %25  (must be first to avoid double-encoding)
          \n → %0A  (breaks line-based section parsing)
          \r → %0D  (normalised away but encode for safety)
          space → %20  (breaks space-delimited N: token parsing)
          ,  → %2C  (breaks comma-delimited array parsing in tags/bt/bc/dc)
          [  → %5B  (structural in array notation)
          ]  → %5D  (structural in array notation)
          |  → %7C  (section-level field separator)
          =  → %3D  (key=value separator)
        """
        s = s.replace("%", "%25")
        s = s.replace("\r", "%0D")
        s = s.replace("\n", "%0A")
        s = s.replace(" ", "%20")
        s = s.replace(",", "%2C")
        s = s.replace("[", "%5B")
        s = s.replace("]", "%5D")
        s = s.replace("|", "%7C")
        s = s.replace("=", "%3D")
        return s

    def encode_array(arr: Optional[List[Any]]) -> str:
        if arr:
            return f"[{','.join(str(x) for x in arr)}]"
        return "[]"

    def dict_section(name: str, dict_data: Optional[Dict[str, str]]) -> str:
        if not dict_data:
            return ""
        entries = [f"{k}={v}" for k, v in dict_data.items()]
        return name + ":" + nl + nl.join(entries)

    def kv_section(name: str, entries: Dict[str, str]) -> str:
        """Generic per-node section: NAME:\nN1=value\n..."""
        if not entries:
            return ""
        lines = [f"{k}={v}" for k, v in entries.items()]
        return name + ":" + nl + nl.join(lines)

    def opt(d: Dict[str, Any], key: str, default: Any) -> Any:
        """d[key]; if missing: _ABSENT when exclude_fields is non-empty (a missing
        field is treated as excluded and must leave no trace), otherwise the
        legacy default."""
        if key in d:
            return d[key]
        return _ABSENT if exclude_fields else default

    def _encode_hp_field(s: str) -> str:
        # Full structural encoding via pct_encode, then also encode ":"
        # which pct_encode leaves alone (it's only structural in HP segments).
        s = pct_encode(s)
        s = s.replace(":", "%3A")
        return s

    def _encode_hp_segment(h: Dict[str, Any]) -> str:
        # Fields are positional (id:name:type). Trailing fields that were
        # excluded are dropped so no dangling ":" separator is left behind.
        fields = [
            (k, opt(h, k, "")) for k in ("id", "name", "type")
        ]
        present = [(k, v) for k, v in fields if v is not _ABSENT]
        if [k for k, _ in present] == [k for k, _ in fields][:len(present)]:
            # Present fields form a prefix of (id, name, type): positional.
            return ":".join(_encode_hp_field(v) if k != "id" else v for k, v in present)
        # A gap would leave an empty slot ("id::type"): use named fields instead.
        # The id never contains "=", so a "=" in the first field marks this form.
        return ":".join(f"{k[0]}={_encode_hp_field(v)}" for k, v in present)

    def _encode_attr(a: Dict[str, Any]) -> str:
        name = opt(a, "name", "")
        value = opt(a, "value", "")
        name_s = "" if name is _ABSENT else name
        if value is _ABSENT:
            return name_s
        return f"{name_s}={pct_encode(value)}"

    # ------------------------------------------------------------------ alias maps

    # Node alias: asset.id -> N1, N2, ...
    alias_map: Dict[str, str] = {}
    for i, asset in enumerate(assets):
        alias_map[asset["id"]] = f"N{i + 1}"

    # Technology lookup (deduplicate by id, fallback to name when id absent)
    t_dict: Dict[str, str] = {}    # T1 -> name
    tid_dict: Dict[str, str] = {}  # T1 -> id
    _tech_id_to_key: Dict[str, str] = {}   # tech id  -> T-alias
    _tech_name_to_key: Dict[str, str] = {} # tech name -> T-alias (fallback)
    _tech_idx = 1

    def get_tech_key(tech: Dict[str, Any]) -> str:
        nonlocal _tech_idx
        tech_id = tech.get("id", "")
        name = opt(tech, "name", "")
        # Prefer deduplication by id; fall back to name when id is absent
        dedup_key = tech_id if tech_id else name
        dedup_store = _tech_id_to_key if tech_id else _tech_name_to_key
        if dedup_key not in dedup_store:
            key = f"T{_tech_idx}"
            _tech_idx += 1
            dedup_store[dedup_key] = key
            if name is not _ABSENT:
                t_dict[key] = name
            if tech_id:
                tid_dict[key] = tech_id
        return dedup_store[dedup_key]

    # BT / BC / DC lookups (deduplicate by id|name)
    bt_dict: Dict[str, str] = {}
    bc_dict: Dict[str, str] = {}
    dc_dict: Dict[str, str] = {}
    # Reverse indexes (combined → alias) for O(1) dedup instead of O(n) scan.
    _bt_rev: Dict[str, str] = {}
    _bc_rev: Dict[str, str] = {}
    _dc_rev: Dict[str, str] = {}

    def get_lookup_key(
        store: Dict[str, str],
        reverse: Dict[str, str],
        idx_ref: List[int],
        prefix: str,
        item_id: Any,
        item_name: Any,
    ) -> str:
        # Excluded fields leave no trace: no trailing "|" when the name is
        # absent, and the named form "n=<name>" (no empty id slot) when the
        # id is absent. An id never contains "=" nor "|".
        if item_id is _ABSENT:
            combined = f"n={item_name}"
        elif item_name is _ABSENT:
            combined = item_id
        else:
            combined = f"{item_id}|{item_name}"
        if combined in reverse:
            return reverse[combined]
        key = f"{prefix}{idx_ref[0]}"
        idx_ref[0] += 1
        store[key] = combined
        reverse[combined] = key
        return key

    bt_idx_ref = [1]
    bc_idx_ref = [1]
    dc_idx_ref = [1]

    # ID and NAME lookups
    id_dict: Dict[str, str] = {}
    name_dict: Dict[str, str] = {}

    # Per-node section dicts
    hp_entries: Dict[str, str] = {}
    attr_entries: Dict[str, str] = {}
    scs_entries: Dict[str, str] = {}
    ca_entries: Dict[str, str] = {}
    pa_entries: Dict[str, str] = {}
    sa_entries: Dict[str, str] = {}
    dsd_entries: Dict[str, str] = {}

    # ------------------------------------------------------------------ node lines

    node_heads: List[str] = []
    node_tokens: List[List[Tuple[str, str]]] = []

    for asset in assets:
        asset_id = asset["id"]
        alias = alias_map[asset_id]

        id_dict[alias] = asset_id
        # pct_encode preserves \n and other structural chars in the name value
        # so the line-based NAME: section parser doesn't split mid-value.
        asset_name = opt(asset, "name", "")
        if asset_name is not _ABSENT:
            name_dict[alias] = pct_encode(asset_name)

        # --- technology path alias
        tech = asset.get("technology")
        tech_alias = get_tech_key(tech) if tech else ""

        # --- BT aliases
        bt_aliases: List[str] = []
        for term in asset.get("business_terms") or []:
            k = get_lookup_key(bt_dict, _bt_rev, bt_idx_ref, "BT", opt(term, "id", ""), opt(term, "name", ""))
            bt_aliases.append(k)

        # --- BC aliases
        bc_aliases: List[str] = []
        for cls in asset.get("business_classifications") or []:
            k = get_lookup_key(bc_dict, _bc_rev, bc_idx_ref, "BC", opt(cls, "id", ""), opt(cls, "name", ""))
            bc_aliases.append(k)

        # --- DC aliases
        dc_aliases: List[str] = []
        for dc in asset.get("data_classes") or []:
            k = get_lookup_key(dc_dict, _dc_rev, dc_idx_ref, "DC", opt(dc, "id", ""), opt(dc, "name", ""))
            dc_aliases.append(k)

        # --- flags bitmask
        flags = (
            (1 if asset.get("is_deduced") else 0)
            | (2 if asset.get("is_transforming") else 0)
            | (4 if asset.get("is_operational") else 0)
            | (8 if asset.get("is_temporary") else 0)
            | (16 if asset.get("is_favorite") else 0)
        )

        # --- children
        children = asset.get("children")

        # --- build N: line parts
        # rk, origin, ik and type are percent-encoded so spaces (and structural
        # chars) don't break the space-delimited inline token format.
        # Tags are individually percent-encoded so commas/spaces/brackets inside
        # a tag value don't corrupt the comma-delimited array.
        # When "type" is excluded the head token is the bare alias (no ":").
        raw_type = opt(asset, "type", "")
        head = alias if raw_type is _ABSENT else f"{alias}:{pct_encode(raw_type)}"
        # Tokens are kept as (key, value) pairs so the alias stage can factor
        # out defaults; without aliases they are joined exactly as before.
        parts: List[Tuple[str, str]] = []
        if asset.get("resource_key"):
            parts.append(("rk", pct_encode(asset['resource_key'])))
        if asset.get("origin"):
            parts.append(("origin", pct_encode(asset['origin'])))
        if asset.get("identity_key"):
            parts.append(("ik", pct_encode(asset['identity_key'])))
        if tech_alias:
            parts.append(("path", tech_alias))
        tags = asset.get("tags") or []
        if tags:
            parts.append(("tags", encode_array([pct_encode(tag) for tag in tags])))
        if bt_aliases:
            parts.append(("bt", encode_array(bt_aliases)))
        if bc_aliases:
            parts.append(("bc", encode_array(bc_aliases)))
        if dc_aliases:
            parts.append(("dc", encode_array(dc_aliases)))
        if flags:
            parts.append(("flags", str(flags)))
        if children is not None:
            # Use comma as separator: ch=count,has_any,href
            # (href may contain colons from URLs, comma never appears in count/has_any/href)
            # Excluded trailing fields are dropped, not left as empty slots.
            ch_count = opt(children, "count", 0)
            ch_has_any = opt(children, "has_any", False)
            ch_href = opt(children, "href", "")
            ch_present = [
                (k, v) for k, v in (
                    ("count", ch_count),
                    ("has_any", ch_has_any),
                    ("href", ch_href),
                ) if v is not _ABSENT
            ]
            ch_keys = [k for k, _ in ch_present]
            ch_values = [
                str(v) if k == "count" else ("1" if v else "0") if k == "has_any" else str(v)
                for k, v in ch_present
            ]
            if ch_keys == ["count", "has_any", "href"][:len(ch_keys)]:
                if ch_values:
                    parts.append(("ch", ",".join(ch_values)))
            else:
                # A gap would leave an empty slot ("ch=,0,href"): use named tokens.
                token = {"count": "chc", "has_any": "cha", "href": "chh"}
                for k, v in zip(ch_keys, ch_values):
                    parts.append((token[k], pct_encode(v) if k == 'href' else v))

        node_heads.append(head)
        node_tokens.append(parts)

        # --- HP section
        # Format: "id:name:type|id:name:type".
        # id is always hex/UUID → never contains ":" or "|".
        # name and type CAN contain ":" and "|", so both are percent-encoded
        # ("%3A" for ":", "%7C" for "|", "%25" for "%").
        # This makes the three-field split unambiguous on parse.
        hp_items = asset.get("hierarchical_path") or []
        if hp_items:
            hp_entries[alias] = "|".join(_encode_hp_segment(h) for h in hp_items)

        # --- ATTR section
        # Format: "name=value|name=value". The separator between attr entries
        # is "|". Within each entry "=" separates name from value.
        # "name" is always a system identifier (no "=" in it).
        # "value" may contain ":" so we cannot use ":" as separator here.
        # "value" may contain "|" so we percent-encode "|" and "%" in values.
        attr_items = asset.get("attributes") or []
        if attr_items:
            attr_entries[alias] = "|".join(_encode_attr(a) for a in attr_items)

        # --- SCS / CA / PA / SA sections (JSON blobs)
        scs = asset.get("source_code_snippets")
        if scs:
            scs_entries[alias] = json.dumps(scs, ensure_ascii=False).replace("\n", " ")

        ca = asset.get("catalog_assignments")
        if ca:
            ca_entries[alias] = json.dumps(ca, ensure_ascii=False).replace("\n", " ")

        pa = asset.get("project_assignments")
        if pa:
            pa_entries[alias] = json.dumps(pa, ensure_ascii=False).replace("\n", " ")

        sa = asset.get("space_assignments")
        if sa:
            sa_entries[alias] = json.dumps(sa, ensure_ascii=False).replace("\n", " ")

        # --- DSD section
        dsd = asset.get("data_source_definition_asset")
        if dsd:
            dsd_id = opt(dsd, "id", "")
            dsd_name = opt(dsd, "name", "")
            if dsd_id is _ABSENT:
                dsd_entries[alias] = f"n={pct_encode(dsd_name)}"
            elif dsd_name is _ABSENT:
                dsd_entries[alias] = dsd_id
            else:
                dsd_entries[alias] = f"{dsd_id}:{pct_encode(dsd_name)}"

    # ------------------------------------------------------------------ GRAPH section

    # First line is a stable marker; dt= and ts= carry the actual values.
    graph_lines = ["lineage_graph"]
    if dt:
        graph_lines.append(f"dt={dt}")
    if ts is not None:
        graph_lines.append(f"ts={ts}")
    GRAPH = "GRAPH:" + nl + nl.join(graph_lines)

    # ------------------------------------------------------------------ START section

    start_alias = alias_map[assets[0]["id"]] if assets else "N1"
    START = f"START:{nl}{start_alias}"

    # ------------------------------------------------------------------ E / EP sections

    edge_lines: List[str] = []
    ep_lines: List[str] = []

    if aliases:
        edge_lines, ep_lines = _encode_edges(edges_raw, alias_map)
    else:
        for edge in edges_raw:
            src_alias = alias_map.get(edge.get("source", ""), edge.get("source", ""))
            tgt_alias = alias_map.get(edge.get("target", ""), edge.get("target", ""))
            # An end edge (no target) is written as just the source alias: "N7", not "N7>".
            pair = f"{src_alias}>{tgt_alias}" if tgt_alias else src_alias
            edge_lines.append(pair)
            if edge.get("type"):
                ep_lines.append(f"{pair} etype={edge['type']}")

    E = "E:" + nl + nl.join(edge_lines) if edge_lines else ""
    EP = "EP:" + nl + nl.join(ep_lines) if ep_lines else ""

    # ------------------------------------------------------------------ N section

    ikp_dict: Dict[str, str] = {}
    ndef_line = ""
    ref_dict: Dict[str, str] = {}

    if aliases:
        # 1. identity_key prefixes
        iks = [dict(tokens).get("ik") for tokens in node_tokens]
        prefixes, assigned = _choose_ik_prefixes(iks)
        pkey = {p: f"P{n}" for n, p in enumerate(prefixes, 1)}
        ikp_dict = {k: p for p, k in pkey.items()}
        for tokens, prefix in zip(node_tokens, assigned):
            if prefix is None:
                continue
            for pos, (key, value) in enumerate(tokens):
                if key == "ik":
                    new = [("ikp", pkey[prefix])]
                    if value[len(prefix):]:
                        new.append(("ik", value[len(prefix):]))
                    tokens[pos:pos + 1] = new
                    break

        # 2. default node tokens
        defaults = _choose_node_defaults(node_tokens)
        if defaults:
            ndef_line = " ".join(f"{k}={v}" for k, v in defaults)
            for tokens in node_tokens:
                own = dict(tokens)
                for key, value in defaults:
                    if key not in own:
                        tokens.append((key, ""))
                    elif own[key] == value:
                        tokens[:] = [t for t in tokens if t[0] != key]

        # 3. "*" defaults and the shared REF pool for per-node sections
        all_aliases = [alias_map[a["id"]] for a in assets]
        hp_entries = _apply_default(hp_entries, all_aliases)
        dsd_entries = _apply_default(dsd_entries, all_aliases)
        pooled, ref_dict = _build_ref_pool(
            {"HP": hp_entries, "ATTR": attr_entries, "DSD": dsd_entries}
        )
        hp_entries, attr_entries, dsd_entries = pooled["HP"], pooled["ATTR"], pooled["DSD"]

    node_lines = [
        " ".join([head] + [f"{k}={v}" for k, v in tokens])
        for head, tokens in zip(node_heads, node_tokens)
    ]
    N = "N:" + nl + nl.join(node_lines)
    NDEF = "NDEF:" + nl + ndef_line if ndef_line else ""

    # ------------------------------------------------------------------ assemble

    sections = [
        GRAPH,
        START,
        E,
        EP,
        NDEF,
        dict_section("IKP", ikp_dict),
        N,
        dict_section("T", t_dict),
        dict_section("TID", tid_dict),
        dict_section("ID", id_dict),
        dict_section("NAME", name_dict),
        dict_section("BT", bt_dict),
        dict_section("BC", bc_dict),
        dict_section("DC", dc_dict),
        kv_section("HP", hp_entries),
        kv_section("ATTR", attr_entries),
        kv_section("SCS", scs_entries),
        kv_section("CA", ca_entries),
        kv_section("PA", pa_entries),
        kv_section("SA", sa_entries),
        kv_section("DSD", dsd_entries),
        dict_section("REF", ref_dict),
    ]

    return section_break.join(s for s in sections if s)


def lineage_format_to_json(input_text: str) -> Dict[str, Any]:
    """
    Convert lineage format string back to the backend LineageGraph JSON schema.

    Args:
        input_text: String in lineage format

    Returns:
        Dictionary matching the backend LineageGraph schema:
            - assets_in_view: list of LineageAsset dicts
            - edges_in_view: list of FlowEdge dicts
            - graph_calculation_datetime: ISO datetime string (optional)
            - graph_calculation_timestamp: Unix timestamp int (optional)
    """
    normalized = input_text.replace('\r', '').strip()
    lines = normalized.split('\n')

    sections: Dict[str, List[str]] = {}
    current = ""

    for line in lines:
        trimmed = line.strip()
        if not trimmed:
            continue
        # Section header: all-uppercase word followed by colon
        if trimmed.endswith(':') and trimmed[:-1].replace('_', '').isupper():
            current = trimmed[:-1]
            sections[current] = []
            continue
        if not current:
            continue
        sections[current].append(line)

    # ------------------------------------------------------------------ helpers

    def parse_dict(key: str) -> Dict[str, str]:
        """Parse a lookup section into alias->value dict."""
        result: Dict[str, str] = {}
        for raw_line in sections.get(key, []):
            t = raw_line.strip()
            if not t:
                continue
            eq = t.find("=")
            if eq == -1:
                continue
            result[t[:eq]] = t[eq + 1:]
        return result

    def parse_id_name(combined: str) -> Dict[str, Any]:
        """Split 'id|name' → {"id", "name"}. id never contains '|'.
        Forms written when a field was excluded: 'id' (no name) and
        'n=name' (no id); the missing key is then omitted."""
        if combined.startswith("n="):
            return {"name": combined[2:]}
        pipe = combined.find("|")
        if pipe == -1:
            return {"id": combined}
        return {"id": combined[:pipe], "name": combined[pipe + 1:]}

    def pct_decode(s: str) -> str:
        """Reverse percent-encoding applied by the serializer.
        Order matters: %25 → % must be last to avoid double-decoding.
        """
        s = s.replace("%3D", "=")
        s = s.replace("%3A", ":")
        s = s.replace("%7C", "|")
        s = s.replace("%5D", "]")
        s = s.replace("%5B", "[")
        s = s.replace("%2C", ",")
        s = s.replace("%20", " ")
        s = s.replace("%0A", "\n")
        s = s.replace("%0D", "\r")
        s = s.replace("%25", "%")
        return s

    # ------------------------------------------------------------------ lookup tables

    T = parse_dict("T")      # T1 -> technology name
    TID = parse_dict("TID")  # T1 -> technology UUID
    ID = parse_dict("ID")    # N1 -> node UUID
    NAME = parse_dict("NAME")  # N1 -> display name
    BT = parse_dict("BT")    # BT1 -> "uuid|name"
    BC = parse_dict("BC")    # BC1 -> "uuid|name"
    DC = parse_dict("DC")    # DC1 -> "uuid|name"

    # Per-node blob sections
    HP = parse_dict("HP")    # N1 -> "id:name:type|..."
    ATTR = parse_dict("ATTR")  # N1 -> "name:value|..."
    SCS = parse_dict("SCS")  # N1 -> json string
    CA = parse_dict("CA")    # N1 -> json string
    PA = parse_dict("PA")    # N1 -> json string
    SA = parse_dict("SA")    # N1 -> json string
    DSD = parse_dict("DSD")  # N1 -> "id:name"

    # Alias-compression tables (written when the "aliases" option is on).
    # All are optional; legacy documents simply do not contain them.
    #   REF  : R1 -> encoded value shared by ATTR / HP / DSD entries ("@R1")
    #   IKP  : P1 -> encoded identity_key prefix (node token "ikp=P1")
    #   NDEF : default node tokens, inherited by nodes that do not carry them
    REF = parse_dict("REF")
    IKP = parse_dict("IKP")

    ndef_kv: Dict[str, str] = {}
    for raw_line in sections.get("NDEF", []):
        for token in raw_line.strip().split(" "):
            eq = token.find("=")
            if eq > 0:
                ndef_kv[token[:eq]] = token[eq + 1:]

    def deref(value: str, depth: int = 0) -> str:
        """Expand "@Rn" references of a "|"-separated entry value.

        An element "@Rn" is replaced by REF[Rn] (which may itself hold several
        "|"-separated elements and further references). An "@..." element whose
        key is not in REF is a plain literal and is kept unchanged."""
        if depth > 16:
            return value
        out = []
        for el in value.split("|"):
            if el.startswith("@") and el[1:] in REF:
                out.append(deref(REF[el[1:]], depth + 1))
            else:
                out.append(el)
        return "|".join(out)

    # ------------------------------------------------------------------ GRAPH meta

    graph_dt: Optional[str] = None
    graph_ts: Optional[int] = None
    for raw_line in sections.get("GRAPH", []):
        t = raw_line.strip()
        if t.startswith("dt="):
            graph_dt = t[3:]
        elif t.startswith("ts="):
            try:
                graph_ts = int(t[3:])
            except ValueError:
                pass

    # ------------------------------------------------------------------ edges

    def split_edges(pair: str) -> List[Tuple[str, str]]:
        """'N1>N2' -> [('N1', 'N2')]. An end edge, written 'N7' (or 'N7>' by
        older versions), gives [('N7', '')]. Edges grouped by source,
        'N1>N2,N3', give one pair per target, in the written order."""
        src, _, tgt = pair.partition(">")
        src = src.strip()
        targets = [x.strip() for x in tgt.split(",") if x.strip()]
        return [(src, x) for x in targets] if targets else [(src, "")]

    # EP types, queued per (source, target) pair in file order. Edges are matched
    # to them in E order, so several edges between the same pair (e.g. a direct
    # and a summary edge) each keep their own type instead of sharing the last one.
    # Default lines apply to edges without an own entry: '*>* etype=direct' for
    # edges with a target and '* etype=summary' for end edges. An empty
    # 'etype=' is an explicit "no type".
    edge_types: Dict[Tuple[str, str], List[str]] = {}
    default_types: Dict[bool, str] = {}  # has_target -> type
    for raw_line in sections.get("EP", []):
        t = raw_line.strip()
        if not t:
            continue
        # Format: N1>N2 etype=direct (end edge: N7 etype=direct)
        space_idx = t.find(" ")
        pair = t[:space_idx] if space_idx != -1 else t
        rest_ep = t[space_idx + 1:] if space_idx != -1 else ""
        etype: Optional[str] = None
        for kv in rest_ep.split(" "):
            if kv.startswith("etype="):
                etype = kv[6:]
        if etype is None:
            continue
        for key in split_edges(pair):
            if key[0] == "*":
                default_types[bool(key[1])] = etype
            else:
                edge_types.setdefault(key, []).append(etype)

    edges_in_view: List[Dict[str, Any]] = []
    for raw_line in sections.get("E", []):
        t = raw_line.strip()
        if not t:
            continue
        for src_alias, tgt_alias in split_edges(t):
            if not src_alias:
                continue
            edge: Dict[str, Any] = {"source": ID.get(src_alias, src_alias)}
            # An end edge has no target: the key is omitted, as in the original input.
            if tgt_alias:
                edge["target"] = ID.get(tgt_alias, tgt_alias)
            queued = edge_types.get((src_alias, tgt_alias))
            etype_value = queued.pop(0) if queued else default_types.get(bool(tgt_alias), "")
            if etype_value:
                edge["type"] = etype_value
            edges_in_view.append(edge)

    # ------------------------------------------------------------------ nodes

    assets_in_view: List[Dict[str, Any]] = []

    for raw_line in sections.get("N", []):
        t = raw_line.strip()
        if not t:
            continue

        # Format: N1:Column rk=... origin=... path=T1 tags=[...] bt=[...] bc=[...] dc=[...] flags=N ch=count:has_any[:href]
        # The type (after ":") is absent when it was excluded on write.
        space_idx = t.find(" ")
        head_end = space_idx if space_idx != -1 else len(t)
        colon_idx = t.find(":", 0, head_end)
        if colon_idx == -1:
            alias = t[:head_end]
            rest = t[head_end + 1:] if space_idx != -1 else ""
            if not alias:
                continue
            rest = " " + rest  # keep the "first token is the type" layout
        else:
            alias = t[:colon_idx]
            rest = t[colon_idx + 1:]

        # Split on spaces but the first token is node type (no key=value).
        # node_type is percent-decoded because pct_encode is applied on write.
        raw_parts = rest.split(" ")
        node_type = pct_decode(raw_parts[0]) if raw_parts else ""
        kv_parts = raw_parts[1:] if len(raw_parts) > 1 else []

        # Parse key=value tokens from the node line. Tokens from NDEF are
        # inherited; an own token overrides it, and an own empty token
        # (e.g. "origin=") removes the inherited value.
        node_kv: Dict[str, str] = dict(ndef_kv)
        for part in kv_parts:
            eq = part.find("=")
            if eq == -1:
                continue
            key, value = part[:eq], part[eq + 1:]
            if value == "" and key in ndef_kv:
                node_kv.pop(key, None)
            else:
                node_kv[key] = value

        # Resolve scalar fields
        asset_id = ID.get(alias, alias)
        # NAME values are pct_encoded on write; decode back here.
        asset_name = pct_decode(NAME.get(alias, ""))
        resource_key = pct_decode(node_kv["rk"]) if "rk" in node_kv else None
        origin = pct_decode(node_kv["origin"]) if "origin" in node_kv else None
        # ik is optionally split into a shared prefix (ikp=P1 -> IKP) and a suffix.
        identity_key = None
        if "ik" in node_kv or "ikp" in node_kv:
            identity_key = (
                pct_decode(IKP.get(node_kv.get("ikp", ""), ""))
                + pct_decode(node_kv.get("ik", ""))
            )

        # Technology
        technology: Optional[Dict[str, Any]] = None
        tech_alias = node_kv.get("path")
        if tech_alias:
            technology = {}
            if tech_alias in TID:
                technology["id"] = TID[tech_alias]
            if tech_alias in T:
                technology["name"] = T[tech_alias]

        # Tags — each tag was individually pct_encoded on write, so decode each.
        tags: List[str] = []
        if "tags" in node_kv:
            tags = [pct_decode(x) for x in node_kv["tags"].strip("[]").split(",") if x]

        # Business terms
        business_terms: List[Dict[str, Any]] = []
        if "bt" in node_kv:
            for k in node_kv["bt"].strip("[]").split(","):
                k = k.strip()
                if k and k in BT:
                    business_terms.append(parse_id_name(BT[k]))

        # Business classifications
        business_classifications: List[Dict[str, Any]] = []
        if "bc" in node_kv:
            for k in node_kv["bc"].strip("[]").split(","):
                k = k.strip()
                if k and k in BC:
                    business_classifications.append(parse_id_name(BC[k]))

        # Data classes
        data_classes: List[Dict[str, Any]] = []
        if "dc" in node_kv:
            for k in node_kv["dc"].strip("[]").split(","):
                k = k.strip()
                if k and k in DC:
                    data_classes.append(parse_id_name(DC[k]))

        # Flags bitmask → individual booleans
        flags = int(node_kv.get("flags", "0"))
        is_deduced = bool(flags & 1)
        is_transforming = bool(flags & 2)
        is_operational = bool(flags & 4)
        is_temporary = bool(flags & 8)
        is_favorite = bool(flags & 16)

        # Children (format: ch=count,has_any[,href])
        children: Optional[Dict[str, Any]] = None
        if "ch" in node_kv:
            ch_parts = node_kv["ch"].split(",", 2)
            # Missing trailing slots mean the field was excluded on write.
            children = {"count": int(ch_parts[0]) if ch_parts[0] else 0}
            if len(ch_parts) > 1:
                children["has_any"] = ch_parts[1] == "1"
            if len(ch_parts) > 2:
                children["href"] = ch_parts[2]
        elif any(k in node_kv for k in ("chc", "cha", "chh")):
            # Named tokens: written when excluded fields left a gap.
            children = {}
            if "chc" in node_kv:
                children["count"] = int(node_kv["chc"])
            if "cha" in node_kv:
                children["has_any"] = node_kv["cha"] == "1"
            if "chh" in node_kv:
                children["href"] = pct_decode(node_kv["chh"])

        # Hierarchical path
        # Encoding: "id:name:type|...".
        # id is hex/UUID (no ":" or "|"). name and type have ":", "|", "%"
        # percent-encoded as %3A, %7C, %25 so split(":") produces exactly 3
        # tokens: [id, encoded_name, encoded_type].
        hierarchical_path: List[Dict[str, Any]] = []
        # A "*" entry is the default for nodes without an own entry.
        hp_raw = HP.get(alias, HP.get("*"))
        if hp_raw is not None:
            for segment in deref(hp_raw).split("|"):
                if not segment:
                    continue
                seg_parts = segment.split(":")
                hp_item: Dict[str, Any] = {}
                if "=" in seg_parts[0]:
                    # Named form (written when excluded fields left a gap).
                    names = {"i": "id", "n": "name", "t": "type"}
                    for sp in seg_parts:
                        k, _, v = sp.partition("=")
                        if k in names:
                            hp_item[names[k]] = pct_decode(v)
                else:
                    hp_item["id"] = seg_parts[0]
                    if len(seg_parts) > 1:
                        hp_item["name"] = pct_decode(seg_parts[1])
                    if len(seg_parts) > 2:
                        hp_item["type"] = pct_decode(seg_parts[2])
                hierarchical_path.append(hp_item)

        # Attributes
        # Encoding: "name=value|...". name is a system identifier (no "=").
        # value may contain ":" (safe) and "|" (percent-encoded as %7C).
        attributes: List[Dict[str, str]] = []
        if alias in ATTR:
            for attr_seg in deref(ATTR[alias]).split("|"):
                eq = attr_seg.find("=")
                if eq != -1:
                    attributes.append({
                        "name": attr_seg[:eq],
                        "value": pct_decode(attr_seg[eq + 1:]),
                    })
                elif attr_seg:
                    attributes.append({"name": attr_seg})

        # JSON blob sections
        source_code_snippets: List[Any] = json.loads(SCS[alias]) if alias in SCS else []
        catalog_assignments: List[Any] = json.loads(CA[alias]) if alias in CA else []
        project_assignments: List[Any] = json.loads(PA[alias]) if alias in PA else []
        space_assignments: List[Any] = json.loads(SA[alias]) if alias in SA else []

        # Data source definition asset
        data_source_definition_asset: Optional[Dict[str, str]] = None
        dsd_raw = DSD.get(alias, DSD.get("*"))
        if dsd_raw is not None:
            dsd_raw = deref(dsd_raw)
            colon = dsd_raw.find(":")
            if dsd_raw.startswith("n="):
                data_source_definition_asset = {"name": pct_decode(dsd_raw[2:])}
            elif colon != -1:
                data_source_definition_asset = {
                    "id": dsd_raw[:colon],
                    "name": pct_decode(dsd_raw[colon + 1:]),
                }
            elif dsd_raw:
                data_source_definition_asset = {"id": dsd_raw}

        asset: Dict[str, Any] = {
            "id": asset_id,
            "name": asset_name,
            "type": node_type,
            "attributes": attributes,
            "source_code_snippets": source_code_snippets,
            "business_classifications": business_classifications,
            "business_terms": business_terms,
            "catalog_assignments": catalog_assignments,
            "children": children,
            "hierarchical_path": hierarchical_path,
            "data_classes": data_classes,
            "is_deduced": is_deduced,
            "is_transforming": is_transforming,
            "is_operational": is_operational,
            "is_temporary": is_temporary,
            "is_favorite": is_favorite,
            "identity_key": identity_key,
            "origin": origin,
            "project_assignments": project_assignments,
            "resource_key": resource_key,
            "space_assignments": space_assignments,
            "tags": tags,
        }
        if technology is not None:
            asset["technology"] = technology
        if data_source_definition_asset is not None:
            asset["data_source_definition_asset"] = data_source_definition_asset

        assets_in_view.append(asset)

    # ------------------------------------------------------------------ result

    result: Dict[str, Any] = {
        "assets_in_view": assets_in_view,
        "edges_in_view": edges_in_view,
    }
    if graph_dt is not None:
        result["graph_calculation_datetime"] = graph_dt
    if graph_ts is not None:
        result["graph_calculation_timestamp"] = graph_ts
    return result


def convert_json_file_to_lineage(
    input_path: str,
    output_path: str,
    compact: bool = False,
    exclude_fields: Optional[List[str]] = None,
    aliases: bool = True
) -> None:
    """
    Convert a backend LineageGraph JSON file to a lineage format (.ldf) file.

    Args:
        input_path: Path to input JSON file (backend LineageGraph schema)
        output_path: Path to output lineage format file
        compact: Whether to use compact format (no extra whitespace)
        exclude_fields: Fields to remove from the input (see json_to_lineage_format)
        aliases: Whether to use alias compression (see json_to_lineage_format)
    """
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    options: Dict[str, Any] = {"compact": compact, "aliases": aliases}
    if exclude_fields:
        options["exclude_fields"] = exclude_fields
    formatted = json_to_lineage_format(data, options)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(formatted)


def convert_lineage_file_to_json(
    input_path: str,
    output_path: str,
    indent: int = 2
) -> None:
    """
    Convert a lineage format (.ldf) file to a backend LineageGraph JSON file.

    Args:
        input_path: Path to input lineage format file
        output_path: Path to output JSON file (backend LineageGraph schema)
        indent: JSON indentation level (default: 2)
    """
    with open(input_path, "r", encoding="utf-8") as f:
        input_text = f.read()
    json_data = lineage_format_to_json(input_text)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=indent)

# Made with Bob
