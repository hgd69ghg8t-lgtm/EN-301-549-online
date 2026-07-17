# Performance: architecture, budgets, hosting and caching

This page documents how the site stays fast, how the performance budgets
are enforced, and what the hosting layer should (and currently does)
provide. Companion to the "Production assets are minified and
content-hashed" section of the README.

## What the build produces

Every page is static HTML with, at most:

- **one render-blocking stylesheet** — `assets/css/style.<hash>.css`
  (~28.5 KB raw, ~5.8 KB gzipped);
- **one small deferred script** — `assets/js/core.<hash>.js` (~8.7 KB
  raw, ~3 KB gzipped), discovered early in `<head>` but executed after
  parsing;
- **zero webfonts** — typography is the reader's own system font stack,
  so there is no font transfer and no font-swap layout shift;
- a tiny synchronous inline theme script (before the stylesheet, so an
  explicitly chosen Dark/Light theme can never flash wrong).

Everything else loads only when it can actually be used:

| Module | Loads when |
| --- | --- |
| `search.<hash>.js` | Eagerly (deferred) on `search.html` only; on other pages injected the first time the header search field gets focus or two typed characters, or when a page arrives with a `?h=` highlight parameter |
| `search-worker.<hash>.js` + `search-index.<hash>.json` | On `search.html` only — the full index is never downloaded on ordinary pages |
| `search-suggestions.<hash>.json` | After search intent in the header (the module itself only loads on intent, and it fetches the index on focus) |
| `tables.<hash>.js` | Emitted by the build only on the 13 pages that contain a `.table-wrap` |
| `reader-library.<hash>.js` | The first time Reading options is opened |

Ordinary reading therefore costs 4 requests (page, CSS, core.js,
favicon) and roughly 40 KB gzipped, most of which is cached after the
first page.

Prefetching is intent-based only: `<link rel="prefetch">` for a
same-origin page the reader hovers or focuses, plus the previous/next
clause during idle time once they are clearly paging sequentially. It is
disabled when `navigator.connection.saveData` is on or the connection
reports a 2G class, capped in count, never external URLs or PDFs, and
never the current page.

## Budgets

`data/performance-budgets.json` holds the measured pre-optimisation
baseline (for the record) and the enforced budgets. CI runs

```
npm run test:performance
```

which serves the **local generated `docs/`** over loopback (never the
public internet — no network-weather flakes), drives Chromium with a
mobile viewport, fast-3G-class network throttling and 4× CPU
throttling, and fails with actionable output when a budget is breached,
e.g.:

```
FAIL: core JavaScript is 31.2 KB; budget is 28 KB.
```

Byte budgets are strict (they are deterministic); timing budgets carry
wide tolerances because throttled timings jitter. Two budgets are
special:

- `fontBytes: 0` — the site must not ship webfonts at all;
- `forbidFullIndexOnOrdinaryPages: true` — no non-search page may fetch
  any JSON during initial load.

If you deliberately grow an asset (a new feature), re-measure with
`node scripts/check-performance.mjs` and raise the budget in the same
commit, explaining why.

## Recommended production cache policy

Content-hashed filenames make the caching story simple and safe:

**Hashed assets** (`assets/css/*.css`, `assets/js/*.js`,
`search-index.<hash>.json`, `search-suggestions.<hash>.json`):

```
Cache-Control: public, max-age=31536000, immutable
```

A hashed file's bytes can never change under the same name — a change
produces a new name and new page references in the same build — so
"cache forever" is correct by construction.

**HTML pages** (and `sitemap.xml`, `robots.txt`):

```
Cache-Control: public, max-age=0, must-revalidate
```

Pages are the mutable entry points that name the immutable assets; they
should revalidate so a deployment is visible immediately (revalidation
of an unchanged page is a cheap 304).

**Host requirements.** Any static host used for this site should
provide: Brotli compression with gzip fallback (the full search index is
662 KB raw but ~118 KB gzipped and smaller still with Brotli), HTTP/2 or
HTTP/3, edge caching, configurable response headers, HTTPS, and correct
MIME types (including `application/json` for the indexes and
`text/javascript` for the worker — a wrong worker MIME type breaks
`new Worker()` in some browsers).

**Precompressed files:** the build deliberately does **not** emit `.br`
or `.gz` files, because the current host (GitHub Pages) cannot serve
them via `Accept-Encoding` negotiation — they would be dead bytes in the
repository. Revisit only on a host that genuinely negotiates them.

## What GitHub Pages actually provides today

Be precise about this — none of the headers above can be *configured* on
GitHub Pages, and nothing in this repository should claim they are
active:

- GitHub Pages serves with `Cache-Control: max-age=600` (10 minutes) on
  all files, gzip (not Brotli) compression, HTTP/2, HTTPS, and correct
  MIME types for everything this site ships. Response headers are not
  configurable.
- **Which optimisation benefits remain anyway:** every byte reduction,
  the request-count reduction, zero fonts, the deferred/split JS, the
  worker, minification and conservative HTML compaction are all
  host-independent. Content hashing still guarantees atomic rollout
  (pages and the assets they name always change together) and gives
  repeat visitors within the 10-minute window instant cache hits; after
  the window, revalidation of an unchanged hashed asset is a 304, not a
  re-download.
- **What a future CDN or static host could improve:** the
  year-long-immutable policy above (repeat visits and clause-to-clause
  navigation would re-download nothing), Brotli (roughly 15–20% smaller
  than gzip on this site's text-heavy payloads), HTTP/3, and closer edge
  caching. Cloudflare in front of Pages, Netlify, or any host with
  header control can apply the policy exactly as written.

## Measuring

```
node scripts/check-performance.mjs              # measure and print a report
node scripts/check-performance.mjs --json out.json   # also save raw numbers
npm run test:performance                        # measure + enforce budgets
```

The static size report lists every production CSS/JS/font/JSON file and
every generated HTML page (raw and gzipped). The page measurements cover
first-load transfer by type, request counts, DCL/load/FCP/LCP/CLS, long
tasks, script evaluation time, DOM nodes, and the search page's
type-to-results latency.
