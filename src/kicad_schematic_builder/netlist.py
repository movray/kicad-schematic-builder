"""Read KiCad S-expression netlists (as written by SKiDL or kicad-cli)."""

import re
from pathlib import Path


def _components_text(text):
    return text[: text.index("(nets")]


def read_components(path):
    """ref -> dict(value, footprint, datasheet, description, lib_id, in_bom)."""
    text = Path(path).read_text()
    comps = {}
    for block in re.split(r"\(comp\b", _components_text(text))[1:]:
        def get(key):
            m = re.search(r"\(" + key + r' "([^"]*)"\)', block)
            return m.group(1) if m else ""

        comps[get("ref")] = {
            "value": get("value"),
            "footprint": get("footprint"),
            "datasheet": get("datasheet"),
            "description": get("description"),
            "lib_id": f'{get("lib")}:{get("part")}',
            "in_bom": "exclude_from_bom" not in block,
        }
    return comps


def read_connectivity(path):
    """Sorted list of nets, each a sorted tuple of 'ref.pin'. Single-pin nets are skipped,
    so the result does not depend on net names."""
    text = Path(path).read_text()
    text = text[text.index("(nets"):]
    nets = []
    for block in re.split(r"\(net\b", text)[1:]:
        nodes = tuple(sorted(f"{r}.{p}" for r, p in re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', block)))
        if len(nodes) > 1:
            nets.append(nodes)
    return sorted(nets)
