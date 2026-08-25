"""
Converter module for lineage data format.
Provides functions to convert between JSON and lineage format.
"""

import json
from typing import Dict, List, Any, Optional, Tuple


def json_to_lineage_format(graph: Dict[str, Any], options: Optional[Dict[str, bool]] = None) -> str:
    """
    Convert a backend LineageGraph dict to lineage format string.

    Args:
        graph: Dictionary in backend LineageGraph format with keys:
            - assets_in_view: List of asset dicts (LineageAsset)
            - edges_in_view: List of edge dicts (FlowEdge)
            - graph_calculation_datetime: ISO datetime string (optional)
            - graph_calculation_timestamp: Unix timestamp (optional)
        options: Optional dict with 'compact' boolean flag

    Returns:
        String in lineage format
    """
    compact = options.get("compact", False) if options else False
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
        name = tech.get("name", "")
        # Prefer deduplication by id; fall back to name when id is absent
        dedup_key = tech_id if tech_id else name
        dedup_store = _tech_id_to_key if tech_id else _tech_name_to_key
        if dedup_key not in dedup_store:
            key = f"T{_tech_idx}"
            _tech_idx += 1
            dedup_store[dedup_key] = key
            t_dict[key] = name
            if tech_id:
                tid_dict[key] = tech_id
        return dedup_store[dedup_key]

    # BT / BC / DC lookups (deduplicate by id|name)
    bt_dict: Dict[str, str] = {}
    bc_dict: Dict[str, str] = {}
    dc_dict: Dict[str, str] = {}
    _bt_idx = _bc_idx = _dc_idx = 1

    def get_lookup_key(
        store: Dict[str, str],
        idx_ref: List[int],
        prefix: str,
        item_id: str,
        item_name: str,
    ) -> str:
        combined = f"{item_id}|{item_name}"
        for k, v in store.items():
            if v == combined:
                return k
        key = f"{prefix}{idx_ref[0]}"
        idx_ref[0] += 1
        store[key] = combined
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

    node_lines: List[str] = []

    for asset in assets:
        asset_id = asset["id"]
        alias = alias_map[asset_id]

        id_dict[alias] = asset_id
        # pct_encode preserves \n and other structural chars in the name value
        # so the line-based NAME: section parser doesn't split mid-value.
        name_dict[alias] = pct_encode(asset.get("name", ""))

        # --- technology path alias
        tech = asset.get("technology")
        tech_alias = get_tech_key(tech) if tech else ""

        # --- BT aliases
        bt_aliases: List[str] = []
        for term in asset.get("business_terms") or []:
            k = get_lookup_key(bt_dict, bt_idx_ref, "BT", term["id"], term.get("name", ""))
            bt_aliases.append(k)

        # --- BC aliases
        bc_aliases: List[str] = []
        for cls in asset.get("business_classifications") or []:
            k = get_lookup_key(bc_dict, bc_idx_ref, "BC", cls["id"], cls.get("name", ""))
            bc_aliases.append(k)

        # --- DC aliases
        dc_aliases: List[str] = []
        for dc in asset.get("data_classes") or []:
            k = get_lookup_key(dc_dict, dc_idx_ref, "DC", dc["id"], dc.get("name", ""))
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
        node_type = pct_encode(asset.get("type", ""))
        parts: List[str] = [f"{alias}:{node_type}"]
        if asset.get("resource_key"):
            parts.append(f"rk={pct_encode(asset['resource_key'])}")
        if asset.get("origin"):
            parts.append(f"origin={pct_encode(asset['origin'])}")
        if asset.get("identity_key"):
            parts.append(f"ik={pct_encode(asset['identity_key'])}")
        if tech_alias:
            parts.append(f"path={tech_alias}")
        tags = asset.get("tags") or []
        if tags:
            parts.append(f"tags={encode_array([pct_encode(tag) for tag in tags])}")
        if bt_aliases:
            parts.append(f"bt={encode_array(bt_aliases)}")
        if bc_aliases:
            parts.append(f"bc={encode_array(bc_aliases)}")
        if dc_aliases:
            parts.append(f"dc={encode_array(dc_aliases)}")
        if flags:
            parts.append(f"flags={flags}")
        if children is not None:
            count = children.get("count", 0)
            has_any = 1 if children.get("has_any") else 0
            href = children.get("href", "")
            # Use comma as separator: ch=count,has_any,href
            # (href may contain colons from URLs, comma never appears in count/has_any/href)
            ch_str = f"ch={count},{has_any},{href}" if href else f"ch={count},{has_any}"
            parts.append(ch_str)

        node_lines.append(" ".join(parts))

        # --- HP section
        # Format: "id:name:type|id:name:type".
        # id is always hex/UUID → never contains ":" or "|".
        # name and type CAN contain ":" and "|", so both are percent-encoded
        # ("%3A" for ":", "%7C" for "|", "%25" for "%").
        # This makes the three-field split unambiguous on parse.
        hp_items = asset.get("hierarchical_path") or []
        if hp_items:
            def _encode_hp_field(s: str) -> str:
                # Full structural encoding via pct_encode, then also encode ":"
                # which pct_encode leaves alone (it's only structural in HP segments).
                s = pct_encode(s)
                s = s.replace(":", "%3A")
                return s
            def _encode_hp_segment(h: Dict[str, Any]) -> str:
                return (f"{h['id']}:{_encode_hp_field(h.get('name',''))}"
                        f":{_encode_hp_field(h.get('type',''))}")
            hp_entries[alias] = "|".join(_encode_hp_segment(h) for h in hp_items)

        # --- ATTR section
        # Format: "name=value|name=value". The separator between attr entries
        # is "|". Within each entry "=" separates name from value.
        # "name" is always a system identifier (no "=" in it).
        # "value" may contain ":" so we cannot use ":" as separator here.
        # "value" may contain "|" so we percent-encode "|" and "%" in values.
        attr_items = asset.get("attributes") or []
        if attr_items:
            attr_entries[alias] = "|".join(
                f"{a['name']}={pct_encode(a['value'])}" for a in attr_items
            )

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
            dsd_entries[alias] = f"{dsd['id']}:{pct_encode(dsd.get('name', ''))}"

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

    for edge in edges_raw:
        src_alias = alias_map.get(edge.get("source", ""), edge.get("source", ""))
        tgt_alias = alias_map.get(edge.get("target", ""), edge.get("target", ""))
        edge_lines.append(f"{src_alias}>{tgt_alias}")
        if edge.get("type"):
            ep_lines.append(f"{src_alias}>{tgt_alias} etype={edge['type']}")

    E = "E:" + nl + nl.join(edge_lines) if edge_lines else ""
    EP = "EP:" + nl + nl.join(ep_lines) if ep_lines else ""

    # ------------------------------------------------------------------ N section

    N = "N:" + nl + nl.join(node_lines)

    # ------------------------------------------------------------------ assemble

    sections = [
        GRAPH,
        START,
        E,
        EP,
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

    def parse_id_name(combined: str) -> Tuple[str, str]:
        """Split 'id|name' → (id, name). id never contains '|'."""
        pipe = combined.find("|")
        if pipe == -1:
            return combined, ""
        return combined[:pipe], combined[pipe + 1:]

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

    # Build edge map keyed by "src_alias>tgt_alias" for EP merge
    edge_type_map: Dict[str, str] = {}
    for raw_line in sections.get("EP", []):
        t = raw_line.strip()
        if not t:
            continue
        # Format: N1>N2 etype=direct
        space_idx = t.find(" ")
        pair = t[:space_idx] if space_idx != -1 else t
        rest_ep = t[space_idx + 1:] if space_idx != -1 else ""
        etype = ""
        for kv in rest_ep.split(" "):
            if kv.startswith("etype="):
                etype = kv[6:]
        if etype:
            edge_type_map[pair] = etype

    edges_in_view: List[Dict[str, Any]] = []
    for raw_line in sections.get("E", []):
        t = raw_line.strip()
        if not t:
            continue
        arrow = t.find(">")
        if arrow == -1:
            continue
        src_alias = t[:arrow].strip()
        tgt_alias = t[arrow + 1:].strip()
        if not src_alias or not tgt_alias:
            continue
        src_id = ID.get(src_alias, src_alias)
        tgt_id = ID.get(tgt_alias, tgt_alias)
        edge: Dict[str, Any] = {"source": src_id, "target": tgt_id}
        pair_key = f"{src_alias}>{tgt_alias}"
        if pair_key in edge_type_map:
            edge["type"] = edge_type_map[pair_key]
        edges_in_view.append(edge)

    # ------------------------------------------------------------------ nodes

    assets_in_view: List[Dict[str, Any]] = []

    for raw_line in sections.get("N", []):
        t = raw_line.strip()
        if not t:
            continue

        # Format: N1:Column rk=... origin=... path=T1 tags=[...] bt=[...] bc=[...] dc=[...] flags=N ch=count:has_any[:href]
        colon_idx = t.find(":")
        if colon_idx == -1:
            continue

        alias = t[:colon_idx]
        rest = t[colon_idx + 1:]

        # Split on spaces but the first token is node type (no key=value).
        # node_type is percent-decoded because pct_encode is applied on write.
        raw_parts = rest.split(" ")
        node_type = pct_decode(raw_parts[0]) if raw_parts else ""
        kv_parts = raw_parts[1:] if len(raw_parts) > 1 else []

        # Parse key=value tokens from the node line
        node_kv: Dict[str, str] = {}
        for part in kv_parts:
            eq = part.find("=")
            if eq == -1:
                continue
            node_kv[part[:eq]] = part[eq + 1:]

        # Resolve scalar fields
        asset_id = ID.get(alias, alias)
        # NAME values are pct_encoded on write; decode back here.
        asset_name = pct_decode(NAME.get(alias, ""))
        resource_key = pct_decode(node_kv["rk"]) if "rk" in node_kv else None
        origin = pct_decode(node_kv["origin"]) if "origin" in node_kv else None
        identity_key = pct_decode(node_kv["ik"]) if "ik" in node_kv else None

        # Technology
        technology: Optional[Dict[str, Any]] = None
        tech_alias = node_kv.get("path")
        if tech_alias:
            technology = {
                "id": TID.get(tech_alias, tech_alias),
                "name": T.get(tech_alias, tech_alias),
            }

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
                    bt_id, bt_name = parse_id_name(BT[k])
                    business_terms.append({"id": bt_id, "name": bt_name})

        # Business classifications
        business_classifications: List[Dict[str, Any]] = []
        if "bc" in node_kv:
            for k in node_kv["bc"].strip("[]").split(","):
                k = k.strip()
                if k and k in BC:
                    bc_id, bc_name = parse_id_name(BC[k])
                    business_classifications.append({"id": bc_id, "name": bc_name})

        # Data classes
        data_classes: List[Dict[str, Any]] = []
        if "dc" in node_kv:
            for k in node_kv["dc"].strip("[]").split(","):
                k = k.strip()
                if k and k in DC:
                    dc_id, dc_name = parse_id_name(DC[k])
                    data_classes.append({"id": dc_id, "name": dc_name})

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
            ch_count = int(ch_parts[0]) if ch_parts else 0
            ch_has_any = ch_parts[1] == "1" if len(ch_parts) > 1 else False
            ch_href = ch_parts[2] if len(ch_parts) > 2 else ""
            children = {"count": ch_count, "has_any": ch_has_any, "href": ch_href}

        # Hierarchical path
        # Encoding: "id:name:type|...".
        # id is hex/UUID (no ":" or "|"). name and type have ":", "|", "%"
        # percent-encoded as %3A, %7C, %25 so split(":") produces exactly 3
        # tokens: [id, encoded_name, encoded_type].
        hierarchical_path: List[Dict[str, Any]] = []
        if alias in HP:
            for segment in HP[alias].split("|"):
                if not segment:
                    continue
                seg_parts = segment.split(":")
                if len(seg_parts) < 3:
                    continue
                hierarchical_path.append({
                    "id": seg_parts[0],
                    "name": pct_decode(seg_parts[1]),
                    "type": pct_decode(seg_parts[2]),
                })

        # Attributes
        # Encoding: "name=value|...". name is a system identifier (no "=").
        # value may contain ":" (safe) and "|" (percent-encoded as %7C).
        attributes: List[Dict[str, str]] = []
        if alias in ATTR:
            for attr_seg in ATTR[alias].split("|"):
                eq = attr_seg.find("=")
                if eq != -1:
                    attributes.append({
                        "name": attr_seg[:eq],
                        "value": pct_decode(attr_seg[eq + 1:]),
                    })

        # JSON blob sections
        source_code_snippets: List[Any] = json.loads(SCS[alias]) if alias in SCS else []
        catalog_assignments: List[Any] = json.loads(CA[alias]) if alias in CA else []
        project_assignments: List[Any] = json.loads(PA[alias]) if alias in PA else []
        space_assignments: List[Any] = json.loads(SA[alias]) if alias in SA else []

        # Data source definition asset
        data_source_definition_asset: Optional[Dict[str, str]] = None
        if alias in DSD:
            colon = DSD[alias].find(":")
            if colon != -1:
                data_source_definition_asset = {
                    "id": DSD[alias][:colon],
                    "name": pct_decode(DSD[alias][colon + 1:]),
                }

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
    compact: bool = False
) -> None:
    """
    Convert a backend LineageGraph JSON file to a lineage format (.ldf) file.

    Args:
        input_path: Path to input JSON file (backend LineageGraph schema)
        output_path: Path to output lineage format file
        compact: Whether to use compact format (no extra whitespace)
    """
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    formatted = json_to_lineage_format(data, {"compact": compact})
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
