"""Command line: python -m kicad_schematic_builder verify <schematic> <netlist>"""

import argparse
import sys

from .verify import verify


def main():
    parser = argparse.ArgumentParser(prog="kicad-schematic-builder")
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("verify", help="compare the connectivity of a schematic with a netlist")
    v.add_argument("schematic")
    v.add_argument("netlist")
    v.add_argument("--export-to", help="where to write the netlist exported from the schematic")
    args = parser.parse_args()
    if args.command == "verify":
        sys.exit(0 if verify(args.schematic, args.netlist, args.export_to) else 1)


if __name__ == "__main__":
    main()
