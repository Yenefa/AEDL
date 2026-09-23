# DC-06 输入治理事件记录（GH-56 / Y4-dry）

状态：`RECORDED` / `PENDING_HUMAN_REVIEW`。Host-side 治理记录；**永不作为 C/D 输入**。
决策：Owner Option B（2026-09-10）——DC-06 在正式冻结前移除，替换而非用 oracle 回填。

## 1. 结构化字段

| 字段 | 值 |
|---|---|
| incident_id | `GH56-DC06-INPUT-GOV-2026-09-10` |
| detected_stage | `PRE_FREEZE_INPUT_REVIEW` |
| affected_case | `DC-06` |
| failure_mode | `PUBLIC_INPUT_INSUFFICIENT` |
| evidence_gap | 缺少 proposer 可见的实际工况/负载条件；仅有设计边界假设，不能支撑确定判断 |
| prohibited_recovery | `ORACLE_BACKFILL` |
| system_response | `FAIL_CLOSED / EXCLUDE_BEFORE_FREEZE` |
| human_owner_decision | `REPLACE_CASE` |
| impact | `prevented invalid benchmark contamination` |
| limitations | `governance result, not electrical validation result` |

## 2. 过程角色（原文记录）

> Before formal benchmark freeze, AEDL's fail-closed input-governance and independent review process detected that DC-06 did not contain enough proposer-visible evidence to support a determinate evaluation. The process prevented private/oracle operating-point information from being used to retroactively complete the public input, and required the case to be excluded/replaced before scoring.

**明确非主张（不得越界解读）：**

- 不声称生产修复系统（C/D/native executor）自主发现了该问题——这是 benchmark/input governance + review workflow 的结果；
- 不声称 AEDL 证明该硬件安全或不安全；
- 不声称 DC-06 电气失败（未运行任何电气验证）；
- 人类 owner 裁决明确：Option B = 移除并替换；不是自动结论。

## 3. 证据缺口（evidence_gap）

- DC-06（无注入的当前 M2 原理图）要形成确定评测，proposer 需要可见的"实际工况/负载"条件；仅有封装功耗上限等文档事实不足以判定工作点；
- 已批准材料中只有设计边界假设 A3：`U3 持续负载 < 147mA（V20 保守边界，ADR-005）`（requirements contract）。它是边界假设、非实测工况，不能证明当前工作点与 250 mW 上限的关系；
- 未发现独立批准、proposer 可见的实际工况来源；项目记录中相应整板实测仍为待办；
- 私有/oracle 工况数值存在，但不得用于回填公开输入（`prohibited_recovery = ORACLE_BACKFILL`）。

## 4. 审计轨迹（完整保留）

1. **r3（候选生成）**：DC-06 = `src/hardware/m2-board/m2_board.kicad_sch`（sha256 `306156853af7fd12afaacb30e09b0c435e2c249a848e50c6e2c33ff59634294a`，无注入；未创建 native/DC-06）。真实导出生成 g1/g2 observation 与生成时 binding，位于 r3 `observations/SRC-d86c37ebd789/`（binding `observation_sha256 = 8d65f0b4777c7fbe8276607c9c724c8e4a7991b965c01df0a92767972187bf2c`）。随机映射草案中为 Y4-001（该映射见 §5，已作废）。
2. **r4（facts 补充）**：为 DC-06 补 U3 facts（PBF-011～016）；其中 PBF-016 暴露 V20 同页 IOUTMAX 500/400 mA 差异。
3. **r5（owner CHANGES_REQUIRED 处置）**：PBF-016 撤回并转入 host-only 差异笔记；PBF-013 加注"设计边界、非工况"；PBF-015 收敛；DC-06 标记 `PUBLIC_INPUT_INSUFFICIENT`。
4. **r6（owner 决定）**：DC-06 退场，`EXCLUDED_BEFORE_FREEZE` / `reason = PUBLIC_INPUT_INSUFFICIENT`；替换检索结果 `REPLACEMENT_CASE_NOT_AVAILABLE`；映射/数组 hash 作废；未 freeze、未跑 C/D。

## 5. PBF-016 数据手册差异（保留，未静默取舍）

- V20 印刷 p9 通用表：IOUTMAX = 500 mA；
- V20 印刷 p9 专属表 `ME6211C33 (SOT343R, FBP1*1-4L, SOT353)`：IOUTMAX = 400 mA；
- 仓库裁决记录 `src/hardware/m2-board/evidence/contracts/m2_component_contracts.json`（文件 sha256 `9d0ac9a0ab1b54131eb014f802131863c23e18f81056baea4044253cbd3ff9ba`）与 `docs/compliance/ai-usage/AI-20260831-010.md`（sha256 `595a2e0b08448e922ed10f80de7a8269b5e11a3bea1be1e4509e6bbecdf8be8c`）记 400 mA；
- 完整差异与状态见 host delivery `r5/U3-DATASHEET-DISCREPANCY-NOTE.json`（`FOR_LATER_HUMAN_DATASHEET_ADJUDICATION`）。本事件解决的是输入充分性，**不是**该差异的技术定案。

## 6. 历史保留（不得删除）

- 原 DC-06 候选源、r3 observation/绑定目录、r5 差异笔记与 PBF-016 记录全部只读保留；
- 旧随机映射与旧六例数组保留但标记 `INVALIDATED_BY_CASE_SET_CHANGE`，**不得再用作 trusted pin**；
- 替换案例获批前不重建映射、不冻结。

## 7. 后续边界

> **SUPERSEDED by §8 below**（owner r7）：替换路径已取消；计分集修订为五例（DC-01..DC-05），DC-06 角色为 `UNSCORED_GOVERNANCE_INCIDENT`。本节保留为历史。

- 第六例替换仅可从"预先存在、可独立辩护"的候选来源中选择；须具备充分 proposer 可见的 source + observation + facts；
- 不得围绕期望答案设计新案例，不得从 DC-06 私有期望结果派生，不得使用 private oracle 数值；
- 当前 `REPLACEMENT_CASE_NOT_AVAILABLE`（见 `REPLACEMENT-CANDIDATE-REVIEW.json`），无法进入正式冻结。

## 8. Owner update（2026-09-10，r7）——取消替换路径，计分集修订为五例

- r6 治理处置获 owner **APPROVED**；
- 新决定：**不寻找、不编造第六例**；pre-freeze 计分的 Y4-dry 实验由 6 例修订为 **5 例（DC-01..DC-05）**；
- DC-06 角色更新为 `UNSCORED_GOVERNANCE_INCIDENT`（保持 `EXCLUDED_BEFORE_FREEZE` / `reason = PUBLIC_INPUT_INSUFFICIENT`）；全部历史继续保留，不得删除；
- 修订发生在正式冻结之前；`C_D_runs = NOT_RUN`、`A_B_scores = NOT_RUN`；修订动因是**输入确定性/证据充分性**，不是已观察到的模型表现；
- 旧六例 mapping / array / run-plan / freeze hash **永久作废**、禁止复用；
- 运行计划假设：5 例 × C/D × 3 次重复 = 30 槽（待 owner 确认沿用既有重复策略）；
- 详见 r7 `PROTOCOL-AMENDMENT-5CASE.json`（host delivery）及 `notes/y4/README.md` 修订说明。
