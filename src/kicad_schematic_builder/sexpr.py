"""Minimal S-expression helpers for KiCad files."""

import re

_TOKEN = re.compile(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+')


def parse(text):
    """Parse the first S-expression in text into nested lists. Atoms keep their quotes."""
    stack = [[]]
    for tok in _TOKEN.findall(text):
        if tok == "(":
            stack.append([])
        elif tok == ")":
            node = stack.pop()
            stack[-1].append(node)
        else:
            stack[-1].append(tok)
    return stack[0][0]


def dump(node, indent=1):
    """Serialize nested lists back to text, one child list per line."""
    pad = "\t" * indent
    atoms = [x for x in node if not isinstance(x, list)]
    lists = [x for x in node if isinstance(x, list)]
    if not lists:
        return pad + "(" + " ".join(atoms) + ")"
    inner = "\n".join(dump(x, indent + 1) for x in lists)
    return f"{pad}({' '.join(atoms)}\n{inner}\n{pad})"


def extract_block(text, start):
    """Return the balanced '( ... )' block starting at index start."""
    depth, i, in_str = 0, start, False
    while True:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1


def find_symbol(text, name):
    """Text of the top-level '(symbol "name" ...)' block, or None."""
    m = re.search(r'\(symbol "' + re.escape(name) + r'"\s', text)
    return extract_block(text, m.start()) if m else None


def child(node, key):
    return next((x for x in node if isinstance(x, list) and x and x[0] == key), None)


def quote(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def unquote(s):
    return s[1:-1].replace('\\"', '"').replace("\\\\", "\\") if s.startswith('"') else s
