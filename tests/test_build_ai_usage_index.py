"""Tests for the AI usage ledger split storage / generated index / checks.

Covers the GH-49 tool (migrate / build / check) and the dev_gate wiring
(check_ai_usage_ledger). All fixtures are synthetic tempdirs — the real
ledger content is exercised by dev_gate itself on this repo.
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from tools import build_ai_usage_index as bi
from tools import dev_gate

LEGACY_ENTRY = """## AI-20260901-007

- 日期：2026-09-01
- 任务名称：stub 条目
- 人工审核：`PENDING_HUMAN_REVIEW`
"""

ACTOR_ENTRY = """## AI-20260908-YEN-001

- 日期：2026-09-08
- 任务名称：actor 格式条目
- 人工审核：`PENDING_HUMAN_REVIEW`
"""

SECOND_ACTOR_ENTRY = """## AI-20260908-PER-001

- 日期：2026-09-08
- 任务名称：另一个 actor 的同日条目
- 人工审核：`HUMAN_REVIEWED`
"""


class LedgerToolTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / ".git").mkdir()
        self.entries = self.tmp / "docs" / "compliance" / "ai-usage"
        self.entries.mkdir(parents=True)
        self.ledger = self.tmp / "docs" / "compliance" / "AI_USAGE_LOG.md"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_entry(self, name, text):
        (self.entries / name).write_bytes(text.encode("utf-8"))

    def write_ledger(self, text):
        self.ledger.write_bytes(text.encode("utf-8"))


class MigrateTests(LedgerToolTestBase):
    def test_same_id_changed_content_is_hard_failure(self):
        self.write_ledger(LEGACY_ENTRY)
        self.write_entry("AI-20260901-007.md", LEGACY_ENTRY.replace("stub", "edited"))
        before = (self.entries / "AI-20260901-007.md").read_bytes()
        with self.assertRaisesRegex(bi.LedgerError, "existing per-entry content differs"):
            bi.cmd_migrate(self.tmp)
        self.assertEqual((self.entries / "AI-20260901-007.md").read_bytes(), before)

    def test_mismatch_is_detected_before_any_new_file_is_written(self):
        self.write_ledger(ACTOR_ENTRY + "\n" + LEGACY_ENTRY)
        self.write_entry("AI-20260901-007.md", LEGACY_ENTRY.replace("stub", "edited"))
        with self.assertRaises(bi.LedgerError):
            bi.cmd_migrate(self.tmp)
        self.assertFalse((self.entries / "AI-20260908-YEN-001.md").exists())

    def test_migration_preserves_internal_crlf_and_trailing_spaces(self):
        body = LEGACY_ENTRY.replace("stub 条目", "stub 条目  ").replace("\n", "\r\n")
        self.write_ledger(body + "\r\n")
        bi.cmd_migrate(self.tmp)
        self.assertEqual((self.entries / "AI-20260901-007.md").read_bytes(), body.encode("utf-8"))
        self.assertEqual(bi.cmd_migrate(self.tmp)["skipped"], 1)

    def test_invalid_migration_id_fails_before_writes(self):
        self.write_ledger(LEGACY_ENTRY + ACTOR_ENTRY.replace("AI-20260908-YEN-001", "AI-bad/path"))
        with self.assertRaises(bi.LedgerError):
            bi.cmd_migrate(self.tmp)
        self.assertEqual(list(self.entries.iterdir()), [])

    def test_explicit_legacy_source_preserves_generated_index(self):
        self.write_entry("AI-20260908-YEN-001.md", ACTOR_ENTRY)
        bi.cmd_build(self.tmp)
        before = self.ledger.read_bytes()
        source = self.tmp / "legacy.md"
        source.write_bytes(LEGACY_ENTRY.encode("utf-8"))
        result = bi.cmd_migrate(self.tmp, source=source)
        self.assertEqual(result["migrated"], ["AI-20260901-007"])
        self.assertEqual(self.ledger.read_bytes(), before)

    def test_migrate_generated_index_is_noop(self):
        self.write_entry("AI-20260908-YEN-001.md", ACTOR_ENTRY)
        bi.cmd_build(self.tmp)
        self.assertEqual(bi.cmd_migrate(self.tmp)["migrated"], [])

    def test_split_single_ledger(self):
        self.write_ledger("# AI Usage Log\n\n> header\n\n" + LEGACY_ENTRY + "\n" + ACTOR_ENTRY)
        result = bi.cmd_migrate(self.tmp)
        self.assertEqual(result["migrated"], ["AI-20260901-007", "AI-20260908-YEN-001"])
        body = (self.entries / "AI-20260901-007.md").read_text(encoding="utf-8")
        self.assertTrue(body.startswith("## AI-20260901-007"))
        self.assertIn("任务名称：stub 条目", body)

    def test_migrate_is_idempotent(self):
        self.write_ledger("# AI Usage Log\n\n" + LEGACY_ENTRY)
        bi.cmd_migrate(self.tmp)
        again = bi.cmd_migrate(self.tmp)
        self.assertEqual(again["migrated"], [])
        self.assertEqual(again["skipped"], 1)

    def test_duplicate_heading_rejected(self):
        self.write_ledger(LEGACY_ENTRY + "\n" + LEGACY_ENTRY)
        with self.assertRaises(bi.LedgerError):
            bi.cmd_migrate(self.tmp)

    def test_empty_ledger_is_noop(self):
        self.write_ledger("   \n")
        result = bi.cmd_migrate(self.tmp)
        self.assertEqual(result["migrated"], [])


class BuildTests(LedgerToolTestBase):
    def test_missing_summary_has_visible_fallback(self):
        body = "## AI-20260908-YEN-001\n- 日期：2026-09-08\n- 人工审核：PENDING_HUMAN_REVIEW\n"
        self.write_entry("AI-20260908-YEN-001.md", body)
        bi.cmd_build(self.tmp)
        self.assertIn("— (no summary line)", self.ledger.read_text(encoding="utf-8"))

    def test_index_lists_all_entries_sorted(self):
        self.write_entry("AI-20260908-PER-001.md", SECOND_ACTOR_ENTRY)
        self.write_entry("AI-20260901-007.md", LEGACY_ENTRY)
        self.write_entry("AI-20260908-YEN-001.md", ACTOR_ENTRY)
        result = bi.cmd_build(self.tmp)
        self.assertEqual(result["index_entries"], 3)
        text = self.ledger.read_text(encoding="utf-8")
        self.assertIn(bi.INDEX_MARKER, text)
        self.assertLess(text.index("AI-20260901-007"), text.index("AI-20260908-PER-001"))
        self.assertLess(text.index("AI-20260908-PER-001"), text.index("AI-20260908-YEN-001"))
        self.assertIn("(ai-usage/AI-20260908-YEN-001.md)", text)

    def test_build_refuses_empty_dir(self):
        with self.assertRaises(bi.LedgerError):
            bi.cmd_build(self.tmp)

    def test_index_rebuild_is_stable(self):
        for name, text in [("AI-20260901-007.md", LEGACY_ENTRY), ("AI-20260908-YEN-001.md", ACTOR_ENTRY)]:
            self.write_entry(name, text)
        bi.cmd_build(self.tmp)
        first = self.ledger.read_text(encoding="utf-8")
        bi.cmd_build(self.tmp)
        self.assertEqual(first, self.ledger.read_text(encoding="utf-8"))


class CheckTests(LedgerToolTestBase):
    def test_changed_index_count_fails_with_same_links_and_marker(self):
        self.write_entry("AI-20260908-YEN-001.md", ACTOR_ENTRY)
        bi.cmd_build(self.tmp)
        self.write_ledger(self.ledger.read_text(encoding="utf-8").replace("共 1 条", "共 999 条"))
        self.assertTrue(any("content differs from generated output" in f for f in bi.check_ledger(self.tmp)))

    def test_changed_index_summary_fails_with_same_links_and_marker(self):
        self.write_entry("AI-20260908-YEN-001.md", ACTOR_ENTRY)
        bi.cmd_build(self.tmp)
        self.write_ledger(self.ledger.read_text(encoding="utf-8").replace("actor 格式条目", "wrong summary"))
        self.assertTrue(any("content differs from generated output" in f for f in bi.check_ledger(self.tmp)))

    def test_stray_files_and_subdirectories_fail_but_readme_is_allowed(self):
        self.write_entry("AI-20260908-YEN-001.md", ACTOR_ENTRY)
        bi.cmd_build(self.tmp)
        (self.entries / "README.md").write_bytes(b"# How to use\n")
        self.assertEqual(bi.check_ledger(self.tmp), [])
        for name in ("NOTES.txt", ".hidden"):
            (self.entries / name).write_bytes(b"stray")
        (self.entries / "nested").mkdir()
        findings = bi.check_ledger(self.tmp)
        for name in ("NOTES.txt", ".hidden", "nested"):
            self.assertTrue(any(name in f and "stray" in f for f in findings), findings)

    def test_random_actor_id_accepted_alongside_legacy_formats(self):
        entry_id = "AI-20260908-CODEX-" + "A91F72C4B13E6D805CF438021BE97A52"
        self.write_entry(entry_id + ".md", ACTOR_ENTRY.replace("AI-20260908-YEN-001", entry_id))
        self.write_entry("AI-20260901-007.md", LEGACY_ENTRY)
        self.write_entry("AI-20260908-YEN-001.md", ACTOR_ENTRY)
        bi.cmd_build(self.tmp)
        self.assertEqual(bi.check_ledger(self.tmp), [])

    def test_healthy_ledger_passes(self):
        self.write_entry("AI-20260901-007.md", LEGACY_ENTRY)
        self.write_entry("AI-20260908-YEN-001.md", ACTOR_ENTRY)
        bi.cmd_build(self.tmp)
        generated = self.ledger.read_bytes()
        for ending in (b"\n", b"\r\n"):
            with self.subTest(checkout_line_ending=ending):
                self.ledger.write_bytes(generated.replace(b"\n", ending))
                self.assertEqual(bi.check_ledger(self.tmp), [])

    def test_duplicate_filename_and_heading(self):
        self.write_entry("AI-20260901-007.md", LEGACY_ENTRY)
        # a file whose heading disagrees with its name
        self.write_entry("AI-20260909-YYY-001.md", ACTOR_ENTRY)
        findings = bi.check_ledger(self.tmp)
        self.assertTrue(any("filename does not match" in f for f in findings))

    def test_unregistered_actor_fails(self):
        self.write_entry("AI-20260908-FOO-001.md", ACTOR_ENTRY.replace("YEN-001", "FOO-001"))
        findings = bi.check_ledger(self.tmp)
        self.assertTrue(any("not registered" in f for f in findings))

    def test_bad_id_format_fails(self):
        self.write_entry("AI-20260908-1.md", ACTOR_ENTRY.replace("YEN-001", "1"))
        findings = bi.check_ledger(self.tmp)
        self.assertTrue(any("does not match" in f for f in findings))

    def test_date_mismatch_fails(self):
        self.write_entry("AI-20260908-YEN-001.md", ACTOR_ENTRY.replace("2026-09-08", "2026-09-07"))
        bi.cmd_build(self.tmp)
        findings = bi.check_ledger(self.tmp)
        self.assertTrue(any("ID 日期" in f for f in findings))

    def test_missing_review_status_fails(self):
        text = ACTOR_ENTRY.replace("- 人工审核：`PENDING_HUMAN_REVIEW`\n", "")
        self.write_entry("AI-20260908-YEN-001.md", text)
        findings = bi.check_ledger(self.tmp)
        self.assertTrue(any("status field" in f for f in findings), findings)

    def test_hand_edited_index_fails(self):
        self.write_entry("AI-20260908-YEN-001.md", ACTOR_ENTRY)
        bi.cmd_build(self.tmp)
        self.write_ledger("# AI Usage Log\n\nhand edited, no marker\n")
        findings = bi.check_ledger(self.tmp)
        self.assertTrue(any("GENERATED marker" in f for f in findings))

    def test_index_out_of_sync_fails(self):
        self.write_entry("AI-20260908-YEN-001.md", ACTOR_ENTRY)
        bi.cmd_build(self.tmp)
        self.write_entry("AI-20260908-PER-001.md", SECOND_ACTOR_ENTRY)  # not yet in index
        findings = bi.check_ledger(self.tmp)
        self.assertTrue(any("out of sync" in f for f in findings))


class ReviewStatusFieldTests(LedgerToolTestBase):
    """GH-49 review M1: the review status must come from a parsed field.

    A bare occurrence of PENDING_HUMAN_REVIEW / HUMAN_REVIEWED / ACCEPTED in
    the body must never satisfy the check, and an invalid value in a review
    field must not be laundered by a valid token elsewhere in the body.
    """

    def test_body_mention_without_review_field_fails(self):
        text = ACTOR_ENTRY.replace(
            "- 人工审核：`PENDING_HUMAN_REVIEW`\n",
            "- 备注：正文提到 HUMAN_REVIEWED，但没有人工审核字段。\n")
        self.write_entry("AI-20260908-YEN-001.md", text)
        findings = bi.check_ledger(self.tmp)
        self.assertTrue(any("no status field" in f for f in findings), findings)

    def test_invalid_status_value_is_not_laundered_by_body_text(self):
        text = ACTOR_ENTRY.replace(
            "- 人工审核：`PENDING_HUMAN_REVIEW`\n",
            "- 人工审核：SOME_INVALID_STATUS\n"
            "- 备注：正文同时出现 PENDING_HUMAN_REVIEW 与 HUMAN_REVIEWED。\n")
        self.write_entry("AI-20260908-YEN-001.md", text)
        findings = bi.check_ledger(self.tmp)
        self.assertTrue(any("SOME_INVALID_STATUS" in f for f in findings), findings)

    def test_inline_trailing_garbage_is_not_a_valid_status(self):
        # prefix matching would launder "HUMAN_REVIEWED garbage" into a status
        text = ACTOR_ENTRY.replace("- 人工审核：`PENDING_HUMAN_REVIEW`\n",
                                   "- 人工审核：HUMAN_REVIEWED garbage\n")
        self.write_entry("AI-20260908-YEN-001.md", text)
        findings = bi.check_ledger(self.tmp)
        self.assertTrue(
            any("review-status" in f and "HUMAN_REVIEWED garbage" in f for f in findings),
            findings)

    def test_nested_trailing_garbage_is_not_a_valid_status(self):
        text = ACTOR_ENTRY.replace("- 人工审核：`PENDING_HUMAN_REVIEW`\n",
                                   "- 人工审核：\n  - 状态：ACCEPTED garbage\n")
        self.write_entry("AI-20260908-YEN-001.md", text)
        findings = bi.check_ledger(self.tmp)
        self.assertTrue(
            any("review-status" in f and "ACCEPTED garbage" in f for f in findings),
            findings)

    def test_each_allowed_status_value_passes(self):
        for status in ("PENDING_HUMAN_REVIEW", "HUMAN_REVIEWED", "ACCEPTED"):
            with self.subTest(status=status):
                self.write_entry("AI-20260908-YEN-001.md",
                                 ACTOR_ENTRY.replace("PENDING_HUMAN_REVIEW", status))
                bi.cmd_build(self.tmp)
                self.assertEqual(bi.check_ledger(self.tmp), [])

    def test_review_field_forms_present_in_existing_stock_pass(self):
        # Forms that actually occur under docs/compliance/ai-usage/.
        forms = {
            "inline_backtick": "- 人工审核：`PENDING_HUMAN_REVIEW`\n",
            "inline_ascii_colon": "- 人工审核: PENDING_HUMAN_REVIEW\n",
            "inline_with_note": "- 人工审核：`PENDING_HUMAN_REVIEW`（PR #21）\n",
            "nested_status": "- 人工审核：\n  - 状态：`PENDING_HUMAN_REVIEW`\n  - 审核人：待定\n",
            "legacy_final_status": "- 最终状态：\n  - `PENDING_HUMAN_REVIEW`\n",
        }
        for name, field in forms.items():
            with self.subTest(form=name):
                self.write_entry(
                    "AI-20260908-YEN-001.md",
                    "## AI-20260908-YEN-001\n\n- 日期：2026-09-08\n"
                    "- 任务名称：actor 格式条目\n" + field)
                bi.cmd_build(self.tmp)
                self.assertEqual(bi.check_ledger(self.tmp), [])

    def test_unrelated_field_name_does_not_satisfy_check(self):
        text = ACTOR_ENTRY.replace("- 人工审核：`PENDING_HUMAN_REVIEW`\n",
                                   "- 审核状态：`PENDING_HUMAN_REVIEW`\n")
        self.write_entry("AI-20260908-YEN-001.md", text)
        findings = bi.check_ledger(self.tmp)
        self.assertTrue(any("no status field" in f for f in findings), findings)

    def test_coexisting_review_fields_in_existing_stock_pass(self):
        # AI-20260829-001..005 carry both 人工审核：HUMAN_REVIEWED and
        # 最终状态：ACCEPTED; repeated fields are part of the existing stock,
        # so the strict parser must not treat them as a conflict.
        text = ACTOR_ENTRY.replace(
            "- 人工审核：`PENDING_HUMAN_REVIEW`\n",
            "- 人工审核：`HUMAN_REVIEWED`\n- 最终状态：\n  - `ACCEPTED`\n")
        self.write_entry("AI-20260908-YEN-001.md", text)
        bi.cmd_build(self.tmp)
        self.assertEqual(bi.check_ledger(self.tmp), [])


class DevGateWiringTests(LedgerToolTestBase):
    def test_index_body_tamper_fails_development_gate(self):
        self.write_entry("AI-20260908-YEN-001.md", ACTOR_ENTRY)
        bi.cmd_build(self.tmp)
        self.write_ledger(self.ledger.read_text(encoding="utf-8").replace("共 1 条", "共 999 条"))
        self.assertEqual(dev_gate.check_ai_usage_ledger(self.tmp)["status"], "fail")

    def test_check_ai_usage_ledger_pass_on_tmp_repo(self):
        self.write_entry("AI-20260908-YEN-001.md", ACTOR_ENTRY)
        (self.entries / "README.md").write_bytes(b"# Instructions\n")
        bi.cmd_build(self.tmp)
        receipt = dev_gate.check_ai_usage_ledger(self.tmp)
        self.assertEqual(receipt["status"], "pass")
        self.assertIn("1 entry file(s)", receipt["detail"])

    def test_check_ai_usage_ledger_fails_closed(self):
        self.write_entry("AI-20260908-YEN-001.md", ACTOR_ENTRY)
        self.write_entry("AI-20260908-PER-001.md", SECOND_ACTOR_ENTRY)
        bi.cmd_build(self.tmp)
        self.write_entry("AI-20260908-FOO-999.md", ACTOR_ENTRY.replace("YEN-001", "FOO-999"))
        receipt = dev_gate.check_ai_usage_ledger(self.tmp)
        self.assertEqual(receipt["status"], "fail")
        self.assertIn("not registered", receipt["detail"])

    def test_dry_run_receipt_includes_ledger_check(self):
        receipt = dev_gate.run_gate(dry_run=True)
        self.assertIn("ai_usage_ledger", receipt["checks"])
        self.assertEqual(receipt["checks"]["ai_usage_ledger"]["status"], "pending")


class NewEntryTests(LedgerToolTestBase):
    def test_same_actor_from_identical_branch_snapshots_uses_random_ids(self):
        other = self.tmp / "branch-b"
        (other / bi.ENTRIES_DIR).mkdir(parents=True)
        existing = ACTOR_ENTRY.replace("YEN-001", "CODEX-003")
        self.write_entry("AI-20260908-CODEX-003.md", existing)
        (other / bi.ENTRIES_DIR / "AI-20260908-CODEX-003.md").write_bytes(existing.encode("utf-8"))
        with patch.object(bi.secrets, "token_hex", side_effect=["a" * 32, "b" * 32]):
            first = bi.cmd_new(self.tmp, "CODEX", "2026-09-08", "branch A")
            second = bi.cmd_new(other, "CODEX", "2026-09-08", "branch B")
        self.assertEqual(first["entry_id"], "AI-20260908-CODEX-" + "A" * 32)
        self.assertEqual(second["entry_id"], "AI-20260908-CODEX-" + "B" * 32)
        bi.cmd_build(self.tmp)
        self.assertEqual(bi.check_ledger(self.tmp), [])

    def test_collision_retries_without_overwriting(self):
        entry_id = "AI-20260908-CODEX-" + "A" * 32
        self.write_entry(entry_id + ".md", "preserve this content")
        with patch.object(bi.secrets, "token_hex", side_effect=["a" * 32, "b" * 32]):
            result = bi.cmd_new(self.tmp, "CODEX", "2026-09-08", "retry")
        self.assertNotEqual(result["entry_id"], entry_id)
        self.assertEqual((self.entries / (entry_id + ".md")).read_bytes(), b"preserve this content")

    def test_exhausted_collision_retries_fail_closed(self):
        entry_id = "AI-20260908-CODEX-" + "A" * 32
        self.write_entry(entry_id + ".md", "preserve")
        with patch.object(bi.secrets, "token_hex", return_value="a" * 32):
            with self.assertRaisesRegex(bi.LedgerError, "unique"):
                bi.cmd_new(self.tmp, "CODEX", "2026-09-08", "retry")
        self.assertEqual((self.entries / (entry_id + ".md")).read_bytes(), b"preserve")

    def test_same_actor_concurrent_creates_do_not_lose_records(self):
        def create(n):
            return bi.cmd_new(self.tmp, "CODEX", "2026-09-08", "session " + str(n))
        with ThreadPoolExecutor(max_workers=4) as pool:
            records = list(pool.map(create, range(12)))
        self.assertEqual(len({r["entry_id"] for r in records}), 12)
        bi.cmd_build(self.tmp)
        self.assertEqual(len(bi.read_entries(self.tmp)), 12)
        self.assertEqual(bi.check_ledger(self.tmp), [])

    def test_new_rejects_unknown_actor_bad_date_and_multiline_summary(self):
        for actor, day, summary in [("UNKNOWN", "2026-09-08", "a"),
                                    ("CODEX", "2026-02-30", "a"),
                                    ("CODEX", "2026-09-08", "a\n## injected")]:
            with self.subTest(actor=actor, day=day, summary=summary):
                with self.assertRaises(bi.LedgerError):
                    bi.cmd_new(self.tmp, actor, day, summary)
        self.assertEqual(list(self.entries.iterdir()), [])


class AutonomousStatusLaneTests(LedgerToolTestBase):
    """ADR-022 / AGENTS.md 0A.4: the 自主验收 lane, fail-closed and disjoint.

    Two properties are enforced, both of them about not being able to fake a
    lane: an unknown 自主验收 value is rejected rather than ignored, and the
    two lanes cannot be crossed in either direction — an AI acceptance typed
    into 人工审核, or a human status typed into 自主验收, is a finding.
    """

    AUTO_ENTRY = """## AI-20260908-YEN-002

- 日期：2026-09-08
- 任务名称：自治验收条目
- 人工审核：`PENDING_HUMAN_REVIEW`
- 自主验收：`AI_REVIEWED`
"""

    def findings_for(self, text):
        self.write_entry("AI-20260908-YEN-002.md", text)
        bi.cmd_build(self.tmp)
        return bi.check_ledger(self.tmp)

    def test_autonomous_lane_alone_satisfies_the_status_requirement(self):
        text = self.AUTO_ENTRY.replace("- 人工审核：`PENDING_HUMAN_REVIEW`\n", "")
        findings = self.findings_for(text)
        self.assertFalse([f for f in findings if "no status field" in f], findings)

    def test_each_allowed_autonomous_value_passes(self):
        for status in bi.AUTONOMOUS_STATUS_VALUES:
            with self.subTest(status=status):
                shutil.rmtree(self.entries)
                self.entries.mkdir(parents=True)
                findings = self.findings_for(
                    self.AUTO_ENTRY.replace("AI_REVIEWED", status))
                self.assertFalse([f for f in findings if "自主验收" in f], findings)

    def test_invalid_autonomous_value_is_rejected(self):
        findings = self.findings_for(
            self.AUTO_ENTRY.replace("AI_REVIEWED", "AI_APPROVED_BY_HUMAN"))
        self.assertTrue(
            any("自主验收" in f and "AI_APPROVED_BY_HUMAN" in f for f in findings), findings)

    def test_trailing_garbage_is_not_laundered_into_a_valid_status(self):
        findings = self.findings_for(
            self.AUTO_ENTRY.replace("`AI_REVIEWED`", "AI_ACCEPTED garbage"))
        self.assertTrue(
            any("自主验收" in f and "AI_ACCEPTED garbage" in f for f in findings), findings)

    def test_autonomous_status_in_the_human_field_is_a_finding(self):
        findings = self.findings_for(
            self.AUTO_ENTRY.replace(
                "- 人工审核：`PENDING_HUMAN_REVIEW`", "- 人工审核：`AI_ACCEPTED`"))
        self.assertTrue(
            any("HUMAN review" in f and "自主验收" in f for f in findings), findings)

    def test_human_status_in_the_autonomous_field_is_a_finding(self):
        findings = self.findings_for(
            self.AUTO_ENTRY.replace("`AI_REVIEWED`", "`HUMAN_REVIEWED`"))
        self.assertTrue(
            any("never records human review" in f for f in findings), findings)

    def test_body_mention_of_an_autonomous_status_is_not_a_declaration(self):
        # Same laundering rule as the human lane: a bare mention in prose never
        # satisfies the requirement.
        text = self.AUTO_ENTRY.replace(
            "- 自主验收：`AI_REVIEWED`\n",
            "- 备注：正文提到 AI_ACCEPTED，但没有自主验收字段。\n")
        findings = self.findings_for(text)
        self.assertFalse([f for f in findings if "自主验收 value" in f], findings)

    def test_autonomous_field_forms_in_existing_stock_pass(self):
        for form in (
            "- 自主验收: AI_ACCEPTED\n",             # ASCII colon, no backticks
            "- 自主验收：`AI_REVIEWED`（ADR-022）\n",   # trailing annotation
            "* 自主验收：`AI_REVIEWED`\n",            # bullet asterisk
        ):
            with self.subTest(form=form):
                shutil.rmtree(self.entries)
                self.entries.mkdir(parents=True)
                findings = self.findings_for(
                    self.AUTO_ENTRY.replace("- 自主验收：`AI_REVIEWED`\n", form))
                self.assertFalse([f for f in findings if "自主验收" in f], findings)

    def test_mutation_the_lane_rules_actually_bite(self):
        """Negative control: neutralise the cross-lane rule, both cases go green.

        An earlier version of this control widened AUTONOMOUS_STATUS_VALUES and
        asserted the invalid-value case turned green. That was wrong twice: the
        failing path had the module global baked into its message so the case
        stayed red anyway, and widening an allow-set does not touch either
        cross-lane rule. The rule now lives in `cross_lane_findings` purely so
        it can be swapped out here without patching source text.
        """
        cross_human = self.AUTO_ENTRY.replace(
            "- 人工审核：`PENDING_HUMAN_REVIEW`", "- 人工审核：`AI_ACCEPTED`")
        cross_auto = self.AUTO_ENTRY.replace("`AI_REVIEWED`", "`HUMAN_REVIEWED`")

        for label, text, needle in (
            ("human field", cross_human, "HUMAN review"),
            ("autonomous field", cross_auto, "never records human review"),
        ):
            with self.subTest(before_removal=label):
                shutil.rmtree(self.entries)
                self.entries.mkdir(parents=True)
                findings = self.findings_for(text)
                self.assertTrue(any(needle in f for f in findings),
                                "expected a cross-lane finding, got %s" % (findings,))

        original = bi.cross_lane_findings
        try:
            bi.cross_lane_findings = lambda rel, declared, autonomous: []
            for label, text in (("human field", cross_human), ("autonomous field", cross_auto)):
                with self.subTest(after_removal=label):
                    shutil.rmtree(self.entries)
                    self.entries.mkdir(parents=True)
                    findings = self.findings_for(text)
                    self.assertFalse(
                        [f for f in findings
                         if "HUMAN review" in f or "never records human review" in f],
                        "cross-lane finding survived removal: %s" % (findings,))
        finally:
            bi.cross_lane_findings = original

        # And the restored rule reports them again — the swap really was the
        # only thing making the cases green.
        for label, text, needle in (
            ("human field", cross_human, "HUMAN review"),
            ("autonomous field", cross_auto, "never records human review"),
        ):
            with self.subTest(after_restore=label):
                shutil.rmtree(self.entries)
                self.entries.mkdir(parents=True)
                findings = self.findings_for(text)
                self.assertTrue(any(needle in f for f in findings), findings)


if __name__ == "__main__":
    unittest.main()
