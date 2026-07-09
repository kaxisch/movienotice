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
