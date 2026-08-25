# -*- coding: utf-8 -*-
"""diag_route.py — 找出未布线网络与封装禁布区。"""
import io
import re

# 1) SES 中 unrouted 清单
ses = io.open(
    r"src\hardware\m2-board\m2_board.ses", encoding="utf-8", errors="ignore"
).read()
routes = re.findall(r'\(net\s+(\w+|"[^"]+")', ses)
print("SES nets touched:", sorted(set(routes))[:30])

un = re.findall(r'\(unresolved[^)]*\)|\(pin\s+([^)]+)\)\s*\(pin\s+([^)]+)\)', ses)
print("via-sample:", un[:3])

# 2) 模块封装里的 zone/keepout
fp = io.open(
    r"C:\Users\fuker\AppData\Local\Programs\KiCad\10.0\share\kicad\footprints"
    r"\RF_Module.pretty\ESP32-C3-WROOM-02.kicad_mod", encoding="utf-8", errors="ignore").read()
print("has zones:", fp.count("(zone "), "| locked pads:", fp.count("locked"))
for m in re.finditer(r"\(layer \"?([\w\.]+)\"?\)", fp):
    pass
layers = set(re.findall(r'\(layer "([\w\.\*]+)"\)', fp))
print("fp layers:", layers)
# 找 courtyard/禁止区提示
print("courtyard lines:", len(re.findall(r'F\.Courtyard', fp)))

# 3) DSN 里每网络连线需求
dsn = io.open(r"src\hardware\m2-board\m2_board.dsn", encoding="utf-8", errors="ignore").read()
netpins = re.findall(r'\(net\s+(\d+)\s+\(pins\s+([^)]+)\)\)', dsn)
print("DSN net count:", len(netpins))
for code, pins in netpins:
    names = pins.split()
    if len(names) >= 6:
        print(f"  big-net({len(names)}): {names[:8]}")
