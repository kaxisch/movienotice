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

STATUS_MAP = {
    "Released": "已上映",
    "In Production": "製作中",
    "Planned": "計畫中",
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


def description_for(movie, detail):
    title = movie.get("titleZh") or detail.get("origTitle") or movie.get("titleEn") or "電影"
    parts = [f"《{title}》"]
    if movie.get("releaseDate"):
        parts.append(f"台灣上映日期 {format_date(movie.get('releaseDate'))}")
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


def render_meta_panel(movie, detail):
    countries = detail.get("countries") or movie.get("countries") or []
    rows = [
        ("原始標題", detail.get("origTitle") or movie.get("titleEn") or "—"),
        ("狀態", STATUS_MAP.get(detail.get("status"), detail.get("status") or "—")),
        ("原始語言", LANG_MAP.get(detail.get("origLang"), detail.get("origLang") or "—")),
        ("製片國家", "、".join(countries) if countries else "—"),
        ("電影成本", f"${detail.get('budget'):,}" if detail.get("budget") else "—"),
        ("票房收入", f"${detail.get('revenue'):,}" if detail.get("revenue") else "—"),
    ]
    return "\n".join(
        f'<div class="meta-row"><span class="meta-key">{h(key)}</span><span class="meta-val">{h(value)}</span></div>'
        for key, value in rows
    )


def render_movie_page(movie, generated_at):
    detail = detail_for(movie)
    title_zh = movie.get("titleZh") or detail.get("origTitle") or movie.get("titleEn") or "電影"
    title_en = movie.get("titleEn") or detail.get("origTitle") or ""
    page_title = f"《{title_zh}》台灣上映日期、評分、預告、劇情簡介 | MovieNotice"
    description = description_for(movie, detail)
    url = movie_url(movie)
    hero_image = detail.get("backdrop") or movie.get("backdrop") or movie.get("poster") or ""
    poster = detail.get("poster") or movie.get("poster") or hero_image
    genres = normalize_genres(movie, detail)
    subtitle = " · ".join(
        part
        for part in [
            title_en,
            format_date(movie.get("releaseDate")),
            f"{detail.get('duration')}分鐘" if detail.get("duration") else "",
        ]
        if part
    )
    genre_tags = "".join(f'<span class="genre-tag">{h(genre)}</span>' for genre in genres[:3])
    ratings_html = "".join(
        f'<span class="rating-item"><span class="rating-label">{h(label)}</span><span class="rating-value">{h(value)}</span></span>'
        for label, value in rating_items(movie, detail)
    )
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
        f'<a class="trailer-link" href="https://www.youtube.com/watch?v={h(trailer_key)}" rel="noopener" target="_blank">播放預告</a>'
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
    css = """
*{box-sizing:border-box}body{margin:0;background:#0a0a0f;color:#fff;font-family:Manrope,-apple-system,BlinkMacSystemFont,"Noto Sans TC",sans-serif;font-weight:300}.page-bg{position:fixed;inset:0;z-index:-1;background:radial-gradient(circle at 90% 10%,rgba(220,170,20,.16),transparent 38%),radial-gradient(circle at 0 85%,rgba(30,72,240,.13),transparent 42%),#0a0a0f}.topbar{position:sticky;top:0;z-index:10;background:rgba(10,10,15,.9);border-bottom:1px solid rgba(255,255,255,.08);backdrop-filter:blur(18px)}.topbar-inner{max-width:1040px;margin:0 auto;padding:14px 24px;display:flex;align-items:center;justify-content:space-between}.brand{display:flex;align-items:center;gap:10px;color:#fff;text-decoration:none}.brand img{height:34px;width:auto}.brand span{color:rgba(255,255,255,.68);font-size:13px}.back-link{color:rgba(255,255,255,.58);font-size:13px;text-decoration:none}.hero{position:relative;min-height:520px;display:flex;align-items:flex-end;overflow:hidden}.hero-media{position:absolute;inset:0}.hero-media img{width:100%;height:100%;object-fit:cover;opacity:.46}.hero-media:after{content:"";position:absolute;inset:0;background:linear-gradient(to top,#0a0a0f 0%,rgba(10,10,15,.82) 28%,rgba(10,10,15,.18) 100%)}.hero-content{position:relative;width:100%;max-width:1040px;margin:0 auto;padding:96px 24px 42px}.genre-tags{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}.genre-tag{font-size:12px;color:rgba(255,255,255,.72);border:1px solid rgba(255,255,255,.18);border-radius:999px;padding:4px 10px;background:rgba(255,255,255,.06)}h1{font-size:clamp(34px,6vw,68px);line-height:1.02;margin:0 0 12px;font-weight:300;letter-spacing:0}.subtitle{margin:0;color:rgba(255,255,255,.68);font-size:15px}.ratings{display:flex;gap:8px;flex-wrap:wrap;margin-top:22px}.rating-item{display:inline-flex;gap:6px;align-items:center;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);border-radius:10px;padding:6px 9px;font-size:13px}.rating-label{color:rgba(255,255,255,.58)}.rating-value{color:#fff}.trailer-link{display:inline-flex;margin-top:18px;color:#0a0a0f;background:#fff;text-decoration:none;border-radius:999px;padding:9px 14px;font-size:14px}.content{max-width:1040px;margin:0 auto;padding:34px 24px 72px}.synopsis{font-size:17px;line-height:1.9;color:rgba(255,255,255,.8);max-width:820px;margin:0 0 34px}.crew-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:16px;margin-bottom:34px}.crew-name,.cast-name{margin:0;color:#fff;font-size:14px}.crew-role,.cast-char{margin:4px 0 0;color:rgba(255,255,255,.52);font-size:12px}.section-label{margin:0 0 14px;color:rgba(255,255,255,.42);font-size:12px;text-transform:uppercase;letter-spacing:.1em}.cast-row{display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:16px;margin-bottom:36px}.cast-photo,.cast-no-photo{width:100%;aspect-ratio:2/3;object-fit:cover;border-radius:12px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08)}.cast-card{min-width:0}.cast-name{margin-top:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.cast-char{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.meta-panel{border:1px solid rgba(255,255,255,.08);border-radius:14px;overflow:hidden;background:rgba(255,255,255,.03)}.meta-row{display:flex;justify-content:space-between;gap:18px;padding:13px 16px;border-bottom:1px solid rgba(255,255,255,.06)}.meta-row:last-child{border-bottom:0}.meta-key{color:rgba(255,255,255,.45);font-size:13px}.meta-val{color:rgba(255,255,255,.82);font-size:13px;text-align:right}.footer-note{margin-top:28px;color:rgba(255,255,255,.36);font-size:12px}@media(max-width:720px){.topbar-inner{padding:12px 18px}.brand img{height:30px}.brand span{display:none}.hero{min-height:470px}.hero-content{padding:82px 20px 34px}.content{padding:28px 20px 58px}.cast-row{grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.synopsis{font-size:15px}.meta-row{align-items:flex-start;flex-direction:column;gap:5px}.meta-val{text-align:left}}
"""
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
<meta property="og:site_name" content="MovieNotice"/>
<meta property="og:title" content="{h(page_title)}"/>
<meta property="og:description" content="{h(description)}"/>
<meta property="og:url" content="{h(url)}"/>
<meta property="og:image" content="{h(poster or hero_image)}"/>
<meta name="twitter:card" content="summary_large_image"/>
<meta name="twitter:title" content="{h(page_title)}"/>
<meta name="twitter:description" content="{h(description)}"/>
<meta name="twitter:image" content="{h(poster or hero_image)}"/>
<link rel="icon" href="../../favicon.ico" sizes="32x32"/>
<link rel="icon" href="../../favicon.svg" type="image/svg+xml" sizes="any"/>
<link rel="apple-touch-icon" href="../../apple-touch-icon.png"/>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@200;300;400;500&display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..400,0..1&display=swap" rel="stylesheet"/>
<style>{css}</style>
<script type="application/ld+json">{json.dumps(json_ld, ensure_ascii=False, separators=(",", ":"))}</script>
</head>
<body>
<div class="page-bg"></div>
<header class="topbar"><div class="topbar-inner"><a class="brand" href="../../"><img src="../../logo.svg" alt="MovieNotice 電影佈告欄"/><span>電影佈告欄</span></a><a class="back-link" href="../../">回電影列表</a></div></header>
<main>
<section class="hero"><div class="hero-media">{hero_media}</div><div class="hero-content"><div class="genre-tags">{genre_tags}</div><h1>{h(title_zh)}</h1><p class="subtitle">{h(subtitle)}</p><div class="ratings">{ratings_html}</div>{trailer_html}</div></section>
<section class="content">
{f'<p class="synopsis">{h(detail.get("synopsis") or movie.get("synopsis"))}</p>' if (detail.get("synopsis") or movie.get("synopsis")) else ''}
{f'<div class="crew-grid">{crew_html}</div>' if crew_html else ''}
{f'<div><p class="section-label">主要演員</p><div class="cast-row">{cast_html}</div></div>' if cast_html else ''}
<div><p class="section-label">其他資訊</p><div class="meta-panel">{render_meta_panel(movie, detail)}</div></div>
<p class="footer-note">MovieNotice · 資料來源 TMDB、OMDb（含 IMDb、爛番茄、Metacritic 評分）· 更新時間 {h(format_date(str(generated_at)[:10]))}</p>
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
