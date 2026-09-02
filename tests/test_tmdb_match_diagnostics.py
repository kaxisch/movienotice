import unittest

from scripts.weekly_check import score_tmdb_candidate, tmdb_candidate_match_diagnostics


class TmdbMatchDiagnosticsTests(unittest.TestCase):
    def test_bilingual_source_title_with_exact_chinese_prefix_is_not_suspicious(self):
        movie = {
            "title_zh": "人吶，為什麼要跑步？ Hit the Road Now！",
            "release_date_tw": "2026-10-02",
        }
        candidate = {
            "title": "人吶，為什麼要跑步？",
            "original_title": "人吶，為什麼要跑步？",
            "release_date": "2026-10-02",
        }

        score = score_tmdb_candidate(movie, candidate)
        reasons = tmdb_candidate_match_diagnostics(movie, candidate, score)

        self.assertGreaterEqual(score, 55)
        self.assertEqual(reasons, [])

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
