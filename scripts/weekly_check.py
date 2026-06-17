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
# NOW 改爬「首輪 List」分頁(有準確上映日期和廳數)
ATMOVIES_NOW_BASE = "http://www.atmovies.com.tw/movie/now/1/"
# NEXT 改爬週次分頁列表(從 next 主頁抓取所有 w 連結)
ATMOVIES_NEXT_INDEX = "http://www.atmovies.com.tw/movie/next/"
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


def fetch_now_all_pages():
    """爬 NOW 首輪 List 的所有分頁,直到找不到 ~MORE~ 連結為止"""
    all_html = []
    url = ATMOVIES_NOW_BASE
    page_num = 1
    max_pages = 6  # 安全機制,避免無限迴圈

    while page_num <= max_pages:
        log(f"Fetching NOW page {page_num}: {url}")
        html = fetch_atmovies(url)
        all_html.append(html)

        # 在 HTML 中找下一頁的連結
        # 開眼用 "~MORE~更多影片" 標示下一頁
        soup = BeautifulSoup(html, "html.parser")

        # 開眼用 onclick="grabFile('/movie/...')" 來翻頁
        # 不是普通 href,要從 onclick 屬性抓
        next_link = None
        for a in soup.find_all("a"):
            text = a.get_text(strip=True)
            onclick = a.get("onclick", "")
            if "MORE" in text and "grabFile" in onclick:
                # 從 onclick="grabFile('/movie/movie2_now_2.html','LA-more');" 抓出 URL
                match = re.search(r"grabFile\(['\"]([^'\"]+)['\"]", onclick)
                if match:
                    next_link = match.group(1)
                    break

        if not next_link:
            log(f"NOW: no more pages after page {page_num}")
            break

        # 組出絕對 URL
        if next_link.startswith("/"):
            url = "http://www.atmovies.com.tw" + next_link
        elif next_link.startswith("http"):
            url = next_link
        else:
            url = "http://www.atmovies.com.tw/movie/" + next_link

        page_num += 1
        time.sleep(SCRAPE_DELAY)

    log(f"NOW: fetched {page_num} pages total")
    return all_html


def fetch_next_all_weeks():
    """爬 NEXT 主頁取得所有週次分頁的 URL,然後個別爬每個週次分頁"""
    all_html = []

    # 1. 爬主頁找所有 wXX 連結
    log(f"Fetching NEXT index: {ATMOVIES_NEXT_INDEX}")
    index_html = fetch_atmovies(ATMOVIES_NEXT_INDEX)
    soup = BeautifulSoup(index_html, "html.parser")

    # 用 set 去重(主頁可能多處列出同一連結)
    week_links = set()
    for a in soup.find_all("a"):
        href = a.get("href", "")
        # 匹配 /movie/next/w23/ 這種格式
        match = re.match(r".*?(/movie/next/w\d+/?)$", href)
        if match:
            week_links.add(match.group(1))

    log(f"NEXT: found {len(week_links)} week pages")

    # 2. 個別爬每個週次分頁
    for week_path in sorted(week_links):
        time.sleep(SCRAPE_DELAY)
        url = "http://www.atmovies.com.tw" + week_path
        log(f"Fetching NEXT week: {url}")
        html = fetch_atmovies(url)
        all_html.append(html)

    log(f"NEXT: fetched {len(all_html)} week pages total")
    return all_html


def parse_now(html_pages):
    """解析首輪 List 多分頁的所有電影
    Args:
        html_pages: list[str],每個元素是一個分頁的 HTML
    Returns:
        list[dict]: 包含每部電影的資訊
    """
    movies = []
    seen_ids = set()

    for html in html_pages:
        soup = BeautifulSoup(html, "html.parser")

        # 找所有 <article class="filmList"> (首輪 List 每部電影一個 article)
        articles = soup.find_all("article", class_="filmList")

        for article in articles:
            # 找片名連結
            title_div = article.find("div", class_="filmTitle")
            if not title_div:
                continue

            link = title_div.find("a")
            if not link:
                continue

            href = link.get("href", "")
            movie_id = extract_atmovies_id(href)
            if not movie_id:
                continue

            # 去重(以防同部片出現在多個分頁)
            if movie_id in seen_ids:
                continue
            seen_ids.add(movie_id)

            # 提取中文片名 + 英文片名
            # 開眼的格式: "中文片名 English Title"
            # 中文部分(到第一個空格或英文字之前)是中文片名
            full_title = link.get_text(strip=True)

            # 簡單分離: 找第一個英文/數字字元的位置
            match = re.search(r"[A-Za-z0-9]", full_title)
            if match and match.start() > 0:
                title_zh = full_title[:match.start()].strip()
                title_en = full_title[match.start():].strip()
            else:
                title_zh = full_title.strip()
                title_en = ""

            # 找上映日期和廳數 (在 <div class="runtime"> 標籤裡)
            release_date_tw = None
            screen_count = 0

            for runtime_div in article.find_all("div", class_="runtime"):
                text = runtime_div.get_text()

                # 找「上映日期:6/12/2026」
                date_match = re.search(r"上映日期[:：]\s*(\d{1,2}/\d{1,2}/\d{4})", text)
                if date_match:
                    date_str = date_match.group(1)
                    # 轉成 YYYY-MM-DD
                    parts = date_str.split("/")
                    if len(parts) == 3:
                        m, d, y = parts
                        release_date_tw = f"{y}-{m.zfill(2)}-{d.zfill(2)}"

                # 找「上映廳數 (89)」
                screen_match = re.search(r"上映廳數\s*\(?(\d+)\)?", text)
                if screen_match:
                    screen_count = int(screen_match.group(1))

            # 如果沒抓到日期,跳過這部
            if not release_date_tw:
                continue

            movies.append({
                "title_zh": title_zh,
                "title_en": title_en,
                "release_date_tw": release_date_tw,
                "screen_count": screen_count,
                "atmovies_id": movie_id,
                "atmovies_url": f"http://www.atmovies.com.tw{href}",
            })

    return movies


def parse_next(html_pages):
    """解析 NEXT 週次分頁的所有電影
    Args:
        html_pages: list[str],每個元素是一個週次分頁的 HTML
    Returns:
        list[dict]: 包含每部電影的資訊
    """
    movies = []
    seen_ids = set()

    for html in html_pages:
        soup = BeautifulSoup(html, "html.parser")

        articles = soup.find_all("article", class_="filmList")

        for article in articles:
            title_div = article.find("div", class_="filmTitle")
            if not title_div:
                continue

            link = title_div.find("a")
            if not link:
                continue

            href = link.get("href", "")
            movie_id = extract_atmovies_id(href)
            if not movie_id:
                continue

            if movie_id in seen_ids:
                continue
            seen_ids.add(movie_id)

            full_title = link.get_text(strip=True)

            match = re.search(r"[A-Za-z0-9]", full_title)
            if match and match.start() > 0:
                title_zh = full_title[:match.start()].strip()
                title_en = full_title[match.start():].strip()
            else:
                title_zh = full_title.strip()
                title_en = ""

            release_date_tw = None
            screen_count = 0

            for runtime_div in article.find_all("div", class_="runtime"):
                text = runtime_div.get_text()

                date_match = re.search(r"上映日期[:：]\s*(\d{1,2}/\d{1,2}/\d{4})", text)
                if date_match:
                    date_str = date_match.group(1)
                    parts = date_str.split("/")
                    if len(parts) == 3:
                        m, d, y = parts
                        release_date_tw = f"{y}-{m.zfill(2)}-{d.zfill(2)}"

                screen_match = re.search(r"上映廳數\s*\(?(\d+)\)?", text)
                if screen_match:
                    screen_count = int(screen_match.group(1))

            if not release_date_tw:
                continue

            movies.append({
                "title_zh": title_zh,
                "title_en": title_en,
                "release_date_tw": release_date_tw,
                "screen_count": screen_count,
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
        # NOW: 爬首輪 List + 翻頁 (約 2-4 頁)
        now_pages = fetch_now_all_pages()
        time.sleep(SCRAPE_DELAY)
        # NEXT: 從主頁抓所有 wXX 連結, 個別爬每個週次分頁
        next_pages = fetch_next_all_weeks()
    except Exception as e:
        log(f"FATAL: failed to fetch atmovies: {e}")
        sys.exit(1)

    movies_now = parse_now(now_pages)
    movies_next = parse_next(next_pages)
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

    # 產出 tw-whitelist.json 給網站使用 (精簡版,只有 TMDB ID + TW 上映日期)
    whitelist_path = OUTPUT_DIR / "tw-whitelist.json"
    whitelist_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tmdb_ids": []
    }

    # 從 tmdb_has_tw_date bucket 抓出所有有 TMDB ID 的片
    for m in output["tmdb_has_tw_date"]:
        if m.get("tmdb_id"):
            whitelist_data["tmdb_ids"].append(m["tmdb_id"])

    # 從 missing_tw_date bucket 也抓 (這些片有 TMDB 條目,只是缺 TW date)
    for m in output["missing_tw_date"]:
        if m.get("tmdb_id"):
            whitelist_data["tmdb_ids"].append(m["tmdb_id"])

    # 去重並排序
    whitelist_data["tmdb_ids"] = sorted(set(whitelist_data["tmdb_ids"]))

    with open(whitelist_path, "w", encoding="utf-8") as f:
        json.dump(whitelist_data, f, ensure_ascii=False, indent=2)
    log(f"Whitelist written to: {whitelist_path} ({len(whitelist_data['tmdb_ids'])} ids)")


if __name__ == "__main__":
    main()
