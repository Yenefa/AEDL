# 开源项目 Intake 目录

> 依据：《AEDL_开源项目吸收与再设计策略_2026-08-30.md》（同目录）
> 协议：任何新发现的 AI EDA / Hardware Agent 项目，统一走六步 Intake（CLAIM / SOURCE / FAILURE / REUSABLE / TRANSFORM / VERIFY），禁止只看 README 就下结论。
> 已完成：CircuitBot（Phase 1，2026-08-31，见 circuitbot.md）；KiCadAI + KiCad MCP（Phase 2-3，2026-08-31，见 kicadai.md / kicad-mcp.md）

## 目录

| 文件 | 项目 | 状态 | 结论一句话 |
|---|---|---|---|
| circuitbot.md | CircuitBot (HiwarkhedePrasad) | 六步完成 | 吃 clarify 交互模式与 5 维度框架，拒绝其 fail-open 超时继续；AEDL 重新定义为 requirements_contract + SHA256 门禁 |
| kicadai.md | KiCadAI (dshills) | 六步完成 | 生成前能力评估+证据挂链+fail-closed 为真实现；碰撞分析"生成链路未见源码"经本轮克隆复核判为误判已校准（writer/ERC/DRC/MNA 仿真源码俱在）。吃 preflight 机制与工具错误四分类，不接其代码 |
| neuroboard.md | NeuroBoard (Be-bibek) | 未开始 | 碰撞分析已核：IPC/UI/事件流可吃，事务回滚为位置级快照（半实现） |
| kicad-mcp.md | KiCad MCP（家族，深审 mixelpixx 版） | 六步完成 | 工具层判决缺席 by design，AEDL 判决自持不变；JLC 检索仅可做 discovery 不得做 gating；后继项目 Konnect 为 AGPL-3.0 禁接触 |

## 附属

- `_circuitbot_repo/`：本地克隆（ff9b003，2026-08-16），供后续 Phase 2-4 复查；含 .git，勿提交进 AEDL 仓库（已在 AEDL .gitignore 排除前先确认）。
- `_kicadai_repo/`：本地浅克隆（`4f18765`，2026-08-24，depth=1；Windows 检出需 `core.longpaths=true`），供人工复核本轮结论；含 .git，勿提交进 AEDL 仓库。
- `_kicad_mcp_repo/`：本地浅克隆（`aa53d52`，v2.7.0，2026-08-20，depth=1），同上，勿提交进 AEDL 仓库。
- 策略文档原件在同目录，已从 Downloads 归位（2026-08-31）。

## 铁律（继承自策略文档 §12）

成熟的轮子直接用；有缺陷的轮子拆开修；真正没有的机制集中火力自己造。
