# SchGen comparator 解剖 + Benchmark oracle 分层 + AP63203 事实核验（2026-10-02 外部调研存档）

> 来源：ChatGPT DeepSearch 外部调研，由 Owner 于 2026-10-02 提供原文，本文件为逐字入库。
> 状态：**研究输入，不是团队决策**。其中 benchmark 口径建议（§5）若采纳，需另立 ADR（Verification
> Protocol / Benchmark 口径变更）并经 Owner 裁决；AP63203 事实核验（§7）可作为 POWER
> 合同冻结复核的输入之一。
> 凡标注“估计”“我估计”处为工程估算，不是外部来源事实；凡写 UNKNOWN 处为未查到，不得引作结论。

---

## 0. 结论（Primary oracle 口径建议）

- Primary oracle = AEDL frozen-contract FAIL→PASS
- Regression guard = 非目标合同仍 PASS
- Secondary score = SchGen structural F1/Jaccard / collateral delta

也就是说，SchGen 给“分”，AEDL 合同给“判决”。

改动量级属于小到中等：在已有只读 adapter 的前提下，估计约 1–3 个工程日能做出可信 v1，
包括 comparator wrapper、实例身份修正、before/after fixture 和多解测试。
（这是工程估算，不是外部来源事实。）

---

## 1. SchGen 到底在比什么？

### 1.1 它不是逐连接 edge comparison，而是「net 的 endpoint-set」

当前 netlist_comparison_new.py 会：

1. 从 KiCad netlist 的 components 中建立 ref → (lib, part)；
2. 对每个 net 读取它包含的 nodes；
3. 把每个 node 转换为：`lib:part:pin`
4. 一个 net 变成一个 `frozenset(...)`；
5. 整张板最终成为一个 set of frozensets；
6. 然后两个整板集合做 exact intersection，算 Jaccard / precision / recall / F1。

这意味着一个例如 `U1.Pin3 + C4.Pin1 + R7.Pin2` 组成的网络，不是按三条 edge 分开算，
而是整个 endpoint 集合必须和 golden 中某个 net 的 endpoint 集合完全一致才算一个
matched net。只差一个 endpoint，那个 net 就不是 partial match，而是整个 signature
mismatch。

### 1.2 器件比较：有，但存在一个很重要的信息损失

它使用 lib、part、pin，但最终 token 不包含 instance ref。也就是说：

- R1 和 R7 如果来自同一个 library part；
- 比较空间最终都只留下类似 `Device:R:1`；
- R1 / R7 的实例身份被抹掉。

这不是小问题。对于 generation benchmark，它可能是在追求“功能结构等价”；
但对于 repair benchmark，你经常关心的是“U3 的 Pin 4 必须接 GND”，而不是
“某个同类型器件的 Pin 4 接 GND 就行”。因此它的 identity semantics 天生比 AEDL
repair contract 弱一层。

### 1.3 Net name 基本不参与评分

GND、VBUS、3V3 等 net name 不是 endpoint signature 的组成部分。net name 主要被用于
识别并丢弃形如 `unconnected-(...)` / `Net-(...)` 的 dangling singleton nets；
真正比较的是 endpoint set。

所以一个极其典型的 AEDL 合同（`U1.PinX must be on GND`）不能简单认为 SchGen 会
忠实地把“GND 语义”评分进去。它评分的是 connectivity equivalence，不是冻结
net-label semantic contract。

### 1.4 Value / MPN / tolerance 呢？

当前 comparator 没有把 component value、MPN、tolerance、voltage rating、
power rating、footprint、datasheet constraint 放进 signature。

因此这里不是“SchGen 给了 ±5% 电阻容差”，而是：这些参数根本不在这个 netlist
scorer 的评价维度里。

另一方面，对于 connectivity endpoint-set 本身，它又几乎是 zero tolerance：
集合必须 exact-equal 才算 matched net。

## 2. SchGen 的通过/失败阈值是什么？

答案：这个 netlist scorer 本身没有 PASS/FAIL threshold。`compare_netlists_sets()`
返回 nets_A、nets_B、matched_nets、jaccard、precision_A->B、recall_A->B、f1_A->B，
但没有诸如 `f1 >= 0.95 => PASS` 这样的逻辑。

更容易误读的是 sch_evaluation.py 里的 `{"passed": 1}`：这个 passed 是生成代码没有抛
execution exception 后设置的；netlist evaluation 和 ERC error counts 是另外附加进去
的字段。也就是说，这里的 passed=1 不能解释为“电路通过 SchGen connectivity
benchmark”。

所以“通过/失败阈值是多少”，严格答案就是：UNKNOWN / 不存在于当前公开 scorer
implementation 中。如果论文实验阶段另外使用了 aggregate threshold，需要引用论文
实验定义；当前公开 comparator/evaluator 代码本身没有单样本 connectivity PASS
cutoff。SchGen 论文把该系统定位为 NL→editable schematic generation，并报告
connectivity/functionality evaluation，但不能反推出这个 comparator 存在隐藏的
binary threshold。

## 3. 输入格式：AEDL 的 KiCad netlist 能不能直接进？

文件层：可以，前提是同类 KiCad S-expression export。SchGen 自己调用
`kicad-cli sch export netlist` 生成 netlist，然后把文本送给 comparator。
Comparator 依赖的核心 block 是 components / comp / libsource / nets / net /
node / ref / pin。因此如果 AEDL 所谓 fresh netlist 就是现代 kicad-cli sch export
netlist 输出，wire format 不需要先转换成 SchGen 私有 JSON。

如果已有 netlist 是另一种 KiCad legacy XML / custom canonical format，没有看到
实际样本的话不会猜：UNKNOWN。

语义层：不能称为无损。这是最容易踩坑的一点。虽然原始 KiCad netlist 可以直接喂进去，
但 SchGen 会投影掉：instance ref、net name、component value、footprint/MPN 等信息。
所以准确表述必须是：输入 wire-format 可以直接接；进入 SchGen scoring
representation 后是 lossy projection。因此不会写“KiCad netlist 可无损转入 SchGen”。

## 4. 与 AEDL「单规则 FAIL→PASS」到底哪里不兼容？

| 维度 | SchGen | AEDL repair contract | 结论 |
|---|---|---|---|
| Granularity | 整板 net-set similarity | 单条冻结规则 before/after | 不相容 |
| 判定性质 | 连续分数 Jaccard/P/R/F1 | binary FAIL→PASS | 不相容 |
| 连接容差 | 一个 net endpoint-set 要 exact match | 只要求目标合同成立 | 过严/错层 |
| 参数容差 | value/tolerance 不评分 | 可以由合同定义 | 缺失维度 |
| Net semantics | net name 不进入 signature | GND/3V3/VBUS 等可直接是规则语义 | 不相容 |
| Instance identity | ref 被投影掉 | 可指定特定器件/引脚 | 不相容 |
| 多解接受 | 相对于一个 golden topology | 任何满足冻结合同的修复都应接受 | 不相容 |
| Collateral damage | 全板 F1 可以感知大量结构变化 | 需要明确验证非目标合同未退化 | 可作为辅助指标 |

SchGen 的目标本身是 natural-language PCB schematic generation，因此用 golden
schematic connectivity 做整体相似度是合理的；这和 repair task 不同。

一个非常具体的反例：冻结规则 `U3.EN must connect to VIN`。Agent A 只改一个 label
使它满足合同；Agent B 用另一种 electrically valid topology 解决相同问题。只要它们
不复现 SchGen golden net 的完整 endpoint membership，两者的该 net 都可能不算
exact matched net；而从 AEDL repair 任务看，两者可能都应该 PASS。

反过来，也存在更危险情况：如果一个修改保持 endpoint membership 不变，只改变了
重要的 semantic net label，那么 SchGen 结构分数可能不反映这条合同是否已经被修好。

## 5. 建议的 SchGen→AEDL benchmark 架构

不是改合同去迁就 benchmark，而是把 SchGen 降级为第二 oracle：

- **Tier 1 — Repair correctness**，决定 PASS。固定 same frozen contract + fresh
  netlist，要求 before = FAIL、after = PASS。这是 episode 成功的必要条件。
- **Tier 2 — Regression safety**，仍然是硬门禁。验证原来 PASS 的 frozen contracts
  没有因为 repair 变 FAIL；不允许改变的 design region 没变化；verifier 必须
  read-back fresh artifact，而不是相信 agent 自报。这符合 AEDL“独立 read-back
  verifier、fail-closed、candidate/baseline 隔离”架构。
- **Tier 3 — SchGen structure score**，只作为质量分。记录 Jaccard、Precision、
  Recall、F1、before→after delta。用途是回答：“虽然修好了目标问题，但它为了修一根
  网，把半张板搞没了吗？”

如果还想提高 scorer 对 repair 的可解释性，可以对 SchGen projection 做两处
modification：保留 ref identity（endpoint 逻辑身份至少能区别 U1 与 U7）；为 AEDL
合同敏感的 named nets 建立 semantic channel，而不是把 GND/VBUS/3V3 全部抹掉。

## 6. 对 AEDL 来说，这个结果其实是好消息：真正的 moat 在哪里

截至 2026-10-02，简单的“AI + KiCad + MCP + ERC/DRC”已经不构成壁垒。公开生态：

| 项目 | 已经做到的东西 | 对 AEDL 的含义 |
|---|---|---|
| KiCad Agentic MCP | typed/reference-checked Plan IR、deterministic execution、transaction/rollback、revision/idempotency、semantic diff、server-side evidence、kicad-cli ERC/DRC + read-back 决定结果 | “deterministic executor + independent readback + evidence”本身已不独有 |
| Copperhead | NL brief→spec→architecture→parts→schematic/layout，直接编辑 KiCad，proposal-gated mutation，ERC/DRC loop、git rollback、人类最终 sign-off | “spec before edit / verify after edit”已进入开源项目 |
| KiCad Copilot | MCP、自然语言修改 schematic、PCB placement/local routing、checkpoint、kicad-cli ERC/DRC/export、offline design analysis | KiCad MCP 和 NL→EDA execution 正快速 commodity 化 |
| KiCad MCP Pro | schematic/PCB/ERC/DRC/DFM/BOM/manufacturing review；readonly/build/release profile；明确不自称 sign-off authority | tool breadth 和 permission profiles 也不能单独当壁垒 |
| PCB Flow | requirements→BOM→schematic→placement→routing→verification→manufacturing，human checkpoints，EasyEDA/KiCad | “阶段流水线 + 人工 checkpoint”本身也不稀缺 |
| SchGen | NL→editable PCB schematic，semantic-grounded primitives，大规模数据集，connectivity/function evaluation | generation benchmark 正在形成，不该和它正面比“谁更会生成” |

研究界也正在从“LLM 会不会画电路”向 agent workflow evaluation 移动（PCB-QA 比较 LLM
对 KiCad/native PCB 表示的理解；FluxBench 证明相同 foundation model 下 agent
architecture 本身会显著改变完整 EDA workflow 的表现）。

AEDL 的技术主张应收敛为：预先冻结、独立于生成器的工程语义合同；基于 fresh
artifact 的独立 read-back；在同一合同上证明真实 FAIL→PASS；允许
contract-equivalent 多解；同时证明非目标约束没有退化，并把整个因果链固化成可审计
Evidence。

关键句：不是“agent 修完后 ERC=0”，而是“一个在修复前已经存在且不可随候选修改的
外部合同，原来明确 FAIL；同一合同在 fresh output 上明确 PASS”。这一层比单纯
ERC/DRC 更强。KiCad Agentic MCP 和 Copperhead 已逼近很多工程思想，但它们公开描述的
oracle 仍主要是 KiCad ERC/DRC、设计 read-back、spec drift 等；AEDL 如果把 frozen
external semantic contract + repair episode causality 做扎实，这才是现在还能成立的
differentiator。

## 7. AP63203 / ESP32-S3-LCD-EV / USB 电源事实核验

全部以 Diodes DS41326 Rev. 3-2, November 2024 为当前基准。

| # | 裁定 | 核实结果 |
|---|---|---|
| 1 | 对，但 Figure 编号描述需修正 | DS41326 Rev.3-2, Nov 2024，Table 2 对 AP63203 / 3.3V 明确给出 L=3.9µH、C1(Cin)=10µF、C2(Cout)=2×22µF、C3(CBST)=100nF。但 AP63205 / 5V / L=4.7µH 的典型应用电路是 **Figure 1，不是 Figure 2**；Figure 2 是 efficiency-vs-output-current 图 |
| 2 | 对 | EN rising threshold VEN_H：min 1.15V、typ 1.18V、max 1.23V；正文 upper threshold approximately 1.18V |
| 3 | 对 | AP63203 系列额定 3.8–32V input、2A；AP63203 是 fixed 3.3V variant；ordering table AP63203WU-7 = TSOT26 |
| 4 | 错（原句是混合命题） | ESP32-S3-LCD-EV-Board MB V1.5 的 SYS 3.3V 是 ETA3409S2F；SY8088AAC 产生约 3.3V Audio VDD；ME6211C18M5G-N 是 1.8V rail。因此“3.3V rail 由 SY8088/ETA3409/ME6211 共同供电”不准确；但“它不能作为 AP63203WU-7 方案先例”和“ME6211 只供这里的 1.8V rail”均成立 |
| 5 | 对，需精确措辞 | USBLC6-2SC6 是 USB 两条数据线 + VBUS 的 ESD/transient protection network（rail-to-rail protection）；VBUS 在这里是 clamp rail，不是拿该 IC 串进整板 VBUS load path。ESP32-S3-LCD-EV-Board V1.5 中两个 USB VBUS 分别经 SS34 汇入 USB_5V，因此在该具体原理图里的功能可准确描述为 input isolation / diode-OR / anti-backfeed |

Rev 差异核验：可核到的旧版是 DS41326 Rev.2-2, January 2019。对于本次关心的
AP63203 Table 2（3.9µH / 10µF / 2×22µF / 100nF）与 EN rising typical（1.18V），
Rev.2-2 与 Rev.3-2 Nov 2024 没发现变化。但 revision 不是纯排版更新（另一非本次目标
参数中 AP63200/AP63201 3.3V configuration 的 Table 1 resistor 值可见新旧版变化），
所以合同必须继续 pin 到 DS41326 Rev.3-2 / Nov 2024，不要只写“AP63203 datasheet”。

## 8. 据此建议改的三个技术主张

1. 别再把“KiCad MCP / 自动 ERC/DRC / agent 可以自己修板”放在核心创新位。2026 年 10 月
   这个赛道已经过线，别人甚至有 transaction、rollback、semantic diff、server-side evidence。
2. 把 Repair Episode 做成真正可发表/benchmark 的东西：frozen contract at T0 →
   verified pre-state FAIL → agent only receives permitted evidence/actions → mutation →
   fresh independent export → same contract PASS → non-target contracts still PASS →
   immutable before/after evidence bundle。这个比“ERC 从 7 个变 0 个”强太多。
3. SchGen 正好能补上缺的一条轴，但不能接管 oracle。可以公开报告两个指标：
   Contract Repair Success Rate（修复语义到底对没对，AEDL 自己的东西）；
   Structural Preservation Score（为了修这一处到底破坏了多少原电路，可从 SchGen
   net-set methodology 派生）。不是硬蹭 SchGen benchmark，而是把它放到正确的
   measurement layer。

判断更新：“独立验证”已不足以做 moat；“独立、预冻结、不可被生成路径重写的语义合同 +
可证明的 repair causality”才有机会。这条线值得继续狠狠干。
