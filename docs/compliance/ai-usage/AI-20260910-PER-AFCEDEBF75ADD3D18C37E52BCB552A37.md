## AI-20260910-PER-AFCEDEBF75ADD3D18C37E52BCB552A37

- 日期：2026-09-10
- 任务名称：W2 TASK-B6 —— 再分发 / 隐私 / 证据三条发布边界入库；发现 RES-007 登记与实际状态不符
- 记录者：PER
- 会话：Claude Code 主会话
- 参与：RESEARCH、DOCUMENT
- AI 工具/平台：Claude Code
- 模型：`claude-opus-5`
- 模块/路径：
  - `docs/compliance/PUBLICATION_BOUNDARY.md`（新增）
  - 本条台账（ADR-012 随机 ID）
- 人类指令：Percy 2026-09-10 指定按 W2 r3 任务卡执行 B6（其份额为 redistribution / privacy / evidence boundary，2h）。

### 调查方法（逐项实查仓库现状，不凭既有文档转述）

- 逐条解析 `THIRD_PARTY_RESOURCES.md` 的 RES-001..010，提取「是否随 AEDL 再分发 / 合规状态 / 最终开放方式」三字段。
- 用 `git ls-files --error-unmatch` 逐份确认 `evidence/datasheets/` 下第三方原件是否受版本控制。
- 读 `NOTICE` 第三方节全文，逐份核对其点名覆盖范围。
- 读 `datasheet_manifest.json`，确认 source_url / sha256 / retrieved_at 归因完整性。
- 读 E5 协议 §8.1 / §8.2 / §8.3；对 `notes/e5-user-trial/` 全目录做姓名 / 手机号 / 邮箱 / 单位模式检索。
- 清点 `delivery/` 制造导出物、`board_*.png` 渲染图、`notes/` 下运行证据目录。

### 主要发现

**B-1（阻断项）· RES-007 的登记与实际状态直接冲突。** RES-007 明写 `是否随 AEDL 再分发：NO`、`最终开放方式：仅保留链接和必要事实引用`；但 `src/hardware/m2-board/evidence/datasheets/` 下 **8 份第三方原件、4628 KB，经实测 8/8 全部被 git 跟踪**。仓库一旦 public，这 8 份即被再分发，与已登记的合规结论相反。

已按风险分三档：**高**——`KT-0603R_KENTO_approval_spec_revA0.pdf`（承认书类文档，通常不面向公开分发）与 `TYPE-C-31-M-12_drawing_elecfans_mirror.pdf`（manifest 自记 `FROZEN_PROVENANCE_QUESTIONABLE`、带 HIROSE 水印）；**中**——两份第三方站点镜像（stm32base / elecfans）；**低**——原厂 / LCSC 托管的常规数据手册。

同时记录了**已经做对、不必重做**的部分：NOTICE 已逐份声明版权归属并标注可疑来源，manifest 归因完整。

给出三种处置供裁定（全部移除 / 分档移除 / 全部保留并改登记），并指出**仅从工作树删除不足以撤销 git 历史中的再分发**——该点须在转 public 决策时一并考虑。

**B-2 · RES-001 / RES-003 三字段全为 `TO_VERIFY`**，而 `AGENTS.md` 本身已在仓库根目录。判定口径：`TO_VERIFY` 不等于「可以」。

**B-3 · RES-009（LangGraph）无任何字段。**

**隐私边界给出结论**：协议 §8.2 留有「仓库公开前将再评估是否需要进一步脱敏」，本次即该再评估。三档处置已定；另**新增一条协议原本没有的风险**——3 人小样本下，「相关专业 + 不同实验室 + 画过 1/1/2 块板」这类背景信息**单条无害、组合起来在小圈子内可能足以指认到人**，故规定报告只出汇总、逐字记录中的可定位内容记录时即改写。

**退出权的技术落实**：协议允许参与者退出并选择删除记录，但 git 历史会留存；故本文件把「E5 会话记录在转 public 前应视为可能需要撤回的内容」列为给 public timing 决策的输入。

### 边界纪律

本文件**不改写** RES-001..010 任何一条登记，只指出不符之处；**不裁定** LICENSE、secrets sign-off、转 public 时点（按 W2 r3 属 Yenefa）；对第三方内容一律按「`TO_VERIFY` = 未获授权」处理，不主张任何一项「可以公开」。

### 验证（真实运行）

- 8 份第三方原件受控状态：`git ls-files` 逐份确认 **8/8 已跟踪**；总体积 `du -ck` 实测 **4628 KB**
- 隐私检索：`notes/e5-user-trial/` 全目录手机号 / 邮箱模式 **0 命中**
- 文件计数：渲染图 `board_*.png` **4 份**、`notes/` 下证据目录 **8 个**、`delivery/` 5 项
- `manufacturing_release` 实读 **false**
- 文档内引用的 5 个上游文件均已确认存在
- `build_ai_usage_index check` → OK

### 已知限制

- 本文件是**边界与缺口的登记**，不是处置本身；B-1/B-2/B-3 的实际执行需 owner 裁定后另行进行。
- 未对 `delivery/` 制造导出物公开与否作出结论——仅指出它含完整板卡设计且 `manufacturing_release=false`，公开须显式标注状态以免他人据以下单。
- RES-001 / RES-003 的源规范授权情况**未做外部核实**，仅指出其登记为 `TO_VERIFY`。
- 分支基于 PR #57 的 head（`1b4b8a1`）以继承台账索引修复；#57 合并后本分支须 rebase。

### 团队自主部分

B6 的执行由 Percy 按 r3 任务卡指派；三条边界的调查与缺口判定由 Agent 完成，**处置方案只提供选项、不代为裁定**。

- 人工审核：`PENDING_HUMAN_REVIEW`
