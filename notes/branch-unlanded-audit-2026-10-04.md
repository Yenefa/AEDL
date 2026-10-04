# Remote branch unlanded-work audit (2026-10-04, AEDL-AUTO)

> 结论先行：**91 条远端分支中，0 条可证明为「已全部落地」**。此前把它们当作
> 「陈旧分支」并计划清理，是**错误判断**。本文件记录实测结果与正确的处置口径。

## 为什么不能按「陈旧」清理

`git rev-list --count origin/<branch>..origin/master == 0`（即 ahead==0）是对
「分支提交已全部进入 master」的**唯一可靠证明**。本仓库 91 条非 master 远端分支中，
只有 `origin/master` 自身满足 ahead==0，**其余 91 条全部 ahead>0**。

ahead>0 **不等于**「有未落地工作」——squash / rebase 合入会改写提交身份，内容可能
已在 master 而提交不可达。但 ahead>0 也**不能被反过来用作「可删除」的证据**。
因此在缺少逐条内容核对的情况下，删除任一条分支都属于猜测，而 ADR-022 决策 5 第 5 条
明令禁止销毁未落地内容。

## 实测抽样：确有未落地内容（不是理论风险）

以 blob 身份比对（`git rev-parse <ref>:<path>` 双端取 blob SHA 后逐个比对）：

| 分支 | 与 master 差异文件 | **blob 仍不同（真未落地）** |
| --- | --- | --- |
| `feat/c5-commit-writer` | 6 | 4（含 `tools/repair_pipeline.py`、`tests/test_repair_pipeline.py`） |
| `fix/schgen-dev-native-chain` | 10 | **10（全部）** |
| `notes/e5-exploratory-board` | 14 | **14（全部）** |
| `docs/w1-competition-briefing` | 10 | 8 |
| `feat/w4a-evidence-freeze` | 13 | 9 |

未落地内容包含：`docs/evidence/EVIDENCE_INDEX.md`、`docs/compliance/THIRD_PARTY_RESOURCES.md`、
`docs/compliance/AI_USAGE_{LOG,SUMMARY}.md`、`docs/competition/internal/*`（含研究素材与
框架判定 xlsx）、`notes/e5-user-trial/*`、`.gitattributes`。**Evidence 索引、第三方资源
台账、赛事判断书都在其中**——按「陈旧分支」删掉会直接销毁证据链与合规记录。

## 本轮处置

- **未删除任何分支。** 依据：ADR-022 决策 5 第 5 条（禁止销毁未落地内容）+ 上表实测。
- 前次 subagent 报告中的「80 条陈旧分支、无 OPEN PR、tip 早于 2026-10-01」**不足以
  支撑删除**：PR 已合并的分支同样 ahead>0，且其内容可能经 squash 落地，也可能根本没落地。
- 该报告自身已提示「branch-tip age is not evidence that the content is unlanded」——
  本文件即为把该提示落到实测的结论。

## 正确的后续口径（待排期，本轮不做）

1. 逐条判定需要 blob 级内容比对（本文件表格已给出可复用脚本口径）。
2. 未落地且**无价值**（已被后续提交取代、纯过程稿）的分支：先在仓库内留下
   「分支 → 内容 → 处置」清单，再删，且清单本身入库。
3. 未落地且**有价值**的：按内容另开 PR / 归档到 `notes/`，不得留在悬空分支上。
4. 6 条 OPEN PR（#58 #65 #67 #70 为正式、#93 #94 为 draft）是这批工作里**唯一有
   评审载体**的部分，应优先于任何清理动作处理。

## 复现方式

```text
git rev-list --count origin/<branch>..origin/master      # ahead
git rev-list --count origin/master..origin/<branch>      # behind
git diff --name-only origin/master...origin/<branch>     # 差异文件
git rev-parse origin/master:<path> ; git rev-parse origin/<branch>:<path>   # blob 身份
```

`NOT_RUN`：本轮只抽样 5 条分支，未对全部 91 条做 blob 级比对；因此「其余 86 条各自
是否含未落地内容」为 `UNKNOWN`，不得据此推断可删。