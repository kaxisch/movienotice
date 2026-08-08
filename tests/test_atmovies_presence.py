import sys
import unittest
from datetime import date
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts"))

import publish_to_google_sheet as publish
import refresh_site_from_google_sheet as refresh
import weekly_check as weekly


class CandidatePresenceTests(unittest.TestCase):
    def test_now_movie_without_atmovies_date_is_retained_for_tmdb_verification(self):
        html = """
        <article class="filmList">
          <div class="filmTitle"><a href="/movie/ften20391483/">外賣(4K數位紀念版) Take Out</a></div>
          <div class="runtime">片長：88分 上映廳數 (2)</div>
        </article>
        """

        movies = weekly.parse_now([html])

        self.assertEqual(len(movies), 1)
        self.assertEqual(movies[0]["atmovies_id"], "ften20391483")
        self.assertEqual(movies[0]["release_date_tw"], "")
        self.assertEqual(movies[0]["screen_count"], 2)

    def test_missing_candidates_increment_and_seen_candidates_reset(self):
        previous = [
            {"tmdb_id": "101", "title_zh": "仍在開眼", "atmovies_present": "FALSE", "consecutive_misses": "2"},
            {"tmdb_id": "202", "title_zh": "本次消失", "atmovies_present": "TRUE", "consecutive_misses": "0"},
        ]
        current = [
            {"tmdb_id": 101, "title_zh": "仍在開眼"},
            {"tmdb_id": 303, "title_zh": "新電影"},
        ]

        merged = publish.merge_candidate_presence(current, previous, "2026-07-18")
        by_id = {item["tmdb_id"]: item for item in merged}

        self.assertTrue(by_id[101]["atmovies_present"])
        self.assertEqual(by_id[101]["consecutive_misses"], 0)
        self.assertEqual(by_id[101]["last_seen_atmovies"], "2026-07-18")
        self.assertFalse(by_id[202]["atmovies_present"])
        self.assertEqual(by_id[202]["consecutive_misses"], 1)
        self.assertTrue(by_id[303]["ever_seen_atmovies"])

    def test_abnormally_small_audit_does_not_update_presence(self):
        previous = [
            {"tmdb_id": str(index), "atmovies_present": "TRUE"}
            for index in range(1, 21)
        ]
        current = [{"tmdb_id": index} for index in range(1, 10)]

        with self.assertRaises(RuntimeError):
            publish.merge_candidate_presence(current, previous, "2026-07-18")

    def test_same_date_rerun_does_not_increment_missing_count_twice(self):
        previous = [{
            "tmdb_id": "202",
            "ever_seen_atmovies": "TRUE",
            "atmovies_present": "FALSE",
            "consecutive_misses": "1",
            "last_audit_date": "2026-07-18",
        }]

        merged = publish.merge_candidate_presence([], previous, "2026-07-18")

        self.assertEqual(merged[0]["consecutive_misses"], 1)
        self.assertEqual(merged[0]["last_audit_date"], "2026-07-18")

    def test_next_successful_audit_date_increments_missing_count(self):
        previous = [{
            "tmdb_id": "202",
            "ever_seen_atmovies": "TRUE",
            "atmovies_present": "FALSE",
            "consecutive_misses": "1",
            "last_audit_date": "2026-07-18",
        }]

        merged = publish.merge_candidate_presence([], previous, "2026-07-22")

        self.assertEqual(merged[0]["consecutive_misses"], 2)
        self.assertEqual(merged[0]["last_audit_date"], "2026-07-22")

    def test_far_future_candidate_clears_old_misses(self):
        previous = [{
            "tmdb_id": "1437511",
            "tmdb_tw_release_date": "2026-11-13",
            "consecutive_misses": "8",
            "last_audit_date": "2026-08-02",
        }]

        merged = publish.merge_candidate_presence([], previous, "2026-08-06")

        self.assertEqual(merged[0]["consecutive_misses"], 0)
        self.assertEqual(merged[0]["handoff_started_at"], "pending")

    def test_first_audit_after_entering_sixty_days_starts_fresh(self):
        previous = [{
            "tmdb_id": "1437511",
            "tmdb_tw_release_date": "2026-11-13",
            "consecutive_misses": "8",
            "last_audit_date": "2026-09-08",
            "handoff_started_at": "pending",
        }]

        merged = publish.merge_candidate_presence([], previous, "2026-09-14")

        self.assertEqual(merged[0]["consecutive_misses"], 1)
        self.assertEqual(merged[0]["handoff_started_at"], "2026-09-14")

    def test_return_after_hide_starts_new_run(self):
        previous = [{
            "tmdb_id": "202",
            "tmdb_tw_release_date": "2026-02-06",
            "consecutive_misses": "2",
            "run_generation": "1",
            "run_started_at": "2026-02-06",
            "ever_published": "TRUE",
        }]
        current = [{"tmdb_id": 202, "tmdb_tw_release_date": "2026-02-06"}]

        merged = publish.merge_candidate_presence(current, previous, "2026-08-08")

        self.assertEqual(merged[0]["run_generation"], 2)
        self.assertEqual(merged[0]["run_started_at"], "2026-08-08")
        self.assertTrue(merged[0]["reappeared_after_hidden"])

    def test_current_site_movie_is_marked_as_ever_published(self):
        items = [{"tmdb_id": 101}, {"tmdb_id": 202, "ever_published": False}]
        payload = {"movies": {"now": [{"id": 202}], "soon": []}}

        marked = publish.mark_published_candidates(items, payload)

        self.assertNotIn("ever_published", marked[0])
        self.assertTrue(marked[1]["ever_published"])

    def test_candidate_rows_sort_by_release_date_with_missing_dates_last(self):
        items = [
            {"tmdb_id": 303, "release_date_tw": ""},
            {"tmdb_id": 202, "release_date_tw": "2026-08-01", "atmovies_present": False},
            {"tmdb_id": 101, "release_date_tw": "2026-07-25", "atmovies_present": True},
            {"tmdb_id": 102, "release_date_tw": "2026-07-25", "atmovies_present": False},
        ]

        rows = publish.candidate_items_to_rows(items)
        tmdb_id_index = publish.CANDIDATE_HEADERS.index("tmdb_id")

        self.assertEqual([row[tmdb_id_index] for row in rows[1:]], [101, 102, 202, 303])

    def test_only_unprotected_hidden_candidates_outside_retention_are_pruned(self):
        items = [
            {
                "tmdb_id": 101,
                "release_date_tw": "2025-12-30",
                "tmdb_tw_release_date": "2025-12-31",
                "ever_seen_atmovies": False,
                "atmovies_present": False,
                "consecutive_misses": 2,
            },
            {
                "tmdb_id": 202,
                "release_date_tw": "2025-12-30",
                "tmdb_tw_release_date": "2025-12-31",
                "ever_seen_atmovies": True,
                "atmovies_present": False,
                "consecutive_misses": 2,
            },
            {
                "tmdb_id": 303,
                "release_date_tw": "2026-06-30",
                "tmdb_tw_release_date": "2026-07-01",
                "ever_seen_atmovies": True,
                "atmovies_present": False,
                "consecutive_misses": 2,
            },
        ]

        retained = publish.prune_retired_candidates(
            items,
            "2026-08-02",
            published_ids={202},
            whitelist_ids=set(),
            manual_ids=set(),
        )

        self.assertEqual({item["tmdb_id"] for item in retained}, {202, 303})

    def test_candidate_without_reliable_release_date_is_never_pruned(self):
        item = {
            "tmdb_id": 101,
            "release_date_tw": "",
            "tmdb_tw_release_date": "",
            "ever_seen_atmovies": True,
            "atmovies_present": False,
            "consecutive_misses": 99,
        }

        retained = publish.prune_retired_candidates(
            [item], "2026-08-02", set(), set(), set()
        )

        self.assertEqual(retained, [item])

    def test_tmdb_discover_movie_is_seeded_when_it_enters_sixty_day_window(self):
        payload = {
            "movies": {
                "now": [],
                "soon": [{
                    "id": 404,
                    "titleZh": "交接電影",
                    "titleEn": "Handoff Movie",
                    "releaseDate": "2026-09-15",
                }],
            }
        }

        seeded = publish.seed_site_handoff_candidates([], payload, "2026-07-18", set())

        self.assertEqual(len(seeded), 1)
        self.assertEqual(seeded[0]["tmdb_id"], 404)
        self.assertFalse(seeded[0]["ever_seen_atmovies"])
        merged = publish.merge_candidate_presence([], seeded, "2026-07-18")
        self.assertEqual(merged[0]["consecutive_misses"], 1)
        self.assertFalse(merged[0]["ever_seen_atmovies"])

    def test_tmdb_discover_movie_over_sixty_days_away_is_not_seeded(self):
        payload = {
            "movies": {
                "now": [],
                "soon": [{
                    "id": 505,
                    "titleZh": "遠期電影",
                    "releaseDate": "2026-09-17",
                }],
            }
        }

        seeded = publish.seed_site_handoff_candidates([], payload, "2026-07-18", set())

        self.assertEqual(seeded, [])

    def test_existing_manual_movie_is_not_seeded_for_handoff(self):
        payload = {
            "movies": {
                "now": [{"id": 606, "titleZh": "人工保留", "releaseDate": "2026-07-17"}],
                "soon": [],
            }
        }

        seeded = publish.seed_site_handoff_candidates([], payload, "2026-07-18", {606})

        self.assertEqual(seeded, [])


class RefreshVisibilityTests(unittest.TestCase):
    TODAY = date(2026, 7, 18)

    def candidate(self, misses, present=False, ever_seen=True):
        return {
            "tmdb_id": 101,
            "ever_seen_atmovies": ever_seen,
            "atmovies_present": present,
            "consecutive_misses": misses,
        }

    def test_pending_rerelease_does_not_override_verified_atmovies_candidate(self):
        candidates = [
            {
                "tmdb_id": 45580,
                "candidate_kind": "atmovies",
                "tmdb_tw_release_date": "2026-07-31",
            },
            {
                "tmdb_id": 45580,
                "candidate_kind": "rerelease",
                "cinema_release_date": "",
            },
        ]

        indexed = refresh.index_candidates_by_tmdb_id(candidates)

        self.assertEqual(indexed[45580]["candidate_kind"], "atmovies")

    def test_dated_rerelease_overrides_regular_candidate(self):
        candidates = [
            {"tmdb_id": 101, "candidate_kind": "atmovies"},
            {
                "tmdb_id": 101,
                "candidate_kind": "rerelease",
                "cinema_release_date": "2026-08-07",
            },
        ]

        indexed = refresh.index_candidates_by_tmdb_id(candidates)

        self.assertEqual(indexed[101]["candidate_kind"], "rerelease")

    def test_verified_rerelease_is_not_filtered_as_streaming_only_without_atmovies_id(self):
        movie = {
            "releaseDate": "2026-07-24",
            "platforms": ["Some streaming platform"],
            "duration": 123,
        }
        record = {
            "candidate_kind": "rerelease",
            "source_bucket": "now",
            "atmovies_id": "",
        }

        self.assertTrue(weekly.should_keep_static_movie(movie, record))

    def test_now_movie_hides_on_second_miss(self):
        self.assertEqual(publish.NOW_ATMOVIES_MISS_LIMIT, refresh.NOW_ATMOVIES_MISS_LIMIT)
        release_date = date(2026, 7, 17)
        self.assertFalse(refresh.should_hide_for_atmovies_absence(self.candidate(1), release_date, self.TODAY, set()))
        self.assertTrue(refresh.should_hide_for_atmovies_absence(self.candidate(2), release_date, self.TODAY, set()))

    def test_soon_movie_hides_on_fifth_miss(self):
        self.assertEqual(publish.SOON_ATMOVIES_MISS_LIMIT, refresh.SOON_ATMOVIES_MISS_LIMIT)
        release_date = date(2026, 8, 7)
        self.assertFalse(refresh.should_hide_for_atmovies_absence(self.candidate(4), release_date, self.TODAY, set()))
        self.assertTrue(refresh.should_hide_for_atmovies_absence(self.candidate(5), release_date, self.TODAY, set()))

    def test_far_future_movie_ignores_old_misses(self):
        self.assertFalse(
            refresh.should_hide_for_atmovies_absence(
                self.candidate(8), date(2026, 11, 13), date(2026, 8, 6), set()
            )
        )

    def test_present_and_manual_movies_are_not_hidden(self):
        release_date = date(2026, 7, 17)
        self.assertFalse(refresh.should_hide_for_atmovies_absence(self.candidate(9, present=True), release_date, self.TODAY, set()))
        self.assertFalse(refresh.should_hide_for_atmovies_absence(self.candidate(9), release_date, self.TODAY, {101}))

    def test_published_continuous_run_can_exceed_180_days(self):
        candidate = self.candidate(0, present=True)
        candidate["ever_published"] = True
        release_date = date(2026, 1, 1)

        self.assertTrue(refresh.allows_continuous_theatrical_run(candidate, release_date, self.TODAY))
        self.assertEqual(
            weekly.classify_release_bucket(
                {"source_bucket": "now", "continuous_run": True},
                release_date,
                self.TODAY,
                True,
            ),
            "now",
        )

    def test_old_unpublished_candidate_cannot_use_old_tmdb_date(self):
        candidate = self.candidate(0, present=True)
        candidate["ever_published"] = False

        self.assertFalse(
            refresh.allows_continuous_theatrical_run(candidate, date(2015, 1, 9), self.TODAY)
        )

    def test_reappeared_hidden_movie_must_wait_for_rerelease_date(self):
        candidate = self.candidate(0, present=True)
        candidate.update({"ever_published": True, "reappeared_after_hidden": True})

        self.assertFalse(
            refresh.allows_continuous_theatrical_run(candidate, date(2026, 1, 1), self.TODAY)
        )

    def test_legacy_row_just_past_cutoff_can_be_migrated_once(self):
        candidate = self.candidate(0, present=True)
        candidate.pop("ever_published", None)

        self.assertTrue(
            refresh.allows_continuous_theatrical_run(candidate, date(2026, 1, 18), self.TODAY)
        )
        self.assertFalse(
            refresh.allows_continuous_theatrical_run(candidate, date(2025, 1, 1), self.TODAY)
        )

    def test_handed_off_tmdb_movie_hides_even_if_never_seen_atmovies(self):
        release_date = date(2026, 7, 17)
        self.assertTrue(
            refresh.should_hide_for_atmovies_absence(
                self.candidate(2, ever_seen=False), release_date, self.TODAY, set()
            )
        )

    def test_transient_tmdb_failure_retains_previously_verified_movie(self):
        movies = {"now": [], "soon": []}
        existing_ids = set()
        previous = {
            101: {
                "id": 101,
                "releaseDate": "2026-07-17",
                "twReleaseDateVerified": True,
            }
        }

        retained = weekly.retain_previous_static_movie(movies, existing_ids, previous, 101, self.TODAY)

        self.assertTrue(retained)
        self.assertEqual([movie["id"] for movie in movies["now"]], [101])

    def test_unverified_movie_is_not_retained_but_previous_long_run_is(self):
        movies = {"now": [], "soon": []}
        existing_ids = set()
        previous = {
            101: {"id": 101, "releaseDate": "2026-07-17", "twReleaseDateVerified": False},
            202: {"id": 202, "releaseDate": "2025-01-01", "twReleaseDateVerified": True},
        }

        self.assertFalse(weekly.retain_previous_static_movie(movies, existing_ids, previous, 101, self.TODAY))
        self.assertTrue(weekly.retain_previous_static_movie(movies, existing_ids, previous, 202, self.TODAY))


if __name__ == "__main__":
    unittest.main()
