# EDD-001 Engineering Design Sandbox 设计规格

**状态：** 用户已批准总体定义；实施前书面冻结

**日期：** 2026-09-01

**范围：** EDD-001 的封闭设计域、执行域、信任域与跨层状态控制平面

## 1. 目标

AEDL Sandbox 不是一个泛化的“安全运行目录”，而是一个受约束的硬件工程执行域。它必须限制 Agent：

- 能看到什么工程知识；
- 能选择什么器件和拓扑；
- 能使用哪些引脚和参数；
- 能修改哪些候选文件；
- 能调用哪些本地工具；
- 能产生哪些输出；
- 哪些结论需要独立验证；
- 哪些状态晋升必须由人工批准。

首个适用域是 `EDD-001`。其核心、供电、USB 与 CORE_BASE 已由人工收敛，不允许 Agent 在运行中重新选型或重新发明基础拓扑。

## 2. 冻结定义

> **AEDL Sandbox 是由哈希绑定合同定义、默认拒绝的封闭硬件工程执行域；它分别隔离设计自由度、执行能力和可信度，并由跨层状态控制平面保证冻结对象不可原地变异。任何未声明、未取证、未支持或未覆盖验证的行为一律停止；所有产物先成为候选，只有通过独立验证和规定的人工审批后才能晋升。**

等价短式：

```text
AEDL Sandbox
= Design Domain Isolation
+ Execution Isolation
+ Trust Isolation
+ Cross-layer State Control
```

## 3. 三层 Sandbox 与状态控制平面

```text
                 State Control Plane
       run_id / hashes / lifecycle / recovery
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
  Design Sandbox   Execution Sandbox   Trust Sandbox
  能设计什么         能怎么动手           什么值得相信
```

### 3.1 Design Sandbox

Design Sandbox 隔离硬件设计自由度，至少包含：

1. **器件域**：只能使用明确允许的精确 MPN、封装、角色与使用条件。
2. **拓扑域**：只能组合合同中声明的电路块、端口、网络和不变量。
3. **引脚域**：区分 allowed、reserved、soft-reserved 与 hard-forbidden。
4. **参数域**：电压、电流、阻值、频率、温度等必须有单位、范围和适用条件。
5. **能力域**：compiler 与 verifier 必须明确声明支持范围；未覆盖即停止。

`LED_GENERIC`、`BUTTON_GENERIC` 一类符号只允许停留在需求或 HIR 层。进入 KiCad 编译前必须解析为精确器件、封装、引脚和冻结证据，否则返回 `BLOCKED_COMPONENT_RESOLUTION`。

### 3.2 Execution Sandbox

Execution Sandbox 隔离 Agent 的动作能力：

- Agent 只能向候选工作区写入；冻结合同、冻结证据和已晋升设计只读。
- Agent 不直接手写 `.kicad_sch` 或 `.kicad_pcb`；先生成 HIR，再由确定性 compiler 写候选工程文件。
- 只允许调用带版本与能力声明的白名单工具。
- 任意 shell、任意路径写入、未声明工具和网络访问默认拒绝。
- 正式 EDD-001 运行时默认离线；外部资料检索、下载、许可证核对和证据摄取属于 Sandbox 外部流程。
- V1 的“离线”首先由不暴露网络工具、拒绝网络能力请求和白名单本地工具实现；在没有 OS/容器级 egress 证明前，不宣称具备对抗恶意进程的系统级网络隔离。

### 3.3 Trust Sandbox

Trust Sandbox 隔离结论可信度：

- 工程事实必须标明 `VERIFIED_SOURCE`、`UNVERIFIED_SOURCE`、`MODEL_PRIOR` 或 `HUMAN_INPUT`。
- `MODEL_PRIOR` 不能单独支持硬件工程事实。
- compiler 输出必须由独立解析器重新读取最终工程文件，再执行合同、ERC、DRC、几何和仿真检查。
- compiler 与 verifier 不得只消费同一份 HIR 后互相证明。
- 缺 datasheet、缺哈希、缺 verifier coverage、缺工具输出或证据损坏时不得晋升。
- 新器件、设计域扩张、替换 VERIFIED_BLOCK、制造输出和制造签发需要人工批准。

### 3.4 State Control Plane

状态控制平面横跨三层，记录：

- `run_id`、`domain_id`、合同 bundle hash；
- baseline、candidate 与 parent hash；
- 当前阶段、修复次数、finding fingerprint 与停滞状态；
- policy decision、tool result、verification result 与 evidence receipt；
- human interrupt、resume value 与最终状态。

任何 `VERIFIED_BLOCK` 内容变化都必须创建新的 candidate 和 content hash；旧 evidence receipt 自动失效。禁止原地修改后继续保留 `VERIFIED` 标签。

## 4. 判定语义

所有策略判断只允许三种结果：

```text
ALLOW
DENY
BLOCKED
```

- `ALLOW`：动作在声明域内，所需证据、compiler 与 verifier coverage 齐全。
- `DENY`：已知违反合同，例如使用 GPIO36、调用未授权工具或写入候选根目录之外。
- `BLOCKED`：当前无法证明，例如缺数据手册、参数规则未定义或验证器不覆盖。

三者必须带稳定的 `reason_code` 和结构化 findings。`DENY` 与 `BLOCKED` 都停止执行，但不得混淆事实含义。

## 5. 多维状态而非单一 VERIFIED 枚举

Artifact 至少分开记录：

```yaml
lifecycle_status: DRAFT | CANDIDATE | REJECTED | PROMOTED | FROZEN
verification_status: NOT_RUN | PASS | FAIL | BLOCKED
approval_status: NOT_REQUIRED | PENDING | APPROVED | REJECTED
evidence_status: MISSING | PARTIAL | COMPLETE | INVALID
```

任何一轴为未知或阻塞，都不能用另一轴的绿色状态覆盖。例如 `lifecycle_status=FROZEN` 只代表范围冻结，不代表 datasheet 已核实或制造已批准。

## 6. 数据流

```text
Frozen Contract Bundle
        ↓ preflight
Sandbox Policy Decision
        ↓ ALLOW only
Candidate Workspace
        ↓
HIR / deterministic compiler
        ↓
Candidate KiCad / firmware artifacts
        ↓ independent read-back
ERC / DRC / contract / simulation / firmware checks
        ↓
Structured Findings
   ↙ FAIL/BLOCKED       PASS ↘
Repair Planner          Human Review
   ↓ bounded loop             ↓
new Candidate            Promote / Reject
```

修复循环必须有最大次数、重复 finding fingerprint 检测和停滞熔断。修复在候选工作区中进行，失败候选保留为审计证据或安全丢弃，不修改冻结 baseline。

## 7. LangGraph 的边界

LangGraph 只承担：

- 状态图和条件路由；
- checkpoint 与进程恢复；
- 有上限的修复循环；
- human interrupt / resume；
- 节点事件与审计流。

LangGraph 不承担硬件正确性判断。合同解析、策略决策、ERC/DRC、仿真结果解析、证据哈希与晋升判断均由 AEDL 确定性模块完成。

由于 interrupt 恢复时节点可能重新执行，所有有副作用节点必须幂等；人工中断必须发生在写入或晋升动作之前。

## 8. 开源能力映射

- **LangGraph / CircuitBot**：状态图、条件边、修复路由与交互恢复。
- **kicad-happy**：确定性 KiCad 解析、结构化 finding 与 evidence envelope。
- **boardsmith**：HIR、provenance、bounded repair 与 stall detection 思路；AGPL 代码不复制。
- **NextBoard**：阶段 Gate 与独立 Reviewer；许可证未澄清前只借鉴流程。
- **KiCadAI**：能力预检、证据绑定和 RecordedProvider 测试模式。
- **KiCad MCP**：EDA 工具适配与错误语义；判决体系不外包。
- **NeuroBoard**：事件流与产品交互经验；许可证冲突和弱验证部分不吸收。

AEDL 自研边界是 Sandbox Contract、三态策略语义、跨层状态控制、独立验证、证据晋升与人工制造签发。

## 9. V1 非目标

- 不实现任意硬件品类生成。
- 不执行正式 B1/U3 ECO，不修改 M2。
- 不宣称 OS/容器级对抗恶意代码隔离已经完成。
- 不实现真实 LLM 自主补丁；V1 用可替换 RepairPort 和确定性修复 fixture 证明多轮循环。
- 不把 ERC/DRC、Wokwi、SPICE 或静态合同表述为实体板验证。
- 不设置 `manufacturing_release=true`，不执行下单。

## 10. V1 验收

V1 至少证明：

1. 未声明器件和禁用引脚被 `DENY`。
2. 缺 datasheet、缺 POWER 合同和缺 verifier coverage 被 `BLOCKED`。
3. 未授权工具、网络能力、候选根之外写入和 Agent 直接写 KiCad 被 `DENY`。
4. 合法候选只能在 run/candidate 工作区生成。
5. 相同 findings 连续出现会触发 stall；达到修复上限会终止。
6. human interrupt 可持久化并恢复，且不会重复执行前置副作用。
7. VERIFIED_BLOCK 发生变化时旧 evidence receipt 失效。
8. 当前 EDD-001 资料不完整时如实保持 `BLOCKED`，不使用示例数据制造假 PASS。
