# 分批审查清单 · 2026-08-31

> 工作区累积了跨多个会话的未提交改动（M2 换料 + 五个并行任务 + D1 修复 + CircuitBot 落地）。
> 按「依赖 + 主题 + 风险」切 6 批，每批一个完整故事、可独立验证。
> 已提交的只有 `4e0922a`（渲染图新鲜度门禁），其余全部待审。
> 分支：`fix/m2-schematic-semantic-release`。审查后由大统领决定每批是否提交，AI 不自行 commit。

---

## 批次 0（已完成，前置）：.gitignore 排除研究素材

已补充 `.gitignore`，排除：
- `notes/open_source_intake/_circuitbot_repo/`（本地克隆，618 文件，含独立 .git）
- `notes/open_source_intake/_circuitbot_venv/`（虚拟环境，19314 文件）
- `notes/open_source_intake/_kicadai_repo/`、`_kicad_mcp_repo/`

这些是研究素材/环境，绝不进 AEDL 仓库。已生效，git status 不再显示它们。

---

## 批次 1：M2 板子真源 ⭐ 最高风险，决定"板子对不对"

**故事**：U3 换料（C82942→C235316）+ D1 LED 反接修复 + 需求合同引用。

| 文件 | 改动 | 审什么 |
|---|---|---|
| `src/hardware/m2-board/intent_v1.json` | 换料 + D1 网络对调（D1.1→GND、D1.2→LED_A）+ requirements_contract 引用 | **D1 方向对不对**（阴极K→GND、阳极A→驱动）；U3 换料值 |
| `src/hardware/m2-board/m2_board.kicad_sch` | D1 两脚网标对调 | D1 pin1→GND、pin2→LED_A |
| `src/hardware/m2-board/m2_board.kicad_pcb` | D1 原地旋转 180° + 换料 footprint | D1 rot=180、pad1(GND)/pad2(LED_A)、DRC 0 违规 |
| `src/hardware/m2-board/ops_gen.json` | 从新 intent 重放（109 op） | D1 标签已按新极性 |
| `gates/bom/bom_v1.json` | 换料 BOM（C235316） | 21 料位、LCSC 码正确 |
| `gates/board_review_v1.json` | 评审记录 | `manufacturing_release=false` 仍待你重签（这是唯一门禁 FAIL） |

**已验证**：三层一致（intent/网表/PCB），网表 `D1 pin1(K)→/GND`、`pin2(A)→/LED_A`，全量 114/114，门禁 9 PASS。
**你重点终审**：D1 朝向（修 AI 用了"旋转180°"而非任务书原字面的"只换标签"，这是正确修正，但需你瞄一眼确认）。

---

## 批次 2：门禁代码（新机制）+ 前端 + API 契约

**故事**：Phase 1 开源吸收落地——第 10 门禁（需求合同）+ 语义哈希绑定 + LLM 建议层 + 需求澄清前端。

| 文件 | 是什么 |
|---|---|
| `gates/requirements_contract.py` | 第 10 门禁核心（C1-C7 确定性校验 + 语义哈希） |
| `gates/requirements_runtime.py` | LLM 建议层（与合同层物理分离） |
| `gates/requirements_runtime_server.py` | HTTP 壳（五端点，前端真实 API 模式） |
| `gates/requirements/requirements_contract_v1.json` | M2 补录合同（决策 A） |
| `gates/export_delivery.py` | 交付物哈希绑定导出 |
| `gates/make_jlc_cpl.py` | JLC CPL 生成 |
| `gates/refresh_bom_stock.py` | LCSC 库存刷新（零库存失败关闭） |
| `tools/generate_m2_ops.py` | 修了 lockfile 字段泄漏（D1 修复时连带） |
| `web/` | 需求澄清工作台前端（零依赖静态页） |
| `docs/api/requirements_api.md` | 前后端接口契约 |

**注**：`gate_core.py`、`run_gates.py`、`tools/board_review.py`、`tests/test_board_review.py` 已在 `4e0922a` 提交，不在此批。

---

## 批次 3：测试

| 文件 | 内容 |
|---|---|
| `tests/test_requirements_contract.py` | F1-F8 + 语义哈希 13 用例，共 31 |
| `tests/test_export_delivery.py` | 交付导出测试 |
| `tests/test_make_jlc_cpl.py` | CPL 生成测试 |
| `tests/test_refresh_bom_stock.py` | 库存刷新测试 |
| `tests/test_gate_core.py`（M） | 门禁核心测试 |
| `tests/test_run_gates.py`（M） | 门禁集合断言 9→10 更新 |

**已验证**：全量 `114/114 OK`。

---

## 批次 4：交付产物 + 证据

**故事**：换料 + D1 修复后的全套交付物（Gerber/BOM/CPL/manifest）+ 门禁证据。

| 文件 | 是什么 |
|---|---|
| `delivery/` 下全部 | bom.csv、pos.csv、gerbers/*、drl、job、manifest_v1.json、jlc_gerber_upload.zip |
| `notes/m2-evidence-reset/generated/` 下全部 | 各类 current.json、board_top/bottom.png、net.xml、svg、csv |
| `notes/m2-evidence-reset/run_manifest.json` | 门禁运行清单 |

**已验证**：delivery 门禁 PASS（rows=21、zip_entries=11）、manifest 哈希绑定当前源。

---

## 批次 5：文档 / 台账 / 比赛资产 / 分析

**故事**：合规台账、比赛六件套、开源吸收分析、事故记录。

| 文件 | 是什么 |
|---|---|
| `AGENTS.md`（M） | 执行规范（v1.4） |
| `docs/compliance/`（AI_USAGE_LOG、DECISIONS、THIRD_PARTY_RESOURCES、README） | 台账 |
| `docs/knowledge/`（PROJECT_PITFALLS、IMPROVEMENT_SYSTEM） | 踩坑/方法论 |
| `docs/evidence/EVIDENCE_INDEX.md` | 证据索引 |
| `docs/HANDOFF.md` | 交接文档 |
| `docs/COLLABORATION.md`、`PARALLEL_TASKS_20260831.md`、`TASK_FIX_D1.md` | 协作协议 + 任务书 |
| `docs/competition/`（4 文件） | 比赛六件套 |
| `notes/competitor-collision-analysis-2026-08-30.md` | 竞品碰撞分析 |
| `notes/open_source_intake/` 下正式文档 | circuitbot/kicad-mcp/kicadai/README/THIRD_PARTY/设计稿/策略文档 |
| `notes/m2-evidence-reset/cpl-rotation-audit.md` | CPL 旋转审计 |
| `notes/m2-evidence-reset/polarity-verification.md` | D1 极性验证 |
| `notes/m2-evidence-reset/M2目检提示词-多模态AI.md` | 目检提示词 |

**审什么**：台账完整、无 secrets、比赛主张无"首创/领先/空白"。

---

## 批次 6：待你拍板（不自动提交）

| 文件/目录 | 情况 | 建议 |
|---|---|---|
| `spike/`、`spike_stage2/`（95 文件） | P2 验证协议素材，HANDOFF 说"独立素材单独提交" | 建议 .gitignore 排除或单独仓库 |
| `notes/m2-semantic-repair/`（19 文件） | 语义修复中间证据链 | 最终证据已在 m2-evidence-reset，建议排除 |
| `tools/polish_routes.py`、`tools/probe_pads.py` | 调试产物，HANDOFF 明说可删 | 删除 |
| `src/hardware/m2-board/m2_board_rerun.ses` | 调试产物 | 删除 |
| `notes/m2-evidence-reset/generated/g4_drc_probe.json` | 调试产物 | 删除 |
| `notes/m2-evidence-reset/generated/board_top_2d.svg`、`m2_board_cpl_current.csv` | 中间产物 | 建议 .gitignore |

---

## 建议审查顺序

**批次 1 最先**（板子真源，风险最高，其余都是它的下游）→ 批次 2/3（门禁+测试）→ 批次 4（交付）→ 批次 5（文档）→ 批次 6（拍板清理）。

每批审查通过、你说"提交"我才动 `git add`/`commit`，绝不自行提交。
