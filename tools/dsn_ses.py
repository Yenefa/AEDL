# -*- coding: utf-8 -*-
"""dsn_ses.py — M2-7c 辅助：DSN 导出与 SES 回读（KiCad 自带 Python）。

用法:
    dsn_ses.py export <board.kicad_pcb> <out.dsn>
    dsn_ses.py import <board.kicad_pcb> <in.ses>
"""
import sys

import pcbnew


def main(argv):
    mode, board_path, f_path = argv[1], argv[2], argv[3]
    board = pcbnew.LoadBoard(board_path)
    if mode == "export":
        ok = pcbnew.ExportSpecctraDSN(board, f_path)
        print("dsn_export_ok=", bool(ok))
        return 0 if ok else 5
    if mode == "import":
        # SES 会话导入后需保存
        pcbnew.ImportSpecctraSES(board, f_path)
        ok = pcbnew.SaveBoard(board_path, board)
        print("ses_import_saved=", bool(ok))
        return 0 if ok else 6
    print("unknown mode", mode)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
