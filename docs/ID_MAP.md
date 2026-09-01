# ID_MAP — ID 引用地图（结构化检索入口）

> 目的：新会话不必通读全部文档——先查这张表定位 ID 真源，再按需加载。
> 格式约定与 `AGENTS.md` §8.5 按需加载思想一致。**本表只做导航，不能替代真源文件本身。**
> 建立日期：2026-08-31（AI-20260831-011）；各 ID 格式已逐个与真源文件核对。

## ID 体系一览

| ID 体系 | 格式 | 真源文件 | 典型用法 |
|---|---|---|---|
| AI 台账 ID | `AI-YYYYMMDD-NNN`（如 AI-20260831-011） | `docs/compliance/AI_USAGE_LOG.md` | 解码 git 提交信息里的 `[AI-...]` 标签，定位到具体会话的工作边界与文件清单 |
| 架构决策 ID | `ADR-NNN`（如 ADR-005） | `docs/compliance/DECISIONS.md` | 引用设计依据（换料方法论、单一真源等）；立项标准见 `AGENTS.md` §6 |
| 证据 ID | `EVID-YYYYMMDD-NNN`（如 EVID-20260829-001） | `docs/evidence/EVIDENCE_INDEX.md` | 支撑技术主张（比赛材料、评审结论）；AI 不得手工改写原始 evidence |
| 第三方资源 ID | `RES-NNN`（如 RES-001） | `docs/compliance/THIRD_PARTY_RESOURCES.md` | 查 license/授权边界/再分发义务；未知项标 `TO_VERIFY` |
| 事故教训 ID | `PIT-YYYYMMDD-NNN`（如 PIT-20260830-001） | `gates/lessons_registry_v1.json`（机器可执行）+ `docs/knowledge/PROJECT_PITFALLS.md`（叙述版） | 已防错误清单；排查"为什么门禁这样设计"时先查 |
| 协作任务卡 | `TASK-PN`（如 TASK-P5） | `docs/COLLABORATION.md` | 多 AI 领地划分与任务领取状态 |

## 真人身份与代称

> 仓库内以 GitHub 账号名作为权威标识；代称用于会话、对话与口头引用，不替代账号名。
> 身份边界与贡献分类见 `docs/COLLABORATION.md`；本表只做检索导航。

| GitHub 账号 | 代称 | 角色 |
|---|---|---|
| `Yenefa` | Yenefa | 项目负责人（大统领）；原 `sca331613-commits`，2026-09-01 改名 |
| `la4876949-bot` | Percy | 正式团队成员（AEDL_TEAM）；第二名真人协作者，2026-09-01 确认 |

## 按需加载路由（任务类型 → 必读文件）

- **硬件发布 / 下单 / 重签 board_review** → `AGENTS.md` §2.1 → `docs/knowledge/` 两份（IMPROVEMENT_SYSTEM、PROJECT_PITFALLS）→ `gates/board_review_v1.json` + `notes/m2-evidence-reset/generated/board_review_auto.json` → 先跑 `py -3 gates/run_gates.py` 看基线。
- **门禁 / 合同 / intent 改动** → 先跑 `run_gates.py` 确认基线 → `docs/HANDOFF.md` 状态卡 → 相关 ADR → 改后必须全量测试（当前 127 例）。
- **比赛材料 / 对外主张** → `docs/competition/` 五件套 + `SUBMISSION_CHECKLIST.md` §3 FAIRNESS_CHECK → 主张逐条对 EVID/ADR 台账核验（`AGENTS.md` §8.8）。
- **开源吸收 / 第三方引入** → `notes/open_source_intake/README.md` → 对应 intake 报告（circuitbot.md、kicadai.md、kicad-mcp.md）→ `THIRD_PARTY.md`（Konnect AGPL 红线）→ 登记 RES-NNN。
- **新会话接手** → `AGENTS.md` → 本表 → `docs/HANDOFF.md` 状态卡（1 分钟）→ 台账最近 2–3 条（AI ID 解码 git log）→ 按任务类型走上述路由。
- **多 AI 并行开工** → `docs/COLLABORATION.md` 领地规则 → `git status` 确认他人未提交改动 → 领卡开工。
