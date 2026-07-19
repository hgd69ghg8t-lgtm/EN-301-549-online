# Performance: baseline, method and budgets

This file records how the site's front-end resource cost is measured, the
baseline before the asset/search performance phase, and the outcome after
it. It is the reference for the deterministic budgets enforced by
`npm run test:performance`.

## How to measure locally

```
npm run build
PLAYWRIGHT_CHROMIUM_PATH=<chromium> node scripts/measure-performance.mjs        # human summary
PLAYWRIGHT_CHROMIUM_PATH=<chromium> node scripts/measure-performance.mjs --json # machine-readable
```

`scripts/measure-performance.mjs` loads representative pages in headless
Chromium against the same local static server the browser suites use
(`scripts/browser-test-lib.mjs`), and records, per page:

- request count (total and excluding the HTML document),
- decoded bytes per resource type (HTML, CSS, JS, font, search indexes,
  images),
- the gzip size of each file on disk (a proxy for what a production host
  transfers — see limitations),
- `DOMContentLoaded` / `load` timings and any layout-shift score,

plus which search index (small suggestion index vs full-text index) is
fetched when typing into the header search box and when loading the full
search page.

### Test environment

- Headless Chromium (the environment's pinned Playwright build).
- A local Node static file server serving `docs/` uncompressed over
  `http://127.0.0.1`, with the custom 404 page returned at a real 404
  status for missing paths (like GitHub Pages / Cloudflare Pages).
- Representative pages: `index.html`, `about.html`, `clause-9-web.html`,
  `annex-b-functional-performance-relationship.html`, `search.html`,
  `404.html`.

### Limitations of local measurement

Local measurement reliably captures **resource counts and sizes** and
**relative before/after differences**, and it exposes obvious
main-thread or request-graph regressions. It does **not** model real
mobile-network latency, bandwidth, or CPU. The local server serves
uncompressed bytes, so "decoded" ≈ "transfer" locally; the "gzip (disk)"
column estimates production transfer because GitHub Pages and Cloudflare
Pages serve gzip/brotli. Wall-clock timings are shown only for relative
comparison and are **never** used as CI budgets — hosted runners vary too
much for a stable millisecond threshold. Budgets are based on bytes and
request counts, which are deterministic.

## Baseline (before this phase)

Measured on the committed `docs/` at the parent commit. Decoded KB as the
browser received them; the two self-hosted variable fonts are already
woff2-compressed, so gzip does not shrink them further.

| Page | Requests (excl. HTML) | JS decoded | CSS decoded | Font decoded | Full-index fetched |
|---|---|---|---|---|---|
| index.html | 5 | 31.9 KB | 50.6 KB | 66.5 KB (2 files) | no |
| about.html | 5 | 31.9 KB | 50.6 KB | 66.5 KB (2 files) | no |
| clause-9-web.html | 5 | 31.9 KB | 50.6 KB | 66.5 KB (2 files) | no |
| annex-b-…relationship.html | 5 | 31.9 KB | 50.6 KB | 66.5 KB (2 files) | no |
| search.html | 6 | 31.9 KB | 50.6 KB | 66.5 KB (2 files) | **yes — 719.8 KB decoded / 130 KB gzip** |
| 404.html | 6 | 31.9 KB | 50.6 KB | 66.5 KB (2 files) | no |

Interaction behaviour:

- **Typing in the header search box fetched the full 719.8 KB search
  index** (130 KB gzip) on every page — the single largest avoidable
  transfer, incurred just to show a few title suggestions.
- The full search page fetched the same 719.8 KB index.

Baseline observations that shaped the work:

1. Two webfonts cost ~66.5 KB and two requests on every page, for a
   design that reads well in system fonts.
2. One 32 KB unminified JavaScript file loaded on every page, including
   the full search-results rendering machinery that only `search.html`
   needs.
3. The 720 KB full-text index was fetched for header suggestions, which
   need only titles and clause numbers.

## Outcome (after this phase)

Same method, same pages, after: system fonts (no webfont), `site.js` split
into a small always-loaded `main` bundle plus conditional `tables` and
`search-page` bundles, minified and content-fingerprinted CSS/JS, and a
separate body-free suggestion index for the header search box.

Per-page total transfer (gzip on disk — the production-transfer proxy) and
request counts, before → after:

| Page | Requests excl. HTML | Font bytes | Total transfer (gzip) | Reduction |
|---|---|---|---|---|
| index.html | 5 → **3** | 66.5 KB → **0** | 94.2 KB → **16.0 KB** | **−83%** |
| about.html | 5 → **4** | 66.5 KB → **0** | 101.7 KB → **24.1 KB** | **−76%** |
| clause-9-web.html | 5 → **4** | 66.5 KB → **0** | 100.7 KB → **23.0 KB** | **−77%** |
| annex-b-…relationship.html | 5 → **4** | 66.5 KB → **0** | 99.6 KB → **22.0 KB** | **−78%** |
| search.html | 6 → **5** | 66.5 KB → **0** | 223.7 KB → **128.4 KB** | **−43%** |
| 404.html | 6 → **4** | 66.5 KB → **0** | 89.5 KB → **11.2 KB** | **−87%** |

Individual assets (raw / gzip):

| Asset | Before | After |
|---|---|---|
| Stylesheet | 50.6 KB / 13.3 KB (`style.css`) | 31.9 KB / **6.0 KB** (`style.<hash>.css`, minified) |
| JS on an ordinary page | 32.7 KB / 9.2 KB (`site.js`, everything) | 18.1 KB / **5.1 KB** (`main.<hash>.js`) |
| JS on a clause page | 32.7 KB / 9.2 KB | 19.7 KB / **5.7 KB** (`main` + `tables` 1.6 KB / 0.6 KB) |
| JS on search.html | 32.7 KB / 9.2 KB | 21.6 KB / **6.5 KB** (`main` + `search-page` 3.5 KB / 1.4 KB) |
| Webfonts | 66.5 KB (2 requests) | **0** |
| Header-search index | full 737 KB / 130 KB | suggestions **128.8 KB / 16.4 KB** (titles only) |
| Full-text index (search.html only) | 737 KB / 130 KB | **644.9 KB / 114.8 KB** (−12% raw; body cap 4000→1500, top results unchanged) |

Interaction behaviour, before → after:

- **Typing in the header search box** fetched the full 737 KB / 130 KB
  index → now fetches only the 128.8 KB / **16.4 KB** suggestion index
  (titles, clause numbers, page names). ~**87% less** transfer to show
  suggestions, on every page.
- **The full-text index is no longer fetched on ordinary pages at all** —
  only `search.html` loads it.
- **Repeat navigation**: fingerprinted CSS/JS filenames let a host cache
  them for a year as immutable (`_headers`), so moving between pages
  re-downloads only the small HTML; before, unfingerprinted `?v=` assets
  could only be cached briefly.
- **Layout stability**: system fonts render immediately with no webfont
  swap, so there is no font-driven reflow; measured CLS stays 0 on the
  representative pages.

## Budgets (`npm run test:performance`)

`scripts/test-performance.mjs` enforces deterministic budgets — request
graph and byte sizes only, never wall-clock — against a clean build:

| Budget | Threshold | Current |
|---|---|---|
| Homepage requests (excl. HTML) | ≤ 5 | 3 |
| Ordinary clause requests (excl. HTML) | ≤ 6 | 4 |
| Font requests (every page) | 0 | 0 |
| `main` bundle (minified) | ≤ 24 KB | 17.6 KB |
| Stylesheet (minified) | ≤ 40 KB | 31.2 KB |
| Suggestion index | ≤ 160 KB | 125.8 KB |
| Full-text index | ≤ 660 KB (materially below the 738 KB baseline) | 629.8 KB |
| Full index / search-page bundle on ordinary pages | never | never |
| Tables bundle on table-free pages | never | never |

It also fails on any unexpected or failed same-origin request (shared
`browser-test-lib.mjs` runtime tracking). It is part of `npm run
test:browser` / `npm test`.

## Deliberately deferred

- Service worker / offline support.
- Content-Security-Policy (must be designed against the inline pre-paint
  theme script — see `cloudflare-pages.md`).
- Custom-domain / Cloudflare deployment changes.
- Wall-clock performance budgets (too variable on hosted runners).
