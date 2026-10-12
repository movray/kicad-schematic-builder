"""Find KiCad library symbols and turn them into the flattened form a schematic embeds."""

import json
import os
import re
from pathlib import Path

from .sexpr import child, dump, find_symbol, parse, quote, unquote

KICAD_VERSION = "9.0"
DEFAULT_ENV = {
    "KICAD9_SYMBOL_DIR": "/usr/share/kicad/symbols",
    "KICAD9_FOOTPRINT_DIR": "/usr/share/kicad/footprints",
}


def kicad_config_dir():
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "kicad" / KICAD_VERSION


class SymbolLibraries:
    """Resolves library nicknames to .kicad_sym files the same way KiCad does.

    Lookup order: explicit `extra` mapping, project sym-lib-table, global sym-lib-table,
    and finally <KICAD9_SYMBOL_DIR>/<nickname>.kicad_sym.
    """

    def __init__(self, project_dir=None, extra=None):
        self.project_dir = Path(project_dir) if project_dir else None
        self.env = self._environment()
        self.paths = {}
        global_table = kicad_config_dir() / "sym-lib-table"
        if global_table.exists():
            self.paths.update(self._read_table(global_table))
        if self.project_dir and (self.project_dir / "sym-lib-table").exists():
            self.paths.update(self._read_table(self.project_dir / "sym-lib-table"))
        self.paths.update({k: Path(v) for k, v in (extra or {}).items()})
        self._texts = {}

    def _environment(self):
        env = dict(DEFAULT_ENV)
        common = kicad_config_dir() / "kicad_common.json"
        if common.exists():
            env.update(json.loads(common.read_text()).get("environment", {}).get("vars") or {})
        env.update({k: v for k, v in os.environ.items() if k.startswith("KICAD")})
        if self.project_dir:
            env["KIPRJMOD"] = str(self.project_dir)
        return env

    def _expand(self, uri):
        return re.sub(r"\$\{([^}]+)\}", lambda m: self.env.get(m.group(1), m.group(0)), uri)

    def _read_table(self, path):
        result = {}
        for name, uri in re.findall(r'\(lib \(name "([^"]+)"\)\s*\(type "KiCad"\)\s*\(uri "([^"]+)"\)', path.read_text()):
            result[name] = Path(self._expand(uri))
        return result

    def path(self, lib):
        return self.paths.get(lib, Path(self.env["KICAD9_SYMBOL_DIR"]) / f"{lib}.kicad_sym")

    def text(self, lib):
        if lib not in self._texts:
            path = self.path(lib)
            if not path.exists():
                raise FileNotFoundError(f"Symbol library '{lib}' not found (looked for {path})")
            self._texts[lib] = path.read_text()
        return self._texts[lib]

    def flattened(self, lib_id):
        """Symbol tree named 'lib:name' with any 'extends' chain resolved."""
        lib, name = lib_id.split(":", 1)
        tree = self._flatten(lib, name)
        tree[1] = quote(lib_id)
        return tree

    def _flatten(self, lib, name):
        block = find_symbol(self.text(lib), name)
        if block is None:
            raise KeyError(f"Symbol '{name}' not found in library '{lib}' ({self.path(lib)})")
        tree = parse(block)
        extends = child(tree, "extends")
        if extends is None:
            return tree
        parent_name = unquote(extends[1])
        parent = self._flatten(lib, parent_name)
        own_props = {unquote(x[1]) for x in tree if isinstance(x, list) and x[0] == "property"}
        own_keys = {x[0] for x in tree if isinstance(x, list) and x[0] not in ("property", "extends")}
        result = ["symbol", quote(name)]
        # Flags (pin_names, in_bom, ...) from the parent unless the child overrides them
        result += [x for x in parent if isinstance(x, list) and x[0] not in ("property", "symbol") and x[0] not in own_keys]
        result += [x for x in tree if isinstance(x, list) and x[0] not in ("property", "extends")]
        # Child properties first, parent properties the child does not define afterwards
        result += [x for x in tree if isinstance(x, list) and x[0] == "property"]
        result += [x for x in parent if isinstance(x, list) and x[0] == "property" and unquote(x[1]) not in own_props]
        # Graphic units, renamed from Parent_u_s to Child_u_s
        for sub in parent:
            if isinstance(sub, list) and sub[0] == "symbol":
                suffix = unquote(sub[1])[len(parent_name):]
                result.append([sub[0], quote(name + suffix)] + sub[2:])
        # KiCad keeps embedded_fonts last
        fonts = [x for x in result if isinstance(x, list) and x[0] == "embedded_fonts"]
        return [x for x in result if x not in fonts] + fonts[:1]


class LibSymbol:
    """A library symbol with pin and property positions, ready to embed in a schematic."""

    def __init__(self, libraries, lib_id):
        self.lib_id = lib_id
        tree = libraries.flattened(lib_id)
        self.text = dump(tree, indent=2)
        in_bom = child(tree, "in_bom")
        self.in_bom = in_bom is None or in_bom[1] == "yes"
        self.props = {}  # name -> (x, y) in library coordinates (y up)
        self.pins = {}  # (unit, number) -> (x, y) in library coordinates (y up)
        for item in tree:
            if isinstance(item, list) and item[0] == "property":
                at = child(item, "at")
                self.props[unquote(item[1])] = (float(at[1]), float(at[2]))
        for sub in tree:
            if isinstance(sub, list) and sub[0] == "symbol":
                unit = int(unquote(sub[1]).rsplit("_", 2)[1])
                for pin in sub:
                    if isinstance(pin, list) and pin[0] == "pin":
                        at = child(pin, "at")
                        number = unquote(child(pin, "number")[1])
                        self.pins[(unit, number)] = (float(at[1]), float(at[2]))

    def has_pin(self, unit, number):
        return (unit, number) in self.pins or (0, number) in self.pins

    def pin(self, unit, number):
        return self.pins.get((unit, number)) or self.pins[(0, number)]
