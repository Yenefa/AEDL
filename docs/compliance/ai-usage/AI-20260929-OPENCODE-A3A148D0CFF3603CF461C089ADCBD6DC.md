## AI-20260929-OPENCODE-A3A148D0CFF3603CF461C089ADCBD6DC

- 日期：2026-09-29
- 任务名称：the Linux-only path-flavour failure on master left by PR #104
- 记录者：OPENCODE
- 人工审核：`PENDING_HUMAN_REVIEW`

- 会话：opencode（Space Bunny Free），本机 `C:\dev\AEDL`，分支 `fix/linux-path-flavour`
- 参与：DEBUG、GENERATE_CODE、GENERATE_TEST、RESEARCH、DOCUMENT
- AI 工具/平台：opencode / `space-bunny-free`（provider `opencode`）
- 模型：`space-bunny-free`
- 授权来源：Owner 2026-09-28 ——「停止所有人工review纪律，全量推进」
- 关联：`tasks/PR1-LINUX-PATH-FLAVOUR.yaml`；前序 `AI-20260928-OPENCODE-92503CBF192B51EC0ECAEBF2B1859A4F`（F1/F6，PR #105）
- 提交：`2520ee3`（envelope）、其余为修复与测试提交

### 起点：不是「CI 又红了」，是 master 已经在红

我原本以为 #105 的 CI 红是基础设施问题（前面几次确实卡在 `Set up job`）。查下来发现
**#103 和 #104 不是** —— 它们跑完了 9 个 step，红在真正的那一步：

```
Development gate (compileall + main tests + sandbox tests + secret scan)  failure
```

#104 的日志里带着完整回执，于是原因是可以读的：

```
FAIL: test_the_helper_agrees_on_both_path_flavours
  (test_repair_pipeline.PathComparisonHygieneTests)
  tests/test_repair_pipeline.py:3692
  AssertionError: False is not true : rejected 'C:\\x\\cand\\design'
Ran 1167 tests in 57.661s
FAILED (failures=1, skipped=19)
platform linux, uv CPython 3.11.16
```

helper 当时是：

```python
parts = Path(path).parts
return len(parts) >= 2 and parts[-2:] == ("cand", "design")
```

`Path` 在 Windows 上是 `WindowsPath`、在 linux 上是 `PosixPath`，所以**同一个字符串**
在一个平台是四段路径、在另一个是一个文件名。

**本地复现**（把 helper 强制到 runner 上 `Path` 真正解析成的 POSIX flavour，这是忠实
模拟而不是猜测）：四个 positive 在 Windows 全 True；强制 POSIX 后 3 个仍 True，
只有 str-windows 那个翻成 `False, parts=('C:\\x\\cand\\design',)`；三个 negative 在两种
flavour 下都是 False。**恰好是 CI 报的那一个，没有别的。**

### 是 helper 错，不是测试错

测试名叫 `test_the_helper_agrees_on_both_path_flavours`，docstring 明说 helper
「is pinned for BOTH renderings explicitly」—— 它编码的正是 #104 自己的意图；而 helper
的 docstring 恰好解释了它随后自己复现的那个失效模式。**放宽这个测试，等于删掉 #104
存在的意义。**

修法：按**值**暗示的 flavour 解析，而不是按**平台**的 flavour；并且对**所有**输入
（含 PurePath）先归一到字符串形式 —— 信任 PurePath 自己的 flavour 是错的，
`PurePosixPath("C:\\x\\cand\\design")` 是个自相矛盾的值，honour 它的 flavour 正是两个
平台分歧的原因。

### 变异检验：M1 存活，而那不是缺口，是**发现**

第一轮 M1 存活。M1 就是**修改前的代码原样**。它在 Windows 上存活，是因为 Windows 上
`Path` **就是** `WindowsPath`，所以原缺陷在它被写出来的那个平台上**碰巧是对的**。

> Windows 上的绿色套件对这个缺陷**零信息量** —— 这正是它能上线的原因。

而我自己在 envelope 里写的验收条件「M1 必须被套件杀掉」**在这个平台上根本做不到**，
我写的时候没验证。这和本分支前面那次「变异锚点没匹配上却当成结论」是同一类错误。

修法不是放宽任何断言，而是加两个测试：

- 把 ambient `Path` **重绑到 POSIX class** 再重跑那四种渲染 —— 咨询平台 `Path` 的
  helper 会失败，不咨询的会通过；
- 把 ambient `Path` **重绑到一个会抛异常的东西** —— 只是碰它一下就算失败。

于是这个跨平台性质**在 Windows 机器上可验证**了。CI 在 linux 上仍是权威确认，
且在 runner 能 provision 之前是 `NOT_RUN`。

最终：**5/5 变异全杀**（M1 恢复 `Path(path).parts`；M2 去掉反斜杠信号；M3 去掉盘符
信号；M4 只比最后一段；M5 去掉长度守卫）。

### 我自己的两个测试先错后对，错误本身有信息量

- 有一个断言「相对路径 `cand/design` 必须被拒」。**错**：这个 helper 一直都是
  **尾部检查**而不是绝对性检查，所有注入故障的调用方递给它的是根路径。要拒绝它就是
  **改契约**而不是修平台 bug —— 于是改名成
  `test_the_helper_is_a_tail_check_not_an_absoluteness_check`，把行为变成决策。
- 第一个盘符测试用的字符串**同时带反斜杠**，所以它分不清 flavour 检测的两个信号，
  于是 M3 存活。要分开必须用**完全没有分隔符**的盘符相对路径 `C:cand/design`，
  那恰好是两种 flavour 对尾部判断不一致的唯一输入。

### 记录下来的限制

POSIX 字符串里如果文件名本身含字面反斜杠，会被判成 Windows flavour —— 因为在不知道
产生者意图的前提下，这是唯一可用的信号；**反方向猜错会静默接受一个非设计路径**，
而那正是这个 helper 存在的意义所在。这条限制由
`test_the_documented_limitation_is_pinned_not_implicit` 钉住，不是隐含。

### 实际运行结果

| 项目 | 结果 |
|---|---|
| `PathComparisonHygieneTests` + `PathFlavourIndependenceTests` | `Ran 12 ... OK` |
| 变异 | **5/5 killed**（含 M1 = 修改前代码原样） |
| 全量 `discover -s tests` | 见 PR；CI **NOT_RUN**（runner provision 未完成） |
| `gates/**` 改动 | 空 |
| 生产代码改动 | 无（helper 在测试文件内，只被测试使用） |

### 明确未实现 / 限制

- **CI 权威确认 `NOT_RUN`**：本机没有 linux runner，验证是在 Windows 上强制 POSIX
  flavour 完成的。这对**本 helper** 是忠实的（它就是 `Path` 在 linux 上解析成的东西），
  但权威结论仍是一次绿色 CI。
- **CI runner 的问题不在本轮范围**：#105 卡在 `Set up job`，那是 provision 问题，与
  本缺陷无关，没有混为一谈。
- #103 / #104 的红色 run 本身是历史；本轮修的是让 #104 变红的那个缺陷，也是唯一仍然
  可达的那个。
