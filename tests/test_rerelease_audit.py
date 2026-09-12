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
    def test_miramar_reads_titles_dates_and_merges_overlapping_sections(self):
        html = '''<ul id="movie_area"><li><a class="img" href="/Movie/detail?id=123"></a>
            <div class="title">測試干擾<span>Test Film</span><span class="date">2026-09-04</span>
            <div class="badge_movie_level">輔15級</div></div></li></ul>'''
        now = cinema.parse_miramar(html)
        soon = cinema.parse_miramar(html, "soon")
        self.assertEqual(now[0]["title_zh"], "測試干擾")
        self.assertEqual(now[0]["title_en"], "Test Film")
        merged = cinema.merge_raw_movies(now + soon)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["statuses"], ["now", "soon"])
        self.assertEqual(merged[0]["release_date_tw"], "2026-09-04")
        missing = cinema.parse_miramar(html.replace("2026-09-04", "上映日期待確認"))
        self.assertEqual(missing[0]["release_date_tw"], "")
        with self.assertRaises(ValueError):
            cinema.parse_miramar("<html>blocked</html>")

    def test_centuryasia_branch_uses_section_status_and_preserves_old_date(self):
        html = '''<ul id="ContentPlaceHolder1_movie_poster"><li>
            <a class="mosaic-overlay" href="Movie_Info_detail.aspx?programid=123">
            <h4>測試重映</h4><p>2024-11-01</p></a></li></ul>
            <ul id="ContentPlaceHolder1_movie_new_poster"><li>
            <a class="mosaic-overlay" href="Movie_Info_detail.aspx?programid=456">
            <h4>新片</h4><p>2026-09-18</p></a></li></ul>'''
        for branch in ("centuryasia_ximen", "centuryasia_beyond", "centuryasia_kaohsiung"):
            movies = cinema.parse_centuryasia_branch(html, branch)
            self.assertEqual([m["status"] for m in movies], ["now", "soon"])
            self.assertEqual(movies[0]["release_date_tw"], "2024-11-01")
            self.assertEqual(movies[0]["source"], branch)
            self.assertTrue(movies[0]["source_url"].startswith(cinema.SOURCE_URLS[branch].rsplit("/", 1)[0]))
        with self.assertRaises(ValueError):
            cinema.parse_centuryasia_branch(html.replace("movie_new_poster", "changed"), "centuryasia_ximen")

    def test_centuryasia_main_rejects_failed_response_and_keeps_missing_dates(self):
        payload = {"status": True, "Data": [{"programid": "0000123", "cname": "測試電影",
                                             "ename": "Test Film", "ReleaseDate": None}]}
        movie = cinema.parse_centuryasia(payload, "soon")[0]
        self.assertEqual(movie["status"], "soon")
        self.assertEqual(movie["release_date_tw"], "")
        self.assertEqual(movie["title_en"], "Test Film")
        self.assertTrue(movie["source_url"].endswith("obj=0000123"))
        for broken in ({"status": False, "Data": payload["Data"]}, {"status": True, "Data": []},
                       {"status": True, "Data": [{}]}, [], {}):
            with self.assertRaises(ValueError):
                cinema.parse_centuryasia(broken)

    def test_additional_source_failure_discards_partial_list_and_continues(self):
        html = '''<ul id="movie_area"><li><a class="img" href="/Movie/detail?id=123"></a>
            <div class="title">測試電影<span>Test Film</span><span class="date">2026-09-04</span>
            </div></li></ul>'''
        def fetch(url, agent):
            if url == cinema.SOURCE_URLS["miramar_now"]:
                return html
            if url in (cinema.SOURCE_URLS["centuryasia_now"], cinema.SOURCE_URLS["centuryasia_soon"]):
                return '{"status":true,"Data":[{"programid":"123","cname":"其他電影"}]}'
            raise RuntimeError("source unavailable")
        with patch.object(cinema, "fetch_html", side_effect=fetch):
            movies, health, errors = cinema.fetch_additional_cinema_movies("test", date(2026, 9, 9))
        self.assertFalse(health["miramar"])
        self.assertIn("miramar", errors)
        self.assertTrue(health["centuryasia"])
        self.assertEqual({movie["source"] for movie in movies}, {"centuryasia"})
        self.assertEqual(set(health), {"miramar", "spot_taipei", "centuryasia", "centuryasia_ximen",
                                      "centuryasia_beyond", "centuryasia_kaohsiung"})
        self.assertTrue(weekly.rerelease_absence_audit_complete({
            **health, "atmovies": True, "showtime": True, "ambassador": True,
        }, True))

    def test_spot_taipei_infers_current_year_without_using_old_url_year(self):
        html = '''<table><tr><td><a class="abgne-zoom-out"
            href="../202202/m1/movie.html"><img></a></td></tr>
            <tr><td><table><tr><td class="movie_body_w3">9/4 - 熱映中</td></tr>
            <tr><td class="movie_title">干擾<br>修復版</td></tr>
            <tr><td class="movie_title_eng">Test Film</td></tr></table></td></tr></table>'''
        movie = cinema.parse_spot_taipei(html, date(2026, 9, 9))[0]
        self.assertEqual(movie["title_zh"], "干擾 修復版")
        self.assertEqual(movie["release_date_tw"], "2026-09-04")
        self.assertEqual(movie["status"], "now")
        self.assertEqual(movie["source"], "spot_taipei")
        self.assertIn("/202202/", movie["source_url"])
        upcoming = cinema.parse_spot_taipei(
            html.replace("9/4 - 熱映中", "2026/9/18"), date(2026, 9, 9)
        )[0]
        self.assertEqual(upcoming["release_date_tw"], "2026-09-18")
        self.assertEqual(upcoming["status"], "soon")

        kusama = cinema.parse_spot_taipei(
            html.replace("9/4 - 熱映中", "9/11 - 本周新片"), date(2026, 9, 10)
        )[0]
        self.assertEqual(kusama["release_date_tw"], "2026-09-11")
        self.assertEqual(kusama["status"], "soon")
        self.assertEqual(cinema.tmdb_date_status(kusama["release_date_tw"], []), "missing")
        self.assertEqual(cinema.tmdb_date_status(kusama["release_date_tw"], [{"date": "2018-09-07"}]), "mismatch")
        self.assertEqual(cinema.tmdb_date_status(kusama["release_date_tw"], [{"date": "2026-09-11"}]), "confirmed")

    def test_spot_taipei_month_day_handles_year_boundary_and_status(self):
        cases = [
            ("1/5 - 即將上映", date(2026, 12, 28), date(2027, 1, 5)),
            ("12/25 - 熱映中", date(2027, 1, 2), date(2026, 12, 25)),
            ("1/5 -", date(2026, 12, 28), date(2027, 1, 5)),
            ("12/25 - 本周新片", date(2026, 12, 26), date(2026, 12, 25)),
            ("9/11 - 熱映中", date(2026, 9, 11), date(2026, 9, 11)),
            ("2018/9/7", date(2026, 9, 10), date(2018, 9, 7)),
            ("2/29 - 即將上映", date(2027, 12, 28), date(2028, 2, 29)),
            ("2/30", date(2026, 9, 10), None),
            ("2026/2/29", date(2026, 9, 10), None),
            ("上映日期待確認", date(2026, 9, 10), None),
        ]
        for value, today, expected in cases:
            with self.subTest(value=value, today=today):
                self.assertEqual(cinema.spot_taipei_release_date(value, today), expected)

    def test_spot_taipei_rejects_empty_or_broken_cards(self):
        for html in ("<html>Access denied</html>", '<td class="movie_title">電影</td>'):
            with self.assertRaises(ValueError):
                cinema.parse_spot_taipei(html)

    def test_review_tsv_row_preserves_matched_tmdb_fields(self):
        rows = []
        weekly.append_rerelease_tsv_rows(rows, {
            "candidates": [],
            "review_rows": [{
                "audit_category": "院線候選－TMDB日期不一致",
                "title_zh": "測試電影",
                "title_en": "Test Movie",
                "release_date_tw": "2026-09-04",
                "tmdb_url": "https://www.themoviedb.org/movie/123?language=zh-TW",
                "tmdb_primary_release_date": "2025-01-02",
                "sources": ["showtime"],
                "source_urls": ["https://example.com/movie"],
            }],
        })

        self.assertEqual(rows[0][4], "https://www.themoviedb.org/movie/123?language=zh-TW")
        self.assertEqual(rows[0][5], "2025-01-02")

    def test_manual_rerelease_override_contains_confirmed_movies(self):
        confirmed_ids = weekly.load_manual_rerelease_ids()
        self.assertTrue({12197, 23160, 311056, 333622, 41498, 44730, 75233, 80518, 490794, 481432, 660120}.issubset(confirmed_ids))

    def test_manual_confirmation_applies_without_automatic_rerelease_evidence(self):
        self.assertTrue(weekly.is_verified_rerelease(
            {"title_zh": "幸福的拉札洛", "release_date_tw": "2026-08-07"},
            {"id": 481432, "release_date": "2018-05-31"},
            [{"date": "2026-08-07"}],
            {481432},
        ))

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

    @patch("weekly_check.tmdb_movie")
    @patch("weekly_check.load_tmdb_overrides")
    def test_rerelease_match_honors_cross_cinema_title_override(self, overrides, tmdb_movie):
        overrides.return_value = {
            "fsjp31415228": {"tmdb_id": 45580, "source_titles": ["手拉你", "SOLANIN"]}
        }
        tmdb_movie.return_value = {
            "id": 45580,
            "title": "樂與路",
            "original_title": "ソラニン",
            "release_date": "2010-04-03",
        }

        result = weekly.choose_rerelease_tmdb_match({
            "title_zh": "SOLANIN",
            "release_date_tw": "2026-07-31",
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

    def test_spot_huashan_parser_reads_current_rerelease_dates(self):
        cards = "".join(
            f'''<div class="nowplayingdiv"><a href="movie202607/movie{index}.html">
              <div class="nowplayingtext_title">{title}</div>
              <div class="nowplayingtext_eng">{english}</div>
              <div class="nowplayingtext6">{release_date}起</div>
            </a></div>'''
            for index, (title, english, release_date) in enumerate([
                ("SOLANIN", "", "2026/7/31"),
                ("蜂蜜之夏", "The Wonders", "2026/7/24"),
                ("電影三", "Movie Three", "2026/8/1"),
                ("電影四", "Movie Four", "2026/8/2"),
                ("電影五", "Movie Five", "2026/8/3"),
            ])
        )
        movies = cinema.parse_spot_huashan(cards)
        self.assertEqual(movies[0]["release_date_tw"], "2026-07-31")
        self.assertEqual(movies[0]["source"], "spot_huashan")
        self.assertEqual(movies[1]["title_en"], "The Wonders")
        self.assertEqual(movies[1]["release_date_tw"], "2026-07-24")

        upcoming = cinema.parse_spot_huashan(cards, "soon", "https://www.spot-hs.org.tw/movie/comingsoon.html")
        self.assertTrue(all(movie["status"] == "soon" for movie in upcoming))

    def test_wonderful_parser_reads_current_release_dates(self):
        cards = "".join(
            f'''<li><a class="poster_wrap" href="/movie/inner?id={index}">
              <p class="movie_title">{title}</p>
              <p class="time">{release_date} 上　　映</p>
            </a></li>'''
            for index, (title, release_date) in enumerate([
                ("壞痞子4K修復版", "2026/07/31"),
                ("電影二", "2026/08/01"),
                ("電影三", "2026/08/02"),
                ("電影四", "2026/08/03"),
                ("電影五", "2026/08/04"),
            ])
        )
        movies = cinema.parse_wonderful(f'<ul class="movie_list">{cards}</ul>')
        self.assertEqual(movies[0]["title_zh"], "壞痞子4K修復版")
        self.assertEqual(movies[0]["release_date_tw"], "2026-07-31")
        self.assertEqual(movies[0]["source"], "wonderful")

        upcoming = cinema.parse_wonderful(
            f'<ul class="movie_list">{cards}</ul>',
            "soon",
            "https://wonderful.movie.com.tw/movie/index?type=upcoming",
        )
        self.assertTrue(all(movie["status"] == "soon" for movie in upcoming))

    def test_eslite_parser_reads_official_activity_release_dates(self):
        cards = "".join(
            f'''<div class="movie-card"><a href="/tw/tc/artshow/{index}">
              <img alt="{title}"></a><p>上映日期 | {release_date}</p></div>'''
            for index, (title, release_date) in enumerate([
                ("蜂蜜之夏 The Wonders", "2026年7月24日"),
                ("電影二", "2026/08/01"),
                ("電影三", "2026/08/02"),
                ("電影四", "2026/08/03"),
                ("電影五", "2026/08/04"),
            ])
        )
        movies = cinema.parse_eslite(cards, date(2026, 7, 31))
        self.assertEqual(movies[0]["title_zh"], "蜂蜜之夏 The Wonders")
        self.assertEqual(movies[0]["release_date_tw"], "2026-07-24")
        self.assertEqual(movies[0]["source"], "eslite")
        self.assertEqual(movies[0]["status"], "now")
        self.assertEqual(movies[1]["status"], "soon")

    def test_rerelease_requires_marker_or_earlier_tw_theatrical_date(self):
        movie = {"title_zh": "普通舊片", "release_date_tw": "2026-08-05"}
        self.assertFalse(cinema.is_confirmed_rerelease(movie, {}, []))
        self.assertTrue(cinema.is_confirmed_rerelease(movie, {}, [{"date": "2001-01-01"}]))
        self.assertFalse(cinema.is_confirmed_rerelease(movie, {}, [{"date": "2026-07-01"}]))
        self.assertFalse(cinema.is_confirmed_rerelease(movie, {"release_date": "1986-11-26"}, []))
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

    def test_missing_cinema_date_uses_recent_verified_tw_theatrical_date(self):
        releases = [{"date": "2018-11-03"}, {"date": "2026-08-21"}]
        self.assertEqual(
            weekly.infer_current_tmdb_theatrical_date(releases, date(2026, 8, 29)),
            "2026-08-21",
        )

    def test_missing_cinema_date_does_not_reuse_ancient_tmdb_date(self):
        self.assertEqual(
            weekly.infer_current_tmdb_theatrical_date(
                [{"date": "1995-11-18"}], date(2026, 8, 29)
            ),
            "",
        )

    def test_old_global_release_without_earlier_tw_date_is_not_rerelease(self):
        self.assertFalse(cinema.is_confirmed_rerelease(
            {"title_zh": "銀河寫手", "release_date_tw": "2026-08-28"},
            {"release_date": "2024-03-30"},
            [{"date": "2026-08-28"}],
        ))

    def test_look_back_animation_date_does_not_mark_live_action_as_rerelease(self):
        self.assertFalse(cinema.is_confirmed_rerelease(
            {"title_zh": "驀然回首(2024)", "release_date_tw": "2026-09-11"},
            {"id": 1591675, "release_date": "2026-09-11"},
            [{"date": "2026-09-11"}],
        ))


class RereleasePresenceTests(unittest.TestCase):
    def test_optional_art_house_failures_do_not_block_absence_audit(self):
        self.assertTrue(weekly.rerelease_absence_audit_complete({
            "atmovies": True, "showtime": True, "ambassador": True,
            "spot_taipei": False, "spot_huashan": False, "wonderful": False,
        }, True))

    def test_vieshow_403_does_not_block_complete_absence_audit(self):
        health = {
            "atmovies": True,
            "showtime": True,
            "ambassador": True,
            "vieshow": False,
            "spot_huashan": True,
            "wonderful": True,
            "eslite": True,
        }
        self.assertTrue(weekly.rerelease_absence_audit_complete(health, True))

    def test_required_source_or_tmdb_failure_blocks_absence_audit(self):
        health = {
            "atmovies": True,
            "showtime": False,
            "ambassador": True,
            "vieshow": False,
            "spot_huashan": True,
            "wonderful": True,
            "eslite": True,
        }
        self.assertFalse(weekly.rerelease_absence_audit_complete(health, True))
        health["showtime"] = True
        self.assertFalse(weekly.rerelease_absence_audit_complete(health, False))

    def test_eslite_failure_does_not_block_stable_source_absence_audit(self):
        health = {
            "atmovies": True,
            "showtime": True,
            "ambassador": True,
            "vieshow": False,
            "spot_huashan": True,
            "wonderful": True,
            "eslite": False,
        }
        self.assertTrue(weekly.rerelease_absence_audit_complete(health, True))

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

    def test_one_complete_absence_hides_and_same_date_does_not_double_count(self):
        first = publish.merge_rerelease_presence([], self.previous(), "2026-08-05", True)
        self.assertEqual(first[0]["consecutive_misses"], 1)
        self.assertTrue(first[0]["hidden"])
        same_date = publish.merge_rerelease_presence([], first, "2026-08-05", True)
        self.assertEqual(same_date[0]["consecutive_misses"], 1)
        self.assertTrue(same_date[0]["hidden"])

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
