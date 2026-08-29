# AEDL 开发记录与 AI 使用规范 v1.0

> 目标：开发即留痕，避免赛前考古。  
> 适用：所有参与 AEDL 的 ChatGPT / Codex / Claude Code / Gemini / Cursor / OpenHands / 其他 AI Agent，以及人工开发任务。

---

# 1. 赛事要求映射

依据《AIC·AI+开源竞赛规则及作品提交要求 0812》，AEDL 开发过程必须持续保留以下信息：

1. **团队真实完成内容**：不得提交与团队实际工作不一致的成果。
2. **第三方资源披露**：软件、模型、数据、素材、组件、工具、第三方服务需要记录名称、版本、来源、许可证/授权类型、使用方式、关键义务和自主开发边界。
3. **AI 工具使用说明**：使用生成式 AI、智能体或自动化工具辅助代码、内容、报告时，需要说明：
   - AI 工具用途；
   - 参与环节；
   - 团队审核；
   - 团队修改；
   - 团队验证。
4. **AI 生成内容权利核查**：AI 生成代码、文本、图片、音视频等不能当然视为团队自主知识产权。
5. **可验证效果**：测试、Benchmark、故障注入、用户反馈、仓库提交记录、Issue / PR 等都应形成可追溯证据。
6. **安全合规**：不得记录或提交 API Key、Token、密码等访问凭据。
7. **公平性**：正式技术报告、演示视频、答辩 PPT 等评审材料不得出现学校名称、学校 LOGO 和指导教师信息。

---

# 2. AEDL 仓库统一记录结构

建议仓库固定维护：

```text
AEDL/
├── AGENTS.md
├── README.md
├── src/
├── tests/
├── benchmark/
└── docs/
    ├── compliance/
    │   ├── AI_USAGE_LOG.md
    │   ├── THIRD_PARTY_RESOURCES.md
    │   ├── DECISIONS.md
    │   └── TEAM_CONTRIBUTIONS.md
    └── evidence/
        ├── EVIDENCE_INDEX.md
        └── runs/
```

四个核心台账：

- `AI_USAGE_LOG.md`：哪个 AI 开发了哪部分，团队如何审核/修改/验证。
- `THIRD_PARTY_RESOURCES.md`：最终直接整理成官方《开源及第三方资源使用清单》。
- `DECISIONS.md`：关键工程决策、自主设计边界和技术取舍。
- `EVIDENCE_INDEX.md`：测试、Benchmark、故障注入、演示等硬证据。

---

# 3. 总原则

## 3.1 开发即留痕

只要 AI 对以下任一内容有实质贡献，就必须追加记录：

- 代码生成/修改
- 重构
- Bug 诊断和修复
- 测试/Benchmark
- 架构与接口设计
- Agent Workflow
- 数据处理
- 文档
- Prompt
- 图片、视频、报告材料
- 第三方资源选型和集成

禁止“先开发，赛前再凭记忆补”。

---

## 3.2 AI 不得自己确认“人工审核”

AI 完成后的默认状态：

```text
PENDING_HUMAN_REVIEW
```

只有团队成员实际查看 diff、运行/检查测试后，才能改为：

```text
HUMAN_REVIEWED
ACCEPTED
```

AI 不得自行声称：

- 已人工审核
- 已人工确认
- 已人工测试

---

## 3.3 不知道就写不知道

统一使用：

```text
UNKNOWN
TO_VERIFY
NOT_RUN
PENDING
```

禁止：

- 猜许可证
- 猜模型版本
- 猜测试结果
- 声称执行过没执行的命令
- 编造 Benchmark 数据
- 编造人工审核
- 无证据声称“首创”“首次”“行业空白”

---

# 4. AI 使用记录格式

每个实质 AI 任务生成唯一 ID：

```text
AI-YYYYMMDD-NNN
```

例如：

```text
AI-20260829-001
```

每次任务结束后，向 `docs/compliance/AI_USAGE_LOG.md` 追加：

```markdown
## AI-20260829-001

- 日期：2026-08-29
- 任务名称：实现 WokwiAdapter 串口结果解析
- 模块/路径：
  - `src/simulator/wokwi_adapter.py`
  - `tests/test_wokwi_adapter.py`

- AI 工具/平台：Codex CLI
- 模型：UNKNOWN / 实际可确认模型名

- AI 参与类型：
  - [x] ADVISE
  - [x] GENERATE_CODE
  - [ ] REFACTOR
  - [ ] DEBUG
  - [x] GENERATE_TEST
  - [ ] RESEARCH
  - [ ] DOCUMENT
  - [ ] BENCHMARK
  - [ ] MEDIA

- 任务目标：
  - 将 Wokwi CLI 输出转换为 AEDL 统一 Observation。

- AI 实际产出：
  - 新增 WokwiAdapter
  - 新增串口 parser
  - 新增 4 个单元测试

- 团队自主部分：
  - SimulatorAdapter 接口由团队确定
  - Observation Schema 与 PASS/FAIL 证据格式由团队定义

- 人工修改：
  - `PENDING_HUMAN_REVIEW`

- 人工审核：
  - 状态：`PENDING_HUMAN_REVIEW`
  - 审核人：
  - 审核内容：

- 验证：
  - 命令：`pytest tests/test_wokwi_adapter.py -q`
  - 结果：真实结果 / `NOT_RUN`
  - Evidence ID：EVID-20260829-001

- 新增第三方资源：
  - 无 / RES-XXX

- 关联设计决策：
  - ADR-XXX / 无

- Commit / PR：
  - 待提交 / commit hash / PR

- 最终状态：
  - `PENDING_HUMAN_REVIEW`

- 备注：
```

### AI 参与类型

不要填写“AI 完成 70%”这类不可审计百分比。

统一用事实标签：

- `ADVISE`：方案建议
- `GENERATE_CODE`：代码生成
- `REFACTOR`：重构
- `DEBUG`：Bug 诊断/修复
- `GENERATE_TEST`：测试生成
- `RESEARCH`：资料调查
- `DOCUMENT`：文档
- `BENCHMARK`：实验/评测
- `MEDIA`：图片/视频/演示材料

---

# 5. 第三方资源登记格式

新增以下任一资源，都必须登记：

- 软件
- 开源库
- SDK
- 模型/API
- SaaS
- 数据
- Datasheet
- 素材
- 示例代码
- Prompt / Skill
- 图标/字体
- 仿真器
- 外部服务

唯一 ID：

```text
RES-NNN
```

模板：

```markdown
## RES-001

- 名称：PlatformIO Core
- 类型：软件 / 框架 / 模型 / 数据 / 服务 / 素材 / 组件 / 工具
- 版本：实际锁定版本
- 来源：官方项目 / 官方发行页
- License / 授权类型：实际确认；未知写 `TO_VERIFY`

- 用途：
  - ESP32 firmware build

- 使用方式：
  - CLI 调用
  - 未修改上游源码

- 是否修改第三方源码：
  - 否

- 是否随 AEDL 再分发：
  - YES / NO / TO_VERIFY

- 关键许可义务：
  - 实际确认；未知写 `TO_VERIFY`

- 使用限制：
  - 无 / TO_VERIFY

- AEDL 自主开发边界：
  - AEDL 自研编排、验证协议、证据格式和错误处理；
    PlatformIO 仅作为构建执行工具。

- 合规状态：
  - OK / TO_VERIFY / BLOCKED

- 最终开放方式：
  - 依赖声明 / 不再分发第三方内容 / 其他

- 对应模块：
  - `src/build/...`

- 备注：
```

特别不要漏掉：

- GPT / Claude / Gemini 等模型和 API
- Wokwi
- KiCad
- PlatformIO
- ESP-IDF / Arduino Core
- QEMU / Renode
- Python/npm 包
- GitHub 参考代码
- Datasheet
- Benchmark 数据来源

---

# 6. 关键工程决策 ADR

任何影响以下内容的决定必须记录：

- 项目架构
- Agent Workflow
- Verification Protocol
- Simulator Adapter
- Benchmark 方法
- Ground Truth
- Complexity Guard
- 模型/仿真器选择
- 关键接口
- 安全边界
- 开源边界

ID：

```text
ADR-NNN
```

模板：

```markdown
## ADR-001 — Wokwi 作为可视化后端而非核心依赖

- 日期：2026-08-29
- 状态：Accepted

- 问题：
  - Wokwi 为闭源 SaaS，强绑定会削弱 AEDL 的开源独立性和可复现性。

- 候选方案：
  1. 完全绑定 Wokwi
  2. 放弃 Wokwi，只使用开放模拟器
  3. Open Core + Pluggable Simulator

- 决策：
  - 采用方案 3。

- 理由：
  - 保留 Wokwi Demo 可视化优势
  - 核心协议和 Benchmark 不绑定单一 SaaS
  - 未来允许 Native/QEMU/Renode 后端

- AI 参与：
  - AI 参与方案讨论和风险分析。

- 团队自主判断：
  - 最终决策由团队基于赛事规则、复现性、开发成本作出。

- Evidence：
  - EVID-XXX

- 影响：
  - SimulatorAdapter 成为 AEDL 核心接口。

- 后续复查条件：
  - 若 Wokwi CLI 不支持稳定 headless 输入注入，则调整默认 backend。
```

---

# 7. Evidence 证据格式

所有准备写进比赛材料的关键技术主张，都应尽量有 Evidence ID。

ID：

```text
EVID-YYYYMMDD-NNN
```

模板：

```markdown
## EVID-20260829-001

- 日期：2026-08-29

- 对应主张：
  - WokwiAdapter 能稳定解析 Smart Plant 行为证据。

- 关联模块：
  - `src/simulator/wokwi_adapter.py`

- 关联 AI Usage：
  - AI-20260829-001

- 关联 ADR：
  - ADR-001

- 测试/实验：
  - 重复运行 normal / low / dry scenario。

- 环境：
  - OS：
  - Python：
  - PlatformIO：
  - Wokwi CLI：
  - MCU：

- 执行命令：
  - `python run_test.py ...`

- Runs：
  - 20

- 结果：
  - 只填写真实结果

- 指标：
  - Pass consistency：
  - False PASS：
  - Runtime：

- 原始证据：
  - `docs/evidence/runs/20260829/...`

- 是否可复现：
  - YES / PARTIAL / NO

- 已知限制：
  - ...

- 人工核验：
  - `PENDING_HUMAN_REVIEW`
```

原始 evidence 推荐保留：

- CLI log
- JSON
- CSV
- test report
- fault injection report
- screenshot
- VCD
- benchmark result
- 必要的视频片段

---

# 8. 人工审核门禁

AI 完成：

```text
AI_COMPLETE
↓
PENDING_HUMAN_REVIEW
↓
人工检查 diff
↓
检查/运行测试
↓
检查第三方资源
↓
检查无秘密凭据
↓
ACCEPTED / NEEDS_CHANGE / REJECTED
```

人工审核 Checklist：

- [ ] Diff 与任务一致
- [ ] 没有无关修改
- [ ] 没有来源不明的大段复制代码
- [ ] 实际执行过的测试与日志一致
- [ ] 没有声称执行未执行测试
- [ ] 新增第三方资源已登记
- [ ] License / 服务条款状态正确或标记 TO_VERIFY
- [ ] 没有 API Key / Token / 密码
- [ ] 没有明显安全问题
- [ ] 没有无证据“首创/首次”宣传
- [ ] Evidence 足以支撑对应技术主张

通过后再将状态改成：

```text
HUMAN_REVIEWED
ACCEPTED
```

---

# 9. Commit 统一格式

推荐：

```text
<type>(<module>): <summary> [AI-LOG-ID]
```

例如：

```text
feat(simulator): add Wokwi serial verifier [AI-20260829-001]
test(benchmark): add fault injection cases [AI-20260830-002]
fix(build): repair PlatformIO classifier [AI-20260831-003]
```

如果某任务完全由人工独立完成，可不带 AI ID。

---

# 10. 所有 AI Coding Agent 的强制收尾规则

建议把下面内容直接放进仓库根目录 `AGENTS.md`：

```markdown
# AEDL AI Development Rules

任何 AI Agent 在完成实质开发任务前，都必须检查并更新项目台账。

1. 修改代码/测试/文档/架构/Benchmark？
   → 更新 `docs/compliance/AI_USAGE_LOG.md`

2. 新增外部依赖、服务、模型、数据、素材、示例代码？
   → 更新 `docs/compliance/THIRD_PARTY_RESOURCES.md`

3. 做了重要架构、接口、验证方法、Benchmark、范围或安全决策？
   → 更新 `docs/compliance/DECISIONS.md`

4. 实际执行了测试、Benchmark、故障注入或形成效果数据？
   → 更新 `docs/evidence/EVIDENCE_INDEX.md`

真实性规则：

- 不得声称运行过未运行测试。
- 不得猜许可证、模型版本、测试结果。
- 不确定时写 `UNKNOWN / TO_VERIFY / NOT_RUN`。
- AI 不得自行填写 `HUMAN_REVIEWED / ACCEPTED`。
- 默认审核状态为 `PENDING_HUMAN_REVIEW`。
- 不得写入 API Key、Token、密码、Cookie、私钥。
- 不得未经证据声称“首创”“首次”“行业空白”。

最终回复必须包含：

Changed:
- ...

Records updated:
- AI-...
- RES-... / none
- ADR-... / none
- EVID-... / none

Tests actually run:
- ...

Not run:
- ...

Pending human review:
- ...
```

---

# 11. 团队贡献记录

`TEAM_CONTRIBUTIONS.md` 模板：

```markdown
## YYYY-MM-DD — 任务名称

- 负责人：
- 协作者：
- 实际完成：
- 人工审核：
- 关联 AI Usage：
- 关联 Commit / PR：
- 关联 Evidence：
- 备注：
```

不要通过 AI 推测成员贡献，只记录实际发生的工作。

---

# 12. 机密信息规则

不得进入仓库或最终材料：

- API Key
- Token
- 密码
- 私钥
- Cookie
- 私人账户凭据
- 不必要个人敏感数据

只允许记录变量名：

```text
WOKWI_CLI_TOKEN=<REDACTED>
OPENAI_API_KEY=<REDACTED>
```

---

# 13. 正式评审材料清洗

技术报告、演示视频、答辩 PPT 和其他评审材料在导出前执行一次：

## FAIRNESS_CHECK

检查并清除：

- [ ] 学校名称
- [ ] 学校 LOGO
- [ ] 指导教师信息
- [ ] 不必要的账号名/个人信息
- [ ] API Keys / Tokens
- [ ] 无权公开的第三方内容

---

# 14. 赛前如何直接利用这些台账

## AI 工具使用说明

直接汇总：

`AI_USAGE_LOG.md`

得到：

- 使用过哪些 AI
- 各参与哪些模块
- 团队如何审核
- 团队如何修改
- 团队如何验证

## 官方《开源及第三方资源使用清单》

直接汇总：

`THIRD_PARTY_RESOURCES.md`

## 团队自主设计内容

直接汇总：

`DECISIONS.md`

## 实现完成度与可验证效果

直接汇总：

`EVIDENCE_INDEX.md`

## 真实性佐证

组合：

- Git commits
- AI Usage records
- ADR
- test logs
- Benchmark
- fault injection
- Issue / PR
- raw evidence

---

# 15. 最小执行成本原则

不要把合规记录变成另一份项目。

普通 AI 开发任务：

> **目标 2–5 分钟完成记录。**

只记录：

- 谁/哪个 AI 做了什么
- 改了哪里
- 人工审核状态
- 如何验证
- 引入什么第三方资源
- 对应什么证据

核心原则：

# 开发即留痕，而不是赛前考古。

---

版本：`AEDL Development & AI Compliance Standard v1.0`
