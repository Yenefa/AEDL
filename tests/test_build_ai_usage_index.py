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
        self.assertTrue(any("review-status" in f for f in findings))

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


if __name__ == "__main__":
    unittest.main()
