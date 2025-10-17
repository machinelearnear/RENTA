"""
Command-line interface for RENTA.

This module provides a simple CLI for basic RENTA operations.
For advanced usage, use the Python API directly.
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from . import RealEstateAnalyzer, __version__, show_legal_notice


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="renta",
        description="RENTA - Real Estate Network and Trend Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  renta --version                    Show version information
  renta --legal-notice              Show legal notice
  renta --config config.yaml        Use custom configuration file
  
For advanced usage, use the Python API:
  from renta import RealEstateAnalyzer
  analyzer = RealEstateAnalyzer()
        """,
    )

    parser.add_argument("--version", action="version", version=f"RENTA {__version__}")

    parser.add_argument(
        "--legal-notice", action="store_true", help="Show legal notice and compliance information"
    )

    parser.add_argument("--config", type=str, help="Path to configuration file")

    parser.add_argument(
        "--validate-config", action="store_true", help="Validate configuration file and exit"
    )

    args = parser.parse_args()

    if args.legal_notice:
        show_legal_notice()
        return 0

    if args.validate_config:
        try:
            analyzer = RealEstateAnalyzer(config_path=args.config)
            print("✓ Configuration is valid")
            return 0
        except Exception as e:
            print(f"✗ Configuration validation failed: {e}")
            return 1

    # If no specific action requested, show help
    if len(sys.argv) == 1:
        parser.print_help()
        return 0

    try:
        analyzer = RealEstateAnalyzer(config_path=args.config)
        print(f"RENTA {__version__} initialized successfully")
        print("Use the Python API for data analysis operations.")
        return 0
    except Exception as e:
        print(f"Error initializing RENTA: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
