"""
Command-line interface for lineage data format converter.
"""

import argparse
import sys
from pathlib import Path
from .converter import (
    convert_json_file_to_lineage,
    convert_lineage_file_to_json,
)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Convert between JSON and Lineage Definition Format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert JSON to lineage format
  ldf json-to-lineage input.json output.ldf
  
  # Convert lineage format to JSON
  ldf lineage-to-json input.ldf output.json
  
  # Use compact format (no extra whitespace)
  ldf json-to-lineage input.json output.ldf --compact
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # json-to-lineage command
    json_parser = subparsers.add_parser(
        'json-to-lineage',
        help='Convert JSON file to lineage format'
    )
    json_parser.add_argument('input', help='Input JSON file path')
    json_parser.add_argument('output', help='Output lineage format file path')
    json_parser.add_argument(
        '--compact',
        action='store_true',
        help='Use compact format (no extra whitespace)'
    )
    
    # lineage-to-json command
    lineage_parser = subparsers.add_parser(
        'lineage-to-json',
        help='Convert lineage format file to JSON'
    )
    lineage_parser.add_argument('input', help='Input lineage format file path')
    lineage_parser.add_argument('output', help='Output JSON file path')
    lineage_parser.add_argument(
        '--indent',
        type=int,
        default=2,
        help='JSON indentation level (default: 2)'
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        if args.command == 'json-to-lineage':
            convert_json_file_to_lineage(
                args.input,
                args.output,
                compact=args.compact
            )
            print(f"✓ Converted {args.input} → {args.output}")
        
        elif args.command == 'lineage-to-json':
            convert_lineage_file_to_json(
                args.input,
                args.output,
                indent=args.indent
            )
            print(f"✓ Converted {args.input} → {args.output}")
    
    except FileNotFoundError as e:
        print(f"Error: File not found - {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

# Made with Bob
