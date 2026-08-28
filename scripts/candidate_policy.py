"""院線候選的共用純判斷規則；本模組不得進行網路或檔案操作。"""

from datetime import datetime, timedelta


NOW_ATMOVIES_MISS_LIMIT = 1
SOON_ATMOVIES_MISS_LIMIT = 1
LEGACY_NOW_ATMOVIES_MISS_LIMIT = 2
LEGACY_SOON_ATMOVIES_MISS_LIMIT = 5
RERELEASE_MISS_LIMIT = 1
CANDIDATE_RETENTION_DAYS = 180
ATMOVIES_HANDOFF_DAYS = 60


def sheet_value_is_true(value, default=False):
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def nonnegative_miss_count(candidate):
    try:
        return max(0, int(candidate.get("consecutive_misses", 0) or 0))
    except (TypeError, ValueError):
        return 0


def candidate_handoff_phase(candidate, audit_date):
    """回傳 now、handoff（上映前 60 天內）或 far（61 天以上）。"""
    try:
        release_date = datetime.strptime(
            str(candidate.get("tmdb_tw_release_date", "")), "%Y-%m-%d"
        ).date()
        if isinstance(audit_date, str):
            audit_date = datetime.strptime(audit_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return ""
    if release_date <= audit_date:
        return "now"
    if release_date > audit_date + timedelta(days=ATMOVIES_HANDOFF_DAYS):
        return "far"
    return "handoff"


def absence_miss_limit(candidate, release_date, audit_date):
    """舊列沿用原門檻；完成新制跨院線稽核後才切換為一次缺席。"""
    if sheet_value_is_true(candidate.get("absence_audit_complete")):
        return NOW_ATMOVIES_MISS_LIMIT if release_date <= audit_date else SOON_ATMOVIES_MISS_LIMIT
    return (
        LEGACY_NOW_ATMOVIES_MISS_LIMIT
        if release_date <= audit_date
        else LEGACY_SOON_ATMOVIES_MISS_LIMIT
    )


def candidate_miss_limit(candidate, audit_date):
    try:
        release_date = datetime.strptime(
            str(candidate.get("tmdb_tw_release_date", "")), "%Y-%m-%d"
        ).date()
        if isinstance(audit_date, str):
            audit_date = datetime.strptime(audit_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    return absence_miss_limit(candidate, release_date, audit_date)


def candidate_has_cinema_presence(candidate):
    return (
        sheet_value_is_true(candidate.get("atmovies_present"))
        or sheet_value_is_true(candidate.get("cinema_present"))
    )


def should_hide_for_absence(candidate, release_date, today, manual_ids):
    """判斷一般候選是否已在完整跨院線稽核中達到缺席門檻。"""
    if candidate.get("tmdb_id") in manual_ids:
        return False
    if release_date > today + timedelta(days=ATMOVIES_HANDOFF_DAYS):
        return False
    if candidate_has_cinema_presence(candidate):
        return False
    return nonnegative_miss_count(candidate) >= absence_miss_limit(
        candidate, release_date, today
    )


def rerelease_is_hidden(candidate):
    return sheet_value_is_true(candidate.get("hidden"))


def rerelease_can_override_regular(candidate):
    """只有未隱藏且影城日期經 TMDB 驗證的重映候選可覆蓋一般候選。"""
    if candidate.get("candidate_kind") != "rerelease" or rerelease_is_hidden(candidate):
        return False
    cinema_date = str(candidate.get("cinema_release_date", "") or "").strip()
    tmdb_date = str(candidate.get("tmdb_tw_release_date", "") or "").strip()
    return (
        bool(cinema_date)
        and candidate.get("tmdb_date_status") == "confirmed"
        and tmdb_date == cinema_date
    )


def candidate_priority(candidate):
    if rerelease_can_override_regular(candidate):
        return 2
    if candidate.get("candidate_kind") == "rerelease":
        return 0
    return 1


def allows_continuous_theatrical_run(candidate, release_date, today):
    """已發布且未達缺席門檻的首輪片，可超過 180 天持續公開。"""
    if candidate.get("candidate_kind") == "rerelease" or release_date > today:
        return False
    if sheet_value_is_true(candidate.get("reappeared_after_hidden")):
        return False
    if nonnegative_miss_count(candidate) >= absence_miss_limit(
        candidate, release_date, today
    ):
        return False
    if sheet_value_is_true(candidate.get("ever_published")):
        return True
    return (
        "ever_published" not in candidate
        and sheet_value_is_true(candidate.get("atmovies_present"))
        and release_date >= today - timedelta(days=365)
    )
