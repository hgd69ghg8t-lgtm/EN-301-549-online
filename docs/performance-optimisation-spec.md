# Performance optimisation specification — EN 301 549 Online

Status: **binding** for the staged performance-optimisation project tracked in
`.claude/performance-progress.md` and `.claude/performance-tasks/`.

Provenance: the commissioning instructions referenced an attached specification
that was not included with the message. With the maintainer's agreement this
document was drafted from a full repository analysis (2026-07-17, commit
`c0d0405`) and approved as the binding specification. Any deviation discovered
during implementation must be recorded in
`docs/performance-optimisation-results.md`.

## 1. Scope

Improve the delivered performance of the generated site under `docs/`
(GitHub Pages) — bytes on the wire, effective caching, font rendering,
JavaScript cost, search-index download size, and navigation latency — without
changing what the site says, how accessible it is, or how it is built and
verified.

## 2. Binding constraints

These apply to **every** task. A change that violates any of them is rejected,
whatever it gains.

- **C1 — ETSI wording integrity.** Visible text reproduced from ETSI EN 301 549
  V4.1.0 must not change. Protected `content/*.html` fragments and
  `data/etsi-content-hashes.json` are not modified by this project.
  `scripts/update_etsi_hashes.py` is never run.
- **C2 — Deterministic builds.** A clean rebuild from unchanged source produces
  byte-identical `docs/` output. The CI step "Fail if committed docs/ doesn't
  match a clean rebuild" must keep passing. No timestamps, no randomness, no
  environment-dependent output.
- **C3 — Python-stdlib-only build.** `scripts/build.py` and every script it
  imports keep working on Python 3 standard library alone. npm/Node remain
  test-only (`html-validate`, Playwright). No new build-time dependencies of
  any kind.
- **C4 — Accessibility and progressive enhancement.** All existing suites
  (`test_build.py`, `check-contrast.py`, html-validate, `test:a11y`,
  `test:layout`, `test:search`, `test:theme`) keep passing, unweakened. Every
  feature that works without JavaScript today still works without JavaScript.
  The pre-paint theme script stays inline and before the stylesheet.
- **C5 — Measured claims only.** Every performance claim is backed by a
  before/after measurement (raw and gzipped bytes; behaviour observed in the
  Playwright suites). Estimates are labelled as estimates.
- **C6 — GitHub Pages hosting.** No server configuration, no custom headers,
  no service assumptions beyond: gzip transfer encoding, `Cache-Control:
  max-age=600` on all responses, HTTPS/HTTP2. Compressed size is the honest
  metric; raw sizes are reported alongside for context.

## 3. Requirements

Requirement IDs are stable; each maps to exactly one task file.

### Baseline and measurement (task 00)

- **R-001** Add `scripts/perf-report.py` (stdlib only): reports raw and
  gzip-compressed (level 9) sizes of every generated HTML page, the CSS, the
  JS, both fonts, favicon images and the search index; plus derived figures —
  total site weight, worst-page and median-page first-visit weight (page +
  CSS + JS + fonts), and the search-first-keystroke cost.
- **R-002** Capture the baseline measurements before any production change and
  record them in `.claude/performance-progress.md` (and later in the results
  document).
- **R-003** Confirm the full existing test suite is green before any change,
  so later failures are attributable.

### Fonts and theme paint (task 10)

- **R-010** Preload both self-hosted WOFF2 fonts from every page's head
  (`rel="preload" as="font" type="font/woff2" crossorigin`), placed after the
  stylesheet link so CSS retains fetch priority.
- **R-011** Reduce font-swap layout shift: metric-tuned local fallback
  `@font-face` rules (`size-adjust`, `ascent-override`, `descent-override`,
  `line-gap-override`) for the body and heading stacks, keeping
  `font-display: swap` (never `block` — text must stay visible).
- **R-012** The pre-paint theme script ordering guarantees (metas → script →
  stylesheet; synchronous; no async step) remain intact and unit-tested.
- **R-013** Font files themselves are not re-encoded or subset in this project
  (licence-preserving files as distributed; recorded as a rejected
  optimisation with rationale).

### Asset pipeline and caching (task 20)

- **R-020** Replace `?v=<hash>` query versioning with content-hashed
  filenames: `docs/assets/css/style.<hash>.css` and
  `docs/assets/js/site.<hash>.js`, referenced from every page. Hash derived
  from file content (first 8 hex chars of SHA-256), so determinism (C2) holds.
- **R-021** Relocate the hand-authored CSS/JS sources out of `docs/` into a
  top-level `assets/` source directory; `docs/assets/` becomes fully
  build-generated for CSS/JS. The build removes stale hashed CSS/JS files on
  rebuild.
- **R-022** Minify the generated CSS with a conservative, deterministic,
  stdlib-only minifier (strip comments and inter-rule whitespace only — no
  property rewriting, no selector mangling).
- **R-023** JavaScript is shipped un-minified. Rationale (recorded): gzip
  already compresses it to ~a quarter; a hand-rolled JS minifier is a
  correctness risk that outweighs the residual byte savings; no build-time
  Node tooling is permitted (C3).
- **R-024** `scripts/check-contrast.py`, `scripts/test_build.py`, the
  Playwright suites and the READMEs are updated for the new source locations
  and reference style; no test is weakened.

### JavaScript loading and execution (task 30)

- **R-030** Load the site script non-blockingly: `<script defer>` in the head
  (or retain end-of-body if measurement shows no benefit — decision and
  measurement recorded either way).
- **R-031** Audit `site.js` initialisation: no forced synchronous reflows on
  load, DOM queries bounded, listeners bound only when their targets exist.
  Fix what the audit finds; behaviour is otherwise unchanged.
- **R-032** No functional change: all Playwright suites pass unmodified except
  where they assert asset paths.

### Search index (task 40)

- **R-040** Split the search index so the header search suggestions (present
  on every page) no longer download section body text: a titles-only index
  (url, page, title) for suggestions, and a full index (with bodies) fetched
  only by the search page.
- **R-041** Reduce full-index size where measurable at the gzip level without
  changing result quality: deduplicate repeated page names via a page table;
  keep `SEARCH_BODY_MAX_CHARS` unless measurement justifies lowering it.
- **R-042** Search behaviour is preserved: same matching semantics, same
  ranking, same snippets, same no-JS fallback messaging. `test:search` is
  extended (not weakened) to cover the split and to assert suggestions never
  fetch the full index.
- **R-043** Both index files are deterministic build outputs (C2).

### HTML delivery and navigation prefetch (task 50)

- **R-050** Each generated page's head carries `<link rel="prefetch">` for its
  pager's previous and next pages (build-time static hints only; the browser
  decides — no JS fetch loops, honouring data-saver behaviour by default).
- **R-051** Head hygiene review: element order is theme metas → pre-paint
  script → Open Graph/meta → stylesheet → font preloads → icons → prefetch;
  anything unused is removed or its retention justified in the results doc.
- **R-052** Head-order and prefetch correctness are asserted in
  `scripts/test_build.py`.

### Performance regression suite, budgets, CI and docs (task 60)

- **R-060** `scripts/perf-report.py --budget` enforces hard gzipped-size
  budgets (values fixed after task 50 from measured reality plus stated
  headroom) for: CSS, JS, each font, titles index, full index, worst-page
  HTML, and worst-page first-visit weight. Non-zero exit on breach.
- **R-061** New Playwright suite `scripts/test-perf.mjs` (`npm run
  test:perf`): serves `docs/` locally and asserts (a) no console errors on a
  sample of pages, (b) typing in the header search fetches only the
  titles index, (c) the full index is fetched on the search page only, and
  (d) stylesheet/script/font URLs are the hashed build outputs.
- **R-062** CI runs the budget check and the perf suite on every push/PR.
- **R-063** `README.md` and `docs-for-maintainers/` document the perf
  tooling, the budgets, and how to update a budget deliberately.

### Final verification and results (task 70)

- **R-070** Full regression: every Python and Node suite, html-validate, and
  the new perf suite, all green, results recorded.
- **R-071** Determinism verified directly: build twice from a clean tree,
  byte-compare `docs/`.
- **R-072** ETSI integrity verified: build validation passes and
  `git diff <baseline>..HEAD -- content/ data/etsi-content-hashes.json` is
  empty.
- **R-073** `docs/performance-optimisation-results.md` written: baseline vs
  final tables, per-task measurements, tests and results, accessibility
  verification, implementation decisions, rejected optimisations with
  reasons, deviations from this spec, remaining risks.
- **R-074** The complete branch is presented for review. No pull request is
  opened and nothing is merged as part of this project.

## 4. Explicitly rejected optimisations

Recorded up front so they are not re-litigated per task; final rationale and
any new rejections land in the results document.

- Font subsetting / re-encoding (R-013): licence-as-distributed files kept;
  they are already small variable fonts (40 KB + 32 KB).
- JS minification (R-023): correctness risk without Node tooling; gzip
  captures most of the win.
- Inlining critical CSS per page: breaks the single cached stylesheet model,
  grows every page, complicates determinism testing — the stylesheet is
  ~10 KB gzipped and render-blocking only on first visit.
- Service worker / offline caching: significant complexity and update-model
  risk for a reference document site; out of scope.
- Third-party search libraries or services: the static, dependency-free
  search is a project principle.
- HTML minification: readable generated HTML is part of this project's
  auditability; gzip already removes most whitespace cost. May be revisited
  only if measurements show a compelling gzipped win.

## 5. Process requirements

- Tasks execute strictly in file order (00 → 70); one task completes —
  including its tests — before the next begins.
- One focused commit per task, pushed to the feature branch; regenerated
  `docs/` output is committed with the change that caused it.
- `.claude/performance-progress.md` is updated after every task.
- Failing tests are fixed or reported — never hidden, skipped or weakened.
- No parallel editing agents on build/template/JS/test files; read-only
  agents may be used for analysis and review.
