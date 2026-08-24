# -*- coding: utf-8 -*-
"""bom_query.py — G1 门禁：jlcpcb 目录实查并输出结构化候选。

用法: python gates/bom_query.py "关键词" [topN]
输出: JSON {query, items:[{code,model,package,library,stock,price_usd,datasheet}]}
退出码: 0=有结果; 3=无库存结果; 2=调用失败（真实码显式传播）
"""
import json
import subprocess
import sys

def main(argv):
    if len(argv) < 2:
        print(json.dumps({"error": "usage: bom_query.py <keyword> [topN]"}))
        return 2
    kw = argv[1]
    topn = int(argv[2]) if len(argv) > 2 else 3
    proc = subprocess.run(
        ["jlcpcb", "part", "list", "-q", kw, "--limit", str(max(topn * 4, 8)), "--in-stock"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
    )
    if proc.returncode != 0:
        print(json.dumps({"error": f"jlcpcb exit {proc.returncode}", "stderr": proc.stderr[-300:]}))
        return 2
    data = json.loads(proc.stdout)
    items = []
    for it in data.get("items", []):
        items.append({
            "code": it.get("component_code"),
            "model": it.get("model"),
            "brand": it.get("brand"),
            "package": it.get("package"),
            "library": it.get("library"),          # basic / expand(Extended)
            "stock": it.get("stock"),               # JLC 贴片装配口径
            "price_usd": it.get("initial_price"),
            "datasheet": it.get("data_manual_url") or "",
        })
        if len(items) >= topn:
            break
    out = {"query": kw, "snapshot_at": "live", "items": items}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if items else 3

if __name__ == "__main__":
    sys.exit(main(sys.argv))
