# -*- coding: utf-8 -*-
"""生成 E5 exploratory 用的 CH340C USB 转串口原理图（KiCad 8 格式，KiCad 10 可读）。

两个变体共用同一套确定性 UUID（uuid5），因此两份文件的差异
应当恰好只有 U1 第 5、6 脚上两个标签的文字：

  --variant defect   USB D+/D- 与 CH340C 的 UD+/UD- 对调（DC-01 类缺陷）
  --variant correct  正确接法（参考答案）

连通性全部用本地网络标签实现（与 M2 原理图约定一致），不画导线。
坐标变换：图纸 = (X + px, Y - py)，库坐标 Y 朝上、图纸 Y 朝下。
"""
import argparse
import pathlib
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from symx import extract, pins  # noqa: E402

NS = uuid.UUID("6f0a2b7e-3c4d-4e5f-8a9b-0c1d2e3f4a5b")
ROOT = str(uuid.uuid5(NS, "root"))
PROJECT = "usb_serial_adapter"


def U(key):
    return str(uuid.uuid5(NS, key))


LIBS = {
    "Interface_USB:CH340C": ("Interface_USB.kicad_sym", "CH340C"),
    "Connector:USB_C_Receptacle_USB2.0_16P": ("Connector.kicad_sym", "USB_C_Receptacle_USB2.0_16P"),
    "Device:R": ("Device.kicad_sym", "R"),
    "Device:C": ("Device.kicad_sym", "C"),
    "Connector_Generic:Conn_01x04": ("Connector_Generic.kicad_sym", "Conn_01x04"),
    "power:PWR_FLAG": ("power.kicad_sym", "PWR_FLAG"),
}


def lib_block(libid):
    f, n = LIBS[libid]
    b = extract(f, n)
    if b is None:
        raise SystemExit(f"symbol not found: {libid}")
    # 只给顶层符号加库前缀；子单元（如 C_0_1）保持原名，与 M2 一致
    return b.replace('(symbol "' + n + '"', '(symbol "' + libid + '"', 1)


def pin_table(libid):
    f, n = LIBS[libid]
    return pins(extract(f, n))


def components(variant):
    ud_plus = "USB_D-" if variant == "defect" else "USB_D+"
    ud_minus = "USB_D+" if variant == "defect" else "USB_D-"
    return [
        # ref, lib_id, x, y, value, footprint, {pin: net 或 None=不连接}
        ("J1", "Connector:USB_C_Receptacle_USB2.0_16P", 50.8, 101.6, "USB-C",
         "Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal",
         {"A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND",
          "A4": "+5V", "A9": "+5V", "B4": "+5V", "B9": "+5V",
          "A5": "CC1", "B5": "CC2",
          "A6": "USB_D+", "B6": "USB_D+", "A7": "USB_D-", "B7": "USB_D-",
          "A8": None, "B8": None, "SH": "GND"}),
        ("U1", "Interface_USB:CH340C", 127.0, 101.6, "CH340C",
         "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
         {"1": "GND", "2": "TXD", "3": "RXD", "4": "V3",
          "5": ud_plus, "6": ud_minus,
          "7": None, "8": None, "9": None, "10": None, "11": None,
          "12": None, "13": None, "14": None, "15": None, "16": "+5V"}),
        ("R1", "Device:R", 76.2, 139.7, "5.1k", "Resistor_SMD:R_0402_1005Metric",
         {"1": "CC1", "2": "GND"}),
        ("R2", "Device:R", 88.9, 139.7, "5.1k", "Resistor_SMD:R_0402_1005Metric",
         {"1": "CC2", "2": "GND"}),
        ("C1", "Device:C", 76.2, 63.5, "10uF", "Capacitor_SMD:C_0402_1005Metric",
         {"1": "+5V", "2": "GND"}),
        ("C2", "Device:C", 152.4, 63.5, "100nF", "Capacitor_SMD:C_0402_1005Metric",
         {"1": "+5V", "2": "GND"}),
        ("C3", "Device:C", 165.1, 63.5, "100nF", "Capacitor_SMD:C_0402_1005Metric",
         {"1": "V3", "2": "GND"}),
        ("J2", "Connector_Generic:Conn_01x04", 203.2, 101.6, "UART",
         "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
         {"1": "GND", "2": "RXD", "3": "TXD", "4": "+5V"}),
        ("#FLG01", "power:PWR_FLAG", 38.1, 50.8, "PWR_FLAG", "", {"1": "+5V"}),
        ("#FLG02", "power:PWR_FLAG", 38.1, 152.4, "PWR_FLAG", "", {"1": "GND"}),
    ]


# 标签朝向：按库内引脚角度（引脚从连接点指向本体的方向）
LABEL_ORIENT = {
    0: (180, "right"),   # 连接点在左，文字向左伸
    180: (0, "left"),    # 连接点在右，文字向右伸
    270: (90, "left"),   # 连接点在上，文字向上伸（与 M2 一致）
    90: (270, "right"),  # 连接点在下，文字向下伸
}

F = '(effects (font (size 1.27 1.27))'


def r(v):
    return f"{round(v, 4):g}"


def build(variant):
    comps = components(variant)
    used_libs = sorted({c[1] for c in comps})
    out = []
    out.append("(kicad_sch")
    out.append("\t(version 20231120)")
    out.append('\t(generator "eeschema")')
    out.append('\t(generator_version "8.0")')
    out.append(f'\t(uuid "{ROOT}")')
    out.append('\t(paper "A4")')
    out.append("\t(title_block")
    out.append('\t\t(title "CH340C USB-Serial Adapter")')
    out.append('\t\t(rev "1.0")')
    out.append("\t)")
    out.append("\t(lib_symbols")
    for lib in used_libs:
        out.append("\t\t" + lib_block(lib))
    out.append("\t)")

    labels, ncs = {}, {}
    for ref, lib, x, y, val, fp, pmap in comps:
        table = {p["num"]: p for p in pin_table(lib)}
        missing = set(table) - set(pmap)
        extra = set(pmap) - set(table)
        if missing or extra:
            raise SystemExit(f"{ref}: pin map mismatch missing={sorted(missing)} extra={sorted(extra)}")
        is_flag = ref.startswith("#")
        pin_uuids = " ".join(f'(pin "{n}" (uuid "{U(f"pin:{ref}:{n}")}"))' for n in sorted(table))
        if lib.startswith("Device:"):
            rpos, vpos, just = (x + 3.302, y - 1.27), (x + 3.302, y + 1.27), " (justify left)"
        elif is_flag:
            rpos, vpos, just = (x, y - 3.81), (x, y - 6.35), ""
        else:
            rpos, vpos, just = (x + 5.08, y - 27.94), (x + 5.08, y + 27.94), " (justify left)"
        hide_ref = " (hide yes)" if is_flag else ""
        out.append(
            f'\t(symbol (lib_id "{lib}") (at {r(x)} {r(y)} 0) (unit 1) (uuid "{U("sym:" + ref)}") {pin_uuids} '
            f'(property "Reference" "{ref}" (at {r(rpos[0])} {r(rpos[1])} 0) {F}{just}{hide_ref})) '
            f'(instances (project "{PROJECT}" (path "/{ROOT}" (reference "{ref}") (unit 1))))')
        out.append(f'\t(property "Value" "{val}" (at {r(vpos[0])} {r(vpos[1])} 0) {F}{just}))')
        out.append(f'\t(property "Footprint" "{fp}" (at {r(x)} {r(y)} 0) {F} (hide yes))))')

        for num, net in pmap.items():
            p = table[num]
            sx, sy = round(x + p["x"], 4), round(y - p["y"], 4)
            key = (sx, sy)
            if net is None:
                ncs[key] = True
                continue
            if key in labels and labels[key][0] != net:
                raise SystemExit(f"net conflict at {key}: {labels[key][0]} vs {net}")
            labels[key] = (net, int(p["ang"]) % 360)

    for (sx, sy), (net, ang) in sorted(labels.items()):
        la, js = LABEL_ORIENT[ang]
        out.append(f'\t(label "{net}" (at {r(sx)} {r(sy)} {la}) {F} (justify {js} bottom)) (uuid "{U(f"label:{sx}:{sy}")}"))')
    for (sx, sy) in sorted(ncs):
        out.append(f'\t(no_connect (at {r(sx)} {r(sy)}) (uuid "{U(f"nc:{sx}:{sy}")}"))')

    out.append("\t(sheet_instances")
    out.append('\t\t(path "/" (page "1"))')
    out.append("\t)")
    out.append(")")
    return "\n".join(out) + "\n", len(labels), len(ncs)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=["defect", "correct"], required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    text, nl, nn = build(a.variant)
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(a.out).write_bytes(text.encode("utf-8"))
    print(f"{a.variant}: {a.out}  labels={nl} no_connect={nn} bytes={len(text.encode('utf-8'))}")
