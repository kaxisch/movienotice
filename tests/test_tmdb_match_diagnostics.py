import unittest

from scripts.weekly_check import tmdb_candidate_match_diagnostics


class TmdbMatchDiagnosticsTests(unittest.TestCase):
    def test_low_english_similarity_alone_is_not_suspicious(self):
        movie = {
            "title_zh": "國有器官",
            "title_en": "State Organs",
            "release_date_tw": "2024-10-01",
        }
        candidate = {
            "title": "國有器官",
            "original_title": "國有器官",
            "release_date": "2024-10-01",
        }

        reasons = tmdb_candidate_match_diagnostics(movie, candidate, 87.6)

        self.assertEqual(reasons, [])

    def test_low_english_similarity_is_reported_when_chinese_is_also_low(self):
        movie = {
            "title_zh": "粽邪4",
            "title_en": "The Rope Curse 4",
            "release_date_tw": "2026-08-27",
        }
        candidate = {
            "title": "坤蒂拉娜",
            "original_title": "Kuntilanak",
            "release_date": "2026-08-27",
        }

        reasons = tmdb_candidate_match_diagnostics(movie, candidate, 41.1)

        self.assertTrue(any(reason.startswith("英文片名相似度偏低") for reason in reasons))
        self.assertTrue(any(reason.startswith("中文片名相似度偏低") for reason in reasons))


if __name__ == "__main__":
    unittest.main()
