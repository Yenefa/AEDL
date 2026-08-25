# -*- coding: utf-8 -*-
"""build_board.py v2 — M2-7b：intent 建板 + 自动排布（按实测封装尺寸装箱）。

改进 v1 的三个结构性问题：
1. 手工坐标导致 courtyard 重叠 → 改为按实测 bbox 的货架式自动装箱
2. 板级最小约束与网络类不一致 → 同步 DS 最小值
3. 板框过小 → 60x40
"""
import json
import os
import sys

import pcbnew

ROOT = r"C:\Users\fuker\Desktop\workspace\project-027-autonomous-hardware-agent"
FPDIR = r"C:\Users\fuker\AppData\Local\Programs\KiCad\10.0\share\kicad\footprints"
OUT = os.path.join(ROOT, r"src\hardware\m2-board\m2_board.kicad_pcb")

FP_MAP = {
    "U1": ("RF_Module", "ESP32-C3-WROOM-02"),
    "U2": ("Sensor_Humidity", "Sensirion_DFN-8-1EP_2.5x2.5mm_P0.5mm_EP1.1x1.7mm"),
    "U3": ("Package_TO_SOT_SMD", "SOT-23-5"),
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
    "C1": ("Capacitor_SMD", "C_0805_2012Metric"),
    "C2": ("Capacitor_SMD", "C_0805_2012Metric"),
    "C3": ("Capacitor_SMD", "C_0603_1608Metric"),
    "C4": ("Capacitor_SMD", "C_0603_1608Metric"),
}

W, H = 60.0, 40.0
MARGIN = 3.0
GAP = 1.5


def fp_bbox_mm(fp):
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


def main():
    intent = json.load(open(os.path.join(ROOT, r"src\hardware\m2-board\intent_v1.json"), encoding="utf-8"))

    board = pcbnew.BOARD()

    nc = board.GetDesignSettings().m_NetSettings.GetDefaultNetclass()
    TRACK, CLR, VIA_D, VIA_DRILL = 0.2, 0.18, 0.6, 0.3
    MIN_TRACK = 0.15
    MIN_DRILL = 0.2
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
        ("m_ViasMinSize", VIA_D),
        ("m_ViasMinDrill", VIA_DRILL),
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
    for ref, comp in intent["components"].items():
        lib, name = FP_MAP[ref]
        fp = pcbnew.FootprintLoad(os.path.join(FPDIR, lib + ".pretty"), name)
        if fp is None:
            raise RuntimeError(f"footprint not found: {lib}:{name}")
        fp.SetReference(ref)
        fp.SetValue(comp.get("value", ""))
        loaded[ref] = fp
        sizes[ref] = fp_bbox_mm(fp)

    order = sorted(sizes, key=lambda r: -(sizes[r][0] * sizes[r][1]))
    x = MARGIN
    y = MARGIN
    row_h = 0.0
    pos_mm = {}
    for ref in order:
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

    assigned, unmatched = 0, []
    for net, members in intent["nets"].items():
        for member in members:
            ref, pin = member.split(".", 1)
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

    def seg(x1, y1, x2, y2):
        sh = pcbnew.PCB_SHAPE(board)
        sh.SetShape(pcbnew.SHAPE_T_SEGMENT)
        sh.SetLayer(pcbnew.Edge_Cuts)
        sh.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        sh.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        sh.SetWidth(pcbnew.FromMM(0.1))
        board.Add(sh)

    seg(0, 0, W, 0); seg(W, 0, W, H); seg(W, H, 0, H); seg(0, H, 0, 0)

    ok = pcbnew.SaveBoard(OUT, board)
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
