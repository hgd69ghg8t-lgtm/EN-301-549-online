# Task 00 — Baseline and measurement tooling

Spec requirements: **R-001, R-002, R-003** (constraints C1–C6 apply).

## Goal

Create the measurement tool and record the untouched baseline so every later
claim is a measured before/after comparison. No production change.

## Steps

1. `npm ci` (Playwright browsers: use the pre-installed Chromium at
   `/opt/pw-browsers`; `PLAYWRIGHT_BROWSERS_PATH` is already set in the
   remote container — do not run `playwright install` there. In CI the
   existing workflow installs Chromium itself).
2. Write `scripts/perf-report.py` (stdlib only: `pathlib`, `gzip`, `json`,
   `argparse`, `statistics`):
   - Per file (every `docs/*.html`, `docs/assets/css/*.css`,
     `docs/assets/js/*.js`, `docs/assets/fonts/*.woff2`, `docs/assets/img/*`,
     `docs/search-index*.json`): raw bytes and `gzip.compress(data, 9)` bytes.
   - Derived: total site weight; per-page first-visit weight (page HTML +
     CSS + JS + both fonts, gzipped where the browser sees gzip — fonts are
     already compressed, count raw); worst and median page; search
     first-keystroke cost (today: full `search-index.json`).
   - `--json <path>` mode to save a machine-readable snapshot for later
     comparison; human-readable table by default.
   - Handles hashed filenames (globs, not fixed names) so it keeps working
     after task 20. Excludes `docs/source/*.pdf` from page-weight figures
     (report it separately as a static download).
3. Run it; save the snapshot to `.claude/performance-tasks/baseline.json`
   and paste the human-readable summary into this file (below) and into
   `.claude/performance-progress.md`.
4. Run the full existing suite to confirm a green starting point (R-003):
   `python3 -m unittest scripts/test_build.py`, `python3
   scripts/check-contrast.py`, `npm run build` + `git diff --exit-code --
   docs/`, `npx html-validate "docs/*.html"`, `npm run test:a11y`,
   `npm run test:layout`, `npm run test:search`, `npm run test:theme`.
   Record results.

## Files changed

- `scripts/perf-report.py` (new)
- `.claude/performance-tasks/baseline.json` (new)
- This file + `.claude/performance-progress.md` (baseline numbers)

## Done criteria

- Baseline table recorded (raw + gzip for CSS, JS, fonts, search index,
  worst/median page, first-visit weight).
- Full suite green, results noted.
- One commit: measurement tool + baseline records. `docs/` diff is empty.

## Baseline results

Recorded 2026-07-17 on commit `846f69a` (branch
`claude/performance-optimization-planning-ofj09d`); full snapshot in
`.claude/performance-tasks/baseline.json`. Gzip = level 9, the honest
GitHub Pages wire metric (no brotli there).

| Asset | Raw | Gzip |
|---|---|---|
| `assets/css/style.css` | 50.5 KB | 13.3 KB |
| `assets/js/site.js` | 31.9 KB | 9.2 KB |
| `assets/fonts/overpass-var.woff2` | 38.5 KB | (pre-compressed) |
| `assets/fonts/sourcesans3-var.woff2` | 28.1 KB | (pre-compressed) |
| `search-index.json` | **719.8 KB** | **129.5 KB** |
| Largest page (`annex-za-directive-2016-2102.html`) | 127.2 KB | 16.4 KB |

Derived figures (spec R-001):

- Worst first visit: **110.6 KB** (`clause-11-non-web-software.html`:
  21.7 KB page gzip + 13.3 CSS + 9.2 JS + 66.5 fonts)
- Median first visit: **96.7 KB**
- Search first-keystroke download: **129.5 KB gzipped** (719.8 KB raw) —
  the full index, fetched by the header search box on any page
- Total site raw (PDF excluded): 2568.7 KB across 38 pages
- Source PDF (separate static download): 4281.5 KB

Green starting point (R-003), all run on this commit:

- `python3 -m unittest scripts/test_build.py` — OK
- `python3 scripts/check-contrast.py` — OK (80 pairings pass)
- `npm run build` + `git diff --exit-code -- docs/` — clean (deterministic)
- `npx html-validate "docs/*.html"` — OK
- `npm run test:a11y` — OK (37 pages × both automatic themes + 7 pages ×
  both explicit overrides, 0 violations)
- `npm run test:layout` — OK (9 pages × 7 widths)
- `npm run test:search` — OK (all checks pass)
- `npm run test:theme` — OK (all checks pass)

Playwright suites were run with
`PLAYWRIGHT_CHROMIUM_PATH=/opt/pw-browsers/chromium` (the remote
container's pre-installed Chromium; see progress-file setup note).
