# Task 10 — Fonts and theme paint

Spec requirements: **R-010, R-011, R-012, R-013** (constraints C1–C6 apply).

Depends on: task 00 (baseline recorded).

## Goal

Fonts arrive earlier (preload) and swap with less layout shift (metric-tuned
fallbacks), without touching the pre-paint theme guarantees.

## Steps

1. In `scripts/build.py`'s page template, add two font preloads **after** the
   stylesheet link (CSS keeps fetch priority):
   `<link rel="preload" href="{asset_prefix}assets/fonts/overpass-var.woff2"
   as="font" type="font/woff2" crossorigin>` and the same for
   `sourcesans3-var.woff2`. (`crossorigin` is required for font preloads even
   same-origin, else the browser double-fetches.)
2. In the CSS source, add metric-tuned fallback faces, e.g.
   `@font-face { font-family: 'Overpass Fallback'; src: local('Arial');
   size-adjust/ascent-override/descent-override/line-gap-override: …}` and
   likewise a fallback for Source Sans 3; insert them into the
   `--font-heading` / `--font-body` stacks between the webfont and the
   generic families. Derive override values from the fonts' actual metrics
   (compute from the WOFF2 head/hhea tables with a small throwaway stdlib
   script, or use published metrics for these faces; verify visually).
   Keep `font-display: swap`.
3. Do NOT re-encode or subset the font binaries (R-013 — licence
   as-distributed; record as rejected optimisation).
4. Rebuild; verify determinism (`npm run build` twice → `git diff` clean
   between runs).
5. Extend `scripts/test_build.py`: preloads present on every page, placed
   after the stylesheet link, `crossorigin` present; existing
   `PrePaintOrderingTests` untouched and passing (R-012).

## Files changed

- `scripts/build.py` (template head)
- `docs/assets/css/style.css` (source CSS — still in docs/ until task 20)
- `scripts/test_build.py` (new assertions)
- Regenerated `docs/*.html`

## Tests to run

`python3 -m unittest scripts/test_build.py` · `python3 scripts/check-contrast.py`
· `npm run build` + docs diff clean · `npx html-validate "docs/*.html"` ·
`npm run test:theme` · `npm run test:a11y` · `npm run test:layout`

## Done criteria

- Every page preloads both fonts, correctly ordered; fallback metrics in the
  font stacks; all suites green; determinism holds; one focused commit.
- Measured: first-visit weight delta from preloads (should be 0 — same bytes,
  earlier) recorded in progress file; note any CLS observation from
  Playwright if obtainable.
