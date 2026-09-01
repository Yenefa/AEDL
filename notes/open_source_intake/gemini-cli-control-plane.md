# Donor: Gemini CLI — Policy Engine / Hooks（控制面）

## 元信息

- Layer: `control-plane`
- Reviewed: 2026-09-01 | Verifier: DeepSeek Harness（raw GitHub 抓取 + web search）；用户二轮 primary 核实补充
- Status: `CONFIRMED`（核心机制）/ `STRONG_REPORT`（workspace-tier 限制）
- Primary sources:
  - [policy-engine.md（主仓正式 reference，raw 抓取）](https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/policy-engine.md)
  - [hooks/reference.md](https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/reference.md)
  - [PR #10630：ASK_USER policy decisions 接入 message bus](https://github.com/google-gemini/gemini-cli/pull/10630)
  - [PR #21146：BeforeTool hooks 支持 'ask' decision](https://github.com/google-gemini/gemini-cli/pull/21146)
  - [Issue #18186：workspace tier 项目级 policies 当前不生效（用户核实，未独立复核）](https://github.com/google-gemini/gemini-cli/issues/18186)

## Capability

Tool-call 级 admission：LLM 每次想执行工具时，由规则集裁决 `ALLOW / DENY / ASK_USER`；
规则 = 条件 + 决策 + 优先级（高者胜）；BeforeTool hook 可在动作前检查参数并机器级阻断。

## Mechanism

- Policy Engine 在 agent loop 内**同步求值**：请求工具 → 求值全部规则 → 最高优先级命中
  规则的 decision 生效。
- 规则是 TOML 文件（`~/.gemini/policies/*.toml`，quick start 即用户级路径）；条件覆盖
  toolName（通配符 `*`、`mcp_server_*`）、参数（如 `commandPrefix = "rm -rf"`）、
  approval mode。
- Hook 插入 PreTool 阶段（BeforeTool）：可检查参数、返回 deny/block 阻断、exit code 2
  阻断；`ask` decision 已由 PR #21146 支持。
- 非交互（headless）模式下 `ASK_USER` 退化为 `DENY`（用户核实）。

## Maturity

- `CONFIRMED`：主仓正式 reference 文档原文（raw 抓取 2026-09-01）——decision 三值
  allow/deny/ask_user、conditions（tool/参数/approval mode）、priority 高者胜。
- `CONFIRMED`（search 佐证）：PR #10630 / #21146 显示 ASK_USER 与 hook ask decision
  处于活跃演进，不是死文档。
- `STRONG_REPORT`：Workspace tier 的 `.gemini/policies` 当前不生效（#18186，
  用户核实；我未独立复核该 issue 内容）。

## Failure Mode

- `STRONG_REPORT`：#18186 项目级 policy 失效 → **repo 里放 policy 文件 ≠ 已生效的
  enforcement**。
- `CONFIRMED`（设计使然）：headless 下 ASK_USER→DENY → 无人工在场时 fail-closed。
- `ANECDOTE→CONFIRMED 边界`：hook/policy 行为随版本演进（PR 活跃），依赖 CLI 版本。

## AEDL Adaptation

- 吸收 **decision model**：`ALLOW / DENY / ESCALATE` 三元（= Gemini 的
  ALLOW/DENY/ASK_USER）；未来若 admit.py 需要中间态，加 `ASK` + priority
  （dirty 类软规则 vs base 漂移类硬规则分优先级）。
- 确认既有架构（本切片已落地）：envelope=declaration（repo 文件不 enforcement）；
  `tools/dev_gate.py` + CI=enforcement（机器层）；BLOCKED 记录 + 人工决策
  = headless-safe 的 ASK 路径（fail-closed，与 Gemini 非交互退化同构）。
- 明确不做什么：不引入 Gemini CLI；不依赖任何 vendor 的 project-policy 文件机制
  （#18186 教训）；不在当前切片加 ASK 中间态（等 Trigger）。

## Trigger

CRLF 真实 Issue 的首次真实 escalation 完成后：对照 BLOCKED 记录，若出现
"想放行/想拦但二元模型表达不了"的具体案例 → 才给 admit.py 加 ASK 中间态与 priority。
