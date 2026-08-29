#!/usr/bin/env python3
"""檢查今天是否已有完整院線稽核，供 GitHub Actions 漏跑補救使用。"""

import os
import sys

from dotenv import load_dotenv

from candidate_policy import sheet_value_is_true
from publish_to_google_sheet import (
    AUDIT_STATUS_SHEET_TITLE,
    ROOT_DIR,
    get_all_sheet_values,
    load_service_account_credentials,
    today_taipei,
)


def audit_completed_for_date(rows, target_date):
    if not rows:
        return False
    headers = [str(value).strip() for value in rows[0]]
    try:
        date_index = headers.index("audit_date")
        complete_index = headers.index("audit_complete")
    except ValueError:
        return False
    for row in rows[1:]:
        audit_date = str(row[date_index]).strip() if date_index < len(row) else ""
        complete = row[complete_index] if complete_index < len(row) else ""
        if audit_date == target_date and sheet_value_is_true(complete):
            return True
    return False


def main():
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(ROOT_DIR / "scripts" / ".env")
    spreadsheet_id = os.environ.get("GOOGLE_SPREADSHEET_ID", "").strip()
    if not spreadsheet_id:
        raise RuntimeError("GOOGLE_SPREADSHEET_ID is required")

    from googleapiclient.discovery import build

    service = build(
        "sheets",
        "v4",
        credentials=load_service_account_credentials(),
        cache_discovery=False,
    )
    try:
        rows = get_all_sheet_values(
            service, spreadsheet_id, AUDIT_STATUS_SHEET_TITLE
        )
    except Exception as exc:
        status_code = getattr(getattr(exc, "resp", None), "status", None)
        if status_code == 400:
            rows = []
        else:
            raise

    target_date = today_taipei()
    completed = audit_completed_for_date(rows, target_date)
    output_path = os.environ.get("GITHUB_OUTPUT", "").strip()
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(f"audit_date={target_date}\n")
            output.write(f"completed={'true' if completed else 'false'}\n")
    print(
        f"Weekly audit for {target_date}: "
        f"{'already complete' if completed else 'missing or incomplete'}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
