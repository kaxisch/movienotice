import unittest

from scripts.generate_movie_pages import format_tmdb_score, rating_items


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


if __name__ == "__main__":
    unittest.main()
