import unittest

from unittest.mock import patch

from scripts.weekly_check import find_tmdb_override, tmdb_title_override


class TmdbOverrideTests(unittest.TestCase):
    def test_finds_override_by_atmovies_id_first(self):
        overrides = {
            "movie-id": {"tmdb_id": 1, "source_titles": ["同名片"]},
            "title:other": {"tmdb_id": 2, "source_titles": ["同名片"]},
        }

        override = find_tmdb_override(
            {"atmovies_id": "movie-id", "title_zh": "同名片"}, overrides
        )

        self.assertEqual(override["tmdb_id"], 1)

    def test_finds_override_by_confirmed_source_title(self):
        overrides = {
            "title:銀河寫手": {
                "tmdb_id": 1196840,
                "source_titles": ["銀河寫手", "Galaxy Writer"],
            }
        }

        override = find_tmdb_override(
            {"atmovies_id": "new-id", "title_en": "Galaxy Writer"}, overrides
        )

        self.assertEqual(override["tmdb_id"], 1196840)

    @patch("scripts.weekly_check.load_tmdb_overrides")
    def test_uses_persistent_title_override(self, load_overrides):
        load_overrides.return_value = {
            "title:泥面人": {"tmdb_id": 1400940, "title_zh": "泥面人"}
        }

        self.assertEqual(tmdb_title_override(1400940), "泥面人")


if __name__ == "__main__":
    unittest.main()
