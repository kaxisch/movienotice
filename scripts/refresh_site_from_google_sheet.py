#!/usr/bin/env python3
"""Refresh public site data from private Google Sheet candidates and TMDB only."""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from candidate_policy import (
    ATMOVIES_HANDOFF_DAYS,
    LEGACY_NOW_ATMOVIES_MISS_LIMIT,
    LEGACY_SOON_ATMOVIES_MISS_LIMIT,
    NOW_ATMOVIES_MISS_LIMIT,
    SOON_ATMOVIES_MISS_LIMIT,
    allows_continuous_theatrical_run,
    candidate_priority as shared_candidate_priority,
    nonnegative_miss_count,
    rerelease_can_override_regular,
    rerelease_is_hidden,
    sheet_value_is_true as shared_sheet_value_is_true,
    should_hide_for_absence,
)

import weekly_check as weekly
from publish_to_google_sheet import (
    CANDIDATES_SHEET_TITLE,
    RERELEASES_SHEET_TITLE,
    load_service_account_credentials,
    quote_sheet_range,
)


ROOT_DIR = Path(__file__).resolve().parent.parent
MOVIE_DATA_FILE = ROOT_DIR / "data" / "movie-data.json"
MANUAL_RELEASES_FILE = ROOT_DIR / "data" / "manual-releases.json"
WHITELIST_FILE = ROOT_DIR / "data" / "tw-whitelist.json"
GOOGLE_SHEETS_RETRY_ATTEMPTS = 4
GOOGLE_SHEETS_RETRY_DELAY = 2
GOOGLE_SHEETS_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


def log(message):
    print(message, file=sys.stderr)


def load_environment():
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(Path(__file__).resolve().parent / ".env")


def is_transient_google_sheets_error(error):
    status = getattr(getattr(error, "resp", None), "status", None)
    return status in GOOGLE_SHEETS_TRANSIENT_STATUS_CODES or isinstance(
        error, (TimeoutError, ConnectionError, OSError)
    )


def execute_google_sheets_request(request, operation):
    """重試 Google Sheets 的暫時性限流、服務異常與連線錯誤。"""
    for attempt in range(1, GOOGLE_SHEETS_RETRY_ATTEMPTS + 1):
        try:
            return request.execute()
        except Exception as error:
            if not is_transient_google_sheets_error(error) or attempt >= GOOGLE_SHEETS_RETRY_ATTEMPTS:
                raise
            delay = GOOGLE_SHEETS_RETRY_DELAY * (2 ** (attempt - 1))
            log(
                f"Google Sheets temporary failure during {operation}; "
                f"retry {attempt}/{GOOGLE_SHEETS_RETRY_ATTEMPTS - 1} in {delay}s: {error}"
            )
            time.sleep(delay)


def load_sheet_candidates():
    spreadsheet_id = os.environ.get("GOOGLE_SPREADSHEET_ID", "").strip()
    if not spreadsheet_id:
        raise RuntimeError("GOOGLE_SPREADSHEET_ID is required for TMDB-only refresh")

    credentials = load_service_account_credentials()
    from googleapiclient.discovery import build

    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    metadata = execute_google_sheets_request(service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties(title))",
    ), "spreadsheet metadata read")
    titles = {
        sheet.get("properties", {}).get("title", "")
        for sheet in metadata.get("sheets", [])
    }
    if CANDIDATES_SHEET_TITLE not in titles:
        log(f"Google Sheet worksheet {CANDIDATES_SHEET_TITLE} does not exist yet; retaining current site IDs")
        candidates = []
    else:
        candidates = load_candidate_worksheet(service, spreadsheet_id, CANDIDATES_SHEET_TITLE, "atmovies")
    if RERELEASES_SHEET_TITLE in titles:
        candidates.extend(
            load_candidate_worksheet(service, spreadsheet_id, RERELEASES_SHEET_TITLE, "rerelease")
        )
    return candidates


def classify_rerelease_candidate(item):
    """重映證據不足時仍保留為一般院線候選，但不加重映標籤。"""
    if not shared_sheet_value_is_true(item.get("rerelease_present")):
        return "rerelease_history"
    if shared_sheet_value_is_true(item.get("rerelease_verified")):
        return "rerelease"
    return "cinema"


def load_candidate_worksheet(service, spreadsheet_id, title, candidate_kind):
    response = execute_google_sheets_request(service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=quote_sheet_range(title, "A:Z"),
    ), f"worksheet {title} read")
    values = response.get("values", [])
    if not values:
        raise RuntimeError(f"Google Sheet worksheet {title} is empty")
    headers = values[0]
    candidates = []
    for row in values[1:]:
        item = {headers[index]: value for index, value in enumerate(row) if index < len(headers)}
        try:
            item["tmdb_id"] = int(item.get("tmdb_id", ""))
        except (TypeError, ValueError):
            continue
        if candidate_kind == "rerelease":
            item["candidate_kind"] = classify_rerelease_candidate(item)
        else:
            item["candidate_kind"] = candidate_kind
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
    return shared_sheet_value_is_true(value)


def atmovies_miss_count(candidate):
    return nonnegative_miss_count(candidate)


def should_hide_for_atmovies_absence(candidate, release_date, today, manual_ids):
    """對已進入院線稽核範圍的非人工電影套用全來源缺席隱藏規則。"""
    return should_hide_for_absence(candidate, release_date, today, manual_ids)


def should_hide_rerelease(candidate):
    return rerelease_is_hidden(candidate)


def should_hold_tmdb_only_near_term_candidate(
    tmdb_id, release_date, today, sheet_candidate_ids, manual_ids
):
    """0～60 天內只有 TMDB 日期、尚無院線候選狀態的電影不得先公開。"""
    if not release_date or tmdb_id in sheet_candidate_ids or tmdb_id in manual_ids:
        return False
    return today <= release_date <= today + timedelta(days=ATMOVIES_HANDOFF_DAYS)


def rerelease_can_override_regular_candidate(candidate):
    """Only a currently visible, date-verified rerelease may replace a regular candidate."""
    return rerelease_can_override_regular(candidate)


def index_candidates_by_tmdb_id(candidates):
    """同片重複時，只有已驗證且未隱藏的重映候選可蓋掉一般候選。"""
    indexed = {}
    for candidate in candidates:
        if candidate.get("candidate_kind") == "rerelease_history":
            continue
        if (
            candidate.get("candidate_kind") == "rerelease"
            and not rerelease_can_override_regular_candidate(candidate)
        ):
            continue
        tmdb_id = candidate["tmdb_id"]
        previous = indexed.get(tmdb_id)
        if previous is None:
            indexed[tmdb_id] = candidate
            continue
        current_priority = shared_candidate_priority(candidate)
        previous_priority = shared_candidate_priority(previous)
        if current_priority > previous_priority:
            indexed[tmdb_id] = candidate
    return indexed


def build_verified_output(candidates):
    candidate_by_id = index_candidates_by_tmdb_id(candidates)
    sheet_candidate_ids = set(candidate_by_id)
    ordered_ids = list(candidate_by_id)

    today = datetime.now(timezone(timedelta(hours=8))).date()
    supplemental = weekly.fetch_supplemental_soon_candidates(today)
    log(f"Discovered {len(supplemental)} TMDB Taiwan theatrical candidates for days 0-180")
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
        source = candidate_by_id[tmdb_id]
        source_date = weekly.parse_iso_date(source.get("tmdb_tw_release_date", ""))
        continuous_run = bool(
            source_date and allows_continuous_theatrical_run(source, source_date, today)
        )
        if not eligible_releases and continuous_run:
            eligible_releases = [
                item for item in theatrical_releases
                if item.get("date") == source_date.isoformat()
            ]
        if not eligible_releases:
            available_dates = ", ".join(item["date"] for item in theatrical_releases) or "none"
            log(
                f"  Excluded TMDB {tmdb_id}: no Taiwan cinema release type 1, 2, or 3 date inside "
                f"{past_cutoff.isoformat()}..{future_cutoff.isoformat()} (available: {available_dates})"
            )
            continue
        if source.get("candidate_kind") in {"rerelease", "cinema"}:
            cinema_date = str(source.get("cinema_release_date", "") or "")
            exact_releases = [item for item in eligible_releases if item.get("date") == cinema_date]
            if not exact_releases:
                log(
                    f"  Excluded cinema candidate TMDB {tmdb_id}: TW cinema release type 1, 2, or 3 "
                    f"does not match cinema date {cinema_date}"
                )
                continue
            selected_releases = exact_releases
            if source.get("candidate_kind") == "rerelease" and should_hide_rerelease(source):
                log(f"  Hidden rerelease TMDB {tmdb_id}: absent from all required sources in one complete audit")
                continue
            tw_date = cinema_date
        else:
            selected_releases = weekly.select_public_tw_theatrical_releases(tmdb_id, eligible_releases)
            tw_date = selected_releases[0]["date"]
        release_date = weekly.parse_iso_date(tw_date)

        if should_hold_tmdb_only_near_term_candidate(
            tmdb_id, release_date, today, sheet_candidate_ids, manual_ids
        ):
            log(
                f"  Held TMDB-only candidate {tmdb_id}: Taiwan cinema date {tw_date} is "
                "within days 0-60 but no cinema audit candidate exists"
            )
            continue

        if source.get("candidate_kind") != "rerelease" and should_hide_for_atmovies_absence(
            source, release_date, today, manual_ids
        ):
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
            "tmdb_tw_release_dates": selected_releases,
            "release_date_tw": tw_date,
            "title_zh": movie.get("title") or movie.get("original_title", ""),
            "title_en": movie.get("original_title", ""),
            "atmovies_id": source.get("atmovies_id", ""),
            "atmovies_url": source.get("atmovies_url", ""),
            "candidate_kind": source.get("candidate_kind", ""),
            "source_bucket": "now" if release_date <= today else "next",
            "continuous_run": continuous_run,
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
