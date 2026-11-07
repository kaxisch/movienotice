#!/usr/bin/env python3
"""將人工確認的 TMDB 對照套用到私人稽核工作表，不重新爬取影城。"""

import os
import sys
from datetime import date, datetime

from dotenv import load_dotenv

import weekly_check as weekly
from publish_to_google_sheet import (
    AUDIT_STATUS_SHEET_TITLE,
    CANDIDATE_HEADERS,
    CANDIDATES_SHEET_TITLE,
    discard_superseded_candidates,
    load_service_account_credentials,
    load_superseded_tmdb_ids,
    quote_sheet_range,
    sheet_rows_to_items,
)


ROOT_DIR = weekly.OUTPUT_DIR.parent
MANUAL_MATCH_STATUS = "manually_matched"
REVIEWABLE_STATUSES = {
    "tmdb_not_found",
    "missing_tw_date",
    "tmdb_match_suspicious",
    "tmdb_date_mismatch",
    MANUAL_MATCH_STATUS,
}
AUDIT_HEADERS = [
    "類別", "台灣中文片名", "台灣上映日期", "原文片名", "TMDB連結",
    "原上映日期", "備註", "發現來源", "來源連結",
]


def log(message):
    print(message, file=sys.stderr)


def load_environment():
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(ROOT_DIR / "scripts" / ".env")


def latest_audit_sheet_title(titles):
    dated = []
    for title in titles:
        try:
            datetime.strptime(title, "%Y-%m-%d")
        except (TypeError, ValueError):
            continue
        dated.append(title)
    return max(dated) if dated else ""


def source_bucket(release_date, today=None):
    today = today or date.today()
    try:
        return "now" if date.fromisoformat(release_date) <= today else "next"
    except (TypeError, ValueError):
        return "next"


def audit_is_complete(rows, audit_date):
    if not rows:
        return False
    headers = rows[0]
    for row in rows[1:]:
        item = {headers[index]: value for index, value in enumerate(row) if index < len(headers)}
        if str(item.get("audit_date", "")).strip() == audit_date:
            return str(item.get("audit_complete", "")).strip().lower() in {"true", "1", "yes"}
    return False


def manual_matches_from_rows(rows, overrides, audit_date, audit_complete=False):
    """從日期分頁找出已有人工 override 的未配對電影。"""
    if not rows:
        return []
    headers = rows[0]
    matches = []
    audit_day = date.fromisoformat(audit_date)
    for row_number, row in enumerate(rows[1:], start=2):
        item = {headers[index]: value for index, value in enumerate(row) if index < len(headers)}
        movie = {
            "title_zh": str(item.get("台灣中文片名", "")).strip(),
            "title_en": str(item.get("原文片名", "")).strip(),
        }
        override = weekly.find_tmdb_override(movie, overrides)
        if not override or not override.get("tmdb_id"):
            continue
        status = str(item.get("類別", "")).strip()
        current_link = str(item.get("TMDB連結", "")).strip()
        superseded_links = {
            weekly.tmdb_movie_url(value).split("?", 1)[0]
            for value in override.get("supersedes_tmdb_ids", [])
        }
        if status not in REVIEWABLE_STATUSES and not any(
            current_link.startswith(link) for link in superseded_links
        ):
            continue
        tmdb_id = int(override["tmdb_id"])
        title_zh = str(override.get("title_zh") or movie["title_zh"]).strip()
        release_date = str(
            override.get("release_date_tw") or item.get("台灣上映日期", "")
        ).strip()
        matches.append({
            "row_number": row_number,
            "tmdb_id": tmdb_id,
            "source_bucket": source_bucket(release_date, audit_day),
            "title_zh": title_zh,
            "title_en": movie["title_en"],
            "release_date_tw": release_date,
            "tmdb_title": movie["title_en"],
            "ever_seen_atmovies": True,
            "atmovies_present": True,
            "consecutive_misses": 0,
            "last_seen_atmovies": audit_date,
            "last_audit_date": audit_date,
            "cinema_present": True,
            "present_sources": "atmovies",
            "absence_audit_complete": audit_complete,
        })
    return matches


def merge_manual_candidates(existing, matches):
    """以 TMDB ID 冪等合併，保留既有候選的發布與交接狀態。"""
    merged = {}
    for item in existing:
        try:
            merged[int(item.get("tmdb_id", 0))] = dict(item)
        except (TypeError, ValueError):
            continue
    for match in matches:
        tmdb_id = int(match["tmdb_id"])
        candidate = {**merged.get(tmdb_id, {}), **{
            key: value for key, value in match.items() if key != "row_number"
        }}
        merged[tmdb_id] = candidate
    return list(merged.values())


def candidate_rows(items):
    return [CANDIDATE_HEADERS] + [
        [item.get(header, "") for header in CANDIDATE_HEADERS]
        for item in sorted(items, key=lambda value: (
            str(value.get("release_date_tw", "")), int(value.get("tmdb_id", 0))
        ))
    ]


def updated_audit_rows(rows, matches):
    updated = [list(row) for row in rows]
    while len(updated[0]) < len(AUDIT_HEADERS):
        updated[0].append(AUDIT_HEADERS[len(updated[0])])
    by_row = {match["row_number"]: match for match in matches}
    for row_number, match in by_row.items():
        index = row_number - 1
        while len(updated[index]) < len(AUDIT_HEADERS):
            updated[index].append("")
        updated[index][0] = MANUAL_MATCH_STATUS
        updated[index][1] = match["title_zh"]
        updated[index][2] = match["release_date_tw"]
        updated[index][4] = weekly.tmdb_movie_url(match["tmdb_id"])
        updated[index][6] = "人工確認 TMDB 配對；由 Refresh 驗證台灣院線日期"
    return updated


def get_values(service, spreadsheet_id, title):
    return service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=quote_sheet_range(title, "A:Z"),
    ).execute().get("values", [])


def ensure_candidate_sheet(service, spreadsheet_id, titles):
    if CANDIDATES_SHEET_TITLE in titles:
        return
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": CANDIDATES_SHEET_TITLE}}}]},
    ).execute()
    titles.append(CANDIDATES_SHEET_TITLE)


def apply_reviews():
    load_environment()
    spreadsheet_id = os.environ.get("GOOGLE_SPREADSHEET_ID", "").strip()
    if not spreadsheet_id:
        raise RuntimeError("GOOGLE_SPREADSHEET_ID is required")

    from googleapiclient.discovery import build

    service = build(
        "sheets", "v4", credentials=load_service_account_credentials(), cache_discovery=False
    )
    metadata = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties(title))",
    ).execute()
    titles = [sheet.get("properties", {}).get("title", "") for sheet in metadata.get("sheets", [])]
    audit_title = latest_audit_sheet_title(titles)
    if not audit_title:
        log("No dated audit worksheet exists; no manual TMDB reviews to apply.")
        return 0

    audit_rows = get_values(service, spreadsheet_id, audit_title)
    audit_status_rows = (
        get_values(service, spreadsheet_id, AUDIT_STATUS_SHEET_TITLE)
        if AUDIT_STATUS_SHEET_TITLE in titles else []
    )
    matches = manual_matches_from_rows(
        audit_rows,
        weekly.load_tmdb_overrides(),
        audit_title,
        audit_complete=audit_is_complete(audit_status_rows, audit_title),
    )
    if not matches:
        log(f"No manual TMDB reviews found in worksheet {audit_title}.")
        return 0

    ensure_candidate_sheet(service, spreadsheet_id, titles)
    existing_rows = (
        get_values(service, spreadsheet_id, CANDIDATES_SHEET_TITLE)
        if CANDIDATES_SHEET_TITLE in titles else []
    )
    existing = discard_superseded_candidates(
        sheet_rows_to_items(existing_rows), load_superseded_tmdb_ids()
    )
    merged = merge_manual_candidates(existing, matches)
    body = {
        "valueInputOption": "RAW",
        "data": [
            {
                "range": quote_sheet_range(CANDIDATES_SHEET_TITLE, "A1"),
                "values": candidate_rows(merged),
            },
            {
                "range": quote_sheet_range(audit_title, "A1"),
                "values": updated_audit_rows(audit_rows, matches),
            },
        ],
    }
    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id, body=body
    ).execute()
    log(f"Applied {len(matches)} manual TMDB review(s) from {audit_title} to {CANDIDATES_SHEET_TITLE}.")
    return len(matches)


if __name__ == "__main__":
    try:
        apply_reviews()
    except Exception as error:
        log(f"ERROR: {error}")
        sys.exit(1)
