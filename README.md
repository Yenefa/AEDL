# AEDL

**Autonomous Engineering Design Loop · 自主嵌入式工程研发闭环**

AEDL 探索如何在明确的人类审批边界内，把自然语言需求转化为可审计的嵌入式设计候选，并让需求合同、EDA 产物、固件、验证器和 Evidence 保持可追溯。

**北极星**：AEDL 的最终目标是**在受控工程流程下正确交付实体板卡**——从自然语言需求出发，经过可审计的设计闭环，产出能一次做对、可追溯的硬件。直接生成 PCB 不难，难的是让结果可信：M2 载板在终检时暴露的六项硬件语义缺陷（USB D+/D- 接反、SHT30 ADDR 悬空等，PIT-20260830-001）证明，生成器自证与文件一致性无法保证正确性。因此 AEDL 把“做板子”工程化为可验证闭环，并以 **EDD-001** 作为第一块在 Sandbox 验证下设计的兑现板。

本仓库是 AEDL 的**集成与技术主张真源**。当前已经具备确定性合同、失败关闭门禁、候选/证据隔离、M2 硬件载体和软件验证基线；它仍不是一个已经完成、可以无人监督下单的通用硬件 Agent。

## Human-directed, AI-assisted · 人类主导，AI 辅助

AEDL is human-directed and AI-assisted.
The project owner defines product scope, acceptance criteria, architecture boundaries, verification policy, engineering claims, and release decisions.
AI agents are used for research, implementation, testing, documentation, and adversarial review.

AEDL 由人类主导、AI 辅助：项目负责人定义产品范围、验收标准、架构边界、验证政策、工程主张与发布决策；AI Agent 承担研究、实现、测试、文档与对抗性审查。

| Area | Owner |
| --- | --- |
| Product direction | Yenefa |
| Scope / acceptance criteria | Yenefa |
| Architecture approval | Yenefa |
| Verification policy | Yenefa + Percy (SHARED) |
| Engineering claims | Yenefa |
| Final merge / release | Human review + human merge; release sign-off: Yenefa |
| Implementation assistance | AI-assisted |
| Testing / adversarial review | AI-assisted |
| Documentation assistance | AI-assisted |

> Ownership here means **decision and approval authority, not sole authorship**. Implementation, research, tests and documentation in this repository are routinely AI-assisted, and every AI contribution stays on the record.
> 这里的 Owner 指**决策与批准权，不是"唯一作者"**；仓库的实现、研究、测试与文档普遍由 AI 协助完成，全部记录保留可追溯。
>
> 逐条职责与证据：[Human Ownership](docs/HUMAN_OWNERSHIP.md) · 归因分类与红线：[Attribution Policy](docs/compliance/ATTRIBUTION_POLICY.md) · AI 使用聚合视图：[AI Usage Summary](docs/compliance/AI_USAGE_SUMMARY.md)。

## 当前真实状态

> README 只描述稳定边界，不复制会过期的门禁计数。每次接手请以 [HANDOFF](docs/HANDOFF.md)、[Evidence Index](docs/evidence/EVIDENCE_INDEX.md) 和当前结构化门禁结果为准。

| 范围 | 当前边界 | 权威入口 |
| --- | --- | --- |
| M2 ESP32-C3/SHT30 设计 | 已有原理图、PCB、制造导出物和机器/静态验证记录；**物理线已冻结（2026-09-01 裁决：不再下单/重签/换料）**，其验证机制保留为 Sandbox 地基 | [M2 硬件目录](src/hardware/m2-board/)、[HANDOFF](docs/HANDOFF.md) |
| 制造放行 | **BLOCKED**；`manufacturing_release=false`，尚未重新人工签发，不得据旧记录下单 | [board_review_v1.json](gates/board_review_v1.json) |
| 数据手册合同 | 仍有人工签发项；自动检查不能替代具名工程复核 | [硬件 Evidence](src/hardware/m2-board/evidence/)、[HANDOFF](docs/HANDOFF.md) |
| 实体板验证 | **NOT_RUN**；上电、功耗、BLE、传感器精度、USB 眼图、瞬态与长期稳定性仍待回件 | [Evidence Index](docs/evidence/EVIDENCE_INDEX.md) |
| EDD-001 自主设计闭环 | Sandbox 运行时已实现；真实 preflight 对缺失资料、POWER 合同、compiler 和独立 verifier 保持失败关闭 | [Sandbox 设计规格](docs/superpowers/specs/2026-09-01-edd001-engineering-design-sandbox-design.md)、[HANDOFF](docs/HANDOFF.md) |

没有当前 Evidence 支撑的性能、可制造性或自主能力，不应从历史 PASS、文件存在或工具清单中推导。

## 系统边界

```text
自然语言需求
  → 可签发需求合同
  → 受约束的设计候选
  → EDA / firmware compiler
  → 独立 read-back verifier
  → content-addressed Evidence
  → 人工 Review / 晋升 / 制造决策
```

核心原则：

- **失败关闭**：`UNKNOWN`、缺资料或证据失配不能降级为 PASS。
- **候选不污染基线**：设计变更先进入 candidate，冻结 baseline 不原地改写。
- **验证器独立**：生成器自报成功不能代替独立解析与对抗性验证。
- **人机权限分离**：Agent 可以生成、诊断和验证；人工保留候选晋升、制造签发、下单和最终 Review。
- **证据分级**：静态检查、仿真、软件 loopback 与实体硬件结果分别记录，不能互相冒充。

## 从这里开始

### 推荐阅读顺序

```text
README.md
  ↓  docs/HUMAN_OWNERSHIP.md                    人类职责、决策权与验收权
  ↓  docs/compliance/DECISIONS.md               架构与治理决策（ADR）
  ↓  技术文档（HANDOFF / COLLABORATION / CONTROL_PLANE / Evidence）
  ↓  docs/compliance/AI_USAGE_SUMMARY.md        AI 使用的工作单元聚合视图
  ↓  docs/compliance/AI_USAGE_LOG.md            完整可审计索引（逐条真源在 ai-usage/）
```

AI 台账是**审计层**，不是入门读物：先看清"谁做决策、谁验收"，再看 AI 如何协助。

### 人类开发者

1. 阅读 [HANDOFF](docs/HANDOFF.md) 获取最新分支、阻塞项和验证状态。
2. 阅读 [协作协议](docs/COLLABORATION.md)，从当前协作基线创建 Issue 对应的任务分支。
3. 一个 Issue 只设一个 Owner 和一组独占写路径；通过 Draft PR 交接给另一名真人 Review。

不要仅凭 GitHub 默认分支名判断当前完整工作线；协作基线以 HANDOFF 为准。

### AI Agent

新会话 / 新 clone 先读根目录 [AGENT_ONBOARDING.md](AGENT_ONBOARDING.md)：环境自检（autocrlf /
Python 3.9 / uv / gh）、AECP 生命周期速查与红线。然后，在产生任何实质贡献前，必须依次完整读取：

1. 根目录 [AGENTS.md](AGENTS.md)；
2. [docs/HANDOFF.md](docs/HANDOFF.md)；
3. [docs/COLLABORATION.md](docs/COLLABORATION.md)；
4. 当前 Issue / PR 的 Goal、Scope、Owned paths 和 Acceptance Criteria。

硬件发布、BOM、原理图、PCB 或制造任务还必须读取 [PROJECT_PITFALLS](docs/knowledge/PROJECT_PITFALLS.md) 与 [IMPROVEMENT_SYSTEM](docs/knowledge/IMPROVEMENT_SYSTEM.md)。

## 安全验证入口

以下命令不会被 README 宣称为实体硬件验证：

```powershell
# 主仓库确定性单元/集成测试
py -3 -S -m unittest discover -s tests

# Sandbox 运行时测试
uv run --frozen --project sandbox_runtime python -m unittest discover -s sandbox_runtime/tests -p "test_*.py"

# 真实 EDD-001 preflight；存在资料/覆盖缺口时应返回 BLOCKED
uv run --frozen --project sandbox_runtime python -m aedl_sandbox.cli preflight --repo-root . --domain EDD-001
```

完整 M2 runner 会刷新 `notes/m2-evidence-reset/` 下的运行证据。只有在 Issue 明确拥有 Evidence 写路径、已保存旧批次并准备记录新运行时，才执行：

```powershell
py -3 gates\run_gates.py
```

不得为了得到绿色输出，在普通文档或协作任务中原地重跑并覆盖证据。

## 双仓库结构

| 仓库 | 责任 | 不承担的责任 |
| --- | --- | --- |
| [`Yenefa/AEDL`](https://github.com/Yenefa/AEDL) | 集成代码、工程合同、ADR、合规台账、比赛主张与正式 Evidence 索引 | 不把未经晋升的实验结果直接包装成产品能力 |
| [`Yenefa/AEDL-spike`](https://github.com/Yenefa/AEDL-spike) | 协议执行器实验、故障注入样例和过程 Evidence 卫星 | 不单独决定主仓架构、制造放行或比赛技术主张 |

卫星成果回流主仓时，必须引用精确 spike commit、文件路径、限制和复现方法，并通过主仓 Issue 与另一名真人 Review 的 PR。当前卫星治理见 [`AEDL-spike` Draft PR #2](https://github.com/Yenefa/AEDL-spike/pull/2)。

## 项目结构

| 路径 | 内容 |
| --- | --- |
| `src/hardware/m2-board/` | M2 intent、KiCad 原理图/PCB、硬件 Evidence 合同 |
| `src/firmware/` | 固件源码 |
| `gates/` | 失败关闭门禁、合同与制造放行真源 |
| `sandbox_runtime/` | Design / Execution / Trust 三层 Sandbox 运行时 |
| `tests/` | 主仓库确定性测试与对抗性夹具 |
| `notes/` | 机器生成的运行批次、manifest 与原始证据 |
| `delivery/` | 当前制造导出物；存在不等于获准下单 |
| `docs/evidence/` | 可验证主张与原始证据索引 |
| `docs/compliance/` | AI 使用、第三方资源、ADR 与贡献边界 |
| `docs/competition/` | 融合图、开放成果和提交检查资产 |
| `web/` | 需求澄清工作台 |
| `tools/` | 建板、布线、导出、评审和文档工具 |

## 协作与审计

标准路径是：

```text
Issue → task branch → exact-path staging → tests → Draft PR
      → another human review → merge decision
```

- 正式团队成员、AI 贡献和第三方资源分别登记，不能混写成“全部团队自研”。
- AI 的实质贡献按**可审计工作单元**逐条记录在 [docs/compliance/ai-usage/](docs/compliance/ai-usage/)；默认浏览入口是 [AI_USAGE_SUMMARY.md](docs/compliance/AI_USAGE_SUMMARY.md)（工作单元聚合），完整索引为 [AI_USAGE_LOG.md](docs/compliance/AI_USAGE_LOG.md)（脚本生成，禁手改）。审核状态保持 `PENDING_HUMAN_REVIEW`。
- 关键决策见 [DECISIONS](docs/compliance/DECISIONS.md)，第三方与许可证边界见 [THIRD_PARTY_RESOURCES](docs/compliance/THIRD_PARTY_RESOURCES.md)。
- 仓库当前的具体分支策略与 GitHub 强制能力边界见 [协作协议](docs/COLLABORATION.md)。

## 许可

AEDL 自研代码与文档按 [Apache License 2.0](LICENSE) 发布；第三方归因与再分发边界见 [NOTICE](NOTICE) 和 [THIRD_PARTY_RESOURCES](docs/compliance/THIRD_PARTY_RESOURCES.md)。冻结的数据手册、图纸和其他外部资料版权归各权利人，本仓库不将其声明为团队作品。
