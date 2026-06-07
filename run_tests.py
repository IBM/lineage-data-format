#!/usr/bin/env python3
"""
Simple test runner that doesn't require pytest.
Runs all tests from tests/test_converter.py
"""

import sys
import os
import json
import tempfile

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from ldf import (  # type: ignore
    json_to_lineage_format,
    lineage_format_to_json,
    convert_json_file_to_lineage,
    convert_lineage_file_to_json,
)


def test_simple_graph_to_lineage():
    """Test converting a simple graph to lineage format."""
    print("Testing: simple_graph_to_lineage...", end=" ")
    
    graph = {
        'graph': 'test-graph-id',
        'start': 'N1',
        'edges': [['N1', 'N2']],
        'nodes': {
            'N1': {
                'type': 'table',
                'path': 'T1/D1',
                'attributes': {'dq': 95}
            },
            'N2': {
                'type': 'view',
                'path': 'T1/D1',
                'attributes': {'sla': 0}
            }
        },
        'dictionaries': {
            'T': {'T1': 'PostgreSQL'},
            'D': {'D1': 'production'},
            'TID': {'T1': 'tech-uuid'},
            'DID': {'D1': 'db-uuid'},
            'TP': {'table': 'table', 'view': 'view'},
            'ID': {'N1': 'node-1', 'N2': 'node-2'},
            'NAME': {'N1': 'users', 'N2': 'active_users'},
            'BT': {}
        }
    }
    
    result = json_to_lineage_format(graph)
    
    assert 'GRAPH:' in result
    assert 'test-graph-id' in result
    assert 'START:' in result
    assert 'N1' in result
    assert 'E:' in result
    assert 'N1>N2' in result
    assert 'N:' in result
    assert 'T:' in result
    assert 'PostgreSQL' in result
    
    print("✓ PASSED")


def test_lineage_to_json():
    """Test converting lineage format back to JSON."""
    print("Testing: lineage_to_json...", end=" ")
    
    ldf_text = """GRAPH:
test-graph-id

START:
N1

E:
N1>N2

N:
N1:table path=T1/D1 dq=95
N2:view path=T1/D1 sla=0

T:
T1=PostgreSQL

D:
D1=production

TID:
T1=tech-uuid

DID:
D1=db-uuid

ID:
N1=node-1
N2=node-2

NAME:
N1=users
N2=active_users
"""
    
    result = lineage_format_to_json(ldf_text)
    
    assert result['graphId'] == 'test-graph-id'
    assert result['startingNodeIds'] == ['node-1']
    assert len(result['nodes']) == 2
    assert len(result['edges']) == 1
    assert result['edges'][0]['sourceId'] == 'node-1'
    assert result['edges'][0]['targetId'] == 'node-2'
    
    print("✓ PASSED")


def test_round_trip_conversion():
    """Test that conversion is lossless (round-trip)."""
    print("Testing: round_trip_conversion...", end=" ")
    
    original_graph = {
        'graph': 'round-trip-test',
        'start': 'N1',
        'edges': [['N1', 'N2'], ['N2', 'N3']],
        'nodes': {
            'N1': {
                'type': 'table',
                'path': 'T1/D1',
                'attributes': {
                    'dq': 95,
                    'sla': 0,
                    'tags': ['pii', 'critical']
                }
            },
            'N2': {
                'type': 'view',
                'path': 'T1/D1',
                'attributes': {'dq': 90}
            },
            'N3': {
                'type': 'table',
                'path': 'T2/D2',
                'attributes': {'sla': 1}
            }
        },
        'dictionaries': {
            'T': {'T1': 'PostgreSQL', 'T2': 'MySQL'},
            'D': {'D1': 'prod', 'D2': 'analytics'},
            'TID': {'T1': 'tech-1', 'T2': 'tech-2'},
            'DID': {'D1': 'db-1', 'D2': 'db-2'},
            'TP': {'table': 'table', 'view': 'view'},
            'ID': {'N1': 'uuid-1', 'N2': 'uuid-2', 'N3': 'uuid-3'},
            'NAME': {'N1': 'users', 'N2': 'active', 'N3': 'analytics'},
            'BT': {}
        }
    }
    
    # Convert to lineage format
    ldf_text = json_to_lineage_format(original_graph)
    
    # Convert back to JSON
    restored = lineage_format_to_json(ldf_text)
    
    # Verify key properties
    assert restored['graphId'] == original_graph['graph']
    assert len(restored['nodes']) == len(original_graph['nodes'])
    assert len(restored['edges']) == len(original_graph['edges'])
    
    # Verify node data
    node_ids = {n['id'] for n in restored['nodes']}
    assert 'uuid-1' in node_ids
    assert 'uuid-2' in node_ids
    assert 'uuid-3' in node_ids
    
    print("✓ PASSED")


def test_json_file_to_lineage_file():
    """Test converting JSON file to lineage format file."""
    print("Testing: json_file_to_lineage_file...", end=" ")
    
    test_data = {
        'graphId': 'file-test',
        'startingNodeIds': ['node-1'],
        'nodes': [
            {
                'id': 'node-1',
                'type': 'table',
                'name': 'test_table',
                'path': [
                    {'id': 'tech-1', 'name': 'DB2', 'type': 'technology'},
                    {'id': 'db-1', 'name': 'testdb', 'type': 'database'}
                ],
                'dqScore': 95,
                'slaFails': 0,
                'tags': ['test']
            }
        ],
        'edges': []
    }
    
    with tempfile.TemporaryDirectory() as tmpdir:
        input_file = os.path.join(tmpdir, 'input.json')
        output_file = os.path.join(tmpdir, 'output.ldf')
        
        # Write test data
        with open(input_file, 'w') as f:
            json.dump(test_data, f)
        
        # Convert
        convert_json_file_to_lineage(input_file, output_file)
        
        # Verify output exists and contains expected content
        assert os.path.exists(output_file)
        with open(output_file, 'r') as f:
            content = f.read()
            assert 'GRAPH:' in content
            assert 'file-test' in content
            assert 'N1:table' in content
    
    print("✓ PASSED")


def test_business_terms():
    """Test handling of business terms."""
    print("Testing: business_terms...", end=" ")
    
    graph = {
        'graph': 'bt-test',
        'start': 'N1',
        'edges': [],
        'nodes': {
            'N1': {
                'type': 'table',
                'path': 'T1/D1',
                'attributes': {
                    'bt': ['BT1', 'BT2']
                }
            }
        },
        'dictionaries': {
            'T': {'T1': 'DB'},
            'D': {'D1': 'db'},
            'TID': {},
            'DID': {},
            'TP': {'table': 'table'},
            'ID': {'N1': 'n1'},
            'NAME': {'N1': 'name1'},
            'BT': {
                'BT1': 'bt-uuid-1|Term One',
                'BT2': 'bt-uuid-2|Term Two'
            }
        }
    }
    
    ldf = json_to_lineage_format(graph)
    restored = lineage_format_to_json(ldf)
    
    assert 'businessTerms' in restored['nodes'][0]
    assert len(restored['nodes'][0]['businessTerms']['data']) == 2
    assert restored['nodes'][0]['businessTerms']['data'][0]['id'] == 'bt-uuid-1'
    assert restored['nodes'][0]['businessTerms']['data'][0]['value'] == 'Term One'
    
    print("✓ PASSED")


def test_50_nodes_conversion():
    """Test conversion with 50 nodes mock data."""
    print("Testing: 50_nodes_conversion...", end=" ")
    
    input_file = 'examples/mock_50_nodes_linear_edges.json'
    
    if not os.path.exists(input_file):
        print("⊘ SKIPPED (file not found)")
        return
    
    with open(input_file, 'r') as f:
        original = json.load(f)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        ldf_file = os.path.join(tmpdir, 'test.ldf')
        json_file = os.path.join(tmpdir, 'restored.json')
        
        # Convert to LDF
        convert_json_file_to_lineage(input_file, ldf_file)
        
        # Convert back to JSON
        convert_lineage_file_to_json(ldf_file, json_file)
        
        with open(json_file, 'r') as f:
            restored = json.load(f)
        
        # Verify
        assert len(restored['nodes']) == len(original['nodes'])
        assert len(restored['edges']) == len(original['edges'])
        assert restored['graphId'] == original['graphId']
    
    print("✓ PASSED")


def test_100_nodes_conversion():
    """Test conversion with 100 nodes mock data."""
    print("Testing: 100_nodes_conversion...", end=" ")
    
    input_file = 'examples/mock_100_nodes_combined_edges.json'
    
    if not os.path.exists(input_file):
        print("⊘ SKIPPED (file not found)")
        return
    
    with open(input_file, 'r') as f:
        original = json.load(f)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        ldf_file = os.path.join(tmpdir, 'test.ldf')
        json_file = os.path.join(tmpdir, 'restored.json')
        
        # Convert to LDF
        convert_json_file_to_lineage(input_file, ldf_file)
        
        # Convert back to JSON
        convert_lineage_file_to_json(ldf_file, json_file)
        
        with open(json_file, 'r') as f:
            restored = json.load(f)
        
        # Verify
        assert len(restored['nodes']) == len(original['nodes'])
        assert len(restored['edges']) == len(original['edges'])
        assert restored['graphId'] == original['graphId']
    
    print("✓ PASSED")


def main():
    """Run all tests."""
    print("=" * 70)
    print("Running LDF Converter Tests")
    print("=" * 70)
    print()
    
    tests = [
        test_simple_graph_to_lineage,
        test_lineage_to_json,
        test_round_trip_conversion,
        test_json_file_to_lineage_file,
        test_business_terms,
        test_50_nodes_conversion,
        test_100_nodes_conversion,
    ]
    
    passed = 0
    failed = 0
    skipped = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ ERROR: {e}")
            failed += 1
    
    print()
    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)
    
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())

# Made with Bob
