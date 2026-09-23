# PBF-001..010 公共事实交接件（供评分侧核对 B 维）

## 权威 provenance（叙事以此为准）

`v3d freeze manifest 3935891e9f144a88d09ba514b8695ec113e97d6fd64773499ddf49169ec09b56`
→ **bound case package** `Y4-001`（其 sha256 = **9767134b33a708cb785d86b2953346cdfb0e425103a767ce2e7994df3485e5db**）
→ `public_context.public_facts`（本件即该字段的逐字提取）

**重建位置**（仅供复现，非权威来源）：`r20/critic20/claim3/freeze-work/pass2/Y4-001.json`。
该目录名属 critic 工作区；其字节与冻结绑定一致，但权威性是上面的 manifest → package hash 链，不是路径名。

- 五例一致：`Y4-001..Y4-005` 的 `public_facts` 均为 **10 条且 ID 集合相同**（已核）
- 形态提示：`PBF-*` 用 `fact_id`；BB-001 用 `id`，且 **v3d 中不存在 BB-001**（见 Issue #68 第 1 项）
- 批准引用：`r17/FACTS-CHANGE-REVIEW.md`（BB-001 `ACCEPTED_PUBLIC_POLICY_ADDITION`）；PBF-001..010 记为 `OWNER_APPROVED (r8)`
- 请重点核对：**typical → mandatory**、**recommended → required** 一类语义升级（会污染 B 维）；若发现差异按**输入缺陷**处理（Y4 方案 §8）

## PBF-001 — ESP32-C3-WROOM-02/02U module

- **statement（逐字）**：Module pin 13 is GPIO18/USB D-; pin 14 is GPIO19/USB D+.
- **scope**：Generic device information; no case-specific repair target.
- **verification_status**：PRIMARY_SOURCE_TEXT_CHECKED_BY_AGENT
- **source**：version=1.7；locator=Table 3-1, printed p11；url=https://documentation.espressif.com/esp32-c3-wroom-02_datasheet_en.pdf

## PBF-002 — ESP32-C3-WROOM-02/02U EN

- **statement（逐字）**：EN high enables the chip, EN low disables it; the EN input must not float.
- **scope**：Generic device information; no case-specific repair target.
- **verification_status**：PRIMARY_SOURCE_TEXT_CHECKED_BY_AGENT
- **source**：version=1.7；locator=Table 3-1, printed p11；url=https://documentation.espressif.com/esp32-c3-wroom-02_datasheet_en.pdf

## PBF-003 — ESP32-C3 strapping inputs

- **statement（逐字）**：GPIO9 defaults to a weak pull-up at reset when external circuitry is absent or high-impedance; external drive and reset sampling conditions matter.
- **scope**：Generic device information; no case-specific repair target.
- **verification_status**：PRIMARY_SOURCE_TEXT_CHECKED_BY_AGENT
- **source**：version=1.7；locator=Table 4-1 and accompanying text, printed p12；url=https://documentation.espressif.com/esp32-c3-wroom-02_datasheet_en.pdf

## PBF-004 — ESP32-C3 internal pull resistors

- **statement（逐字）**：45 kohm is a typical internal weak pull-up/down value at 3.3 V and 25 C, not a guaranteed minimum or maximum.
- **scope**：Generic device information; no case-specific repair target.
- **verification_status**：PRIMARY_SOURCE_TEXT_CHECKED_BY_AGENT
- **source**：version=1.7；locator=Table 6-3, printed p22；url=https://documentation.espressif.com/esp32-c3-wroom-02_datasheet_en.pdf

## PBF-005 — ESP32-C3-WROOM-02/02U EN timing

- **statement（逐字）**：An EN RC delay is advised; 10 kohm and 1 uF are usual recommended values, to be adjusted for actual supply rise and reset timing.
- **scope**：Generic device information; no case-specific repair target.
- **verification_status**：PRIMARY_SOURCE_TEXT_CHECKED_BY_AGENT
- **source**：version=1.7；locator=Section 9 notes, printed p34；url=https://documentation.espressif.com/esp32-c3-wroom-02_datasheet_en.pdf

## PBF-006 — ESP32-C3 USB design

- **statement（逐字）**：The guide recommends reserving series resistors with initial values 22/33 ohm and optional initially unpopulated shunt capacitors near the chip; this is a design recommendation.
- **scope**：Generic device information; no case-specific repair target.
- **verification_status**：PRIMARY_SOURCE_TEXT_CHECKED_BY_AGENT
- **source**：version=latest; captured 2026-09-10；locator=USB section；url=https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c3/schematic-checklist.html

## PBF-007 — ESP32-C3 GPIO9 design

- **statement（逐字）**：The guide recommends an external GPIO9 pull-up and warns against high-value capacitors there. This does not erase its default internal pull-up.
- **scope**：Generic device information; no case-specific repair target.
- **verification_status**：PRIMARY_SOURCE_TEXT_CHECKED_BY_AGENT
- **source**：version=latest; captured 2026-09-10；locator=Strapping Pins section；url=https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c3/schematic-checklist.html

## PBF-008 — SHT3x-DIS ADDR

- **statement（逐字）**：ADDR must not float. Logic low selects 7-bit address 0x44; logic high selects 0x45. Keep its level stable throughout an I2C transaction.
- **scope**：Generic device information; no case-specific repair target.
- **verification_status**：PRIMARY_SOURCE_TEXT_CHECKED_BY_AGENT
- **source**：version=December 2022, Version 7；locator=Table 7 / Section 3.4 / Table 8, printed pp8-9；url=https://sensirion.com/media/documents/213E6A3B/63A5A569/Datasheet_SHT3x_DIS.pdf；document_sha256=095b1853e7f4328f5897c9ca6c392a7dd8b0202eda66b0a2629f9cb840dd496d

## PBF-009 — SHT3x-DIS nRESET

- **statement（逐字）**：Unused nRESET is recommended to float or connect to VDD through at least 2 kohm; it has an internal typical 50 kohm pull-up.
- **scope**：Generic device information; no case-specific repair target.
- **verification_status**：PRIMARY_SOURCE_TEXT_CHECKED_BY_AGENT
- **source**：version=December 2022, Version 7；locator=Section 3.6, printed p9；url=https://sensirion.com/media/documents/213E6A3B/63A5A569/Datasheet_SHT3x_DIS.pdf；document_sha256=095b1853e7f4328f5897c9ca6c392a7dd8b0202eda66b0a2629f9cb840dd496d

## PBF-010 — Current project firmware source

- **statement（逐字）**：The driver source defines DEFAULT_ADDR as 0x44; application source assigns SHT_ADDR from that constant. This is a static source observation, not proof of deployed firmware or a human-approved immutable requirement.
- **scope**：Owner-approved ordinary project-source observation (not an immutable requirement).
- **verification_status**：SOURCE_CONSTANTS_READ_BY_AGENT; RUNTIME_NOT_CHECKED
- **source**：repository=Yenefa/AEDL；baseline=63bc7e31523b403f3229cda2f2db5c291b33482d

