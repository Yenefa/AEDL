# -*- coding: utf-8 -*-
import re, sys, pathlib
LIB = pathlib.Path(r"D:/Program Files/KiCad/10.0/share/kicad/symbols")
BS = chr(92)
def extract(libfile, name):
    t = (LIB / libfile).read_text(encoding="utf-8")
    i = t.find('(symbol "' + name + '"')
    if i < 0: return None
    depth, j, n = 0, i, len(t)
    while j < n:
        c = t[j]
        if c == '"':
            j += 1
            while j < n and t[j] != '"':
                if t[j] == BS: j += 1
                j += 1
        elif c == '(': depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0: return t[i:j+1]
        j += 1
    return None
def pins(block):
    out = []
    for m in re.finditer(r'\(pin (\w+) (\w+)\s*\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\)\s*\(length ([-\d.]+)\)(.*?)\(name "([^"]*)"(.*?)\(number "([^"]*)"', block, re.S):
        out.append(dict(etype=m.group(1), x=float(m.group(3)), y=float(m.group(4)), ang=float(m.group(5)), L=float(m.group(6)), num=m.group(10), name=m.group(8)))
    return out
if __name__ == "__main__":
    lib, name = sys.argv[1], sys.argv[2]
    b = extract(lib, name)
    if b is None: print("NOT FOUND", lib, name); sys.exit(1)
    ext = re.search(r'\(extends "([^"]+)"\)', b)
    ps = pins(b)
    print(f"{lib}:{name}  pins={len(ps)}" + (f"  EXTENDS {ext.group(1)}" if ext else ""))
    for p in sorted(ps, key=lambda p: (len(p['num']), p['num'])):
        print(f"  {p['num']:>4} {p['name']:<10} {p['etype']:<13} at({p['x']:>7},{p['y']:>7}) ang={p['ang']:>3.0f} L={p['L']}")
