#!/usr/bin/env python3
"""Record a successful public movie-data refresh in one private Google Sheet tab."""

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from publish_to_google_sheet import (
    ensure_date_sheet,
    load_service_account_credentials,
    quote_sheet_range,
)


ROOT_DIR = Path(__file__).resolve().parent.parent
REFRESH_LOG_SHEET_TITLE = "_refresh_log"
MAX_LOG_ROWS = 2000
HEADERS = [
    "完成時間",
    "列類型",
    "變更類型",
    "TMDB ID",
    "片名",
    "原上映日期",
    "新上映日期",
    "原分類",
    "新分類",
    "原重映",
    "新重映",
    "備註",
    "Run ID",
    "Commit SHA",
]
RUN_ID_INDEX = HEADERS.index("Run ID")
GOOGLE_SHEETS_RETRY_ATTEMPTS = 4
GOOGLE_SHEETS_RETRY_DELAY = 2
GOOGLE_SHEETS_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


def is_transient_google_sheets_error(error):
    status = getattr(getattr(error, "resp", None), "status", None)
    return status in GOOGLE_SHEETS_TRANSIENT_STATUS_CODES or isinstance(
        error, (TimeoutError, ConnectionError, OSError)
    )


def execute_google_sheets_request(request, operation):
    """Retry transient Google Sheets failures without importing the TMDB refresh."""
    for attempt in range(1, GOOGLE_SHEETS_RETRY_ATTEMPTS + 1):
        try:
            return request.execute()
        except Exception as error:
            if not is_transient_google_sheets_error(error) or attempt >= GOOGLE_SHEETS_RETRY_ATTEMPTS:
                raise
            delay = GOOGLE_SHEETS_RETRY_DELAY * (2 ** (attempt - 1))
            print(
                f"Google Sheets temporary failure during {operation}; "
                f"retry {attempt}/{GOOGLE_SHEETS_RETRY_ATTEMPTS - 1} in {delay}s: {error}",
                flush=True,
            )
            time.sleep(delay)


def parse_args():
    parser = argparse.ArgumentParser(description="Publish a successful Refresh diff to Google Sheets.")
    parser.add_argument("previous_movie_data", type=Path)
    parser.add_argument("current_movie_data", type=Path)
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    parser.add_argument("--commit-sha", default=os.environ.get("REFRESH_COMMIT_SHA", ""))
    return parser.parse_args()


def load_environment():
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(Path(__file__).resolve().parent / ".env")


def load_movie_index(path):
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    result = {}
    buckets = payload.get("movies", {})
    for key, label in (("now", "現正熱映"), ("soon", "即將上映")):
        for movie in buckets.get(key, []):
            movie_id = int(movie["id"])
            result[movie_id] = {
                "id": movie_id,
                "title": movie.get("titleZh") or movie.get("titleEn") or str(movie_id),
                "release_date": movie.get("releaseDate", ""),
                "bucket": label,
                "is_rerelease": bool(movie.get("isRerelease", False)),
            }
    return result


def diff_movies(previous, current):
    changes = []
    for movie_id in sorted(set(previous) | set(current)):
        before = previous.get(movie_id)
        after = current.get(movie_id)
        if before is None:
            changes.append({"kind": "新增", "before": None, "after": after})
            continue
        if after is None:
            changes.append({"kind": "移除", "before": before, "after": None})
            continue

        changed_fields = []
        if before["release_date"] != after["release_date"]:
            changed_fields.append("上映日期")
        if before["bucket"] != after["bucket"]:
            changed_fields.append("分類")
        if before["is_rerelease"] != after["is_rerelease"]:
            changed_fields.append("重映標記")
        if before["title"] != after["title"]:
            changed_fields.append("片名")
        if changed_fields:
            changes.append({
                "kind": "、".join(changed_fields),
                "before": before,
                "after": after,
            })
    return changes


def yes_no(value):
    if value is None:
        return ""
    return "是" if value else "否"


def build_log_block(previous, current, completed_at, run_id, commit_sha):
    changes = diff_movies(previous, current)
    added = sum(change["kind"] == "新增" for change in changes)
    removed = sum(change["kind"] == "移除" for change in changes)
    changed = len(changes) - added - removed
    note = (
        f"更新前 {len(previous)} 部｜更新後 {len(current)} 部｜"
        f"新增 {added}｜移除 {removed}｜變更 {changed}"
    )
    if not changes:
        note += "｜無異動"

    rows = [[completed_at, "摘要", "", "", "", "", "", "", "", "", "", note, run_id, commit_sha]]
    for change in changes:
        before = change["before"] or {}
        after = change["after"] or {}
        movie = change["after"] or change["before"]
        rows.append([
            completed_at,
            "明細",
            change["kind"],
            movie["id"],
            after.get("title") or before.get("title", ""),
            before.get("release_date", ""),
            after.get("release_date", ""),
            before.get("bucket", ""),
            after.get("bucket", ""),
            yes_no(before.get("is_rerelease") if before else None),
            yes_no(after.get("is_rerelease") if after else None),
            "",
            run_id,
            commit_sha,
        ])
    return rows


def split_blocks(rows):
    blocks = []
    current = []
    for row in rows:
        if not any(str(value).strip() for value in row):
            if current:
                blocks.append(current)
                current = []
        else:
            current.append(row)
    if current:
        blocks.append(current)
    return blocks


def merge_log_rows(existing_rows, new_block, run_id, max_rows=MAX_LOG_ROWS):
    if existing_rows and existing_rows[0] != HEADERS:
        raise RuntimeError(
            f"{REFRESH_LOG_SHEET_TITLE} 表頭與程式預期不同，為避免覆寫既有資料已停止。"
        )

    retained_blocks = []
    for block in split_blocks(existing_rows[1:] if existing_rows else []):
        block_run_ids = {
            str(row[RUN_ID_INDEX])
            for row in block
            if len(row) > RUN_ID_INDEX and str(row[RUN_ID_INDEX]).strip()
        }
        if run_id and run_id in block_run_ids:
            continue
        retained_blocks.append(block)

    output = [HEADERS]
    for block_index, block in enumerate([new_block, *retained_blocks]):
        required = len(block) + (1 if len(output) > 1 else 0)
        # The current run must never be partially omitted, even in the unlikely
        # event that its change list alone is larger than the retention target.
        if block_index > 0 and len(output) + required > max_rows:
            break
        if len(output) > 1:
            output.append([])
        output.extend(block)
    return output


def write_log(service, spreadsheet_id, sheet_id, rows):
    execute_google_sheets_request(
        service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=quote_sheet_range(REFRESH_LOG_SHEET_TITLE, "A:N"),
            body={},
        ),
        "refresh log clear",
    )
    execute_google_sheets_request(
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=quote_sheet_range(REFRESH_LOG_SHEET_TITLE, "A1"),
            valueInputOption="RAW",
            body={"values": rows},
        ),
        "refresh log write",
    )

    requests = [
        {
            "updateSheetProperties": {
                "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        },
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": len(rows), "startColumnIndex": 0, "endColumnIndex": len(HEADERS)},
                "cell": {"userEnteredFormat": {"backgroundColor": {"red": 1, "green": 1, "blue": 1}, "textFormat": {"bold": False}, "verticalAlignment": "MIDDLE", "wrapStrategy": "WRAP"}},
                "fields": "userEnteredFormat(backgroundColor,textFormat.bold,verticalAlignment,wrapStrategy)",
            }
        },
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": len(HEADERS)},
                "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9}, "textFormat": {"bold": True}}},
                "fields": "userEnteredFormat(backgroundColor,textFormat.bold)",
            }
        },
    ]
    colors = {
        "摘要": {"red": 0.85, "green": 0.92, "blue": 0.98},
        "新增": {"red": 0.85, "green": 0.95, "blue": 0.86},
        "移除": {"red": 0.98, "green": 0.86, "blue": 0.86},
        "變更": {"red": 1.0, "green": 0.95, "blue": 0.8},
    }
    for index, row in enumerate(rows[1:], start=1):
        if not row:
            continue
        style = "摘要" if len(row) > 1 and row[1] == "摘要" else row[2] if len(row) > 2 else ""
        color = colors.get(style, colors["變更"])
        requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": index, "endRowIndex": index + 1, "startColumnIndex": 0, "endColumnIndex": len(HEADERS)},
                "cell": {"userEnteredFormat": {"backgroundColor": color, "textFormat": {"bold": style == "摘要"}}},
                "fields": "userEnteredFormat(backgroundColor,textFormat.bold)",
            }
        })
    widths = [155, 70, 140, 85, 260, 105, 105, 100, 100, 75, 75, 320, 150, 160]
    for index, width in enumerate(widths):
        requests.append({
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": index, "endIndex": index + 1},
                "properties": {"pixelSize": width},
                "fields": "pixelSize",
            }
        })
    execute_google_sheets_request(
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests},
        ),
        "refresh log formatting",
    )


def publish():
    load_environment()
    args = parse_args()
    spreadsheet_id = os.environ.get("GOOGLE_SPREADSHEET_ID", "").strip()
    if not spreadsheet_id:
        raise RuntimeError("GOOGLE_SPREADSHEET_ID is required")

    completed_at = datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds")
    run_id = args.run_id.strip() or completed_at
    previous = load_movie_index(args.previous_movie_data)
    current = load_movie_index(args.current_movie_data)
    new_block = build_log_block(previous, current, completed_at, run_id, args.commit_sha.strip())

    from googleapiclient.discovery import build

    service = build(
        "sheets",
        "v4",
        credentials=load_service_account_credentials(),
        cache_discovery=False,
    )
    sheet_id = ensure_date_sheet(service, spreadsheet_id, REFRESH_LOG_SHEET_TITLE)
    response = execute_google_sheets_request(
        service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=quote_sheet_range(REFRESH_LOG_SHEET_TITLE, "A:N"),
        ),
        "refresh log read",
    )
    rows = merge_log_rows(response.get("values", []), new_block, run_id)
    write_log(service, spreadsheet_id, sheet_id, rows)
    print(f"Recorded Refresh run {run_id}: {len(new_block) - 1} movie change(s).")


if __name__ == "__main__":
    publish()
