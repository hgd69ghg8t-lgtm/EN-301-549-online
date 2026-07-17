# Maintenance guide

Routine maintenance tasks for this site, in one place. Each section says what to change, where, and how to verify it. After any of these, always finish with:

```
python3 scripts/build.py && git diff --exit-code -- docs/
```

If that reports a diff, `docs/` was out of date — commit the rebuilt output together with your source change. See the README's ["Which files are source of truth"](../README.md#which-files-are-source-of-truth-and-how-to-rebuild) section for the full list of what's hand-edited versus generated.

## Updating the ETSI publication status

The standard's current status (draft, under approval, published, superseded, etc.) is described by the `status` field in `data/source-metadata.json` (shown on the About page; the homepage intro also describes the draft status in its own words — update both together). Base any change on what you actually found when checking the [ETSI deliverable page](https://www.etsi.org/deliver/etsi_en/301500_301599/301549/) (the URL in `sourcePdfUrl`). Don't guess or infer a status from indirect signals — check the page itself.

If the version number itself has changed (e.g. a new V4.2.0 supersedes V4.1.0), that's a much bigger change than this section covers — it likely means re-extracting content from a new source PDF (see the README's `pdftotext` instructions) and re-running every step in this guide, not just editing `data/source-metadata.json`.

## Updating the status-check date

`statusLastChecked` in `data/source-metadata.json` must be the date someone genuinely checked ETSI's publication status — never a build timestamp, never advanced just because time has passed. Update it only immediately after actually re-checking the ETSI deliverable page above, in `YYYY-MM-DD` form. The build rejects a missing, malformed, future-dated, or placeholder-looking value here (see `validate_iso_date_field()` in `scripts/build.py`). Record what you found (changed or unchanged) in your commit message.

## Updating the source PDF link

`sourcePdfUrl` in `data/source-metadata.json` is the link readers use to reach the official ETSI page for this standard. If ETSI restructures their site or the deliverable moves, update this field to the new URL — verify the new URL actually loads the correct deliverable before committing it.

If you replace the committed PDF file itself (`docs/source/en_301549v040100va.pdf`) with a different edition:

1. Update `SOURCE_PDF_NAME` and `SOURCE_PDF_PATH` in `scripts/build.py` if the filename changes.
2. Recompute the checksum: `sha256sum docs/source/<the new file>` and update `sha256` in `data/source-metadata.json`.
3. Update `dateDownloaded` and `sourcePdfPublicationDate` to match the new file.
4. Re-check `statusLastChecked` at the same time (see above) — a new download is itself a status check.

## Updating or removing the PDF file size

Nothing to do by hand: the download link's file size (`{{SOURCE_PDF_SIZE}}`) is computed directly from whatever file is actually committed at `docs/source/`, every build — never downloaded from ETSI, never hand-entered, and never able to silently go stale. If the file is missing, or looks implausibly small (under 1&nbsp;KB — almost certainly a truncated or corrupted commit), the build either omits the size (falling back to plain "Download the official ETSI standard (PDF)" wording) or fails outright — see `source_pdf_size()` in `scripts/build.py`.

## Updating clause summaries

`data/clause-summaries.json` holds the short "About this clause"/"About this annex" orientation boxes. To add or edit one:

- Keep it to at most two short paragraphs, each under 400 characters.
- Describe what the clause/annex covers — never interpret conformance requirements, add obligations, or narrow the standard's scope.
- Write it so it's clearly website-authored, in plain language, not something that could be mistaken for ETSI's own wording.
- Use `{{normative}}` / `{{informative}}` to link those words to their definition on the About page — don't hand-write an `<a>` tag (raw HTML isn't supported in this file).
- To say a part is normative or informative, set the optional `"nature": "normative"` (or `"informative"`) field instead of writing the sentence out — the build appends the standard "It is normative/informative, which means …" wording automatically, so it can never drift between entries.
- The slug you key it by must be a real page slug from `scripts/sitemap.json`.

The build validates all of this automatically (unknown slug, duplicate key, empty/oversized text, raw HTML, placeholder text) — but it cannot judge whether a summary is *accurate*. Re-read it against the clause it summarises before committing.

## Adding or changing site-authored wording

Website-authored text (introductions, summaries, navigation labels, the About page's own sentences, the accessibility statement, the search page, notices) lives in `content/index.html`, `content/about.html` (which includes the accessibility statement section), `content/search.html`, and `data/clause-summaries.json` — edit freely, following the [content-authoring conventions](../README.md#content-authoring-conventions) in the README (sentence case, plain language, no italics for publication references, human-readable dates via `{{TOKEN}}`s rather than hand-typed ones).

Never mix new site-authored wording into a clause/annex `content/*.html` file's reproduced ETSI text — those files are protected by the wording-integrity check (see below), and adding your own sentences there would either fail that check or (worse) blur the line between what ETSI wrote and what this website added.

## Protecting ETSI source text

**Never rewrite, simplify, correct, paraphrase, or otherwise change wording reproduced from the ETSI EN 301 549 standard.** This is enforced two ways:

1. `data/etsi-content-hashes.json` records a hash of every clause/annex file's actual text (markup stripped, whitespace collapsed). The build fails, naming the exact file, if any protected file's text no longer matches its recorded hash.
2. That baseline can only be refreshed deliberately, by running `python3 scripts/update_etsi_hashes.py` — never automatically by `scripts/build.py`.

If you have a genuine reason to touch reproduced text — the only legitimate one is correcting an actual transcription error found by comparing against the source PDF, not a copy-edit — after making the fix:

```
python3 scripts/update_etsi_hashes.py
```

and explain exactly what you corrected and why, with a page/clause reference, in your commit message. If the build fails this check and you *didn't* intend to change any wording, that's a signal to investigate (a bad merge, an accidental edit) and revert — not to just re-run the script to make the failure go away.

## Running the full build and test suite

```
npm install                                     # once
npx playwright install --with-deps chromium     # once, for the browser-based tests
python3 scripts/build.py                        # build (also the primary validator)
npm test                                        # build + html-validate
npm run test:a11y                               # axe-core sweep against every page
npm run test:layout                             # responsive layout assertions, 320-1920px
npm run test:search                             # site-search end-to-end checks
git diff --exit-code -- docs/                   # confirm docs/ matches a clean rebuild
```

All of these should be run, and pass, before merging a change that touches `content/`, `data/`, `scripts/`, `docs/assets/`, or `scripts/sitemap.json`.

## Reviewing the accessibility statement

The accessibility statement section of `content/about.html` has a "Testing status" part that must always accurately reflect what has and hasn't actually been done — see the automated-completed / manual-not-yet-completed / still-planned / known-issues / formal-audit-status split in that file. When you complete a real manual test session, update:

- the relevant part of "Testing status" (move it out of "not yet completed" only once it genuinely is),
- the "Review history" table,
- and `docs-for-maintainers/accessibility-testing.md`'s test log (see below) — keep the two in sync.

Never mark manual or screen-reader testing as done without an actual recorded session backing it up.

## Recording manual accessibility testing

Follow the repeatable checklist in [`docs-for-maintainers/accessibility-testing.md`](accessibility-testing.md) (keyboard-only navigation, zoom/reflow/text-spacing, and screen-reader testing with at least NVDA+Firefox/Chrome and VoiceOver+Safari). After a real session, add a new row to that file's test log — date, tester, browser, assistive technology, pages tested, findings, issue links, retest result. Don't overwrite previous rows. Then update the accessibility statement as described above.

## Cross-reference links

Nothing to maintain: references in the text ("clause 5.1.3", "Annex ZA", "[i.25]") are linked automatically at render time from the current headings and clause 2's bibliography. If a heading is renumbered, the links follow it on the next build; a reference the build can't resolve is simply left unlinked, and a clause number duplicated across pages fails the build (`xref-ambiguous-number`).

## Site search

Nothing to maintain: `docs/search-index.json` is regenerated from the content on every build (`build_search_index()` in `scripts/build.py`), and `npm run test:search` verifies the search end-to-end in CI. If a new website-authored page is added, it becomes searchable automatically via its sitemap entry.

## Reviewing broken links

Same-site links and same-page fragment links are checked on every build (`broken-internal-link`, `broken-anchor-link` in `scripts/build.py`) — nothing to do manually for those. External links (the ETSI deliverable page, GitHub links, W3C references in the reproduced front matter) aren't checked automatically and can go stale independently of this repository; periodically click through the external links on the homepage, About page, and accessibility statement and confirm they still resolve.

## Checking the GitHub accessibility issue form

`.github/ISSUE_TEMPLATE/accessibility.yml` is the form linked from the accessibility statement's "Report an accessibility problem" section. Periodically:

- Open a new issue from the template in the actual repository to confirm it still renders as expected (GitHub occasionally changes issue-form rendering).
- Check for open issues filed through it that haven't been triaged.
- If a dedicated, monitored contact channel (a public-sector accessibility mailbox or contact form) is ever set up, add it alongside — or instead of — the GitHub form, and update the accessibility statement's wording accordingly. Don't present the GitHub form as a substitute for a formal public-sector contact channel; it currently is the only reporting route, and the statement says so.

## Refreshing clause 3 anchors safely

Clause 3's glossary and abbreviation term ids (`def-...`) and A-Z index are generated automatically at build time from `content/clause-3-definitions.html`'s `<dt>` elements — see `apply_glossary_terms()` in `scripts/build.py`. There is normally nothing to "refresh" by hand. If you do need to touch this content:

- **Never reorder or reword existing `<dt>`/`<dd>` pairs** without going through the ETSI wording-integrity process above (`clause-3-definitions.html` is a protected file).
- If you add a genuinely new term (e.g. a future version of the standard adds one), leave its `<dt>` without an `id` attribute — the build assigns one deterministically from the term's own text. Only hand-set an `id` if you need to override the generated slug for some reason; the build always keeps an existing `id` rather than overwriting it.
- After any change, rebuild and check the generated `docs/clause-3-definitions.html`: every `<dt>` has a unique id, the A-Z index's letter links all resolve, and letters are still in alphabetical order — all of this is validated automatically (`glossary-term-missing-id`, `glossary-term-duplicate-id`, `az-index-broken-link`, `az-index-unsorted`), so a build failure here means something needs attention before committing.

## Checking licensing and reproduction status

See the README's ["Licensing, copyright and publication readiness"](../README.md#licensing-copyright-and-publication-readiness) section for the full picture. In short, periodically confirm:

- Whether the ETSI reproduction-permission question has been resolved (still "not confirmed" as of this writing) — update the "ETSI reproduction permission" record in the README the moment it is.
- Whether a licence has been chosen yet for this site's own code/design, and that wherever it's stated, it's clear it doesn't extend to the reproduced ETSI text or the trademarks named in it.
- That the publication-readiness checklist in the README still reflects reality — don't let a checked box go stale if circumstances change.
