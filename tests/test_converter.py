"""
Tests for the LDF converter module.
"""

import json
import os
import tempfile
import pytest  # type: ignore
from ldf import (  # type: ignore
    json_to_lineage_format,
    lineage_format_to_json,
    convert_json_file_to_lineage,
    convert_lineage_file_to_json,
)


class TestBasicConversion:
    """Test basic conversion functionality."""
    
    def test_simple_graph_to_lineage(self):
        """Test converting a simple graph to lineage format."""
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
    
    def test_lineage_to_json(self):
        """Test converting lineage format back to JSON."""
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
    
    def test_round_trip_conversion(self):
        """Test that conversion is lossless (round-trip)."""
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


class TestFileConversion:
    """Test file-based conversion functions."""
    
    def test_json_file_to_lineage_file(self):
        """Test converting JSON file to lineage format file."""
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
    
    def test_lineage_file_to_json_file(self):
        """Test converting lineage format file to JSON file."""
        ldf_content = """GRAPH:
file-test

START:
N1

E:

N:
N1:table path=T1/D1 dq=95

T:
T1=DB2

D:
D1=testdb

TID:
T1=tech-1

DID:
D1=db-1

ID:
N1=node-1

NAME:
N1=test_table
"""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            input_file = os.path.join(tmpdir, 'input.ldf')
            output_file = os.path.join(tmpdir, 'output.json')
            
            # Write test data
            with open(input_file, 'w') as f:
                f.write(ldf_content)
            
            # Convert
            convert_lineage_file_to_json(input_file, output_file)
            
            # Verify output
            assert os.path.exists(output_file)
            with open(output_file, 'r') as f:
                data = json.load(f)
                assert data['graphId'] == 'file-test'
                assert len(data['nodes']) == 1
                assert data['nodes'][0]['id'] == 'node-1'


class TestEdgeCases:
    """Test edge cases and special scenarios."""
    
    def test_empty_attributes(self):
        """Test nodes with no attributes."""
        graph = {
            'graph': 'empty-attrs',
            'start': 'N1',
            'edges': [],
            'nodes': {
                'N1': {
                    'type': 'table',
                    'path': 'T1/D1',
                    'attributes': {}
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
                'BT': {}
            }
        }
        
        ldf = json_to_lineage_format(graph)
        restored = lineage_format_to_json(ldf)
        
        assert len(restored['nodes']) == 1
        assert restored['nodes'][0]['type'] == 'table'
    
    def test_business_terms(self):
        """Test handling of business terms."""
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
    
    def test_compact_format(self):
        """Test compact format option."""
        graph = {
            'graph': 'compact-test',
            'start': 'N1',
            'edges': [['N1', 'N2']],
            'nodes': {
                'N1': {'type': 'table', 'path': 'T1/D1', 'attributes': {}},
                'N2': {'type': 'view', 'path': 'T1/D1', 'attributes': {}}
            },
            'dictionaries': {
                'T': {'T1': 'DB'},
                'D': {'D1': 'db'},
                'TID': {},
                'DID': {},
                'TP': {'table': 'table', 'view': 'view'},
                'ID': {'N1': 'n1', 'N2': 'n2'},
                'NAME': {'N1': 'name1', 'N2': 'name2'},
                'BT': {}
            }
        }
        
        compact = json_to_lineage_format(graph, {'compact': True})
        normal = json_to_lineage_format(graph, {'compact': False})
        
        # Compact should have fewer characters (no extra newlines)
        assert len(compact) < len(normal)
        
        # Both should restore to same data
        restored_compact = lineage_format_to_json(compact)
        restored_normal = lineage_format_to_json(normal)
        
        assert restored_compact['graphId'] == restored_normal['graphId']
        assert len(restored_compact['nodes']) == len(restored_normal['nodes'])


class TestRealDataFiles:
    """Test with real mock data files."""
    
    @pytest.fixture
    def examples_dir(self):
        """Get the examples directory path."""
        return os.path.join(os.path.dirname(__file__), '..', 'examples')
    
    def test_50_nodes_conversion(self, examples_dir):
        """Test conversion with 50 nodes mock data."""
        input_file = os.path.join(examples_dir, 'mock_50_nodes_linear_edges.json')
        
        if not os.path.exists(input_file):
            pytest.skip("Mock data file not found")
        
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
    
    def test_100_nodes_conversion(self, examples_dir):
        """Test conversion with 100 nodes mock data."""
        input_file = os.path.join(examples_dir, 'mock_100_nodes_combined_edges.json')
        
        if not os.path.exists(input_file):
            pytest.skip("Mock data file not found")
        
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

# Made with Bob
