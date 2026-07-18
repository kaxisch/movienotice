import sys
import unittest
from datetime import date
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts"))

import publish_to_google_sheet as publish
import refresh_site_from_google_sheet as refresh


class CandidatePresenceTests(unittest.TestCase):
    def test_missing_candidates_increment_and_seen_candidates_reset(self):
        previous = [
            {"tmdb_id": "101", "title_zh": "仍在開眼", "atmovies_present": "FALSE", "consecutive_misses": "2"},
            {"tmdb_id": "202", "title_zh": "本次消失", "atmovies_present": "TRUE", "consecutive_misses": "0"},
        ]
        current = [
            {"tmdb_id": 101, "title_zh": "仍在開眼"},
            {"tmdb_id": 303, "title_zh": "新電影"},
        ]

        merged = publish.merge_candidate_presence(current, previous, "2026-07-18")
        by_id = {item["tmdb_id"]: item for item in merged}

        self.assertTrue(by_id[101]["atmovies_present"])
        self.assertEqual(by_id[101]["consecutive_misses"], 0)
        self.assertEqual(by_id[101]["last_seen_atmovies"], "2026-07-18")
        self.assertFalse(by_id[202]["atmovies_present"])
        self.assertEqual(by_id[202]["consecutive_misses"], 1)
        self.assertTrue(by_id[303]["ever_seen_atmovies"])

    def test_abnormally_small_audit_does_not_update_presence(self):
        previous = [
            {"tmdb_id": str(index), "atmovies_present": "TRUE"}
            for index in range(1, 21)
        ]
        current = [{"tmdb_id": index} for index in range(1, 10)]

        with self.assertRaises(RuntimeError):
            publish.merge_candidate_presence(current, previous, "2026-07-18")


class RefreshVisibilityTests(unittest.TestCase):
    TODAY = date(2026, 7, 18)

    def candidate(self, misses, present=False, ever_seen=True):
        return {
            "tmdb_id": 101,
            "ever_seen_atmovies": ever_seen,
            "atmovies_present": present,
            "consecutive_misses": misses,
        }

    def test_now_movie_hides_on_third_miss(self):
        release_date = date(2026, 7, 17)
        self.assertFalse(refresh.should_hide_for_atmovies_absence(self.candidate(2), release_date, self.TODAY, set()))
        self.assertTrue(refresh.should_hide_for_atmovies_absence(self.candidate(3), release_date, self.TODAY, set()))

    def test_soon_movie_hides_on_fifth_miss(self):
        release_date = date(2026, 8, 7)
        self.assertFalse(refresh.should_hide_for_atmovies_absence(self.candidate(4), release_date, self.TODAY, set()))
        self.assertTrue(refresh.should_hide_for_atmovies_absence(self.candidate(5), release_date, self.TODAY, set()))

    def test_seen_manual_and_tmdb_only_movies_are_not_hidden(self):
        release_date = date(2026, 7, 17)
        self.assertFalse(refresh.should_hide_for_atmovies_absence(self.candidate(9, present=True), release_date, self.TODAY, set()))
        self.assertFalse(refresh.should_hide_for_atmovies_absence(self.candidate(9), release_date, self.TODAY, {101}))
        self.assertFalse(
            refresh.should_hide_for_atmovies_absence(
                self.candidate(9, ever_seen=False), release_date, self.TODAY, set()
            )
        )


if __name__ == "__main__":
    unittest.main()
