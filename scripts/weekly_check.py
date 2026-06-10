#!/usr/bin/env python3
"""
MovieNotice weekly check
爬開眼電影網,比對 TMDB 看哪些電影缺台灣上映日期
"""

import os
import re
import sys
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# 設定區塊
CONTACT_EMAIL = "quietcron@gmail.com"
USER_AGENT = f"MovieNotice-DataChecker/1.0 (+{CONTACT_EMAIL})"
ATMOVIES_NOW = "http://www.atmovies.com.tw/movie/now/"
ATMOVIES_NEXT = "http://www.atmovies.com.tw/movie/next/"
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_DELAY = 0.3
SCRAPE_DELAY = 2

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "missing-tw-dates.json"

# 載入 TMDB API key
load_dotenv(Path(__file__).resolve().parent / ".env")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
if not TMDB_API_KEY:
    print("ERROR: TMDB_API_KEY not set in .env", file=sys.stderr)
    sys.exit(1)


def log(msg):
    print(msg, file=sys.stderr)


def normalize_date(s):
    """把 2026/5/27 或 2026/06/03 轉成 2026-05-27"""
    s = s.strip()
    m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", s)
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def extract_atmovies_id(href):
    """從 /movie/fben26657236/ 取出 fben26657236"""
    m = re.search(r"f[a-z]{3}\d{8}", href)
    return m.group(0) if m else None


def fetch_atmovies(url):
    """抓開眼頁面 HTML"""
    log(f"Fetching {url}")
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()

    raw_bytes = r.content

    # 先從 HTML head 抓 meta charset
    detected = None
    head_chunk = raw_bytes[:2048].decode("ascii", errors="ignore").lower()
    if "charset=utf-8" in head_chunk:
        detected = "utf-8"
    elif "charset=big5" in head_chunk:
        detected = "big5-hkscs"

    # 沒抓到就讓 chardet 偵測
    if not detected:
        detected = r.apparent_encoding or "utf-8"

    log(f"  Detected encoding: {detected}")

    try:
        return raw_bytes.decode(detected, errors="replace")
    except LookupError:
        return raw_bytes.decode("utf-8", errors="replace")


def parse_now(html):
    """解析現正熱映 ul.filmListPA"""
    soup = BeautifulSoup(html, "html.parser")
    ul = soup.find("ul", class_="filmListPA")
    movies = []
    if not ul:
        log("WARN: filmListPA not found in NOW page")
        return movies
    for li in ul.find_all("li", recursive=False):
        a = li.find("a")
        runtime = li.find("span", class_="runtime")
        if not a or not runtime:
            continue
        title = a.get_text(strip=True)
        href = a.get("href", "")
        movie_id = extract_atmovies_id(href)
        date = normalize_date(runtime.get_text())
        if title and movie_id and date:
            movies.append({
                "title_zh": title,
                "release_date_tw": date,
                "atmovies_id": movie_id,
                "atmovies_url": f"http://www.atmovies.com.tw{href}",
            })
    return movies


def parse_next(html):
    """解析即將上映 ul.filmListAllX"""
    soup = BeautifulSoup(html, "html.parser")
    ul = soup.find("ul", class_="filmListAllX")
    movies = []
    if not ul:
        log("WARN: filmListAllX not found in NEXT page")
        return movies
    for li in ul.find_all("li", recursive=False):
        title_div = li.find("div", class_="filmtitle")
        runtime_div = li.find("div", class_="runtime")
        if not title_div or not runtime_div:
            continue
        a = title_div.find("a")
        if not a:
            continue
        title = a.get_text(strip=True)
        href = a.get("href", "")
        movie_id = extract_atmovies_id(href)
        date_a = runtime_div.find("a")
        date_text = date_a.get_text() if date_a else runtime_div.get_text()
        date = normalize_date(date_text)
        if title and movie_id and date:
            movies.append({
                "title_zh": title,
                "release_date_tw": date,
                "atmovies_id": movie_id,
                "atmovies_url": f"http://www.atmovies.com.tw{href}",
            })
    return movies


def tmdb_search(title, year=None):
    """用片名搜 TMDB"""
    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "language": "zh-TW",
        "region": "TW",
    }
    if year:
        params["year"] = year
    try:
        r = requests.get(f"{TMDB_BASE}/search/movie", params=params, timeout=15)
        r.raise_for_status()
        results = r.json().get("results", [])
        return results[0] if results else None
    except Exception as e:
        log(f"  TMDB search failed for '{title}': {e}")
        return None


def tmdb_release_dates(tmdb_id):
    """查 release_dates"""
    try:
        r = requests.get(
            f"{TMDB_BASE}/movie/{tmdb_id}/release_dates",
            params={"api_key": TMDB_API_KEY},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception as e:
        log(f"  TMDB release_dates failed for id={tmdb_id}: {e}")
        return []


def has_tw_release(release_results):
    """檢查有沒有 TW"""
    for entry in release_results:
        if entry.get("iso_3166_1") == "TW":
            return True
    return False


def main():
    try:
        html_now = fetch_atmovies(ATMOVIES_NOW)
        time.sleep(SCRAPE_DELAY)
        html_next = fetch_atmovies(ATMOVIES_NEXT)
    except Exception as e:
        log(f"FATAL: failed to fetch atmovies: {e}")
        sys.exit(1)

    movies_now = parse_now(html_now)
    movies_next = parse_next(html_next)
    log(f"Scraped NOW: {len(movies_now)} movies")
    log(f"Scraped NEXT: {len(movies_next)} movies")

    all_movies = movies_now + movies_next
    seen = set()
    unique = []
    for m in all_movies:
        if m["atmovies_id"] in seen:
            continue
        seen.add(m["atmovies_id"])
        unique.append(m)
    log(f"Unique movies: {len(unique)}")

    tmdb_not_found = []
    tmdb_has_tw_date = []
    missing_tw_date = []

    for i, movie in enumerate(unique, 1):
        log(f"[{i}/{len(unique)}] {movie['title_zh']} ({movie['release_date_tw']})")
        year = int(movie["release_date_tw"][:4])

        result = tmdb_search(movie["title_zh"], year=year)
        time.sleep(TMDB_DELAY)

        if not result:
            result = tmdb_search(movie["title_zh"])
            time.sleep(TMDB_DELAY)

        if not result:
            tmdb_not_found.append(movie)
            continue

        tmdb_id = result["id"]
        tmdb_title = result.get("title") or result.get("original_title", "")
        tmdb_year = (result.get("release_date") or "")[:4]

        release_results = tmdb_release_dates(tmdb_id)
        time.sleep(TMDB_DELAY)

        record = {
            **movie,
            "tmdb_id": tmdb_id,
            "tmdb_url": f"https://www.themoviedb.org/movie/{tmdb_id}",
            "tmdb_title": tmdb_title,
            "tmdb_release_year": tmdb_year,
        }

        if has_tw_release(release_results):
            tmdb_has_tw_date.append(record)
        else:
            missing_tw_date.append(record)

    tz = timezone(timedelta(hours=8))
    output = {
        "generated_at": datetime.now(tz).isoformat(),
        "source": "atmovies.com.tw",
        "summary": {
            "total_scraped": len(unique),
            "tmdb_not_found": len(tmdb_not_found),
            "tmdb_has_tw_date": len(tmdb_has_tw_date),
            "missing_tw_date": len(missing_tw_date),
        },
        "missing_tw_date": missing_tw_date,
        "tmdb_not_found": tmdb_not_found,
        "tmdb_has_tw_date": tmdb_has_tw_date,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log("")
    log("=== Summary ===")
    log(f"Total scraped: {len(unique)}")
    log(f"TMDB not found: {len(tmdb_not_found)}")
    log(f"TMDB has TW date: {len(tmdb_has_tw_date)}")
    log(f"Missing TW date (NEEDS UPDATE): {len(missing_tw_date)}")
    log(f"\nOutput written to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
