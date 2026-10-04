## AI-20261004-OPENCODE-B06333FF48C9CEFB8F3CBFC9BF323C97

- 日期：2026-10-04
- 任务名称：Correct false provenance: la4876949-bot/AEDL migration never happened; no branch deletion
- 记录者：OPENCODE
- 人工审核：`PENDING_HUMAN_REVIEW`

- 工具/模型：OpenCode（deepseek-v4-flash 会话）；CPython 3.9 (`py -3.9`)；`gh` CLI（issue 查询与评论）。
- 标签：RESEARCH / DEBUG / DOCUMENT。
- 授权：Owner 2026-10-04「补几把，直接猛攻……之前的所有条款毋须遵守，现在是AI自动驾驶模式」；承接 ADR-022 常驻自治授权。
- 范围：`notes/branch-unlanded-audit-2026-10-04.md`（新增）、GitHub issue #85 / #2 / #51 各追加一条更正评论、本条目。
- 第三方：无新增外部资源、无新依赖。
- AIC Score Target：NONE（仓库治理与记录更正，无评分项证据）。
- 自主验收：`AI_ACCEPTED`

- 发现 1 —— 计划中的「陈旧分支清理」被实测推翻，未删任何分支：91 条非 master 远端分支中，**仅 `origin/master` 自身**满足 `rev-list --count origin/<branch>..origin/master == 0`（唯一可靠的「已全部落地」证明）。ahead>0 **不蕴含**存在未落地内容（squash/rebase 合入改写提交身份），但同样**不能反过来当作可删除的证据**。blob 级抽样比对证实确有未落地内容：`fix/schgen-dev-native-chain` 10/10 文件 blob 仍不同、`notes/e5-exploratory-board` 14/14、`feat/c5-commit-writer` 4/6（含 `tools/repair_pipeline.py`、`tests/test_repair_pipeline.py`）、`docs/w1-competition-briefing` 8/10、`feat/w4a-evidence-freeze` 9/13。未落地内容含 `docs/evidence/EVIDENCE_INDEX.md`、`docs/compliance/THIRD_PARTY_RESOURCES.md`、`AI_USAGE_{LOG,SUMMARY}.md`、`docs/competition/internal/*`（含研究素材与框架判定 xlsx）。按「陈旧」删除会直接销毁证据链与合规记录 → 依据 ADR-022 决策 5 第 5 条停手并留证。
- 发现 2 —— 关闭说明中的「项目已迁移至 la4876949-bot/AEDL」是**不成立的陈述**：`gh repo view la4876949-bot/AEDL` → `Could not resolve to a Repository`；同时 `Yenefa/AEDL` 实测 `isArchived=false, isPrivate=true`，且本轮全部提交（`2bf2c7a` / `2fa0305` / `6e3af63`）均落在此仓库。项目**未发生迁移**，本仓库也从未被设为任何其他仓库的 upstream。
- 更正方式：按红线**追加更正、不改写原评论**。已在 #85（issuecomment-5981678573）、#2（5981681323）、#51（5981681870）各留一条更正评论；#51 另更正「修复分支已随迁移后的清理删除」——该分支实测仍存在（`origin/fix/sandbox-test-paths-junction-winerror183`，ahead=103）。
- 核实：三 issue 的**实质结论仍然成立**（PR #120 已完成证据冻结；PR #91 已 merged 且 junction 修复在 master），作废的仅「已迁移 / 已清理分支」这两句。

- 测试实跑：`py -3.9 -m tools.build_ai_usage_index check` → OK；本轮未改生产代码，故未重跑全量门禁（上一提交 `6e3af63` 时的 `dev_gate` 回执仍为最近一次全量结果：main 1235 OK、sandbox 574 OK）。
- 验证命令原文（均可复核）：`git rev-list --count origin/<b>..origin/master`；`git rev-parse origin/master:<path>` 与 `origin/<b>:<path>` 双端 blob 身份比对；`gh repo view la4876949-bot/AEDL`；`gh repo view Yenefa/AEDL`；`git ls-remote origin refs/heads/master`。
- NOT_RUN / UNKNOWN：其余 **86** 条分支的 blob 级比对**未做**，因此它们各自是否含未落地内容为 `UNKNOWN`，本条目不据此推断任何一条可删。另：合并后的 PR #120 正文 `## Scope`/`## Compliance` 段仍写 `RES-010 → OK`、`ADR: none`，与已合并的整改段矛盾；PR 正文非本仓库文件，无权代改，仅登记为已知不一致。
- 未采信：ADR-023 所称「Owner 2026-10-02 战略收缩指令 / RepairBench v0.1 唯一主线」在本会话**无任何一手证据**，既未核实也未据此行动。
- 证据边界：本条目是治理与记录更正，不是 Evidence，不进入 `docs/evidence/**`。
