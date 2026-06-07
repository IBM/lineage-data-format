"""
Converter module for lineage data format.
Provides functions to convert between JSON and lineage format.
"""

import json
from typing import Dict, List, Any, Optional


def json_to_lineage_format(graph: Dict[str, Any], options: Optional[Dict[str, bool]] = None) -> str:
    """
    Convert a LineageGraph dict to lineage format string.
    
    Args:
        graph: Dictionary containing graph data with keys:
            - graph: Graph ID
            - start: Starting node alias
            - edges: List of edge pairs
            - nodes: Dictionary of node definitions
            - dictionaries: Lookup dictionaries (T, D, TID, DID, TP, ID, BT, NAME)
        options: Optional dict with 'compact' boolean flag
    
    Returns:
        String in lineage format
    """
    compact = options.get("compact", False) if options else False
    nl = "" if compact else "\n"
    section_break = "" if compact else "\n\n"

    def encode_array(arr: Optional[List[Any]]) -> str:
        if arr and len(arr) > 0:
            return f"[{','.join(str(x) for x in arr)}]"
        return "[]"

    def dict_section(name: str, dict_data: Optional[Dict[str, str]]) -> str:
        if not dict_data or len(dict_data) == 0:
            return ""
        entries = [f"{k}={v}" for k, v in dict_data.items()]
        return name + ":" + nl + nl.join(entries)

    GRAPH = f"GRAPH:{nl}{graph['graph']}"
    START = f"START:{nl}{graph['start']}"
    E = "E:" + nl + nl.join(">".join(e) for e in graph['edges'])

    node_lines = []
    for node_id, node in graph['nodes'].items():
        attrs = node.get('attributes', {})
        parts = []
        parts.append(f"{node_id}:{node['type']}")
        if node.get('path'):
            parts.append(f"path={node['path']}")
        if attrs.get('dq') is not None:
            parts.append(f"dq={attrs['dq']}")
        if attrs.get('sla') is not None:
            parts.append(f"sla={attrs['sla']}")
        if attrs.get('tags'):
            parts.append(f"tags={encode_array(attrs['tags'])}")
        if attrs.get('bt'):
            parts.append(f"bt={encode_array(attrs['bt'])}")
        node_lines.append(" ".join(parts))

    N = "N:" + nl + nl.join(node_lines)

    dictionaries = graph.get('dictionaries', {})
    sections = [
        GRAPH,
        START,
        E,
        N,
        dict_section("T", dictionaries.get('T')),
        dict_section("D", dictionaries.get('D')),
        dict_section("TP", dictionaries.get('TP')),
        dict_section("ID", dictionaries.get('ID')),
        dict_section("BT", dictionaries.get('BT')),
        dict_section("NAME", dictionaries.get('NAME')),
        dict_section("TID", dictionaries.get('TID')),
        dict_section("DID", dictionaries.get('DID')),
    ]

    return section_break.join(s for s in sections if s)


def lineage_format_to_json(input_text: str) -> Dict[str, Any]:
    """
    Convert lineage format string back to JSON.
    
    Args:
        input_text: String in lineage format
    
    Returns:
        Dictionary with graph data containing:
            - graphId: Graph identifier
            - startingNodeIds: List of starting node IDs
            - nodes: List of node objects
            - edges: List of edge objects with sourceId and targetId
    """
    normalized = input_text.replace('\r', '').strip()
    lines = normalized.split('\n')

    sections: Dict[str, List[str]] = {}
    current = ""

    for line in lines:
        trimmed = line.strip()

        if not trimmed:
            continue

        # Check if this is a section header
        if trimmed.endswith(':') and trimmed[:-1].isupper():
            current = trimmed[:-1]
            sections[current] = []
            continue

        if not current:
            continue
        sections[current].append(line)

    graph_id = sections.get("GRAPH", [""])[0].strip() if "GRAPH" in sections else ""

    # --- Lookup tables ---

    def parse_dict(key: str) -> Dict[str, str]:
        raw = sections.get(key)
        if not raw:
            return {}

        result: Dict[str, str] = {}
        for line in raw:
            trimmed = line.strip()
            if not trimmed:
                continue
            eq = trimmed.find("=")
            if eq == -1:
                continue
            k = trimmed[:eq]
            v = trimmed[eq + 1:]
            result[k] = v
        return result

    T = parse_dict("T")      # technology name lookup  e.g. T1 -> "DB2"
    D = parse_dict("D")      # database name lookup    e.g. D1 -> "Database2"
    TID = parse_dict("TID")  # technology id lookup    e.g. T1 -> UUID
    DID = parse_dict("DID")  # database id lookup      e.g. D1 -> UUID
    ID = parse_dict("ID")    # node UUID lookup        e.g. N1 -> UUID
    NAME = parse_dict("NAME")  # node display name     e.g. N1 -> "Node 1"
    BT = parse_dict("BT")    # business term           e.g. BT1 -> UUID|value

    # --- Starting nodes (resolve aliases to UUIDs) ---

    starting_node_ids = [
        ID.get(alias, alias)
        for line in sections.get("START", [])
        for alias in [line.strip()]
        if alias
    ]

    # --- Edges (resolve aliases to UUIDs, return { sourceId, targetId }) ---

    edges: List[Dict[str, str]] = []

    for line in sections.get("E", []):
        trimmed = line.strip()
        if not trimmed:
            continue
        parts = trimmed.split(">")
        if len(parts) < 2:
            continue
        src = parts[0].strip()
        tgt = parts[1].strip()
        if not src or not tgt:
            continue
        edges.append({
            "sourceId": ID.get(src, src),
            "targetId": ID.get(tgt, tgt),
        })

    # --- Nodes ---

    nodes: List[Dict[str, Any]] = []

    for line in sections.get("N", []):
        trimmed = line.strip()
        if not trimmed:
            continue

        # Format: N1:schema path=T1/D1 dq=90 sla=0 tags=[...] bt=[...]
        colon_idx = trimmed.find(":")
        if colon_idx == -1:
            continue

        alias = trimmed[:colon_idx]
        rest = trimmed[colon_idx + 1:]

        parts = rest.split(" ")
        node_type = parts[0] if parts else ""
        attr_parts = parts[1:] if len(parts) > 1 else []

        attributes: Dict[str, Any] = {}
        path_str = ""

        for part in attr_parts:
            eq_idx = part.find("=")
            if eq_idx == -1:
                continue
            key = part[:eq_idx]
            value = part[eq_idx + 1:]

            if key == "path":
                path_str = value
            elif key == "dq":
                attributes["dqScore"] = float(value) if '.' in value else int(value)
            elif key == "sla":
                attributes["slaFails"] = float(value) if '.' in value else int(value)
            elif key == "tags":
                tags_str = value.strip("[]")
                attributes["tags"] = [t for t in tags_str.split(",") if t]
            elif key == "bt":
                bt_keys_str = value.strip("[]")
                bt_keys = [k for k in bt_keys_str.split(",") if k]

                bt_data = []
                for k in bt_keys:
                    combined = BT.get(k)
                    if not combined:
                        continue
                    pipe_idx = combined.find("|")
                    if pipe_idx == -1:
                        continue
                    bt_data.append({
                        "id": combined[:pipe_idx],
                        "value": combined[pipe_idx + 1:],
                    })

                attributes["businessTerms"] = {
                    "data": bt_data,
                    "count": len(bt_keys),
                }

        # Reconstruct path with IDs if available
        reconstructed_path: List[Dict[str, Any]] = []

        if path_str:
            path_parts = path_str.split("/")
            if len(path_parts) >= 2:
                tech_key = path_parts[0]
                db_key = path_parts[1]
                reconstructed_path = [
                    {
                        "id": TID.get(tech_key),
                        "name": T.get(tech_key, tech_key),
                        "type": "technology",
                    },
                    {
                        "id": DID.get(db_key),
                        "name": D.get(db_key, db_key),
                        "type": "database",
                    },
                ]

        node = {
            "id": ID.get(alias, alias),
            "type": node_type,
            "name": NAME.get(alias, ""),
            "path": reconstructed_path,
        }
        node.update(attributes)
        nodes.append(node)

    return {
        "graphId": graph_id,
        "startingNodeIds": starting_node_ids,
        "nodes": nodes,
        "edges": edges,
    }


def convert_json_file_to_lineage(
    input_path: str,
    output_path: str,
    compact: bool = False
) -> None:
    """
    Convert a JSON file to lineage format file.
    
    Args:
        input_path: Path to input JSON file
        output_path: Path to output lineage format file
        compact: Whether to use compact format (no extra whitespace)
    """
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Build the lineage graph structure from JSON
    parsed = data
    
    tech_dict: Dict[str, str] = {}
    db_dict: Dict[str, str] = {}
    tp_dict: Dict[str, str] = {}
    id_dict: Dict[str, str] = {}
    bt_dict: Dict[str, str] = {}
    
    tech_index = 1
    db_index = 1
    bt_index = 1
    
    # Create node key mapping
    node_key_map: Dict[str, str] = {}
    for i, node in enumerate(parsed['nodes']):
        node_key_map[node['id']] = f"N{i + 1}"
    
    nodes_record: Dict[str, Any] = {}
    name_dict: Dict[str, str] = {}
    tid_dict: Dict[str, str] = {}
    did_dict: Dict[str, str] = {}
    
    # Process nodes
    for node in parsed['nodes']:
        tech = node['path'][0]
        db = node['path'][1]
        
        # Find or create tech key
        tech_key = None
        for k, v in tech_dict.items():
            if v == tech['name']:
                tech_key = k
                break
        
        if not tech_key:
            tech_key = f"T{tech_index}"
            tech_index += 1
            tech_dict[tech_key] = tech['name']
            if tech.get('id'):
                tid_dict[tech_key] = tech['id']
        
        # Find or create db key
        db_key = None
        for k, v in db_dict.items():
            if v == db['name']:
                db_key = k
                break
        
        if not db_key:
            db_key = f"D{db_index}"
            db_index += 1
            db_dict[db_key] = db['name']
            if db.get('id'):
                did_dict[db_key] = db['id']
        
        # Add type to type dict
        if node['type'] not in tp_dict:
            tp_dict[node['type']] = node['type']
        
        # Add node ID
        id_dict[node_key_map[node['id']]] = node['id']
        
        # Process business terms
        bt_keys: List[str] = []
        business_terms = node.get('businessTerms', {}).get('data', [])
        for term in business_terms:
            combined = f"{term['id']}|{term['value']}"
            existing_key = None
            for k, v in bt_dict.items():
                if v == combined:
                    existing_key = k
                    break
            
            if not existing_key:
                existing_key = f"BT{bt_index}"
                bt_index += 1
                bt_dict[existing_key] = combined
            
            bt_keys.append(existing_key)
        
        # Add node name
        name_dict[node_key_map[node['id']]] = node['name']
        
        # Build node record
        nodes_record[node_key_map[node['id']]] = {
            'type': node['type'],
            'path': f"{tech_key}/{db_key}",
            'attributes': {
                'dq': node.get('dqScore'),
                'sla': node.get('slaFails'),
                'tags': node.get('tags'),
                'bt': bt_keys,
            }
        }
    
    # Process edges
    edges = [
        [node_key_map[e['sourceId']], node_key_map[e['targetId']]]
        for e in parsed['edges']
    ]
    
    # Build lineage graph
    lineage_graph = {
        'graph': parsed['graphId'],
        'start': node_key_map[parsed['startingNodeIds'][0]],
        'edges': edges,
        'nodes': nodes_record,
        'dictionaries': {
            'T': tech_dict,
            'D': db_dict,
            'TID': tid_dict,
            'DID': did_dict,
            'TP': tp_dict,
            'ID': id_dict,
            'BT': bt_dict,
            'NAME': name_dict,
        }
    }
    
    # Convert and write
    formatted = json_to_lineage_format(lineage_graph, {'compact': compact})
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(formatted)


def convert_lineage_file_to_json(
    input_path: str,
    output_path: str,
    indent: int = 2
) -> None:
    """
    Convert a lineage format file to JSON file.
    
    Args:
        input_path: Path to input lineage format file
        output_path: Path to output JSON file
        indent: JSON indentation level (default: 2)
    """
    with open(input_path, "r", encoding="utf-8") as f:
        input_text = f.read()
    
    json_data = lineage_format_to_json(input_text)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=indent)

# Made with Bob
