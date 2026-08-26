import unittest

from scripts.weekly_check import split_atmovies_title


class AtmoviesTitleTests(unittest.TestCase):
    def test_keeps_all_english_vr_concert_title_intact(self):
        title = "TOMORROW X TOGETHER VR CONCERT : ENDLESS RIDE"

        self.assertEqual(split_atmovies_title(title), (title, ""))

    def test_keeps_all_english_nct_title_intact(self):
        title = "NCT 127 5TH TOUR ‘NEO CITY SEOUL - THE REDLINE’ in CINEMAS"

        self.assertEqual(split_atmovies_title(title), (title, ""))

    def test_still_splits_chinese_and_english_titles(self):
        self.assertEqual(
            split_atmovies_title("大風殺 The Trapped"),
            ("大風殺", "The Trapped"),
        )

    def test_preserves_mixed_chinese_title_prefix(self):
        self.assertEqual(
            split_atmovies_title("哆啦A夢 STAND BY ME Doraemon"),
            ("哆啦A夢", "STAND BY ME Doraemon"),
        )


if __name__ == "__main__":
    unittest.main()
