"""Run with: python -m pytest tests  (needs the KiCad 9 symbol libraries)"""

from kicad_schematic_builder import LibSymbol, SymbolLibraries, transform


def test_extends_is_flattened():
    sym = LibSymbol(SymbolLibraries(), "Transistor_FET:AO3401A")
    assert "(extends" not in sym.text
    assert '(symbol "AO3401A_1_1"' in sym.text
    assert {n for (_, n) in sym.pins} == {"1", "2", "3"}


def test_multi_unit_pins():
    sym = LibSymbol(SymbolLibraries(), "Device:R_Pack04_Split")
    assert {u for (u, _) in sym.pins} == {1, 2, 3, 4}


def test_transform():
    assert transform(0, 2.54, 0, None) == (0, -2.54)  # library y up -> schematic y down
    assert transform(0, 2.54, 90, None) == (-2.54, 0)
    assert transform(2.54, 0, 0, "y") == (-2.54, 0)
