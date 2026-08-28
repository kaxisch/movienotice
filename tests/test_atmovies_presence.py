import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts"))

import publish_to_google_sheet as publish
import refresh_site_from_google_sheet as refresh
import weekly_check as weekly


class CandidatePresenceTests(unittest.TestCase):
    def test_taiwan_title_override_replaces_japanese_shell_character(self):
        self.assertEqual(
            weekly.tmdb_title_override(9323),
            "攻殼機動隊 / GHOST IN THE SHELL",
        )
        self.assertNotIn("殻", weekly.tmdb_title_override(9323))

    def test_tmdb_tw_cinema_release_accepts_premiere_limited_and_theatrical(self):
        releases = weekly.extract_tw_theatrical_releases_from_results([
            {
                "iso_3166_1": "TW",
                "release_dates": [
                    {"type": 1, "release_date": "2026-09-01T00:00:00.000Z", "iso_639_1": "zh"},
                    {"type": 2, "release_date": "2026-09-02T00:00:00.000Z", "iso_639_1": "zh"},
                    {"type": 3, "release_date": "2026-09-03T00:00:00.000Z", "iso_639_1": "zh"},
                ],
            }
        ])

        self.assertEqual(
            [item["date"] for item in releases],
            ["2026-09-01", "2026-09-02", "2026-09-03"],
        )

    def test_tmdb_tw_cinema_release_rejects_home_and_non_taiwan_dates(self):
        releases = weekly.extract_tw_theatrical_releases_from_results([
            {
                "iso_3166_1": "TW",
                "release_dates": [
                    {"type": 4, "release_date": "2026-09-04T00:00:00.000Z"},
                    {"type": 5, "release_date": "2026-09-05T00:00:00.000Z"},
                    {"type": 6, "release_date": "2026-09-06T00:00:00.000Z"},
                ],
            },
            {
                "iso_3166_1": "US",
                "release_dates": [
                    {"type": 1, "release_date": "2026-09-01T00:00:00.000Z"},
                    {"type": 2, "release_date": "2026-09-02T00:00:00.000Z"},
                    {"type": 3, "release_date": "2026-09-03T00:00:00.000Z"},
                ],
            },
        ])

        self.assertEqual(releases, [])

    @patch.object(weekly, "tmdb_discover", return_value=[])
    def test_far_future_discover_uses_all_cinema_release_types(self, tmdb_discover):
        weekly.fetch_supplemental_soon_candidates(date(2026, 8, 19))

        params = tmdb_discover.call_args.args[1]
        self.assertEqual(params["region"], "TW")
        self.assertEqual(params["with_release_type"], "1|2|3")

    def test_public_release_selection_keeps_only_latest_date(self):
        releases = [
            {"date": "2026-06-26", "language": ""},
            {"date": "2026-08-16", "language": ""},
            {"date": "2026-09-04", "language": ""},
        ]

        self.assertEqual(
            weekly.select_public_tw_theatrical_releases(1193673, releases),
            [{"date": "2026-09-04", "language": ""}],
        )

    def test_chiikawa_keeps_japanese_and_chinese_release_dates(self):
        releases = [
            {"date": "2026-07-31", "language": "ja"},
            {"date": "2026-08-07", "language": "zh"},
        ]

        self.assertEqual(
            weekly.select_public_tw_theatrical_releases(1586876, releases),
            releases,
        )

    def test_transient_tmdb_failure_normalizes_previous_movie_to_latest_date(self):
        previous = {
            101: {
                "id": 101,
                "releaseDate": "2026-08-16",
                "twReleaseDateVerified": True,
                "twTheatricalReleases": [
                    {"date": "2026-08-16", "language": ""},
                    {"date": "2026-09-04", "language": ""},
                ],
            }
        }
        movies = {"now": [], "soon": []}

        retained = weekly.retain_previous_static_movie(
            movies,
            set(),
            previous,
            101,
            date(2026, 8, 19),
        )

        self.assertTrue(retained)
        self.assertEqual(movies["soon"][0]["releaseDate"], "2026-09-04")
        self.assertEqual(
            movies["soon"][0]["twTheatricalReleases"],
            [{"date": "2026-09-04", "language": ""}],
        )

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

    def test_short_movie_with_atmovies_cinema_evidence_is_kept(self):
        movie = {"releaseDate": "2026-08-21", "duration": 45, "platforms": []}
        record = {
            "source_bucket": "now",
            "candidate_kind": "atmovies",
            "atmovies_id": "ftko99799079",
        }

        self.assertTrue(weekly.should_keep_static_movie(movie, record))

    def test_short_tmdb_only_discovery_without_cinema_evidence_is_excluded(self):
        movie = {"releaseDate": "2026-11-01", "duration": 45, "platforms": []}
        record = {"source_bucket": "next", "candidate_kind": ""}

        self.assertFalse(weekly.should_keep_static_movie(movie, record))

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

    def test_corrected_tmdb_match_replaces_old_candidate_for_same_atmovies_id(self):
        previous = [
            {
                "tmdb_id": "1700944",
                "title_zh": "LOVE ≠",
                "atmovies_id": "fjjp43653895",
                "ever_seen_atmovies": "TRUE",
                "atmovies_present": "TRUE",
            },
            {
                "tmdb_id": "1701409",
                "title_zh": "LOVE ≠ COMEDY",
                "atmovies_id": "fjjp43653895",
                "ever_published": "TRUE",
                "atmovies_present": "FALSE",
            },
        ]
        current = [{
            "tmdb_id": 1701409,
            "title_zh": "LOVE ≠ COMEDY",
            "title_en": "Love Not Comedy",
            "atmovies_id": "fjjp43653895",
        }]

        merged = publish.merge_candidate_presence(current, previous, "2026-08-29")

        self.assertEqual([item["tmdb_id"] for item in merged], [1701409])
        self.assertEqual(merged[0]["title_zh"], "LOVE ≠ COMEDY")
        self.assertTrue(merged[0]["atmovies_present"])
        self.assertTrue(merged[0]["ever_published"])

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

    def test_incomplete_cross_cinema_audit_does_not_increment_missing_count(self):
        previous = [{
            "tmdb_id": "202",
            "atmovies_present": "FALSE",
            "consecutive_misses": "0",
            "last_audit_date": "2026-07-18",
        }]

        merged = publish.merge_candidate_presence(
            [], previous, "2026-07-22", audit_complete=False
        )

        self.assertEqual(merged[0]["consecutive_misses"], 0)
        self.assertEqual(merged[0]["last_audit_date"], "2026-07-18")
        self.assertFalse(merged[0]["absence_audit_complete"])

    def test_incomplete_audit_does_not_resurrect_candidate_hidden_by_complete_audit(self):
        previous = [{
            "tmdb_id": "202",
            "tmdb_tw_release_date": "2026-07-17",
            "atmovies_present": "FALSE",
            "cinema_present": "FALSE",
            "consecutive_misses": "1",
            "last_audit_date": "2026-07-18",
            "absence_audit_complete": "TRUE",
        }]

        merged = publish.merge_candidate_presence(
            [], previous, "2026-07-22", audit_complete=False
        )

        self.assertEqual(merged[0]["consecutive_misses"], 1)
        self.assertTrue(merged[0]["absence_audit_complete"])
        self.assertTrue(
            refresh.should_hide_for_atmovies_absence(
                merged[0], date(2026, 7, 17), date(2026, 7, 22), set()
            )
        )

    def test_other_cinema_presence_resets_absence_without_atmovies(self):
        previous = [{
            "tmdb_id": "202",
            "atmovies_present": "FALSE",
            "consecutive_misses": "1",
            "last_audit_date": "2026-07-18",
        }]

        merged = publish.merge_candidate_presence(
            [], previous, "2026-07-22", {"202": ["showtime"]}, True
        )

        self.assertFalse(merged[0]["atmovies_present"])
        self.assertTrue(merged[0]["cinema_present"])
        self.assertEqual(merged[0]["present_sources"], "showtime")
        self.assertEqual(merged[0]["consecutive_misses"], 0)

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

    def test_confirmed_dated_rerelease_overrides_regular_candidate(self):
        candidates = [
            {"tmdb_id": 101, "candidate_kind": "atmovies"},
            {
                "tmdb_id": 101,
                "candidate_kind": "rerelease",
                "cinema_release_date": "2026-08-07",
                "tmdb_tw_release_date": "2026-08-07",
                "tmdb_date_status": "confirmed",
                "hidden": False,
            },
        ]

        indexed = refresh.index_candidates_by_tmdb_id(candidates)

        self.assertEqual(indexed[101]["candidate_kind"], "rerelease")

    def test_hidden_unverified_rerelease_does_not_override_present_regular_candidate(self):
        candidates = [
            {
                "tmdb_id": 1621964,
                "candidate_kind": "atmovies",
                "tmdb_tw_release_date": "2026-09-04",
                "atmovies_present": True,
                "consecutive_misses": 0,
            },
            {
                "tmdb_id": 1621964,
                "candidate_kind": "rerelease",
                "cinema_release_date": "2026-09-04",
                "tmdb_tw_release_date": "",
                "tmdb_date_status": "missing",
                "rerelease_present": False,
                "hidden": True,
            },
        ]

        indexed = refresh.index_candidates_by_tmdb_id(candidates)

        self.assertEqual(indexed[1621964]["candidate_kind"], "atmovies")

    def test_mismatched_rerelease_date_does_not_override_regular_candidate(self):
        candidates = [
            {"tmdb_id": 101, "candidate_kind": "atmovies"},
            {
                "tmdb_id": 101,
                "candidate_kind": "rerelease",
                "cinema_release_date": "2026-08-07",
                "tmdb_tw_release_date": "2026-08-14",
                "tmdb_date_status": "mismatch",
                "hidden": False,
            },
        ]

        indexed = refresh.index_candidates_by_tmdb_id(candidates)

        self.assertEqual(indexed[101]["candidate_kind"], "atmovies")

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

    @patch.object(refresh.time, "sleep")
    @patch.object(refresh, "load_current_whitelist_ids", return_value=[])
    @patch.object(refresh, "load_current_site_ids", return_value=[])
    @patch.object(refresh, "load_manual_ids", return_value=[])
    @patch.object(weekly, "fetch_supplemental_soon_candidates", return_value=[])
    def test_rerelease_outputs_only_release_records_matching_the_cinema_date(
        self,
        _supplemental,
        _manual_ids,
        _site_ids,
        _whitelist_ids,
        _sleep,
    ):
        today = datetime.now(timezone(timedelta(hours=8))).date()
        premiere_date = (today + timedelta(days=1)).isoformat()
        cinema_date = (today + timedelta(days=2)).isoformat()
        candidate = {
            "tmdb_id": 101,
            "candidate_kind": "rerelease",
            "cinema_release_date": cinema_date,
        }
        release_results = [{
            "iso_3166_1": "TW",
            "release_dates": [
                {"type": 1, "release_date": f"{premiere_date}T00:00:00.000Z"},
                {"type": 2, "release_date": f"{cinema_date}T00:00:00.000Z"},
            ],
        }]

        with patch.object(weekly, "tmdb_movie", return_value={
            "id": 101,
            "title": "測試重映片",
            "original_title": "Test Rerelease",
            "release_date": "2000-01-01",
        }), patch.object(weekly, "tmdb_release_dates", return_value=release_results):
            output, _, _ = refresh.build_verified_output([candidate])

        record = output["tmdb_has_tw_date"][0]
        self.assertEqual(record["tmdb_tw_release_date"], cinema_date)
        self.assertEqual(record["tmdb_tw_release_dates"], [{"date": cinema_date, "language": ""}])

    def test_now_movie_hides_after_one_complete_all_source_absence(self):
        self.assertEqual(publish.NOW_ATMOVIES_MISS_LIMIT, refresh.NOW_ATMOVIES_MISS_LIMIT)
        release_date = date(2026, 7, 17)
        candidate = self.candidate(1)
        candidate["absence_audit_complete"] = True
        self.assertTrue(refresh.should_hide_for_atmovies_absence(candidate, release_date, self.TODAY, set()))

    def test_soon_movie_hides_after_one_complete_all_source_absence(self):
        self.assertEqual(publish.SOON_ATMOVIES_MISS_LIMIT, refresh.SOON_ATMOVIES_MISS_LIMIT)
        release_date = date(2026, 8, 7)
        candidate = self.candidate(1)
        candidate["absence_audit_complete"] = True
        self.assertTrue(refresh.should_hide_for_atmovies_absence(candidate, release_date, self.TODAY, set()))

    def test_incomplete_audit_or_other_cinema_presence_does_not_hide(self):
        release_date = date(2026, 7, 17)
        incomplete = self.candidate(1)
        self.assertFalse(refresh.should_hide_for_atmovies_absence(incomplete, release_date, self.TODAY, set()))
        present = self.candidate(1)
        present.update({"absence_audit_complete": True, "cinema_present": True})
        self.assertFalse(refresh.should_hide_for_atmovies_absence(present, release_date, self.TODAY, set()))

    def test_legacy_hidden_candidates_stay_hidden_without_new_audit_column(self):
        now_date = date(2026, 7, 17)
        soon_date = date(2026, 8, 7)
        self.assertFalse(
            refresh.should_hide_for_atmovies_absence(
                self.candidate(1), now_date, self.TODAY, set()
            )
        )
        self.assertTrue(
            refresh.should_hide_for_atmovies_absence(
                self.candidate(2), now_date, self.TODAY, set()
            )
        )
        self.assertFalse(
            refresh.should_hide_for_atmovies_absence(
                self.candidate(4), soon_date, self.TODAY, set()
            )
        )
        self.assertTrue(
            refresh.should_hide_for_atmovies_absence(
                self.candidate(5), soon_date, self.TODAY, set()
            )
        )

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
                {**self.candidate(1, ever_seen=False), "absence_audit_complete": True},
                release_date, self.TODAY, set()
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
