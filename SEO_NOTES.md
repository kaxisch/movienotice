# MovieNotice SEO Notes

## Current SEO Status

- The site has a basic homepage `title` and `meta description`.
- Google Analytics and Google Search verification are already installed.
- The site is a JavaScript-heavy single-page app, with movie details shown in a modal instead of indexable detail pages.
- There is currently no `canonical`, `robots.txt`, `sitemap.xml`, Open Graph metadata, or structured data markup.

## Biggest SEO Bottleneck

The biggest limitation is not keywords. It is site structure.

- Search engines can likely understand and index the homepage.
- Search engines have a harder time treating each movie as its own searchable page.
- The current `#soon` hash-based navigation does not create strong indexable URLs.
- Movie detail content is hidden behind modal UI, not standalone pages.

## Highest Priority Improvements

### 1. Create indexable movie detail pages

Target direction:

- `/movies/spider-man-brand-new-day`
- `/movies/last-night-in-taipei`

Why this matters:

- Each movie can rank independently.
- Each page can have its own title, description, canonical URL, and structured data.
- This is the highest-leverage SEO change for the project.

Implementation idea:

- Reuse `data/movie-data.json`
- Generate static HTML pages for each movie
- Keep the homepage as the discovery UI, but link to dedicated pages

### 2. Add unique page metadata

Homepage should have a stronger description.

Suggested homepage title:

`台灣上映電影查詢｜現正熱映、即將上映、IMDb/TMDB評分 | MovieNotice`

Suggested homepage description:

`MovieNotice 提供台灣現正熱映與即將上映電影資訊，包含上映日期、IMDb、TMDB、爛番茄與 Metacritic 評分，方便快速查詢近期電影。`

For movie detail pages, generate:

- unique `<title>`
- unique `<meta name="description">`
- `canonical`

Suggested movie page pattern:

- Title: `《電影名》台灣上映日期、評分、預告、劇情簡介 | MovieNotice`
- Description: include title, release date, genres, ratings, and short synopsis

### 3. Add crawl/index files

Add:

- `/robots.txt`
- `/sitemap.xml`

Why this matters:

- Helps search engines discover pages faster
- Helps keep indexing structure clean
- Especially useful once movie detail pages exist

### 4. Add structured data

Recommended types:

- `WebSite`
- `Organization`
- `BreadcrumbList`
- `Movie` on detail pages

Why this matters:

- Helps search engines understand entities and page meaning
- Can improve search appearance eligibility

### 5. Add more crawlable homepage content

The homepage currently relies heavily on JS-rendered cards.

Add visible text sections such as:

- What MovieNotice is
- What data sources it uses
- How often it updates
- A short explanation of `現正熱映` and `即將上映`
- Text links to featured or popular movies

Also improve semantic structure:

- add `<main>`
- add a clear `<h1>`
- add section `<h2>` headings

## Technical Notes

### JavaScript SEO

Google can render JavaScript, but relying on JS for most critical content is still a weaker setup than serving indexable HTML directly.

Current risks:

- content depends on client-side rendering
- movie details are not standalone URLs
- metadata is not page-specific

### Core Web Vitals

Need to monitor:

- LCP
- INP
- CLS

Search Console should be used later to review these.

### Service Worker Caching

The site uses a service worker in [sw.js](/Users/designer/Documents/movienotice/sw.js).

This already caused an update visibility issue once. Future SEO changes should be checked carefully after deployment to confirm the live HTML matches the latest source.

## Recommended Execution Order

If only doing three things first, do them in this order:

1. Build static movie detail pages
2. Add `robots.txt`, `sitemap.xml`, and `canonical`
3. Add page-specific metadata and JSON-LD structured data

## Practical Next Step

Best next implementation step:

1. Improve homepage SEO tags
2. Add `robots.txt`
3. Add `sitemap.xml`
4. Plan static generation for movie detail pages

## Useful References

- Google SEO Starter Guide
  - https://developers.google.com/search/docs/fundamentals/seo-starter-guide
- Google JavaScript SEO Basics
  - https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics
- Google Title Links
  - https://developers.google.com/search/docs/appearance/title-link
- Google Snippets / Meta Descriptions
  - https://developers.google.com/search/docs/appearance/snippet
- Google Structured Data Intro
  - https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data
- Google Core Web Vitals
  - https://developers.google.com/search/docs/appearance/core-web-vitals
