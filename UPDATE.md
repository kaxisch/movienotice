# Weekly Update Flow

## 1. Run the crawler

From the project root:

```bash
python3 scripts/weekly_check.py
```

Required in `scripts/.env`:

```env
TMDB_API_KEY=...
OMDB_API_KEYS=key1,key2,key3,key4
```

This updates:

- `data/movie-data.json`
- `data/tw-whitelist.json`
- `data/atmovies-candidates.json`
- `data/atmovies-next-snapshot.json`
- `data/atmovies-next-diff.json`
- `data/missing-tw-dates.json`
- `data/YYYY-MM-DD.tsv`

## 2. Check the site locally

Open the site locally and confirm:

- `現正熱映 / 即將上映` counts look reasonable
- modal content loads correctly
- IMDb / Rotten Tomatoes / Metacritic ratings appear
- obvious TMDB mismatches are not present

## 3. If the browser still shows old data

Because the site uses a service worker, local preview may keep old files cached.

In browser DevTools:

1. Open `Application`
2. Go to `Service Workers` and click `Unregister`
3. Go to `Storage` and click `Clear site data`
4. Reload the page

## 4. Review output files

Usually the important files are:

- `data/movie-data.json`
- `data/tw-whitelist.json`
- `data/atmovies-candidates.json`
- `data/atmovies-next-diff.json`

Reference / review files:

- `data/atmovies-next-snapshot.json`
- `data/missing-tw-dates.json`
- `data/YYYY-MM-DD.tsv`

## 5. Commit and push

Typical flow:

```bash
git add data/movie-data.json data/tw-whitelist.json data/atmovies-candidates.json
git commit -m "Update weekly movie data"
git push origin main
```

If code changed too, also add:

```bash
git add app.js index.html sw.js scripts/weekly_check.py
```

## 6. Automated Google Sheets weekly run

GitHub Actions can run the crawler every Wednesday and Saturday at 09:00 Asia/Taipei:

```yaml
cron: "0 1 * * 3,6"
```

The workflow writes the generated `data/YYYY-MM-DD.tsv` into Google Sheets:

- Drive folder: `tw movie` (prefer setting the exact folder id)
- Spreadsheet: `movienotice_weekly`
- Worksheet per run: `YYYY-MM-DD`
- Columns: `類別`, `台灣中文片名`, `台灣上映日期`, `原文片名`, `連結`, `原上映日期`, `備註`

The sheet includes these review categories:

- `missing_tw_date`
- `tmdb_not_found`
- `近期上映新增`
- `近期上映清單移除` (removed from Atmovies NEXT only; it may still be on the site as `現正熱映`)
- `近期上映資料變更`
- `人工保留片`
- `現正熱映`
- `即將上映`

`data/manual-releases.json` stores confirmed theatrical releases that should stay visible
even when they are not currently listed by Atmovies. These rows are deduplicated by TMDB ID,
so if Atmovies later lists the movie again, the Atmovies-sourced entry wins and the manual
row only acts as backup.

Recommended setup: create the `movienotice_weekly` spreadsheet manually in your Drive,
share it with the service account email as Editor, and set `GOOGLE_SPREADSHEET_ID`.
This keeps the file owned by your Google account and avoids service-account Drive quota issues.

Required GitHub Secrets:

```env
TMDB_API_KEY=...
OMDB_API_KEYS=key1,key2,key3,key4
GOOGLE_SERVICE_ACCOUNT_JSON={...}
GOOGLE_SPREADSHEET_ID=...
```

Optional fallback secret if the workflow should find/create the spreadsheet by folder:

```env
GOOGLE_DRIVE_FOLDER_ID=...
```

Optional GitHub Variables:

```env
GOOGLE_DRIVE_FOLDER_NAME=tw movie
GOOGLE_SPREADSHEET_NAME=movienotice_weekly
```

Share the `tw movie` folder with the service account email and grant Editor access.
If the same date is published again, the existing date worksheet is cleared and rewritten.

The workflow also validates the generated site data before updating the public site.
It fails without publishing site changes if:

- `movie-data.json` is not valid JSON or required movie fields are missing
- `現正熱映` or `即將上映` drops below 20 movies
- total site movies drops below 50
- total site movies drops below 50% of the previous committed site data
- `missing_tw_date` or `tmdb_not_found` exceeds 40 items

When validation passes, GitHub Actions commits these site data files back to `main`:

- `data/movie-data.json`
- `data/tw-whitelist.json`
- `data/atmovies-candidates.json`
- `data/atmovies-next-snapshot.json`
- `data/atmovies-next-diff.json`

## Notes

- The public site now reads static data from `data/movie-data.json`
- Regular visitors do not consume TMDB / OMDb API usage
- API usage happens when you run `scripts/weekly_check.py`
- `data/atmovies-next-diff.json` compares this run with the previous `近期上映` snapshot and shows `added` / `removed` / `changed`

## Recent UI Notes

- `modal` now supports mobile / tablet right-swipe close
- right-swipe close timing was tuned to feel smoother and slightly slower
- opening `modal` now shows a temporary hero image first, so text does not appear much earlier than the image
- iPhone Safari `modal` scrolling was adjusted to reduce background page exposure during vertical drag / overscroll
- bottom spacing in the `其他資訊` area was increased to `56px` plus safe-area inset on mobile
