import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from unittest.mock import patch

from scripts.weekly_check import (
    find_tmdb_override,
    load_tmdb_overrides,
    tmdb_title_override,
    write_json,
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

    def test_json_writer_preserves_source_wording_without_opencc_conversion(self):
        with TemporaryDirectory() as directory:
            output_path = Path(directory) / "output.json"
            write_json(output_path, {"synopsis": "猛烈攻擊干擾", "title": "泥面人"})
            written = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(written["synopsis"], "猛烈攻擊干擾")
        self.assertEqual(written["title"], "泥面人")

    def test_user_confirmed_matches_are_persistent(self):
        overrides = load_tmdb_overrides()
        expected = {
            "粽邪4": 1433568,
            "劇場版 境界的彼方 -I'LL BE HERE- 未來篇": 333622,
            "極限攀登1": 1280454,
            "藝妓日記": 489552,
            "書店裡的影像詩：生活不在他方": 1678745,
            "幕末太陽傳": 125217,
            "雁之寺": 333361,
            "Look Back": 1591675,
            "驀然回首（真人版）": 1591675,
            "白色情迷 經典數位修復": 109,
            "紅色情深 經典數位修復": 110,
            "攻殼機動隊1995": 9323,
            "人吶，為什麼要跑步？": 1758564,
            "洲崎樂園 赤信號": 125222,
            "安詳之獸": 125253,
        }
        for title, tmdb_id in expected.items():
            with self.subTest(title=title):
                override = find_tmdb_override({"title_zh": title}, overrides)
                self.assertIsNotNone(override)
                self.assertEqual(override["tmdb_id"], tmdb_id)


if __name__ == "__main__":
    unittest.main()
