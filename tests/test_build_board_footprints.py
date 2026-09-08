"""build_board.py 的封装映射必须与设计意图一致。

背景（P5）：`tools/build_board.py` 的 `FP_MAP` 曾把 U3 映射为 `SOT-23-5`，而
U3 在 C82942 -> C235316（ME6211C33R5G）换料后的封装是 `SOT-353`；
`intent_v1.json`、`ops_gen.json`、BOM、器件合同与 board_review 全链均为
SOT-353。任何人跑 build_board 重建，都会把换料前的旧封装静默带回来。

这里钉的不是"U3 这一处"，而是那一类缺陷：**builder 的封装表与 intent 声明
不一致**。intent 里任何一件已声明 footprint 的器件发生漂移，都必须失败。
"""
import json
import unittest
from pathlib import Path

from tools.build_board import FP_MAP

REPO_ROOT = Path(__file__).resolve().parents[1]
INTENT_PATH = REPO_ROOT / "src" / "hardware" / "m2-board" / "intent_v1.json"


def _declared_footprints():
    """intent 中显式声明 footprint 的器件 -> 'Lib:Name'。

    footprint 在 intent 里是可选字段；未声明的器件（U1/U2/J1/SW1/SW2 与两个
    电源标记）不在本测试的断言范围内——补声明属设计意图变更，不是 builder 修复。
    """
    intent = json.loads(INTENT_PATH.read_text(encoding="utf-8"))
    return {
        ref: comp["footprint"]
        for ref, comp in intent["components"].items()
        if isinstance(comp, dict) and comp.get("footprint")
    }


class BuildBoardFootprintMapTests(unittest.TestCase):
    def test_every_intent_declared_footprint_matches_the_builder_map(self):
        declared = _declared_footprints()
        self.assertTrue(declared, "intent 中没有任何已声明的 footprint，测试失去意义")

        mismatches = []
        for ref, expected in sorted(declared.items()):
            if ref not in FP_MAP:
                mismatches.append(f"{ref}: intent 声明 {expected}，但 FP_MAP 中没有该位号")
                continue
            lib, name = FP_MAP[ref]
            actual = f"{lib}:{name}"
            if actual != expected:
                mismatches.append(f"{ref}: intent={expected} builder={actual}")

        self.assertEqual(
            [], mismatches,
            "builder 的封装表与 intent 声明不一致；重建会把错误封装写进 PCB：\n  "
            + "\n  ".join(mismatches),
        )

    def test_u3_is_pinned_to_the_post_substitution_footprint(self):
        # 换料后的具体钉值。上面的通用断言已覆盖它，这里单独钉是为了让回归
        # 失败时直接指向 PIT 记录在案的那次换料，而不用回头翻 intent。
        self.assertEqual(("Package_TO_SOT_SMD", "SOT-353"), FP_MAP["U3"])

    def test_the_check_actually_fails_when_the_map_drifts(self):
        # 验收要求：证明这条检查不是空转。用一个受控的漂移副本重跑同一比较逻辑，
        # 必须报出不一致——不修改真实的 FP_MAP。
        declared = _declared_footprints()
        ref = "U3"
        self.assertIn(ref, declared)

        perturbed = dict(FP_MAP)
        perturbed[ref] = ("Package_TO_SOT_SMD", "SOT-23-5")  # 换料前的旧值

        mismatches = [
            r for r, expected in declared.items()
            if r in perturbed and f"{perturbed[r][0]}:{perturbed[r][1]}" != expected
        ]
        self.assertEqual([ref], mismatches)


if __name__ == "__main__":
    unittest.main()
