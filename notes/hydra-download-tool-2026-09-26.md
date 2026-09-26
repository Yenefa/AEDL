# hydra 下载工具实测与 Agent 下载决策准则

- 日期：2026-09-26
- 记录者：OPENCODE（AI，见 `AI-20260926-OPENCODE-65018682D75AB30F6B0863D636B20EBC`）
- 人工审核：`PENDING_HUMAN_REVIEW`
- 范围：**开发工具（DEV_ONLY）评估**。不涉及 AEDL 核心机制、门禁、合同或 Evidence 语义；
  本文不构成任何比赛技术主张，也未产生 EVID-*。
- 第三方资源登记：RES-012（`docs/compliance/THIRD_PARTY_RESOURCES.md`）

## 1. 为什么做这件事

Agent 在本项目及其他工作里经常需要下载较大的外部资源（安装包、release 资产、镜像内数据）。
默认用 `curl` / `Invoke-WebRequest` 是单连接流式下载，遇到"服务端对单连接限速"时会浪费时间。
本轮实测一个多连接下载器（hydra）到底**在什么条件下才有用**，并把结论固化成 Agent 可执行的决策准则，
而不是留下"用多线程下载更快"这类未经验证的说法。

## 2. 工具事实（全部来自本机实测输出，未猜测）

| 项 | 值 | 来源 |
|---|---|---|
| 名称 / 版本 | hydra 0.6.1 | `hydra --version` |
| 作者 / 版权 | Copyright (C) 2026 Javad Rajabzadeh | `hydra --version` |
| License | 二进制本体 GPL-3.0-or-later；链接的 `hydra-core` / `hydra-net` 库为 MIT OR Apache-2.0（见其 `THIRD-PARTY-NOTICES.md`） | `hydra --version` 输出原文 |
| 安装路径 | `C:\Users\<user>\AppData\Local\Programs\Hydra\`（`hydra.exe` / `hydra-gui.exe` / `hydra-host.exe` / `hydra-updater.exe` / `hya.exe` + `extensions\` `scripts\`） | 目录列举 |
| 是否在 PATH | 是（`where.exe hydra` 命中） | `where.exe hydra` |
| 二进制是否入仓 | **否**（机器本地安装，仓库只留本报告与决策准则摘要） | 本轮工作树 |

上游仓库 `ja7ad/hydra`；本轮**未**克隆其源码，也未审计其实现，机制描述仅引用其 `--help` 自述文本，
未独立验证调度器内部行为（`TO_VERIFY`）。

## 3. 测试环境

- Windows + PowerShell；单一 ISP 链路；单机器、非并发测试
- 被测对象：hydra 0.6.1
- 基线：系统自带 `curl 8.9.1 (Windows) libcurl/8.9.1 Schannel zlib/1.3`
- 临时工作目录：仓库外 `%LOCALAPPDATA%\Temp\opencode\hydra-tests\`
  （测试后已删除大体积下载物，保留报告与小型取证样本；**该目录不入 git**）

## 4. 测试矩阵

| ID | 测试 | 期望 | 实测 | 判定 |
|----|------|------|------|------|
| T1 | Range 支持探测（GitHub release 资产） | HTTP 206 + `Accept-Ranges` | `http=206`，取回 100 B，`Accept-Ranges: bytes`，总长 111161483 | PASS |
| T2 | `--inspect` 只探测不下载 | 报出大小/类型且不落文件 | 报出 size/type；对 `speed.cloudflare.com` 明确 `Resumable: no` | PASS（见 F2） |
| T3a | `--fail` + 404 URL | 非零退出 + 原因 | exit=1，`server answered 404 Not Found` | PASS |
| T3b | `--fail` + 正常 URL | exit 0 | exit=0 | PASS |
| T4 | `--checksum` 故意给错 hash | 非零退出 + 明确信息 | exit=1，`checksum MISMATCH: the delivered bytes are not the bytes requested` | PASS |
| T5 | `--checksum` 给正确 hash | exit 0 | exit=0（实算 sha256 `eef10c4b…d1c19eb`） | PASS |
| T6 | `-c` 从截断文件续传（50 MiB → 全量） | 从断点续、完成到全尺寸 | `resumed_from=52428800`，终尺寸 178473080，`ok=true`，exit=0 | PASS |
| T7 | **服务端忽略 Range**（`speed.cloudflare.com`） | （原设想）优雅退化为单流 | **exit=1**，`ok=false`，`note: server ignored Range and sent 200 for a request from offset …` | **与设想不符 → 见 F1** |
| T8 | `--preview` 列 32.6 MB ZIP 内容 | 不整包下载即列目录 | 列出 2521 个文件，exit=0，只取回索引 | PASS |
| T9 | `--json` 模式下失败如何报告 | 解析器能拿到原因 | 原因在 stdout JSON：`ok=false` + `note=…`；**stderr 为空（0 字节）** | PASS 带坑（F3） |
| T10 | `--inspect` + `--json` | 机器可读 JSON | 输出仍是人读表格，`--json` 未生效 | 与期望不符 → F4 |

## 5. 基准：curl（单连接）vs hydra（自适应多连接）

同一 URL 逐次交错执行（`https://cdn-zcode.z.ai/…/ZCode-3.14.3-win-x64.exe`，
178,473,080 B，探测确认 `Resumable: yes`）：

| 次序 | 工具 | 耗时 | 吞吐 | 明细 |
|---|---|---|---|---|
| 1 | curl | 22.92 s | 7.79 MB/s | 1 连接 |
| 2 | hydra | 11.65 s | 15.55 MB/s | 4 连接，15 requests |
| 3 | curl | 13.70 s | 13.02 MB/s | 1 连接 |
| 4 | hydra | 15.62 s | 11.54 MB/s | 4 连接，10 requests |

旁证（与工具无关的网络事实）：同一时段从 GitHub release 资产用 curl 拉取仅约 34 KB/s
（300 s 只拿到 10 MB，该次测试中止），而 cdn-zcode.z.ai 为 8–15 MB/s。

### 5.1 结论（如实，不夸大）

- 两组数据**重叠明显**：curl 最好的一次（13.70 s）快过 hydra 的某一次（15.62 s）；
  hydra 最好的一次（11.65 s）也快过 curl 最好的一次（22.92 s）。
- **本轮未能证明稳定提速**。n=2/组、交错单次、无重复试验，方差 ≥ 2 倍
  （curl 第一次偏慢可能含 CDN 边缘节点冷启动）。
- 加速幅度主张：**`TO_VERIFY`**（需 n≥3/组、受控交错、记录同窗口网络条件）。
  在拿到该数据前，**禁止**在任何文档或汇报中引用"hydra 比 curl 快 X%"。

## 6. 发现与对 Agent 准则的修正

| # | 实测发现 | 对准则的修正 |
|---|---|---|
| F1 | Range 被忽略时 hydra **不会**自动退化为单流，而是 exit=1 硬失败 | 决策规则改为：**下载前先 `--inspect` 看 `Resumable: yes/no`；`no` 就用普通 curl** |
| F2 | `--inspect` 是零成本预检（`Resumable` 字段直接对应多连接前提） | 纳入决策流程，作为"是否值得多连接"的前置探针 |
| F3 | `--json` 失败时错误在 stdout 的 `ok`/`note` 字段，stderr 可能为空 | 准则规定：失败时必须解析 JSON，不能因 stderr 空就判定"无错误信息" |
| F4 | `--inspect` 不接受 `--json` | 准则注明其输出只能按文本解析 |
| F5 | 输出路径含非 ASCII 时，PowerShell `ConvertFrom-Json` 报 `Bad JSON escape sequence` | 准则要求先 `[Console]::OutputEncoding = [Text.Encoding]::UTF8` |
| F6 | 用 `Select-Object -First N` 截断管道会污染退出码观测（T8 首跑 exit=1，重定向到文件后 exit=0） | 准则要求预览类输出先重定向到文件再看退出码 |
| F7 | 同工具同 URL 两次运行差异可达 2 倍 | 准则重申"禁止承诺加速百分比"，要求交错 ≥2 轮并报实测值 |

## 7. 准则落点

Agent 决策准则已固化为**机器级 OpenCode skill**（不在本仓库内）：

```
~/.config/opencode/skills/hydra-download/SKILL.md
```

选择机器级而非入库的理由：hydra 是**开发机本地安装**的工具，与具体仓库无关；
放全局可让所有项目的 Agent 复用，入库则会造成"仓库里有规则但环境未必有工具"的错配。
若后续决定让 AEDL 仓库自带该 skill，需另开一轮并显式登记为可选依赖。

准则骨架（摘要，权威版本在 skill 文件）：

1. 先 `where.exe hydra` 确认可用；不可用则回退 curl 并如实说明，不阻塞任务。
2. 满足"文件 ≥ ~20 MB 或需续传/校验/镜像合并"**且** `Resumable: yes` **且**非交互 → 用 hydra；否则用普通 curl。
3. Agent 调用模板固定为 `--json --fail -P <dir>`，有发布方 hash 时必带 `--checksum`，无 hash 则报 `checksum: NOT_PUBLISHED`。
4. 只报实测数字（路径、尺寸、耗时、requests 数），**不报未测的加速幅度**。
5. 失败处理：非零退出 → 解析 JSON 原因；checksum 不匹配 → 是字节错误，不是网络抖动，**不得盲目重试**。

## 8. AEDL 边界与未做事项

- hydra 在本项目中的角色：**DEV_ONLY**（下载通道），不参与任何门禁判定、评分或技术主张。
- 未修改 hydra 上游源码；未把其二进制、脚本或扩展入仓；不再分发。
- 加速结论 `TO_VERIFY`；本文不进入 `docs/evidence/`，不生成 EVID-*。

### 未运行 / 限制

- `--mirrors` 多镜像合并：`NOT_RUN`（需要同尺寸同 validator 的两个同源副本）。
- `parity`（Reed-Solomon）、`metalink`、HLS/DASH 码流选择与直播录制：`NOT_RUN`。
- hydra 调度器内部实现的独立审计：`NOT_RUN`（仅引用其自述）。
- 多平台 / 长时间稳定性、代理与 Cookie 流程：`NOT_RUN`。
- 基准 n=2/组、单机单链路、时段固定在 2026-09-26 下午；不构成分布式结论。

## 9. 复现命令（脱敏后按需替换路径）

```powershell
# 工具事实
hydra --version
where.exe hydra

# 预检（是否支持 Range / 是否可续传）
hydra --inspect "<URL>"

# Agent 标准调用（机器可读 + 失败非零 + 指定目录）
hydra -P "<dir>" --json --fail "<URL>"

# 基线对照（单连接）
curl.exe -s -L -o "<dir>\out.bin" -w "http=%{http_code} bytes=%{size_download} time=%{time_total}\n" "<URL>"

# 校验（发布方给出 hash 时）
hydra --fail --checksum "sha256:<hash>" -P "<dir>" "<URL>"

# 续传
hydra -c -q -P "<dir>" --json "<URL>"
```

## 10. 人工确认项

- 本报告与 RES-012 条目均待人工 review；AI 不 merge、不 approve。
- 加速主张在补齐 n≥3 受控对照前，保持 `TO_VERIFY`，不得对外引用数字。
- 是否把该 skill 纳入仓库（可选依赖）需 Owner 决定。
