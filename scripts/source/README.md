# Readable asset sources

The hand-authored, documented source for every production stylesheet and
script. `scripts/build.py` minifies these (via `scripts/minify-assets.mjs`
— terser for JS, csso for CSS, both pinned in `package-lock.json`) and
writes content-hashed files under `docs/assets/`; never edit anything
under `docs/assets/css` or `docs/assets/js` by hand.

| File | Production role |
| --- | --- |
| `style.css` | The one stylesheet, both themes, print, forced colours |
| `core.js` | The only script on every page (deferred, in `<head>`): disclosures, preferences, copy-link, back-to-top, prefetch, lazy-loading of the modules below |
| `search.js` | Search page UI + header suggestions; loads on search intent |
| `search-worker.js` | Full-index ranking off the main thread (search page) |
| `tables.js` | Scrollable-table access; only emitted on pages with tables |
| `reader-library.js` | Saved/recent page lists; loads when Reading options opens |

The scoring functions in `search.js` and `search-worker.js` must stay
identical — the worker runs standalone, and the no-Worker fallback must
rank results the same way.

This directory is scanned by the minifier: only `.js` and `.css` files
become assets (this README is ignored).
