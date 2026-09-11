# -*- coding: utf-8 -*-
"""解析两个变体的 KiCad 网表，独立核对连通性。

断言：
  1. 缺陷版：USB_D+ = {J1.A6, J1.B6, U1.6}，USB_D- = {J1.A7, J1.B7, U1.5}
  2. 正确版：USB_D+ = {J1.A6, J1.B6, U1.5}，USB_D- = {J1.A7, J1.B7, U1.6}
  3. 两版除上述两网外，其余每个网络的节点集合完全相同
  4. 其余网络与设计意图一致
"""
import re
import sys
import pathlib


def parse(path):
    t = pathlib.Path(path).read_text(encoding="utf-8")
    nets, unconnected = {}, set()
    # KiCad 10 网表为多行、制表符缩进：token 之间是换行 + 空白，不是单个空格
    starts = [m.start() for m in re.finditer(r'\(net\s*\(code', t)]
    starts.append(len(t))
    for i in range(len(starts) - 1):
        blk = t[starts[i]:starts[i + 1]]
        m = re.search(r'\(name\s+"([^"]*)"\)', blk)
        if not m:
            continue
        name = m.group(1).lstrip("/")
        nodes = {f"{a}.{b}" for a, b in re.findall(r'\(node\s*\(ref\s+"([^"]+)"\)\s*\(pin\s+"([^"]+)"\)', blk)}
        if name.startswith("unconnected-") or name.startswith("Net-("):
            unconnected |= nodes
        else:
            nets[name] = nodes
    return nets, unconnected


EXPECT_COMMON = {
    "+5V": {"J1.A4", "J1.A9", "J1.B4", "J1.B9", "U1.16", "C1.1", "C2.1", "J2.4"},
    "GND": {"J1.A1", "J1.A12", "J1.B1", "J1.B12", "J1.SH", "U1.1",
            "R1.2", "R2.2", "C1.2", "C2.2", "C3.2", "J2.1"},
    "CC1": {"J1.A5", "R1.1"},
    "CC2": {"J1.B5", "R2.1"},
    "V3": {"U1.4", "C3.1"},
    "TXD": {"U1.2", "J2.3"},
    "RXD": {"U1.3", "J2.2"},
}
EXPECT_NC = {"U1.7", "U1.8", "U1.9", "U1.10", "U1.11", "U1.12", "U1.13", "U1.14", "U1.15", "J1.A8", "J1.B8"}
EXPECT_DEFECT = {"USB_D+": {"J1.A6", "J1.B6", "U1.6"}, "USB_D-": {"J1.A7", "J1.B7", "U1.5"}}
EXPECT_CORRECT = {"USB_D+": {"J1.A6", "J1.B6", "U1.5"}, "USB_D-": {"J1.A7", "J1.B7", "U1.6"}}


def real(nodes):
    return {n for n in nodes if not n.startswith("#")}


def main(defect_net, correct_net):
    d, d_nc = parse(defect_net)
    c, c_nc = parse(correct_net)
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
        ok = ok and cond

    print("=== 缺陷版网络 ===")
    for n in sorted(d):
        print(f"  {n:<8} {sorted(real(d[n]))}")
    print()
    print("=== 断言 ===")
    for n, exp in EXPECT_DEFECT.items():
        check(f"缺陷版 {n}", real(d.get(n, set())) == exp, f"得到 {sorted(real(d.get(n, set())))}")
    for n, exp in EXPECT_CORRECT.items():
        check(f"正确版 {n}", real(c.get(n, set())) == exp, f"得到 {sorted(real(c.get(n, set())))}")
    for n, exp in EXPECT_COMMON.items():
        check(f"两版 {n} 与设计一致", real(d.get(n, set())) == exp and real(c.get(n, set())) == exp)
    diff = sorted(n for n in set(d) | set(c) if real(d.get(n, set())) != real(c.get(n, set())))
    check("两版差异仅限 USB_D+ / USB_D-", diff == ["USB_D+", "USB_D-"], f"差异网络 {diff}")
    moved = sorted((real(d["USB_D+"]) ^ real(c["USB_D+"])) | (real(d["USB_D-"]) ^ real(c["USB_D-"])))
    check("被移动的引脚恰好是 U1.5 与 U1.6", moved == ["U1.5", "U1.6"], f"{moved}")
    check("未连接引脚与设计一致（两版相同）", real(d_nc) == EXPECT_NC and real(c_nc) == EXPECT_NC,
          f"缺陷版 {sorted(real(d_nc))}")
    print()
    print("RESULT:", "ALL PASS" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
