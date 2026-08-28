"""Shared candidate-retention rules used by audit publishing and site refresh."""


NOW_ATMOVIES_MISS_LIMIT = 1
SOON_ATMOVIES_MISS_LIMIT = 1
LEGACY_NOW_ATMOVIES_MISS_LIMIT = 2
LEGACY_SOON_ATMOVIES_MISS_LIMIT = 5


def sheet_value_is_true(value, default=False):
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def absence_miss_limit(candidate, release_date, audit_date):
    """舊列沿用原門檻；完成新制跨院線稽核後才切換為一次缺席。"""
    if sheet_value_is_true(candidate.get("absence_audit_complete")):
        return NOW_ATMOVIES_MISS_LIMIT if release_date <= audit_date else SOON_ATMOVIES_MISS_LIMIT
    return (
        LEGACY_NOW_ATMOVIES_MISS_LIMIT
        if release_date <= audit_date
        else LEGACY_SOON_ATMOVIES_MISS_LIMIT
    )
