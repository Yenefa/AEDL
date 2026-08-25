# -*- coding: utf-8 -*-
"""fix_flasher_args.py — 修正 PIO+IDF6 flasher_args.json 的陈旧相对路径。

IDF6 实际产物在 build 根：bootloader.bin / partitions.bin / firmware.bin
但 flasher_args 仍引用 bootloader/xxx、partition_table/xxx 子目录。
"""
import io
import json
import os
import sys

BD = r"src\firmware\.pio\build\esp32c3_simstub"
p = os.path.join(BD, "flasher_args.json")
d = json.load(io.open(p, encoding="utf-8"))

fixed = {}
missing = []
# IDF6 产物实际名与 flasher_args 引用名的别名表
ALIASES = {
    "partition-table.bin": "partitions.bin",
    "sht30-logger.bin": "firmware.bin",
}
for off, rel in d.get("flash_files", {}).items():
    base = os.path.basename(rel)
    if not os.path.exists(os.path.join(BD, base)):
        base = ALIASES.get(base, base)
    if os.path.exists(os.path.join(BD, base)):
        fixed[off] = base
    else:
        missing.append(rel)

print("fixed:", json.dumps(fixed))
if missing:
    print("MISSING:", missing)
    sys.exit(4)
d["flash_files"] = fixed
io.open(p, "w", encoding="utf-8", newline="\n").write(json.dumps(d, indent=2))
print("OK")
