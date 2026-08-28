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

MOVIE_PAGE_CSS = r"""
:root {
  --paper: #fcfcfb;
  --ink: #191712;
  --muted: #57534a;
  --line: rgba(25, 23, 18, .25);
  --ornament-dot: #c3c3c2;
}

* { box-sizing: border-box; }
html { background: var(--paper); }
body {
  margin: 0;
  overflow-x: hidden;
  background: var(--paper);
  color: var(--ink);
  font-family: 'Lato', -apple-system, BlinkMacSystemFont, sans-serif;
  font-weight: 400;
  font-optical-sizing: auto;
  -webkit-font-smoothing: antialiased;
}

@media (max-width: 1024px) and (pointer: coarse) {
  body.movie-page-swiping {
    overflow: hidden;
    will-change: transform;
    box-shadow: -12px 0 28px rgba(25, 23, 18, .18);
  }
  body.movie-page-snap-back {
    transition: transform .22s cubic-bezier(.22, .61, .36, 1);
  }
  body.movie-page-exiting {
    transition: transform .2s ease-out;
  }
}
.page-bg { display: none; }
.material-symbols-outlined {
  font-family: 'Material Symbols Outlined' !important;
  font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
  font-weight: normal;
  font-style: normal;
  display: inline-block;
  line-height: 1;
  text-transform: none;
  letter-spacing: normal;
}
.topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  height: 56px;
  background: rgba(252, 252, 251, .94);
  border-bottom: 1px solid var(--line);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}
.topbar-inner {
  width: 100%;
  max-width: 1040px;
  height: 100%;
  margin: 0 auto;
  padding: 0 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.brand { min-width: 0; display: flex; align-items: center; gap: 10px; color: var(--ink); text-decoration: none; }
.brand img { display: block; width: auto; height: 40px; }
.brand .nav-copy { display: flex; align-items: baseline; margin-left: -6px; white-space: nowrap; transform: translateY(3px); }
.brand .nav-name { color: #4b422f; font-family: 'Lato', sans-serif; font-size: 12px; font-weight: 500; line-height: 1.15; letter-spacing: .04em; }
.back-link {
  flex-shrink: 0;
  color: #6b675e;
  font-size: 12px;
  letter-spacing: .04em;
  text-decoration: none;
  transition: color .18s ease;
}
.back-link:hover { color: var(--ink); }
.back-link::before { content: '←'; margin-right: 6px; }
.hero { position: relative; height: 480px; overflow: hidden; }
.hero-media { position: absolute; inset: 0; background: #d7d5cf; }
.hero-media img { width: 100%; height: 100%; object-fit: cover; object-position: top center; display: block; }
.hero-media::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(to bottom, transparent 0%, rgba(25, 23, 18, .16) 24%, rgba(25, 23, 18, .9) 100%);
}
.hero-content {
  position: absolute;
  z-index: 1;
  left: 50%;
  bottom: 0;
  width: 100%;
  max-width: 1040px;
  padding: 24px 32px;
  transform: translateX(-50%);
}
.genre-tags { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 10px; }
.genre-tag {
  padding: 2px 10px;
  color: #fff;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, .45);
  border-radius: 0;
  font-size: 10px;
  letter-spacing: .05em;
}
h1 {
  margin: 0 0 4px;
  color: #fff;
  font-family: 'Crimson Pro', 'Noto Serif TC', serif;
  font-size: clamp(24px, 4vw, 36px);
  font-weight: 400;
  line-height: 1.2;
}
.subtitle { margin: 0; color: rgba(255, 255, 255, .65); font-size: 14px; }
.original-title { font-family: 'Lora', serif; font-style: italic; font-weight: 400; }
.ratings { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin: 18px 0 20px; }
.rating-divider { width: 1px; height: 12px; background: rgba(255, 255, 255, .3); }
.rating-item { display: flex; align-items: center; gap: 4px; color: rgba(255, 255, 255, .55); font-size: 13px; }
.rating-item .star { color: rgba(255, 255, 255, .65); font-size: 13px; font-variation-settings: 'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 24; }
.rating-item .val { color: #fff; }
.trailer-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 18px 6px 8px;
  color: #fff;
  background: rgba(255, 255, 255, .2);
  border: 1px solid rgba(255, 255, 255, .4);
  border-radius: 0;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  font-size: 14px;
  text-decoration: none;
  transition: background .2s ease;
}
.trailer-link:hover { background: rgba(255, 255, 255, .28); }
.content { width: 100%; max-width: 1040px; margin: 0 auto; padding: 32px 32px 72px; }
.content > * + * { margin-top: 32px; }
.synopsis {
  margin: 0;
  color: #403d36;
  font-family: 'Crimson Pro', 'Noto Serif TC', serif;
  font-size: 18px;
  line-height: 1.9;
}
.crew-grid,
.meta-panel {
  position: relative;
  background: transparent;
  border: 1px solid rgba(25, 23, 18, .36);
  box-shadow: inset 0 0 0 5px var(--paper), inset 0 0 0 6px var(--line);
}
.crew-grid::after,
.meta-panel::after {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(circle 5px at 6px 6px, var(--ornament-dot) 0 1.5px, var(--paper) 1.5px 5px, transparent 5px),
    radial-gradient(circle 5px at 50% 6px, var(--ornament-dot) 0 1.5px, var(--paper) 1.5px 5px, transparent 5px),
    radial-gradient(circle 5px at calc(100% - 6px) 6px, var(--ornament-dot) 0 1.5px, var(--paper) 1.5px 5px, transparent 5px),
    radial-gradient(circle 5px at 6px calc(100% - 6px), var(--ornament-dot) 0 1.5px, var(--paper) 1.5px 5px, transparent 5px),
    radial-gradient(circle 5px at 50% calc(100% - 6px), var(--ornament-dot) 0 1.5px, var(--paper) 1.5px 5px, transparent 5px),
    radial-gradient(circle 5px at calc(100% - 6px) calc(100% - 6px), var(--ornament-dot) 0 1.5px, var(--paper) 1.5px 5px, transparent 5px);
}
.crew-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  padding: 26px;
}
.crew-name, .cast-name { margin: 0; color: #4b4840; font-size: 14px; font-weight: 500; }
.cast-name { color: #403d36; }
.crew-grid > div { min-width: 0; }
.crew-name { overflow-wrap: anywhere; }
.crew-role { margin: 4px 0 0; color: #777168; font-size: 12px; }
.cast-char { margin: 4px 0 0; color: #777168; font-family: 'Lora', serif; font-size: 12px; font-style: normal; }
.detail-section { margin-top: 48px !important; }
.section-label { margin: 0 0 18px; color: var(--muted); font-family: 'Noto Serif TC', serif; font-size: 16px; font-weight: 600; letter-spacing: .06em; }
.cast-row { display: grid; grid-template-columns: repeat(auto-fill, minmax(80px, 1fr)); gap: 24px 16px; }
.cast-card { min-width: 0; text-align: center; }
.cast-photo, .cast-no-photo {
  width: 64px;
  height: 64px;
  margin: 0 auto 14px;
  border-radius: 999px;
  border: 1px solid rgba(25, 23, 18, .16);
  object-fit: cover;
}
.cast-no-photo { display: flex; align-items: center; justify-content: center; color: rgba(25, 23, 18, .25); background: rgba(25, 23, 18, .05); border: 1px solid var(--line); }
.cast-no-photo .material-symbols-outlined { width: 24px; height: 24px; font-size: 24px; line-height: 24px; }
.cast-name { font-size: 13px; line-height: 1.3; }
.cast-char { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.meta-panel {
  padding: 26px;
}
.meta-row { display: flex; gap: 16px; margin-bottom: 12px; }
.meta-row:last-child { margin-bottom: 0; }
.meta-key { width: 80px; flex-shrink: 0; padding-top: 2px; color: #625e56; font-size: 13px; }
.meta-val { color: #36332d; font-size: 13px; }

@media (max-width: 1024px) {
  .content { padding-bottom: 96px; }
}

@media (max-width: 720px) {
  .topbar { height: 56px; }
  .topbar-inner { padding: 0 20px; }
  .brand { gap: 4px; }
  .brand img { height: 30px; }
  .brand .nav-copy { margin-left: -4px; transform: translateY(0); }
  .hero { height: 45vh; min-height: 300px; }
  .hero-content { padding: 24px 20px; }
  .content { padding: 32px 20px 96px; }
  .crew-grid { grid-template-columns: repeat(2, 1fr); }
  .cast-row { display: flex; gap: 16px; overflow-x: auto; padding-bottom: 8px; scrollbar-width: none; }
  .cast-row::-webkit-scrollbar { display: none; }
  .cast-card { width: 80px; flex: 0 0 80px; }
  .meta-row { align-items: flex-start; }
}
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
    slug = ""
    for title in (
        movie.get("titleEn"),
        movie.get("origTitle"),
        movie.get("titleZh"),
    ):
        if not title:
            continue
        has_cjk = bool(re.search(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]", title))
        ascii_letter_count = len(re.findall(r"[a-z]", title.lower()))
        if has_cjk and ascii_letter_count < 3:
            continue
        if ascii_letter_count == 0 and any(
            char.isalpha() and not char.isascii() for char in title
        ):
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        if slug:
            break
    slug = slug or "movie"
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
        items.append(("TMDB", format_tmdb_score(detail.get("voteAverage"))))
    return items


def format_tmdb_score(value):
    """將 TMDB 的十分制分數轉成與 TMDB 網站一致的百分比。"""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{int(score * 10 + 0.5)}%"


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
    subtitle_meta = " · ".join(
        part for part in [format_release_dates(movie), f"{detail.get('duration')}分鐘" if detail.get("duration") else ""] if part
    )
    subtitle = (
        (f'<span class="original-title">{h(title_en)}</span>' if title_en else "")
        + (" · " if title_en and subtitle_meta else "")
        + h(subtitle_meta)
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
            else '<div class="cast-no-photo"><span class="material-symbols-outlined" aria-hidden="true">person</span></div>'
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
<link href="https://fonts.googleapis.com/css2?family=Crimson+Pro:ital,wght@0,300..600;1,300..600&amp;family=Lato:wght@300;400;500;700&amp;family=Lora:ital,wght@0,400..700;1,400..700&amp;family=Noto+Serif+TC:wght@400;500;600&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..400,0..1&display=swap" rel="stylesheet"/>
<link rel="stylesheet" href="../../movie-page.css?v=24"/>
<script src="../../movie-page.js?v=3" defer></script>
<script type="application/ld+json">{json.dumps(json_ld, ensure_ascii=False, separators=(",", ":"))}</script>
</head>
<body>
<div class="page-bg"></div>
<header class="topbar"><div class="topbar-inner"><a class="brand" href="../../"><img src="../../logo.svg?v=10" alt="MovieNotice 電影佈告欄"/><span class="nav-copy"><span class="nav-name">電影佈告欄</span></span></a><a class="back-link" href="../../">返回</a></div></header>
<main>
<section class="hero"><div class="hero-media">{hero_media}</div><div class="hero-content"><div class="genre-tags">{genre_tags}</div><h1>{h(title_zh)}</h1><p class="subtitle">{subtitle}</p><div class="ratings">{ratings_html}</div>{trailer_html}</div></section>
<section class="content">
{f'<p class="synopsis">{h(detail.get("synopsis") or movie.get("synopsis"))}</p>' if (detail.get("synopsis") or movie.get("synopsis")) else ''}
{f'<div class="crew-grid">{crew_html}</div>' if crew_html else ''}
{f'<div class="detail-section"><p class="section-label">主要演員</p><div class="cast-row">{cast_html}</div></div>' if cast_html else ''}
<div class="detail-section"><p class="section-label">其他資訊</p><div class="meta-panel">{render_meta_panel(movie, detail)}</div></div>
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
        ("https://movienotice.pages.dev/privacy.html", "yearly", "0.3"),
        ("https://movienotice.pages.dev/terms.html", "yearly", "0.3"),
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
