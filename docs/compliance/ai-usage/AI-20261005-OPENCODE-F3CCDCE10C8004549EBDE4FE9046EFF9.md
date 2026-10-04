## AI-20261005-OPENCODE-F3CCDCE10C8004549EBDE4FE9046EFF9

- 日期：2026-10-05
- 任务名称：Placement-source audit: DC fixtures and frozen M2 PCB are in different coordinate frames, so missing-part faults are unsolvable from frozen sources
- 记录者：OPENCODE
- 人工审核：`PENDING_HUMAN_REVIEW`

- 工具/模型：OpenCode（deepseek-v4-flash 会话）；CPython 3.9 (`py -3.9`)。**本轮零模型调用、零花费。**
- 标签：RESEARCH / DEBUG / DOCUMENT / ADVISE。
- 授权：Owner 2026-10-05「行行行，你做吧」；承接 ADR-022 常驻自治授权与 1 元预算上限（`tools/repairbench_budget.py`）。
- 范围：`benchmarks/repairbench_v0_1/placement_source_audit_20261005.md`（新）、本条目。**只读审计，未改任何夹具 / 合同 / PCB。**
- 第三方：无新增。
- AIC Score Target：`NONE`（题目可解性审计，非评分项证据）。
- 自主验收：`AI_ACCEPTED`

- 起点：`EVID-20261005-001` 发现合同只断言器件**值**、不断言**存在**、无坐标，
  导致 DC-03/04/05（补器件类）不可解。本轮追问：这些信息能否从别的**冻结源**合法补上。
- **逐源实测结论**：
  - `intent_v1.json`（冻结设计意图）**有**器件存在性、lib_id、value、footprint（R7/R8/R9/C5 齐全），**无坐标**。
  - `m2_board.kicad_pcb`（冻结 PCB）**有**坐标，但**坐标系与 DC 夹具不一致**：R9 在 PCB 是
    (1.45, 22.50) mm，而答案键 `acceptance_v1.json` 是 (34.29, 257.81) mm，**相差近一个数量级**。
    佐证：DC-02 夹具 sheet UUID `a1dbe1c3-…`，其元件坐标在 154–277 mm 量级。
  - 故 **DC 夹具不是 M2 板自身坐标系的产物**，不能用 PCB 摆放器件。
- **方法论修正（如实记录）**：我第一次用**固定 2500 字符窗口**做正则抽 PCB footprint，
  会跨进相邻 footprint 块。改为**锚定切片**（在相邻 `(footprint` 起点之间切）后结论不变，
  但**方法**才是可信的——固定窗口的正则抽取在这种 s-expr 上不可信。
- **结论**：在「求解臂不得读答案键」的前提下，**DC-03/04/05 不可解**。
  这不是实现不够努力，而是**题目缺一个坐标真源**。
- **由此得到两条决策选项（不是能力主张）**：
  (a) 换一批**自带布局意图**的夹具（每集携带与合同同源、同坐标系的器件坐标真源）；
  (b) 把 v0.1 故障族**明确限定为纯连通性类**，并在 `episodes_v1.json` 写明「补器件类不在 v0.1 范围内」，
      而不是让它们以 0 分混在分数里。
  两者都比「让求解臂去读答案键」诚实。
- 未验证 / UNKNOWN（不判定责任方）：夹具来源转换过程未复核（`manifest_v1.json` 指向
  `docs/competition/internal/AEDL_PR1_原生资格记录_20260907.json`，未查证是否声明坐标系转换）；
  夹具**是否本应**与 M2 PCB 同坐标系（即生成过程是否有缺陷）未查证。本记录只陈述「两者不一致」这一实测事实。
- 测试实跑：本轮为只读审计 + 脚本探针，未改生产代码，故未重跑全量门禁；最近一次全量结果见上一提交
  （main 1256 OK、sandbox 574 OK、台账 157 条 in sync）。
- 证据边界：本条只主张「坐标系不一致」与「因此该类故障在当前题目下不可解」这一实测事实，
  **不主张**任何修复能力，也不主张夹具生成过程有错。
