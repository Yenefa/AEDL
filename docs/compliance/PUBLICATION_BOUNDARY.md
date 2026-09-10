# PUBLICATION_BOUNDARY — 再分发 / 隐私 / 证据三条边界

> 状态：`PENDING_HUMAN_REVIEW`。日期：2026-09-10。编制：Percy（W2 TASK-B6）。
>
> **本文件只回答一个问题：仓库若对外开放，哪些内容可以随之出去，哪些不能。**
>
> 归属（W2 r3 §B6）：再分发 / 隐私 / 证据边界属 Percy；**LICENSE 决策、secrets sign-off、
> 转 public 的时点属 Yenefa**。本文件对后三项只做输入，不做裁定。
>
> 上游真源：[`THIRD_PARTY_RESOURCES.md`](THIRD_PARTY_RESOURCES.md)（RES-001..010）、
> [`NOTICE`](../../NOTICE)、[`e5-protocol-v1.md`](../../notes/e5-user-trial/e5-protocol-v1.md) §8、
> [`OPEN_OUTPUTS.md`](../competition/OPEN_OUTPUTS.md)。本文件不改写上述任何一处，只做汇总与补缺。

---

## 0. 一句话结论

**三条边界中，隐私边界可以现在定死；证据边界基本清晰；再分发边界存在一处登记与实际状态不符，必须在转 public 前处理。**

---

## 1. 再分发边界

### 1.1 现状汇总（实查 RES-001..010）

| RES | 资源 | 随 AEDL 再分发 | 合规状态 |
|---|---|---|---|
| RES-001 | AEDL 开发记录与 AI 使用规范 v1.0 | `TO_VERIFY` | `TO_VERIFY` |
| RES-002 | OpenAI Codex desktop | NO | `TO_VERIFY` |
| RES-003 | AEDL AGENTS.md 源规范 | `TO_VERIFY` | `TO_VERIFY` |
| RES-004 | GitHub.com | NO | `TO_VERIFY` |
| RES-005 | akcli-kicad | NO | `TO_VERIFY` |
| RES-006 | jlcpcb CLI / JLC 目录 | NO | `TO_VERIFY` |
| RES-007 | 器件原厂数据手册与 LCSC 托管副本 | **NO** | `TO_VERIFY` |
| RES-008 | 本项目自身代码与文档（Apache-2.0） | 是 | — |
| RES-009 | LangGraph + langgraph-checkpoint | **字段空白** | **字段空白** |
| RES-010 | EDD-001 组件证据远程来源（六份） | 否 | `TO_VERIFY` |

### 1.2 ⚠️ B-1（必须在转 public 前处理）· RES-007 的登记与实际状态不符

**登记**：RES-007 写明 `是否随 AEDL 再分发：NO`，`最终开放方式：仅保留链接和必要事实引用`。

**实际**：`src/hardware/m2-board/evidence/datasheets/` 下 **8 份第三方原件、约 4.6 MB，全部被 git 跟踪**：

| 文件 | 体积 | 性质 |
|---|---:|---|
| `U1_ESP32-C3-WROOM-02/esp32-c3-wroom-02_datasheet_en.pdf` | 940 KB | 原厂数据手册 |
| `U1_ESP32-C3-WROOM-02/esp32c3_schematic_checklist_power_supply_2026-08-31.html` | 60 KB | 官方指南页面快照 |
| `U2_SHT30-DIS-B10KS/Sensirion_SHT3x_DIS_datasheet.pdf` | 792 KB | 原厂数据手册 |
| `U3_ME6211C33R5G/ME6211_V20_lcsc_official.pdf` | 848 KB | LCSC 托管副本 |
| `U3_ME6211C33R5G/ME6211_stm32base_mirror.pdf` | 1176 KB | **第三方站点镜像**（stm32-base.org） |
| `U3_CANDIDATE_AMS1117-3.3_C6186/AMS1117_..._C6186.pdf` | 96 KB | LCSC 托管副本，候选件 |
| `J1_TYPE-C-31-M-12/TYPE-C-31-M-12_drawing_elecfans_mirror.pdf` | 116 KB | **第三方站点镜像**，manifest 记为 `FROZEN_PROVENANCE_QUESTIONABLE`（带 HIROSE 水印） |
| `D1_KT-0603R/KT-0603R_KENTO_approval_spec_revA0.pdf` | 600 KB | **approval specification**（供应商承认书类文档） |

**仓库一旦 public，这 8 份就是被再分发了** —— 与 RES-007 的登记直接冲突。这不是措辞问题：`是否随 AEDL 再分发：NO` 是一条已登记的合规结论，而当前状态与之相反。

**已经做对的部分**（不必重做）：
- `NOTICE` 已逐份声明版权归原厂，并明确 AEDL 不主张著作权；对 TYPE-C 图纸的可疑来源、AMS1117 为 LCSC 托管而非官网，均已显式标注。
- `datasheet_manifest.json` 记录了 source_url / sha256 / retrieved_at 的完整归因。

**风险不均等，三档**：

| 档 | 文件 | 理由 |
|---|---|---|
| **高** | `KT-0603R_KENTO_approval_spec_revA0.pdf` | approval spec 属供应商对特定客户出具的承认书，通常不面向公开分发 |
| **高** | `TYPE-C-31-M-12_drawing_elecfans_mirror.pdf` | 来源已自记 `FROZEN_PROVENANCE_QUESTIONABLE`，带第三方水印 |
| **中** | 两份站点镜像（stm32base / elecfans） | 镜像件的再分发权比原厂官方副本更难主张 |
| **低** | 原厂 / LCSC 托管的常规数据手册 | 普遍可公开获取，但版权仍归原厂，`NO` 的登记依然有效 |

**建议处置（三选一，属 Yenefa 的最终裁定范围）**：

1. **转 public 前从工作树移除全部 8 份**，保留 `datasheet_manifest.json`（含 URL + sha256）与 NOTICE 声明 —— 与 RES-007 登记完全一致，代价是外部复现需自行下载。
2. **保留低风险的、移除高/中风险的**（至少 KENTO approval spec 与 TYPE-C 镜像）—— 折中，但需修改 RES-007 的 `NO` 登记，使登记与实际一致。
3. **全部保留** —— 必须先把 RES-007 的 `是否随 AEDL 再分发` 由 `NO` 改为实际值，并取得各权利人的再分发依据；在此之前 `TO_VERIFY` 不得当作「可以」。

> **无论选哪个，`git` 历史中仍留有这些文件。** 若最终结论是不得再分发，仅从工作树删除**不够** —— 这一点须在转 public 决策时一并考虑。

### 1.3 B-2 · RES-001 / RES-003 全字段 `TO_VERIFY`，但产物已在库中

两条登记的是 AEDL 开发记录规范与 AGENTS.md 的**源规范**，其再分发权、合规状态、最终开放方式**三项全为 `TO_VERIFY`**。而 `AGENTS.md` 本身就在仓库根目录、随时会被公开。

**`TO_VERIFY` 不是「可以」**。转 public 前须给出结论：这两份源规范的授权是否允许其衍生物公开。

### 1.4 B-3 · RES-009 字段空白

LangGraph + langgraph-checkpoint 一条**没有任何字段**（无许可证、无再分发、无合规状态）。需补齐后才能纳入公开审计。

### 1.5 已定、无需再议

RES-002 / 004 / 005 / 006 / 010 均已登记 `NO` 且理由清楚（不随仓库分发本机安装、服务或目录数据全集）。RES-008 为本项目自身产物，Apache-2.0，可随仓库公开。

---

## 2. 隐私边界（E5 用户数据）

### 2.1 结论：可以现在定死

协议 §8.2 已把口径由 `anonymous` 更正为 **`repository-pseudonymized`**，定义为：

> 仓库内仅出现编号与 pseudonymized 记录；真实身份只存在于 Percy 本人的线下通讯录，不入仓库、不入竞赛材料。

§8.2 同时留了一句：「**仓库公开前将再评估是否需要进一步脱敏**」。**本节即该再评估的结论。**

### 2.2 三档处置

| 内容 | 处置 | 依据 |
|---|---|---|
| **编号、背景表、访谈逐字记录、任务计时、两 arm 数据** | **可随仓库公开** | 已 pseudonymized；无姓名 / 联系方式 / 单位 |
| **真实身份、联系方式、所属实验室与课程名称** | **永不入库** | §8.2；本次招募已实测确认库内 0 命中 |
| **可间接识别的组合信息** | **需逐条判断，见 §2.3** | 小样本下的再识别风险 |

### 2.3 小样本的再识别风险（本次新增，非协议原有）

样本仅 3 人且背景已披露（人工智能 / 物联网及相关专业在校学生、分属不同实验室、画过 1 / 1 / 2 块板）。**这些信息单条无害，组合起来在小圈子内可能足以指认到人。**

**规则**：

- 报告与竞赛材料中**只出现汇总统计**，不出现「U-01 是那个只画过一块板的物联网专业学生」这类可拼合的个体描述；
- 逐字记录中若出现能定位到具体课程、项目名、实验室或竞赛的内容，**记录时即改写**（保留语义、去掉标识），并在该条记录中标注「已改写」；
- 违反本条的成本不可逆 —— 一旦公开，撤回无效。

### 2.4 退出权的技术落实

协议 §8.1 规定参与者可随时退出，且**退出前已收集记录的去留由其本人选择**。

- 选择「删除」时，须从工作树删除该 `U-0N.md`，并在 `recruitment-log.md` 记录「U-0N 已退出并要求删除，记录已移除」；
- **但 git 历史仍留有该文件** —— 若记录已进入公开历史，删除工作树不构成真正删除。
- **因此**：**E5 会话记录在仓库转 public 之前，应视为「可能需要撤回」的内容**；转 public 的时点须与 E5 数据的最终去留一并决定。这是给 Yenefa 的 public timing 决策的一条输入。

---

## 3. 证据边界

| 类别 | 实际内容 | 处置 | 依据 |
|---|---|---|---|
| **静态验证证据** | ERC / DRC JSON、网表、门禁结果、`notes/` 下 8 个运行证据目录 | ✅ 可公开 | AEDL 自研产物 |
| **渲染图 PNG** | 4 份 `board_*.png` | ⚠️ **公开前需审计** | `OPEN_OUTPUTS.md:64` 已登记「不随项目再分发：渲染图 PNG 本身（含板卡设计内容）」 |
| **制造导出物** | `delivery/`：gerbers、`bom.csv`、`pos.csv`、`jlc_gerber_upload.zip`、`manifest_v1.json` | ⚠️ **需决定** | 含完整板卡设计。**`manufacturing_release=false`、实测 `NOT_RUN`** —— 公开一套未经放行的制造文件，须明确标注其状态，避免他人据以下单 |
| **第三方原件** | 见 §1.2 | ❌ 见 §1.2 | RES-007 |
| **E5 用户数据** | 见 §2 | ✅ 按 §2 分档 | 协议 §8 |

**共同要求**：任何对外发布的证据必须保留其**证据等级标注**（静态检查 / 仿真 / 软件 loopback / 实体硬件），不得互相冒充。实体板 `NOT_RUN`、U3 `BLOCKED` 须如实随附，不得因材料好看而省略。

---

## 4. 转 public 前的检查清单

按处理顺序，前三项为**阻断项**：

- [ ] **B-1** RES-007 的三选一处置已裁定并执行（§1.2）；若选保留，RES-007 的 `NO` 登记须同步改为实际值
- [ ] **B-2** RES-001 / RES-003 的再分发权已由 `TO_VERIFY` 变为明确结论（§1.3）
- [ ] **B-3** RES-009 字段补齐（§1.4）
- [ ] E5 数据的最终去留已与转 public 时点一并决定（§2.4）
- [ ] 渲染图 PNG 与 `delivery/` 的公开与否已裁定（§3）
- [ ] 若结论含「不得再分发」，git 历史中的对应文件已一并处理（§1.2 末）
- [ ] secrets 扫描 0 命中 —— **属 Yenefa 的 sign-off**
- [ ] LICENSE 与转 public 时点 —— **属 Yenefa 的裁定**

---

## 5. 本文件不做的事

- **不裁定** LICENSE、secrets sign-off、转 public 的时点（属 Yenefa）；
- **不改写** RES-001..010 任何一条登记 —— 只指出登记与实际不符之处，改由 owner 决定；
- **不主张**任何第三方内容「可以公开」 —— `TO_VERIFY` 一律按「未获授权」处理，直到有明确依据。

---

## 版本表

| 版本 | 日期 | 状态 | 备注 |
|---|---|---|---|
| v1.0 | 2026-09-10 | `PENDING_HUMAN_REVIEW` | W2 TASK-B6；实查 RES-001..010、8 份第三方原件、NOTICE、manifest 后编制；发现 B-1/B-2/B-3 三处阻断项 |
