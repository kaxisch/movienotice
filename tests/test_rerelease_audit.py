import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts"))

import cinema_rereleases as cinema
import publish_to_google_sheet as publish
import refresh_site_from_google_sheet as refresh
import weekly_check as weekly


class CinemaParserTests(unittest.TestCase):
    @patch("weekly_check.tmdb_movie")
    @patch("weekly_check.load_tmdb_overrides")
    def test_rerelease_match_honors_atmovies_override(self, overrides, tmdb_movie):
        overrides.return_value = {"fsjp31415228": {"tmdb_id": 45580}}
        tmdb_movie.return_value = {
            "id": 45580,
            "title": "樂與路",
            "original_title": "ソラニン",
            "release_date": "2010-04-03",
        }

        result = weekly.choose_rerelease_tmdb_match({
            "atmovies_id": "fsjp31415228",
            "title_zh": "手拉你",
            "title_en": "Solanin",
            "release_date_tw": "2010-08-13",
        })

        self.assertEqual(result["id"], 45580)

    def test_ambassador_parser_reads_both_statuses_and_dates(self):
        html = """
        <div class="movie-list"><div class="cell"><div class="title">
          <h6><a href="/home/MovieContent?MID=one&DT=2026/08/05">你的名字。（十周年重映）</a></h6>
          <p class="show-for-large">Your Name.</p>
        </div></div></div>
        <div class="movie-list"><div class="cell"><div class="title">
          <h6><a href="/home/MovieContent?MID=two&DT=2026/08/21">魯冰花（數位修復版）</a></h6>
          <p class="show-for-large">The Dull-Ice Flower</p>
        </div></div></div>
        """
        with self.assertRaisesRegex(ValueError, "數量異常"):
            cinema.parse_ambassador(html)

        # 補足健康檢查門檻，並驗證前後片單的狀態與日期。
        filler = "".join(
            f'<div class="cell"><div class="title"><h6><a href="/home/MovieContent?MID=x{index}&DT=2026/08/10">電影{index}</a></h6></div></div>'
            for index in range(3)
        )
        html = html.replace('<div class="movie-list">', f'<div class="movie-list">{filler}', 1)
        movies = cinema.parse_ambassador(html)
        your_name = next(movie for movie in movies if "你的名字" in movie["title_zh"])
        self.assertEqual(your_name["status"], "now")
        self.assertEqual(your_name["release_date_tw"], "2026-08-05")
        self.assertEqual(movies[-1]["status"], "soon")

    def test_showtime_parser_classifies_by_release_date(self):
        items = "".join(
            f'<li><a href="/programs/{index}/"><strong>電影{index}</strong>'
            f'<div>{release_date} 上映</div></a></li>'
            for index, release_date in enumerate(
                ["2026-08-01", "2026-08-05", "2026-08-06", "2026-08-07", "2026-08-08"], 1
            )
        )
        movies = cinema.parse_showtime(
            f'<ul class="seo-movie-list">{items}</ul>', date(2026, 8, 5)
        )
        self.assertEqual([movie["status"] for movie in movies[:3]], ["now", "now", "soon"])

    def test_rerelease_requires_marker_or_earlier_tw_theatrical_date(self):
        movie = {"title_zh": "普通舊片", "release_date_tw": "2026-08-05"}
        self.assertFalse(cinema.is_confirmed_rerelease(movie, {}, []))
        self.assertTrue(cinema.is_confirmed_rerelease(movie, {}, [{"date": "2001-01-01"}]))
        self.assertFalse(cinema.is_confirmed_rerelease(movie, {}, [{"date": "2026-07-01"}]))
        self.assertTrue(cinema.is_confirmed_rerelease(movie, {"release_date": "1986-11-26"}, []))
        marked = {"title_zh": "普通舊片（4K修復版）", "release_date_tw": "2026-08-05"}
        self.assertTrue(cinema.is_confirmed_rerelease(marked, {}, []))

    def test_rerelease_labels_are_removed_without_damaging_search_title(self):
        self.assertEqual(cinema.strip_rerelease_labels("你的名字。（十周年重映）"), "你的名字")
        self.assertEqual(cinema.strip_rerelease_labels("魯冰花（數位修復版）"), "魯冰花")
        self.assertEqual(cinema.strip_rerelease_labels("魯冰花 數位修復版"), "魯冰花")
        self.assertEqual(cinema.strip_rerelease_labels("Your Name.(2026)"), "Your Name")

    def test_promotional_screening_is_not_treated_as_general_rerelease(self):
        self.assertTrue(cinema.is_promotional_screening("（DBOX特別場）蜘蛛人：重生日"))
        self.assertFalse(cinema.is_promotional_screening("你的名字。（十周年重映）"))

    def test_ambassador_detail_parser_uses_real_release_date(self):
        html = '<div class="movie-info-box"><p class="note">上映日期：2026/07/24</p></div>'
        self.assertEqual(cinema.parse_ambassador_release_date(html), "2026-07-24")

    @patch("weekly_check.time.sleep")
    @patch("weekly_check.tmdb_search")
    def test_rerelease_match_prioritizes_exact_chinese_title(self, tmdb_search, _sleep):
        tmdb_search.return_value = [
            {"id": 372058, "title": "你的名字", "original_title": "君の名は。"},
            {"id": 553301, "title": "Your Name", "original_title": "Your Name"},
        ]
        result = weekly.choose_rerelease_tmdb_match({
            "title_zh": "你的名字。（十周年重映）",
            "title_en": "Your Name.(2026)",
        })
        self.assertEqual(result["id"], 372058)

    @patch("weekly_check.time.sleep")
    @patch("weekly_check.tmdb_search")
    def test_unmarked_same_title_prefers_new_movie_from_cinema_year(self, tmdb_search, _sleep):
        tmdb_search.return_value = [
            {"id": 100001, "title": "驀然回首", "original_title": "Look Back", "release_date": "2024-06-28"},
            {"id": 1591675, "title": "驀然回首", "original_title": "Look Back", "release_date": "2026-08-07"},
        ]
        result = weekly.choose_rerelease_tmdb_match({
            "title_zh": "驀然回首",
            "title_en": "Look Back",
            "release_date_tw": "2026-08-07",
        })
        self.assertEqual(result["id"], 1591675)

    @patch("weekly_check.time.sleep")
    @patch("weekly_check.tmdb_search")
    def test_theatrical_edition_word_does_not_block_old_movie_match(self, tmdb_search, _sleep):
        tmdb_search.return_value = [{
            "id": 44728,
            "title": "航海王：被詛咒的聖劍",
            "original_title": "ONE PIECE 呪われた聖剣",
            "release_date": "2004-03-06",
        }]
        result = weekly.choose_rerelease_tmdb_match({
            "title_zh": "航海王劇場版：被詛咒的聖劍",
            "release_date_tw": "2026-08-14",
        })
        self.assertEqual(result["id"], 44728)

    @patch("weekly_check.time.sleep")
    @patch("weekly_check.tmdb_search")
    def test_franchise_subtitle_can_match_longer_tmdb_title(self, tmdb_search, _sleep):
        tmdb_search.return_value = [{
            "id": 260916,
            "title": "航海王電影：阿拉巴斯坦戰記 沙漠王女與海賊們",
            "original_title": "ONE PIECE エピソードオブアラバスタ",
            "release_date": "2007-03-03",
        }]
        result = weekly.choose_rerelease_tmdb_match({
            "title_zh": "航海王：阿拉巴斯坦戰記",
            "release_date_tw": "2008-09-19",
        })
        self.assertEqual(result["id"], 260916)

    @patch("weekly_check.time.sleep")
    @patch("weekly_check.tmdb_search")
    def test_short_subtitle_matches_same_franchise_with_chapter_label(self, tmdb_search, _sleep):
        tmdb_search.return_value = [{
            "id": 47747,
            "title": "空之境界 第八章：終章",
            "original_title": "劇場版 空の境界 終章",
            "release_date": "2010-12-18",
        }]
        result = weekly.choose_rerelease_tmdb_match({
            "title_zh": "空之境界劇場版：終章",
            "release_date_tw": "2026-06-17",
        })
        self.assertEqual(result["id"], 47747)

    def test_missing_current_date_is_pending_not_tmdb_mismatch(self):
        self.assertEqual(cinema.tmdb_date_status("", [{"date": "2005-01-28"}]), "pending")

    @patch("weekly_check.time.sleep")
    @patch("weekly_check.tmdb_search")
    def test_rerelease_search_uses_global_primary_date(self, tmdb_search, _sleep):
        tmdb_search.return_value = [{
            "id": 64131,
            "title": "壞痞子",
            "original_title": "Mauvais Sang",
            "release_date": "1986-11-26",
        }]
        weekly.choose_rerelease_tmdb_match({
            "title_zh": "壞痞子",
            "release_date_tw": "2026-07-31",
        })
        self.assertTrue(any(call.kwargs.get("region") is False for call in tmdb_search.call_args_list))

    def test_atmovies_old_date_is_a_private_rerelease_candidate_signal(self):
        self.assertTrue(weekly.is_stale_atmovies_release_date("2005-01-28", date(2026, 8, 6)))
        self.assertFalse(weekly.is_stale_atmovies_release_date("2026-07-31", date(2026, 8, 6)))
        self.assertFalse(weekly.is_stale_atmovies_release_date("", date(2026, 8, 6)))

    def test_updated_atmovies_date_still_recognizes_old_tmdb_movie(self):
        self.assertTrue(weekly.is_known_old_atmovies_movie({
            "title_zh": "空之境界劇場版：終章",
            "release_date_tw": "2026-06-17",
            "tmdb_primary_release_date": "2010-12-28",
            "tmdb_tw_releases": [],
        }))


class RereleasePresenceTests(unittest.TestCase):
    def test_vieshow_403_does_not_block_complete_absence_audit(self):
        health = {
            "atmovies": True,
            "showtime": True,
            "ambassador": True,
            "vieshow": False,
        }
        self.assertTrue(weekly.rerelease_absence_audit_complete(health, True))

    def test_required_source_or_tmdb_failure_blocks_absence_audit(self):
        health = {
            "atmovies": True,
            "showtime": False,
            "ambassador": True,
            "vieshow": False,
        }
        self.assertFalse(weekly.rerelease_absence_audit_complete(health, True))
        health["showtime"] = True
        self.assertFalse(weekly.rerelease_absence_audit_complete(health, False))

    def previous(self, misses=0, audit_date="2026-08-01"):
        return [{
            "tmdb_id": "101",
            "title_zh": "經典電影",
            "rerelease_present": "TRUE",
            "consecutive_misses": str(misses),
            "hidden": "FALSE",
            "last_audit_date": audit_date,
        }]

    def test_partial_failure_does_not_increment_or_hide(self):
        merged = publish.merge_rerelease_presence([], self.previous(1), "2026-08-05", False)
        self.assertEqual(merged[0]["consecutive_misses"], "1")
        self.assertEqual(merged[0]["hidden"], "FALSE")

    def test_confirmed_new_movie_removes_previous_wrong_rerelease_match(self):
        previous = self.previous()
        previous[0]["source_urls"] = "https://www.showtimes.com.tw/programs/look-back/"
        merged = publish.merge_rerelease_presence(
            [], previous, "2026-08-05", False,
            ["https://www.showtimes.com.tw/programs/look-back/"],
        )
        self.assertEqual(merged, [])

    def test_two_complete_absences_hide_and_same_date_does_not_double_count(self):
        first = publish.merge_rerelease_presence([], self.previous(), "2026-08-05", True)
        self.assertEqual(first[0]["consecutive_misses"], 1)
        self.assertFalse(first[0]["hidden"])
        same_date = publish.merge_rerelease_presence([], first, "2026-08-05", True)
        self.assertEqual(same_date[0]["consecutive_misses"], 1)
        second = publish.merge_rerelease_presence([], same_date, "2026-08-08", True)
        self.assertEqual(second[0]["consecutive_misses"], 2)
        self.assertTrue(second[0]["hidden"])

    def test_any_present_source_restores_candidate(self):
        current = [{"tmdb_id": 101, "present_sources": "showtime", "rerelease_present": True}]
        previous = self.previous(2)
        previous[0]["hidden"] = "TRUE"
        merged = publish.merge_rerelease_presence(current, previous, "2026-08-05", True)
        self.assertEqual(merged[0]["consecutive_misses"], 0)
        self.assertFalse(merged[0]["hidden"])
        self.assertEqual(merged[0]["present_sources"], "showtime")

    def test_refresh_hidden_flag_is_independent_from_atmovies(self):
        self.assertTrue(refresh.should_hide_rerelease({"hidden": "TRUE", "atmovies_present": "TRUE"}))
        self.assertFalse(refresh.should_hide_rerelease({"hidden": "FALSE"}))


if __name__ == "__main__":
    unittest.main()
