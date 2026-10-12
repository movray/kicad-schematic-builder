"""Check that a schematic connects exactly what a reference netlist says."""

import subprocess
from pathlib import Path

from .netlist import read_components, read_connectivity


def export_netlist(schematic, output):
    """Let kicad-cli export the netlist of a schematic."""
    subprocess.run(["kicad-cli", "sch", "export", "netlist", "-o", str(output), str(schematic)],
                   check=True, capture_output=True)


def verify(schematic, netlist, export_to=None):
    """Compare parts and connectivity of schematic with netlist and print the differences.

    export_to -- where to keep the netlist exported from the schematic (default: <schematic>-schematic.net).
    Net names are ignored, only which pins are connected counts. Returns True if both match.
    """
    schematic = Path(schematic)
    export_to = Path(export_to) if export_to else schematic.with_name(schematic.stem + "-schematic.net")
    export_netlist(schematic, export_to)

    drawn_parts = {r for r in read_components(export_to) if not r.startswith("#")}
    expected_parts = set(read_components(netlist))
    for ref in sorted(expected_parts - drawn_parts):
        print("MISSING part in schematic:", ref)
    for ref in sorted(drawn_parts - expected_parts):
        print("EXTRA part in schematic:  ", ref)

    drawn = read_connectivity(export_to)
    expected = read_connectivity(netlist)
    missing = [n for n in expected if n not in drawn]
    extra = [n for n in drawn if n not in expected]
    for n in missing:
        print("MISSING net in schematic:", " ".join(n))
    for n in extra:
        print("EXTRA net in schematic:  ", " ".join(n))

    ok = not missing and not extra and drawn_parts == expected_parts
    print(f"Parts: {len(drawn_parts)} drawn, {len(expected_parts)} expected. "
          f"Nets: {len(drawn)} drawn, {len(expected)} expected -> {'OK' if ok else 'MISMATCH'}")
    return ok
