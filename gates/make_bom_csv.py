# -*- coding: utf-8 -*-
"""make_bom_csv.py — 从 bom_v1.json 展开 per-ref BOM CSV（G10 交付物）。

输出: delivery/bom.csv（嘉立创 SMT 可直接使用的列结构）
退出码: 0 成功
"""
import csv
import io
import json
import sys

SRC = r"gates\bom\bom_v1.json"
OUT = r"delivery\bom.csv"


def main():
    bom = json.load(io.open(SRC, encoding="utf-8"))
    rows = []
    for item in bom["items"]:
        refs = [r.strip() for r in item["ref"].split(",")]
        lcsc = item.get("lcsc", "")
        if lcsc == "TBD":
            continue  # 未冻结料位不进交付 BOM（R5/R6 已在下方特判）
        for ref in refs:
            rows.append({
                "Comment": item["value"],
                "Designator": ref,
                "Footprint": item.get("footprint", ""),
                "LCSC Part #": lcsc,
                "JLC Lib": item.get("jlc_lib", ""),
                "Stock@freeze": item.get("stock", ""),
            })
    # R5/R6 5.1k（bom_v1 中 TBD→已实查 C22356467）
    for ref in ("R5", "R6"):
        rows.append({
            "Comment": "5.1kΩ",
            "Designator": ref,
            "Footprint": "Resistor_SMD:R_0603_1608Metric",
            "LCSC Part #": "C22356467",
            "JLC Lib": "expand",
            "Stock@freeze": 352561,
        })

    rows.sort(key=lambda r: r["Designator"])
    with io.open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"bom rows={len(rows)} -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
