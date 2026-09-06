import unittest

from scripts.generate_movie_pages import format_tmdb_score, rating_items, render_movie_page, slugify


class GenerateMoviePagesRatingTests(unittest.TestCase):
    def test_formats_tmdb_score_as_percentage(self):
        self.assertEqual(format_tmdb_score("7.2"), "72%")

    def test_rounds_tmdb_percentage_like_frontend(self):
        self.assertEqual(format_tmdb_score(7.25), "73%")

    def test_rating_items_only_formats_tmdb_value(self):
        self.assertEqual(
            rating_items(
                {"imdb": "8.1", "rt": "94%", "mc": "77"},
                {"voteAverage": "7.2"},
            ),
            [("IMDb", "8.1"), ("RT", "94%"), ("MT", "77"), ("TMDB", "72%")],
        )


class GenerateMoviePagesSlugTests(unittest.TestCase):
    def test_hero_uses_original_tmdb_backdrop_on_high_resolution_displays(self):
        page = render_movie_page({
            "id": 1,
            "titleZh": "測試電影",
            "releaseDate": "2026-08-30",
            "backdrop": "https://image.tmdb.org/t/p/w1280/example.jpg",
        }, "2026-08-30T00:00:00+08:00")

        self.assertIn("/original/example.jpg", page)
        self.assertIn("min-resolution: 1.5dppx", page)
        self.assertIn("/w1280/example.jpg", page)

    def test_hero_places_original_release_year_after_title(self):
        page = render_movie_page({
            "id": 23160,
            "titleZh": "鯨魚馬戲團",
            "titleEn": "Werckmeister harmóniák",
            "releaseYear": "2000",
            "releaseDate": "2026-09-05",
        }, "2026-09-06T00:00:00+08:00")

        self.assertIn(
            '<h1>鯨魚馬戲團<span class="production-year">（'
            '<span class="production-year-value">2000</span>）</span></h1>',
            page,
        )
        self.assertIn('<span class="original-title">Werckmeister harmóniák</span> · 2026/09/05', page)
        self.assertNotIn("台灣上映 2026/09/05", page)

    def test_poster_fallback_uses_original_tmdb_image_on_high_resolution_displays(self):
        page = render_movie_page({
            "id": 2,
            "titleZh": "只有直式海報的電影",
            "releaseDate": "2026-10-02",
            "poster": "https://image.tmdb.org/t/p/w500/poster.jpg",
            "backdrop": None,
        }, "2026-08-30T00:00:00+08:00")

        self.assertIn("/original/poster.jpg", page)
        self.assertIn("/w500/poster.jpg", page)

    def test_uses_english_title_when_available(self):
        self.assertEqual(
            slugify({"id": 1400940, "titleEn": "Clayface", "titleZh": "泥面人"}),
            "1400940-clayface",
        )

    def test_falls_back_when_original_title_has_no_ascii_slug(self):
        self.assertEqual(
            slugify({
                "id": 1701409,
                "titleEn": "ラブ≠コメディ",
                "titleZh": "LOVE ≠ COMEDY",
            }),
            "1701409-love-comedy",
        )

    def test_uses_movie_when_no_title_has_ascii_characters(self):
        self.assertEqual(
            slugify({"id": 1, "titleEn": "電影", "titleZh": "電影"}),
            "1-movie",
        )

    def test_ignores_single_latin_character_inside_cjk_title(self):
        self.assertEqual(
            slugify({
                "id": 1542261,
                "titleEn": "映畫ドラえもん 新・のび太の海底鬼巖城",
                "titleZh": "電影哆啦A夢：新‧大雄的海底鬼巖城",
            }),
            "1542261-movie",
        )

    def test_ignores_number_inside_non_latin_title(self):
        self.assertEqual(
            slugify({
                "id": 1264821,
                "titleEn": "Коты Эрмитажа 2. Тайна египетского зала",
                "titleZh": "喵喵博物館2：埃及寶藏",
            }),
            "1264821-movie",
        )


if __name__ == "__main__":
    unittest.main()
