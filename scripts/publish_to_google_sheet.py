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
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
CANDIDATES_FILE = DATA_DIR / "atmovies-candidates.json"
CANDIDATES_SHEET_TITLE = "_candidates"
CANDIDATE_HEADERS = [
    "tmdb_id", "source_bucket", "title_zh", "title_en",
    "release_date_tw", "atmovies_id", "atmovies_url", "tmdb_title",
    "ever_seen_atmovies", "atmovies_present", "consecutive_misses", "last_seen_atmovies",
]
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
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def merge_candidate_presence(current_items, previous_items, run_date):
    """合併本次開眼候選與前次私人狀態；只有成功發布的稽核才會累加缺席。"""
    current_by_id = {str(item["tmdb_id"]): dict(item) for item in current_items if item.get("tmdb_id")}
    previous_by_id = {str(item.get("tmdb_id", "")): dict(item) for item in previous_items if item.get("tmdb_id")}

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
    for tmdb_id in sorted(set(previous_by_id) | set(current_by_id), key=lambda value: int(value)):
        previous = previous_by_id.get(tmdb_id, {})
        current = current_by_id.get(tmdb_id)
        if current:
            item = {**previous, **current}
            item.update({
                "ever_seen_atmovies": True,
                "atmovies_present": True,
                "consecutive_misses": 0,
                "last_seen_atmovies": run_date,
            })
        else:
            item = dict(previous)
            try:
                misses = int(item.get("consecutive_misses", 0) or 0)
            except (TypeError, ValueError):
                misses = 0
            item.update({
                "ever_seen_atmovies": True,
                "atmovies_present": False,
                "consecutive_misses": misses + 1,
            })
        item["tmdb_id"] = int(tmdb_id)
        merged.append(item)
    return merged


def candidate_items_to_rows(items):
    rows = [CANDIDATE_HEADERS]
    for item in sorted(
        items,
        key=lambda value: (
            not is_sheet_true(value.get("atmovies_present")),
            value.get("release_date_tw", ""),
            int(value.get("tmdb_id", 0)),
        ),
    ):
        rows.append([item.get(header, "") for header in CANDIDATE_HEADERS])
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

    current_candidate_items = load_candidate_items()
    if current_candidate_items:
        metadata = get_spreadsheet_metadata(sheets_service, spreadsheet_id)
        existing_candidate_sheet = sheet_by_title(metadata, CANDIDATES_SHEET_TITLE)
        previous_candidate_items = []
        if existing_candidate_sheet:
            previous_candidate_items = sheet_rows_to_items(
                get_all_sheet_values(sheets_service, spreadsheet_id, CANDIDATES_SHEET_TITLE)
            )
        candidate_items = merge_candidate_presence(current_candidate_items, previous_candidate_items, run_date)
        candidate_rows = candidate_items_to_rows(candidate_items)
        candidate_sheet_id = ensure_date_sheet(sheets_service, spreadsheet_id, CANDIDATES_SHEET_TITLE)
        write_rows(sheets_service, spreadsheet_id, CANDIDATES_SHEET_TITLE, candidate_rows)
        format_sheet(sheets_service, spreadsheet_id, candidate_sheet_id, len(candidate_rows[0]))
        log(f"Wrote {len(candidate_rows) - 1} refresh candidates to worksheet {CANDIDATES_SHEET_TITLE}.")

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
