## AI-20260929-OPENCODE-4DF0E253EF9FDABD36AF6D7ECF0E97FC

- 日期：2026-09-29
- 任务名称：GH-109: fix the two Linux CI platform defects (directory st_nlink read as alias count; Windows-only cmd probe) and the ENOTDIR link removal they masked
- 记录者：OPENCODE
- 人工审核：`PENDING_HUMAN_REVIEW`

### 工作单元

Issue #109 / 分支 `fix/linux-nlink-and-cmd-probe` / 基线 `c6d52d9`（PR #108 合并提交）。
起点是 PR #108 完成报告的结论：两处 master 自有代码的平台 bug 属 FOREIGN，
「建议另立任务修复」。本条记录该任务的全部产出。

### 参与标签

`DEBUG`（定位并修复三处平台缺陷）、`GENERATE_TEST`（两个变异体杀手测试 +
一个可移植性修复）、`RESEARCH`（POSIX `st_nlink` 语义与契约/ADR 对齐）、
`DOCUMENT`（ADR-017 修正、Issue、Envelope、Review Bundle）。

### 直接修改

- `sandbox_runtime/src/aedl_sandbox/workspace.py` — `_ensure_within` 的
  `st_nlink` 检查改为**只对非目录生效**，docstring 写明 POSIX 规则。
- `sandbox_runtime/tests/orchestrator/test_workspace.py` — 两个测试 +
  `_posix_directory_link_counts()` / `_nlink_two_for()` 辅助；`_junction` 产物
  按类型选择 `os.unlink` / `os.rmdir`。
- `tests/test_control_plane_tools.py` — 非解释器探针按平台选取（`cmd` / `sh`）。
- `tasks/GH-109.yaml`、`docs/compliance/DECISIONS.md`（ADR-017 修正）、
  本文件与生成索引。

### 根因（实测，非推断）

1. **56/57 的 Linux 失败同源**。POSIX 下目录的 `st_nlink` 是
   `2 + 子目录数`，不是别名计数；一个从未含过子目录的新目录也报 2。
   `_ensure_within` 把它当别名计数，于是**拒绝 Linux 上的每一个目录**，
   包括 `create_candidate` 刚建好的候选根。Windows 的 NTFS 不报告目录链接
   数（恒为 1），所以同一份代码在本平台通过——缺陷在它被书写的平台上不可见。
   修复方向不是放宽守卫：ADR-017 §4 与合同 :378 原文都写的是**「文件」**
   link count，代码比它所引用的决策更宽，因此这是**实现向决策回归**。

2. **`cmd` 是 Windows-only 探针**。Linux 上 `cmd` 不在 PATH，
   `probe_interpreter` 正确返回「no interpreter at 'cmd'」，断言失败。
   工具行为正确，错的是测试的平台假设——所以**没有改 `tools/dev_gate.py`**。

3. **`os.rmdir` 移除 symlink**（Scope Amendment A1）。这一条**是被缺陷 1 掩盖
   的**，不是独立发现：该测试断言的拒绝发生在 `setUp` 里，所以 Linux 上永远
   走不到第 394 行。修好缺陷 1 让 54 个 `setUp` error 真正开始执行，才暴露出
   它。本任务的验收条件之一正是「54 个 error 变成**被执行且通过**的断言」，
   该行不修则此条件无法满足。

### 实际运行的验证

修复前（基线 `c6d52d9`，WSL2 Ubuntu-24.04）：

- `uv run --project sandbox_runtime python -m unittest discover -s sandbox_runtime/tests -p 'test_*.py'`
  → `Ran 438 tests, FAILED (failures=2, errors=54, skipped=1, expected failures=1)`
- `python3 -S -m unittest discover -s tests`
  → `Ran 1223 tests, FAILED (failures=1, skipped=29)`

修复后（同环境）：

- sandbox → `Ran 440 tests, OK (skipped=1, expected failures=1)`
- main → `Ran 1223 tests, OK (skipped=29)`
- Windows `uv run --frozen --project sandbox_runtime …` → `Ran 440 tests, OK (skipped=1, expected failures=1)`
- Windows `python -S -m unittest discover -s tests -p "test_control_plane_tools.py"`
  → `Ran 65 tests, OK (skipped=1)`

skipped 与 xfail 计数**修复前后完全一致**（1 / 1），没有新 skip——
「不是靠跳过变绿」。

**变异验证（Windows 上执行，这是本任务的关键判据）**：
缺陷在 Windows 上不可见，所以「Windows 绿」本身不能证明修复有效。两个变异
都被杀死，且**都是在 Windows 上**：

- 删除 `S_ISDIR` 分支 → `test_a_directory_is_not_refused_for_its_posix_link_count`
  以与 Linux 完全相同的 `WorkspaceEscapeError` 失败。
- 把 `links > 1` 改成 `links > 99` →
  `test_a_file_with_two_names_is_still_refused_under_posix_semantics`
  报 `WorkspaceEscapeError not raised`。

这两个测试把豁免从两侧钉住：目录必须豁免，文件仍必须拒绝，且区分二者的
**只有**文件/目录位。

### 已知限制（NOT_RUN / TO_VERIFY）

- **CI 权威信号 NOT_RUN**：`minimal-ci` 在本机跑不了，最终以 PR 上的绿灯为准。
- 本机 Linux 为 WSL2：sandbox 腿由 uv 钉在 Python 3.11，与 CI 完全一致；
  main 腿本地 3.12 vs CI 3.9，差一个版本，属「强但非逐位相同」。
- sandbox 套件跑在 `/mnt/c`（DrvFs）而非原生 Linux 文件系统上，
  差异已记录。
- **交叉平台污染（实测）**：WSL 与 Windows 共享 `sandbox_runtime/.venv`，
  Linux 侧 uv 写入 POSIX `lib64` symlink，导致 Windows 侧 uv
  `failed to remove file ...\.venv\lib64: 拒绝访问`，需
  `cmd /c rmdir` 移除该链接后恢复。该 venv 是 gitignore 的构建产物，
  无受跟踪文件受影响；已写入 Envelope 的 `known_limitations`。
- **范围修正 A1 已先呈交 Owner 批准**（Owner 答「继续」），
  记录在 Envelope `scope_amendment`；若被否决，回退是 4 行，linux 腿
  将剩 1 个 error。

### AIC 归属

`AIC Score Target: NONE`。这是 CI 正确性修复，不改变任何机制、benchmark 或
融合关系，**刻意不**映射到任何评分项。

### 边界

`gates/**`、`docs/evidence/**`、`src/**`、`tools/**`、`.github/**` 零改动
（`dev_gate` 的 `scope_check` 证明）。未接真实 LLM、未跑 benchmark。
