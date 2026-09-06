# SUBMISSION_CHECKLIST — AIC「AI+开源」正式提交清单

> 用途：AIC「AI+开源」评分项「材料规范与表达」的证据资产。进入报告、PPT、视频、正式提交或 Release 阶段时逐项核对。
> 素材来源：`AGENTS.md` §8.1（六个评分项与证据映射）、§8.6（FAIRNESS_CHECK）、§8.7（版本冻结）、§8.8（技术主张真实性）；`docs/competition/` 其余五件套；`docs/compliance/` 台账。
> 状态：DRAFT，`PENDING_HUMAN_REVIEW`。本清单是"进入正式提交时"的核对工具，不是当前已完成事项的声明；凡未完成的项保持未勾选。

---

## 0. 赛事关键信息（以官网为准，提交前复核）

- 赛事：第八届全球校园人工智能算法精英大赛（2026），算法主题赛「AI+开源」
- 官方赛题页：`https://www.aicomp.cn/tracks/tracks-5/4924.html`
- 报名入口：`https://reg.aicomp.cn/`
- 截止时间：官方开源初赛 2026-10-15 20:00（2026-09-06 按官网核实更正；原记录约 2026-10-03 为过期信息。提交前仍以官网最新通知为准）
- 团队/成员/指导教师/项目流程修改窗口：以官方规则为准（此前已确认可修改，提交前再核官网）
- 参赛承诺书：需手写签名后扫描/拍照上传（此前已确认）

> ⚠️ 以上赛事信息来自此前会话核实的官网页面；**提交前必须重新打开官网复核**，本清单不替代官网。

---

## 1. 六个评分项证据映射（AGENTS.md §8.1）

| 评分项 | 证据资产 | 当前状态 |
|---|---|---|
| 问题与场景价值 | `docs/competition/PROBLEM_EVIDENCE.md` | 已建（4 起真实事故） |
| 创新性与方案设计 | `docs/compliance/DECISIONS.md` + Baseline | 已建（ADR-001..005） |
| AI 与开源融合 | `docs/competition/FUSION_MAP.md` + `docs/compliance/THIRD_PARTY_RESOURCES.md` | 已建（六大能力） |
| 实现完成度与可验证效果 | `docs/evidence/EVIDENCE_INDEX.md` | 已建（EVID-20260829-001/002/003、EVID-20260830-001） |
| 开放成果与复用价值 | `docs/competition/OPEN_OUTPUTS.md` | 已建（协议/门禁/夹具/提示词） |
| 材料规范与表达 | `docs/competition/SUBMISSION_CHECKLIST.md` | 本文件 |

---

## 2. 提交前材料核对清单

### 2.1 核心材料

- [ ] 技术报告（版本号 + 生成日期 + 与冻结 commit 对应）
- [ ] 演示视频（16:9，1920×1080；含版本号；与报告/代码版本一致）
- [ ] 答辩 PPT（版本号）
- [ ] 参赛承诺书（手写签名扫描/拍照件）
- [ ] 报名表信息复核（团队名称、成员、指导教师、项目流程）
- [ ] 项目简介 / 技术路线图（与 FUSION_MAP 一致）

### 2.2 代码与仓库

- [ ] 仓库 LICENSE 已确定（当前 `TO_VERIFY`，ADR-003 公开化决策前置）
- [ ] 4 个含本机用户路径的已跟踪文件已参数化或脱敏（ADR-003 记录）
- [ ] secrets 扫描 0 命中（API Key / Token / 密码 / 私钥 / Cookie / 私人账户凭据）
- [ ] 第三方资源清单版本与 `THIRD_PARTY_RESOURCES.md` / `notes/open_source_intake/THIRD_PARTY.md` 一致
- [ ] 克隆审查目录（`notes/open_source_intake/_circuitbot_repo/` 等）已按 `.gitignore` 排除，不随仓库提交
- [ ] 公开内容审计完成（含渲染图、板卡设计、目检产物）

### 2.3 版本冻结（AGENTS.md §8.7）

进入阶段提交/初赛提交/决赛提交/正式 Release 时记录并核对：

- [ ] commit hash（建议 tag：`aic-2026-initial` / `aic-2026-final`）
- [ ] Git tag / GitHub Release
- [ ] 技术报告版本
- [ ] 演示视频版本
- [ ] 第三方资源清单版本
- [ ] Evidence 索引版本
- [ ] 开放成果版本
- [ ] 成果链接有效性（报告/视频/截图/代码全部回到同一确定版本）

---

## 3. FAIRNESS_CHECK（正式材料输出前逐项核对）

> 来源：AGENTS.md §8.6。以下任何一项在正式技术报告、演示视频、答辩 PPT、评审截图和其他提交材料中出现，必须先移除或脱敏。

- [ ] **学校名称**：不出现（除非官方要求标注）
- [ ] **学校 LOGO**：不出现
- [ ] **指导教师信息**：不出现（除非官方要求）
- [ ] **不必要账号/个人信息**：不出现
- [ ] **API Key / Token / secrets**：不出现（一律占位符 `<REDACTED>`）
- [ ] **无权公开的第三方内容**：不出现（KiCad 库、akcli、jlcpcb 数据、数据手册全文、被借鉴项目代码）
- [ ] **无 Evidence 支撑的技术/创新主张**：不出现（一律用"截至检查日尚未发现等价实现"并配证据 ID）
- [ ] **成果链接不可访问或版本不一致**：不出现（提交前逐条验证链接与版本）

### FAIRNESS_CHECK 附加（本项目专属）

- [ ] 不把"用了 Git / Python / LLM / 开源库"当融合创新（AGENTS.md §8.2）
- [ ] 不把第三方能力写成 AEDL 自研能力（AGENTS.md §8.4：自研 / AI / 第三方 / 外部贡献分开）
- [ ] 不把机器门禁/ERC/DRC/语义合同表述为实体 C 级验证（HANDOFF 约束）
- [ ] 不把"板子能工作"作为已成立结论（回件前 C 级实测 `NOT_RUN`）
- [ ] 不使用"首创 / 首次 / 行业空白 / 行业领先"字样（AGENTS.md §8.8）
- [ ] 不引用 kicad-ai（amcolex）的任何描述（仓库真实性待人工定案）
- [ ] Konnect（AGPL-3.0）零接触声明已写入 THIRD_PARTY.md 红线行

---

## 4. 技术主张真实性（AGENTS.md §8.8）

提交前对每一条性能/稳定性/效果/创新性/复用价值主张核对：

- [ ] 有真实 Evidence / ADR / Repository History 对齐
- [ ] 没有对照却声称显著优于 Baseline → 不写
- [ ] 没有运行却填写测试结果 → 不写（写 `NOT_RUN`）
- [ ] 普通工具使用包装成创新机制 → 不写
- [ ] 第三方能力写成 AEDL 自研能力 → 不写
- [ ] 无证据声称"首创/首次/行业空白/行业领先" → 不写

---

## 5. 当前未完成项（诚实登记）

- [ ] 项目 LICENSE 未定（`TO_VERIFY`）
- [ ] 仓库公开化决策未做（ADR-003）
- [ ] 回件后实体 C 级实测未执行（`NOT_RUN`）
- [ ] `board_review` 的 `manufacturing_release` 仍为 `false`，等待人工重签
- [ ] 需求合同 `intent_binding` 的 `intent_semantic_sha256` 重签待人工审（TASK-C）
- [ ] P2 前端真实 API 联调 `NOT_RUN`（待 P1 定案契约冲突）
- [ ] 演示视频 / 答辩 PPT / 技术报告正式稿未产出
