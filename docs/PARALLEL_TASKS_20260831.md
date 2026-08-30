# 并行任务书 · 2026-08-31（多 AI 并发开发）

> 复制对应「TASK-XX」整段给你的 AI 即可。每个任务领地互不重叠，可安全并行。
> 通用前置：先读 `AGENTS.md`（v1.4）+ `docs/COLLABORATION.md`（含比赛时钟第 0 节）。
> 铁律：只写自己领地；不动 `src/`、`delivery/`、既有门禁逻辑（除非任务书明确授权）；
> 不 commit；收尾在 `docs/compliance/AI_USAGE_LOG.md` 追加一条 `AI-YYYYMMDD-NNN`（PENDING_HUMAN_REVIEW）。

---

## TASK-R1：渲染图新鲜度门禁（主线，防板子错）⭐ 文本 AI

### 背景（为什么做）
2026-08-31 发现：M2 目检用的 `board_top.png`/`board_bottom.png` 是 8-29 生成的过期图（比当前
PCB 旧一天，跨过 U3 换料），导致多模态 AI 目检全部误判（"丝印 17/21 缺失"等假警报）。
根因：渲染图是**一次性手工渲的，没脚本化、没 hash 绑定、没进门禁链**。这正是
`lessons_registry` PIT-20260830-001「历史快照不等于独立正确性」的同型病。

### 领地（可写）
- `tools/board_review.py`
- `gates/gate_core.py`（只新增函数，不改现有函数）
- `gates/run_gates.py`（只改 `_evaluate_board_review` 内部，不动 gates 列表其他项）
- `tests/test_board_review.py`（新增测试）
- `notes/m2-evidence-reset/generated/board_top.png` / `board_bottom.png`（脚本重渲覆盖）

### 任务内容
1. `tools/board_review.py` 的 `main()` 末尾加渲染步骤：
   - 用 `kicad-cli.exe` 渲染当前 PCB 的 top/bottom 到固定路径（`notes/m2-evidence-reset/generated/board_top.png`、`board_bottom.png`），覆盖旧图。
   - kicad-cli 绝对路径：`C:\Users\fuker\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe`（用 `shutil.which("kicad-cli")` 或环境变量，找不到即 fail，不硬编码到报错）。
   - 命令参考：`kicad-cli pcb render --side top --quality high --width 1600 --height 900 -o <out.png> <pcb>`（已验证可用，约 12-13s/张）。
2. 在 `board_review_auto.json` 顶层新增 `render_evidence` 字段，记录（**全部用 sha256 内容寻址，不用 mtime**）：
   ```json
   "render_evidence": {
     "pcb_sha256": "<m2_board.kicad_pcb 的 sha256>",
     "top_png_sha256": "<board_top.png 的 sha256>",
     "bottom_png_sha256": "<board_bottom.png 的 sha256>",
     "rendered_at": "<ISO8601 UTC>"
   }
   ```
3. `gates/gate_core.py` 新增 `validate_render_evidence(auto_evidence_path: Path, pcb_path: Path) -> List[str]`：
   - auto 证据缺 `render_evidence` → error；
   - `render_evidence.pcb_sha256` != 当前 PCB sha256 → error（**这是"图过期"的机器判定核心**）；
   - top/bottom png 文件不存在 → error；
   - png sha256 != 记录值 → error。
4. `gates/run_gates.py` 的 `_evaluate_board_review`：读完 board_review_v1.json 后，取其
   `_meta.auto_evidence` 指向的 auto json，调用 `validate_render_evidence`，把结果并入该 gate 的 errors。

### 验收标准
- `py -3 tools\board_review.py` 会重新渲染当前 PCB 并写 render_evidence，8 项评审仍 pass。
- 手动改 PCB 文件（不改图不重渲）→ `py -3 gates\run_gates.py` 的 board_review gate 报"pcb_sha256 失配"。
- `py -3 -m unittest tests.test_board_review` 全绿；新增测试覆盖：缺 render_evidence / pcb 失配 / png 缺失 / png 失配。
- 全量 `py -3 -m unittest discover -s tests` 不回归。

### 禁止
- 不引入 pcbnew Python 模块依赖（用 kicad-cli.exe 二进制，普通 `py -3` 可跑）。
- 不改 8 项评审逻辑、不改 manufacturing_release 语义（那是人工签发的，AI 不得置 true）。
- 不用 mtime 判新鲜度（mtime 会骗人），只用 sha256。

### 已知约束
- kicad-cli 渲染约 12-13s/张，board_review.py 整体会慢 ~25s，可接受（低频工具）。
- 渲染图是 3D 视图；若想同时输出 2D 丝印图（更利目检），可额外 `kicad-cli pcb export svg --layers "F.Silkscreen,F.Fab,Edge.Cuts"`，但 SVG→PNG 本机缺转换工具，选做，不强求。

---

## TASK-C：C 方案语义哈希绑定（Phase 1 最后一公里）⭐ 文本 AI

> **状态：✅ done（AI-20260831-006，WorkBuddy 认领，待人工审）** —— 详见
> `docs/COLLABORATION.md` 的 TASK-P5 卡片与 `docs/HANDOFF.md` 的 P5-SEMANTIC-BINDING 小节。
> 验收已实测：U9 加件/换料 → FAIL；只改绑定字段 → PASS；`tests.test_requirements_contract`
> 31/31；全量 114/114；`run_gates.py` requirements_contract PASS（board_review 仍待人工重签）。
> ⚠️ 连带缺口交 P1：`requirements_runtime_server.py::finalize` 未写 `intent_semantic_sha256`。

### 背景
第 10 门禁（requirements_contract）现为单向绑定：intent 持 `{sha256, path}` 指向合同，合同只声明
`intent_path`。缺口：**改 intent 的电路内容（换料/加器件）而保留旧合同引用时，门禁抓不到**
（已实测：塞一个 U9 电阻 gate 仍 PASS）。C 方案 = 让合同记录 intent 的「语义字段哈希」，
改电路必须重签合同。

### 领地（可写）
- `gates/requirements_contract.py`
- `gates/requirements/requirements_contract_v1.json`（M2 合同）
- `gates/requirements_runtime.py`（draft_contract 签名如涉及）
- `tests/test_requirements_contract.py`
- `docs/api/requirements_api.md`（契约文档同步）

### 任务内容
1. 定义「语义字段」白名单 = `components` + `nets`（排除 `requirements_contract` 绑定字段本身、
   `protocol_version` 等元数据）。写一个 `intent_semantic_sha256(intent: dict) -> str`：
   对 components/nets 两字段做 canonical JSON（ensure_ascii=False, sort_keys=True,
   separators=(",",":")) 后 sha256。
2. 合同 `intent_binding` 从 `{"intent_path"}` 扩为 `{"intent_path", "intent_semantic_sha256"}`。
   **保持单向**：语义哈希存的是 intent 的 components+nets，不依赖合同内容 → 无循环依赖。
3. C4 检查新增：合同 `intent_binding.intent_semantic_sha256` != 当前 intent 的语义哈希 → error
   （"intent 语义内容已变更，须重签合同"）。
4. 重签 M2 合同：算当前 intent 的语义哈希，写进 intent_binding，重算 contract_sha256。
5. 同步 `docs/api/requirements_api.md`：intent_binding 含 intent_semantic_sha256，说明语义哈希范围。

### 验收标准
- 改 intent 的 components（如换料 U3 value）不重签合同 → requirements_contract gate FAIL。
- 只改 intent 的 `requirements_contract` 绑定字段（不改 components/nets）→ 仍 PASS（绑定字段本身可白改）。
- `py -3 -m unittest tests.test_requirements_contract` 全绿（含新加"语义变更 fail"用例）。
- 全量回归不回归；`py -3 gates\run_gates.py` 的 requirements_contract 仍 PASS（M2 已重签）。

### 禁止
- 不引入双向哈希（intent 语义哈希不依赖合同内容，合同自哈希不含 intent 哈希）。
- 不把 `requirements_contract` 字段本身算进语义哈希（会再次循环）。

### 已知约束
- 语义字段白名单（components+nets）要在代码注释写死约定；将来 intent 协议扩展字段时白名单要跟动。

---

## TASK-COMP：比赛资产六件套 + THIRD_PARTY.md ⭐ 文本 AI

### 背景
AIC 赛事约 10-03 截止（33 天）。`docs/competition/` 目录**尚未建**（AGENTS.md 8.1 引用的
FUSION_MAP/OPEN_OUTPUTS 等实体全缺）。策略文档 §8 要求的 intake 版 THIRD_PARTY.md 也没建。

### 领地（可写）
- `docs/competition/`（新建全部）
- `notes/open_source_intake/THIRD_PARTY.md`（新建）

### 任务内容
从三处素材合成，逐项标注来源、不脑补：
1. `docs/competition/FUSION_MAP.md`：AEDL 核心能力 = 10 门禁 fail-closed + 语义合同 + 故障注入 +
   跨视图哈希 + 人工制造签发 + 经验学习门禁；每条写「AI 做什么、为什么必要、哪些开源资源参与、
   自研模块是什么、移除 AI 会损失什么、如何验证」。用碰撞分析 §3 的判定语言（"截至检查日尚未
   发现等价实现"），禁用"首创/领先/空白"。
2. `docs/competition/OPEN_OUTPUTS.md`：准备复用的协议/门禁代码/测试夹具/需求合同 schema/目检提示词。
3. `docs/competition/PROBLEM_EVIDENCE.md`：硬件 Agent 验证可信度问题的真实痛点证据（PIT-20260830-001
   USB 接反事故 + 渲染图过期事故是现成案例）。
4. `docs/competition/SUBMISSION_CHECKLIST.md` + FAIRNESS_CHECK 清单。
5. `notes/open_source_intake/THIRD_PARTY.md`：表格记录已实际复用的外部项目（CircuitBot 思想借鉴、
   KiCad MCP 引用边界、KiCadAI 引用边界、Konnect AGPL 红线），含 license/是否修改/是否再分发。

### 验收标准
- 六件套文件齐全，每条主张有真实证据/ADR/台账 ID 支撑，无"首创"字样。
- THIRD_PARTY.md 表格含 Konnect=AGPL 禁止吸收的红线行。

### 禁止
- 不编造 benchmark/测试结果/用户反馈；无证据的写 NOT_RUN / TO_VERIFY。
- 不把"用了 Git/Python/LLM/开源库"当融合创新写进 FUSION_MAP。

---

## TASK-CPL：CPL 旋转 vs JLC 约定核对（板子最隐蔽的雷）⭐ 文本 AI（建议主会话认领）

### 背景
`board_review_v1.json` 的 ASSEMBLY 项明确标注"当前 JLC CPL 为 21 行、毫米单位，**但未应用板厂
自动旋转修正**"。极性器件（LED/LDO/SHT30/USB）旋转差 90/180° = 贴反 = 整板报废，且 DRC/ERC/语义
合同都查不到。这是打板前必须闭环的数据核对。

### 领地（可写）
- `notes/m2-evidence-reset/cpl-rotation-audit.md`（产出审计报告，新建）

### 任务内容
对 5 个方向敏感件（D1/U2/U3/J1）+ U1，逐器件对齐三要素：
1. footprint 库的 0° 朝向（pin1/极性标记在哪个方位）——读本机 KiCad footprint 库：
   `C:\Users\fuker\AppData\Local\Programs\KiCad\10.0\share\kicad\footprints\`
   （SOT-353：`Package_TO_SOT_SMD.pretty/SOT-353_SC-70-5.kicad_mod`；LED：
   `LED_SMD.pretty/LED_0603_1608Metric.kicad_mod`；SHT30：`Sensor_Humidity.pretty/…`；USB：
   `Connector_USB.pretty/USB_C_Receptacle_HRO_TYPE-C-31-M-12.kicad_mod`）
2. CPL 旋转值（`delivery/pos.csv` 的 Rotation 列）
3. JLC 贴片机旋转约定（联网核实；豆包额度已尽，Go 网关缺 key，用 WebFetch 抓 JLC 文档或
   KiCad→JLC 旋转对照表，抓不到就标"规则待核实"不脑补）
输出：每个器件的「footprint 0° 朝向 + CPL 旋转值 + JLC 是否需修正 + 结论(对/错/待核实)」。

### 验收标准
- 5 个极性件 + U1 各有一行结论；凡规则未核实的标"待核实"而非猜。

### 禁止
- 不猜 JLC 旋转规则；搜索通道全挂就明说"规则待核实"。
- 不改 pos.csv 本身（只出审计报告，改动由人工/主会话执行）。

---

## TASK-VIS：M2 目检（当前版）👁 多模态 AI（唯一能看图）

### 背景
第一轮目检用了过期图作废。已重新渲染当前版，请用**新图**重看。

### 任务
读 `notes/m2-evidence-reset/M2目检提示词-多模态AI.md` 的「一、提示词」整段（含版本警告和新图路径），
连同这两张**门禁绑定版**新图一起发给多模态 AI：
- `notes/m2-evidence-reset/generated/board_top.png`（1600×900，sha256 已绑定当前 PCB）
- `notes/m2-evidence-reset/generated/board_bottom.png`（1600×900，sha256 已绑定当前 PCB）
- 可选：`board_top_2d.svg`（若模型能读 SVG）

⚠️ 图路径以提示词文件为准（`board_top.png`/`board_bottom.png`，非 `_20260830` 后缀的旧手动渲图）。

### 验收标准
- 产出 L1/L2 观察清单（位号|观察|可疑否|置信度|说明），只报告"图里画了什么朝向"，不下对错终审。

---

## 分配建议（4 AI）

| AI | 认领 | 理由 |
|---|---|---|
| 多模态 AI | TASK-VIS | 唯一能看图 |
| 文本 AI A | TASK-R1 | 主线防板错，改 board_review 门禁 |
| 文本 AI B | TASK-C | Phase 1 最后一公里，纯 requirements_contract |
| 文本 AI C | TASK-COMP | 纯 docs/competition 新建，最独立 |

TASK-CPL 建议主会话（我）认领——已开了头（确认了雷 + footprint 库可用 + 搜索通道现状），
续做成本最低。
