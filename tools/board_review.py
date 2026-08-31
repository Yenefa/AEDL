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

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # 允许 `py tools/board_review.py` 直接运行
    sys.path.insert(0, str(ROOT))

# 评审合同单一真源在 gates.gate_core（BOARD_REVIEW_ALGORITHM_CONTRACT）：
# 角色集/阈值/算法修订号都在那里定义，报告生成端与门禁校验端永不漂移。
# 改动任何一项都会改变 BOARD_REVIEW_ALGORITHM_REVISION，门禁随即失败关闭
# 所有旧算法产出的报告，防止人工重签哈希时把旧算法证据当成当前算法证据
# 钉进制造签发。
from gates.gate_core import (  # noqa: E402
    ANTENNA_KEEPOUT_MM,
    ANTENNA_MODULE_REF,
    BOARD_REVIEW_ALGORITHM_REVISION,
    DECOUPLING_MAX_MM,
    EXPECTED_IC_REFS,
    HEAT_SOURCE_REFS,
    POLARITY_REFS,
    POWER_NET_PREFIX,
    SENSOR_REF,
    THERMAL_MIN_DIST_MM,
    USB_DIFF_MAX_SKEW_MM,
    USB_EDGE_MAX_MM,
)

ALGORITHM_REVISION = BOARD_REVIEW_ALGORITHM_REVISION  # 报告里的算法修订号

PCB_PATH = ROOT / "src" / "hardware" / "m2-board" / "m2_board.kicad_pcb"
SCH_PATH = ROOT / "src" / "hardware" / "m2-board" / "m2_board.kicad_sch"
OUT_PATH = ROOT / "notes" / "m2-evidence-reset" / "generated" / "board_review_auto.json"

# 目检渲染图固定输出（3D 视图，1600x900 high；约 12-13s/张，低频工具可接受）
RENDER_TARGETS = (("top", "board_top.png"), ("bottom", "board_bottom.png"))
RENDER_WIDTH, RENDER_HEIGHT = 1600, 900

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

# 评审对象一律按预期 ref 认定——禁止用封装/库名关键字识别器件：
# 换封装（如 U3 的 SOT-353 → SC-70-5）或改库名都不得让检查项静默消失；
# 板上缺了预期 ref 必须失败关闭，而不是缩小检查范围继续"通过"。


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
        # courtyard：F.CrtYd 端点按文件旋转角变换（KiCad 旋转：x'=x·cosθ−y·sinθ,
        # y'=x·sinθ+y·cosθ）后取包络。旋转件不得静默丢掉 courtyard——
        # 无 courtyard 可测时保持 None，由评审侧失败关闭（不退回质心距）。
        rot_rad = math.radians(rot)
        cos_r, sin_r = math.cos(rot_rad), math.sin(rot_rad)
        cxs, cys = [], []
        for fm in re.finditer(
                r'\(fp_line\s*\(start (-?[\d.]+) (-?[\d.]+)\)\s*\(end (-?[\d.]+) (-?[\d.]+)\)'
                r'(?:(?!\(fp_line).)*?\(layer "F\.CrtYd"\)', block, re.S):
            for px, py in ((float(fm.group(1)), float(fm.group(2))),
                           (float(fm.group(3)), float(fm.group(4)))):
                cxs.append(px * cos_r - py * sin_r)
                cys.append(px * sin_r + py * cos_r)
        courtyard = None
        if cxs:
            courtyard = (min(cxs), min(cys), max(cxs), max(cys))
        # Reference 丝印属性：所在层 + 是否隐藏（装配评审只认 F.SilkS/B.SilkS 且未隐藏）
        ref_layer: Optional[str] = None
        ref_hidden = False
        next_prop = block.find("(property", ref_m.end())
        ref_scope = block[ref_m.start(): next_prop if next_prop != -1 else len(block)]
        layer_m = re.search(r'\(layer "([^"]+)"\)', ref_scope)
        if layer_m:
            ref_layer = layer_m.group(1)
        ref_hidden = bool(re.search(r'\(hide yes\)', ref_scope))
        footprints.append({
            "ref": ref_m.group(1), "lib_id": lib_id,
            "x": float(at_m.group(1)), "y": float(at_m.group(2)),
            "rot": rot, "courtyard": courtyard,
            "ref_layer": ref_layer, "ref_hidden": ref_hidden,
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

    # Bulk-capacitor count on +5V, computed here so review_protection stays a
    # pure function of its inputs instead of re-reading the global PCB_PATH.
    block_starts = [m.start() for m in re.finditer(r'\(footprint "[^"]+"', text)]
    block_starts.append(len(text))
    vbus_caps = 0
    for i in range(len(block_starts) - 1):
        block = text[block_starts[i]:block_starts[i + 1]]
        if re.search(r'\(property "Reference" "C\d+"', block) and \
           re.search(r'\(net "\+5V"\)', block):
            vbus_caps += 1

    return {"footprints": footprints, "edge": edge, "segments": segments,
            "vias": vias, "has_zone": has_zone, "nets": nets, "pins": pins,
            "vbus_caps": vbus_caps}


# ---------------------------------------------------------------- 评审项

def dist(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def edge_distance(fp: Dict[str, Any], edge: Tuple[float, ...]) -> float:
    """质心到最近板边的有符号间距：板内非负，板外为负。
    调用方必须先判定板内/板外（inside_edge），不得直接拿负值当距离用。"""
    x1, y1, x2, y2 = edge
    return min(fp["x"] - x1, x2 - fp["x"], fp["y"] - y1, y2 - fp["y"])


def inside_edge(x: float, y: float, edge: Tuple[float, ...]) -> bool:
    x1, y1, x2, y2 = edge
    return x1 <= x <= x2 and y1 <= y <= y2


def point_to_rect_distance(x: float, y: float, edge: Tuple[float, ...]) -> float:
    """点到板框矩形的非负距离（板内为 0，板外为到矩形边界的欧氏距离）。"""
    x1, y1, x2, y2 = edge
    dx = max(x1 - x, 0.0, x - x2)
    dy = max(y1 - y, 0.0, y - y2)
    return math.hypot(dx, dy)


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
        gx1, gy1 = usb["x"] + cx1, usb["y"] + cy1
        gx2, gy2 = usb["x"] + cx2, usb["y"] + cy2
        # 先判板框合法性：courtyard 包络任意边越界都失败关闭
        # （旧实现只看前沿 Y 距，横向/整体越界的连接器会静默 PASS）。
        over = [side for side, violated in (
            ("left", gx1 < x1), ("right", gx2 > x2),
            ("top", gy1 < y1), ("bottom", gy2 > y2)) if violated]
        if over:
            return {"id": "USB_EDGE", "status": "fail",
                    "evidence": (f"USB-C {usb['ref']} 质心 ({usb['x']},{usb['y']})，"
                                 f"courtyard 包络越出板框：{over}——布局不成立，失败关闭"),
                    "measured": {"courtyard_outside_outline": over}}
        front_y = gy1  # 壳体前沿（全局坐标）
        d = front_y - y1
        ok = 0 <= d <= USB_EDGE_MAX_MM
        evidence = (f"USB-C {usb['ref']} 质心 ({usb['x']},{usb['y']})，"
                    f"courtyard 前沿距上板边 {d:.2f}mm（板边贴装要求 0~{USB_EDGE_MAX_MM}mm）；"
                    f"外形/禁布区与外壳配合需评审人在 PCB 渲染中目检")
        measured = {"courtyard_front_to_edge_mm": round(d, 2)}
    elif inside_edge(usb["x"], usb["y"], edge):
        d = edge_distance(usb, edge)  # 板内必为非负
        ok = d <= USB_EDGE_MAX_MM
        evidence = (f"USB-C {usb['ref']} 无 courtyard，质心在板内、距最近板边 {d:.2f}mm（近似判据）")
        measured = {"centroid_to_edge_mm": round(d, 2)}
    else:
        d = point_to_rect_distance(usb["x"], usb["y"], edge)
        ok = False
        evidence = (f"USB-C {usb['ref']} 无 courtyard 且质心位于板框之外"
                    f"（出界距离 {d:.2f}mm）——布局不成立，失败关闭")
        measured = {"centroid_outside_outline_mm": round(d, 2)}
    return {"id": "USB_EDGE", "status": "pass" if ok else "fail",
            "evidence": evidence, "measured": measured}


def review_antenna(footprints, edge, module_ref: str = ANTENNA_MODULE_REF) -> Dict[str, Any]:
    esp = next((f for f in footprints if f["ref"] == module_ref), None)
    if not esp or not edge:
        return {"id": "ESP_ANTENNA", "status": "fail",
                "evidence": f"antenna module {module_ref} or board edge not found"}
    # 先判板内/板外：模组越出板框（任意边）布局不成立，失败关闭。
    # 旧实现拿板外为负的 edge_distance 继续判朝向，板外模组会静默 PASS。
    if not inside_edge(esp["x"], esp["y"], edge):
        d = point_to_rect_distance(esp["x"], esp["y"], edge)
        return {"id": "ESP_ANTENNA", "status": "fail",
                "evidence": (f"ESP32-C3 {esp['ref']} ({esp['x']},{esp['y']}) rot={esp['rot']}；"
                             f"质心位于板框之外（出界距离 {d:.2f}mm）——布局不成立，失败关闭"),
                "measured": {"edge_distance_mm": round(-d, 2),
                             "centroid_outside_outline_mm": round(d, 2),
                             "keepout_intruders": [],
                             "antenna_facing_edge": False}}
    d = edge_distance(esp, edge)
    near = [(f["ref"], round(dist(esp, f), 1)) for f in footprints
            if f is not esp and dist(esp, f) < ANTENNA_KEEPOUT_MM]
    # 朝向判定：WROOM-02 天线在模组本地 -Y 端，随文件旋转角变换到板坐标：
    # 方向向量 = (sinθ, -cosθ)。rot=0 朝 -Y（上）；rot=180 朝 +Y（下）——
    # （旧实现把 rot=0 与 rot=180 混为一谈，模组靠上板边且旋转 180° 时会误判朝外。）
    # 判据：沿天线方向到对应板边的距离 < 反方向到对面板边的距离，才判"朝外"；
    # 不能要求射线穿过"最近"板边——天线指向次近板边同样是合法朝外布局。
    x1, y1, x2, y2 = edge
    rot = esp["rot"] % 360
    theta = math.radians(rot)
    dx, dy = math.sin(theta), -math.cos(theta)

    def ray_exit(px, py, vx, vy) -> float:
        candidates = []
        if vx > 0:
            candidates.append((x2 - px) / vx)
        elif vx < 0:
            candidates.append((x1 - px) / vx)
        if vy > 0:
            candidates.append((y2 - py) / vy)
        elif vy < 0:
            candidates.append((y1 - py) / vy)
        return min(candidates) if candidates else float("inf")

    antenna_out = ray_exit(esp["x"], esp["y"], dx, dy) < \
        ray_exit(esp["x"], esp["y"], -dx, -dy)
    ok = not near and antenna_out
    return {"id": "ESP_ANTENNA", "status": "pass" if ok else "fail",
            "evidence": f"ESP32-C3 {esp['ref']} ({esp['x']},{esp['y']}) rot={esp['rot']}; "
                        f"质心距板边 {d:.2f}mm；{ANTENNA_KEEPOUT_MM}mm 净空圈内器件: "
                        f"{near if near else '无'}；天线端朝向={'板边(正确)' if antenna_out else '板内(错误)'}"
                        f"（按模组天线在本地 -Y 端、旋转后方向向量 ({dx:.2f},{dy:.2f}) 推断）",
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
    """电容质心到 IC courtyard 边界的距离。
    courtyard 缺失/不可测时返回 None——调用方必须失败关闭，
    禁止静默退化成质心距（那是更弱的判据，会把远电容读成近的）。"""
    if not ic.get("courtyard"):
        return None
    cx1, cy1, cx2, cy2 = ic["courtyard"]
    gx1, gy1 = ic["x"] + cx1, ic["y"] + cy1
    gx2, gy2 = ic["x"] + cx2, ic["y"] + cy2
    dx = max(gx1 - cap["x"], 0.0, cap["x"] - gx2)
    dy = max(gy1 - cap["y"], 0.0, cap["y"] - gy2)
    return math.hypot(dx, dy)


def review_decoupling(footprints, pins, expected_ics=EXPECTED_IC_REFS) -> Dict[str, Any]:
    """IC 按评审合同的预期 ref 集合认定（不认封装关键字）；
    电容必须与该 IC 共享至少一条电源网络才算它的去耦电容。"""
    by_ref = {f["ref"]: f for f in footprints}
    caps = [f for f in footprints if f["lib_id"].startswith("C_")]
    problems: List[str] = []
    if not caps:
        problems.append("板上没有任何电容")
    findings, worst = [], 0.0
    for ref in expected_ics:
        ic = by_ref.get(ref)
        if ic is None:
            problems.append(f"预期 IC {ref} 未在板上找到")
            continue
        ic_power_nets = {net for pad, net in pins.items()
                         if pad.startswith(ref + ".") and net and net.startswith(POWER_NET_PREFIX)}
        eligible = [c for c in caps
                    if any(net in ic_power_nets for pad, net in pins.items()
                           if pad.startswith(c["ref"] + ".") and net)]
        if not eligible:
            problems.append(
                f"{ref}: 没有共享其电源网络 {sorted(ic_power_nets) or '(未检出电源网络)'} 的电容"
                f"——任意无关电容不得冒充去耦电容")
            continue
        distances = [(boundary_distance(c, ic), c["ref"]) for c in eligible]
        if all(dd is None for dd, _ in distances):
            problems.append(f"{ref}: courtyard 缺失，边界距离不可测（失败关闭，不退质心距）")
            continue
        dd, nearest_cap = min((dd, ref_c) for dd, ref_c in distances if dd is not None)
        worst = max(worst, dd)
        findings.append({"ic": ref, "nearest_cap": nearest_cap,
                         "boundary_distance_mm": round(dd, 2)})
    ok = not problems and worst <= DECOUPLING_MAX_MM and len(findings) == len(expected_ics)
    return {"id": "DECOUPLING", "status": "pass" if ok else "fail",
            "evidence": f"预期 IC 角色集 {list(expected_ics)}；IC→最近去耦电容距离"
                        f"（courtyard 边界距，电容须与该 IC 共享电源网络，上限 {DECOUPLING_MAX_MM}mm）："
                        f"{json.dumps(findings, ensure_ascii=False)}"
                        + (f"；问题：{problems}" if problems else ""),
            "measured": {"worst_distance_mm": round(worst, 2), "ics": findings,
                         "problems": problems}}


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


def review_thermal(footprints, sensor_ref: str = SENSOR_REF,
                   heat_source_refs=HEAT_SOURCE_REFS) -> Dict[str, Any]:
    """传感器与热源均按评审合同的预期 ref 认定（不认封装关键字）；
    预期热源在板上缺失时失败关闭，而不是缩小热源集合继续"通过"。"""
    by_ref = {f["ref"]: f for f in footprints}
    sht = by_ref.get(sensor_ref)
    if not sht:
        return {"id": "SHT30_THERMAL", "status": "fail",
                "evidence": f"SHT30 {sensor_ref} footprint not found"}
    sources, problems = [], []
    for ref in heat_source_refs:
        f = by_ref.get(ref)
        if f is None:
            problems.append(f"预期热源 {ref} 未在板上找到")
        elif ref != sensor_ref:
            sources.append((ref, dist(sht, f)))
    if problems:
        return {"id": "SHT30_THERMAL", "status": "fail",
                "evidence": f"热源角色集不完整（失败关闭）：{problems}",
                "measured": {"nearest_heat_source_mm": None, "problems": problems}}
    if not sources:
        return {"id": "SHT30_THERMAL", "status": "pass",
                "evidence": "板上无 USB/LDO/LED 热源",
                "measured": {"nearest_heat_source_mm": None}}
    nearest = min(sources, key=lambda t: t[1])
    ok = nearest[1] >= THERMAL_MIN_DIST_MM
    return {"id": "SHT30_THERMAL", "status": "pass" if ok else "fail",
            "evidence": f"SHT30 {sht['ref']} ({sht['x']},{sht['y']})；热源角色集"
                        f"{list(heat_source_refs)} 距离："
                        f"{[(r, round(d, 1)) for r, d in sources]}；最近 {nearest[0]} "
                        f"@{nearest[1]:.1f}mm（要求 >= {THERMAL_MIN_DIST_MM}mm）；"
                        f"外壳气流需实物复核",
            "measured": {"nearest_heat_source_mm": round(nearest[1], 1)}}


def review_protection(sch_text: str, pcb: Dict[str, Any]) -> Dict[str, Any]:
    if not sch_text:
        return {"id": "PROTECTION", "status": "fail", "evidence": "schematic not found"}
    has_tvs = bool(re.search(r'(TVS|ESD|USBLC|PESD|SP050)', sch_text, re.I))
    # PCB 侧确认：+5V 网络上是否有电容（bulk）挂接。
    # 计数由 parse_pcb 完成（返回键 vbus_caps），这里只读入参、不再读文件——
    # 否则传入"另一块板"的 parse 结果时会静默返回错误板子的结论（见 TASK-P9 进度日志 bug-1）。
    vbus_caps = pcb.get("vbus_caps", 0)
    ok = vbus_caps >= 1
    return {"id": "PROTECTION", "status": "pass" if ok else "fail",
            "evidence": f"PCB 实测：挂接 +5V 的电容 {vbus_caps} 个（bulk 要求 >=1）；"
                        f"原理图 TVS/ESD 器件={has_tvs}（USB 5V 直供 LDO 场景为建议项）；"
                        f"反接/过压/热插拔瞬态属实物级验证",
            "measured": {"vbus_caps": vbus_caps, "tvs": has_tvs}}


def review_assembly(footprints, polarity_refs=POLARITY_REFS) -> Dict[str, Any]:
    """丝印检查逐件验证 Reference 属性：必须位于 F.SilkS/B.SilkS 且未隐藏
    （旧实现只做全局字符串搜索，属性被移层/隐藏/挪进其他对象都会漏判）。
    方向敏感件按评审合同的预期 ref 角色集认定（不认封装关键字）。"""
    by_ref = {f["ref"] for f in footprints}
    silk_missing = [f["ref"] for f in footprints
                    if f.get("ref_hidden")
                    or f.get("ref_layer") not in ("F.SilkS", "B.SilkS")]
    polarity_parts = [r for r in polarity_refs if r in by_ref]
    polarity_missing = [r for r in polarity_refs if r not in by_ref]
    ok = not silk_missing and not polarity_missing and len(footprints) > 0
    evidence = (f"丝印 Reference 覆盖（须位于 F.SilkS/B.SilkS 且未隐藏）"
                f"{len(footprints) - len(silk_missing)}/{len(footprints)}"
                + (f"；缺失/不合格: {silk_missing}" if silk_missing else "")
                + f"；方向敏感件（pin1/极性）：{polarity_parts}"
                + (f"；缺失方向敏感件：{polarity_missing}" if polarity_missing else "")
                + "；装配方向与工艺备注由评审人在装配图上确认")
    return {"id": "ASSEMBLY", "status": "pass" if ok else "fail",
            "evidence": evidence,
            "measured": {"silk_missing": silk_missing,
                         "polarity_parts": polarity_parts,
                         "polarity_missing": polarity_missing}}


# ---------------------------------------------------------------- 目检渲染（kicad-cli）

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_kicad_cli() -> Optional[Path]:
    """KICAD_CLI 环境变量 → PATH → 已知安装路径；找不到返回 None（渲染即 fail）。"""
    env_value = os.environ.get("KICAD_CLI")
    if env_value and Path(env_value).is_file():
        return Path(env_value).resolve()
    found = shutil.which("kicad-cli")
    if found:
        return Path(found).resolve()
    default = Path(r"C:\Users\fuker\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe")
    if default.is_file():
        return default
    return None


def render_board_views(kicad_cli: Path, pcb_path: Path, out_dir: Path) -> List[str]:
    """用 kicad-cli 重渲 top/bottom 目检图（覆盖旧图），返回错误列表（空=成功）。"""
    errors: List[str] = []
    for side, filename in RENDER_TARGETS:
        out_path = out_dir / filename
        command = [
            str(kicad_cli), "pcb", "render",
            "--side", side, "--quality", "high",
            "--width", str(RENDER_WIDTH), "--height", str(RENDER_HEIGHT),
            "-o", str(out_path), str(pcb_path),
        ]
        try:
            completed = subprocess.run(command, capture_output=True, timeout=180)
        except Exception as exc:
            errors.append(f"kicad-cli render {side} could not run: {type(exc).__name__}: {exc}")
            continue
        if completed.returncode != 0 or not out_path.is_file():
            stderr = (completed.stderr or b"").decode("utf-8", errors="replace")[-400:]
            errors.append(
                f"kicad-cli render {side} failed (exit {completed.returncode}): {stderr.strip()}"
            )
    return errors


# ---------------------------------------------------------------- 主流程

def main() -> int:
    pcb_text = PCB_PATH.read_text(encoding="utf-8")
    sch_text = SCH_PATH.read_text(encoding="utf-8") if SCH_PATH.exists() else ""
    pcb = parse_pcb(pcb_text)

    reviews = [
        review_usb_edge(pcb["footprints"], pcb["edge"]),
        review_antenna(pcb["footprints"], pcb["edge"]),
        review_ground_return(pcb),
        review_decoupling(pcb["footprints"], pcb["pins"]),
        review_usb_routing(pcb["segments"], pcb["pins"]),
        review_thermal(pcb["footprints"]),
        review_protection(sch_text, pcb),
        review_assembly(pcb["footprints"]),
    ]

    render_errors: List[str] = []
    kicad_cli = find_kicad_cli()
    if kicad_cli is None:
        render_errors.append(
            "kicad-cli not found; set KICAD_CLI or add KiCad to PATH "
            "(render evidence is mandatory for the board_review gate)"
        )
    else:
        print(f"[RENDER] {kicad_cli}")
        render_errors = render_board_views(kicad_cli, PCB_PATH, OUT_PATH.parent)

    report = {
        # Stable revision of the review algorithm itself. The gate refuses any
        # auto report whose revision differs, so a human re-signing hashes can
        # never pin evidence produced by an older (or unknown) algorithm.
        "algorithm_revision": ALGORITHM_REVISION,
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
    if not render_errors:
        report["render_evidence"] = {
            "pcb_sha256": sha256_file(PCB_PATH),
            "top_png_sha256": sha256_file(OUT_PATH.parent / "board_top.png"),
            "bottom_png_sha256": sha256_file(OUT_PATH.parent / "board_bottom.png"),
            "rendered_at": utc_now(),
        }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"[BOARD-REVIEW-AUTO] {OUT_PATH}")
    for r in reviews:
        print(f"  {r['id']:15s} {r['status'].upper():6s} {r['evidence'][:110]}")
    if render_errors:
        for message in render_errors:
            print(f"  RENDER FAIL     {message}")
        print("RESULT: render evidence missing; board_review gate will fail closed")
        return 1
    for _, filename in RENDER_TARGETS:
        print(f"  RENDER          {OUT_PATH.parent / filename}")
    failed = [r["id"] for r in reviews if r["status"] != "pass"]
    print(f"RESULT: {len(reviews) - len(failed)}/{len(reviews)} pass"
          + (f"; failed: {failed}" if failed else ""))
    return review_exit_code(reviews)


if __name__ == "__main__":
    sys.exit(main())
