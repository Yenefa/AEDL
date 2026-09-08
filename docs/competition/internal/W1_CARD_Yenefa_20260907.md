# W1 任务卡 · Yenefa（实现侧）

> 周期：2026-09-07 ~ 09-12 ｜ 预计 22 人时 ｜ 状态源：`docs/competition/internal/W1_TASKS_20260907.md`（AEW 领地表）
>
> ⚠️ INTERNAL — DEVELOPER FACING，公开/提交前随 `internal/` 一并移除。

## 你的角色纪律

- **Yenefa = 实现侧**：主链路、akcli 适配、模型适配。Percy 负责独立验收，**不要把验收判据的编写混进你的实现工作**——25 分证据链靠的是人 separation。
- W1 是止损闸门：你的 Y4 是全周最重要的一张卡，结论决定 W3 的 36 人时投不投。

## 2026-09-07 裁决更新（开工 Y2 前必读）

资格实测已完成：akcli 身份定为**受控 writer**（不是 Repair Executor）；DC-01/02/03 走受控例外
（原生 writer + 精确差分验收），DC-04/05 单批 strict（place+connect 同一 op-list）。PR-1 =
Minimum Safe Repair Transaction（最薄验证前移）。**下一张卡是"审查并冻结 PR-1 implementation
contract"，不是直接开写**；关键红线：topology policy 的 expected after 拓扑**只进 host 验收侧，
绝不进 C/D 输入包**（Y4 答案泄漏防线）。详见 `internal/AEDL_PR1_大统领裁决_20260907.md`。

## 2026-09-07 实现合同冻结（PR-1 开写入口）

**下一张卡已完成**：Implementation Contract v1 + Ready-to-Code 任务卡 + topology policy 草案已入库
（`internal/AEDL_PR1_实现合同/开发任务卡/topology_policy_v1_draft`），五查通过（Y4 泄漏/绕过
Sandbox/policy 自授权/过宽例外/回滚漏洞；结论见 PR）。**PR-1 现在按
`AEDL_PR1_开发任务卡_20260907.md` 直接开写**：五个生产文件、四套测试、C1→C6 commit 顺序、
原生验收走 `AEDL_PR1_NATIVE=1` opt-in。实现红线：只按合同第 4/5/8/9/10 节数据形状编码；
Proposal 三原语之外一律拒绝；host-only policy 的 after/expected 绝不进 C/D 输入（三层可见性）；
commit 谓词是合取没有例外。akcli 身份裁决见 `AEDL_PR1_大统领裁决_20260907.md`（PR #45，待合）。

## 你的任务

### Y1｜范围冻结　3h
- 文件形式冻结本期范围：支持「信号接线关系」「已核实器件参数」两类修复及各自边界；不支持几何布局/布线/热 EMI/整板功能保证。
- 判定语义：`PASS / FAIL / UNKNOWN / NOT_RUN / TOOL_ERROR / NOT_APPLICABLE`，**零覆盖不算通过**。
- 完成：范围文档经双方交叉复核。评分关联 S2、S6。

### Y2｜akcli 适配器接入　10h
- 把 akcli 0.21.0 接成受约束的补丁执行通道。已实测可用：读 M2（23 符号/29 网络）、改 C1 真实写入、重复执行字节相同、strict-nets 拒绝合网（退出码 6）。
- **两个必处理的坑（Codex 实测）**：
  1. 命令默认 dry-run，退出码 0 ≠ 已写入——必须 `applied` 字段 + 重新读取 + 字节哈希三重核对；
  2. 重复 apply 会移动回滚快照位置——用固定快照回滚，**别依赖 undo**。
- 完成：一次真实修改能写入、重读确认、按基准版本字节级还原。评分关联 S3、S4。
- **工程拆分（2026-09-07 执行计划）**：Y2 = PR-1，最小新增 `src/repair/patch_schema_v1.json`、
  `tools/akcli_adapter.py`、`tools/repair_pipeline.py` + 两套测试；commit 顺序：必要操作资格测试 →
  patch 合同/adapter → 快照与恢复 → 异常路径。**首个工作项必须是 strict-nets 资格测试**
  （DC-01 端点交换/DC-03 拆网按 0.21.0 源码会被 strict 拒——资格不通过则通道 BLOCKED，
  需 Y1 批准"白名单内预期拓扑差分"，不得静默关 strict）。C1 改值成功 ≠ 通道就绪。
  详细文件级任务见 `internal/AEDL_W1_工程执行计划.md` §1。

### Y3｜KiCad 独立重验链路　6h　依赖 Y2
- 补丁写入后用**独立的** KiCad 原生解析/导出/ERC 重读验证，不复用写入方解析结果（ADR-008：compiler 与 verifier 不得只消费同一份数据互相证明）。
- 完成：改一处 → 重新导出 → 独立 ERC → 可与改动前对比。
- Percy 的 KiCad 10.0.5 环境已装好并复现成功，可作第二套独立环境交叉核对。
- **工程拆分（2026-09-07 执行计划）**：Y3 = PR-2，新增 `gates/repair_verification.py` +
  `run_gates.py` 加 m2-repair 范围 + `schematic_semantics.py` 加结构化差分接口；四个连接点：
  候选目录适配、ERC 报告新鲜度（现有 netlist_fresh 无 ERC 等价物）、源哈希绑定、
  全部受保护关系差分（五条规则不覆盖全部 29 网）。详见执行计划 §2。

### Y4｜6 案例 AI vs 脚本小试　4h　依赖 P4 + Y2　★W1 止损闸门
- 用 Percy 的 6 个开发案例跑两组：**D 固定规则脚本 vs C AI 结构化定位反馈**，各限 3 轮。
- 完成：明确结论。**若脚本覆盖全部 6 例，必须调整 AI 承担的任务与创新表述，再决定是否进 W3。**
- **预注册方案 v1.1**：`internal/AEDL_W1_Y4_AI_vs_Script_实验方案.md`——36 条轨迹、180s/轨迹预算、
  A 稳定修复 K/5 + B 定性正确 n/6 两维独立记分（A 通过 B 失败要如实分开报）、误放行底线、
  W3 投入判据已运行前冻结；来源核查与 P3 勘误见 `internal/AEDL_Y4_复核与修订说明.md`；
  照它执行，不临场改判据。

### Y5｜正式挂起 PR #34 / Issue #5　1h
- 两处留言「本期挂起、非废弃」，重启条件 = 真实多租户需求出现。不留悬空，避免答辩被问。

### J1｜W1 收尾交叉复核（双方）　9/12　各 1h
- 你核 Percy 事实目录有无未标注推断；他核你有没有越出冻结范围。产出 W1 止损决策。

## 需要你拍板的三件事

1. **U3 的 ECO 你做不做？** U3 热超标（150mA→0.310W、WiFi 峰值 345mA→0.6415W，均超 SOT-353 250mW absmax）。换 SOT-223 涉及布局/铺铜/重跑 DRC，需要硬件背景。做 → 旗舰案例（真实、未解决、完整热分析），还可能打出实物板；不做 → 保持 BLOCKED，作「缺资料正确拒绝」案例（也有价值）。
2. **仓库何时公开？** S5「仅有开放计划」封顶 10 分。LICENSE 已有，剩内容审计 + 决策，建议 W5 前完成。
3. **容量重排。** Percy 可全投，总容量 150 → 240–260 人时。W2–W6 分配按「把 E1/E3/E4/E5 做到评委挑不出毛病」重算，不加新功能。

## 本周不做（防范围蔓延）

通用生成、自动布局布线、模型微调、RL、多 Agent 编排、继续扩 sandbox 控制平面/签名体系、EDD-001 原理图与固件、整板 SPICE/EMI/热仿真（E6 可选，基本包之外）。
