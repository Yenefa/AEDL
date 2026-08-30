# project-027 → AEDL 优化系统

目标是把已证实的项目经验逐级转化为可复用能力，同时防止一次事故被过早包装成“通用自主硬件 Agent 已完成”。

## 三层状态

### 1. 项目专属（project-local）

事故已在本项目发生，具有原始失败证据、负向夹具和项目门禁。此时规则只约束 project-027。

### 2. 晋级候选（candidate）

项目内持续通过，故障注入稳定；规则的输入、输出、失败语义和证据边界已抽象为不依赖 M2 器件编号的协议。候选仍不能称为通用能力。

### 3. AEDL 可复用（promoted）

至少在另一个不同硬件载体上成功复用，且由人工审核确认没有把静态门禁当成实体验证，才能进入 AEDL 优化系统默认模板。

## 晋级门禁

每条 critical 经验必须在 `gates/lessons_registry_v1.json` 中拥有：

- `root_cause`：真实根因；
- `escaped_controls`：旧防线为什么失效；
- `failure_evidence`：事故发生时的原始证据；
- `failing_fixtures`：可永久重放的负向样本；
- `regression_tests`：先红后绿的测试入口；
- `fail_closed_controls`：实际阻断发布的代码或合同；
- `fault_injection_proof`：最新机器生成的捕获证明；
- `optimization.promotion_criteria`：从项目规则晋级的附加条件。

`gates/learning_gate.py` 对缺字段、未知值、丢失文件、哈希漂移、漏捕故障或伪造 proof 一律失败。

## 本次经验的后续优化方向

`PIT-20260830-001` 当前状态为 `project_validated`。在 project-027 内先完成：

1. 将语义合同接口从 M2 固定规则抽象为插件协议；
2. 将 KiCad 网表/PCB/固件观察器变成可注册适配器；
3. 把故障注入和经验登记变成新硬件项目模板；
4. 用第二块不同载板验证，而不是只在 ESP32-C3/SHT30 上自证；
5. 经人工审核后才把候选规则写入 AEDL 默认优化系统。

## 证据边界

优化系统管理的是设计过程、软件门禁和证据质量。它不能自动创造实体测试结果，也不能在人工未签发时把 `manufacturing_release` 改为 `true`。
