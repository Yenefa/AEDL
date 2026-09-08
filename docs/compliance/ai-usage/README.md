# ai-usage/ — AI Usage 台账条目真源（GH-49 / ADR-012）

一个文件 = 一个可审计工作单元。文件名 = 条目 ID（如 `AI-20260908-YEN-001.md`），
标题必须是 `## <同一 ID>`，否则 `dev_gate` 的 `ai_usage_ledger` 检查 fail-closed。

## 新增条目（三步）

1. 新建 `<ID>.md`，ID 格式 `AI-YYYYMMDD-<ACTOR>-<NN>`（actor 见 `docs/ID_MAP.md`；
   `<NN>` 只在自己 actor 名下递增）。必含字段：`- 日期：YYYY-MM-DD`（与 ID 一致）、
   任务名称、AI 工具/模型、参与标签、产出、`- 人工审核：`PENDING_HUMAN_REVIEW``。
2. 完工后运行 `python -m tools.build_ai_usage_index build` 重建索引。
3. 提交。占位文件（标题+状态行+claimed by 说明）即锁号，可先提交再补内容。

## 规则

- `AI_USAGE_LOG.md` 是生成索引，**禁止手工编辑**（会被覆盖 + 门禁拦截）。
- 存量旧格式 `AI-YYYYMMDD-NNN` 只读，不追溯改号。
- 不改别人条目；修订自己的条目直接编辑自己的文件。
- 审核状态只有团队人工审核后才能改为 `HUMAN_REVIEWED` / `ACCEPTED`。

## 工具

```text
python -m tools.build_ai_usage_index migrate  # 旧 ledger 追加部分收编（幂等）
python -m tools.build_ai_usage_index build    # 重建 AI_USAGE_LOG.md 索引
python -m tools.build_ai_usage_index check    # 校验（dev_gate 已自动调用）
```

背景与决策依据：ADR-012（`docs/compliance/DECISIONS.md`）；规范真源 `AGENTS.md` §4。