# TASK-INFO：信息架构治理（HANDOFF 状态卡 + ID 引用地图 + RAG 决策记录）

> 通用前置（必做，按序）：读 `AGENTS.md`（v1.4，注意 8.5 节按需加载规则）→ 读 `docs/COLLABORATION.md`
> （多 AI 领地规则）→ `git status` 确认工作区（当前有另一会话的未提交改动：第 11 门禁
> datasheet_contract 等，**不要动它们**）。
> 铁律：只写自己领地；不 commit；收尾在 `docs/compliance/AI_USAGE_LOG.md` 追加一条
> `AI-YYYYMMDD-NNN`（PENDING_HUMAN_REVIEW）；改动前 Read 目标文件。

---

## 背景（为什么做这个任务）

项目信息量随并行会话增长（42 个 md ≈ 14 万 token、902 个 JSON 证据、台账 1248 行），新会话
接手成本在涨。大统领问"要不要引入 RAG"，主会话基于真实数据规模判定：**现在不需要 RAG**
（14 万 token 长上下文直接装得下；信息强结构化、ID 引用检索精确率 100%；数据手册真值层走
sha256 精确绑定优于向量检索）。本任务把这个判断落地成三件事：状态卡压缩、ID 引用地图、
RAG 决策记录（防止以后重复讨论）。

## 领地（可写）

- `docs/HANDOFF.md`（重构）
- `docs/ID_MAP.md`（新建）
- `docs/knowledge/RAG_DECISION.md`（新建）
- `docs/compliance/AI_USAGE_LOG.md`（追加自己一条）

其余文件一律只读（尤其 `gates/run_gates.py`、`gates/datasheet_contract.py`、
`src/hardware/m2-board/evidence/` 是另一会话的未提交工作）。

## 任务内容

### 1. HANDOFF 重构为「状态卡 + 归档」双层结构

当前 `docs/HANDOFF.md` 187 行，其中 100+ 行是各并行会话的历史叙述（P3-INTAKE、P2-FRONTEND、
P5-SEMANTIC-BINDING 等小节）。重构为：

**顶部：M2-STATE 状态卡（目标 ≤15 行，新会话 1 分钟读完）**，固定字段：
```text
## 项目状态卡（<更新日期>）
- 板子: M2 ESP32-C3+SHT30, D1 极性已修(U3 已换料 C235316), 待人工重签 board_review
- 门禁: 11 个 = 9 PASS + board_review FAIL(等重签) + datasheet_contract 32 BLOCK(等人工签发)
- 分支: fix/m2-schematic-semantic-release @ <当前 HEAD 短哈希>, 已推送
- 测试: <N>/<N> 全绿（跑 py -3 -m unittest discover -s tests 确认实际数字）
- 待大统领: ① 重签 board_review ② 下单时 JLC 装配预览目检方向 ③ master 合并
- 吸收: CircuitBot 已跑通+修2bug; Phase 2/3 研究完; NeuroBoard 未开始
- 详细: 见下方归档区 + docs/ID_MAP.md
```
（字段内容以你实际核实的当前状态为准，上面是格式样例不是答案——**逐项跑命令核实再填**，
不准抄这段示例。）

**中部：接手惯例**（保留现有前置块原文，不改动）。

**底部：归档区**——现有各并行会话小节**原文搬入** `## 归档：并行会话历史（截至 <日期>）`
标题下，一个字不删（它们是审计记录）。归档区顶部加一行说明："历史会话记录，仅审计用，
现状以上方状态卡为准"。

### 2. 新建 `docs/ID_MAP.md`（ID 引用地图）

项目的结构化检索入口。把散在各文件的 ID 体系汇成一张表，**每个 ID 前缀一行，写清格式、
在哪查、怎么用**：

| ID 体系 | 格式 | 真源文件 | 典型用法 |
|---|---|---|---|
| AI-YYYYMMDD-NNN | 会话台账 | docs/compliance/AI_USAGE_LOG.md | 解码 git 提交里的 [AI-...] 标签 |
| ADR-NNN | 架构决策 | docs/compliance/DECISIONS.md | 设计依据引用 |
| EVID-YYYYMMDD-NNN | 证据 | docs/evidence/EVIDENCE_INDEX.md | 支撑技术主张 |
| RES-NNN | 第三方资源 | docs/compliance/THIRD_PARTY_RESOURCES.md | license/边界查询 |
| PIT-YYYYMMDD-NNN | 事故教训 | gates/lessons_registry_v1.json | 已防错误清单 |
（以上 5 行先核实格式是否属实——去对应文件 head 看真实样例，不准编。缺的体系补，错的改。）

表格下方写「按需加载路由」：什么任务读什么文件（参照 AGENTS.md 8.5 的按需加载思想，
扩展到 docs/ 全部：比如"涉及硬件发布→必读 knowledge/ 两份；涉及比赛材料→competition/ 四件；
涉及门禁改动→先跑 run_gates 看基线"）。

### 3. 新建 `docs/knowledge/RAG_DECISION.md`（决策记录，防止重复讨论）

一页纸，含三部分：
1. **决策**：2026-08-31 判定暂不引入 RAG，理由三条（数据规模 14 万 token 可直塞长上下文；
   信息强结构化 ID 检索精确率 100% 优于向量相似度；数据手册走 sha256 绑定严格优于 RAG chunk）。
2. **触发条件**（到哪个条件才重启讨论）：文档量 >50 万 token；M3+ 多板并行需跨板查询；
   CircuitBot 生成层接入（它自带 FAISS 器件 RAG 直接复用）；台账数千条（先 SQLite 索引）。
3. **关联**：这是 ADR 级决策吗？——按 AGENTS.md 第 6 节判断（信息架构不触发 ADR 条目的话，
   写明"判定不立 ADR，理由：非系统架构/接口/验证协议变更"，留给人工复核）。

## 验收标准（逐条可验证）

1. `docs/HANDOFF.md` 顶部状态卡 ≤15 行，且**每个字段与实际一致**（门禁数、测试数、HEAD
   哈希、待办都要跑命令核实，不许编）。
2. 历史会话小节在归档区完整保留（diff 检查：内容零丢失，只是位置移动）。
3. `docs/ID_MAP.md` 的 ID 格式逐个与真源文件核对过（抽查任一 ID 能在真源 grep 到）。
4. `docs/knowledge/RAG_DECISION.md` 一页内，三条理由 + 四条触发条件齐全。
5. 未触碰另一会话的未提交文件（`git status` 前后对比，`gates/run_gates.py` 等 mtime 不变）。
6. 台账追加了自己的记录。

## 禁止

- 不改 `AGENTS.md`（它是执行规范，这次动的是 HANDOFF 不是规范）。
- 不动 `docs/competition/`（比赛资产已定稿待审）。
- 不实施任何 RAG/向量库/依赖安装——本任务是"决策记录"，不是"引入 RAG"。
- 状态卡里的数字必须实测，抄示例数字 = 不合格。
