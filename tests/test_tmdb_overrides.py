import unittest

from unittest.mock import patch

from scripts.weekly_check import (
    find_tmdb_override,
    tmdb_title_override,
    to_traditional_text,
)


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

    def test_tomorrow_concert_uses_confirmed_atmovies_override(self):
        overrides = {
            "ftko99799079": {
                "tmdb_id": 1741921,
                "title_zh": "TOMORROW X TOGETHER VR CONCERT : ENDLESS RIDE",
            }
        }

        override = find_tmdb_override(
            {"atmovies_id": "ftko99799079", "title_zh": "TOMORROW"}, overrides
        )

        self.assertEqual(override["tmdb_id"], 1741921)

    def test_love_not_comedy_uses_confirmed_atmovies_override(self):
        overrides = {
            "fjjp43653895": {
                "tmdb_id": 1701409,
                "title_zh": "LOVE ≠ COMEDY",
            }
        }

        override = find_tmdb_override(
            {"atmovies_id": "fjjp43653895", "title_zh": "LOVE ≠ COMEDY"},
            overrides,
        )

        self.assertEqual(override["tmdb_id"], 1701409)

    @patch("scripts.weekly_check.load_tmdb_overrides")
    def test_uses_persistent_title_override(self, load_overrides):
        load_overrides.return_value = {
            "title:泥面人": {"tmdb_id": 1400940, "title_zh": "泥面人"}
        }

        self.assertEqual(tmdb_title_override(1400940), "泥面人")

    def test_traditional_conversion_preserves_manual_title_wording(self):
        self.assertEqual(to_traditional_text("泥面人"), "泥面人")


if __name__ == "__main__":
    unittest.main()
