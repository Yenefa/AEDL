# -*- coding: utf-8 -*-
"""build_board.py v2 — M2-7b：intent 建板 + 自动排布（按实测封装尺寸装箱）。

改进 v1 的三个结构性问题：
1. 手工坐标导致 courtyard 重叠 → 改为按实测 bbox 的货架式自动装箱
2. 板级最小约束与网络类不一致 → 同步 DS 最小值
3. 板框过小 → 60x40
"""
import argparse
import json
import os
from pathlib import Path
import sys

FP_MAP = {
    "U1": ("RF_Module", "ESP32-C3-WROOM-02"),
    "U2": ("Sensor_Humidity", "Sensirion_DFN-8-1EP_2.5x2.5mm_P0.5mm_EP1.1x1.7mm"),
    # U3 换料 C82942 -> C235316（ME6211C33R5G）后封装为 SOT-353，不是换料前的
    # SOT-23-5。此表若与 intent_v1.json 不一致，重建会把旧封装带回来——
    # tests/test_build_board_footprints.py 对全部 intent 已声明封装做回归。
    "U3": ("Package_TO_SOT_SMD", "SOT-353"),
    "J1": ("Connector_USB", "USB_C_Receptacle_HRO_TYPE-C-31-M-12"),
    "SW1": ("Button_Switch_SMD", "SW_SPST_TS-1088-xR020"),
    "SW2": ("Button_Switch_SMD", "SW_SPST_TS-1088-xR020"),
    "D1": ("LED_SMD", "LED_0603_1608Metric"),
    "R1": ("Resistor_SMD", "R_0603_1608Metric"),
    "R2": ("Resistor_SMD", "R_0603_1608Metric"),
    "R3": ("Resistor_SMD", "R_0603_1608Metric"),
    "R4": ("Resistor_SMD", "R_0603_1608Metric"),
    "R5": ("Resistor_SMD", "R_0603_1608Metric"),
    "R6": ("Resistor_SMD", "R_0603_1608Metric"),
    "R7": ("Resistor_SMD", "R_0603_1608Metric"),
    "R8": ("Resistor_SMD", "R_0603_1608Metric"),
    "R9": ("Resistor_SMD", "R_0603_1608Metric"),
    "C1": ("Capacitor_SMD", "C_0805_2012Metric"),
    "C2": ("Capacitor_SMD", "C_0805_2012Metric"),
    "C3": ("Capacitor_SMD", "C_0603_1608Metric"),
    "C4": ("Capacitor_SMD", "C_0603_1608Metric"),
    "C5": ("Capacitor_SMD", "C_0603_1608Metric"),
}

# 布局 v2 — 功能布局覆盖表（质心 mm，rot 度）。
# v1 纯面积装箱导致三类板级评审 FAIL（见 notes/m2-evidence-reset/generated/board_review_auto.json）：
#   1) J1 未贴板边（USB_EDGE）      → J1 贴上边（y=3.75 ≈ 连接器深度 7.45mm 之半）
#   2) 去耦电容远离 IC（DECOUPLING）→ C1→U3 入口 / C2→U3 出口 / C3→U1 / C4→U2 就近
#   3) SHT30 距 LDO 5.3mm（THERMAL）→ U2 独占左下角，距 U3/J1/D1 均 >=30mm
# 另：U1 天线端（-Y）朝上板边且 7.5mm 净空圈内无器件（ESP_ANTENNA）。
PLACEMENT = {
    "J1": (45.0, 5.3, 0),     # USB-C 贴上板边：courtyard 前沿距边 0.55mm，舌片焊盘顶距边 0.53mm（>=0.5 DRC 约束）
    "U1": (12.0, 18.0, 0),    # ESP32 天线朝上（最近边），左侧
    "U3": (54.0, 13.0, 0),    # LDO 右上，J1 下方
    "C1": (54.0, 8.5, 0),     # +5V bulk，U3 入口旁
    "C2": (49.0, 13.0, 0),    # +3V3 bulk，U3 出口旁
    "C3": (23.5, 12.0, 0),    # U1 电源去耦，贴 U1 右边界
    "U2": (10.0, 35.0, 0),    # SHT30 左下角，远离热源
    "C4": (14.0, 35.0, 0),    # U2 去耦旁
    "R5": (40.0, 11.5, 0),    # CC1 下拉，J1 下方（避开 J1 courtyard）
    "R6": (44.0, 11.5, 0),    # CC2 下拉，J1 下方
    "R3": (23.5, 26.0, 0),    # EN 上拉，U1 右侧
    "C5": (1.45, 13.5, 90),   # EN RC 电容，旋转后位于 U1 左侧 courtyard 外
    "R7": (23.3, 18.0, 180),  # USB D+ 串阻，R7.2 朝向 U1.14
    "R8": (23.3, 19.5, 180),  # USB D- 串阻，R8.2 朝向 U1.13
    "R9": (1.45, 22.5, 90),   # GPIO9/BOOT 上拉，旋转后位于 U1 左侧 courtyard 外
    "R1": (23.0, 31.0, 0),    # I2C SDA 上拉，U1/U2 之间
    "R2": (23.0, 34.0, 0),    # I2C SCL 上拉
    "SW1": (29.0, 33.0, 0),   # EN 按键
    "SW2": (37.0, 36.0, 0),   # BOOT 按键
    "R4": (38.0, 26.0, 0),    # LED 限流
    "D1": (44.0, 26.0, 0),    # LED
}

# 自动布线后仍必须满足丝印 DRC；以下为绝对板坐标，避免默认字段落在相邻焊盘或板边。
REFERENCE_PLACEMENT = {
    "C5": (1.45, 10.0, 90),
    "R7": (23.3, 16.2, 0),
    "R9": (1.45, 27.0, 90),
    "U1": (12.0, 27.0, 0),
}

W, H = 60.0, 40.0
MARGIN = 3.0
GAP = 1.5


def resolve_root(root_arg):
    """Resolve an override or derive the repository root from this script."""
    if root_arg:
        return Path(root_arg).resolve()
    return Path(__file__).resolve().parents[1]


def resolve_footprint_root(override):
    if override:
        return Path(override).resolve()
    configured = os.environ.get("KICAD10_FOOTPRINT_DIR")
    if configured:
        return Path(configured).resolve()
    symbol_dir = os.environ.get("KICAD10_SYMBOL_DIR")
    if symbol_dir:
        return (Path(symbol_dir).resolve().parent / "footprints")
    raise ValueError("KiCad footprint root unavailable; use --footprint-root")


def physical_components(components):
    """Return intent components that require PCB footprints."""
    return {
        ref: component
        for ref, component in components.items()
        if not component.get("virtual", False)
    }


def apply_reference_placement(loaded, pcbnew):
    """Apply the audited absolute silkscreen reference positions."""
    missing = sorted(set(REFERENCE_PLACEMENT) - set(loaded))
    if missing:
        raise ValueError(f"reference placement targets missing from board: {missing}")
    for ref, (ref_x, ref_y, ref_angle) in REFERENCE_PLACEMENT.items():
        reference = loaded[ref].Reference()
        reference.SetPosition(
            pcbnew.VECTOR2I(pcbnew.FromMM(ref_x), pcbnew.FromMM(ref_y))
        )
        reference.SetTextAngleDegrees(ref_angle)


def fp_bbox_mm(fp, pcbnew):
    """实测封装外廓（优先 Courtyard，退回 BoundingBox），返回 (w,h)。"""
    try:
        crty = fp.GetCourtyard(pcbnew.F_CrtYd)
        bb = crty.BBox()
        if bb.GetWidth() > 0:
            return pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())
    except Exception:
        pass
    bb = fp.GetBoundingBox()
    return pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root")
    parser.add_argument("--footprint-root")
    parser.add_argument(
        "--references-only",
        action="store_true",
        help="update audited silkscreen reference positions on the existing routed PCB",
    )
    args = parser.parse_args(argv)

    root = resolve_root(args.root)
    footprint_root = resolve_footprint_root(args.footprint_root)
    intent_path = root / "src" / "hardware" / "m2-board" / "intent_v1.json"
    output_path = root / "src" / "hardware" / "m2-board" / "m2_board.kicad_pcb"

    import pcbnew

    if args.references_only:
        if not output_path.is_file():
            raise FileNotFoundError(f"existing PCB not found: {output_path}")
        board = pcbnew.LoadBoard(str(output_path))
        existing = {fp.GetReference(): fp for fp in board.GetFootprints()}
        apply_reference_placement(existing, pcbnew)
        ok = pcbnew.SaveBoard(str(output_path), board)
        print(f"references_only_saved={ok} targets={len(REFERENCE_PLACEMENT)}")
        return 0 if ok else 5

    with intent_path.open("r", encoding="utf-8-sig") as handle:
        intent = json.load(handle)

    board = pcbnew.BOARD()

    nc = board.GetDesignSettings().m_NetSettings.GetDefaultNetclass()
    TRACK, CLR, VIA_D, VIA_DRILL = 0.2, 0.18, 0.6, 0.3
    MIN_TRACK = 0.15
    MIN_DRILL = 0.2
    MIN_VIA_D = 0.4  # 舌片 0.5mm 节距走廊放不下 0.6 过孔，允许 0.4/0.2 小过孔
    nc.SetTrackWidth(pcbnew.FromMM(TRACK))
    nc.SetClearance(pcbnew.FromMM(CLR))
    nc.SetViaDiameter(pcbnew.FromMM(VIA_D))
    nc.SetViaDrill(pcbnew.FromMM(VIA_DRILL))

    # 板级硬下限与网络类同步（属性名按版本容错）
    ds = board.GetDesignSettings()
    for attr, val in (
        ("m_TrackMinWidth", MIN_TRACK),
        ("m_MinThroughDrill", MIN_DRILL),
        ("m_MinClearance", CLR),
        ("m_ViasMinSize", MIN_VIA_D),
        ("m_ViasMinDrill", MIN_DRILL),
    ):
        if hasattr(ds, attr):
            try:
                setattr(ds, attr, pcbnew.FromMM(val))
            except Exception as e:
                print(f"WARN setattr {attr}: {e}")
        else:
            print(f"WARN ds has no {attr}")

    net_items = {}
    for net in intent["nets"]:
        item = pcbnew.NETINFO_ITEM(board, net)
        board.Add(item)
        net_items[net] = item

    # 先加载全部封装，测尺寸，按面积降序装箱
    loaded = {}
    sizes = {}
    for ref, comp in physical_components(intent["components"]).items():
        lib, name = FP_MAP[ref]
        fp = pcbnew.FootprintLoad(str(footprint_root / (lib + ".pretty")), name)
        if fp is None:
            raise RuntimeError(f"footprint not found: {lib}:{name}")
        fp.SetReference(ref)
        fp.SetValue(comp.get("value", ""))
        loaded[ref] = fp
        sizes[ref] = fp_bbox_mm(fp, pcbnew)

    order = sorted(sizes, key=lambda r: -(sizes[r][0] * sizes[r][1]))

    # 布局 v2：PLACEMENT 覆盖的器件用功能位（rot 全为 0）；其余回退货架装箱
    pos_mm = {}
    for ref in order:
        if ref in PLACEMENT:
            cx, cy, rotation = PLACEMENT[ref]
            pos_mm[ref] = (cx, cy)
            loaded[ref].SetOrientationDegrees(rotation)
            loaded[ref].SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(cx), pcbnew.FromMM(cy)))
            board.Add(loaded[ref])

    x = MARGIN
    y = MARGIN
    row_h = 0.0
    for ref in order:
        if ref in PLACEMENT:
            continue  # 已按功能位放置
        w, h = sizes[ref]
        if x + w > W - MARGIN:
            x = MARGIN
            y += row_h + GAP
            row_h = 0.0
        cx = x + w / 2.0
        cy = y + h / 2.0
        pos_mm[ref] = (cx, cy)
        loaded[ref].SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(cx), pcbnew.FromMM(cy)))
        board.Add(loaded[ref])
        x += w + GAP
        row_h = max(row_h, h)

    apply_reference_placement(loaded, pcbnew)

    assigned, unmatched = 0, []
    for net, members in intent["nets"].items():
        for member in members:
            ref, pin = member.split(".", 1)
            if ref not in loaded and intent["components"].get(ref, {}).get("virtual", False):
                continue
            if ref not in loaded:
                unmatched.append(member)
                continue
            hits = [pd for pd in loaded[ref].Pads() if pd.GetNumber() == pin]
            if not hits:
                unmatched.append(member)
                continue
            for pad in hits:
                pad.SetNet(net_items[net])
                assigned += 1

    floating = sum(
        1 for fp in loaded.values() for pad in fp.Pads() if not pad.GetNetname()
    )

    # J1 手工扇出：0.5mm 舌片节距下 freerouting 无法自行逃逸的焊盘。
    # 几何依据（J1@45,5.3，舌片焊盘底边 y=1.98，定位 NPTH @ (42.11/47.89, 2.7) r=0.325，
    # 孔-铜净距约束 0.25 → 走线中心距孔心 >= 0.65）：
    #   A6(USB_DP_CONN)/A7(USB_DM_CONN) 直下即可（相邻逃逸柱中心距 0.5，净距 0.3 >= 0.18）；
    #   A9(+5V) 与右 NPTH 水平距仅 0.65 → 0.15mm 细线贴净空边缘下钻 B.Cu 后交给 freerouting；
    #   B5(CC2) 过孔 (46.45, 3.15) 避开 A9 走廊与 USB_DP 汇合横线（净距 >=0.48）。
    # 2026-08-29 实测（freerouting 日志）：fanout 阶段 61 个 SMD 焊盘仅 A7 逃逸失败
    # → USB_DM 永久未连接，必须手工补对称逃逸柱；+5V 深回廊 (44.6,12.81) 是按
    # 历史布线主流硬编码的，重建后堵死 C1-1 接入通道（via→C1-1 unrouted）→ 删除。
    def fanout(net_name, pts, layer, width):
        net = net_items[net_name]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            tr = pcbnew.PCB_TRACK(board)
            tr.SetNet(net)
            tr.SetLayer(layer)
            tr.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
            tr.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
            tr.SetWidth(pcbnew.FromMM(width))
            board.Add(tr)

    def fanout_via(net_name, x, y, size=0.6, drill=0.3):
        v = pcbnew.PCB_VIA(board)
        v.SetNet(net_items[net_name])
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        v.SetWidth(pcbnew.FromMM(size))
        v.SetDrill(pcbnew.FromMM(drill))
        board.Add(v)

    # USB 差分对四焊盘交错（B7/DM=44.25, A6/DP=44.75, A7/DM=45.25, B6/DP=45.75，
    # 全 F.Cu、0.5mm 节距）：0.6mm 过孔需与相邻走线中心距 >=0.58，走廊里放不下
    # → DM 两焊盘就近下 0.4/0.2 小过孔（环宽 0.1/孔径 0.2 = 约束下限）转 B.Cu 汇合；
    #   DP 在 F.Cu 于 y=2.8 汇合（A7 过孔底缘 y=2.5，净距 0.2）后中柱下行。
    fanout("USB_DM_CONN", [(44.25, 1.9), (44.25, 2.3)], pcbnew.F_Cu, 0.2)
    fanout_via("USB_DM_CONN", 44.25, 2.3, 0.4, 0.2)
    fanout("USB_DM_CONN", [(45.25, 1.9), (45.25, 2.3)], pcbnew.F_Cu, 0.2)
    fanout_via("USB_DM_CONN", 45.25, 2.3, 0.4, 0.2)
    # B.Cu 两小过孔直连（中心距 1.0，边缘净距 0.6），无悬空端；逃逸由 freerouting 从过孔续接
    fanout("USB_DM_CONN", [(44.25, 2.3), (45.25, 2.3)], pcbnew.B_Cu, 0.2)

    fanout("USB_DP_CONN", [(44.75, 1.9), (44.75, 2.8)], pcbnew.F_Cu, 0.2)
    fanout("USB_DP_CONN", [(45.75, 1.9), (45.75, 2.8)], pcbnew.F_Cu, 0.2)
    fanout("USB_DP_CONN", [(44.75, 2.8), (45.25, 2.8), (45.25, 5.2)], pcbnew.F_Cu, 0.2)
    fanout("USB_DP_CONN", [(45.75, 2.8), (45.25, 2.8)], pcbnew.F_Cu, 0.2)
    fanout_via("USB_DP_CONN", 45.25, 5.2)

    # A9/B4 +5V：贴 NPTH 净空边缘下钻 B.Cu，后续交给 freerouting
    fanout("+5V", [(47.2, 1.9), (47.2, 3.6)], pcbnew.F_Cu, 0.15)
    fanout_via("+5V", 47.2, 3.6)

    # B5 CC2：过孔置于 USB_DP 汇合横线与 +5V 逃逸柱之间
    #   (46.45,3.15) 距 DP 横线端点 (45.75,2.8) 0.78、距 +5V 过孔 (47.2,3.6) 0.87（均 >=0.58/0.78）
    fanout("CC2", [(46.75, 1.9), (46.75, 2.3), (46.45, 3.15)], pcbnew.F_Cu, 0.2)
    fanout_via("CC2", 46.45, 3.15)
    fanout("CC2", [(46.45, 3.15), (46.45, 4.4)], pcbnew.B_Cu, 0.2)

    # J1 Reference 丝印默认在封装外上方 rel(0,-5.645)，贴边放置会超出板外 → 移到左侧板内
    j1_ref = loaded["J1"].Reference()
    try:
        j1_ref.SetPos0(pcbnew.VECTOR2I(pcbnew.FromMM(-6.3), pcbnew.FromMM(0.0)))
    except Exception:
        j1_ref.SetPosition(
            pcbnew.VECTOR2I(pcbnew.FromMM(45.0 - 6.3), pcbnew.FromMM(5.3))
        )

    def seg(x1, y1, x2, y2):
        sh = pcbnew.PCB_SHAPE(board)
        sh.SetShape(pcbnew.SHAPE_T_SEGMENT)
        sh.SetLayer(pcbnew.Edge_Cuts)
        sh.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        sh.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        sh.SetWidth(pcbnew.FromMM(0.1))
        board.Add(sh)

    seg(0, 0, W, 0); seg(W, 0, W, H); seg(W, H, 0, H); seg(0, H, 0, 0)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    ok = pcbnew.SaveBoard(str(output_path), board)
    print(f"saved={ok} board={W}x{H}mm")
    print("positions:")
    for ref in sorted(pos_mm):
        print(f"  {ref:>4} @ ({pos_mm[ref][0]:.1f},{pos_mm[ref][1]:.1f}) size={sizes[ref][0]:.1f}x{sizes[ref][1]:.1f}")
    print(f"components={len(loaded)} pads_assigned={assigned} unmatched={len(unmatched)} floating={floating}")
    if unmatched:
        print("UNMATCHED:", unmatched)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
