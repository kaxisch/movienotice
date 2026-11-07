import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts"))

import apply_manual_tmdb_reviews as reviews


class ApplyManualTmdbReviewsTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            reviews.AUDIT_HEADERS,
            ["tmdb_not_found", "樂園追放", "2026-11-06", "Expelled from Paradise", "", "", ""],
            ["其他", "不應處理", "2026-11-06", "Ignored", "", "", ""],
        ]
        self.overrides = {
            "title:樂園追放": {
                "tmdb_id": 304023,
                "title_zh": "樂園追放",
                "source_titles": ["樂園追放", "Expelled from Paradise"],
            }
        }

    def test_builds_candidate_from_reviewed_audit_row(self):
        matches = reviews.manual_matches_from_rows(self.rows, self.overrides, "2026-11-01")

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["tmdb_id"], 304023)
        self.assertEqual(matches[0]["source_bucket"], "next")
        self.assertTrue(matches[0]["cinema_present"])
        self.assertEqual(matches[0]["present_sources"], "atmovies")

    def test_marks_audit_row_and_adds_tmdb_link(self):
        matches = reviews.manual_matches_from_rows(self.rows, self.overrides, "2026-11-01")

        updated = reviews.updated_audit_rows(self.rows, matches)

        self.assertEqual(updated[1][0], "manually_matched")
        self.assertEqual(
            updated[1][4],
            "https://www.themoviedb.org/movie/304023?language=zh-TW",
        )
        self.assertEqual(updated[2], self.rows[2])

    def test_repeat_run_is_idempotent_and_preserves_existing_state(self):
        matches = reviews.manual_matches_from_rows(self.rows, self.overrides, "2026-11-01")
        existing = [{"tmdb_id": "304023", "ever_published": "TRUE", "consecutive_misses": "2"}]

        first = reviews.merge_manual_candidates(existing, matches)
        second = reviews.merge_manual_candidates(first, matches)

        self.assertEqual(first, second)
        self.assertEqual(second[0]["ever_published"], "TRUE")
        self.assertEqual(second[0]["consecutive_misses"], 0)

    def test_latest_audit_sheet_ignores_private_control_tabs(self):
        self.assertEqual(
            reviews.latest_audit_sheet_title(["_candidates", "2026-10-28", "2026-11-01"]),
            "2026-11-01",
        )

    def test_uses_recorded_audit_completeness_instead_of_assuming_success(self):
        rows = [
            ["audit_date", "completed_at", "audit_complete"],
            ["2026-11-01", "2026-11-01T07:00:00+08:00", "FALSE"],
        ]

        self.assertFalse(reviews.audit_is_complete(rows, "2026-11-01"))
        self.assertFalse(
            reviews.manual_matches_from_rows(
                self.rows, self.overrides, "2026-11-01", audit_complete=False
            )[0]["absence_audit_complete"]
        )

    def test_handles_missing_date_and_suspicious_manual_corrections(self):
        rows = [
            reviews.AUDIT_HEADERS,
            ["missing_tw_date", "正義女聲", "2026-12-31", "First Voice", "https://www.themoviedb.org/movie/1362419?language=zh-TW"],
            ["tmdb_match_suspicious", "大天使", "2026-12-24", "Archangel", "https://www.themoviedb.org/movie/1318889?language=zh-TW"],
        ]
        overrides = {
            "title:正義女聲": {
                "tmdb_id": 1706689,
                "source_titles": ["正義女聲", "First Voice"],
                "supersedes_tmdb_ids": [1362419],
            },
            "title:大天使": {
                "tmdb_id": 1562642,
                "source_titles": ["大天使", "Archangel"],
                "supersedes_tmdb_ids": [1318889],
            },
        }

        matches = reviews.manual_matches_from_rows(rows, overrides, "2026-11-04")

        self.assertEqual([item["tmdb_id"] for item in matches], [1706689, 1562642])

    def test_recovers_misaligned_row_when_current_link_is_superseded(self):
        rows = [
            reviews.AUDIT_HEADERS,
            ["大天使", "正義女聲", "2026-12-31", "First Voice", "https://www.themoviedb.org/movie/1362419?language=zh-TW"],
        ]
        overrides = {
            "title:正義女聲": {
                "tmdb_id": 1706689,
                "source_titles": ["正義女聲", "First Voice"],
                "supersedes_tmdb_ids": [1362419],
            }
        }

        matches = reviews.manual_matches_from_rows(rows, overrides, "2026-11-04")

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["tmdb_id"], 1706689)

    def test_manual_date_override_corrects_audit_date(self):
        rows = [
            reviews.AUDIT_HEADERS,
            ["tmdb_date_mismatch", "憤怒鳥玩電影3", "2027-12-31", "The Angry Birds Movie 3", ""],
        ]
        overrides = {
            "title:憤怒鳥玩電影3": {
                "tmdb_id": 1300926,
                "release_date_tw": "2026-12-31",
                "source_titles": ["憤怒鳥玩電影3", "The Angry Birds Movie 3"],
            }
        }

        matches = reviews.manual_matches_from_rows(rows, overrides, "2026-11-07")
        updated = reviews.updated_audit_rows(rows, matches)

        self.assertEqual(matches[0]["release_date_tw"], "2026-12-31")
        self.assertEqual(updated[1][2], "2026-12-31")


if __name__ == "__main__":
    unittest.main()
