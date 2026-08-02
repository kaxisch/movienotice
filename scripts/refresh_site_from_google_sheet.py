#!/usr/bin/env python3
"""Refresh public site data from private Google Sheet candidates and TMDB only."""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

import weekly_check as weekly
from publish_to_google_sheet import (
    CANDIDATES_SHEET_TITLE,
    load_service_account_credentials,
    quote_sheet_range,
)


ROOT_DIR = Path(__file__).resolve().parent.parent
MOVIE_DATA_FILE = ROOT_DIR / "data" / "movie-data.json"
MANUAL_RELEASES_FILE = ROOT_DIR / "data" / "manual-releases.json"
WHITELIST_FILE = ROOT_DIR / "data" / "tw-whitelist.json"
NOW_ATMOVIES_MISS_LIMIT = 2
SOON_ATMOVIES_MISS_LIMIT = 5


def log(message):
    print(message, file=sys.stderr)


def load_environment():
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(Path(__file__).resolve().parent / ".env")


def load_sheet_candidates():
    spreadsheet_id = os.environ.get("GOOGLE_SPREADSHEET_ID", "").strip()
    if not spreadsheet_id:
        raise RuntimeError("GOOGLE_SPREADSHEET_ID is required for TMDB-only refresh")

    credentials = load_service_account_credentials()
    from googleapiclient.discovery import build

    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    metadata = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties(title))",
    ).execute()
    titles = {
        sheet.get("properties", {}).get("title", "")
        for sheet in metadata.get("sheets", [])
    }
    if CANDIDATES_SHEET_TITLE not in titles:
        log(f"Google Sheet worksheet {CANDIDATES_SHEET_TITLE} does not exist yet; retaining current site IDs")
        return []
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=quote_sheet_range(CANDIDATES_SHEET_TITLE, "A:Z"),
    ).execute()
    values = response.get("values", [])
    if not values:
        raise RuntimeError(f"Google Sheet worksheet {CANDIDATES_SHEET_TITLE} is empty")

    headers = values[0]
    candidates = []
    for row in values[1:]:
        item = {headers[index]: value for index, value in enumerate(row) if index < len(headers)}
        try:
            item["tmdb_id"] = int(item.get("tmdb_id", ""))
        except (TypeError, ValueError):
            continue
        candidates.append(item)
    return candidates


def verified_signature(output):
    return {
        int(item["tmdb_id"]): item.get("tmdb_tw_release_date", "")
        for item in output.get("tmdb_has_tw_date", [])
        if item.get("tmdb_id") and item.get("tmdb_tw_release_date")
    }


def current_whitelist_signature():
    if not WHITELIST_FILE.exists():
        return {}
    with open(WHITELIST_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)
    dates = payload.get("tw_release_dates", {})
    return {
        int(tmdb_id): dates.get(str(tmdb_id), "")
        for tmdb_id in payload.get("tmdb_ids", [])
        if dates.get(str(tmdb_id), "")
    }


def load_current_whitelist_ids():
    return list(current_whitelist_signature())


def load_current_site_ids():
    return list(load_current_site_movies())


def load_current_site_movies():
    if not MOVIE_DATA_FILE.exists():
        return {}
    with open(MOVIE_DATA_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return {
        movie["id"]: movie
        for bucket in ("now", "soon")
        for movie in payload.get("movies", {}).get(bucket, [])
        if movie.get("id")
    }


def load_manual_ids():
    if not MANUAL_RELEASES_FILE.exists():
        return []
    with open(MANUAL_RELEASES_FILE, "r", encoding="utf-8") as f:
        return [item.get("tmdb_id") for item in json.load(f) if item.get("tmdb_id")]


def sheet_value_is_true(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def atmovies_miss_count(candidate):
    try:
        return max(0, int(candidate.get("consecutive_misses", 0) or 0))
    except (TypeError, ValueError):
        return 0


def should_hide_for_atmovies_absence(candidate, release_date, today, manual_ids):
    """對已進入開眼接手範圍的非人工電影套用連續缺席隱藏規則。"""
    tmdb_id = candidate.get("tmdb_id")
    if tmdb_id in manual_ids:
        return False
    if sheet_value_is_true(candidate.get("atmovies_present")):
        return False
    misses = atmovies_miss_count(candidate)
    limit = NOW_ATMOVIES_MISS_LIMIT if release_date <= today else SOON_ATMOVIES_MISS_LIMIT
    return misses >= limit


def build_verified_output(candidates):
    candidate_by_id = {item["tmdb_id"]: item for item in candidates}
    ordered_ids = list(candidate_by_id)

    today = datetime.now(timezone(timedelta(hours=8))).date()
    supplemental = weekly.fetch_supplemental_soon_candidates(today)
    log(f"Discovered {len(supplemental)} TMDB Taiwan theatrical candidates for days 61-180")
    for item in supplemental:
        tmdb_id = item.get("id")
        if tmdb_id and tmdb_id not in candidate_by_id:
            ordered_ids.append(tmdb_id)
            candidate_by_id[tmdb_id] = {"tmdb_id": tmdb_id}

    manual_ids = set(load_manual_ids())
    retained_ids = load_current_site_ids() + load_current_whitelist_ids() + list(manual_ids)
    for tmdb_id in retained_ids:
        if tmdb_id not in candidate_by_id:
            ordered_ids.append(tmdb_id)
            candidate_by_id[tmdb_id] = {"tmdb_id": tmdb_id}

    past_cutoff = today - timedelta(days=weekly.NOW_LOOKBACK_DAYS)
    future_cutoff = today + timedelta(days=weekly.SOON_WINDOW_DAYS)
    verified = []
    transient_failure_ids = set()

    for index, tmdb_id in enumerate(ordered_ids, 1):
        log(f"TMDB candidate [{index}/{len(ordered_ids)}] {tmdb_id}")
        movie = weekly.tmdb_movie(tmdb_id)
        if not movie:
            transient_failure_ids.add(tmdb_id)
            log(f"  Retaining previous TMDB {tmdb_id}: movie details could not be loaded")
            continue
        release_results = weekly.tmdb_release_dates(tmdb_id)
        if release_results is None:
            transient_failure_ids.add(tmdb_id)
            log(f"  Retaining previous TMDB {tmdb_id}: release_dates could not be loaded")
            continue
        theatrical_releases = weekly.extract_tw_theatrical_releases_from_results(release_results)
        eligible_releases = weekly.releases_in_window(theatrical_releases, past_cutoff, future_cutoff)
        if not eligible_releases:
            available_dates = ", ".join(item["date"] for item in theatrical_releases) or "none"
            log(
                f"  Excluded TMDB {tmdb_id}: no Taiwan theatrical type 3 date inside "
                f"{past_cutoff.isoformat()}..{future_cutoff.isoformat()} (available: {available_dates})"
            )
            continue
        tw_date = eligible_releases[0]["date"]
        release_date = weekly.parse_iso_date(tw_date)

        source = candidate_by_id[tmdb_id]
        if should_hide_for_atmovies_absence(source, release_date, today, manual_ids):
            log(
                f"  Hidden TMDB {tmdb_id}: absent from Atmovies for "
                f"{atmovies_miss_count(source)} consecutive successful audits"
            )
            continue
        verified.append({
            "tmdb_id": tmdb_id,
            "tmdb_url": weekly.tmdb_movie_url(tmdb_id),
            "tmdb_title": movie.get("title") or movie.get("original_title", ""),
            "tmdb_primary_release_date": movie.get("release_date", ""),
            "tmdb_release_year": (movie.get("release_date") or "")[:4],
            "tmdb_tw_release_date": tw_date,
            "tmdb_tw_release_dates": eligible_releases,
            "release_date_tw": tw_date,
            "title_zh": movie.get("title") or movie.get("original_title", ""),
            "title_en": movie.get("original_title", ""),
            "atmovies_id": source.get("atmovies_id", ""),
            "atmovies_url": source.get("atmovies_url", ""),
            "source_bucket": "now" if release_date <= today else "next",
        })
        time.sleep(weekly.TMDB_DELAY)

    generated_at = datetime.now(timezone(timedelta(hours=8)))
    return {
        "generated_at": generated_at.isoformat(),
        "source": "api.themoviedb.org",
        "summary": {"tmdb_has_tw_date": len(verified)},
        "tmdb_has_tw_date": verified,
        "missing_tw_date": [],
        "tmdb_not_found": [],
        "tmdb_date_mismatch": [],
        "tmdb_match_suspicious": [],
    }, generated_at, transient_failure_ids


def main():
    load_environment()
    candidates = load_sheet_candidates()
    log(f"Loaded {len(candidates)} candidates from Google Sheet")
    output, generated_at, transient_failure_ids = build_verified_output(candidates)
    if verified_signature(output) == current_whitelist_signature():
        log("No TMDB Taiwan theatrical date changes; refreshing full site metadata anyway")
    weekly.write_tw_whitelist(output)
    path, payload = weekly.export_static_movie_data(
        output,
        generated_at,
        previous_movies=load_current_site_movies(),
        transient_failure_ids=transient_failure_ids,
    )
    log(
        f"Wrote {path}: now={payload['summary']['now_count']} "
        f"soon={payload['summary']['soon_count']}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log(f"ERROR: {exc}")
        sys.exit(1)
