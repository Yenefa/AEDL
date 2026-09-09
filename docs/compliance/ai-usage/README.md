# ai-usage/ — AI Usage 台账条目真源（GH-49 / ADR-012）

一个文件 = 一个可审计工作单元。文件名 = 条目 ID，
标题必须是 `## <同一 ID>`，否则 `dev_gate` 的 `ai_usage_ledger` 检查 fail-closed。

## 新增条目（三步）

1. `python -m tools.build_ai_usage_index new --actor CODEX --summary "任务名称"`。
   工具生成 `AI-YYYYMMDD-<ACTOR>-<RANDOM>.md`，RANDOM 为 32 位大写 hex（128 bit），
   默认本地日期，可显式给 `--date YYYY-MM-DD`。补齐 AI 工具/模型、参与标签、产出、
   实际验证和限制；人工审核保持 `PENDING_HUMAN_REVIEW`。
2. 完工后运行 `python -m tools.build_ai_usage_index build` 重建索引。
3. 检查 diff 和门禁后，按既有授权规则提交。生成器用排他创建防止本地覆盖，碰撞重试；
   随机性支持同 actor 多分支/多机器独立分配，但不是跨分支锁或数学上的零碰撞。

## 粒度：一个可审计工作单元，不是一个 prompt

- **一个 work unit = 一个可审计工作单元**（一个 Issue / PR / 同一目标的连续多轮活动），不是一次对话、一次 prompt 或一次重跑。
- 同一 Issue / PR、同一目标的多轮 AI 交互**应聚合为一条记录**；不要为每一步追问单独开条目。
- 只有一次会话横跨多个互不相关的目标时，才拆成多条记录。
- 历史条目按原样保留：不重写、不合并、不删除、不追溯改号。
- 粗粒度浏览走 [`../AI_USAGE_SUMMARY.md`](../AI_USAGE_SUMMARY.md)（工作单元聚合视图，人工维护，只引用 ID）；
  本目录的 `<ID>.md` 是逐条真源；`AI_USAGE_LOG.md` 是生成索引，供审计与 `[AI-...]` 标签解码。

## 规则

- `AI_USAGE_LOG.md` 是生成索引，**禁止手工编辑**（会被覆盖 + 门禁拦截）。
- 新增条目后，把该 ID 归入 `../AI_USAGE_SUMMARY.md` 的对应工作单元；聚合层只引用 ID，不重述结论、不新增事实。
- 存量 `AI-YYYYMMDD-NNN` 与早期 `AI-YYYYMMDD-<ACTOR>-<NN>` 只读兼容，不追溯改号；不再以最大序号 +1 新发 ID。
- 不改别人条目；修订自己的条目直接编辑自己的文件。
- 审核状态只有团队人工审核后才能改为 `HUMAN_REVIEWED` / `ACCEPTED`。

## 工具

```text
python -m tools.build_ai_usage_index migrate  # 旧 ledger 追加部分收编（幂等）
python -m tools.build_ai_usage_index migrate --source ../legacy-ledger.md
python -m tools.build_ai_usage_index build    # 重建 AI_USAGE_LOG.md 索引
python -m tools.build_ai_usage_index check    # 校验（dev_gate 已自动调用）
```

`migrate` 仅在 **同 ID、同字节正文** 时 skip；任一已有 ID 的正文不同便 HARD FAIL，
并在写入新条目前预检整个批次。它不自动覆盖、合并或选择任一方。`--source` 可导入
外部旧台账快照，保留现有生成索引，随后再 `build`。对纯生成索引再 migrate 是 no-op。

迁移保留条目内部原始字节（含 CRLF 和行尾空格），只移除条目之间的分隔空行、保留一个
终止换行。从 Git 获取源快照时用原始 blob 字节，避免 PowerShell 重编码；遵循
`CONTROL_PLANE.md` 的 `core.autocrlf=false` 检出基线。曾用 true 检出的旧副本必须先确认
并恢复其 Git 字节，不能通过放宽内容比较隐藏差异。

`check` 对数量、摘要、链接和顺序都比较生成全文，并拒绝目录内除正常 `<ID>.md` 和
`README.md` 外的文件、目录及符号链接。提交后的共同索引仍可能产生 Git 冲突：合并时
保留双方条目，重新生成索引；不声称 Git 永远不会冲突。

索引是文本：读取时统一 Windows CRLF / LF 换行后比较全文，避免正常 Git checkout
产生假失败。迁移的原始正文仍按字节严格比较；索引数量、摘要等改写仍会失败。

## 合并前置条件

1. 先处理仍向旧台账追加内容的 PR（目前包括 #34 及其他仍开放的旧式分支），再安排 #49。
   #50 已合入 master `4d5a8f45ff40e0b3d0a0a7562cd45c7691c253b5`；本轮迁移包含其
   `AI-20260908-002` / `-003`，索引共 84 条（81 legacy + 3 actor）。这不是 #34 合并后的计数。
2. 最终同步最新 master，导出其旧台账原始 blob；运行 migrate → build → check，并核对
   旧条目、新 actor 条目及索引的完整集合。任何正文差异需逐条保存两边 diff 并明确调和。
3. #49 原提交已对 `AI-20260901-007` / `-008` 各追加一行默认审核状态。新 migrate
   **也会拒绝这两处差异**。核对确认仍仅是已披露的补记后，在独立的调和源快照中保留该
   补记并记录源提交、两边摘要和差异，再重跑；不能添加“此 ID 永远跳过”特例。
4. 最终同步后重跑完整 unittest、Sandbox 和 dev_gate；PR 描述的数量与验证结果必须取自
   最终提交。当前-master 的迁移演练不等于所有依赖合并后的最终验收。

背景与决策依据：ADR-012（`docs/compliance/DECISIONS.md`）；规范真源 `AGENTS.md` §4。
