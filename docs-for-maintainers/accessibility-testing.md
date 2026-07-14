# Manual accessibility testing

This document is for the checks automation genuinely cannot do. CI (`npm test`, `npm run test:a11y`, see [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) already covers: heading structure, one `<h1>` per page, duplicate IDs, broken internal/fragment links, HTML/ARIA conformance, and an axe-core sweep. None of that tells you whether the site is actually *usable* with a keyboard or a screen reader — that's what this checklist is for.

This is a **repeatable test procedure**, not a record of completed testing. The checklists below describe what to do; the [test log](#test-log) at the bottom is where you record what you actually did and found. Do not mark an item as tested until you have actually done it. An unchecked item is honest; a checked item that wasn't really tested is worse than no record at all.

## Keyboard-only testing

Unplug the mouse. Test on at least one full clause page with numbered headings and an "On this page" list (e.g. `clause-9-web.html`), one page with a `data/clause-summaries.json` entry (e.g. `clause-9-web.html` again, or `clause-4-functional-performance.html`), `clause-3-definitions.html` (glossary + A-Z index), and the homepage.

- [ ] **Skip link** — load a page, press Tab once, confirm "Skip to main content" appears and activating it moves focus/reading position past the header and contents sidebar.
- [ ] **Contents sidebar / mobile disclosure** — reach the contents toggle, contents links, and (at a narrow viewport) the close button, using only Tab, Shift+Tab, Enter, and Space; confirm the panel never visually covers other content and Escape also closes it.
- [ ] **Heading links** — reach a numbered heading (its text is itself a link) by keyboard and activate it with Enter; confirm the address bar now holds the deep link and, with JavaScript on, the "Link to this heading copied" announcement fires.
- [ ] **"On this page" list** — reach every link in the "On this page" box by keyboard and confirm each one moves focus/reading position to the correct heading.
- [ ] **Clause summary box** — on a page with a `data/clause-summaries.json` entry, confirm the summary box itself doesn't trap focus or introduce a confusing tab stop (it has no interactive controls, so it should simply be skipped over in the normal reading/tab order).
- [ ] **Glossary definitions and A-Z index** (`clause-3-definitions.html`) — reach the A-Z index and activate a letter link; confirm focus lands on the corresponding `<dt>` term (not just a visual scroll) and that a screen reader would announce the term/definition as the new context. Confirm the "Back to A-Z index" link is reachable and works the same way in reverse.
- [ ] **Previous/next pager** — reach the "previous" and "next" page links at the bottom of a clause page and confirm both work.
- [ ] **Document toolbar** — reach print, copy-link, and (where present) the download link, by keyboard.
- [ ] **PDF/external download link** — reach the "Download the official ETSI standard (PDF)" link (or the no-size fallback wording) by keyboard; confirm it's a real, working link with an accessible name that makes sense out of context (not just "click here" or "PDF").
- [ ] **Focus order** — confirm the order controls receive focus in matches the visual reading order on the page; nothing jumps unexpectedly.
- [ ] **Visible focus** — as you tab through, confirm a visible focus indicator is present on every control reached above, at default zoom.
- [ ] **No keyboard traps** — confirm you can always Tab or Shift+Tab away from every control above, including the mobile contents panel and any `<details>` disclosure, without needing the mouse.

## Zoom, reflow and text spacing

- [ ] **Browser zoom at 200%** — confirm no content is lost, clipped, or overlapping; confirm the heading links and A-Z index are still visible and operable.
- [ ] **Browser zoom at 400%** — same checks as 200%, at 400%.
- [ ] **Reflow at 320 CSS pixels** — confirm no horizontal scrolling is required for the page itself (individual wide tables are expected to scroll within their own region, and that region should have an announced accessible name).
- [ ] **Text spacing override** — apply the [WCAG 1.4.12 text-spacing bookmarklet/extension values](https://www.w3.org/WAI/WCAG21/Understanding/text-spacing.html) and confirm no text is clipped or overlapping.
- [ ] **Forced-colours mode** (Windows, where available) — confirm all controls and focus indicators remain visible and operable.
- [ ] **Reduced motion** — enable "reduce motion" in the OS, confirm in-page anchor navigation (contents links, heading links, on-this-page, A-Z index, back-to-top) jumps instantly instead of animating, and that nothing stops functioning.
- [ ] **Print layout** — print preview a long page, confirm the contents sidebar/toolbar/back-to-top are hidden and the content itself is legible and complete.

## Screen-reader testing

This is a **test plan**, not a record of testing already performed — no screen-reader pass has been completed and recorded for this site yet (see the [test log](#test-log)). Use at minimum one Windows combination and VoiceOver on macOS; testing more combinations is better but these two give the broadest practical coverage.

**Minimum recommended combination:**

- NVDA with Firefox or Chrome (Windows)
- VoiceOver with Safari (macOS)

**Additional combinations, if available:**

- JAWS with Chrome or Edge (Windows)
- VoiceOver (iOS)
- TalkBack (Android)

For each combination, on the same set of pages as the keyboard checklist above, verify:

- [ ] **Page title** — the announced document title is accurate and distinct per page.
- [ ] **Landmarks** — the landmark list (e.g. NVDA/JAWS landmark navigation, VoiceOver Rotor → Landmarks) shows banner (header), navigation (contents), main, and contentinfo (footer) exactly once each; on `clause-3-definitions.html`, the two A-Z index `<nav>` landmarks are announced with distinct, meaningful names (not both just "navigation").
- [ ] **Heading navigation** — the heading list (e.g. NVDA Elements List, VoiceOver Rotor → Headings) shows exactly one H1 and a sensible, non-skipping hierarchy; jumping heading-by-heading reaches every numbered clause heading.
- [ ] **Link lists** — the link list (e.g. VoiceOver Rotor → Links) shows link text that's meaningful out of context — no bare "here"/"link" text, and heading links are distinguishable from each other (each is named by its own heading text).
- [ ] **Current navigation state** — in the contents sidebar, confirm the current page/section is announced as current (not just visually indicated) as you scroll.
- [ ] **Status wording** — confirm the homepage's draft-status wording ("The draft is still under approval…") and the About page's "Standard and source information" are read as ordinary content in a sensible position, so the document's non-final status is discoverable without a site-wide banner.
- [ ] **"On this page" list** — confirm it's announced as a distinct navigable list, and each entry's accessible name matches the heading it links to.
- [ ] **Clause summary box** — confirm the "About this clause"/"About this annex" summary is read as ordinary content in a sensible place (before the reproduced ETSI text it summarises), not confused with the ETSI content itself.
- [ ] **Glossary definitions** (`clause-3-definitions.html`) — confirm each term and its definition are associated in a way the screen reader conveys as a pair (term, then definition), and that following an A-Z index link both moves focus and is announced as landing on the target term.
- [ ] **Heading links** — confirm each numbered heading is announced both as a heading and as a link whose name is the heading's own number and text (e.g. "9.1.1.1 Non-text content"), not "#" or "link".
- [ ] **Download link** — confirm the PDF download link's accessible name and any file-type/size information is announced sensibly (not just a bare filename).

## Test log

Add a new row for every test session. Do not overwrite previous entries — the history matters. Record only sessions that actually happened; do not pre-fill expected results.

| Date | Tester | Browser | Assistive technology | Pages tested | Findings | Issue link(s) | Retest result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| _(none yet)_ | | | | | | | |

The accessibility statement (`content/accessibility-statement.html`) links back to this file. Keep the statement's "review history" table and this log in sync — the statement is the public summary, this file is the working record.
