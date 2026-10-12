# kicad-schematic-builder

Draw readable KiCad 9 schematics from a netlist with a few lines of Python.

Tools like SKiDL describe a circuit as code, but their generated schematics are hard to read.
kicad-schematic-builder takes the parts from the netlist and lets you place symbols, wires, labels and power
symbols on a grid yourself, like you would in the schematic editor. Afterwards it checks with
`kicad-cli` that the drawing connects exactly what the netlist says.

## Install

```bash
pip install -e ~/priv/office/make/kicad-schematic-builder      # into the venv you use for SKiDL
```

Needs KiCad 9 (`kicad-cli` and the symbol libraries). No other dependencies.

## Usage

Starting point with comments on every function: copy `schematic.py.example` into your project as `schematic.py`.

```python
from kicad_schematic_builder import Schematic, verify

sch = Schematic("board.net")                       # parts, values, footprints from the netlist
sch.place("U1", 100, 100)                          # mm, y points down
sch.place("C1", 120, 80, rot=90)
sch.wire(sch.pin("U1", "VDD_PIN_NUMBER"), (100, 80), sch.pin("C1", "1"))
sch.power("VCC", 100, 75)                          # power symbol with its pin at (100, 75)
sch.power("GND", *sch.pin("C1", "2"))
sch.label("SDA", 130, 100)                         # net label, angle 180 = text to the left
sch.write("board.kicad_sch", title="My board")

verify("board.kicad_sch", "board.net")            # prints differences, returns True if equal
```

* `place(ref, x, y, rot=0, mirror=None, unit=1, ref_at=None, value_at=None, show_ref=True, show_value=True)`
  places one unit of a part. `mirror` is `"x"` or `"y"`, `ref_at` / `value_at` are field offsets from the symbol origin.
* `pin(ref, number)` returns the schematic position of a pin, so wires can be drawn between pins.
* `wire(*points)` draws a polyline with horizontal and vertical segments.
  Wires are split where they touch pins, labels or other wire ends, junction dots are added automatically.
* Coordinates are snapped to the 1.27 mm grid.

Command line check: `kicad-schematic-builder verify board.kicad_sch board.net`

## Symbol libraries

Symbols are looked up like KiCad does: project `sym-lib-table` next to the netlist, the global
`~/.config/kicad/9.0/sym-lib-table`, then `${KICAD9_SYMBOL_DIR}/<lib>.kicad_sym`.
Other libraries can be passed with `Schematic(..., extra_libs={"MyLib": "path/MyLib.kicad_sym"})`.
Symbols that `extends` another symbol are flattened the same way KiCad embeds them.

## Limits

* Single sheet, net labels only (no hierarchical or global labels yet).
* The layout is up to you: there is no automatic placement or routing.
* The output is regenerated on every run, edits made in KiCad are overwritten.

## Example

`~/priv/office/make/7segment/7segment-panel-v2/schematic.py`

## Tests

```bash
python -m pytest tests
```
