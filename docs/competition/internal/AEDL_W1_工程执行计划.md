> ⚠️ INTERNAL — DEVELOPER FACING：本文件为竞赛内部工程执行计划（2026-09-07，Codex 会话产出），仅面向 AEDL 开发者（Yenefa/Percy）。仓库转 public 或打包正式提交材料前必须移除，见 docs/competition/internal/INTERNAL_CLEANUP.md。

# AEDL W1 工程执行计划：Y2 / Y3 / Y4 前置

审查日期：2026-09-07。性质：代码与接口审查、工程任务拆分；未实现这些任务，未运行 Y4。

## 0. 决策与版本基线

**目前还不能有效运行 Y4。应按“受约束写入与恢复 → 独立重验 → 六例输入与 C/D 执行准备”拆成三个 PR。**

最优先的阻塞不是模型接口，而是 akcli strict-nets 与合法拓扑修复之间的冲突。若通道不能执行正确的端点交换和串阻插入，C/D 都失败时只能说明公共执行器受限，不能比较决策能力。

本轮核对版本：

| 资产 | 读取版本 / 状态 | 判断 |
|---|---|---|
| 主分支 | 01e30d6a33ca959d2197736242ee49de5a11f476 | 当前审查基线；Y4 v1.1、PR #33 已合入 |
| Y1 / PR #37 | a403ac470fb425df1231bce3ea599adda6f156b6；open | SCOPE_FREEZE_W1.md 仍为 DRAFT / PENDING_HUMAN_REVIEW |
| P3 / PR #38 | 最新接口返回 8f4d904f2e023c232461aaf65f21e5df9dc7063b；open；已按 SHA 读取事实正文 | 文档已交付；10 条核验表中 7 条 HUMAN_VERIFIED、3 条待人工核验 |
| P4 / PR #39 | 0e84912dd3cd56f1364c7ffc69fd7a9a68ca9ba0；open | 六例定义、A/B 记分、曝光边界已交付；明确尚未生成故障副本 |
| akcli-kicad | 0.21.0 wheel 及其源码 | wheel SHA256 已重新核对；未在本轮运行写入试验 |

审查期间主分支发生更新，已撤销早期“Y4 v1.1 尚未同步”的临时判断。**不要重复编写 P3/P4 或 Y4 协议。** 准备清单记录所用精确 SHA 即可；PR 未合并本身不阻塞读取与开发准备，实际计分仍需范围和所用事实完成相应复核。

核心来源：[W1 Card](https://github.com/Yenefa/AEDL/blob/01e30d6a33ca959d2197736242ee49de5a11f476/docs/competition/internal/W1_CARD_Yenefa_20260907.md)、[Y1 草案](https://github.com/Yenefa/AEDL/blob/a403ac470fb425df1231bce3ea599adda6f156b6/docs/competition/SCOPE_FREEZE_W1.md)、[P3](https://github.com/Yenefa/AEDL/blob/8f4d904f2e023c232461aaf65f21e5df9dc7063b/notes/device-facts/m2-device-facts-v1.md)、[P4](https://github.com/Yenefa/AEDL/blob/0e84912dd3cd56f1364c7ffc69fd7a9a68ca9ba0/notes/dev-cases/m2-dev-cases-v1.md)。

## 1. Y2：已有资产与最小接入路径

### 1.1 可复用的文件

| 当前文件 | 已有能力 | W1 使用方式 / 限制 |
|---|---|---|
| tools/generate_m2_ops.py:17,168 | 固定 0.21.0/protocol 2；版本检测、from-intent、ops validate、SHA256 证据 | 复用版本常量、调用及验证约定；不要用全量 from-intent 重建来替代局部修复 |
| gates/run_gates.py:256,271 | akcli 查找、live ops 校验、绑定 ops 哈希和数量 | 复用前置检测与校验思路；它验证 op-list，尚不证明实际修改 .sch |
| src/hardware/m2-board/m2_board.kicad_sch | 真实 M2 原理图，含已批准 R7/R8/R9/C5 | 作为冻结输入来源，复制到实验候选目录 |
| src/hardware/m2-board/intent_v1.json、ops_gen.json | 已有设计表达与生成操作 | 作为只读设计资产；不把整份正确终态直接交给修复模型 |
| gates/gate_core.py:sha256_file | 按文件原始字节计算 SHA256 | 直接复用 |
| sandbox_runtime/src/aedl_sandbox/protocol.py:241 | ExecutorPort / VerifierPort / RepairPort 边界 | 沿用职责划分；不改冻结协议，不引入新的控制平面 |
| sandbox_runtime/src/aedl_sandbox/workspace.py:112,125,158 | 候选目录、字节写入、action ledger、内容哈希 | 可参考候选隔离与幂等逻辑；**没有固定文件快照恢复**，不能宣称已有 rollback |
| sandbox_runtime/src/aedl_sandbox/adapters.py:462–580 | TEST_ONLY execute / verify / repair 串联示例 | 仅编排测试；不能作为 M2 真实修复实现 |

尤其要分清：现有 _TestOnlyRepair 只是增加 fixture_attempt；_TestOnlyVerifier 在 attempt >= 2 时 PASS。它们没有修改或验证电子设计。现有图的 checkpoint 恢复也不等于 .kicad_sch 字节恢复。

最小新增入口是 **tools/repair_pipeline.py 的单次事务**：接收已校验补丁，调用 akcli，调用 Y3，失败恢复。Y4 的三轮控制放在实验脚本。不把 W1 接入改造成 EDD-001 bundle、LangGraph、签名或 promotion 扩建。

代码依据：[生成器](https://github.com/Yenefa/AEDL/blob/01e30d6a33ca959d2197736242ee49de5a11f476/tools/generate_m2_ops.py#L168)、[TEST_ONLY adapters](https://github.com/Yenefa/AEDL/blob/01e30d6a33ca959d2197736242ee49de5a11f476/sandbox_runtime/src/aedl_sandbox/adapters.py#L462)、[候选工作区](https://github.com/Yenefa/AEDL/blob/01e30d6a33ca959d2197736242ee49de5a11f476/sandbox_runtime/src/aedl_sandbox/workspace.py#L158)。

### 1.2 必须先处理的 strict-nets 冲突

0.21.0 的实际源码行为：

- pipeline/draw.py:94：strict 检查只在 do_apply && strict_nets 时生效。
- pipeline/draw.py:116：只要 net_risk 为真，写入前拒绝。
- netdiff.py:diff / has_risk：按引脚成员交叠识别拆网/合网，不按网络名称判断；任一拆分/合并触及命名网络即有风险。
- commands/drawing.py:754：这条拒绝路径抛错误，不能假设所有错误响应都有普通 draw-result 的 applied 字段。

因此，“dry-run 退出 0”甚至不足以证明“随后带 strict 的 apply 可执行”。

按这套算法推导：

| 必要修复 | 风险 |
|---|---|
| DC-01：交换 U1.13/U1.14 的网络归属 | 两个旧网的成员分别落入两个新网，构成 split/merge |
| DC-03：把直连 USB 网络重新分成连接器侧和芯片侧，中间串阻 | 对命名网络进行必要拆分 |
| DC-02：将独立 ADDR 接入 GND | 若浮空引脚被读成独立网络，可能被识别为涉及命名 GND 的 merge，需真实文件验证 |
| DC-04/05：恢复缺失阻容 | 不能从“支持 place_component”推定完整连线、符号库、净变化检查都可通过 |

以上是源码级可执行性分析；**本轮没有运行这些案例的 akcli 修复**。

PR-1 首个工作项必须是必要操作的通道资格测试。默认保持 strict-nets；不能静默去掉参数，也不能通过“先删除全部对象、再重建”规避它。

若真实资格测试确认必要修复被拒，建议的最小解决方向是：由 Y1 所有人明确批准“仅容许白名单内的预期拓扑差分”，执行器在隔离候选中检查确切引脚集合、获准变化及所有受保护关系，独立验证通过后才保留候选。普通操作继续 strict。**这是待裁定的约束变更建议，不是当前已获准的实现；原版 0.21.0 的 CLI 没有已核实的此类例外参数。** 如坚持任何命名网拆分/合并一律拒绝，DC-01/DC-03 就保持通道 BLOCKED，不能硬算 C/D 失败或声称六例已就绪。

上游来源：[0.21.0 发布说明与 strict-nets 语义](https://pypi.org/project/akcli-kicad/0.21.0/)；本地审查包 SHA256：63672f4e9ad9a1d6b6ffcee46b0369384c2088485cd42f3c7e3d8412cd2332e6。

### 1.3 Patch schema：AEDL envelope 包住上游 protocol 2

建议新增 src/repair/patch_schema_v1.json。只约束本期单个 M2 原理图；不另造通用 EDA 操作语言。

| 字段 | 类型 / 约束 | 谁负责 |
|---|---|---|
| schema_version | 固定 aedl.repair-patch.v1 | schema |
| patch_id | 本轨迹内唯一字符串 | 宿主生成或校验；绑定补丁内容哈希 |
| decision | PATCH / REFUSE | C/D 提议 |
| base.files | 相对路径 → SHA256；覆盖目标及冻结只读依赖 | 宿主提供并与磁盘重算比较，模型无权重定义 |
| policy_ref | 冻结范围文件 ID + SHA256 | 宿主绑定；不是模型自填权限 |
| target | 单一获准 .kicad_sch 相对路径 | 宿主 resolve 后检查仍在候选目录内 |
| preconditions | 精确对象存在性、UUID/Ref/引脚、旧参数或旧连接 | 执行器逐项核对；多匹配或缺对象拒绝 |
| oplist | protocol_version=2、target_format=kicad、ops 数组 | akcli 原生 schema 校验 + AEDL 子集校验 |
| diagnosis | rule_id、对象、observed、requirement_level、fact_ids、简短理由 | C/D 输出；供 B 评分，不能改变 A 判据 |
| refusal | 缺失事实 ID、理由、需要人工确认的内容 | REFUSE 必需；oplist 不含操作 |

整个对象及各对象字段都拒绝未知键；设定固定数量上限。拒绝绝对路径、..、链接越界、多 sheet 路由和任意命令。宿主不接受模型提供 applied、验证结果、快照路径、accepted 或 manufacturing_release。

本期原生 op 子集建议：

- set_component_parameters：只放行 designator + value；阻止借 parameters / footprint / new_designator 修改其他字段。
- place_component：只允许冻结范围内的 Device:R / Device:C、Ref、批准参数和确定性锚点。
- delete_object：优先精确 UUID，附类型/位置前置条件；不能依赖“匹配零个也算 replay-safe”作为第一次执行成功。
- add_wire、add_net_label：只在批准端点与局部范围内。
- delete_component 仅为获准的局部操作或故障输入生成使用；默认禁止 cascade。
- 不开放 rename_net 全局改名、add_sheet、自动布局、任意文本及原理图完整重建。

几何坐标只服务于连接编辑和缺件放置，不扩大为布局优化。UUID 来自当前读取结果，不能让模型猜。组件参数采用有限、明确的单位归一化，例如把批准的等价值规范成 22R / 10k / 1uF；无法识别就拒绝，不猜单位。

applied 不属于补丁请求。它应出现在独立执行回执：

~~~json
{
  "schema_version": "aedl.repair-execution.v1",
  "patch_id": "<host-bound-id>",
  "status": "APPLIED",
  "tool": {"version": "akcli 0.21.0 (protocol 2)", "exit_code": 0},
  "tool_applied": true,
  "bytes_changed": true,
  "before_sha256": "<computed>",
  "after_sha256": "<computed>",
  "reread_confirmed": true,
  "snapshot_id": "<immutable-host-id>",
  "verification_status": "NOT_RUN",
  "rollback": {"attempted": false, "verified": false}
}
~~~

这只是回执形状示例，不是本轮结果。对合法工具错误，tool_applied 可为 null，原始错误照存；缺字段不能转成成功。

### 1.4 四项保证如何实现

1. **applied 与真实效果**  
   显式 --apply；退出 0、普通 draw JSON 中 applied 严格等于 true、status 正确、无 op error、目标重新读取达到提议结果，缺一不可。真正首次修改还必须 before_hash != after_hash。applied=true 但文件相同只能是经过验证的 NO_CHANGE，不能算新修复成功；字节变了但目标未满足也失败。

2. **文件 hash 与重复提交**  
   比较原始 bytes，不读文本后重新编码。记录 run 初始、每轮写前、写后、验证前后、恢复后哈希，并绑定补丁、事实、策略、检查器版本。相同 patch_id 只有在补丁哈希与当前 after_hash 都吻合时才复用旧回执；文件漂移立即拒绝，不能只信 action ledger。

3. **固定 snapshot rollback**  
   轨迹开始保存不可覆盖的“故障输入”快照；每轮另存写前快照，首次写入前落盘。失败回到本轮起点，开始下条 C/D 轨迹则回到同一个初始故障输入。**不能回到正确 golden 文件，否则等同直接给答案。** 不依赖 akcli 的轮转 .bak / undo；日志与 .akcli 元数据与设计哈希分开。

4. **byte-level recovery**  
   原始快照 bytes → 同目录临时文件 → flush / 文件同步 → 原子替换 → 重读逐字节比较并复算 SHA256。恢复后要求文件集合和受保护依赖均与对应快照一致；意外新增文件也要识别。回执只有复核成功才能标 rollback.verified=true。执行进程崩溃后留下未完成事务标记，下次进入先恢复/核验，不能继续计分；恢复失败必须停止并保留候选和快照。W1 可保证经过核验的进程异常恢复，不宣称经过断电/磁盘损坏验证。

严格限定单写者候选目录，拒绝 KiCad GUI 锁与外部并发修改；否则写前 hash 与实际写入之间仍有竞争窗口。

### 1.5 PR-1 文件与推荐 commit 顺序

| 顺序 | 文件（新增，除非另注） | 小任务与验收 |
|---|---|---|
| 1 | tests/test_akcli_adapter.py | 分开写改值、精确删对象、局部接线、端点交换、串阻插入的资格用例；区分 mock 单测与显式 opt-in 原生资格测试 |
| 2 | src/repair/patch_schema_v1.json | 固定 envelope、字段来源、路径/操作子集、PATCH/REFUSE 分支；非法字段、漂移和越界都拒绝 |
| 3 | tools/akcli_adapter.py | 复用生成器的版本约定，配置可执行路径；validate → dry-run → apply → read；记录完整 stdout/stderr 与双形态错误 |
| 4 | tools/repair_pipeline.py | 只做单轮事务：base 核验、固定快照、执行、Y3 回调、恢复、回执；不在这里建多 Agent 或新控制平面 |
| 5 | tests/test_repair_pipeline.py | 分别覆盖假 applied、未改字节、错误重读、重复提交、漂移、写后异常、恢复失败、相同初始快照复用 |

建议 commit：test(repair): pin native operation qualification → feat(repair): constrain patch envelope and akcli execution → fix(repair): bind immutable snapshots and verified recovery。每个 commit 保持可评审，资格试验失败作为阻塞记录，不伪造绿色。

未来验收命令：python -m unittest tests.test_akcli_adapter tests.test_repair_pipeline。原生资格检查采用显式 opt-in，并把可执行路径、0.21.0 版本和实际返回记录作为附件；不能用 mock 通过替代。

## 2. Y3：当前 gate 已支持哪些环节

### 2.1 不需要重新开发的部分

gates/run_gates.py:703 已执行新网表导出、ERC，并在 netlist_fresh 为真时调用 schematic_semantics.evaluate_paths；gate_core 已解析 ERC JSON。evaluate_paths 从 KiCad XML、intent、PCB 和固件收集观察，而非使用 akcli read 的推断结果。已有独立解析路径。

### 2.2 必补的四个连接点

| 缺口 | 当前事实 | 最小修改 |
|---|---|---|
| 候选输入与局部 verdict | run() 固定 M2 路径且顺带运行 DRC、CPL、交付、U3 等全板门禁 | 新增显式 m2-repair scope；根目录为隔离候选，默认 m2 全板行为保留 |
| ERC 报告新鲜度 | 网表用本轮临时文件与 netlist_fresh；ERC 直接写固定旧路径，结果未用同等完成标记约束 | 每次新目录/临时输出，核对进程完成、合法 JSON、source 与工具版本，再发布报告；旧文件不能作为后备 |
| source → evidence 绑定 | manifest 的顶层 artifacts 没有直接列出 .kicad_sch；语义 inputs 绑定 XML 等但不是导出动作的源字节关系 | 增加目标 .sch 的验证前后哈希、原生调用、输出哈希、patch/snapshot/policy/facts 绑定 |
| 全部受保护关系 | 当前五条规则只核列出的 pins/components，未覆盖所有 29 个网；EN/GPIO9 规则未直接核全部 R3/U1 端点 | 新增 KiCad 观察的完整关系差分，对非允许变化的引脚/参数逐项比较；必要原厂端点断言由 Percy 核定 |

[现有 runner](https://github.com/Yenefa/AEDL/blob/01e30d6a33ca959d2197736242ee49de5a11f476/gates/run_gates.py#L703)、[当前语义收集与评估](https://github.com/Yenefa/AEDL/blob/01e30d6a33ca959d2197736242ee49de5a11f476/gates/schematic_semantics.py#L240)、[固定合同](https://github.com/Yenefa/AEDL/blob/01e30d6a33ca959d2197736242ee49de5a11f476/gates/contracts/m2_schematic_contract_v1.json)。

### 2.3 最小实现形态与文件

- 新增 gates/repair_verification.py：候选文件参数适配、原生 KiCad 调用、局部检查、受保护关系差分、六态结果映射。共用已有 ERC parser 和语义规则，不复制另一套判据引擎。
- 修改 gates/run_gates.py：增加显式 m2-repair 入口并由它产出验证 manifest；把本轮报告新鲜度保护用于相关原生调用。禁止 repair scope 的 --skip-kicad。
- 修改 gates/schematic_semantics.py：添加可复用的结构化差异收集接口，返回 view / object / field / expected / observed。保留现有五条规则、现有 details 和全板入口；W1 wrapper 记录完整受保护图的比较结果。
- 新增 tests/test_repair_verification.py；扩充 tests/test_run_gates.py 与 tests/test_schematic_semantics.py。不重构 datasheet_contract、board_review 或制造流程。
- tools/repair_pipeline.py 增加真实 Y3 调用；Y2 的“已写入”状态不能冒充“已验证”。

原生命令沿用官方 CLI：

~~~text
kicad-cli sch export netlist --format kicadxml --output <本轮输出>/candidate.net.xml <candidate.kicad_sch>
kicad-cli sch erc --format json --severity-all --exit-code-violations --output <本轮输出>/erc.json <candidate.kicad_sch>
~~~

--exit-code-violations 下，ERC 返回 5 代表检出了违规，不自动等于工具损坏；结合结构化报告区分设计发现与 TOOL_ERROR。已有 ERC gate 以 error 数判定，warning 必须另存并按冻结策略检查有无新增，不能把环境缺库警告静默忽略。[KiCad 官方 CLI](https://docs.kicad.org/10.0/en/cli/cli.html#_schematic_erc)。

### 2.4 Verdict 与 evidence 的最小规则

- pipeline 顺序固定：patch → 新导出 → ERC → semantic/protected-diff → 验证 manifest → 接受候选或恢复。
- 同一次验证开始/结束的源文件哈希必须相同，并且等于 Y2 写后的哈希；中途被修改则本轮证据无效。
- local_repair_status 与 background_blockers 分开。U3 的既有 BLOCKED 不因 USB 修好而消失；也不直接把每个 USB 局部结果都压成 FAIL。
- 保留只读 intent、PCB、固件。W1 不修改 PCB；可以继续把它们作为冻结对照读取，但本次不运行的几何检查标 NOT_RUN，不声称已通过整板验收。
- 对评估器输入错误或工具缺失保留 TOOL_ERROR / UNKNOWN；零适用检查不能 PASS。不要把现有低层 pass/fail 强行重构成全仓六态，在 W1 回执边界进行映射即可。
- 历史 semantic JSON 只能作为历史样例；本轮结果必须由本轮 KiCad 新导出计算。
- 独立性有两层：KiCad 与 akcli 解析独立；Percy 的验收依据与实现侧独立。两者都要保留。

推荐 commit 顺序：fix(gates): bind fresh native reports to candidate bytes → feat(gates): add scoped repair verdict and protected diffs → test(gates): cover stale evidence and semantic regressions。

未来验收：python -m unittest tests.test_repair_verification tests.test_run_gates tests.test_schematic_semantics。拆开的负例至少包含旧 ERC 遗留、导出失败、源 hash 漂移、ERC=0 但 USB 接反、目标修好却损坏受保护网、零覆盖、warning 增加、U3 背景阻断保留。完成前还须原生 KiCad 资格记录，mock 单测不算完成 Y3。

## 3. Y4：六例能否表达、D/C 缺口

### 3.1 六例覆盖矩阵

| 案例 | 当前能够表达什么 | 距离真实运行还缺什么 |
|---|---|---|
| DC-01 USB 接反 | P4 定义；USB_POLARITY_AND_SERIES；fault_reversed_usb.json | 只在 .sch 副本交换 U1 端点的真实输入；strict 资格；恢复端点且保护 J1/R7/R8/其余网络 |
| DC-02 ADDR 悬空 + 固件 0x44 | SHT30_ADDRESS；fault_floating_addr.json；固件 DEFAULT_ADDR=0x44 | 真实断线 .sch；固件冻结；同一反馈中明确硬件及跨视图两条结论 |
| DC-03 缺 R7/R8、两路直连 | 合同中存在 22R 与两侧网络要求；P4 已定义故障 | 缺专门的现有 JSON 故障夹具，也没有真实直连 .sch；串阻插入及拆网能力；无旁路的独立检查 |
| DC-04 缺 R9 | ESP32_GPIO9_PULLUP；fault_missing_gpio9_pullup.json | 真实删 R9 输入；place + net 接入；B 区分建议加固与内部默认 |
| DC-05 缺 C5 | ESP32_EN_RC；fault_missing_en_cap.json | 真实删 C5 输入；确认 R3/SW1/U1.2 保持；B 不得说 EN 悬空 |
| DC-06 U3 资料不足 | 真实 datasheet_manifest：BLOCKED_POWER_THERMAL，theta_ja=null；P4 拒绝要求 | 无需注入；补 REFUSE 接口、具体缺失项、无写入证明和单独 B/拒绝评分 |

关键区别：仓库现有 **5 个 observation JSON 故障夹具，不是 Y4 的 5 个修复原理图**。其中 fault_firmware_address.json 把固件改为 0x45，Y4 DC-02 则要求固件固定 0x44。现有部分夹具同时改 intent/netlist/PCB，用于检查共同模式失效；不能原样用于“只允许改 .sch”的实验。

gates/semantic_fault_injection.py:51 只是 deepcopy 观察对象并 set/delete；没有生成 KiCad 原理图。因此“检测测试已有”与“执行案例就绪”必须分别列状态。[故障注入实现](https://github.com/Yenefa/AEDL/blob/01e30d6a33ca959d2197736242ee49de5a11f476/gates/semantic_fault_injection.py#L51)。

### 3.2 D baseline 的判断

**知识资产足够建立强 D，但当前没有可计分的 D 修复实现。**

已有规则检查器输出 expected/observed；tools/generate_m2_ops.py 是完整生成工具；_TestOnlyRepair 是假件。三者都不等同于 D。

tools/repair_baseline.py 至少实现：

1. 从实际端点关系恢复 USB 身份；
2. 根据只读固件与已核实逻辑电平事实恢复 ADDR；
3. 识别缺失串阻并形成两条真实串联路径；
4. 恢复 GPIO9 上拉；
5. 恢复 EN 电容且保留既有连接；
6. 对缺事实 / U3 范围外操作输出拒绝。

采用条件规则、图关系和参数模板，和 C 共用同一操作集、adapter、原生验证及预算。禁止 case_id → 标准补丁、按文件名取答案、复制 golden 文件、只打印错误。B 记分下 D 也应输出同字段的事实说明模板；不能把它故意降级成一行 ERROR 来制造 AI 解释优势。

baseline 合格不要求预先证明五例都修好；要求六类规则和必需操作确已实现、校准/单测通过且失败原因可审查。运行结果仍留给后续实验。

### 3.3 C AI interface 的实际缺口

gates/requirements_runtime.py 的 propose hook 处理“需求提问/合同草案”，不是修复补丁。gates/requirements_llm_replay.py 可复用录制/回放方式，但 replay 不是真实 AI 对照组，其宽松降级解析也不适合可执行补丁。

新增 tools/repair_ai.py，只做一条具体模型接入，输出与 D 一样的补丁 envelope：

- 输入：当前候选观察、冻结公共事实、结构化公共反馈、允许动作、剩余预算和本轨迹历史。
- 输出：PATCH 或 REFUSE，连同 B 所需事实引用、要求等级和简短理由；不要求模型内部思维链。
- 边界：严格解析，不从坏 JSON 猜补丁；格式修正与 API 重试计入同一预算；不静默回退成 D。
- 配置：确切模型 ID、服务端点、凭据存在性、提示词 SHA、解码配置、token 限额与超时。
- 留痕：原始响应、规范化补丁、请求 ID、真实 token、调用耗时、费用及不可知项。凭据不进入日志。
- 运行侧不接收整个仓库；只接收冻结公共输入包。私有断言、正确终态与标准补丁不进入 C/D 的提议接口。

### 3.4 Blocker list

以下“关闭条件”是后续工程验收要求，不代表本轮已执行。

| ID | 优先级 | 缺口 | 关闭条件 | 负责 PR / 人 |
|---|---|---|---|---|
| B01 | P0 | strict-nets 与合法端点交换/拆网冲突 | 完成原生必要操作资格测试；受限时先明确允许拓扑差分的约束，不静默绕过 | PR-1；Yenefa，边界由双方核定 |
| B02 | P0 | 缺真实 akcli patch adapter 与幂等回执 | applied、字节变化、重读共同成立；错误/漂移不成功 | PR-1 |
| B03 | P0 | 缺固定快照、错误恢复和重试隔离 | 写后异常及重新启动路径恢复到指定原始 bytes；C/D 每条轨迹同一故障起点 | PR-1 |
| B04 | P0 | 缺候选绑定的独立 KiCad 重验 | 新 XML/ERC + source hash + 无旧报告回退 + 局部 verdict | PR-2 |
| B05 | P0 | 缺完整受保护关系回归检查 | 全部非允许变化的 pins/参数可比；零覆盖和新回归不能 PASS | PR-2；Percy 核验判据 |
| B06 | P0 | 六例未物化 | 5 个真实故障 .sch + DC-06 原状输入；每例带输入 hash、只读依赖、允许变化；故障形态由独立导出核对 | PR-3，依赖 PR-1/2 |
| B07 | P0 | D 尚无六类真实决策逻辑 | 同一通道可发补丁/拒绝，条件规则与说明模板通过独立资格审查 | PR-3 |
| B08 | P0 | C 缺 repair prompt、输出合同及真实传输配置 | 严格 schema、PATCH/REFUSE、计费/时限、录制与 replay 测试均就绪；计分必须 live，不能冒充 replay | PR-3 |
| B09 | P0 | P3 所用事实未全部核验；范围仍 DRAFT | F-U1-03/F-U1-04 完成人工核验；若引用 45kΩ 则 F-U1-05b 同样需核验；实际采用的范围/输入规则完成复核 | 复用 #37/#38；Percy/Yenefa |
| B10 | P0 | 缺统一调度、冻结输入包、状态表与机器预检 | 6×2×3 的运行清单、最多3轮/轨迹、180s/轨迹、所有失败留痕、私有答案隔离；prepare 不调用模型 | PR-3 |
| B11 | P0 | 可运行环境未闭合 | 明确 akcli 0.21.0、其 Python≥3.11、KiCad 10.0.5、库表/符号路径；两组完全一致；原生资格检查留档 | PR-1/2/3 |
| B12 | P0 | 结果记录没有落为可执行评分输入/表格 | A:n/5、B:n/6、DC-06拒绝/无写入、回归、错误提议、成本、曝光和原始证据均能关联；缺项保持 NOT_RUN | PR-3；Percy 评分 |

B09 的界限：P3/P4 文档已存在，不能要求重做；也不能把文档中的 AI_EXTRACTED_UNVERIFIED 自动当 HUMAN_VERIFIED。J1 的 TO_VERIFY 不应自动阻塞所有局部修复：本批沿用获准的连接器侧关系，不新造 J1 厂家映射事实。U3 的资料缺失是拒绝案例的输入，不是要求本周补齐热设计。

本机使用仓库的 _find_kicad_cli / _find_akcli 均返回 None；这只表示当前进程的项目检测未找到工具，不否认 Percy 的独立安装，也不意味着旧隔离 wheel 不存在。本轮未安装或运行原生 EDA 工具。

不是 W1 blocker：P5 的 PCB builder 修复（本路径不运行 builder）、U3 ECO、自动布线、整板制造放行、多 Agent、签名体系、模型微调、E1 的24例。不得为这次准备扩大功能。

## 4. PR-3：实验前必须补的文件

| 文件 / 文件组（均为拟新增） | 内容 | 验收方式 |
|---|---|---|
| tools/prepare_w1_cases.py | 由冻结基线生成候选故障文件；不改正式 M2；生成输入 hash | tests.test_w1_y4_preflight：固定输入可重复生成；只影响声明的故障部位 |
| notes/w1-y4/cases_manifest_v1.json | 六例 ID、故障文件、SHA、固定只读依赖、公共事实包、允许变化、背景阻断、精确来源版本 | 预检发现缺例/错 hash/错固件即拒绝 |
| notes/w1-y4/public/DC-01…DC-06/ | 5 个真实故障原理图与第6例原状输入；所需项目上下文 | 用 PR-2 独立解析确认错误形态和未改变的关系；不得仅凭注入器成功判断 |
| notes/w1-y4/public/facts_v1.json | 从 P3 审核条目整理公共事实；每条带状态、source/page/条件/等级 | Percy 对照现有 P3；无逐例标准补丁或完整正确终态 |
| notes/w1-y4/private/acceptance_v1.json | P4 判据的最小机读化及 B 评分字段 | Percy 维护；只供评分进程读取，不传给提议器；不从实现代码反推答案 |
| tools/repair_baseline.py | D 六类条件规则与说明模板 | tests.test_repair_baseline；禁止按 case_id/文件名取答案 |
| tools/repair_ai.py、notes/w1-y4/prompt_v1.md | C 单一真实 provider、严格补丁边界与冻结 prompt | tests.test_repair_ai：录制成功/拒绝/坏JSON/超时；明确 replay 不计 AI 实验 |
| tools/run_w1_y4.py | 小型实验入口，共用单轮 repair_pipeline；prepare/preflight 模式、后续显式运行入口 | tests.test_w1_y4_preflight：prepare 零模型调用；预算与状态不可漏计 |
| notes/w1-y4/run_config_v1.json | 模型/工具/代码/事实/协议版本、36条轨迹、轮数/时间/token、顺序、曝光记录 | 配置哈希固定，非法额外重试不能通过 |
| notes/w1-y4/results_template.csv | A/B 各自结果、拒绝、回归、成本和证据路径，初值 NOT_RUN | 预检确认行数、维度和分母；DC-06 A=NOT_APPLICABLE |
| tests/test_repair_baseline.py、test_repair_ai.py、test_w1_y4_preflight.py | 单测与准备资格检查 | python -m unittest tests.test_repair_baseline tests.test_repair_ai tests.test_w1_y4_preflight |
| .gitattributes（仅新增夹具规则） | 固定新故障 .sch 的字节处理；不全仓换行归一化 | Windows/Linux 相同夹具 hash；运行内恢复仍以原始 bytes 为准 |

这些是“新增一个受控 W1 实验入口”所需组件，不建设通用 benchmark 平台。故障生成和私有验收由不同职责核对；不能因为生成/修复用了同一套模板就自动判定正确。

B 分数允许 Percy 手工填写固定表格；W1 不需要另建 LLM judge。该表是必需的记录接口，自动评分产品不是前置条件。

建议 commit 顺序：
1. test(y4): materialize and pin six real case inputs；
2. feat(y4): add qualified rule baseline and strict AI proposal adapter；
3. feat(y4): add preparation preflight and frozen run manifest；
4. docs(y4): bind qualification evidence and pending results。

未来准备命令可设计为 python -m tools.run_w1_y4 --config notes/w1-y4/run_config_v1.json --prepare-only。**此入口尚未实现；本轮没有运行。** prepare-only 仅校验已准备文件和列出计划，不发起模型、应用修复或产生分数。原生通道资格验证另行显式执行，不能隐藏在 prepare-only 中。

## 5. 最终 W1 PR 计划

~~~makefile
PR-1:
    Y2：akcli 0.21.0 受约束补丁与字节恢复
    先验证必要拓扑操作和 strict-nets 边界
    新增 patch schema、akcli adapter、单轮事务及恢复测试
    出口：真实写入 + 重读 + 哈希 + 固定快照恢复
    拓扑资格未通过时，不声明六例执行通道就绪

PR-2:
    Y3：候选原理图的独立 KiCad 验证
    复用原生导出/ERC/semantic checker
    补本轮报告新鲜度、源哈希绑定、受保护关系差分
    出口：局部 verdict 可复核，旧证据/缺工具/零覆盖不能 PASS

PR-3:
    Y4 前置：六例真实输入 + 强 D + C 接口 + 统一准备入口
    复用 P3/P4 和已合入的 Y4 v1.1
    固定模型/事实/工具/预算/曝光记录，生成 A/B 结果空表
    出口：preflight 能明确 READY 或逐项 BLOCKED；结果保持 NOT_RUN
~~~

依赖：PR-1 → PR-2 → PR-3 的通道资格与最终预检。P3 所用条目的人工核验和 Y1 范围裁定可同步推进。Y4 卡片的 4 小时是执行/分析时间，不能把上述缺失工程实现算作免费前置。

执行时每个 PR 的 Task Envelope 必须一次列全代码、测试、schema 与必要记录路径，避免用 Y4 仅 notes/ 的旧领地假定授权修改 tools/。沿用现有 Admission、Development Gate、Review Bundle 与 AI/第三方记录流程；不新增流程系统。本报告只是列出拟修改文件，没有修改这些仓库文件、创建 PR、提交或推送。

## 6. 本轮实际验证与限制

已执行：

~~~text
python -m unittest tests.test_generate_m2_ops tests.test_schematic_semantics tests.test_gate_core tests.test_run_gates
Ran 51 tests in 1.857s
OK
~~~

运行环境 Python 3.11.15。测试最初运行于 5d334095ee3534ae61adf89e9e788c10d88e5d3c；随后同步到本报告基线 01e30d6，并检查 gates/、tools/、sandbox_runtime/src/ 及上述四份测试没有差异，因此上述验证所覆盖代码一致。最终审查副本 git status 干净。

这51项只证明已有测试通过，**不证明本报告指出的缺口已经修复**。本轮没有新增生产代码、运行 C/D、生成六例故障文件、执行 akcli repair、调用原生 KiCad 重验、运行整套 Development Gate 或签发正式 Evidence。

未来验收仍须区分：单元测试通过、原生公共通道资格通过、实验准备通过、实际 Y4 成绩。不能跨级填 PASS。

