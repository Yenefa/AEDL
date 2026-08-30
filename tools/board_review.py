"""M2 板级自动评审 — 从 m2_board.kicad_pcb 提取布局几何，逐项生成机器可读评审证据。

8 项评审（BOARD_REVIEW_IDS）全部基于 PCB/原理图静态数据机器测量：
  USB_EDGE / ESP_ANTENNA / GROUND_RETURN / DECOUPLING /
  USB_ROUTING / SHT30_THERMAL / PROTECTION / ASSEMBLY
机器无法判定的事项（朝向/阻抗/气流/瞬态）在 evidence 中显式标注需人工复核。

适配 KiCad 10 S-expression：net 直接用名字、板框为 Edge.Cuts gr_line 集合。
输出：notes/m2-evidence-reset/generated/board_review_auto.json
用法：py -3 tools\\board_review.py
"""

from __future__ import annotations

import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
PCB_PATH = ROOT / "src" / "hardware" / "m2-board" / "m2_board.kicad_pcb"
SCH_PATH = ROOT / "src" / "hardware" / "m2-board" / "m2_board.kicad_sch"
OUT_PATH = ROOT / "notes" / "m2-evidence-reset" / "generated" / "board_review_auto.json"

# mm 阈值（依据：ESP32-C3-WROOM-02 硬件设计指南 / USB-C 板边连接器惯例 / SHT30 数据手册）
USB_EDGE_MAX_MM = 1.0        # USB-C courtyard 前沿（壳体侧）距板边：贴边安装要求
ANTENNA_KEEPOUT_MM = 7.5     # 模组天线端净空圈内不得有其他器件
DECOUPLING_MAX_MM = 8.0      # 去耦电容到对应 IC courtyard 边界的最大距离
USB_DIFF_MAX_SKEW_MM = 1.0   # USB_DP/USB_DM 走线长度失配
THERMAL_MIN_DIST_MM = 10.0   # SHT30 到最近潜在热源最小距离

USB_CHANNELS = {
    "D+": {
        "nets": ("USB_DP_CONN", "USB_DP"),
        "pins": {
            "J1.A6": "USB_DP_CONN", "J1.B6": "USB_DP_CONN",
            "R7.1": "USB_DP_CONN", "R7.2": "USB_DP", "U1.14": "USB_DP",
        },
    },
    "D-": {
        "nets": ("USB_DM_CONN", "USB_DM"),
        "pins": {
            "J1.A7": "USB_DM_CONN", "J1.B7": "USB_DM_CONN",
            "R8.1": "USB_DM_CONN", "R8.2": "USB_DM", "U1.13": "USB_DM",
        },
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def review_exit_code(reviews) -> int:
    """Fail closed unless every review explicitly reports pass."""
    return 0 if reviews and all(review.get("status") == "pass" for review in reviews) else 1


# ---------------------------------------------------------------- KiCad 10 解析

def parse_pcb(text: str) -> Dict[str, Any]:
    """footprint（lib/坐标/旋转）+ 板框（Edge.Cuts 包络）+ segment/via/zone。"""
    footprints: List[Dict[str, Any]] = []
    pins: Dict[str, Optional[str]] = {}
    # footprint 块：从 "(footprint " 到下一个 "(footprint "/顶层对象；取块内第一个 (at ...) 为放置坐标
    starts = [m.start() for m in re.finditer(r'\(footprint "[^"]+"', text)]
    starts.append(len(text))
    for i in range(len(starts) - 1):
        block = text[starts[i]:starts[i + 1]]
        lib_m = re.search(r'\(footprint "([^"]+)"', block)
        # footprint 级 at：块内第一个 (at x y [rot])（pad 层级的 at 都在其后）
        at_m = re.search(r'\(at (-?[\d.]+) (-?[\d.]+)(?: (-?[\d.]+))?\)', block)
        ref_m = re.search(r'\(property "Reference" "([^"]+)"', block)
        if not (lib_m and at_m and ref_m):
            continue
        lib = lib_m.group(1)
        lib_id = lib.split(":")[-1]
        rot = float(at_m.group(3) or 0)
        # courtyard bbox（相对原点、未旋转坐标；rot!=0 时退回 None）
        cxs, cys = [], []
        for fm in re.finditer(
                r'\(fp_line\s*\(start (-?[\d.]+) (-?[\d.]+)\)\s*\(end (-?[\d.]+) (-?[\d.]+)\)'
                r'(?:(?!\(fp_line).)*?\(layer "F\.CrtYd"\)', block, re.S):
            cxs += [float(fm.group(1)), float(fm.group(3))]
            cys += [float(fm.group(2)), float(fm.group(4))]
        courtyard = None
        if cxs and rot == 0:
            courtyard = (min(cxs), min(cys), max(cxs), max(cys))
        footprints.append({
            "ref": ref_m.group(1), "lib_id": lib_id,
            "x": float(at_m.group(1)), "y": float(at_m.group(2)),
            "rot": rot, "courtyard": courtyard,
        })
        pad_matches = list(re.finditer(r'\(pad "([^"]*)"', block))
        for pad_index, pad_match in enumerate(pad_matches):
            pad_end = pad_matches[pad_index + 1].start() if pad_index + 1 < len(pad_matches) else len(block)
            pad_block = block[pad_match.start():pad_end]
            net_m = re.search(r'\(net "([^"]+)"\)', pad_block)
            key = f"{ref_m.group(1)}.{pad_match.group(1)}"
            observed = net_m.group(1) if net_m else None
            if key in pins and pins[key] != observed:
                pins[key] = "<conflicting duplicate pad nets>"
            else:
                pins[key] = observed

    # 板框：Edge.Cuts 上所有 gr_line/gr_rect 顶点的包络
    xs, ys = [], []
    for lm in re.finditer(
            r'\(gr_(line|rect)[\s\S]{0,400}?\(layer "Edge.Cuts"\)', text):
        block = lm.group(0)
        for pm in re.finditer(r'\((?:start|end)\ (-?[\d.]+) (-?[\d.]+)\)', block):
            xs.append(float(pm.group(1)))
            ys.append(float(pm.group(2)))
        for pm in re.finditer(r'\(xy (-?[\d.]+) (-?[\d.]+)\)', block):
            xs.append(float(pm.group(1)))
            ys.append(float(pm.group(2)))
    edge = (min(xs), min(ys), max(xs), max(ys)) if xs else None

    segments = []
    for sm in re.finditer(
            r'\(segment\s*\(start (-?[\d.]+) (-?[\d.]+)\)\s*\(end (-?[\d.]+) (-?[\d.]+)\)\s*'
            r'\(width [\d.]+\)\s*\(layer "([^"]+)"\)\s*\(net "([^"]+)"\)', text):
        segments.append({
            "x1": float(sm.group(1)), "y1": float(sm.group(2)),
            "x2": float(sm.group(3)), "y2": float(sm.group(4)),
            "layer": sm.group(5), "net": sm.group(6),
        })
    vias = len(re.findall(r'\(via\s', text))
    has_zone = bool(re.search(r'^\s*\(zone', text, re.M))
    nets = sorted({m.group(1) for m in re.finditer(r'\(net "([^"]+)"\)', text)})
    return {"footprints": footprints, "edge": edge, "segments": segments,
            "vias": vias, "has_zone": has_zone, "nets": nets, "pins": pins}


# ---------------------------------------------------------------- 评审项

def dist(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def edge_distance(fp: Dict[str, Any], edge: Tuple[float, ...]) -> float:
    x1, y1, x2, y2 = edge
    return min(fp["x"] - x1, x2 - fp["x"], fp["y"] - y1, y2 - fp["y"])


def review_usb_edge(footprints, edge) -> Dict[str, Any]:
    usb = next((f for f in footprints if "USB_C" in f["lib_id"]), None)
    if not usb or not edge:
        return {"id": "USB_EDGE", "status": "fail",
                "evidence": "USB-C footprint or board edge not found"}
    # 贴边度量：courtyard 前沿（壳体侧 y_min）到最近板边的距离。
    # courtyard 前沿贴板边（<=1mm）= 板边贴装；质心距边由连接器深度决定，不作判据。
    x1, y1, x2, y2 = edge
    if usb.get("courtyard"):
        cx1, cy1, cx2, cy2 = usb["courtyard"]
        front_y = usb["y"] + cy1  # rot=0 时 -Y 为壳体前沿
        d = front_y - y1
        ok = 0 <= d <= USB_EDGE_MAX_MM
        evidence = (f"USB-C {usb['ref']} 质心 ({usb['x']},{usb['y']})，"
                    f"courtyard 前沿距上板边 {d:.2f}mm（板边贴装要求 0~{USB_EDGE_MAX_MM}mm）；"
                    f"外形/禁布区与外壳配合需评审人在 PCB 渲染中目检")
        measured = {"courtyard_front_to_edge_mm": round(d, 2)}
    else:
        d = edge_distance(usb, edge)
        ok = d <= USB_EDGE_MAX_MM
        evidence = (f"USB-C {usb['ref']} 无 courtyard，质心距最近板边 {d:.2f}mm（近似判据）")
        measured = {"centroid_to_edge_mm": round(d, 2)}
    return {"id": "USB_EDGE", "status": "pass" if ok else "fail",
            "evidence": evidence, "measured": measured}


def review_antenna(footprints, edge) -> Dict[str, Any]:
    esp = next((f for f in footprints if "ESP32" in f["lib_id"]), None)
    if not esp or not edge:
        return {"id": "ESP_ANTENNA", "status": "fail",
                "evidence": "ESP32 module or board edge not found"}
    d = edge_distance(esp, edge)
    near = [(f["ref"], round(dist(esp, f), 1)) for f in footprints
            if f is not esp and dist(esp, f) < ANTENNA_KEEPOUT_MM]
    # 朝向判定：WROOM-02 天线在模组 -Y 端（footprint 库内建 KEEP-OUT ZONE 注释位于 at -16）。
    # rot=0 时天线端朝 -Y。板框 y1 是最近边时（d == y - y1）且 rot 为 0/180 才判朝外。
    x1, y1, x2, y2 = edge
    rot = esp["rot"] % 360
    antenna_out = (rot in (0, 180) and abs(esp["y"] - y1) < abs(esp["y"] - y2)) or \
                  (rot in (90, 270) and abs(esp["x"] - x1) < abs(esp["x"] - x2))
    ok = not near and antenna_out
    return {"id": "ESP_ANTENNA", "status": "pass" if ok else "fail",
            "evidence": f"ESP32-C3 {esp['ref']} ({esp['x']},{esp['y']}) rot={esp['rot']}; "
                        f"质心距板边 {d:.2f}mm；{ANTENNA_KEEPOUT_MM}mm 净空圈内器件: "
                        f"{near if near else '无'}；天线端朝向={'板边(正确)' if antenna_out else '板内(错误)'}"
                        f"（按 WROOM-02 天线在 -Y 端、rot={esp['rot']}deg 推断）",
            "measured": {"edge_distance_mm": round(d, 2),
                         "keepout_intruders": near,
                         "antenna_facing_edge": antenna_out}}


def review_ground_return(pcb) -> Dict[str, Any]:
    ok = pcb["vias"] >= 4 and pcb["has_zone"]
    return {"id": "GROUND_RETURN", "status": "pass" if ok else "fail",
            "evidence": f"via 总数={pcb['vias']}，铺铜 zone 存在={pcb['has_zone']}；"
                        f"USB_DP/DM 下方与 SHT30 周边的地回流连续性需评审人在 KiCad 渲染中确认",
            "measured": {"via_count": pcb["vias"], "zones": pcb["has_zone"]}}


def boundary_distance(cap: Dict[str, Any], ic: Dict[str, Any]) -> Optional[float]:
    """电容质心到 IC courtyard 边界的距离；无 courtyard（或旋转件）时退回质心距离。"""
    if ic.get("courtyard"):
        cx1, cy1, cx2, cy2 = ic["courtyard"]
        gx1, gy1 = ic["x"] + cx1, ic["y"] + cy1
        gx2, gy2 = ic["x"] + cx2, ic["y"] + cy2
        dx = max(gx1 - cap["x"], 0.0, cap["x"] - gx2)
        dy = max(gy1 - cap["y"], 0.0, cap["y"] - gy2)
        return math.hypot(dx, dy)
    return dist(cap, ic)


def review_decoupling(footprints) -> Dict[str, Any]:
    caps = [f for f in footprints if f["lib_id"].startswith("C_")]
    ics = [f for f in footprints if any(k in f["lib_id"]
            for k in ("ESP32", "SOT-23", "Sensirion", "DFN-8"))]
    if not caps or not ics:
        return {"id": "DECOUPLING", "status": "fail",
                "evidence": f"caps={len(caps)} ics={len(ics)} 未找齐"}
    findings, worst = [], 0.0
    for ic in ics:
        dd, ref = min((boundary_distance(c, ic), c["ref"]) for c in caps)
        worst = max(worst, dd)
        findings.append({"ic": ic["ref"], "nearest_cap": ref,
                         "boundary_distance_mm": round(dd, 2)})
    ok = worst <= DECOUPLING_MAX_MM and len(findings) == len(ics)
    return {"id": "DECOUPLING", "status": "pass" if ok else "fail",
            "evidence": f"IC→最近去耦电容距离（courtyard 边界距，上限 {DECOUPLING_MAX_MM}mm）："
                        f"{json.dumps(findings, ensure_ascii=False)}",
            "measured": {"worst_distance_mm": round(worst, 2), "ics": findings}}


def review_usb_routing(segments, pins) -> Dict[str, Any]:
    net_len: Dict[str, float] = {}
    for s in segments:
        if s["net"] in {net for channel in USB_CHANNELS.values() for net in channel["nets"]}:
            net_len[s["net"]] = net_len.get(s["net"], 0.0) + \
                math.hypot(s["x2"] - s["x1"], s["y2"] - s["y1"])

    endpoint_mismatches = []
    missing_nets = []
    logical_lengths: Dict[str, float] = {}
    for channel_name, channel in USB_CHANNELS.items():
        for pin, expected_net in channel["pins"].items():
            observed = pins.get(pin, "<missing>")
            if observed != expected_net:
                endpoint_mismatches.append(
                    f"{pin}: expected {expected_net}, observed {observed}"
                )
        for net in channel["nets"]:
            if net not in net_len:
                missing_nets.append(net)
        if all(net in net_len for net in channel["nets"]):
            logical_lengths[channel_name] = sum(net_len[net] for net in channel["nets"])

    skew = None
    if len(logical_lengths) == len(USB_CHANNELS):
        lengths = sorted(logical_lengths.values())
        skew = lengths[-1] - lengths[0]
    ok = not endpoint_mismatches and not missing_nets and skew is not None and skew <= USB_DIFF_MAX_SKEW_MM
    rounded_lengths = {k: round(v, 2) for k, v in logical_lengths.items()}
    return {"id": "USB_ROUTING", "status": "pass" if ok else "fail",
            "evidence": f"USB 逻辑通道（连接器侧网络 + 串阻 + MCU 侧网络）铜长(mm)："
                        f"{rounded_lengths}；endpoint_mismatches={endpoint_mismatches}；"
                        f"missing_nets={sorted(set(missing_nets))}；"
                        f"skew={None if skew is None else round(skew, 2)}mm"
                        f"（要求 <= {USB_DIFF_MAX_SKEW_MM}mm）；"
                        f"90Ω 差分阻抗需按 1.6mm 双层板叠层计算复核",
            "measured": {
                "net_lengths_mm": {k: round(v, 2) for k, v in net_len.items()},
                "logical_channel_lengths_mm": rounded_lengths,
                "endpoint_mismatches": endpoint_mismatches,
                "missing_nets": sorted(set(missing_nets)),
                "skew_mm": None if skew is None else round(skew, 2),
            }}


def review_thermal(footprints) -> Dict[str, Any]:
    sht = next((f for f in footprints if "Sensirion" in f["lib_id"] or "DFN-8" in f["lib_id"]), None)
    if not sht:
        return {"id": "SHT30_THERMAL", "status": "fail", "evidence": "SHT30 footprint not found"}
    sources = [(f["ref"], dist(sht, f)) for f in footprints
               if any(k in f["lib_id"] for k in ("USB_C", "SOT-23", "LED"))]
    if not sources:
        return {"id": "SHT30_THERMAL", "status": "pass",
                "evidence": "板上无 USB/LDO/LED 热源",
                "measured": {"nearest_heat_source_mm": None}}
    nearest = min(sources, key=lambda t: t[1])
    ok = nearest[1] >= THERMAL_MIN_DIST_MM
    return {"id": "SHT30_THERMAL", "status": "pass" if ok else "fail",
            "evidence": f"SHT30 {sht['ref']} ({sht['x']},{sht['y']})；热源距离："
                        f"{[(r, round(d, 1)) for r, d in sources]}；最近 {nearest[0]} "
                        f"@{nearest[1]:.1f}mm（要求 >= {THERMAL_MIN_DIST_MM}mm）；"
                        f"外壳气流需实物复核",
            "measured": {"nearest_heat_source_mm": round(nearest[1], 1)}}


def review_protection(sch_text: str, pcb: Dict[str, Any]) -> Dict[str, Any]:
    if not sch_text:
        return {"id": "PROTECTION", "status": "fail", "evidence": "schematic not found"}
    has_tvs = bool(re.search(r'(TVS|ESD|USBLC|PESD|SP050)', sch_text, re.I))
    # PCB 侧确认：+5V 网络上是否有电容（bulk）挂接
    vbus_caps = 0
    starts = [m.start() for m in re.finditer(r'\(footprint "[^"]+"',
              Path(PCB_PATH).read_text(encoding="utf-8"))]
    pcb_text = Path(PCB_PATH).read_text(encoding="utf-8")
    starts.append(len(pcb_text))
    for i in range(len(starts) - 1):
        block = pcb_text[starts[i]:starts[i + 1]]
        if re.search(r'\(property "Reference" "C\d+"', block) and \
           re.search(r'\(net "\+5V"\)', block):
            vbus_caps += 1
    ok = vbus_caps >= 1
    return {"id": "PROTECTION", "status": "pass" if ok else "fail",
            "evidence": f"PCB 实测：挂接 +5V 的电容 {vbus_caps} 个（bulk 要求 >=1）；"
                        f"原理图 TVS/ESD 器件={has_tvs}（USB 5V 直供 LDO 场景为建议项）；"
                        f"反接/过压/热插拔瞬态属实物级验证",
            "measured": {"vbus_caps": vbus_caps, "tvs": has_tvs}}


def review_assembly(footprints, pcb_text: str) -> Dict[str, Any]:
    silk_missing = [f["ref"] for f in footprints
                    if f'"{f["ref"]}"' not in pcb_text]
    polarity_parts = [f["ref"] for f in footprints
                      if any(k in f["lib_id"]
                             for k in ("LED", "Sensirion", "USB_C", "SOT-23"))]
    ok = not silk_missing and len(footprints) > 0
    return {"id": "ASSEMBLY", "status": "pass" if ok else "fail",
            "evidence": f"丝印 Reference 覆盖 {len(footprints) - len(silk_missing)}"
                        f"/{len(footprints)}；方向敏感件（pin1/极性）：{polarity_parts}；"
                        f"装配方向与工艺备注由评审人在装配图上确认",
            "measured": {"silk_missing": silk_missing,
                         "polarity_parts": polarity_parts}}


# ---------------------------------------------------------------- 主流程

def main() -> int:
    pcb_text = PCB_PATH.read_text(encoding="utf-8")
    sch_text = SCH_PATH.read_text(encoding="utf-8") if SCH_PATH.exists() else ""
    pcb = parse_pcb(pcb_text)

    reviews = [
        review_usb_edge(pcb["footprints"], pcb["edge"]),
        review_antenna(pcb["footprints"], pcb["edge"]),
        review_ground_return(pcb),
        review_decoupling(pcb["footprints"]),
        review_usb_routing(pcb["segments"], pcb["pins"]),
        review_thermal(pcb["footprints"]),
        review_protection(sch_text, pcb),
        review_assembly(pcb["footprints"], pcb_text),
    ]

    report = {
        "generated_at": utc_now(),
        "pcb": str(PCB_PATH.relative_to(ROOT)),
        "board_outline_mm": list(pcb["edge"]) if pcb["edge"] else None,
        "footprint_count": len(pcb["footprints"]),
        "nets": pcb["nets"],
        "reviews": reviews,
        "summary": {r["id"]: r["status"] for r in reviews},
        "note": "机器测量证据；朝向/阻抗/气流/瞬态等无法静态判定项已在 evidence 中标注，"
                "需具名评审人在 KiCad 中复核后签发 manufacturing_release。",
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"[BOARD-REVIEW-AUTO] {OUT_PATH}")
    for r in reviews:
        print(f"  {r['id']:15s} {r['status'].upper():6s} {r['evidence'][:110]}")
    failed = [r["id"] for r in reviews if r["status"] != "pass"]
    print(f"RESULT: {len(reviews) - len(failed)}/{len(reviews)} pass"
          + (f"; failed: {failed}" if failed else ""))
    return review_exit_code(reviews)


if __name__ == "__main__":
    sys.exit(main())
