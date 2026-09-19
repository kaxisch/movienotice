import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import publish_refresh_log as refresh_log


def movie(movie_id, title, date, bucket, rerelease=False):
    return {
        "id": movie_id,
        "title": title,
        "release_date": date,
        "bucket": bucket,
        "is_rerelease": rerelease,
    }


class RefreshLogTests(unittest.TestCase):
    def test_google_request_retries_without_tmdb_refresh_dependency(self):
        class Request:
            attempts = 0

            def execute(self):
                self.attempts += 1
                if self.attempts == 1:
                    raise ConnectionError("reset")
                return {"ok": True}

        request = Request()
        with patch.object(refresh_log.time, "sleep"):
            result = refresh_log.execute_google_sheets_request(request, "test")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(request.attempts, 2)

    def test_diff_distinguishes_add_remove_and_field_changes(self):
        previous = {
            1: movie(1, "保留片", "2026-09-19", "現正熱映"),
            2: movie(2, "下架片", "2026-09-18", "現正熱映"),
            3: movie(3, "變更片", "2026-10-01", "即將上映"),
        }
        current = {
            1: movie(1, "保留片", "2026-09-19", "現正熱映"),
            3: movie(3, "變更片", "2026-09-20", "現正熱映", True),
            4: movie(4, "新增片", "2026-10-02", "即將上映"),
        }

        changes = refresh_log.diff_movies(previous, current)

        self.assertEqual([change["kind"] for change in changes], [
            "移除",
            "上映日期、分類、重映標記",
            "新增",
        ])

    def test_no_change_still_builds_summary(self):
        movies = {1: movie(1, "相同片", "2026-09-19", "現正熱映")}

        rows = refresh_log.build_log_block(movies, movies, "2026-09-19T18:00:00+08:00", "run-1", "abc")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], "摘要")
        self.assertIn("無異動", rows[0][11])
        self.assertEqual(rows[0][12:], ["run-1", "abc"])

    def test_merge_keeps_newest_first_and_replaces_same_run(self):
        old_summary = ["old", "摘要", "", "", "", "", "", "", "", "", "", "old", "run-old", "sha-old"]
        duplicate_summary = ["duplicate", "摘要", "", "", "", "", "", "", "", "", "", "duplicate", "run-new", "sha-duplicate"]
        new_summary = ["new", "摘要", "", "", "", "", "", "", "", "", "", "new", "run-new", "sha-new"]
        existing = [refresh_log.HEADERS, duplicate_summary, [], old_summary]

        rows = refresh_log.merge_log_rows(existing, [new_summary], "run-new")

        self.assertEqual(rows, [refresh_log.HEADERS, new_summary, [], old_summary])

    def test_merge_retention_never_splits_a_run_block(self):
        newest = [["new", "摘要", "", "", "", "", "", "", "", "", "", "new", "new", "sha"]]
        old = [
            ["old", "摘要", "", "", "", "", "", "", "", "", "", "old", "old", "sha"],
            ["old", "明細", "新增", 1, "片", "", "2026-10-01", "", "即將上映", "", "否", "", "old", "sha"],
        ]

        rows = refresh_log.merge_log_rows([refresh_log.HEADERS, *old], newest, "new", max_rows=3)

        self.assertEqual(rows, [refresh_log.HEADERS, *newest])

    def test_current_run_is_kept_even_when_it_exceeds_retention_target(self):
        newest = [
            ["new", "摘要", "", "", "", "", "", "", "", "", "", "new", "new", "sha"],
            ["new", "明細", "新增", 1, "片", "", "2026-10-01", "", "即將上映", "", "否", "", "new", "sha"],
        ]

        rows = refresh_log.merge_log_rows([], newest, "new", max_rows=2)

        self.assertEqual(rows, [refresh_log.HEADERS, *newest])

    def test_workflow_records_log_after_site_commit(self):
        workflow = (ROOT_DIR / ".github" / "workflows" / "refresh-site.yml").read_text(encoding="utf-8")

        self.assertLess(workflow.index("Commit refreshed site data"), workflow.index("Record public movie changes"))
        self.assertIn("scripts/publish_refresh_log.py", workflow)


if __name__ == "__main__":
    unittest.main()
