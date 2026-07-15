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
        range=quote_sheet_range(CANDIDATES_SHEET_TITLE, "A:H"),
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
    if not MOVIE_DATA_FILE.exists():
        return []
    with open(MOVIE_DATA_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return [
        movie.get("id")
        for bucket in ("now", "soon")
        for movie in payload.get("movies", {}).get(bucket, [])
        if movie.get("id")
    ]


def load_manual_ids():
    if not MANUAL_RELEASES_FILE.exists():
        return []
    with open(MANUAL_RELEASES_FILE, "r", encoding="utf-8") as f:
        return [item.get("tmdb_id") for item in json.load(f) if item.get("tmdb_id")]


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

    retained_ids = load_current_site_ids() + load_current_whitelist_ids() + load_manual_ids()
    for tmdb_id in retained_ids:
        if tmdb_id not in candidate_by_id:
            ordered_ids.append(tmdb_id)
            candidate_by_id[tmdb_id] = {"tmdb_id": tmdb_id}

    past_cutoff = today - timedelta(days=weekly.NOW_LOOKBACK_DAYS)
    future_cutoff = today + timedelta(days=weekly.SOON_WINDOW_DAYS)
    verified = []

    for index, tmdb_id in enumerate(ordered_ids, 1):
        log(f"TMDB candidate [{index}/{len(ordered_ids)}] {tmdb_id}")
        movie = weekly.tmdb_movie(tmdb_id)
        if not movie:
            continue
        release_results = weekly.tmdb_release_dates(tmdb_id)
        tw_date = weekly.extract_tw_theatrical_date_from_results(release_results)
        release_date = weekly.parse_iso_date(tw_date)
        if not release_date or release_date < past_cutoff or release_date > future_cutoff:
            continue

        source = candidate_by_id[tmdb_id]
        verified.append({
            "tmdb_id": tmdb_id,
            "tmdb_url": weekly.tmdb_movie_url(tmdb_id),
            "tmdb_title": movie.get("title") or movie.get("original_title", ""),
            "tmdb_primary_release_date": movie.get("release_date", ""),
            "tmdb_release_year": (movie.get("release_date") or "")[:4],
            "tmdb_tw_release_date": tw_date,
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
    }, generated_at


def main():
    load_environment()
    candidates = load_sheet_candidates()
    log(f"Loaded {len(candidates)} candidates from Google Sheet")
    output, generated_at = build_verified_output(candidates)
    if verified_signature(output) == current_whitelist_signature():
        log("No TMDB Taiwan theatrical date changes; site refresh is not needed")
        return
    weekly.write_tw_whitelist(output)
    path, payload = weekly.export_static_movie_data(output, generated_at)
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
