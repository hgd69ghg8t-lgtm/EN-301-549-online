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

_Recorded on completion._
