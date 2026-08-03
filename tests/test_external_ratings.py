import unittest
from unittest.mock import patch

from scripts import weekly_check as weekly


EMPTY = {field: {"value": "", "votes": 0} for field in ("imdb", "rt", "mc")}


class ExternalRatingsTests(unittest.TestCase):
    def test_parses_supported_ratings_and_ignores_popcorn(self):
        payload = {
            "ratings": [
                {"source": "imdb", "score": 7.4, "votes": 12345},
                {"source": "tomatoesaudience", "score": 88, "votes": 500},
                {"source": "tomatoes", "score": 92, "votes": 83},
                {"source": "metacritic", "score": 75, "votes": 32},
            ]
        }

        ratings = weekly.parse_mdblist_ratings(payload)

        self.assertEqual(ratings["imdb"], {"value": "7.4", "votes": 12345})
        self.assertEqual(ratings["rt"], {"value": "92%", "votes": 83})
        self.assertEqual(ratings["mc"], {"value": "75", "votes": 32})

    def test_ignores_missing_or_invalid_scores(self):
        self.assertEqual(weekly.parse_mdblist_ratings({"ratings": []}), EMPTY)
        self.assertEqual(
            weekly.parse_mdblist_ratings({"ratings": [{"source": "tomatoes", "score": None}]}),
            EMPTY,
        )

    @patch.object(weekly, "fetch_mdblist_ratings")
    @patch.object(weekly, "parse_omdb_ratings")
    def test_imdb_uses_source_with_more_votes(self, omdb, mdblist):
        omdb.return_value = {
            "imdb": {"value": "7.3", "votes": 12000},
            "rt": {"value": "", "votes": 0},
            "mc": {"value": "", "votes": 0},
        }
        mdblist.return_value = {
            "imdb": {"value": "7.4", "votes": 12500},
            "rt": {"value": "", "votes": 0},
            "mc": {"value": "", "votes": 0},
        }

        ratings = weekly.parse_external_ratings("tt123", checked_at="2026-08-03T18:00:00+08:00")

        self.assertEqual(ratings["imdb"], "7.4")
        self.assertEqual(ratings["meta"]["imdb"]["source"], "mdblist")

    @patch.object(weekly, "fetch_mdblist_ratings")
    @patch.object(weekly, "parse_omdb_ratings")
    def test_rt_and_metacritic_prefer_mdblist_when_difference_is_reasonable(self, omdb, mdblist):
        omdb.return_value = {
            "imdb": {"value": "", "votes": 0},
            "rt": {"value": "88%", "votes": 0},
            "mc": {"value": "72", "votes": 0},
        }
        mdblist.return_value = {
            "imdb": {"value": "", "votes": 0},
            "rt": {"value": "92%", "votes": 83},
            "mc": {"value": "75", "votes": 32},
        }

        ratings = weekly.parse_external_ratings("tt123", checked_at="2026-08-03T18:00:00+08:00")

        self.assertEqual(ratings["rt"], "92%")
        self.assertEqual(ratings["mc"], "75")
        self.assertEqual(ratings["meta"]["rt"]["source"], "mdblist")

    @patch.object(weekly, "fetch_mdblist_ratings")
    @patch.object(weekly, "parse_omdb_ratings")
    def test_large_conflict_retains_previous_value(self, omdb, mdblist):
        omdb.return_value = {
            "imdb": {"value": "", "votes": 0},
            "rt": {"value": "55%", "votes": 0},
            "mc": {"value": "", "votes": 0},
        }
        mdblist.return_value = {
            "imdb": {"value": "", "votes": 0},
            "rt": {"value": "92%", "votes": 83},
            "mc": {"value": "", "votes": 0},
        }
        previous = {
            "rt": "89%",
            "ratingMeta": {"rt": {"source": "mdblist", "votes": 70, "lastChanged": "2026-08-01"}},
        }

        ratings = weekly.parse_external_ratings(
            "tt123", previous=previous, checked_at="2026-08-03T18:00:00+08:00"
        )

        self.assertEqual(ratings["rt"], "89%")
        self.assertEqual(ratings["meta"]["rt"]["lastChanged"], "2026-08-01")

    @patch.object(weekly, "fetch_mdblist_ratings", return_value=EMPTY)
    @patch.object(weekly, "parse_omdb_ratings", return_value=EMPTY)
    def test_source_failures_retain_previous_ratings(self, omdb, mdblist):
        previous = {"imdb": "7.1", "rt": "90%", "mc": "74"}

        ratings = weekly.parse_external_ratings(
            "tt123", previous=previous, checked_at="2026-08-03T18:00:00+08:00"
        )

        self.assertEqual((ratings["imdb"], ratings["rt"], ratings["mc"]), ("7.1", "90%", "74"))


if __name__ == "__main__":
    unittest.main()
