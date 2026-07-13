# Manual accessibility testing

This document is for the checks automation genuinely cannot do. CI (`npm test`, `npm run test:a11y`, see [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) already covers: heading structure, one `<h1>` per page, duplicate IDs, broken internal links, HTML/ARIA conformance, and an axe-core sweep. None of that tells you whether the site is actually *usable* with a keyboard or a screen reader — that's what this checklist is for.

Do not mark an item as tested until you have actually done it. An unchecked item is honest; a checked item that wasn't really tested is worse than no record at all.

## Checklist

For each item, test on at least one full page with numbered headings (e.g. `clause-9-web.html`) and the homepage.

- [ ] **Keyboard-only navigation** — unplug the mouse. Reach every interactive control (contents toggle, contents links, print/download/copy-link, heading permalinks, back-to-top, pager) using only Tab, Shift+Tab, Enter, and Space.
- [ ] **Visible focus** — as you tab through, confirm a visible focus indicator is present on every control, including inside the contents panel and on heading permalinks, at default zoom.
- [ ] **Skip link** — load a page, press Tab once, confirm "Skip to main content" appears and activating it moves focus/reading position past the header and contents sidebar.
- [ ] **Page title and heading structure** — confirm the browser tab title is accurate and distinct per page, and that a screen reader's heading list (e.g. NVDA Insights/Elements List, VoiceOver Rotor) shows exactly one H1 and a sensible, non-skipping hierarchy below it.
- [ ] **Landmarks** — confirm a screen reader's landmark list shows banner (header), navigation (contents), main, and contentinfo (footer) exactly once each, correctly nested.
- [ ] **Direct links to requirements** — copy a heading permalink (e.g. the "#" beside "9.1.1.1 Non-text content"), open it in a new tab, confirm it scrolls to and visually highlights the right heading.
- [ ] **Mobile contents interaction** — at a narrow viewport, open the contents panel with keyboard and touch, confirm it does not visually cover other content, confirm you can tab through nav links, confirm Escape and the close button both work and return focus predictably.
- [ ] **Copy-link interaction** — activate both the page-level "Copy link" button and a heading permalink; confirm the announcement is heard by a screen reader without the button's own label changing.
- [ ] **Tables and horizontal scrolling** — on a page with a wide table (e.g. an Annex C or ZA/ZB page), confirm the table's scroll region is reachable and scrollable by keyboard (arrow keys once focused), and that it has an announced accessible name.
- [ ] **Browser zoom at 200% and 400%** — confirm no content is lost, clipped, or overlapping; confirm the heading permalink control is still visible and operable.
- [ ] **Reflow at 320 CSS pixels** — confirm no horizontal scrolling is required for the page itself (individual wide tables are expected to scroll within their own region).
- [ ] **Text spacing override** — apply the [WCAG 1.4.12 text-spacing bookmarklet/extension values](https://www.w3.org/WAI/WCAG21/Understanding/text-spacing.html) and confirm no text is clipped or overlapping.
- [ ] **Forced-colours mode** (Windows, where available) — confirm all controls and focus indicators remain visible and operable.
- [ ] **Reduced motion** — enable "reduce motion" in the OS, confirm in-page anchor navigation (contents links, heading permalinks, back-to-top) jumps instantly instead of animating, and that nothing stops functioning.
- [ ] **Print layout** — print preview a long page, confirm the contents sidebar/toolbar/back-to-top are hidden and the content itself is legible and complete.
- [ ] **Screen-reader testing** — see the combinations below.

## Suggested screen-reader / browser combinations

These are suggestions for what to test, not a record of what has been tested — see the log below for that.

- NVDA with Firefox or Chrome (Windows)
- JAWS with Chrome or Edge (Windows)
- VoiceOver with Safari (macOS)
- VoiceOver (iOS)
- TalkBack (Android)

## Test log

Add a new row for every test session. Do not overwrite previous entries — the history matters.

| Date | Tester | Environment (browser + AT + OS) | Findings | Defects filed | Retest result |
| --- | --- | --- | --- | --- | --- |
| _(none yet)_ | | | | | |

The accessibility statement (`content/accessibility-statement.html`) links back to this file. Keep the statement's "review history" table and this log in sync — the statement is the public summary, this file is the working record.
