"""Drawing model for a single-sheet KiCad 9 schematic.

Parts come from a netlist, the caller decides where symbols, wires, labels and power symbols go.
Coordinates are in mm, y points down (like in the schematic editor).
"""

import uuid
from collections import Counter
from pathlib import Path

from .library import LibSymbol, SymbolLibraries
from .netlist import read_components

GRID = 1.27


def snap(v):
    return round(round(v / GRID) * GRID, 2)


def transform(lx, ly, rot, mirror):
    """Library coordinates (y up) -> offset in schematic coordinates (y down)."""
    x, y = lx, -ly
    if mirror == "x":
        y = -y
    elif mirror == "y":
        x = -x
    for _ in range((rot // 90) % 4):
        x, y = y, -x
    return x, y


def _on_segment(p, a, b):
    if a[0] == b[0] == p[0]:
        return min(a[1], b[1]) < p[1] < max(a[1], b[1])
    if a[1] == b[1] == p[1]:
        return min(a[0], b[0]) < p[0] < max(a[0], b[0])
    return False


def _esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


class Schematic:
    """Collects symbols, wires and labels and writes them as a .kicad_sch file.

    netlist     -- netlist with the parts (refs, values, footprints, library ids)
    project     -- KiCad project name used in the symbol instances (default: netlist file stem)
    extra_libs  -- {nickname: path to .kicad_sym} for libraries not in any sym-lib-table
    """

    def __init__(self, netlist, project=None, extra_libs=None):
        netlist = Path(netlist)
        self.project = project or netlist.stem
        self.comps = read_components(netlist)
        self.libraries = SymbolLibraries(project_dir=netlist.parent, extra=extra_libs)
        self.libs = {}
        self.symbols = []
        self.wires = []  # [((x0, y0), (x1, y1))]
        self.labels = []  # (name, x, y, angle)
        self.pin_points = []
        self.power_count = 0

    def lib(self, lib_id):
        if lib_id not in self.libs:
            self.libs[lib_id] = LibSymbol(self.libraries, lib_id)
        return self.libs[lib_id]

    # Placing -------------------------------------------------------------------------------------
    def place(self, ref, x, y, rot=0, mirror=None, unit=1, ref_at=None, value_at=None,
              show_ref=True, show_value=True):
        """Place one unit of a netlist part. rot in degrees (0/90/180/270), mirror "x" or "y".
        ref_at / value_at are field offsets from the symbol origin; default is the library position."""
        if ref not in self.comps:
            raise KeyError(f"{ref} is not in the netlist")
        comp = self.comps[ref]
        sym = dict(ref=ref, lib_id=comp["lib_id"], x=x, y=y, rot=rot, mirror=mirror, unit=unit,
                   value=comp["value"], footprint=comp["footprint"], datasheet=comp["datasheet"],
                   description=comp["description"], ref_at=ref_at, value_at=value_at,
                   show_ref=show_ref, show_value=show_value,
                   in_bom=comp["in_bom"] and self.lib(comp["lib_id"]).in_bom)
        self.symbols.append(sym)
        self._register_pins(sym)
        return sym

    def power(self, kind, x, y, rot=0):
        """Power symbol from the 'power' library (VCC, GND, +5V, PWR_FLAG, ...) with its pin at (x, y)."""
        self.power_count += 1
        prefix = "#FLG" if kind == "PWR_FLAG" else "#PWR"
        sym = dict(ref=f"{prefix}{self.power_count:02d}", lib_id=f"power:{kind}", x=x, y=y, rot=rot,
                   mirror=None, unit=1, value=kind, footprint="", datasheet="", description="",
                   ref_at=None, value_at=None, show_ref=False, show_value=True, in_bom=False)
        self.symbols.append(sym)
        self._register_pins(sym)
        return sym

    def _register_pins(self, sym):
        lib = self.lib(sym["lib_id"])
        for (unit, number), (lx, ly) in lib.pins.items():
            if unit in (0, sym["unit"]):
                dx, dy = transform(lx, ly, sym["rot"], sym["mirror"])
                self.pin_points.append((snap(sym["x"] + dx), snap(sym["y"] + dy)))

    def pin(self, ref, number):
        """Schematic position of a pin of an already placed part (any placed unit that has it)."""
        number = str(number)
        for s in self.symbols:
            lib = self.lib(s["lib_id"])
            if s["ref"] == ref and lib.has_pin(s["unit"], number):
                dx, dy = transform(*lib.pin(s["unit"], number), s["rot"], s["mirror"])
                return snap(s["x"] + dx), snap(s["y"] + dy)
        raise KeyError(f"No placed unit of {ref} has pin {number}")

    # Connections ---------------------------------------------------------------------------------
    def wire(self, *points):
        """Polyline through (x, y) points. Only horizontal and vertical segments."""
        pts = [(snap(x), snap(y)) for x, y in points]
        for a, b in zip(pts, pts[1:]):
            if a[0] != b[0] and a[1] != b[1]:
                raise ValueError(f"diagonal wire {a} -> {b}")
            if a != b:
                self.wires.append((a, b))

    def label(self, name, x, y, angle=0):
        """Net label; angle 0 = text to the right, 180 = text to the left."""
        self.labels.append((name, snap(x), snap(y), angle))

    def _finalize_wires(self):
        """Split wires where another wire end, pin or label touches them and return junction points."""
        points = set(self.pin_points) | {p for w in self.wires for p in w} | {(l[1], l[2]) for l in self.labels}
        result = []
        for a, b in self.wires:
            inner = sorted(
                (p for p in points if p not in (a, b) and _on_segment(p, a, b)),
                key=lambda p: abs(p[0] - a[0]) + abs(p[1] - a[1]),
            )
            chain = [a] + inner + [b]
            result.extend(zip(chain, chain[1:]))
        self.wires = result
        degree = Counter()
        for a, b in self.wires:
            degree[a] += 1
            degree[b] += 1
        for p in self.pin_points:
            if p in degree:
                degree[p] += 1
        return [p for p, n in degree.items() if n >= 3]

    # Output --------------------------------------------------------------------------------------
    def write(self, path, title="", paper="A4", comment="Generated by kicad-schematic-builder"):
        junctions = self._finalize_wires()
        root = str(uuid.uuid4())
        out = [
            "(kicad_sch",
            "\t(version 20250114)",
            '\t(generator "eeschema")',
            '\t(generator_version "9.0")',
            f'\t(uuid "{root}")',
            f'\t(paper "{paper}")',
            f'\t(title_block (title "{_esc(title)}") (comment 1 "{_esc(comment)}"))',
            "\t(lib_symbols",
        ]
        out += [lib.text for lib in self.libs.values()]
        out.append("\t)")
        for x, y in junctions:
            out.append(f'\t(junction (at {x} {y}) (diameter 0) (color 0 0 0 0) (uuid "{uuid.uuid4()}"))')
        for (x0, y0), (x1, y1) in self.wires:
            out.append(f'\t(wire (pts (xy {x0} {y0}) (xy {x1} {y1})) (stroke (width 0) (type default)) (uuid "{uuid.uuid4()}"))')
        for name, x, y, angle in self.labels:
            justify = "left bottom" if angle == 0 else "right bottom"
            out.append(f'\t(label "{_esc(name)}" (at {x} {y} {angle}) (effects (font (size 1.27 1.27)) (justify {justify})) (uuid "{uuid.uuid4()}"))')
        out += [self._symbol_text(s, root) for s in self.symbols]
        out.append('\t(sheet_instances (path "/" (page "1")))')
        out.append("\t(embedded_fonts no)")
        out.append(")")
        Path(path).write_text("\n".join(out) + "\n")

    def _symbol_text(self, s, root):
        lib = self.lib(s["lib_id"])
        x, y = snap(s["x"]), snap(s["y"])

        def prop_at(name, given):
            if given is not None:
                return snap(x + given[0]), snap(y + given[1])
            dx, dy = transform(*lib.props.get(name, (0, 0)), s["rot"], s["mirror"])
            return snap(x + dx), snap(y + dy)

        # Field angles are relative to the symbol: 90 keeps text horizontal on rotated symbols
        text_angle = 90 if s["rot"] in (90, 270) else 0

        def prop(name, value, at, hidden):
            hide = " (hide yes)" if hidden else ""
            return (f'\t\t(property "{name}" "{_esc(value)}" (at {at[0]} {at[1]} {text_angle}) '
                    f"(effects (font (size 1.27 1.27)){hide}))")

        mirror = f" (mirror {s['mirror']})" if s["mirror"] else ""
        in_bom = "yes" if s["in_bom"] else "no"
        on_board = "no" if s["lib_id"].startswith("power:") else "yes"
        pins = sorted({n for (u, n) in lib.pins if u in (0, s["unit"])})
        lines = [
            "\t(symbol",
            f'\t\t(lib_id "{s["lib_id"]}") (at {x} {y} {s["rot"]}){mirror} (unit {s["unit"]})',
            f"\t\t(exclude_from_sim no) (in_bom {in_bom}) (on_board {on_board}) (dnp no)",
            f'\t\t(uuid "{uuid.uuid4()}")',
            prop("Reference", s["ref"], prop_at("Reference", s["ref_at"]), not s["show_ref"]),
            prop("Value", s["value"], prop_at("Value", s["value_at"]), not s["show_value"]),
            prop("Footprint", s["footprint"], (x, y), True),
            prop("Datasheet", s["datasheet"], (x, y), True),
            prop("Description", s["description"], (x, y), True),
        ]
        lines += [f'\t\t(pin "{n}" (uuid "{uuid.uuid4()}"))' for n in pins]
        lines.append(f'\t\t(instances (project "{_esc(self.project)}" (path "/{root}" (reference "{s["ref"]}") (unit {s["unit"]}))))')
        lines.append("\t)")
        return "\n".join(lines)
