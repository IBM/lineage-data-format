#!/usr/bin/env python3
"""
Example script demonstrating conversion with real mock data files.
"""

import sys
import os

# Add parent directory to path for imports when not installed
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ldf import convert_json_file_to_lineage, convert_lineage_file_to_json  # type: ignore
import json

def main():
    examples_dir = os.path.dirname(__file__)
    
    # Test with 50 nodes
    print("=" * 70)
    print("Testing with mock_50_nodes_linear_edges.json")
    print("=" * 70)
    
    input_50 = os.path.join(examples_dir, "mock_50_nodes_linear_edges.json")
    output_50_ldf = os.path.join(examples_dir, "output_50_nodes.ldf")
    restored_50 = os.path.join(examples_dir, "restored_50_nodes.json")
    
    # Convert JSON to LDF
    print(f"\n1. Converting {input_50} to LDF format...")
    convert_json_file_to_lineage(input_50, output_50_ldf)
    print(f"   ✓ Created {output_50_ldf}")
    
    # Convert LDF back to JSON
    print(f"\n2. Converting {output_50_ldf} back to JSON...")
    convert_lineage_file_to_json(output_50_ldf, restored_50)
    print(f"   ✓ Created {restored_50}")
    
    # Verify round-trip
    print("\n3. Verifying round-trip conversion...")
    with open(input_50, 'r') as f:
        original = json.load(f)
    with open(restored_50, 'r') as f:
        restored = json.load(f)
    
    print(f"   Original nodes: {len(original['nodes'])}")
    print(f"   Restored nodes: {len(restored['nodes'])}")
    print(f"   Original edges: {len(original['edges'])}")
    print(f"   Restored edges: {len(restored['edges'])}")
    print(f"   Graph ID match: {original['graphId'] == restored['graphId']}")
    
    # Test with 100 nodes
    print("\n" + "=" * 70)
    print("Testing with mock_100_nodes_combined_edges.json")
    print("=" * 70)
    
    input_100 = os.path.join(examples_dir, "mock_100_nodes_combined_edges.json")
    output_100_ldf = os.path.join(examples_dir, "output_100_nodes.ldf")
    restored_100 = os.path.join(examples_dir, "restored_100_nodes.json")
    
    # Convert JSON to LDF
    print(f"\n1. Converting {input_100} to LDF format...")
    convert_json_file_to_lineage(input_100, output_100_ldf)
    print(f"   ✓ Created {output_100_ldf}")
    
    # Convert LDF back to JSON
    print(f"\n2. Converting {output_100_ldf} back to JSON...")
    convert_lineage_file_to_json(output_100_ldf, restored_100)
    print(f"   ✓ Created {restored_100}")
    
    # Verify round-trip
    print("\n3. Verifying round-trip conversion...")
    with open(input_100, 'r') as f:
        original = json.load(f)
    with open(restored_100, 'r') as f:
        restored = json.load(f)
    
    print(f"   Original nodes: {len(original['nodes'])}")
    print(f"   Restored nodes: {len(restored['nodes'])}")
    print(f"   Original edges: {len(original['edges'])}")
    print(f"   Restored edges: {len(restored['edges'])}")
    print(f"   Graph ID match: {original['graphId'] == restored['graphId']}")
    
    print("\n" + "=" * 70)
    print("✓ All conversions completed successfully!")
    print("=" * 70)

if __name__ == "__main__":
    main()

# Made with Bob
