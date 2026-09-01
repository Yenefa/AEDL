# Donor: Gemini CLI — Policy Engine / Hooks — Deep-dive（源码级二轮核实）

> 适用层：**control-plane**。本文是 `gemini-cli-control-plane.md`（首轮切片）的源码级 deep-dive：
> 全部机制按 **raw 源码 + 官方 reference 文档** 逐条核实，置信度标注到每条事实。
> 核实日期：2026-09-01；Verifier：DeepSeek Harness（raw.githubusercontent.com / api.github.com 逐文件抓取，commit = main HEAD）。

## 元信息

- Layer: `control-plane`
- Reviewed: 2026-09-01 | Verifier: DeepSeek Harness（源码抓取 + web） | Status: 核心机制 `CONFIRMED`（读了源码/文档原文）；`STRONG_REPORT`（issue 层面）；个别 `UNVERIFIED`
- Primary sources（全部实际抓取，逐条可回溯）：
  - [docs/reference/policy-engine.md（raw）](https://raw.githubusercontent.com/google-gemini/gemini-cli/main/docs/reference/policy-engine.md)（499 行，全部读）
  - [docs/hooks/reference.md（raw）](https://raw.githubusercontent.com/google-gemini/gemini-cli/main/docs/hooks/reference.md)（330 行，全部读）
  - 源码（raw，全部读）：[policy/types.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/policy/types.ts)、[policy/policy-engine.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/policy/policy-engine.ts)（1011 行）、[policy/toml-loader.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/policy/toml-loader.ts)（748 行）、[policy/config.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/policy/config.ts)（934 行）、[policy/utils.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/policy/utils.ts)、[scheduler/scheduler.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/scheduler/scheduler.ts)（`_processToolCall`）、[scheduler/policy.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/scheduler/policy.ts)、[scheduler/confirmation.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/scheduler/confirmation.ts)、[scheduler/hook-utils.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/scheduler/hook-utils.ts)、[tools/tools.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/tools/tools.ts)、[hooks/hookAggregator.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/hooks/hookAggregator.ts)、[hooks/hookRunner.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/hooks/hookRunner.ts)、[hooks/types.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/hooks/types.ts)、[confirmation-bus/types.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/confirmation-bus/types.ts)、[core/coreToolHookTriggers.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/core/coreToolHookTriggers.ts)
  - [PR #10630（API 抓取，merged 2025-10-15）](https://github.com/google-gemini/gemini-cli/pull/10630)
  - [PR #21146（API 抓取，merged 2026-03-21）](https://github.com/google-gemini/gemini-cli/pull/21146)
  - [Issue #18186 + 评论（API 抓取，open）](https://github.com/google-gemini/gemini-cli/issues/18186)

## Capability

Tool-call 级 admission gate + 事件级 hook 双闸门：LLM 每次想执行工具，先过
BeforeTool hook（可 ask/deny/改参数），再过 PolicyEngine（规则集按优先级裁决
`ALLOW / DENY / ASK_USER`），最后过用户确认环；headless 下 ASK_USER 等价 DENY
（fail-closed）。规则与 hook 都可做到**参数级**精细匹配，且全局 DENY 的工具
从模型可见 toolset 中直接剔除。

## Mechanism

### 1. Agent loop 中的插入点（源码级，CONFIRMED）

`scheduler/scheduler.ts → _processToolCall()`（Phase 3 单调用编排）顺序：

```
1) evaluateBeforeToolHook()      // BeforeTool：block→POLICY_VIOLATION 错误返回 agent；stop→STOP_EXECUTION；ask→hookDecision=ask
2) checkPolicy()                 // PolicyEngine.check()：规则求值 + shell 启发式 + safety checkers
3) if (hookDecision===ask) decision = ASK_USER   // hook ask 覆盖策略决策（源码为无条件覆盖，见 Failure Mode）
4) decision===DENY → 错误响应（ToolErrorType.POLICY_VIOLATION + denyMessage）返回给 agent（本轮继续）
5) decision===ASK_USER → resolveConfirmation()    // 确认环：改参数循环 / 消息总线等待 / IDE 竞速
6) 确认结果 → updatePolicy()（Always Allow 持久化）→ Scheduled → executor 执行
```

- BeforeTool **先于**策略与确认环（PR #21146 重构点：从 ToolExecutor 挪进 MessageBus 主循环，避免双重执行；CONFIRMED 源码 + PR body）。
- 非交互（headless）行为：`checkPolicy()` 中若 decision==ASK_USER 且 `!config.isInteractive()` → **直接 throw**（消息原文：requires user confirmation, which is not supported in non-interactive mode）→ 工具调用以错误收场（等价 DENY，fail-closed）。（CONFIRMED 源码 scheduler/policy.ts + 文档 In non-interactive mode, this is treated as deny）。
  另：`PolicyEngine` 构造时 `defaultDecision = interactive ? ASK_USER : DENY`，headless 下无规则命中也是 DENY。

### 2. ASK_USER 如何到 UI（消息总线，CONFIRMED 双路径）

- **调度器路径（现行主路径）**：`resolveConfirmation` → 状态机置 `AwaitingApproval`（携带 confirmationDetails + correlationId）→ `waitForConfirmation(messageBus, correlationId)` 订阅 `TOOL_CONFIRMATION_RESPONSE` 等待用户答复（IDE 侧经 ideConfirmation Promise 竞速）。TUI 渲染 AwaitingApproval 状态并回发总线消息。
- **工具侧遗留路径（PR #10630）**：`BaseToolInvocation.shouldConfirmExecute()` 发 `TOOL_CONFIRMATION_REQUEST` → 总线 → `PolicyEngine.check()` → ASK_USER → CoreToolScheduler 回 `requiresUserConfirmation=true` → 工具返回 null 哨兵 → 落到 legacy 确认 UI。
- 总线消息类型（CONFIRMED confirmation-bus/types.ts）：`TOOL_CONFIRMATION_REQUEST/RESPONSE`、`ASK_USER_REQUEST/RESPONSE`、`TOOL_POLICY_REJECTION`、`UPDATE_POLICY`、`TOOL_CALLS_UPDATE` 等。
- **超时语义不对称**（CONFIRMED tools.ts getMessageBusDecision）：30s 超时 → 默认 ask_user（弹确认，不自动放行）；AbortSignal 中止 → deny。调度器路径无显式超时（源码注释建议调用方用 AbortSignal.timeout）。

### 3. 规则匹配（CONFIRMED policy-engine.ts ruleMatches + check）

- 条件：`modes`（approval mode 过滤）、`subagent`、`mcpName`（身份或 *）、`toolName`（精确 / * / mcp_* / mcp_<server>_* / mcp_*_<tool> 通配 + MCP 短名/全名互转）、`toolAnnotations`（全部 key-value 匹配）、`argsPattern`（对 stableStringify(args) 排序后 JSON 的正则）、`interactive`（true=仅交互 / false=仅 headless）。
- `commandPrefix` 是语法糖：转成 `"command":"<prefix>` 开头的 argsPattern（**前缀匹配，不是子串**；CONFIRMED utils.ts buildArgsPatterns，前缀后必须跟空白/引号防 git 命中 gitstatus）。`commandRegex` 同构（锚点作用于整段 JSON，文档建议避免 ^）。
- **优先级**：`final_priority = tier_base + toml_priority/1000`；tier 常量（CONFIRMED config.ts）：Default=1、Extension=2、Workspace=3（当前禁用）、User=4、Admin=5。构造时按 priority 降序排序，`check()` 按序求值**第一个命中即赢**（break）；同优先级靠 JS 稳定排序保持插入序（先加者赢）。**文档示例数字已过期**（文档写 User 100→3.100，源码 User=4→4.100，文档自相矛盾）。
- **多规则组合**：规则之间不累积，最高优先级命中者一锤定音；但 shell 命令会**递归拆分**子命令逐段求值（DENY 任意处即 DENY；ASK_USER 降级 ALLOW；重定向把 ALLOW 降级 ASK_USER，除非 allowRedirection 或 AUTO_EDIT/YOLO）；safety checkers 在规则后追加（DENY→deny，ASK_USER→ask，**checker 抛异常→DENY，fail-closed**）。

### 4. 规则加载位置（CONFIRMED config.ts getPolicyDirectories + toml-loader.ts）

- 目录优先级（低→高）：内置 default policies → workspace（settings.workspacePoliciesDir，禁用中）→ user（`--policy` 或 `~/.gemini/policies/*.toml`）→ admin（`--admin-policy` / adminPolicyPaths + 系统目录：Linux /etc/gemini-cli/policies、macOS /Library/Application Support/GeminiCli/policies、Windows C:/ProgramData/gemini-cli/policies）。
- 系统目录安全校验（owner=root、不可被组/其他写），不通过则整目录忽略；补充 admin 路径若系统目录已有 .toml 则整体忽略（防 flag 覆盖，security guard）。
- settings.json 同层可注入规则：mcp.excluded/allowed、tools.core/exclude/allowed/confirmationRequired、mcpServers.*.trust、policyPaths、adminPolicyPaths、disableAlwaysAllow。

### 5. Hooks 生命周期（CONFIRMED docs + hookRunner/hookAggregator/hookTypes）

- 定义：settings.json `hooks`；事件组 {matcher(正则/精确), sequential, hooks[]}；hook {type:command, command, name, timeout(默认 60000ms), description}。
- 通信：stdin 收 JSON 输入，stdout 只允许最终 JSON；exit 0=成功（解析 stdout）、exit 1=warning（放行+警告）、**其他非零（含 2）=系统阻断**（stderr 作为 reason 返回给 agent，本轮继续）。（CONFIRMED hookRunner.ts：EXIT_CODE_SUCCESS=0 / NON_BLOCKING=1 / 其余→decision=deny）。
- 决策语义（CONFIRMED hookTypes.ts）：decision ∈ allow/deny/block/**ask**（PR #21146，isAskDecision()）；continue:false=杀整个 agent loop（shouldStopExecution()）；hookSpecificOutput.tool_input 与模型参数 merge/override 后经 tool.build() 重建（校验失败→INVALID_TOOL_PARAMS）；deny 的 reason 作为工具错误回喂 agent。
- AfterTool：可 deny（隐藏真实输出、reason 替换结果）、追加 additionalContext、请求 tailToolCallRequest（立即追加执行另一工具）、continue=false 杀循环。
- 聚合（CONFIRMED hookAggregator.ts OR 逻辑）：**任意 block 胜 → 其次任意 ask → 默认 allow**；多 hook 并行/串行由 sequential 控制。
- hook source：project | user | system | extension（CONFIRMED types.ts getHookSource）。

### 6. 机器接口（CONFIRMED / 部分 UNVERIFIED）

- TOML 规则 schema（CONFIRMED toml-loader zod schema + 文档）：`[[rule]]` 字段 = toolName(str|array, 必填)、subagent、mcpName、argsPattern、commandPrefix(str|array)、commandRegex（与 prefix 互斥）、decision(allow|deny|ask_user, 必填)、priority(int 0-999, 必填)、modes[]、interactive、toolAnnotations{}、allowRedirection(兼容 allow_redirection)、denyMessage(兼容 deny_message)。另有 [[safety_checker]]（in-process / external 两类）。
- 决策输出：内部 TS 类型 CheckResult{decision, rule?}，**无公开 JSON dump / audit CLI**（UNVERIFIED 官方审计接口；文档未见）。可脚本化审计路径 = hooks 的 Notification(ToolPermission) 事件做外部落盘（CONFIRMED 文档）。

## Maturity

- CONFIRMED：上述机制均读到 raw 源码/文档原文（2026-09-01 抓取，main HEAD）。
- CONFIRMED：policy engine 是活跃演进模块（2025-10 PR #10630 接 UI、2026-03 PR #21146 加 hook ask、scheduler 重构为 packages/core/src/scheduler/）。
- STRONG_REPORT：#18186 显示 workspace-tier policies 失效且用户反复确认（见下节）。
- CONFIRMED：文档公开标注 Workspace tier currently non-functional —— 不是隐藏缺陷，是当前设计状态（文档与源码一致）。

## Failure Mode

- CONFIRMED（源码）：**畸形 policy 文件 fail-OPEN（单文件级）**——TOML 解析错 / schema 校验错 → 该文件规则整体丢弃（其余文件继续加载），错误只经 coreEvents.emitFeedback 弹 UI 警告，不中止、不 fail-closed。规则级错误（commandPrefix 配错 toolName 等）仅记录警告，该规则**仍会被转换生效**（toml-loader 只记 error 不 skip）。
- CONFIRMED（源码）：正则编译失败 / ReDoS 启发式（>2048 字符、嵌套量词）→ 该规则丢弃。
- CONFIRMED（源码）：**hook ask 无条件覆盖策略决策**——`if (hookDecision===ask) decision=ASK_USER` 对 DENY 同样生效（PR 意图只写覆盖 ALLOW，源码为无条件）；用户确认后可能放行被策略 DENY 的调用。对 hook 作为逃生层必须低于 admission gate 的架构是反面教材。
- CONFIRMED（源码）：headless 下 ASK_USER→throw→调用失败（fail-closed），但 **interactive 无规则命中默认 ASK_USER 而非 DENY**——deny-by-default 只存在于 headless。
- STRONG_REPORT：#18186 workspace .gemini/policies 不生效（见下节）。
- CONFIRMED（源码推论）：工具侧 30s 超时默认 ask_user（弹确认）而非 deny——超时≠拒绝。

### Workspace-tier 现状（#18186）

- 状态：**OPEN**，label priority/p3（backlog）+ area/enterprise，16 个 👍，创建 2026-02-03；标题 Workspace/.gemini/policies/*.toml are not taking effect.（CONFIRMED，api 抓取）。
- 文档（CONFIRMED）：policy-engine.md 明确 WARNING —— Workspace tier 当前 non-functional，**workaround = 用 User（~/.gemini/policies）或 Admin 策略**。
- 评论（STRONG_REPORT）：同一 .toml 放 ~/.gemini/policies 生效、放 workspace .gemini/policies 无效；在 workspace settings.json 加 policyPaths 也无效。
- 源码侧（CONFIRMED）：tier 常量/优先级管线都在（WORKSPACE_POLICY_TIER=3；ALWAYS_ALLOW_PRIORITY = 3 + 0.95 = 3.95 恰落在 workspace 层；createPolicyUpdater 在 trusted folder 时把 Always Allow 持久化到 workspace scope）——**管线在，自动发现/加载被禁**（根因已证实：CLI 侧 `disableWorkspacePolicies = true` 临时 flag，见 Authority Provenance 节），故 repo 内 .gemini/policies 文件不产生 enforcement。

## Authority Provenance（谁能写 policy / 批准如何被机器证明）

> 2026-09-01 追加（吸收原 follow-up 补充 7，置于模板标准位）。新增 sources：[cli/config/policy.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/cli/src/config/policy.ts)（resolveWorkspacePolicyState）、[policy/integrity.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/policy/integrity.ts)、[config/storage.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/config/storage.ts)、[hooks/trustedHooks.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/hooks/trustedHooks.ts)、[PR #18682](https://github.com/google-gemini/gemini-cli/pull/18682)（merged 2026-02-20）、[PR #19707](https://github.com/google-gemini/gemini-cli/pull/19707)（merged 2026-02-20）、Issue [#29053](https://github.com/google-gemini/gemini-cli/issues/29053)、[#27367](https://github.com/google-gemini/gemini-cli/issues/27367)、[#25283](https://github.com/google-gemini/gemini-cli/issues/25283)。

### 批准（ASK_USER 确认）存哪里、持久化到哪个 scope

- ProceedOnce（仅本次）：内存 + transcript，不落盘（CONFIRMED）。
- Always Allow（会话级）：内存规则，source=Dynamic (Confirmed)（CONFIRMED config.ts）。
- Always Allow and Save：updatePolicy → createPolicyUpdater 写 `auto-saved.toml`（atomic 写 tmp+rename、损坏备份 .bak）；persistScope = trusted folder 且有 workspacePoliciesDir → workspace（`<proj>/.gemini/policies/auto-saved.toml`），否则 user（`~/.gemini/policies/auto-saved.toml`）（CONFIRMED scheduler-policy.ts + config.ts + storage.ts）。
- **持久化规则零 provenance 元数据**：createTomlRule 只写 decision/priority/toolName/mcpName/commandPrefix/argsPattern/allowRedirection/modes——无时间戳、无用户、无 session（CONFIRMED config.ts）。

### 批准绑定与复用（TOCTOU 面）

- 绑定 = toolName + 参数模式（shell=commandPrefix 解析后的 root command；edit=file_path argsPattern；MCP=server+tool 或 server 全量）+ modes 传递性（plan<default<autoEdit<yolo）；敏感工具强制 narrowing；**不绑定调用实例**（CONFIRMED scheduler-policy.ts + types.ts MODES_BY_PERMISSIVENESS + config.ts）。
- **同前缀复用是设计语义**：批准后同一 prefix 下任意新参数命中（CONFIRMED）。已知过宽 bug：`commandRegex` 无锚点可跨 JSON 字段匹配（`.*` 跨出 command 值），commandPrefix 有 `(?:[\s"]|\\")` 边界（STRONG_REPORT #29053，open）。
- 检查时点：BeforeTool 改参后**重新**过策略；检查与执行之间**无二次校验**；client-initiated 调用 ASK_USER→直接 ALLOW 是绕过面（CONFIRMED 源码）。

### Trust boundary（谁能写 policy）

- User `~/.gemini/policies`：主目录普通文件，**无写保护、无校验**（CONFIRMED storage.ts + toml-loader 仅对 Admin 目录做权限检查）。
- Workspace `.gemini/policies`：被 `disableWorkspacePolicies=true` 临时 flag 整体禁用（#18186 根因，CONFIRMED cli/config/policy.ts）；`settings.workspacePoliciesDir` 显式配置仍可加载（Tier 3，CONFIRMED config.ts + workspace-policy.test.ts）。
- Admin 系统目录：owner 必须 root/UID 0 且组与其他不可写（Linux/macOS，如 chmod 755；Windows 须在 C:/ProgramData 且 Users/Everyone 无 Write/Modify/Full Control），不通过则整目录忽略；补充 admin 路径（--admin-policy）不受该校验 + security guard 防 flag 覆盖（CONFIRMED 文档 + config.ts）。
- 项目级 hooks 需显式 trust（`~/.gemini/trusted_hooks.json`，TrustedHooksManager）；agent/模型不能写 policy 文件（只读加载）（CONFIRMED）。

### 篡改防护 / 静默失效

- **PolicyIntegrityManager**（SHA-256 dir hash：文件名+内容 → `~/.gemini/policy_integrity.json`，key=scope:identifier）：PR #18682 实现；行为 = MATCH 静默加载 / NEW(0 文件) 忽略 / 变更或新建→交互弹 UI 显式接受、**非交互 warn+自动接受加载（fail-open）**；当前被同 flag 关闭（CONFIRMED cli/config/policy.ts resolveWorkspacePolicyState）。
- **pin 与 user policies 同信任域**（同目录同权限）——只防项目内 drift，不防能写 home 的攻击者（CONFIRMED storage.ts）。
- 无 git 追踪（~/.gemini 非 repo）；symlink 的 policy 文件被静默忽略（main 只收 isFile()；PR #20289 未合并——STRONG_REPORT）；#27367（closed）auto-saved.toml 规则被 ReDoS 启发式拒绝、#25283（open）generic denied 无因由（STRONG_REPORT）。
- AEDL 对照：同信任域 pin + headless auto-accept = L2 的失败原型 → **锚定 human-promoted git 状态**；exception 绑 envelope hash + 参数、参数变化重验；不采纳自管 pin / headless 自动接受 / 无 provenance 的批准落盘。

## AEDL Adaptation

- 吸收 1（决策模型，已有切片再确认）：ALLOW / DENY / ESCALATE(ASK) 三元 = Gemini 的 allow/deny/ask_user；headless 无人工时 ASK→DENY（fail-closed）与 AEDL `admit.py` 的 BLOCKED+升级协议同构。
- 吸收 2（**优先级分层**）：借鉴 tier 公式 final = tier_base + intra/1000 —— AEDL 可在 admit 结果里引入层（base 漂移层 > dirty 层 > 默认层），层内再给 0-999 细粒度，天然表达硬规则压软规则。落点：`tools/admit.py` verdict 增加 tier 字段（先不改行为，只记账）。
- 吸收 3（参数级匹配）：Gemini 对 shell 命令用 `"command":"<prefix>` 前缀正则（防 git 命中 gitstatus 需后跟空白/引号），AEDL 可对照 `admit.py` 现有的路径模式匹配，对 envelope 的 scope 校验引入参数级精确匹配 + 前缀防误伤（commandPrefix 展开为正则 `(?:[\s"]|\\")` 后缀约束思路）。
- 吸收 4（审计面）：Gemini 靠 hook Notification(ToolPermission) 做外部留痕；AEDL 已有 receipt JSON 审计，可对照确认每次 admission 决策（含 ESCALATE 后的最终裁定）都落 JSON 即可，不必抄总线。
- 不做什么：
  - 不引入 Gemini CLI / 不依赖任何 vendor 的 project-policy 文件机制（#18186：repo 文件 ≠ enforcement）。
  - **不引入 hook 可覆盖 admission DENY 的逃生层**（Gemini hook-ask 无条件覆盖是反面教材；AEDL 的 exception flags 必须由 envelope 预授权，已正确）。
  - 不在 admit 加 30s 超时→ask_user 式语义：AEDL 超时应 fail-closed（超时=BLOCKED），无人在场时弹窗没有意义。

## Trigger

出现下述任一真实事件才动手：① AEDL 出现第一例想放行/想拦但二元模型表达不了的 admission 真实案例（对应既有切片 Trigger，此时才给 admit 加 ASK 中间态 + tier）；② 出现同一判定规则在多个任务间重复手写的事实（此时才抽规则文件 + 优先级层，且**只做 AEDL 自己的格式**）；③ 有人提议在 repo 内放第三方工具的 policy 文件来替代 enforcement（此时引用 #18186 拒绝）。

## 对 AEDL admit.py 的具体启示

- ① **匹配层级对照**：Gemini 匹配链 = toolName(含 wildcard) → mcpName(身份) → argsPattern(JSON 正则) → annotations；AEDL 目前以 envelope 的 path/条件匹配为主。可借鉴点：**先按对象身份（issue/PR/envelope）粗筛、再按参数级精筛**，避免 path 通配误伤（对照 commandPrefix 后缀约束）。
- ② **ASK-with-timeout 设计选项**：Gemini 交互态 ASK 有 30s 超时（超时→弹确认）与 headless ASK→DENY 两套语义。对 AEDL：**CI/无人工环境必须超时=BLOCKED**；若未来给 admit 加交互模式（本地 human-in-the-loop），可借鉴超时默认不放过而非 Gemini 的超时默认弹窗。
- ③ **优先级分层落地**：把 final = tier_base + intra/1000 直接映射为 `tools/admit.py` 的例外裁决顺序：envelope 预授权（最高层）> 策略文件（中层）> 默认 fail-closed（底层）。层内 0-999 保证同一层内可排序、跨层不可僭越；--allow-dirty/--allow-drift/--skip-deps 建议全部落到预授权层，与 Gemini User/Admin 永远压过 Workspace/Default 同构。
- ④ **fail-open 教训**：Gemini 畸形 policy 文件静默丢规则（只弹 UI 警告）→ 配置漂移无感知。AEDL 反例设计：**admit 配置若解析失败 → GATE_BROKEN（exit 2），而不是当无事发生**——与 `admit.py` 现有 exit 2 语义完全一致（admission 自身无法运行 = broken）。
- ⑤ **hook/策略分离原则**：Gemini 把机器阻断（hook deny / policy deny）与人工确认（ASK）放在同一决策变量上且 hook ask 可覆盖 policy deny。AEDL 应保持：**机器层（dev_gate/CI）的 BLOCKED 不可被任何 ask 降级**；人工放行只能走 envelope 预授权或 BLOCKED 升级记录，杜绝低层覆盖高层。
- ⑥ **不采纳清单**：不采纳 TOML 策略文件格式（无 schema 版本、静默失效）；不采纳全局 DENY 工具从模型记忆剔除（AEDL 是任务级 admission，不涉及 toolset 遮蔽）；不采纳 hook 的 60s 默认超时语义（AEDL 门禁应确定性）。

## 置信度说明

- `CONFIRMED` = 本次直接抓取 raw 源码/文档/PR/issue API 并读到原文（全部条目可回溯到 Primary sources）。
- `STRONG_REPORT` = issue 评论/PR 描述层面的用户证词或意图说明，未在源码完全定论（#18186 现象、PR 意图）。
- `UNVERIFIED` = 未找到公开接口或未验证因果链（如官方 policy 审计 CLI；workspace 因果已由 Authority Provenance 节定位到 disableWorkspacePolicies flag，不再 UNVERIFIED）。