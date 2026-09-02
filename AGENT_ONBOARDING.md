# AGENT_ONBOARDING — AEDL 仓库给所有 AI 编程代理的启动引导

> **读我的人**：Claude Code / Codex / zcode / DSH（DeepSeek Harness）/ opencode / Hermes /
> Trae / Work Buddy / Qoder / OpenClaw / 以及其他任何 AI coding agent。
>
> 你刚 clone 或进入本仓库（Yenefa/AEDL，private）。**在写任何代码、跑任何会改文件的命令、
> 开任何 PR 之前，按顺序做下面 0–4 步。**
>
> 本文件只是启动引导；**执行规范的真源是 `AGENTS.md`**，发生冲突时以 `AGENTS.md`、
> 当前 Issue/PR 与人类明确指令为准。

---

## 0. 身份与定位

- 人类协作者：**Yenefa**（原 sca331613-commits）与 **Percy**（la4876949-bot）。你是被调度进来的临时执行单元，不是仓库所有者。
- 北极星：**在受控工程流程下正确交付实体板卡**；sandbox（EDD-001）是手段，不是目的。
- 你能 **propose**，不能 **promote**：merge / approve / close / 设置批准状态 永远留给人。
- 别只看 master 分支名判断当前工作线——协作基线以 `docs/HANDOFF.md` 为准。

## 1. 环境自检（4 项，错一项都先修再干活）

```powershell
# ① 行尾契约（最重要，最容易踩）
git config core.autocrlf        # 必须输出 false；true 会把 LF 转 CRLF，哈希绑定测试全挂（GH-20 字节契约）
git config core.autocrlf false  # 若为 true 立即改正（Windows 与 Linux 都要）

# ② 主仓解释器 = Python 3.9（golden/hash 测试版本敏感，3.11 会假挂）
py -3 --version                 # Windows；期望 3.9.x
# Linux/macOS 无 py launcher 时：python3.9 --version，或显式 export AEDL_PYTHON=python3.9
# 注意：Windows 上裸 `python` 可能指向别的 venv（如 3.11）——显式用 py -3

# ③ uv（sandbox 测试 REQUIRED；缺失 = dev_gate GATE_BROKEN，无静默排除）
uv --version

# ④ gh CLI 已登录（admit 依赖核验 / PR / Issue 交互）
gh --version && gh auth status
```

（可选）`kicad-cli`：Evidence Gate（`gates/run_gates.py`）的 PCB 渲染需要；dev_gate 不 gate 它。Wokwi 仿真需要 token。

自检通过后跑一次基线，确认你能复现"一个 PASS 语义"：

```powershell
py -3 -m tools.dev_gate
# 期望 exit 0：syntax / main 306 / sandbox 274 (1 skip 1 xfail) / secret_scan 305 files
```

## 2. 必读（按序，读完才动手）

1. `AGENTS.md` — Agent 执行层唯一规范（变更控制 / 权限 / 合规 / 真实性红线）
2. `docs/HANDOFF.md` — 最新分支、阻塞项、验证状态（协作基线真源）
3. `docs/COLLABORATION.md` — 权限模型 OWNED / SHARED / FOREIGN（§0.8）
4. `docs/CONTROL_PLANE.md` — 控制面：Envelope → Admission → Dev Gate → Review Bundle → 人工 merge
5. 当前 Issue / PR 的 Goal / Scope / Owned paths / Acceptance Criteria

硬件任务（选型 / 原理图 / PCB / BOM / 制造签发）还必须读
`docs/knowledge/PROJECT_PITFALLS.md` + `docs/knowledge/IMPROVEMENT_SYSTEM.md`，
并执行 `gates/learning_gate.py` 的控制。

## 3. AECP 速查（每次任务的生命周期）

```text
开工  有 envelope（tasks/GH-N.yaml）→ python -m tools.admit --envelope tasks/GH-N.yaml
      BLOCKED → STOP → 写 BLOCKED 记录 → 升级给人类（不得自行变通，不得 self-authorize）
执行  只在 Owned / Allowed paths 内写；未声明可写 = FOREIGN（默认只读）
收尾  python -m tools.dev_gate [--envelope ...]  → exit 0 全绿才算完
交付  需人工 review 的交付必须附 Review Bundle（review-bundles/run-NNN/，仓库外；
      含 review.md + 真实 hunks .patch + gate receipt）——无 bundle 不进人工 review
留痕  AI 实质参与 → docs/compliance/AI_USAGE_LOG.md（AI-YYYYMMDD-NNN；默认 PENDING_HUMAN_REVIEW）
晋升  永远人类。你能起草 PR、分析 PR、贴 review 建议，不能 merge / approve
```

## 4. 红线（违反 = 不可信）

- 不 merge / approve / force-push main；不设置 `HUMAN_REVIEWED` / `ACCEPTED` / `manufacturing_release`
- 不编造运行结果、Evidence、Benchmark、人工审核；没跑的写 `NOT_RUN`，不知道的写 `UNKNOWN`
- 不把第三方 / AI 产出伪装成团队自研；不把软件 / 静态 / 仿真结果说成实体验证
- 不写 secrets / 凭据；发现泄露 → 停止传播 → 报告 → 要求轮换
- 不改冻结基线：M2 物理线（U3 封存）、哈希绑定 Evidence 字节、.gitattributes 契约
- 不"顺手优化"扩大范围；越过 Change Budget / 触碰 FOREIGN 路径先升级

> **Agent may propose, but not promote.**
> **Rules may guide, but gates enforce.**
> **Memory may suggest, but provenance decides.**
> **Exceptions may escalate, but never silently bypass.**

## 5. 台账与状态指针（真源以 HANDOFF / GitHub 为准）

- 主线状态：`docs/HANDOFF.md` + 最新 Issue / PR
- 合规台账：`docs/compliance/`（AI_USAGE_LOG / THIRD_PARTY_RESOURCES / DECISIONS）
- Evidence：`docs/evidence/EVIDENCE_INDEX.md`
- 赛事材料（评分 / 融合 / 开放成果）：触发时读 `docs/competition/`，平时不要塞进上下文
