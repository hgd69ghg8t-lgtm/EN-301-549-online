# Task 40 — Search index split and size

Spec requirements: **R-040, R-041, R-042, R-043** (C1–C6 apply).

Depends on: task 20 (JS source location), task 30 (JS audit done first so
this diff stays search-only).

## Goal

The header search box (on all 40 pages) stops downloading the full 720 KB
index; the full index itself shrinks where gzip-measurably possible. Search
results, ranking and snippets are unchanged.

## Steps

1. In `scripts/build.py` search-index section, emit two deterministic files:
   - `docs/search-index-titles.json`: `{"pages": [names…], "e": [{"u","p"(index),"t"}…]}`
     — everything header suggestions need (they render title + page name,
     score on title; check `site.js` "Header search suggestions" block for
     exactly which fields it touches and keep those).
   - `docs/search-index.json`: full entries incl. `b` bodies; apply the same
     page-name table dedup. Keep `SEARCH_BODY_MAX_CHARS = 4000` unless a
     measured gzip win justifies lowering (R-041) — bodies also feed
     snippets and match quality, so any cut needs `test:search` proof.
2. In `assets/site.js`:
   - `loadSearchIndex()` splits into `loadTitlesIndex()` (suggestions) and
     `loadFullIndex()` (search page), each fetched at most once; both resolve
     to the SAME in-memory entry shape as today (adapt after fetch) so
     `scoreSearchEntry`/`searchHits`/`snippetFor` stay untouched (R-042).
   - Suggestions score on title/page fields only — confirm current behaviour
     for suggestions already effectively title-driven; if body matches
     currently influence suggestion ranking, preserve semantics by keeping
     suggestions on the titles file but document the (tiny, measured)
     ranking difference in the results doc — or fall back to full index on
     the search page only. Decide from the actual code, favouring R-042.
   - `search.html` full search continues to use the full index.
3. Measure: titles-index raw/gzip, full-index raw/gzip before/after dedup,
   first-keystroke cost on a content page before/after.
4. Extend `scripts/test-search.mjs`: existing end-to-end cases unchanged;
   add (a) header suggestions work and trigger a request for the titles file
   only, (b) search.html results still correct, (c) full index requested on
   search page only. (Network assertions via Playwright request events.)
5. Rebuild ×2; determinism; `robots.txt`/`sitemap.xml` unaffected (indexes
   aren't listed — confirm).

## Files changed

`scripts/build.py`, `assets/site.js`, `scripts/test-search.mjs`,
regenerated `docs/` (+ new `docs/search-index-titles.json`).

## Tests to run

Full Python suite · build ×2 determinism · html-validate · `test:search`
(extended) · `test:a11y` · `test:theme` · `perf-report.py` snapshot.

## Done criteria

- Header suggestion first keystroke costs the titles file only (measured,
  expected ≳80 % transfer reduction vs 720 KB raw / ~its gzip size).
- Search results byte-for-byte equivalent for a fixed query set (spot-check
  several queries incl. clause numbers like "9.1.4.4" and glossary terms).
- All suites green; one focused commit.
