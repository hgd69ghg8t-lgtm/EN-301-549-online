# Session handover — build-tooling hardening (17 July 2026)

Main commit: `dde6f198423dab54753442a36606a53a48429394`
("Harden content normalisation and internal resource validation")

## What was done

Three focused build-tooling fixes; no content, design, search, licensing or
performance work.

### 1. `scripts/normalize_content.py` made consistent with the build

- Removed the stale `KEEP_FRAGMENT_H1 = {"index"}` exemption. The page
  template owns the single `<h1>` on every page, homepage included — the
  normaliser now strips a leading fragment `<h1>` from every fragment,
  matching the build's `h1-in-fragment` rule. (No current fragment still
  had one, so no content changed.)
- Duplicate clause numbers / colliding canonical ids are now hard errors:
  the old code silently suffixed duplicates with `-2`/`-3`; the tool now
  reports file, clause number, canonical id, both heading texts and line
  numbers, and instructs the maintainer to fix the source numbering by
  hand. An `<h1>` that is not the fragment's opening heading is also an
  error (deleting it could drop real content), never a silent removal.
- The complete input set is validated before anything is written — one bad
  file blocks every write, so `content/` can never be left half-rewritten.
- New `--check` mode: reports required changes without writing; exit 0
  only when everything is already normalised and valid.

### 2. Parser-based internal-resource validation in `scripts/build.py`

- The `href="..."` regex (`HREF_RE`) is gone. A stdlib `HTMLParser`
  collector (`collect_resources`) records every `id` and every
  `href`/`src`/`srcset` reference — double-quoted, single-quoted and
  unquoted attributes, each srcset candidate individually (descriptors
  like `2x`/`400w` untouched).
- `validate_site_resources()` resolves each local URL against its page
  with `urllib.parse` + `posixpath` (web-path semantics, never OS paths):
  query strings ignored for existence checks, percent-encoding decoded,
  `./`/`../` resolved, traversal outside `docs/` and root-absolute paths
  rejected, target must be a file this build publishes (rendered pages +
  generated extras + committed assets; a stale top-level `docs/*.html`
  can no longer satisfy a link), and a `#fragment` on an HTML target must
  be a real id on that page — same-page and cross-page alike.
  `javascript:` URLs are rejected; `http`/`https`/`mailto`/`tel`/`data`
  and scheme-relative URLs are ignored as external. Errors are
  deterministic: pages sorted by slug, references in document order.
- Deliberately out of scope: external-link checking (would need a
  scheduled checker), and URLs inside CSS (`url(...)`) or JavaScript.

### 3. Attribute escaping for reconstructed tags

- New shared `escape_attr()` in `scripts/heading_parser.py`
  (`html.escape(value, quote=True)`). Because `HTMLParser` decodes
  entities in attribute values, writing them back verbatim corrupted
  values containing `&`, `<`, `>` or quotes.
- Applied in: `render_starttag()` (normalize_content),
  `render_dt_starttag()` (build), and everywhere a *parsed* id is
  interpolated into generated markup (sidebar subsection tree, on-this-
  page list, heading permalinks, A-Z index). Attribute names, boolean
  attributes, attribute order and the generated canonical ids /
  `tabindex="-1"` are unchanged; escaping happens exactly once (input is
  always the decoded value), so no double escaping.

## Files changed

- `scripts/normalize_content.py` — rewritten (validate-all-then-write,
  `--check`, duplicate errors, h1 rule).
- `scripts/build.py` — resource collector + site-wide validator replace
  the regex link checks; `render_dt_starttag` and id interpolations
  escaped; stale homepage-h1 comment fixed.
- `scripts/heading_parser.py` — added `escape_attr()`.
- `scripts/test_build.py` — 34 new tests (normaliser behaviour and exit
  codes, collector/validator cases incl. srcset, traversal, encoded
  fragments, deterministic ordering, escaping round-trips).
- `.github/workflows/ci.yml`, `README.md`,
  `docs-for-maintainers/{content-ownership,maintenance}.md` — docs
  updated to the real behaviour (external links are NOT checked by CI).

## Tests run (all passing)

- `python3 -m unittest scripts/test_build.py` — 49 tests OK
- `python3 scripts/check-contrast.py` — 80 pairings OK
- `npm run build` — 37 pages, byte-identical rebuild
- `npx html-validate "docs/*.html"` — OK
- `npm run test:a11y` / `test:layout` / `test:search` / `test:theme` — OK
- `python3 scripts/normalize_content.py --check` — exit 0, no changes needed
- `git diff --exit-code -- docs/` and
  `git diff --exit-code HEAD -- data/etsi-content-hashes.json` — clean

## Integrity

No reproduced ETSI wording changed (no `content/clause-*` or
`content/annex-*` diffs at all), `data/etsi-content-hashes.json` is
unchanged, and the committed `docs/` output matches a clean rebuild.

## Remaining limitations

- External (http/https) links are still unchecked; a scheduled external-
  link checker remains future work.
- URLs inside CSS (`url(...)` for webfonts) and JavaScript are not
  validated.
- The normaliser's `--check` mode is not yet a CI step (the build's own
  validators already fail CI on the same problems in practice).
