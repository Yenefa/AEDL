# Control-Plane Donor 模板

> 适用层：**control-plane**——给 AEDL 自己的 Agent-native 开发控制面（admission /
> execution / verification / contract / context）找 donor。产品层 donor（AI EDA /
> Hardware Agent 能力）走同目录六步 Intake 策略文档，两批不混。
>
> 目的：拿回"工程情报"而不是"项目牛逼"。每格结论必须能直接喂给 AEDL 架构决策。

## 元信息

- Layer: `control-plane` | `product`（本模板只用于 control-plane）
- Reviewed: <YYYY-MM-DD> | Verifier: <谁/什么工具> | Status: `CONFIRMED` / `STRONG_REPORT` / `ANECDOTE`
- Primary sources: [<name>](<url>)（逐条挂链接）

## Capability

<什么能力，一句话；必须是机制级，不是功能列表>

## Mechanism

<怎么实现的：决策路径、插入点、数据结构、生命周期>

## Maturity

每条挂证据：

- <CONFIRMED / STRONG_REPORT / ANECDOTE>：<事实>（[source](url)，核实日期）

## Failure Mode

每条带置信度：

- <CONFIRMED / STRONG_REPORT / ANECDOTE>：<已知坑/事故/设计退化>

## AEDL Adaptation

- 吸收什么（最小落点，能对应到 tools/、AGENTS.md、docs/、tests/ 的具体位置）
- 明确不做什么（防止"吃成依赖"）

## Trigger

<什么真实事件发生才动手；事件没发生就不研究不实现>

## 置信度定义

- `CONFIRMED`：独立核实过 primary source（raw 抓取/官方文档原文/已发布 advisory）
- `STRONG_REPORT`：有具体、高优先级公开报告（open issue 等），但尚未定论为官方确认
- `ANECDOTE`：传闻/营销文案，未核实
