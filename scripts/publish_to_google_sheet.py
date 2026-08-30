#!/usr/bin/env python3
"""
Publish a MovieNotice TSV export to Google Sheets.

Each run writes one worksheet named by run date, e.g. 2026-07-11.
If that worksheet already exists, its contents are replaced.
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from candidate_policy import (
    ATMOVIES_HANDOFF_DAYS,
    CANDIDATE_RETENTION_DAYS,
    LEGACY_NOW_ATMOVIES_MISS_LIMIT,
    LEGACY_SOON_ATMOVIES_MISS_LIMIT,
    NOW_ATMOVIES_MISS_LIMIT,
    RERELEASE_MISS_LIMIT,
    SOON_ATMOVIES_MISS_LIMIT,
    candidate_handoff_phase,
    candidate_miss_limit,
    sheet_value_is_true,
)


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
CANDIDATES_FILE = DATA_DIR / "atmovies-candidates.json"
RERELEASE_CANDIDATES_FILE = DATA_DIR / "rerelease-candidates.json"
MOVIE_DATA_FILE = DATA_DIR / "movie-data.json"
WHITELIST_FILE = DATA_DIR / "tw-whitelist.json"
MANUAL_RELEASES_FILE = DATA_DIR / "manual-releases.json"
CANDIDATES_SHEET_TITLE = "_candidates"
RERELEASES_SHEET_TITLE = "_rereleases"
AUDIT_STATUS_SHEET_TITLE = "_audit_status"
CANDIDATE_HEADERS = [
    "tmdb_id", "source_bucket", "title_zh", "title_en",
    "release_date_tw", "tmdb_tw_release_date", "atmovies_id", "atmovies_url", "tmdb_title",
    "ever_seen_atmovies", "atmovies_present", "consecutive_misses", "last_seen_atmovies",
    "last_audit_date", "ever_published", "run_generation", "run_started_at",
    "reappeared_after_hidden", "handoff_started_at", "cinema_present",
    "present_sources", "absence_audit_complete",
]
RERELEASE_HEADERS = [
    "tmdb_id", "title_zh", "title_en", "cinema_release_date", "atmovies_original_date", "tmdb_tw_release_date",
    "tmdb_url", "tmdb_primary_release_date", "present_sources", "source_urls", "cinema_status",
    "tmdb_date_status", "rerelease_verified", "rerelease_present", "consecutive_misses", "hidden",
    "first_seen", "last_seen", "last_audit_date",
]
AUDIT_STATUS_HEADERS = ["audit_date", "completed_at", "audit_complete"]
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]
SPREADSHEET_MIME_TYPE = "application/vnd.google-apps.spreadsheet"
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
DEFAULT_FOLDER_NAME = "tw movie"
DEFAULT_SPREADSHEET_NAME = "movienotice_weekly"


def log(message):
    print(message, file=sys.stderr)


def load_environment():
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(Path(__file__).resolve().parent / ".env")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Publish a MovieNotice TSV file to a dated Google Sheets worksheet."
    )
    parser.add_argument(
        "tsv_path",
        nargs="?",
        help="Path to TSV file. Defaults to data/YYYY-MM-DD.tsv for today's Taipei date.",
    )
    parser.add_argument(
        "--run-date",
        help="Worksheet date in YYYY-MM-DD format. Defaults to the TSV filename stem, then today in Taipei.",
    )
    parser.add_argument(
        "--spreadsheet-name",
        default=os.environ.get("GOOGLE_SPREADSHEET_NAME", DEFAULT_SPREADSHEET_NAME),
        help=f"Google Sheet file name. Default: {DEFAULT_SPREADSHEET_NAME}",
    )
    parser.add_argument(
        "--spreadsheet-id",
        default=os.environ.get("GOOGLE_SPREADSHEET_ID", ""),
        help="Existing Google Spreadsheet id. Preferred because the file stays owned by your Drive account.",
    )
    parser.add_argument(
        "--folder-id",
        default=os.environ.get("GOOGLE_DRIVE_FOLDER_ID", ""),
        help="Target Google Drive folder id. Preferred for automation.",
    )
    parser.add_argument(
        "--folder-name",
        default=os.environ.get("GOOGLE_DRIVE_FOLDER_NAME", DEFAULT_FOLDER_NAME),
        help=f"Target Google Drive folder name if no folder id is provided. Default: {DEFAULT_FOLDER_NAME}",
    )
    return parser.parse_args()


def today_taipei():
    return datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()


def infer_tsv_path(tsv_path, run_date):
    if tsv_path:
        return Path(tsv_path)
    target_date = run_date or today_taipei()
    return DATA_DIR / f"{target_date}.tsv"


def infer_run_date(tsv_path, explicit_run_date):
    if explicit_run_date:
        return normalize_sheet_date(explicit_run_date)
    try:
        return normalize_sheet_date(Path(tsv_path).stem)
    except ValueError:
        return today_taipei()


def normalize_sheet_date(value):
    value = (value or "").strip().replace("/", "-")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid run date '{value}'. Expected YYYY-MM-DD.") from exc


def load_tsv_rows(tsv_path):
    if not tsv_path.exists():
        raise FileNotFoundError(f"TSV file not found: {tsv_path}")

    with open(tsv_path, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))

    if not rows:
        raise ValueError(f"TSV file is empty: {tsv_path}")

    return rows


def load_candidate_items(path=CANDIDATES_FILE):
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return [item for item in payload.get("candidates", []) if item.get("tmdb_id")]


def load_rerelease_audit(path=RERELEASE_CANDIDATES_FILE):
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    payload["candidates"] = [item for item in payload.get("candidates", []) if item.get("tmdb_id")]
    return payload


def sheet_rows_to_items(values):
    if not values:
        return []
    headers = values[0]
    return [
        {headers[index]: value for index, value in enumerate(row) if index < len(headers)}
        for row in values[1:]
        if row
    ]


def is_sheet_true(value, default=False):
    return sheet_value_is_true(value, default=default)


def merge_candidate_presence(
    current_items, previous_items, run_date, cinema_presence=None, audit_complete=True,
    cinema_candidates=None,
):
    """合併本次跨院線候選；只有完整稽核確認全來源缺席才累加缺席。"""
    cinema_presence = {
        str(tmdb_id): sorted(set(sources))
        for tmdb_id, sources in (cinema_presence or {}).items()
    }
    cinema_candidates_by_id = {
        str(item["tmdb_id"]): dict(item)
        for item in (cinema_candidates or [])
        if item.get("tmdb_id")
    }
    current_by_id = {str(item["tmdb_id"]): dict(item) for item in current_items if item.get("tmdb_id")}
    current_id_by_atmovies = {
        str(item.get("atmovies_id", "")).strip(): str(item["tmdb_id"])
        for item in current_items
        if item.get("tmdb_id") and str(item.get("atmovies_id", "")).strip()
    }
    previous_by_id = {}
    migrated_previous = {}
    for item in previous_items:
        if not item.get("tmdb_id"):
            continue
        tmdb_id = str(item["tmdb_id"])
        atmovies_id = str(item.get("atmovies_id", "")).strip()
        current_tmdb_id = current_id_by_atmovies.get(atmovies_id)
        if current_tmdb_id and current_tmdb_id != tmdb_id:
            migrated_previous.setdefault(current_tmdb_id, dict(item))
            continue
        previous_by_id[tmdb_id] = dict(item)
    for tmdb_id, item in migrated_previous.items():
        previous_by_id.setdefault(tmdb_id, item)

    previous_present_count = sum(
        1 for item in previous_by_id.values()
        if is_sheet_true(item.get("atmovies_present"), default=True)
    )
    if previous_present_count >= 20 and len(current_by_id) < previous_present_count * 0.5:
        raise RuntimeError(
            f"Current Atmovies candidate count {len(current_by_id)} is below 50% "
            f"of previous present count {previous_present_count}; presence state was not updated"
        )

    merged = []
    all_ids = set(previous_by_id) | set(current_by_id) | set(cinema_candidates_by_id)
    for tmdb_id in sorted(all_ids, key=lambda value: int(value)):
        previous = previous_by_id.get(tmdb_id, {})
        current = current_by_id.get(tmdb_id)
        cinema_sources = cinema_presence.get(tmdb_id, [])
        handoff_phase = candidate_handoff_phase(current or previous, run_date)
        previous_handoff = str(previous.get("handoff_started_at", "") or "").strip()
        if current:
            item = {**previous, **current}
            miss_limit = candidate_miss_limit(previous, run_date) if previous else None
            try:
                previous_misses = int(previous.get("consecutive_misses", 0) or 0)
            except (TypeError, ValueError):
                previous_misses = 0
            if previous_handoff == "pending" and handoff_phase == "handoff":
                previous_misses = 0
            reappeared = bool(previous) and miss_limit is not None and previous_misses >= miss_limit
            try:
                generation = max(1, int(previous.get("run_generation", 1) or 1))
            except (TypeError, ValueError):
                generation = 1
            if reappeared:
                generation += 1
            item.update({
                "ever_seen_atmovies": True,
                "atmovies_present": True,
                "consecutive_misses": 0,
                "last_seen_atmovies": run_date,
                "last_audit_date": run_date,
                "ever_published": is_sheet_true(previous.get("ever_published"), default=False),
                "run_generation": generation,
                "run_started_at": run_date if reappeared else previous.get("run_started_at") or run_date,
                "reappeared_after_hidden": (
                    reappeared
                    or is_sheet_true(previous.get("reappeared_after_hidden"), default=False)
                ),
                "handoff_started_at": (
                    "pending" if handoff_phase == "far"
                    else run_date if handoff_phase == "handoff" and previous_handoff == "pending"
                    else previous_handoff or (run_date if handoff_phase == "handoff" else "")
                ),
                "cinema_present": bool(cinema_sources),
                "present_sources": ",".join(["atmovies", *cinema_sources]),
                "absence_audit_complete": (
                    True if audit_complete
                    else is_sheet_true(previous.get("absence_audit_complete"), default=False)
                ),
            })
        elif cinema_sources:
            item = {**previous, **cinema_candidates_by_id.get(tmdb_id, {})}
            miss_limit = candidate_miss_limit(previous, run_date)
            try:
                previous_misses = int(previous.get("consecutive_misses", 0) or 0)
            except (TypeError, ValueError):
                previous_misses = 0
            reappeared = miss_limit is not None and previous_misses >= miss_limit
            try:
                generation = max(1, int(previous.get("run_generation", 1) or 1))
            except (TypeError, ValueError):
                generation = 1
            if reappeared:
                generation += 1
            item.update({
                "atmovies_present": False,
                "cinema_present": True,
                "present_sources": ",".join(cinema_sources),
                "consecutive_misses": 0,
                "last_audit_date": run_date,
                "absence_audit_complete": (
                    True if audit_complete
                    else is_sheet_true(previous.get("absence_audit_complete"), default=False)
                ),
                "run_generation": generation,
                "run_started_at": run_date if reappeared else previous.get("run_started_at") or run_date,
                "reappeared_after_hidden": (
                    reappeared
                    or is_sheet_true(previous.get("reappeared_after_hidden"), default=False)
                ),
            })
        else:
            item = dict(previous)
            try:
                misses = int(item.get("consecutive_misses", 0) or 0)
            except (TypeError, ValueError):
                misses = 0
            if handoff_phase == "far":
                misses = 0
            elif handoff_phase == "handoff" and previous_handoff == "pending":
                misses = 0
            last_audit_date = str(item.get("last_audit_date", "") or "").strip()
            if audit_complete and handoff_phase != "far" and last_audit_date != run_date:
                misses += 1
            item.update({
                "ever_seen_atmovies": is_sheet_true(item.get("ever_seen_atmovies"), default=False),
                "atmovies_present": False,
                "cinema_present": False,
                "present_sources": "",
                "consecutive_misses": misses,
                "last_audit_date": run_date if audit_complete else last_audit_date,
                "absence_audit_complete": (
                    True if audit_complete
                    else is_sheet_true(previous.get("absence_audit_complete"), default=False)
                ),
                "handoff_started_at": (
                    "pending" if handoff_phase == "far"
                    else run_date if handoff_phase == "handoff" and previous_handoff == "pending"
                    else previous_handoff or (run_date if handoff_phase == "handoff" else "")
                ),
            })
        item["tmdb_id"] = int(tmdb_id)
        merged.append(item)
    return merged


def mark_published_candidates(items, movie_payload):
    """保存曾公開狀態，讓長期連續上映不受固定天數下架。"""
    published_ids = {
        int(movie.get("id"))
        for bucket in ("now", "soon")
        for movie in movie_payload.get("movies", {}).get(bucket, [])
        if movie.get("id")
    }
    marked = []
    for item in items:
        copy = dict(item)
        if int(copy.get("tmdb_id", 0) or 0) in published_ids:
            copy["ever_published"] = True
        marked.append(copy)
    return marked


def merge_rerelease_presence(
    current_items, previous_items, run_date, audit_complete, rejected_source_urls=None
):
    """合併重映來源聯集；一次完整稽核全來源缺席即隱藏。"""
    rejected_source_urls = set(rejected_source_urls or [])
    current_by_id = {str(item["tmdb_id"]): dict(item) for item in current_items if item.get("tmdb_id")}
    previous_by_id = {}
    for item in previous_items:
        if not item.get("tmdb_id"):
            continue
        # 舊版曾把影城發現的一般新片寫入重映表；沒有重映證據的舊列不再保留。
        if (
            "rerelease_verified" in item
            and not is_sheet_true(item.get("rerelease_verified"), default=False)
        ):
            continue
        item_urls = {
            url.strip()
            for url in str(item.get("source_urls", "") or "").replace(" | ", "\n").splitlines()
            if url.strip()
        }
        if item_urls & rejected_source_urls:
            continue
        previous_by_id[str(item["tmdb_id"])] = dict(item)
    merged = []
    for tmdb_id in sorted(set(previous_by_id) | set(current_by_id), key=lambda value: int(value)):
        previous = previous_by_id.get(tmdb_id, {})
        current = current_by_id.get(tmdb_id)
        if current:
            item = {**previous, **current}
            item.update({
                "rerelease_present": True,
                "consecutive_misses": 0,
                "hidden": False,
                "first_seen": previous.get("first_seen") or run_date,
                "last_seen": run_date,
                "last_audit_date": run_date,
            })
        else:
            item = dict(previous)
            if audit_complete:
                try:
                    misses = int(item.get("consecutive_misses", 0) or 0)
                except (TypeError, ValueError):
                    misses = 0
                if str(item.get("last_audit_date", "") or "") != run_date:
                    misses += 1
                item.update({
                    "rerelease_present": False,
                    "consecutive_misses": misses,
                    "hidden": misses >= RERELEASE_MISS_LIMIT,
                    "last_audit_date": run_date,
                })
        item["tmdb_id"] = int(tmdb_id)
        merged.append(item)
    return merged


def seed_site_handoff_candidates(previous_items, movie_payload, run_date, manual_ids):
    """將已進入上映前 60 天、但尚無候選狀態的公開電影交給開眼稽核追蹤。"""
    audit_date = datetime.strptime(run_date, "%Y-%m-%d").date()
    handoff_cutoff = audit_date + timedelta(days=ATMOVIES_HANDOFF_DAYS)
    existing_ids = {
        int(item.get("tmdb_id"))
        for item in previous_items
        if item.get("tmdb_id")
    }
    seeded = [dict(item) for item in previous_items]
    for bucket in ("now", "soon"):
        for movie in movie_payload.get("movies", {}).get(bucket, []):
            try:
                tmdb_id = int(movie.get("id"))
                release_date = datetime.strptime(str(movie.get("releaseDate", "")), "%Y-%m-%d").date()
            except (TypeError, ValueError):
                continue
            if tmdb_id in existing_ids or tmdb_id in manual_ids or release_date > handoff_cutoff:
                continue
            seeded.append({
                "tmdb_id": tmdb_id,
                "source_bucket": "now" if release_date <= audit_date else "next",
                "title_zh": movie.get("titleZh", ""),
                "title_en": movie.get("titleEn", ""),
                "release_date_tw": movie.get("releaseDate", ""),
                "tmdb_tw_release_date": movie.get("releaseDate", ""),
                "tmdb_title": movie.get("titleZh", ""),
                "ever_seen_atmovies": False,
                "atmovies_present": False,
                "consecutive_misses": 0,
                "last_seen_atmovies": "",
                "last_audit_date": "",
                "ever_published": True,
                "run_generation": 1,
                "run_started_at": run_date,
                "reappeared_after_hidden": False,
                "handoff_started_at": run_date,
            })
            existing_ids.add(tmdb_id)
    return seeded


def prune_retired_candidates(items, run_date, published_ids, whitelist_ids, manual_ids):
    """只清除已隱藏、已離開公開日期範圍且沒有其他保留依據的私人候選狀態。"""
    audit_date = datetime.strptime(run_date, "%Y-%m-%d").date()
    cutoff = audit_date - timedelta(days=CANDIDATE_RETENTION_DAYS)
    protected_ids = {int(value) for value in published_ids | whitelist_ids | manual_ids if value}
    retained = []
    for item in items:
        try:
            tmdb_id = int(item.get("tmdb_id", 0))
            release_date = datetime.strptime(str(item.get("tmdb_tw_release_date", "")), "%Y-%m-%d").date()
            misses = int(item.get("consecutive_misses", 0) or 0)
        except (TypeError, ValueError):
            retained.append(item)
            continue
        miss_limit = candidate_miss_limit(item, run_date)
        can_remove = (
            not is_sheet_true(item.get("atmovies_present"), default=False)
            and miss_limit is not None
            and misses >= miss_limit
            and tmdb_id not in protected_ids
            and release_date < cutoff
        )
        if not can_remove:
            retained.append(item)
    return retained


def load_json_ids(path, kind):
    if not path.exists():
        return set()
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if kind == "movies":
        values = [movie.get("id") for bucket in ("now", "soon") for movie in payload.get("movies", {}).get(bucket, [])]
    elif kind == "whitelist":
        values = payload.get("tmdb_ids", [])
    elif kind == "manual":
        values = [item.get("tmdb_id") for item in payload if isinstance(item, dict)]
    else:
        raise ValueError(f"Unknown id source kind: {kind}")
    ids = set()
    for value in values:
        try:
            ids.add(int(value))
        except (TypeError, ValueError):
            continue
    return ids


def load_json_payload(path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def candidate_items_to_rows(items):
    rows = [CANDIDATE_HEADERS]
    for item in sorted(
        items,
        key=lambda value: (
            not bool(value.get("release_date_tw")),
            value.get("release_date_tw") or "",
            int(value.get("tmdb_id", 0)),
        ),
    ):
        rows.append([item.get(header, "") for header in CANDIDATE_HEADERS])
    return rows


def rerelease_items_to_rows(items):
    rows = [RERELEASE_HEADERS]
    for item in sorted(
        items,
        key=lambda value: (
            not bool(value.get("cinema_release_date")),
            value.get("cinema_release_date") or "",
            int(value.get("tmdb_id", 0)),
        ),
    ):
        rows.append([item.get(header, "") for header in RERELEASE_HEADERS])
    return rows


def load_service_account_credentials():
    raw_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    json_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()

    if raw_json:
        from google.oauth2 import service_account

        info = json.loads(raw_json)
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)

    if json_path:
        from google.oauth2 import service_account

        return service_account.Credentials.from_service_account_file(json_path, scopes=SCOPES)

    raise RuntimeError(
        "Missing Google credentials. Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE."
    )


def quote_query_value(value):
    return value.replace("\\", "\\\\").replace("'", "\\'")


def drive_list_first(service, query, fields):
    response = service.files().list(
        q=query,
        spaces="drive",
        fields=f"files({fields})",
        pageSize=10,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = response.get("files", [])
    return files[0] if files else None


def resolve_folder_id(drive_service, folder_id, folder_name):
    if folder_id:
        return folder_id

    safe_name = quote_query_value(folder_name)
    query = (
        f"mimeType='{FOLDER_MIME_TYPE}' and "
        f"name='{safe_name}' and trashed=false"
    )
    folder = drive_list_first(drive_service, query, "id,name")
    if not folder:
        raise RuntimeError(
            f"Google Drive folder '{folder_name}' was not found. "
            "Set GOOGLE_DRIVE_FOLDER_ID for the exact target folder."
        )
    return folder["id"]


def find_spreadsheet(drive_service, folder_id, spreadsheet_name):
    safe_name = quote_query_value(spreadsheet_name)
    query = (
        f"'{folder_id}' in parents and "
        f"mimeType='{SPREADSHEET_MIME_TYPE}' and "
        f"name='{safe_name}' and trashed=false"
    )
    return drive_list_first(drive_service, query, "id,name,webViewLink")


def create_spreadsheet(drive_service, folder_id, spreadsheet_name):
    metadata = {
        "name": spreadsheet_name,
        "mimeType": SPREADSHEET_MIME_TYPE,
        "parents": [folder_id],
    }
    return drive_service.files().create(
        body=metadata,
        fields="id,name,webViewLink",
        supportsAllDrives=True,
    ).execute()


def get_spreadsheet_file(drive_service, spreadsheet_id):
    return drive_service.files().get(
        fileId=spreadsheet_id,
        fields="id,name,webViewLink",
        supportsAllDrives=True,
    ).execute()


def get_spreadsheet_metadata(sheets_service, spreadsheet_id):
    return sheets_service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="spreadsheetId,spreadsheetUrl,sheets(properties(sheetId,title,gridProperties(rowCount,columnCount)))",
    ).execute()


def sheet_by_title(metadata, title):
    for sheet in metadata.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("title") == title:
            return props
    return None


def get_sheet_values(sheets_service, spreadsheet_id, title):
    response = sheets_service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=quote_sheet_range(title, "A1:A1"),
    ).execute()
    return response.get("values", [])


def get_all_sheet_values(sheets_service, spreadsheet_id, title):
    response = sheets_service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=quote_sheet_range(title, "A:Z"),
    ).execute()
    return response.get("values", [])


def quote_sheet_range(title, cell_range):
    safe_title = title.replace("'", "''")
    return f"'{safe_title}'!{cell_range}"


def ensure_date_sheet(sheets_service, spreadsheet_id, sheet_title):
    metadata = get_spreadsheet_metadata(sheets_service, spreadsheet_id)
    existing = sheet_by_title(metadata, sheet_title)
    if existing:
        return existing["sheetId"]

    sheets = metadata.get("sheets", [])
    if len(sheets) == 1:
        first_props = sheets[0].get("properties", {})
        first_title = first_props.get("title", "")
        first_values = get_sheet_values(sheets_service, spreadsheet_id, first_title)
        if not first_values:
            sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    "requests": [
                        {
                            "updateSheetProperties": {
                                "properties": {
                                    "sheetId": first_props["sheetId"],
                                    "title": sheet_title,
                                },
                                "fields": "title",
                            }
                        }
                    ]
                },
            ).execute()
            return first_props["sheetId"]

    response = sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "requests": [
                {
                    "addSheet": {
                        "properties": {
                            "title": sheet_title,
                        }
                    }
                }
            ]
        },
    ).execute()
    return response["replies"][0]["addSheet"]["properties"]["sheetId"]


def write_rows(sheets_service, spreadsheet_id, sheet_title, rows):
    sheets_service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range=quote_sheet_range(sheet_title, "A:Z"),
        body={},
    ).execute()
    sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=quote_sheet_range(sheet_title, "A1"),
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()


def format_sheet(sheets_service, spreadsheet_id, sheet_id, column_count):
    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "requests": [
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": sheet_id,
                            "gridProperties": {"frozenRowCount": 1},
                        },
                        "fields": "gridProperties.frozenRowCount",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "textFormat": {"bold": True},
                                "backgroundColor": {
                                    "red": 0.88,
                                    "green": 0.93,
                                    "blue": 0.84,
                                },
                            }
                        },
                        "fields": "userEnteredFormat(textFormat,backgroundColor)",
                    }
                },
                {
                    "autoResizeDimensions": {
                        "dimensions": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": 0,
                            "endIndex": column_count,
                        }
                    }
                },
            ]
        },
    ).execute()


def publish():
    load_environment()
    args = parse_args()
    tsv_path = infer_tsv_path(args.tsv_path, args.run_date)
    run_date = infer_run_date(tsv_path, args.run_date)
    rows = load_tsv_rows(tsv_path)

    credentials = load_service_account_credentials()
    from googleapiclient.discovery import build

    drive_service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    sheets_service = build("sheets", "v4", credentials=credentials, cache_discovery=False)

    if args.spreadsheet_id:
        spreadsheet = get_spreadsheet_file(drive_service, args.spreadsheet_id)
        log(f"Using spreadsheet by id: {spreadsheet['name']} ({spreadsheet['id']})")
    else:
        folder_id = resolve_folder_id(drive_service, args.folder_id, args.folder_name)
        spreadsheet = find_spreadsheet(drive_service, folder_id, args.spreadsheet_name)
        if spreadsheet:
            log(f"Using spreadsheet: {spreadsheet['name']} ({spreadsheet['id']})")
        else:
            spreadsheet = create_spreadsheet(drive_service, folder_id, args.spreadsheet_name)
            log(f"Created spreadsheet: {spreadsheet['name']} ({spreadsheet['id']})")

    spreadsheet_id = spreadsheet["id"]
    sheet_id = ensure_date_sheet(sheets_service, spreadsheet_id, run_date)
    write_rows(sheets_service, spreadsheet_id, run_date, rows)
    format_sheet(sheets_service, spreadsheet_id, sheet_id, len(rows[0]))

    rerelease_audit = load_rerelease_audit()
    current_candidate_items = load_candidate_items()
    cinema_candidates = (
        rerelease_audit.get("regular_candidates", []) if rerelease_audit is not None else []
    )
    if current_candidate_items or cinema_candidates:
        metadata = get_spreadsheet_metadata(sheets_service, spreadsheet_id)
        existing_candidate_sheet = sheet_by_title(metadata, CANDIDATES_SHEET_TITLE)
        previous_candidate_items = []
        if existing_candidate_sheet:
            previous_candidate_items = sheet_rows_to_items(
                get_all_sheet_values(sheets_service, spreadsheet_id, CANDIDATES_SHEET_TITLE)
            )
        manual_ids = load_json_ids(MANUAL_RELEASES_FILE, "manual")
        movie_payload = load_json_payload(MOVIE_DATA_FILE, {"movies": {}})
        previous_candidate_items = seed_site_handoff_candidates(
            previous_candidate_items,
            movie_payload,
            run_date,
            manual_ids,
        )
        previous_candidate_items = mark_published_candidates(previous_candidate_items, movie_payload)
        cinema_presence = (
            rerelease_audit.get("cinema_presence", {}) if rerelease_audit is not None else {}
        )
        candidate_items = merge_candidate_presence(
            current_candidate_items,
            previous_candidate_items,
            run_date,
            cinema_presence,
            bool(rerelease_audit and rerelease_audit.get("audit_complete")),
            cinema_candidates,
        )
        candidate_items = prune_retired_candidates(
            candidate_items,
            run_date,
            load_json_ids(MOVIE_DATA_FILE, "movies"),
            load_json_ids(WHITELIST_FILE, "whitelist"),
            manual_ids,
        )
        candidate_rows = candidate_items_to_rows(candidate_items)
        candidate_sheet_id = ensure_date_sheet(sheets_service, spreadsheet_id, CANDIDATES_SHEET_TITLE)
        write_rows(sheets_service, spreadsheet_id, CANDIDATES_SHEET_TITLE, candidate_rows)
        format_sheet(sheets_service, spreadsheet_id, candidate_sheet_id, len(candidate_rows[0]))
        log(f"Wrote {len(candidate_rows) - 1} refresh candidates to worksheet {CANDIDATES_SHEET_TITLE}.")

    if rerelease_audit is not None:
        metadata = get_spreadsheet_metadata(sheets_service, spreadsheet_id)
        existing_rerelease_sheet = sheet_by_title(metadata, RERELEASES_SHEET_TITLE)
        previous_rerelease_items = []
        if existing_rerelease_sheet:
            previous_rerelease_items = sheet_rows_to_items(
                get_all_sheet_values(sheets_service, spreadsheet_id, RERELEASES_SHEET_TITLE)
            )
        rerelease_items = merge_rerelease_presence(
            rerelease_audit.get("candidates", []),
            previous_rerelease_items,
            run_date,
            bool(rerelease_audit.get("audit_complete")),
            rerelease_audit.get("rejected_source_urls", []),
        )
        rerelease_rows = rerelease_items_to_rows(rerelease_items)
        rerelease_sheet_id = ensure_date_sheet(sheets_service, spreadsheet_id, RERELEASES_SHEET_TITLE)
        write_rows(sheets_service, spreadsheet_id, RERELEASES_SHEET_TITLE, rerelease_rows)
        format_sheet(sheets_service, spreadsheet_id, rerelease_sheet_id, len(rerelease_rows[0]))
        log(f"Wrote {len(rerelease_rows) - 1} rerelease candidates to worksheet {RERELEASES_SHEET_TITLE}.")

    audit_complete = bool(rerelease_audit and rerelease_audit.get("audit_complete"))
    audit_status_rows = [
        AUDIT_STATUS_HEADERS,
        [run_date, datetime.now(ZoneInfo("Asia/Taipei")).isoformat(), audit_complete],
    ]
    audit_status_sheet_id = ensure_date_sheet(
        sheets_service, spreadsheet_id, AUDIT_STATUS_SHEET_TITLE
    )
    write_rows(
        sheets_service, spreadsheet_id, AUDIT_STATUS_SHEET_TITLE, audit_status_rows
    )
    format_sheet(
        sheets_service,
        spreadsheet_id,
        audit_status_sheet_id,
        len(AUDIT_STATUS_HEADERS),
    )
    log(
        f"Recorded audit status for {run_date}: complete={audit_complete}."
    )

    metadata = get_spreadsheet_metadata(sheets_service, spreadsheet_id)
    spreadsheet_url = metadata.get("spreadsheetUrl") or spreadsheet.get("webViewLink", "")
    print(spreadsheet_url)
    log(f"Wrote {len(rows) - 1} data rows to worksheet {run_date}.")


if __name__ == "__main__":
    try:
        publish()
    except Exception as exc:
        log(f"ERROR: {exc}")
        sys.exit(1)
