"""私人院線重映稽核：解析影城片單並辨識重映候選。"""

import json
import re
from datetime import date, timedelta
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


SOURCE_URLS = {
    "miramar_now": "https://www.miramarcinemas.tw/Movie/Index?type=now",
    "miramar_soon": "https://www.miramarcinemas.tw/Movie/Index?type=coming",
    "centuryasia_now": "https://www.centuryasia.com.tw/Movie/GetMovieRelease",
    "centuryasia_soon": "https://www.centuryasia.com.tw/Movie/GetMovieComing",
    "centuryasia_ximen": "https://ximen.centuryasia.com.tw/Movie_Info.aspx",
    "centuryasia_beyond": "https://beyond.centuryasia.com.tw/Movie_Info.aspx",
    "centuryasia_kaohsiung": "https://ksml.centuryasia.com.tw/Movie_Info.aspx",
    "spot_taipei": "https://www.spot.org.tw/movies/201404/movies201404.html",
    "vieshow_now": "https://www.vscinemas.com.tw/film/",
    "vieshow_soon": "https://www.vscinemas.com.tw/film/coming.aspx",
    # 直接讀官方靜態檔；目錄網址在 GitHub Actions 的美國 runner 會被
    # Cloudflare 回傳 403，但兩個入口提供相同的 SEO 電影片單。
    "showtime": "https://www.showtimes.com.tw/programs/index.html",
    "ambassador": "https://www.ambassador.com.tw/home/MovieList?Type=1",
    "spot_huashan_now": "https://www.spot-hs.org.tw/movie/nowplaying.html",
    "spot_huashan_soon": "https://www.spot-hs.org.tw/movie/comingsoon.html",
    "wonderful_now": "https://wonderful.movie.com.tw/movie/index?type=online",
    "wonderful_soon": "https://wonderful.movie.com.tw/movie/index?type=upcoming",
    "eslite": "https://meet.eslite.com/tw/tc/gallery/201803020001",
}
RERELEASE_PATTERN = re.compile(
    r"重映|重新上映|重返(?:大)?銀幕|經典重現|(?:數位|數字|4k|2k)\s*(?:經典)?修復(?:版)?",
    re.IGNORECASE,
)
PROMO_PREFIX_PATTERN = re.compile(
    r"^[（(](?:特別場|搶先場|海報場|玩偶拍照會|一日小店長|DBOX特別場)[）)]\s*",
    re.IGNORECASE,
)
PROMOTIONAL_SCREENING_PATTERN = re.compile(
    r"特別場|搶先場|海報場|拍照會|一日小店長|生日場|見面合影場|直播|彩蛋加長版",
    re.IGNORECASE,
)
RERELEASE_PAREN_PATTERN = re.compile(
    r"[（(][^）)]*(?:重映|重新上映|重返(?:大)?銀幕|經典重現|(?:數位|數字|4k|2k)\s*(?:經典)?修復)[^）)]*[）)]",
    re.IGNORECASE,
)


def strip_rerelease_labels(value):
    value = PROMO_PREFIX_PATTERN.sub("", (value or "").strip())
    value = RERELEASE_PAREN_PATTERN.sub("", value)
    value = RERELEASE_PATTERN.sub("", value)
    value = re.sub(r"[（(]\s*20\d{2}\s*[）)]$", "", value)
    return re.sub(r"\s+", " ", value).strip(" （()）【】[]：:．。._－—-")


def clean_title(value):
    value = strip_rerelease_labels(value)
    return re.sub(r"[\s（()）【】\[\]：:．。._－—-]+", "", value).lower()


def has_rerelease_marker(*values):
    return any(RERELEASE_PATTERN.search(value or "") for value in values)


def is_promotional_screening(*values):
    return any(PROMOTIONAL_SCREENING_PATTERN.search(value or "") for value in values)


def fetch_html(url, user_agent, timeout=30):
    browser_agent = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/124.0 Safari/537.36 {user_agent}"
    )
    response = requests.get(url, headers={"User-Agent": browser_agent}, timeout=timeout)
    response.raise_for_status()
    head = response.content[:2048].decode("ascii", errors="ignore").lower()
    html = response.content.decode("utf-8", errors="replace") if "charset=\"utf-8\"" in head or "charset=utf-8" in head else response.text
    if "access denied" in html.lower():
        raise RuntimeError(f"存取遭拒：{url}")
    return html


def _iso_date_from_href(href):
    raw = parse_qs(urlparse(href).query).get("DT", [""])[0]
    return raw.replace("/", "-") if re.fullmatch(r"\d{4}/\d{2}/\d{2}", raw) else ""


def parse_ambassador(html):
    soup = BeautifulSoup(html, "html.parser")
    lists = soup.select("div.movie-list")
    if not lists:
        raise ValueError("國賓片單結構不存在")
    movies = []
    for list_index, movie_list in enumerate(lists[:2]):
        status = "now" if list_index == 0 else "soon"
        for cell in movie_list.select("div.cell"):
            anchor = cell.select_one("h6 a[href*='MovieContent']")
            if not anchor:
                continue
            href = urljoin(SOURCE_URLS["ambassador"], anchor.get("href", ""))
            release_date = _iso_date_from_href(href)
            if not release_date:
                date_text = cell.select_one("span.date")
                match = re.search(r"\d{4}/\d{2}/\d{2}", date_text.get_text(" ", strip=True) if date_text else "")
                release_date = match.group(0).replace("/", "-") if match else ""
            english = cell.select_one("p.show-for-large")
            movies.append({
                "title_zh": anchor.get_text(" ", strip=True),
                "title_en": english.get_text(" ", strip=True) if english else "",
                "release_date_tw": release_date,
                "status": status,
                "source": "ambassador",
                "source_url": href,
            })
    if len(movies) < 5:
        raise ValueError(f"國賓片單數量異常：{len(movies)}")
    return movies


def parse_ambassador_release_date(html):
    soup = BeautifulSoup(html, "html.parser")
    for note in soup.select("p.note"):
        match = re.search(r"上映日期[：:]\s*(\d{4})/(\d{2})/(\d{2})", note.get_text(" ", strip=True))
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return ""


def parse_showtime(html, today=None):
    today = today or date.today()
    soup = BeautifulSoup(html, "html.parser")
    movies = []
    for item in soup.select("ul.seo-movie-list li"):
        anchor = item.select_one("a[href*='/programs/']")
        title = item.select_one("strong")
        match = re.search(r"(\d{4}-\d{2}-\d{2})\s*上映", item.get_text(" ", strip=True))
        if not anchor or not title or not match:
            continue
        release_date = match.group(1)
        parsed_date = date.fromisoformat(release_date)
        movies.append({
            "title_zh": title.get_text(" ", strip=True),
            "title_en": "",
            "release_date_tw": release_date,
            "status": "soon" if parsed_date > today else "now",
            "source": "showtime",
            "source_url": urljoin(SOURCE_URLS["showtime"], anchor.get("href", "")),
        })
    if len(movies) < 5:
        raise ValueError(f"秀泰片單數量異常：{len(movies)}")
    return movies


def _source_release_date(value):
    """來源未提供完整有效日期時留空，保留片單存在訊號。"""
    value = (value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return ""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return ""


def parse_miramar(html, status="now"):
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("#movie_area > li")
    if not cards:
        raise ValueError("美麗華片單數量異常：0")
    movies = []
    for card in cards:
        anchor = card.select_one("a.img[href]")
        title = card.select_one(".title")
        if not anchor or not title:
            raise ValueError("美麗華電影卡片結構異常")
        title_zh = " ".join(title.find_all(string=True, recursive=False)).strip()
        english = title.select_one("span:not(.date)")
        date_node = title.select_one(".date")
        if not title_zh:
            raise ValueError("美麗華電影卡片缺少片名")
        movies.append({
            "title_zh": title_zh,
            "title_en": english.get_text(" ", strip=True) if english else "",
            "release_date_tw": _source_release_date(date_node.get_text(strip=True) if date_node else ""),
            "status": status,
            "source": "miramar",
            "source_url": urljoin(SOURCE_URLS["miramar_now"], anchor["href"]),
        })
    return movies


def parse_centuryasia_branch(html, source):
    """喜樂時代舊版分館：依官網區塊取得狀態，不以舊日期推定仍上映。"""
    soup = BeautifulSoup(html, "html.parser")
    movies = []
    for status, selector in (("now", "#ContentPlaceHolder1_movie_poster"),
                             ("soon", "#ContentPlaceHolder1_movie_new_poster")):
        section = soup.select_one(selector)
        if section is None:
            raise ValueError(f"喜樂時代 {source} 缺少 {status} 片單區塊")
        for card in section.select("li"):
            anchor = card.select_one("a.mosaic-overlay[href]")
            title = card.select_one("h4")
            date_node = card.select_one("p")
            if not anchor or not title or not title.get_text(strip=True):
                raise ValueError(f"喜樂時代 {source} 電影卡片結構異常")
            movies.append({
                "title_zh": title.get_text(" ", strip=True),
                "title_en": "",
                "release_date_tw": _source_release_date(date_node.get_text(strip=True) if date_node else ""),
                "status": status,
                "source": source,
                "source_url": urljoin(SOURCE_URLS[source], anchor["href"]),
            })
    if not movies:
        raise ValueError(f"喜樂時代 {source} 片單數量異常：0")
    return movies


def parse_centuryasia(payload, status="now"):
    """新版主站公開片單涵蓋電影介紹，不推定為單一分館的實際場次。"""
    if not isinstance(payload, dict) or payload.get("status") is not True or not isinstance(payload.get("Data"), list):
        raise ValueError("喜樂時代主站片單回應異常")
    movies = []
    for item in payload["Data"]:
        if not isinstance(item, dict) or not isinstance(item.get("cname"), str) or not item["cname"].strip() or not re.fullmatch(r"\d+", str(item.get("programid", ""))):
            raise ValueError("喜樂時代主站電影資料結構異常")
        movies.append({
            "title_zh": item["cname"].strip(),
            "title_en": (item.get("ename") or "").strip(),
            "release_date_tw": _source_release_date(item.get("ReleaseDate")),
            "status": status,
            "source": "centuryasia",
            "source_url": f"https://www.centuryasia.com.tw/movie-info.html?obj={item['programid']}",
        })
    if not movies:
        raise ValueError("喜樂時代主站片單數量異常：0")
    return movies


def fetch_additional_cinema_movies(user_agent, today):
    """各來源完整解析後才納入；新增來源失敗不影響必要來源完整性。"""
    readers = {
        "spot_taipei": lambda: parse_spot_taipei(fetch_html(SOURCE_URLS["spot_taipei"], user_agent), today),
        "miramar": lambda: [movie for status in ("now", "soon") for movie in
                            parse_miramar(fetch_html(SOURCE_URLS[f"miramar_{status}"], user_agent), status)],
        "centuryasia": lambda: [movie for status in ("now", "soon") for movie in
                                parse_centuryasia(json.loads(fetch_html(SOURCE_URLS[f"centuryasia_{status}"], user_agent)), status)],
    }
    for source in ("centuryasia_ximen", "centuryasia_beyond", "centuryasia_kaohsiung"):
        readers[source] = lambda source=source: parse_centuryasia_branch(fetch_html(SOURCE_URLS[source], user_agent), source)
    movies, health, errors = [], {}, {}
    for source, read in readers.items():
        try:
            movies.extend(read())
            health[source] = True
        except Exception as error:
            health[source] = False
            errors[source] = str(error)
    return movies, health, errors


def parse_spot_huashan(html, status="now", page_url=None):
    """解析光點華山現正放映或即將上映片單。"""
    page_url = page_url or SOURCE_URLS["spot_huashan_now"]
    soup = BeautifulSoup(html, "html.parser")
    movies = []
    for card in soup.select("div.nowplayingdiv"):
        anchor = card.select_one("a[href]")
        title = card.select_one(".nowplayingtext_title")
        english = card.select_one(".nowplayingtext_eng")
        date_node = card.select_one(".nowplayingtext6")
        match = re.search(
            r"(20\d{2})/(\d{1,2})/(\d{1,2})",
            date_node.get_text(" ", strip=True) if date_node else "",
        )
        if not anchor or not title or not match:
            continue
        movies.append({
            "title_zh": title.get_text(" ", strip=True),
            "title_en": english.get_text(" ", strip=True) if english else "",
            "release_date_tw": (
                f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
            ),
            "status": status,
            "source": "spot_huashan",
            "source_url": urljoin(page_url, anchor.get("href", "")),
        })
    if len(movies) < 5:
        raise ValueError(f"光點華山片單數量異常：{len(movies)}")
    return movies


def spot_taipei_release_date(date_text, today):
    """目前片單的月日依放映狀態補最近年份；完整日期保留來源年份。"""
    full_date = re.search(r"(?<!\d)(\d{4})/(\d{1,2})/(\d{1,2})(?!\d)", date_text)
    if full_date:
        try:
            return date(*map(int, full_date.groups()))
        except ValueError:
            return None
    month_day = re.search(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])", date_text)
    if not month_day:
        return None
    month, day = map(int, month_day.groups())
    candidates = []
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if "熱映中" in date_text and candidate > today:
            continue
        if "即將上映" in date_text and candidate < today:
            continue
        candidates.append(candidate)
    return min(candidates, key=lambda value: (abs((value - today).days), value), default=None)


def parse_spot_taipei(html, today=None):
    """解析光點台北目前片單，為只有月日的上映標示補最近合理年份。"""
    today = today or date.today()
    soup = BeautifulSoup(html, "html.parser")
    movies = []
    for title in soup.select(".movie_title"):
        card = next((parent for parent in title.parents
                     if parent.name == "table" and parent.select_one("a.abgne-zoom-out[href]")), None)
        if card is None or len(card.select(".movie_title")) != 1:
            raise ValueError("光點台北電影卡片結構異常")
        anchor = card.select_one("a.abgne-zoom-out[href]")
        english = card.select_one(".movie_title_eng")
        date_node = card.select_one(".movie_body_w3")
        date_text = date_node.get_text(" ", strip=True) if date_node else ""
        release_date = spot_taipei_release_date(date_text, today)
        # 官網詳細頁路徑可能沿用舊年份，不可當作本次上映年份。
        movies.append({
            "title_zh": title.get_text(" ", strip=True),
            "title_en": english.get_text(" ", strip=True) if english else "",
            "release_date_tw": release_date.isoformat() if release_date else "",
            "status": ("soon" if release_date > today else "now") if release_date else (
                "now" if "熱映中" in date_text else "soon"
            ),
            "source": "spot_taipei",
            "source_url": urljoin(SOURCE_URLS["spot_taipei"], anchor["href"]),
        })
    if not movies:
        raise ValueError("光點台北片單數量異常：0")
    return movies


def parse_wonderful(html, status="now", page_url=None):
    """解析台北真善美劇院現正上映或即將上映片單。"""
    page_url = page_url or SOURCE_URLS["wonderful_now"]
    soup = BeautifulSoup(html, "html.parser")
    movies = []
    for card in soup.select("ul.movie_list a.poster_wrap[href]"):
        title = card.select_one(".movie_title")
        time_node = card.select_one(".time")
        match = re.search(
            r"(20\d{2})/(\d{1,2})/(\d{1,2})",
            time_node.get_text(" ", strip=True) if time_node else "",
        )
        if not title or not match:
            continue
        movies.append({
            "title_zh": title.get_text(" ", strip=True),
            "title_en": "",
            "release_date_tw": (
                f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
            ),
            "status": status,
            "source": "wonderful",
            "source_url": urljoin(page_url, card.get("href", "")),
        })
    if len(movies) < 5:
        raise ValueError(f"真善美片單數量異常：{len(movies)}")
    return movies


def parse_eslite(html, today=None):
    """解析誠品電影院官方活動列表中的電影上映日期。"""
    today = today or date.today()
    soup = BeautifulSoup(html, "html.parser")
    movies = []
    seen = set()
    for anchor in soup.select("a[href*='/artshow/']"):
        href = urljoin(SOURCE_URLS["eslite"], anchor.get("href", ""))
        if href in seen:
            continue
        container = anchor
        for parent in anchor.parents:
            if getattr(parent, "name", None) not in {"li", "article", "div"}:
                continue
            if re.search(r"上映日期\s*[|∣：:]?\s*20\d{2}", parent.get_text(" ", strip=True)):
                container = parent
                break
        text_value = container.get_text(" ", strip=True)
        match = re.search(r"上映日期\s*[|∣：:]?\s*(20\d{2})[年/]\s*(\d{1,2})[月/]\s*(\d{1,2})日?", text_value)
        if not match:
            continue
        image = anchor.select_one("img[alt]")
        title = (image.get("alt", "").strip() if image else "") or anchor.get_text(" ", strip=True)
        title = re.sub(r"\s*上映日期.*$", "", title).strip()
        if not title:
            continue
        seen.add(href)
        movies.append({
            "title_zh": title,
            "title_en": "",
            "release_date_tw": (
                f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
            ),
            "status": "soon" if date.fromisoformat(
                f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
            ) > today else "now",
            "source": "eslite",
            "source_url": href,
        })
    if len(movies) < 5:
        raise ValueError(f"誠品電影院片單數量異常：{len(movies)}")
    return movies


def parse_vieshow(html, status, page_url):
    """威秀舊站版型容錯解析；上映日可來自卡片文字或詳細頁連結參數。"""
    soup = BeautifulSoup(html, "html.parser")
    movies = []
    seen = set()
    for anchor in soup.select("a[href*='detail.aspx'], a[href*='/film/detail']"):
        href = urljoin(page_url, anchor.get("href", ""))
        if href in seen:
            continue
        container = anchor.find_parent(["li", "div", "article"]) or anchor
        text = container.get_text(" ", strip=True)
        title_node = container.select_one("h2, h3, h4, h5, .title, .name")
        title = title_node.get_text(" ", strip=True) if title_node else anchor.get_text(" ", strip=True)
        title = title.strip()
        match = re.search(r"(20\d{2})[/.\-](\d{1,2})[/.\-](\d{1,2})", text)
        release_date = ""
        if match:
            release_date = f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
        if title:
            seen.add(href)
            movies.append({
                "title_zh": title,
                "title_en": "",
                "release_date_tw": release_date,
                "status": status,
                "source": "vieshow",
                "source_url": href,
            })
    if len(movies) < 5:
        raise ValueError(f"威秀{status}片單數量異常：{len(movies)}")
    return movies


def vieshow_page_count(html):
    pages = [1]
    for match in re.finditer(r"[?&]p=(\d+)", html or "", re.IGNORECASE):
        pages.append(int(match.group(1)))
    return min(max(pages), 20)


def merge_raw_movies(movies):
    merged = {}
    for movie in movies:
        key = (clean_title(movie.get("title_en")) or clean_title(movie.get("title_zh")), movie.get("release_date_tw", ""))
        if not key[0]:
            continue
        current = merged.setdefault(key, dict(movie, sources=[], source_urls=[], statuses=[]))
        for field, value in (
            ("sources", movie.get("source")),
            ("source_urls", movie.get("source_url")),
            ("statuses", movie.get("status")),
        ):
            if value and value not in current[field]:
                current[field].append(value)
        if not current.get("title_en") and movie.get("title_en"):
            current["title_en"] = movie["title_en"]
    return list(merged.values())


def is_confirmed_rerelease(movie, tmdb_movie, tw_releases):
    """只以明確標記或更早的台灣院線日期確認重映。"""
    cinema_date = movie.get("release_date_tw", "")
    if has_rerelease_marker(movie.get("title_zh"), movie.get("title_en")):
        return True
    try:
        old_release_cutoff = date.fromisoformat(cinema_date) - timedelta(days=365)
    except (TypeError, ValueError):
        return False
    earlier_tw_dates = []
    for item in tw_releases:
        try:
            release_date = date.fromisoformat(item.get("date", ""))
        except (TypeError, ValueError):
            continue
        if release_date <= old_release_cutoff:
            earlier_tw_dates.append(release_date)
    return bool(earlier_tw_dates)


def tmdb_date_status(cinema_date, tw_releases):
    if not cinema_date:
        return "pending"
    dates = {item.get("date", "") for item in tw_releases}
    if cinema_date in dates:
        return "confirmed"
    return "mismatch" if dates else "missing"
