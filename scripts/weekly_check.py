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
import difflib
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
try:
    from opencc import OpenCC
except ImportError:
    OpenCC = None

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
TSV_LOOKBACK_DAYS = 14

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "missing-tw-dates.json"
OVERRIDES_FILE = OUTPUT_DIR / "tmdb-overrides.json"
ATMOVIES_CANDIDATES_FILE = OUTPUT_DIR / "atmovies-candidates.json"
MOVIE_DATA_FILE = OUTPUT_DIR / "movie-data.json"
MANUAL_RELEASES_FILE = OUTPUT_DIR / "manual-releases.json"
IMG_W = "https://image.tmdb.org/t/p/w500"
IMG_BG = "https://image.tmdb.org/t/p/w1280"
NOW_LOOKBACK_DAYS = 180
SOON_WINDOW_DAYS = 180
GENRE_MAP = {
    "动作": "動作",
    "冒险": "冒險",
    "喜剧": "喜劇",
    "犯罪": "犯罪",
    "纪录片": "紀錄片",
    "剧情": "劇情",
    "家庭": "家庭",
    "奇幻": "奇幻",
    "历史": "歷史",
    "恐怖": "恐怖",
    "音乐": "音樂",
    "悬疑": "懸疑",
    "爱情": "愛情",
    "科幻": "科幻",
    "电视电影": "電視電影",
    "惊悚": "驚悚",
    "战争": "戰爭",
    "西部": "西部",
    "动画": "動畫",
    "传记": "傳記",
    "运动": "運動",
    "歌舞": "歌舞",
    "武侠": "武俠",
    "古装": "古裝",
    "记录片": "紀錄片",
    "纪录": "紀錄",
    "记录": "紀錄",
}

# 載入 TMDB API key
load_dotenv(Path(__file__).resolve().parent / ".env")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
OMDB_API_KEYS = [
    item.strip()
    for item in os.environ.get("OMDB_API_KEYS", "").split(",")
    if item.strip()
]
if not TMDB_API_KEY:
    print("ERROR: TMDB_API_KEY not set in .env", file=sys.stderr)
    sys.exit(1)

if OpenCC is None:
    print("ERROR: opencc-python-reimplemented not installed. Run: pip install -r scripts/requirements.txt", file=sys.stderr)
    sys.exit(1)

TRADITIONAL_CONVERTER = OpenCC("s2twp")


def log(msg):
    print(msg, file=sys.stderr)


def to_traditional_text(value):
    return TRADITIONAL_CONVERTER.convert(value) if isinstance(value, str) else value


def to_traditional_data(value):
    if isinstance(value, str):
        return to_traditional_text(value)
    if isinstance(value, list):
        return [to_traditional_data(item) for item in value]
    if isinstance(value, dict):
        return {key: to_traditional_data(item) for key, item in value.items()}
    return value


def write_traditional_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_traditional_data(payload), f, ensure_ascii=False, indent=2)


def parse_iso_date(value):
    """把 YYYY-MM-DD 轉成 date; 失敗回傳 None"""
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def extract_atmovies_id(href):
    """從 /movie/fben26657236/ 取出 fben26657236"""
    m = re.search(r"f[a-z]{3}\d{8}", href)
    return m.group(0) if m else None


def split_atmovies_title(full_title):
    """拆開眼片名成中文/英文,但保留像「哆啦A夢」這種中英混寫中文名"""
    full_title = (full_title or "").strip()
    if not full_title:
        return "", ""

    match = re.match(
        r"^(?P<title_zh>.+?)\s+(?P<title_en>[A-Za-z0-9][A-Za-z0-9\s\-–—:：'\"!?,.&／/·・()\[\]{}]+)$",
        full_title,
    )
    if not match:
        return full_title, ""

    title_zh = match.group("title_zh").strip()
    title_en = match.group("title_en").strip()
    return title_zh or full_title, title_en


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

            title_zh, title_en = split_atmovies_title(full_title)

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
                "source_bucket": "now",
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

            title_zh, title_en = split_atmovies_title(full_title)

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
                "source_bucket": "next",
            })

    return movies


def normalize_title_key(text):
    """做寬鬆比對用的片名正規化"""
    text = (text or "").strip().lower()
    text = re.sub(r"[\s\-–—:：'\"!?,.!&／/·・()\[\]{}]+", "", text)
    return text


def to_trad_genre(genre):
    return GENRE_MAP.get(genre, genre)


def normalize_genres(genres):
    seen = set()
    result = []
    for genre in genres:
        trad = to_trad_genre(genre)
        if not trad or trad in seen:
            continue
        seen.add(trad)
        result.append(trad)
    return result


def title_similarity(a, b):
    """0~1 片名相似度"""
    a_norm = normalize_title_key(a)
    b_norm = normalize_title_key(b)
    if not a_norm or not b_norm:
        return 0.0
    if a_norm == b_norm:
        return 1.0
    if a_norm in b_norm or b_norm in a_norm:
        shorter = min(len(a_norm), len(b_norm))
        longer = max(len(a_norm), len(b_norm))
        return shorter / longer if longer else 0.0
    return difflib.SequenceMatcher(None, a_norm, b_norm).ratio()


def tmdb_search(title, year=None):
    """用片名搜 TMDB,回傳候選清單"""
    if not title:
        return []
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
        return r.json().get("results", [])
    except Exception as e:
        log(f"  TMDB search failed for '{title}': {e}")
        return []


def score_tmdb_candidate(movie, candidate):
    """對單一 TMDB 候選打分"""
    score = 0.0
    title_zh = movie.get("title_zh", "")
    title_en = movie.get("title_en", "")
    candidate_title = candidate.get("title") or ""
    candidate_original = candidate.get("original_title") or ""
    zh_norm = normalize_title_key(title_zh)
    en_norm = normalize_title_key(title_en)
    candidate_title_norm = normalize_title_key(candidate_title)
    candidate_original_norm = normalize_title_key(candidate_original)

    zh_title_score = max(
        title_similarity(title_zh, candidate_title),
        title_similarity(title_zh, candidate_original),
    )
    en_title_score = max(
        title_similarity(title_en, candidate_title),
        title_similarity(title_en, candidate_original),
    )

    if zh_title_score == 1.0:
        score += 45
    else:
        score += zh_title_score * 35

    if zh_norm and (
        candidate_title_norm.startswith(zh_norm)
        or candidate_original_norm.startswith(zh_norm)
    ):
        score += 20

    if title_en:
        if en_title_score == 1.0:
            score += 80
        else:
            score += en_title_score * 60
    elif len(normalize_title_key(title_zh)) <= 2 and zh_title_score < 0.95:
        # 中文超短片名在沒有英文輔助時很容易誤配,先保守扣分
        score -= 15

    release_date = candidate.get("release_date") or ""
    candidate_year = int(release_date[:4]) if len(release_date) >= 4 and release_date[:4].isdigit() else None
    target_year = int(movie["release_date_tw"][:4]) if movie.get("release_date_tw") else None
    if target_year and candidate_year:
        year_gap = abs(candidate_year - target_year)
        strong_title_match = zh_title_score >= 0.95 or en_title_score >= 0.95
        if year_gap == 0:
            score += 25
        elif year_gap == 1:
            score += 10
        elif year_gap >= 3:
            penalty = min(45, year_gap * 12)
            if strong_title_match:
                penalty = min(12, max(4, year_gap * 2))
            score -= penalty

    if title_en and en_title_score < 0.45:
        score -= 25
    if title_zh and zh_title_score < 0.30 and not (
        zh_norm and (
            candidate_title_norm.startswith(zh_norm)
            or candidate_original_norm.startswith(zh_norm)
        )
    ):
        score -= 20

    popularity = candidate.get("popularity") or 0
    score += min(8, popularity / 50.0)

    return score


def tmdb_candidate_match_diagnostics(movie, candidate, score):
    """回傳已接受 TMDB 配對的人工複查理由。"""
    reasons = []
    title_zh = movie.get("title_zh", "")
    title_en = movie.get("title_en", "")
    candidate_title = candidate.get("title") or ""
    candidate_original = candidate.get("original_title") or ""

    zh_title_score = max(
        title_similarity(title_zh, candidate_title),
        title_similarity(title_zh, candidate_original),
    )
    en_title_score = max(
        title_similarity(title_en, candidate_title),
        title_similarity(title_en, candidate_original),
    ) if title_en else 1.0

    release_date = candidate.get("release_date") or ""
    candidate_year = int(release_date[:4]) if len(release_date) >= 4 and release_date[:4].isdigit() else None
    target_year = int(movie["release_date_tw"][:4]) if movie.get("release_date_tw") else None

    if score < 55:
        reasons.append(f"配對分數偏低 {score:.1f}")
    if target_year and candidate_year:
        year_gap = abs(candidate_year - target_year)
        if year_gap >= 2:
            reasons.append(f"開眼年份 {target_year} / TMDB 年份 {candidate_year}")
    # TMDB 的 original_title 常是日文、韓文等原語片名，不一定是開眼列出的
    # 國際英文片名。英文相似度偏低不能單獨視為可疑；中文也偏低時才提醒。
    if title_en and en_title_score < 0.55 and zh_title_score < 0.45:
        reasons.append(f"英文片名相似度偏低 {en_title_score:.2f}")
    if title_zh and zh_title_score < 0.45:
        reasons.append(f"中文片名相似度偏低 {zh_title_score:.2f}")

    return reasons


def choose_tmdb_match(movie):
    """綜合中文/英文搜尋結果後挑最合理的 TMDB 候選"""
    query_year = int(movie["release_date_tw"][:4]) if movie.get("release_date_tw") else None
    candidates = {}

    search_queries = [movie.get("title_zh", "")]
    title_en = movie.get("title_en", "").strip()
    if title_en:
        search_queries.append(title_en)

    for query in search_queries:
        for result in tmdb_search(query, year=query_year):
            candidates[result["id"]] = result
        time.sleep(TMDB_DELAY)

    if query_year:
        for query in search_queries:
            for result in tmdb_search(query):
                candidates[result["id"]] = result
            time.sleep(TMDB_DELAY)

    if not candidates:
        return None

    ranked = sorted(
        (
            {
                "score": score_tmdb_candidate(movie, candidate),
                "candidate": candidate,
            }
            for candidate in candidates.values()
        ),
        key=lambda item: item["score"],
        reverse=True,
    )

    best = ranked[0]
    if best["score"] < 35:
        log(
            f"  TMDB ambiguous match for '{movie['title_zh']}'"
            f" best={best['candidate'].get('title', '')} score={best['score']:.1f}"
        )
        return None

    log(
        f"  TMDB match: {best['candidate'].get('title', '')}"
        f" (id={best['candidate']['id']}, score={best['score']:.1f})"
    )
    candidate = dict(best["candidate"])
    candidate["_match_score"] = best["score"]
    candidate["_match_suspicious_reasons"] = tmdb_candidate_match_diagnostics(
        movie,
        best["candidate"],
        best["score"],
    )
    return candidate


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


def extract_tw_theatrical_date_from_results(release_results):
    """從 /release_dates 結果取出台灣院線上映日。"""
    theatrical = extract_tw_theatrical_releases_from_results(release_results)
    return theatrical[-1]["date"] if theatrical else ""


def extract_tw_theatrical_releases_from_results(release_results):
    """取出台灣 type 3 上映紀錄，依日期由早到晚排列並去除重複項目。"""
    releases = []
    seen = set()
    for entry in release_results:
        if entry.get("iso_3166_1") != "TW":
            continue
        for item in entry.get("release_dates", []):
            if item.get("type") != 3:
                continue
            release_date = item.get("release_date", "")[:10]
            if not parse_iso_date(release_date):
                continue
            language = (item.get("iso_639_1") or "").lower()
            key = (release_date, language)
            if key in seen:
                continue
            seen.add(key)
            releases.append({"date": release_date, "language": language})
    releases.sort(key=lambda item: (item["date"], item["language"]))
    return releases


def releases_in_window(releases, start_date, end_date):
    """只保留網站有效顯示範圍內的上映紀錄。"""
    eligible = []
    for item in releases:
        release_date = parse_iso_date(item.get("date", ""))
        if release_date and start_date <= release_date <= end_date:
            eligible.append(item)
    return eligible


def load_tmdb_overrides():
    """載入人工覆寫的 TMDB 對照"""
    if not OVERRIDES_FILE.exists():
        return {}
    try:
        with open(OVERRIDES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        log(f"  Failed to load overrides: {e}")
        return {}


def tmdb_movie(tmdb_id):
    """直接用 TMDB ID 取單片資料"""
    try:
        r = requests.get(
            f"{TMDB_BASE}/movie/{tmdb_id}",
            params={"api_key": TMDB_API_KEY, "language": "zh-TW", "region": "TW"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log(f"  TMDB movie fetch failed for id={tmdb_id}: {e}")
        return None


def tmdb_movie_url(tmdb_id):
    """站內檢查用 TMDB 連結，固定帶 zh-TW"""
    return f"https://www.themoviedb.org/movie/{tmdb_id}?language=zh-TW"


def tmdb_movie_full(tmdb_id):
    """抓前端完整顯示用的 TMDB 單片資料"""
    try:
        r = requests.get(
            f"{TMDB_BASE}/movie/{tmdb_id}",
            params={
                "api_key": TMDB_API_KEY,
                "language": "zh-TW",
                "region": "TW",
                "append_to_response": "videos,credits,watch/providers,release_dates,external_ids",
            },
            timeout=20,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log(f"  TMDB full movie fetch failed for id={tmdb_id}: {e}")
        return None


def tmdb_discover(path, params, max_pages):
    """抓 TMDB discover 多頁結果"""
    out = []
    total_pages = 1
    for page in range(1, max_pages + 1):
        try:
            req_params = {
                "api_key": TMDB_API_KEY,
                "language": "zh-TW",
                "page": page,
            }
            req_params.update(params)
            r = requests.get(f"{TMDB_BASE}{path}", params=req_params, timeout=20)
            r.raise_for_status()
            data = r.json()
            total_pages = min(data.get("total_pages", 1), max_pages)
            out.extend(data.get("results", []))
            if page >= total_pages:
                break
            time.sleep(TMDB_DELAY)
        except Exception as e:
            log(f"  TMDB discover failed for page={page}: {e}")
            break
    return out


def extract_tw_theatrical_date(payload):
    """從 append_to_response 後的 release_dates 取出台灣院線上映日"""
    release_dates = payload.get("release_dates", {})
    return extract_tw_theatrical_date_from_results(release_dates.get("results", []))


def parse_watch_platforms(payload):
    providers = payload.get("watch/providers", {}).get("results", {}).get("TW", {})
    all_items = providers.get("flatrate", []) + providers.get("rent", []) + providers.get("buy", [])
    seen = set()
    out = []
    for item in all_items:
        name = item.get("provider_name")
        if not name or name in seen:
            continue
        seen.add(name)
        out.append({
            "name": name,
            "logo": item.get("logo_path") or "",
        })
    return out


def parse_cast(payload):
    out = []
    for item in payload.get("credits", {}).get("cast", [])[:8]:
        out.append({
            "name": item.get("name", ""),
            "char": item.get("character", ""),
            "photo": f"{IMG_W}{item['profile_path']}" if item.get("profile_path") else None,
        })
    return out


def parse_crew(payload):
    jobs = {"Director", "Screenplay", "Writer"}
    out = []
    for item in payload.get("credits", {}).get("crew", []):
        if item.get("job") not in jobs:
            continue
        out.append({
            "name": item.get("name", ""),
            "job": item.get("job", ""),
        })
        if len(out) >= 3:
            break
    return out


def pick_trailer_key(payload):
    videos = payload.get("videos", {}).get("results", [])
    trailer = None
    for item in videos:
        if item.get("type") == "Trailer" and item.get("site") == "YouTube":
            trailer = item
            break
    if not trailer and videos:
        trailer = videos[0]
    return trailer.get("key") if trailer else None


def parse_omdb_ratings(imdb_id):
    if not imdb_id or not OMDB_API_KEYS:
        return {"imdb": "", "rt": "", "mc": ""}
    for key in OMDB_API_KEYS:
        try:
            r = requests.get(
                "https://www.omdbapi.com/",
                params={"i": imdb_id, "apikey": key},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            if data.get("Response") == "False":
                continue
            imdb = data.get("imdbRating", "")
            imdb = imdb if imdb and imdb != "N/A" else ""
            rt = ""
            for item in data.get("Ratings", []):
                if item.get("Source") == "Rotten Tomatoes" and item.get("Value") != "N/A":
                    rt = item.get("Value", "")
                    break
            mc = data.get("Metascore", "")
            mc = mc if mc and mc != "N/A" else ""
            return {"imdb": imdb, "rt": rt, "mc": mc}
        except Exception:
            continue
    return {"imdb": "", "rt": "", "mc": ""}


def classify_release_bucket(record, release_date, today_local, tmdb_has_tw_date=True):
    if not release_date:
        return ""
    if record.get("source_bucket") == "manual":
        now_cutoff = today_local - timedelta(days=NOW_LOOKBACK_DAYS)
        if now_cutoff <= release_date <= today_local:
            return "now"
        if today_local + timedelta(days=1) <= release_date <= today_local + timedelta(days=SOON_WINDOW_DAYS):
            return "soon"
        return ""
    if record.get("source_bucket") == "now":
        now_cutoff = today_local - timedelta(days=NOW_LOOKBACK_DAYS)
        if tmdb_has_tw_date and now_cutoff <= release_date <= today_local:
            return "now"
        return ""
    if today_local + timedelta(days=1) <= release_date <= today_local + timedelta(days=SOON_WINDOW_DAYS):
        return "soon"
    return ""


def build_static_movie(record, payload, ratings):
    tmdb_id = record["tmdb_id"]
    title_zh = payload.get("title") or payload.get("original_title") or ""
    release_date = record.get("tmdb_tw_release_date") or extract_tw_theatrical_date(payload)
    theatrical_releases = record.get("tmdb_tw_release_dates") or []
    poster = f"{IMG_W}{payload['poster_path']}" if payload.get("poster_path") else ""
    backdrop = f"{IMG_BG}{payload['backdrop_path']}" if payload.get("backdrop_path") else ""
    genres = normalize_genres([item.get("name", "") for item in payload.get("genres", []) if item.get("name")])
    countries = [item.get("name", "") for item in payload.get("production_countries", []) if item.get("name")]
    platforms = parse_watch_platforms(payload)
    cast = parse_cast(payload)
    crew = parse_crew(payload)
    vote_average = payload.get("vote_average")
    vote_average = f"{vote_average:.1f}" if isinstance(vote_average, (int, float)) and vote_average > 0 else ""
    detail = {
        "duration": payload.get("runtime") or "",
        "genres": genres,
        "synopsis": payload.get("overview") or "",
        "poster": poster or None,
        "backdrop": backdrop or None,
        "voteAverage": vote_average,
        "trailerKey": pick_trailer_key(payload),
        "imdbId": payload.get("imdb_id") or payload.get("external_ids", {}).get("imdb_id", ""),
        "countries": countries,
        "cast": cast,
        "crew": crew,
        "budget": payload.get("budget") or 0,
        "revenue": payload.get("revenue") or 0,
        "status": payload.get("status") or "",
        "origLang": payload.get("original_language") or "",
        "origTitle": payload.get("original_title") or "",
        "platforms": platforms,
    }
    return {
        "id": tmdb_id,
        "titleZh": title_zh,
        "titleEn": payload.get("original_title") or record.get("title_en", ""),
        "releaseDate": release_date,
        "twTheatricalReleases": theatrical_releases,
        "twReleaseDateVerified": bool(release_date),
        "poster": poster or backdrop or None,
        "posterIsBackdrop": not bool(poster) and bool(backdrop),
        "backdrop": backdrop or None,
        "voteAverage": vote_average,
        "genre": genres,
        "duration": detail["duration"],
        "synopsis": detail["synopsis"],
        "imdb": ratings.get("imdb", ""),
        "rt": ratings.get("rt", ""),
        "mc": ratings.get("mc", ""),
        "trailerKey": detail["trailerKey"],
        "cast": cast,
        "crew": crew,
        "budget": detail["budget"],
        "revenue": detail["revenue"],
        "status": detail["status"],
        "origLang": detail["origLang"],
        "origTitle": detail["origTitle"],
        "platforms": platforms,
        "popularity": payload.get("popularity") or 0,
        "imdbId": detail["imdbId"],
        "countries": countries,
        "detail": detail,
        "tmdbUrl": tmdb_movie_url(tmdb_id),
        "atmoviesId": "",
        "atmoviesUrl": "",
        "sourceBucket": "tmdb",
    }


def should_keep_static_movie(movie, record):
    release_date = parse_iso_date(movie.get("releaseDate", ""))
    if not release_date:
        return False
    if record.get("source_bucket") != "manual" and not record.get("atmovies_id") and movie.get("platforms"):
        return False
    duration = movie.get("duration") or 0
    if duration and duration <= 60:
        return False
    return True


def load_manual_releases():
    """載入人工保留片清單；用來補開眼短暫下架或漏列的院線片"""
    if not MANUAL_RELEASES_FILE.exists():
        return []
    try:
        with open(MANUAL_RELEASES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        log(f"  Failed to load manual releases: {e}")
        return []


def dedup_discover_results(items):
    seen = set()
    out = []
    for item in items:
        tmdb_id = item.get("id")
        if not tmdb_id or tmdb_id in seen:
            continue
        seen.add(tmdb_id)
        out.append(item)
    return out


def fetch_supplemental_soon_candidates(today_local):
    """補抓開眼視窗外（第 61～180 天）的台灣院線候選片。

    Discover 只負責找候選 ID；公開前仍須逐片以 release_dates 驗證
    Taiwan theatrical (type 3) 日期。
    """
    far_future_start = (today_local + timedelta(days=61)).isoformat()
    far_future_end = (today_local + timedelta(days=SOON_WINDOW_DAYS)).isoformat()

    tw_results = tmdb_discover(
        "/discover/movie",
        {
            "release_date.gte": far_future_start,
            "release_date.lte": far_future_end,
            "sort_by": "release_date.asc",
            "with_release_type": "3",
            "region": "TW",
        },
        20,
    )
    return dedup_discover_results(tw_results)


def export_static_movie_data(output, generated_at_local):
    """輸出前端使用的完整靜態資料，避免瀏覽器直接打第三方 API"""
    movies = {"now": [], "soon": []}
    today_local = generated_at_local.date()
    # Public site data is intentionally restricted to movies whose TMDB
    # release_dates payload contains a Taiwan theatrical date.
    records = [(record, True) for record in output["tmdb_has_tw_date"]]
    existing_ids = set()

    for idx, (record, tmdb_has_tw_date) in enumerate(records, 1):
        tmdb_id = record.get("tmdb_id")
        if not tmdb_id:
            continue
        log(f"Static export [{idx}/{len(records)}] TMDB {tmdb_id}")
        payload = tmdb_movie_full(tmdb_id)
        if not payload:
            continue
        ratings = parse_omdb_ratings(payload.get("imdb_id") or payload.get("external_ids", {}).get("imdb_id", ""))
        movie = build_static_movie(record, payload, ratings)
        if not should_keep_static_movie(movie, record):
            continue
        bucket = classify_release_bucket(
            record,
            parse_iso_date(movie.get("releaseDate", "")),
            today_local,
            tmdb_has_tw_date,
        )
        if not bucket:
            continue
        existing_ids.add(movie["id"])
        movies[bucket].append(movie)
        time.sleep(TMDB_DELAY)

    manual_releases = load_manual_releases()
    for idx, manual in enumerate(manual_releases, 1):
        tmdb_id = manual.get("tmdb_id")
        if not tmdb_id or tmdb_id in existing_ids:
            continue
        log(f"Manual release [{idx}/{len(manual_releases)}] TMDB {tmdb_id}")
        payload = tmdb_movie_full(tmdb_id)
        if not payload:
            continue
        theatrical_releases = releases_in_window(
            extract_tw_theatrical_releases_from_results(payload.get("release_dates", {}).get("results", [])),
            today_local - timedelta(days=NOW_LOOKBACK_DAYS),
            today_local + timedelta(days=SOON_WINDOW_DAYS),
        )
        if not theatrical_releases:
            continue
        release_date_tw = theatrical_releases[0]["date"]
        record = {
            "tmdb_id": tmdb_id,
            "tmdb_title": manual.get("title_zh") or payload.get("title") or payload.get("original_title") or "",
            "title_zh": manual.get("title_zh") or payload.get("title") or payload.get("original_title") or "",
            "title_en": manual.get("title_en") or payload.get("original_title") or "",
            "release_date_tw": release_date_tw,
            "tmdb_tw_release_date": release_date_tw,
            "tmdb_tw_release_dates": theatrical_releases,
            "atmovies_id": manual.get("atmovies_id", ""),
            "atmovies_url": manual.get("atmovies_url", ""),
            "source_bucket": "manual",
        }
        ratings = parse_omdb_ratings(payload.get("imdb_id") or payload.get("external_ids", {}).get("imdb_id", ""))
        movie = build_static_movie(record, payload, ratings)
        if not should_keep_static_movie(movie, record):
            continue
        bucket = classify_release_bucket(record, parse_iso_date(movie.get("releaseDate", "")), today_local)
        if not bucket:
            continue
        existing_ids.add(movie["id"])
        movies[bucket].append(movie)
        time.sleep(TMDB_DELAY)

    movies["now"].sort(key=lambda item: item.get("releaseDate", ""), reverse=True)
    movies["soon"].sort(key=lambda item: item.get("releaseDate", ""))

    payload = {
        "generated_at": generated_at_local.isoformat(),
        "source": "api.themoviedb.org",
        "summary": {
            "now_count": len(movies["now"]),
            "soon_count": len(movies["soon"]),
        },
        "movies": movies,
    }

    write_traditional_json(MOVIE_DATA_FILE, payload)

    return MOVIE_DATA_FILE, payload


def should_export_tsv_movie(movie, generated_at_local):
    """TSV 只保留未來片與近兩週內的近期片，排除太舊的殘留項"""
    release_date = parse_iso_date(movie.get("release_date_tw", ""))
    if not release_date:
        return True
    cutoff = generated_at_local.date() - timedelta(days=TSV_LOOKBACK_DAYS)
    return release_date >= cutoff


def append_manual_release_tsv_rows(rows, generated_at_local):
    today_local = generated_at_local.date()
    for manual in load_manual_releases():
        release_date = parse_iso_date(manual.get("release_date_tw", ""))
        if not release_date:
            continue
        now_cutoff = today_local - timedelta(days=NOW_LOOKBACK_DAYS)
        soon_cutoff = today_local + timedelta(days=SOON_WINDOW_DAYS)
        if release_date < now_cutoff or release_date > soon_cutoff:
            continue
        rows.append([
            "人工保留片",
            manual.get("title_zh", ""),
            manual.get("release_date_tw", ""),
            manual.get("title_en", ""),
            tmdb_movie_url(manual.get("tmdb_id")) if manual.get("tmdb_id") else "",
            "",
            manual.get("note", ""),
        ])


def append_tmdb_date_mismatch_tsv_rows(rows, output, generated_at_local):
    for movie in output.get("tmdb_date_mismatch", []):
        if not should_export_tsv_movie(movie, generated_at_local):
            continue
        rows.append([
            "tmdb_date_mismatch",
            movie.get("title_zh", ""),
            movie.get("release_date_tw", ""),
            movie.get("tmdb_title", ""),
            movie.get("tmdb_url", ""),
            movie.get("tmdb_tw_release_date", ""),
            "開眼與 TMDB 台灣院線上映日不同，請以開眼為準",
        ])


def append_tmdb_match_suspicious_tsv_rows(rows, output, generated_at_local):
    for movie in output.get("tmdb_match_suspicious", []):
        if not should_export_tsv_movie(movie, generated_at_local):
            continue
        reasons = movie.get("tmdb_match_suspicious_reasons", [])
        rows.append([
            "tmdb_match_suspicious",
            movie.get("title_zh", ""),
            movie.get("release_date_tw", ""),
            movie.get("tmdb_title", ""),
            movie.get("tmdb_url", ""),
            movie.get("tmdb_primary_release_date", ""),
            "、".join(reasons) if reasons else "TMDB 配對可信度偏低，請人工確認",
        ])


def export_google_sheets_tsv(output, generated_at_local, movie_data=None):
    """輸出給 Google Sheets 用的 TSV"""
    tsv_path = OUTPUT_DIR / f"{generated_at_local.date().isoformat()}.tsv"
    rows = [["類別", "台灣中文片名", "台灣上映日期", "原文片名", "連結", "原上映日期", "備註"]]

    append_tmdb_date_mismatch_tsv_rows(rows, output, generated_at_local)

    for movie in output["missing_tw_date"]:
        if not should_export_tsv_movie(movie, generated_at_local):
            continue
        rows.append([
            "missing_tw_date",
            movie.get("title_zh", ""),
            movie.get("release_date_tw", ""),
            movie.get("tmdb_title", ""),
            movie.get("tmdb_url", ""),
            "",
            "",
        ])

    append_tmdb_match_suspicious_tsv_rows(rows, output, generated_at_local)

    for movie in output["tmdb_not_found"]:
        if not should_export_tsv_movie(movie, generated_at_local):
            continue
        rows.append([
            "tmdb_not_found",
            movie.get("title_zh", ""),
            movie.get("release_date_tw", ""),
            movie.get("title_en", ""),
            "",
            "",
            "",
        ])

    append_manual_release_tsv_rows(rows, generated_at_local)

    movie_buckets = movie_data.get("movies", {}) if movie_data else {}

    for movie in movie_buckets.get("now", []):
        rows.append([
            "現正熱映",
            movie.get("titleZh", ""),
            movie.get("releaseDate", ""),
            movie.get("titleEn", ""),
            "",
            "",
            "",
        ])

    for movie in movie_buckets.get("soon", []):
        rows.append([
            "即將上映",
            movie.get("titleZh", ""),
            movie.get("releaseDate", ""),
            movie.get("titleEn", ""),
            "",
            "",
            "",
        ])

    with open(tsv_path, "w", encoding="utf-8", newline="") as f:
        for row in rows:
            f.write("\t".join(str(cell) for cell in row) + "\n")

    return tsv_path


def export_atmovies_candidates(output, generated_at_local):
    """輸出給私人 Google Sheet / TMDB refresh 使用的完整候選片清單"""
    candidates = []

    for movie in output["tmdb_has_tw_date"] + output["missing_tw_date"]:
        candidates.append({
            "source_bucket": movie.get("source_bucket", ""),
            "title_zh": movie.get("title_zh", ""),
            "title_en": movie.get("title_en", ""),
            "release_date_tw": movie.get("release_date_tw", ""),
            "screen_count": movie.get("screen_count", 0),
            "atmovies_id": movie.get("atmovies_id", ""),
            "atmovies_url": movie.get("atmovies_url", ""),
            "tmdb_id": movie.get("tmdb_id"),
            "tmdb_title": movie.get("tmdb_title", ""),
        })

    payload = {
        "generated_at": generated_at_local.isoformat(),
        "source": "atmovies.com.tw",
        "summary": {
            "candidate_count": len(candidates),
        },
        "candidates": candidates,
    }

    write_traditional_json(ATMOVIES_CANDIDATES_FILE, payload)

    return ATMOVIES_CANDIDATES_FILE


def main():
    tmdb_overrides = load_tmdb_overrides()

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
    tmdb_date_mismatch = []
    tmdb_match_suspicious = []

    for i, movie in enumerate(unique, 1):
        log(f"[{i}/{len(unique)}] {movie['title_zh']} ({movie['release_date_tw']})")
        override = tmdb_overrides.get(movie["atmovies_id"])
        if override and override.get("tmdb_id"):
            override_id = override["tmdb_id"]
            log(f"  TMDB override: {movie['atmovies_id']} -> {override_id}")
            result = tmdb_movie(override_id)
            time.sleep(TMDB_DELAY)
        else:
            result = choose_tmdb_match(movie)

        if not result:
            tmdb_not_found.append(movie)
            continue

        tmdb_id = result["id"]
        tmdb_title = result.get("title") or result.get("original_title", "")
        tmdb_primary_release_date = result.get("release_date", "")
        tmdb_year = (result.get("release_date") or "")[:4]

        release_results = tmdb_release_dates(tmdb_id)
        time.sleep(TMDB_DELAY)
        tmdb_tw_release_date = extract_tw_theatrical_date_from_results(release_results)

        record = {
            **movie,
            "tmdb_id": tmdb_id,
            "tmdb_url": tmdb_movie_url(tmdb_id),
            "tmdb_title": tmdb_title,
            "tmdb_primary_release_date": tmdb_primary_release_date,
            "tmdb_release_year": tmdb_year,
            "tmdb_tw_release_date": tmdb_tw_release_date,
            "tmdb_match_score": result.get("_match_score"),
            "tmdb_match_suspicious_reasons": result.get("_match_suspicious_reasons", []),
        }

        if record["tmdb_match_suspicious_reasons"]:
            tmdb_match_suspicious.append(record)

        if tmdb_tw_release_date:
            tmdb_has_tw_date.append(record)
            if movie.get("release_date_tw") and movie.get("release_date_tw") != tmdb_tw_release_date:
                tmdb_date_mismatch.append(record)
        else:
            missing_tw_date.append(record)

    tz = timezone(timedelta(hours=8))
    generated_at_local = datetime.now(tz)
    output = {
        "generated_at": generated_at_local.isoformat(),
        "source": "atmovies.com.tw",
        "summary": {
            "total_scraped": len(unique),
            "tmdb_not_found": len(tmdb_not_found),
            "tmdb_has_tw_date": len(tmdb_has_tw_date),
            "missing_tw_date": len(missing_tw_date),
            "tmdb_date_mismatch": len(tmdb_date_mismatch),
            "tmdb_match_suspicious": len(tmdb_match_suspicious),
        },
        "missing_tw_date": missing_tw_date,
        "tmdb_not_found": tmdb_not_found,
        "tmdb_has_tw_date": tmdb_has_tw_date,
        "tmdb_date_mismatch": tmdb_date_mismatch,
        "tmdb_match_suspicious": tmdb_match_suspicious,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_traditional_json(OUTPUT_FILE, output)

    log("")
    log("=== Summary ===")
    log(f"Total scraped: {len(unique)}")
    log(f"TMDB not found: {len(tmdb_not_found)}")
    log(f"TMDB has TW date: {len(tmdb_has_tw_date)}")
    log(f"Missing TW date (NEEDS UPDATE): {len(missing_tw_date)}")
    log(f"TMDB date mismatch: {len(tmdb_date_mismatch)}")
    log(f"TMDB suspicious match: {len(tmdb_match_suspicious)}")
    log(f"\nOutput written to: {OUTPUT_FILE}")

    # The crawler is audit-only. Public data is rebuilt separately from TMDB.
    candidates_path = export_atmovies_candidates(output, generated_at_local)
    log(f"Private refresh candidates written to: {candidates_path}")
    tsv_path = export_google_sheets_tsv(output, generated_at_local)
    log(f"Google Sheets TSV written to: {tsv_path}")


def write_tw_whitelist(output):
    """Write the public whitelist from TMDB-verified records only."""
    whitelist_path = OUTPUT_DIR / "tw-whitelist.json"
    whitelist_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tmdb_ids": [],
        "tw_release_dates": {},
        "titles_zh": {}
    }

    # 從 tmdb_has_tw_date bucket 抓出所有有 TMDB ID 的片
    for m in output["tmdb_has_tw_date"]:
        if m.get("tmdb_id"):
            whitelist_data["tmdb_ids"].append(m["tmdb_id"])
            if m.get("tmdb_tw_release_date"):
                whitelist_data["tw_release_dates"][str(m["tmdb_id"])] = m["tmdb_tw_release_date"]
            display_title = m.get("tmdb_title", "")
            if display_title:
                whitelist_data["titles_zh"][str(m["tmdb_id"])] = display_title

    # 去重並排序
    whitelist_data["tmdb_ids"] = sorted(set(whitelist_data["tmdb_ids"]))

    write_traditional_json(whitelist_path, whitelist_data)
    log(f"Whitelist written to: {whitelist_path} ({len(whitelist_data['tmdb_ids'])} ids)")
    return whitelist_path, whitelist_data


if __name__ == "__main__":
    main()
