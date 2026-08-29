import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
ROOT_DIR = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from check_weekly_audit_status import audit_completed_for_date


class WeeklyAuditWatchdogTests(unittest.TestCase):
    def test_complete_marker_for_target_date_skips_recovery(self):
        rows = [
            ["audit_date", "completed_at", "audit_complete"],
            ["2026-08-29", "2026-08-29T07:01:00+08:00", "TRUE"],
        ]
        self.assertTrue(audit_completed_for_date(rows, "2026-08-29"))

    def test_missing_incomplete_or_other_date_requires_recovery(self):
        rows = [
            ["audit_date", "completed_at", "audit_complete"],
            ["2026-08-29", "2026-08-29T07:01:00+08:00", "FALSE"],
            ["2026-08-27", "2026-08-27T07:01:00+08:00", "TRUE"],
        ]
        self.assertFalse(audit_completed_for_date(rows, "2026-08-30"))
        self.assertFalse(audit_completed_for_date(rows, "2026-08-29"))

    def test_missing_or_legacy_headers_require_recovery(self):
        self.assertFalse(audit_completed_for_date([], "2026-08-29"))
        self.assertFalse(
            audit_completed_for_date([["last_audit_date", "complete"]], "2026-08-29")
        )

    def test_watchdog_checks_twice_and_dispatches_only_when_incomplete(self):
        workflow = (ROOT_DIR / ".github/workflows/weekly-check-watchdog.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn('cron: "7 0,1 * * 3,6"', workflow)
        self.assertIn("actions: write", workflow)
        self.assertIn("steps.audit.outputs.completed != 'true'", workflow)
        self.assertIn("gh workflow run weekly-check.yml --ref main", workflow)


if __name__ == "__main__":
    unittest.main()
