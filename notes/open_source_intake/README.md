# 开源项目 Intake 目录

> 依据：《AEDL_开源项目吸收与再设计策略_2026-08-30.md》（同目录）
> 协议：任何新发现的 AI EDA / Hardware Agent 项目，统一走六步 Intake（CLAIM / SOURCE / FAILURE / REUSABLE / TRANSFORM / VERIFY），禁止只看 README 就下结论。
> 已完成：CircuitBot（Phase 1，2026-08-31，见 circuitbot.md）；KiCadAI + KiCad MCP（Phase 2-3，2026-08-31，见 kicadai.md / kicad-mcp.md）；NeuroBoard（Phase 4，2026-08-31，见 neuroboard.md）；kicad-happy（Phase 5，2026-09-01，见 kicad-happy.md，Issue #3）

## 目录

| 文件 | 项目 | 状态 | 结论一句话 |
|---|---|---|---|
| circuitbot.md | CircuitBot (HiwarkhedePrasad) | 六步完成 | 吃 clarify 交互模式与 5 维度框架，拒绝其 fail-open 超时继续；AEDL 重新定义为 requirements_contract + SHA256 门禁 |
| kicadai.md | KiCadAI (dshills) | 六步完成 | 生成前能力评估+证据挂链+fail-closed 为真实现；碰撞分析"生成链路未见源码"经本轮克隆复核判为误判已校准（writer/ERC/DRC/MNA 仿真源码俱在）。吃 preflight 机制与工具错误四分类，不接其代码 |
| neuroboard.md | NeuroBoard (Be-bibek) | 六步完成 | LICENSE=MIT 与 README 法律声明块=CC BY-NC 4.0 双声明矛盾 → 按最严解释零代码复用，只作反面教材；验证全链无 fail-closed（GlobalDRC 恒 True、SI/PDN 回退硬编码、失败进 self_correction 继续）、回滚仅位置级快照；11 门禁对照仅 erc/drc 有形态等价且均 fail-open；附 kicad-ai(amcolex) GitHub API 五层取证定案（补记）与 Konnect license 细节（THIRD_PARTY.md §2.4） |
| kicad-mcp.md | KiCad MCP（家族，深审 mixelpixx 版） | 六步完成 | 工具层判决缺席 by design，AEDL 判决自持不变；JLC 检索仅可做 discovery 不得做 gating；后继项目 Konnect 为 AGPL-3.0 禁接触 |
| kicad-happy.md | kicad-happy (aklofas) | 六步完成 | sexp_parser.py 与 finding_schema.py 的分级信任评分可 Adapt；~50 个自动检测器与 AEDL 现有 `gates/schematic_semantics.py` 互补而非重叠（前者是契约校验，后者是自动模式识别）；对 AEDL 真实 M2 板实跑验证，`tools/board_review.py` 8 项检查之外找到 3 处真空白（基准点/环宽/测试点），1 处交叉验证（USB 保护），1 处假阳性（MPN 覆盖率）；"无 ML"式措辞与 `datasheet_verify.py` 自身声明矛盾 |

## 控制面 donor（补充层，与产品层六步 Intake 分开）

| 文件 | 项目 | 层 | 结论一句话 |
|---|---|---|---|
| _CONTROL_PLANE_DONOR_TEMPLATE.md | 模板（七栏） | control-plane | Capability → Mechanism → Maturity(证据) → Failure Mode(置信度) → AEDL Adaptation → Trigger；每条结论必须挂 primary source |
| gemini-cli-control-plane.md | Gemini CLI | control-plane | 吸 ALLOW/DENY/ASK_USER decision model 与 priority；#18186 证明 repo 内 policy 文件 ≠ enforcement（与 CODEOWNERS"路由器不是警察"同构）；headless ASK→DENY 与 AEDL BLOCKED+人工决策同构 |
| gemini-cli-policy-deepdive-2026-09-01.md | Gemini CLI（源码级二轮） | control-plane | 机制 CONFIRMED（scheduler 插入点/优先级公式/TOML schema/hook exit code）；畸形 policy fail-OPEN 与 hook-ask 无条件覆盖 DENY 为 AEDL 反面教材；AEDL 保持：配置解析失败=GATE_BROKEN、机器层 BLOCKED 不可被 ask 降级 |

## 附属

- `_circuitbot_repo/`：本地克隆（ff9b003，2026-08-16），供后续 Phase 2-4 复查；含 .git，勿提交进 AEDL 仓库（已在 AEDL .gitignore 排除前先确认）。
- `_kicadai_repo/`：本地浅克隆（`4f18765`，2026-08-24，depth=1；Windows 检出需 `core.longpaths=true`），供人工复核本轮结论；含 .git，勿提交进 AEDL 仓库。
- `_kicad_mcp_repo/`：本地浅克隆（`aa53d52`，v2.7.0，2026-08-20，depth=1），同上，勿提交进 AEDL 仓库。
- `_neuroboard_repo/`：本地浅克隆（`d8e3248`，2026-08-26，depth=1；Phase 4 取证用），同上，勿提交进 AEDL 仓库（**.gitignore 尚无该条目，本次未越界修改 .gitignore，需大统领补一行排除**）。
- 策略文档原件在同目录，已从 Downloads 归位（2026-08-31）。
- kicad-happy 本地浅克隆（`d5fd7da`，2026-09-01，depth=1）未放在 `_kicad_happy_repo/` 惯例位置——.gitignore 至今没有排除这类目录的规则（同 `_neuroboard_repo/` 已知问题），为避免误提交风险，本轮把克隆放在仓库目录之外的临时路径，未纳入本仓库工作树。

## 铁律（继承自策略文档 §12）

成熟的轮子直接用；有缺陷的轮子拆开修；真正没有的机制集中火力自己造。
