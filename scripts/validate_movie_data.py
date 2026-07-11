#!/usr/bin/env python3
"""
Validate generated MovieNotice static data before publishing it to the site.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MOVIE_DATA = ROOT_DIR / "data" / "movie-data.json"
DEFAULT_MISSING_DATA = ROOT_DIR / "data" / "missing-tw-dates.json"


def log(message):
    print(message, file=sys.stderr)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def movie_count(payload):
    movies = payload.get("movies", {})
    return len(movies.get("now", [])) + len(movies.get("soon", []))


def validate_movie(movie, bucket, index, errors):
    label = f"{bucket}[{index}]"
    if not isinstance(movie, dict):
        errors.append(f"{label} is not an object")
        return

    if not movie.get("id"):
        errors.append(f"{label} missing id")
    if not str(movie.get("titleZh", "")).strip():
        errors.append(f"{label} missing titleZh")
    if not parse_date(movie.get("releaseDate")):
        errors.append(f"{label} has invalid releaseDate: {movie.get('releaseDate')!r}")


def validate_payload(payload, previous_payload, min_now, min_soon, min_total, max_drop_ratio):
    errors = []
    warnings = []

    movies = payload.get("movies")
    if not isinstance(movies, dict):
        errors.append("movies must be an object")
        movies = {}

    now = movies.get("now", [])
    soon = movies.get("soon", [])
    if not isinstance(now, list):
        errors.append("movies.now must be a list")
        now = []
    if not isinstance(soon, list):
        errors.append("movies.soon must be a list")
        soon = []

    now_count = len(now)
    soon_count = len(soon)
    total_count = now_count + soon_count

    summary = payload.get("summary", {})
    if summary.get("now_count") != now_count:
        errors.append(f"summary.now_count={summary.get('now_count')} but movies.now has {now_count}")
    if summary.get("soon_count") != soon_count:
        errors.append(f"summary.soon_count={summary.get('soon_count')} but movies.soon has {soon_count}")

    if now_count < min_now:
        errors.append(f"now_count {now_count} is below minimum {min_now}")
    if soon_count < min_soon:
        errors.append(f"soon_count {soon_count} is below minimum {min_soon}")
    if total_count < min_total:
        errors.append(f"total_count {total_count} is below minimum {min_total}")

    seen_ids = {}
    for bucket, items in (("now", now), ("soon", soon)):
        for index, movie in enumerate(items, 1):
            validate_movie(movie, bucket, index, errors)
            movie_id = movie.get("id") if isinstance(movie, dict) else None
            if movie_id:
                if movie_id in seen_ids:
                    errors.append(f"duplicate movie id {movie_id} in {seen_ids[movie_id]} and {bucket}[{index}]")
                seen_ids[movie_id] = f"{bucket}[{index}]"

    if previous_payload:
        previous_total = movie_count(previous_payload)
        if previous_total:
            allowed_min = int(previous_total * max_drop_ratio)
            if total_count < allowed_min:
                errors.append(
                    f"total_count {total_count} dropped below {max_drop_ratio:.0%} of previous total {previous_total}"
                )

    generated_at = payload.get("generated_at", "")
    if not generated_at:
        warnings.append("generated_at is missing")

    return {
        "now_count": now_count,
        "soon_count": soon_count,
        "total_count": total_count,
        "errors": errors,
        "warnings": warnings,
    }


def validate_missing_payload(path, max_missing_tw_date, max_tmdb_not_found):
    if not path.exists():
        return [], [f"{path} does not exist; skipped missing/TMDB-not-found checks"]

    payload = load_json(path)
    errors = []
    warnings = []
    missing_tw_date = payload.get("missing_tw_date", [])
    tmdb_not_found = payload.get("tmdb_not_found", [])

    if len(missing_tw_date) > max_missing_tw_date:
        errors.append(f"missing_tw_date count {len(missing_tw_date)} exceeds maximum {max_missing_tw_date}")
    if len(tmdb_not_found) > max_tmdb_not_found:
        errors.append(f"tmdb_not_found count {len(tmdb_not_found)} exceeds maximum {max_tmdb_not_found}")

    return errors, warnings


def parse_args():
    parser = argparse.ArgumentParser(description="Validate generated MovieNotice data.")
    parser.add_argument("--movie-data", default=str(DEFAULT_MOVIE_DATA))
    parser.add_argument("--previous-movie-data", default="")
    parser.add_argument("--missing-data", default=str(DEFAULT_MISSING_DATA))
    parser.add_argument("--min-now", type=int, default=20)
    parser.add_argument("--min-soon", type=int, default=20)
    parser.add_argument("--min-total", type=int, default=50)
    parser.add_argument("--max-drop-ratio", type=float, default=0.5)
    parser.add_argument("--max-missing-tw-date", type=int, default=40)
    parser.add_argument("--max-tmdb-not-found", type=int, default=40)
    return parser.parse_args()


def main():
    args = parse_args()
    payload = load_json(Path(args.movie_data))
    previous_payload = load_json(Path(args.previous_movie_data)) if args.previous_movie_data else None

    result = validate_payload(
        payload,
        previous_payload,
        args.min_now,
        args.min_soon,
        args.min_total,
        args.max_drop_ratio,
    )
    missing_errors, missing_warnings = validate_missing_payload(
        Path(args.missing_data),
        args.max_missing_tw_date,
        args.max_tmdb_not_found,
    )
    result["errors"].extend(missing_errors)
    result["warnings"].extend(missing_warnings)

    log(
        "Movie data validation: "
        f"now={result['now_count']}, soon={result['soon_count']}, total={result['total_count']}"
    )
    for warning in result["warnings"]:
        log(f"WARNING: {warning}")
    for error in result["errors"]:
        log(f"ERROR: {error}")

    if result["errors"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
