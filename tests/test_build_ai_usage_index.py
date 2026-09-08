"""Tests for the AI usage ledger split storage / generated index / checks.

Covers the GH-49 tool (migrate / build / check) and the dev_gate wiring
(check_ai_usage_ledger). All fixtures are synthetic tempdirs — the real
ledger content is exercised by dev_gate itself on this repo.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

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
    def test_check_ai_usage_ledger_pass_on_tmp_repo(self):
        self.write_entry("AI-20260908-YEN-001.md", ACTOR_ENTRY)
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


if __name__ == "__main__":
    unittest.main()
