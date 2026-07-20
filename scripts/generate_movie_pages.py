#!/usr/bin/env python3
import json
import re
import shutil
from datetime import date
from html import escape
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "movie-data.json"
MOVIES_DIR = ROOT / "movies"
SITEMAP_PATH = ROOT / "sitemap.xml"
SITE_URL = "https://movienotice.pages.dev"
SITE_NAME = "MovieNotice 電影佈告欄"

MOVIE_PAGE_CSS_PATH = ROOT / "movie-page.css"
MOVIE_PAGE_CSS = """
*{box-sizing:border-box}body{margin:0;background:#0a0a0f;color:#fff;font-family:Manrope,-apple-system,BlinkMacSystemFont,"Noto Sans TC",sans-serif;font-weight:300}.page-bg{position:fixed;inset:0;z-index:-1;background:radial-gradient(circle at 90% 10%,rgba(220,170,20,.16),transparent 38%),radial-gradient(circle at 0 85%,rgba(30,72,240,.13),transparent 42%),#0a0a0f}.material-symbols-outlined{font-family:'Material Symbols Outlined'!important;font-variation-settings:'FILL' 0,'wght' 400,'GRAD' 0,'opsz' 24;font-weight:normal;font-style:normal;display:inline-block;line-height:1;text-transform:none;letter-spacing:normal}.topbar{position:sticky;top:0;z-index:10;background:rgba(10,10,15,.9);border-bottom:1px solid rgba(255,255,255,.08);backdrop-filter:blur(18px)}.topbar-inner{max-width:1040px;margin:0 auto;padding:14px 24px;display:flex;align-items:center;justify-content:space-between}.brand{display:flex;align-items:center;gap:10px;color:#fff;text-decoration:none}.brand img{height:34px;width:auto}.brand span{color:rgba(255,255,255,.68);font-size:13px}.back-link{color:rgba(255,255,255,.58);font-size:13px;text-decoration:none}.hero{position:relative;min-height:520px;display:flex;align-items:flex-end;overflow:hidden}.hero-media{position:absolute;inset:0}.hero-media img{width:100%;height:100%;object-fit:cover;opacity:.46}.hero-media:after{content:"";position:absolute;inset:0;background:linear-gradient(to top,#0a0a0f 0%,rgba(10,10,15,.82) 28%,rgba(10,10,15,.18) 100%)}.hero-content{position:relative;width:100%;max-width:1040px;margin:0 auto;padding:96px 24px 42px}.genre-tags{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}.genre-tag{font-size:12px;color:rgba(255,255,255,.72);border:1px solid rgba(255,255,255,.18);border-radius:999px;padding:4px 10px;background:rgba(255,255,255,.06)}h1{font-size:clamp(34px,6vw,68px);line-height:1.02;margin:0 0 12px;font-weight:300;letter-spacing:0}.subtitle{margin:0;color:rgba(255,255,255,.68);font-size:15px}.ratings{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:22px;margin-bottom:20px}.rating-divider{width:1px;height:12px;background:rgba(255,255,255,.3)}.rating-item{display:flex;align-items:center;gap:4px;font-size:13px;color:rgba(255,255,255,.5)}.rating-item .star{font-size:13px;color:rgba(255,255,255,.6);font-variation-settings:'FILL' 1,'wght' 400,'GRAD' 0,'opsz' 24}.rating-item .val{color:#fff}.trailer-link{display:inline-flex;align-items:center;gap:6px;margin-top:0;padding:6px 18px 6px 8px;background:rgba(255,255,255,.20);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);border:1px solid rgba(255,255,255,.4);border-radius:999px;color:#fff;font-size:14px;font-weight:400;text-decoration:none;transition:background .2s}.trailer-link:hover{background:rgba(255,255,255,.25)}.content{max-width:1040px;margin:0 auto;padding:34px 24px 72px}.synopsis{font-size:17px;line-height:1.9;color:rgba(255,255,255,.8);margin:0 0 34px}.crew-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:16px;margin-bottom:34px}.crew-name,.cast-name{margin:0;color:#fff;font-size:14px}.crew-role,.cast-char{margin:4px 0 0;color:rgba(255,255,255,.52);font-size:12px}.section-label{margin:0 0 14px;color:rgba(255,255,255,.42);font-size:12px;text-transform:uppercase;letter-spacing:.1em}.cast-row{display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));column-gap:16px;row-gap:32px;margin-bottom:36px}.cast-photo,.cast-no-photo{width:100%;aspect-ratio:2/3;object-fit:cover;border-radius:12px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08)}.cast-card{min-width:0}.cast-name{margin-top:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.cast-char{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.meta-panel{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:16px}.meta-row{display:flex;gap:16px;margin-bottom:12px}.meta-row:last-child{margin-bottom:0}.meta-key{font-size:14px;color:rgba(255,255,255,.65);width:80px;flex-shrink:0;padding-top:2px}.meta-val{font-size:14px;color:#fff}@media(max-width:720px){.topbar-inner{padding:12px 18px}.brand img{height:30px}.brand span{display:none}.hero{min-height:470px}.hero-content{padding:82px 20px 34px}.content{padding:28px 20px 58px}.cast-row{grid-template-columns:repeat(3,minmax(0,1fr));column-gap:12px;row-gap:28px}.synopsis{font-size:15px}.meta-row{align-items:flex-start}.meta-val{text-align:left}}
"""

LANG_MAP = {
    "en": "英語",
    "zh": "中文",
    "ja": "日語",
    "ko": "韓語",
    "fr": "法語",
    "es": "西班牙語",
    "de": "德語",
    "it": "義大利語",
    "th": "泰語",
    "hi": "印地語",
    "tl": "菲律賓語",
    "ar": "阿拉伯語",
    "id": "印尼語",
    "pt": "葡萄牙語",
    "tr": "土耳其語",
}

COUNTRY_MAP = {
    "US": "美國", "GB": "英國", "FR": "法國", "DE": "德國", "IT": "義大利", "JP": "日本", "KR": "韓國",
    "CN": "中國", "HK": "香港", "TW": "台灣", "AU": "澳洲", "CA": "加拿大", "ES": "西班牙", "IN": "印度",
    "NZ": "紐西蘭", "IE": "愛爾蘭", "NL": "荷蘭", "BE": "比利時", "SE": "瑞典", "DK": "丹麥", "NO": "挪威",
    "FI": "芬蘭", "RU": "俄羅斯", "MX": "墨西哥", "BR": "巴西", "AR": "阿根廷", "TH": "泰國", "SG": "新加坡",
    "ZA": "南非", "AT": "奧地利", "CH": "瑞士", "PL": "波蘭", "CZ": "捷克", "HU": "匈牙利", "PT": "葡萄牙",
    "GR": "希臘", "IL": "以色列", "TR": "土耳其", "MY": "馬來西亞", "ID": "印尼", "PH": "菲律賓", "VN": "越南",
    "United States of America": "美國", "Japan": "日本", "United Kingdom": "英國", "Taiwan": "台灣",
    "France": "法國", "Canada": "加拿大", "Netherlands": "荷蘭", "South Korea": "韓國", "Germany": "德國",
    "Thailand": "泰國", "Hong Kong": "香港", "Mexico": "墨西哥", "Saudi Arabia": "沙烏地阿拉伯",
    "Spain": "西班牙", "Belgium": "比利時", "Ireland": "愛爾蘭", "United Arab Emirates": "阿拉伯聯合大公國",
    "Brazil": "巴西", "Chile": "智利", "China": "中國", "Tunisia": "突尼西亞", "Cyprus": "賽普勒斯",
    "Italy": "義大利", "Palestinian Territory": "巴勒斯坦", "Indonesia": "印尼", "Hungary": "匈牙利",
    "Turkey": "土耳其", "Greece": "希臘", "Sweden": "瑞典", "Philippines": "菲律賓", "India": "印度",
}


def h(value):
    return escape(str(value or ""), quote=True)


def format_date(value):
    if not value:
        return ""
    parts = str(value).split("-")
    if len(parts) != 3:
        return str(value)
    return f"{parts[0]}/{parts[1]}/{parts[2]}"


def slugify(movie):
    title = movie.get("titleEn") or movie.get("origTitle") or movie.get("titleZh") or "movie"
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if not slug:
        slug = "movie"
    return f"{movie.get('id')}-{slug}"


def movie_url(movie):
    return f"{SITE_URL}/movies/{quote(slugify(movie))}/"


def detail_for(movie):
    detail = movie.get("detail") or {}
    merged = dict(movie)
    merged.update({k: v for k, v in detail.items() if v not in (None, "", [])})
    return merged


def normalize_genres(movie, detail):
    genres = detail.get("genres") or movie.get("genre") or []
    seen = set()
    result = []
    for genre in genres:
        if not genre or genre in seen:
            continue
        seen.add(genre)
        result.append(str(genre))
    return result


RELEASE_LANGUAGE_MAP = {"ja": "日文", "zh": "中文", "en": "英文"}


def format_release_dates(movie, separator="、"):
    releases = movie.get("twTheatricalReleases") or []
    if len(releases) < 2:
        return format_date(movie.get("releaseDate"))
    labels = []
    for item in releases:
        date_label = format_date(item.get("date"))
        language = RELEASE_LANGUAGE_MAP.get(item.get("language"), "")
        labels.append(f"{date_label}（{language}）" if language else date_label)
    return separator.join(labels)


def description_for(movie, detail):
    title = movie.get("titleZh") or detail.get("origTitle") or movie.get("titleEn") or "電影"
    parts = [f"《{title}》"]
    if movie.get("releaseDate"):
        parts.append(f"台灣上映日期 {format_release_dates(movie)}")
    genres = normalize_genres(movie, detail)
    if genres:
        parts.append("類型：" + "、".join(genres[:3]))
    ratings = []
    if movie.get("imdb"):
        ratings.append(f"IMDb {movie.get('imdb')}")
    if detail.get("voteAverage"):
        ratings.append(f"TMDB {detail.get('voteAverage')}")
    if movie.get("rt"):
        ratings.append(f"爛番茄 {movie.get('rt')}")
    if ratings:
        parts.append("評分：" + " / ".join(ratings))
    synopsis = detail.get("synopsis") or movie.get("synopsis") or ""
    if synopsis:
        parts.append(str(synopsis).strip())
    text = "，".join(parts)
    return text[:155]


def rating_items(movie, detail):
    items = []
    if movie.get("imdb"):
        items.append(("IMDb", movie.get("imdb")))
    if movie.get("rt"):
        items.append(("RT", movie.get("rt")))
    if movie.get("mc"):
        items.append(("MT", movie.get("mc")))
    if detail.get("voteAverage"):
        items.append(("TMDB", detail.get("voteAverage")))
    return items


def format_country_list(countries):
    if not countries:
        return "—"
    return " · ".join(COUNTRY_MAP.get(country, country) for country in countries)


def render_meta_panel(movie, detail):
    countries = detail.get("countries") or movie.get("countries") or []
    rows = []
    if len(movie.get("twTheatricalReleases") or []) > 1:
        rows.append(("台灣上映", format_release_dates(movie)))
    rows.extend([
        ("原始標題", detail.get("origTitle") or movie.get("titleEn") or "—"),
        ("原始語言", LANG_MAP.get(detail.get("origLang"), detail.get("origLang") or "—")),
        ("製片國家", format_country_list(countries)),
        ("電影成本", f"${detail.get('budget'):,}" if detail.get("budget") else "—"),
        ("票房收入", f"${detail.get('revenue'):,}" if detail.get("revenue") else "—"),
    ])
    return "\n".join(
        f'<div class="meta-row"><span class="meta-key">{h(key)}</span><span class="meta-val">{h(value)}</span></div>'
        for key, value in rows
    )


def render_movie_page(movie, generated_at):
    detail = detail_for(movie)
    title_zh = movie.get("titleZh") or detail.get("origTitle") or movie.get("titleEn") or "電影"
    title_en = movie.get("titleEn") or detail.get("origTitle") or ""
    page_title = f"《{title_zh}》台灣上映日期、評分、預告、劇情簡介 | {SITE_NAME}"
    description = description_for(movie, detail)
    url = movie_url(movie)
    hero_image = detail.get("backdrop") or movie.get("backdrop") or movie.get("poster") or ""
    poster = detail.get("poster") or movie.get("poster") or hero_image
    genres = normalize_genres(movie, detail)
    subtitle = " · ".join(
        part
        for part in [
            title_en,
            format_release_dates(movie),
            f"{detail.get('duration')}分鐘" if detail.get("duration") else "",
        ]
        if part
    )
    genre_tags = "".join(f'<span class="genre-tag">{h(genre)}</span>' for genre in genres[:3])
    rating_parts = []
    for label, value in rating_items(movie, detail):
        icon = '<span class="material-symbols-outlined star">star</span>' if label in ("IMDb", "TMDB") else ""
        rating_parts.append(
            f'<span class="rating-item">{icon}{h(label)} <span class="val">{h(value)}</span></span>'
        )
    ratings_html = '<span class="rating-divider"></span>'.join(rating_parts)
    crew = detail.get("crew") or movie.get("crew") or []
    crew_html = "".join(
        f'<div><p class="crew-name">{h(person.get("name"))}</p><p class="crew-role">{h("導演" if person.get("job") == "Director" else "編劇" if person.get("job") == "Screenplay" else "製作人")}</p></div>'
        for person in crew
    )
    cast = detail.get("cast") or movie.get("cast") or []
    cast_html = "".join(
        '<div class="cast-card">'
        + (
            f'<img class="cast-photo" src="{h(person.get("photo"))}" alt="{h(person.get("name"))}" loading="lazy"/>'
            if person.get("photo")
            else '<div class="cast-no-photo">person</div>'
        )
        + f'<p class="cast-name">{h(person.get("name"))}</p><p class="cast-char">{h(person.get("char"))}</p></div>'
        for person in cast
    )
    trailer_key = detail.get("trailerKey") or movie.get("trailerKey")
    trailer_html = (
        f'<a class="trailer-link" href="https://www.youtube.com/watch?v={h(trailer_key)}" rel="noopener" target="_blank"><span class="material-symbols-outlined" style="font-size:22px">play_arrow</span>播放預告</a>'
        if trailer_key
        else ""
    )
    json_ld = {
        "@context": "https://schema.org",
        "@type": "Movie",
        "@id": f"{url}#movie",
        "url": url,
        "name": title_zh,
        "alternateName": title_en or None,
        "datePublished": movie.get("releaseDate") or None,
        "image": poster or None,
        "description": detail.get("synopsis") or description,
        "genre": genres or None,
        "duration": f"PT{detail.get('duration')}M" if detail.get("duration") else None,
        "actor": [{"@type": "Person", "name": p.get("name"), "characterName": p.get("char")} for p in cast[:12] if p.get("name")],
        "director": [{"@type": "Person", "name": p.get("name")} for p in crew if p.get("job") == "Director" and p.get("name")],
    }
    json_ld = {k: v for k, v in json_ld.items() if v}

    fallback_bg = "rgba(255,255,255,0.05)"
    hero_media = f'<img src="{h(hero_image)}" alt="{h(title_zh)}" fetchpriority="high" decoding="async"/>' if hero_image else f'<div style="width:100%;height:100%;background:{fallback_bg}"></div>'
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{h(page_title)}</title>
<meta name="description" content="{h(description)}"/>
<link rel="canonical" href="{h(url)}"/>
<meta property="og:locale" content="zh_TW"/>
<meta property="og:type" content="video.movie"/>
<meta property="og:site_name" content="{h(SITE_NAME)}"/>
<meta property="og:title" content="{h(page_title)}"/>
<meta property="og:description" content="{h(description)}"/>
<meta property="og:url" content="{h(url)}"/>
<meta property="og:image" content="{h(poster or hero_image)}"/>
<meta name="twitter:card" content="summary_large_image"/>
<meta name="twitter:title" content="{h(page_title)}"/>
<meta name="twitter:description" content="{h(description)}"/>
<meta name="twitter:image" content="{h(poster or hero_image)}"/>
<link rel="icon" href="../../favicon.ico?v=10" sizes="32x32"/>
<link rel="icon" href="../../favicon.svg?v=10" type="image/svg+xml" sizes="any"/>
<link rel="apple-touch-icon" href="../../apple-touch-icon.png?v=10"/>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@200;300;400;500&display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..400,0..1&display=swap" rel="stylesheet"/>
<link rel="stylesheet" href="../../movie-page.css"/>
<script type="application/ld+json">{json.dumps(json_ld, ensure_ascii=False, separators=(",", ":"))}</script>
</head>
<body>
<div class="page-bg"></div>
<header class="topbar"><div class="topbar-inner"><a class="brand" href="../../"><img src="../../logo.svg?v=10" alt="MovieNotice 電影佈告欄"/><span>電影佈告欄</span></a><a class="back-link" href="../../">回電影列表</a></div></header>
<main>
<section class="hero"><div class="hero-media">{hero_media}</div><div class="hero-content"><div class="genre-tags">{genre_tags}</div><h1>{h(title_zh)}</h1><p class="subtitle">{h(subtitle)}</p><div class="ratings">{ratings_html}</div>{trailer_html}</div></section>
<section class="content">
{f'<p class="synopsis">{h(detail.get("synopsis") or movie.get("synopsis"))}</p>' if (detail.get("synopsis") or movie.get("synopsis")) else ''}
{f'<div class="crew-grid">{crew_html}</div>' if crew_html else ''}
{f'<div><p class="section-label">主要演員</p><div class="cast-row">{cast_html}</div></div>' if cast_html else ''}
<div><p class="section-label">其他資訊</p><div class="meta-panel">{render_meta_panel(movie, detail)}</div></div>
</section>
</main>
</body>
</html>
"""


def load_movies():
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    movies = []
    for bucket in ("now", "soon"):
        for movie in payload.get("movies", {}).get(bucket, []):
            item = dict(movie)
            item["_bucket"] = bucket
            movies.append(item)
    return payload, movies


def write_sitemap(movies):
    today = date.today().isoformat()
    urls = [
        ("https://movienotice.pages.dev/", "daily", "1.0"),
        *[(movie_url(movie), "weekly", "0.8") for movie in movies],
    ]
    body = "\n".join(
        f"  <url>\n    <loc>{h(loc)}</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>{freq}</changefreq>\n    <priority>{priority}</priority>\n  </url>"
        for loc, freq, priority in urls
    )
    SITEMAP_PATH.write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}\n</urlset>\n',
        encoding="utf-8",
    )


def main():
    MOVIE_PAGE_CSS_PATH.write_text(MOVIE_PAGE_CSS.strip() + "\n", encoding="utf-8")
    payload, movies = load_movies()
    if MOVIES_DIR.exists():
        shutil.rmtree(MOVIES_DIR)
    MOVIES_DIR.mkdir()
    seen = set()
    for movie in movies:
        slug = slugify(movie)
        if slug in seen:
            raise RuntimeError(f"duplicate movie slug: {slug}")
        seen.add(slug)
        out_dir = MOVIES_DIR / slug
        out_dir.mkdir(parents=True)
        (out_dir / "index.html").write_text(render_movie_page(movie, payload.get("generated_at", "")), encoding="utf-8")
    write_sitemap(movies)
    print(f"Generated {len(movies)} movie pages")


if __name__ == "__main__":
    main()
