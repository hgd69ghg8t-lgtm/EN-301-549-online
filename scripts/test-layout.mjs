#!/usr/bin/env node
// Responsive layout assertions, run in a real browser against the generated
// site. Complements test-a11y.mjs (axe) with the things axe can't see:
//
//   1. No page-level horizontal overflow at any tested viewport width.
//   2. The main content column actually grows on wider screens (the old
//      layout capped it at 46rem and left the right half of a desktop
//      monitor blank).
//   3. The sidebar and the main content never overlap.
//   4. A .table-wrap only scrolls when its table's natural minimum width
//      genuinely exceeds the space available — never because CSS forced a
//      minimum width on the table or squeezed its container.
//   5. The mobile contents disclosure still works at narrow widths.
//
// Requires a Chromium install (same as test-a11y.mjs):
//   npx playwright install --with-deps chromium
//
// Usage: node scripts/test-layout.mjs

import { chromium } from "playwright";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { startDocsServer, trackAllPages, chromiumLaunchOptions } from "./test-helpers.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sitemap = JSON.parse(readFileSync(path.join(ROOT, "scripts", "sitemap.json"), "utf8"));
const ALL_PAGES = sitemap.map((entry) => `${entry.slug}.html`);

// Representative content shapes, per the layout-review brief:
// ordinary prose; the clause 5 page (note-with-table, the original bug);
// a page with many large tables; nested headings and notes; the very wide
// Annex B matrix; definition lists.
const PAGES = [
  "index.html",
  "about.html",
  "clause-3-definitions.html",
  "clause-5-generic-requirements.html",
  "clause-9-web.html",
  "clause-10-non-web-documents.html",
  "annex-b-functional-performance-relationship.html",
  "annex-za-directive-2016-2102.html",
  "search.html",
];

const WIDTHS = [320, 375, 768, 1024, 1280, 1440, 1920];

async function main() {
  const server = await startDocsServer();
  const port = server.address().port;
  const browser = await chromium.launch(chromiumLaunchOptions());
  const runtimeProblems = trackAllPages(browser);

  const failures = [];
  const contentWidths = {}; // slug -> { width: contentClientWidth }

  for (const width of WIDTHS) {
    const context = await browser.newContext({ viewport: { width, height: 900 }, reducedMotion: "reduce" });
    const page = await context.newPage();

    // Every page gets the most constrained 320px pass. Wider viewports use
    // representative content shapes to keep CI time proportionate.
    const pagesAtWidth = width === 320 ? ALL_PAGES : PAGES;
    for (const slug of pagesAtWidth) {
      await page.goto(`http://127.0.0.1:${port}/${slug}`);
      await page.evaluate(() => document.fonts.ready);

      const r = await page.evaluate(() => {
        const doc = document.documentElement;
        const main = document.querySelector("main");
        const nav = document.querySelector(".site-nav");
        const mainBox = main.getBoundingClientRect();
        const navBox = nav ? nav.getBoundingClientRect() : null;

        // A wrapper may only scroll if the table inside genuinely cannot
        // shrink to fit: its min-content width (measured directly) must
        // exceed the wrapper's inner width. Anything else is CSS forcing
        // an avoidable scrollbar.
        const badWraps = [];
        let scrollingWraps = 0;
        document.querySelectorAll(".table-wrap").forEach((wrap) => {
          const overflows = wrap.scrollWidth > wrap.clientWidth + 1;
          if (!overflows) return;
          scrollingWraps += 1;
          const table = wrap.querySelector("table");
          const probe = table.cloneNode(true);
          probe.style.cssText = "width:min-content;max-width:none;position:absolute;visibility:hidden;left:-9999px";
          document.body.appendChild(probe);
          const minContent = probe.getBoundingClientRect().width;
          probe.remove();
          if (minContent <= wrap.clientWidth + 1) {
            const caption = table.querySelector("caption");
            badWraps.push(`${caption ? caption.textContent.trim().slice(0, 50) : "(no caption)"} (min-content ${Math.round(minContent)}px fits in ${wrap.clientWidth}px but still scrolls)`);
          }
        });

        return {
          pageOverflow: doc.scrollWidth > doc.clientWidth + 1,
          docScrollWidth: doc.scrollWidth,
          docClientWidth: doc.clientWidth,
          contentWidth: main.clientWidth,
          overlap: navBox && navBox.width > 0 && mainBox.width > 0 &&
                   navBox.right > mainBox.left + 1 && navBox.top < mainBox.bottom && navBox.bottom > mainBox.top &&
                   getComputedStyle(document.querySelector(".page-shell")).gridTemplateColumns.split(" ").length > 1,
          badWraps,
          scrollingWraps,
        };
      });

      if (r.pageOverflow) {
        failures.push(`${slug} @ ${width}px: page-level horizontal overflow (${r.docScrollWidth}px > ${r.docClientWidth}px)`);
      }
      if (r.overlap) {
        failures.push(`${slug} @ ${width}px: sidebar overlaps main content`);
      }
      for (const bad of r.badWraps) {
        failures.push(`${slug} @ ${width}px: avoidable table scrollbar — ${bad}`);
      }
      (contentWidths[slug] ||= {})[width] = r.contentWidth;
    }

    // Mobile contents disclosure still works.
    if (width === 375) {
      await page.goto(`http://127.0.0.1:${port}/clause-9-web.html`);
      const toggleVisible = await page.locator(".toc-toggle").isVisible();
      const navHidden = !(await page.locator(".site-nav").isVisible());
      if (!toggleVisible || !navHidden) {
        failures.push(`clause-9-web @ 375px: contents toggle/panel initial state wrong (toggle visible=${toggleVisible}, panel hidden=${navHidden})`);
      } else {
        await page.locator(".toc-toggle").click();
        if (!(await page.locator(".site-nav").isVisible())) {
          failures.push("clause-9-web @ 375px: contents panel did not open on toggle");
        }
      }
    }

    await context.close();
  }

  // Browser zoom reduces the effective CSS viewport. These cases model a
  // 1280px desktop viewport at 200% and 400%, the WCAG reflow boundary.
  for (const { label, width } of [
    { label: "200% zoom", width: 640 },
    { label: "400% zoom", width: 320 },
  ]) {
    const context = await browser.newContext({ viewport: { width, height: 900 } });
    const page = await context.newPage();
    for (const slug of ALL_PAGES) {
      await page.goto(`http://127.0.0.1:${port}/${slug}`);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
      );
      if (overflow) failures.push(`${slug} @ ${label}: page-level horizontal overflow`);
    }
    await context.close();
  }

  // Forced-colours must retain visible, operable navigation and controls.
  {
    const context = await browser.newContext({
      viewport: { width: 1280, height: 900 },
      forcedColors: "active",
    });
    const page = await context.newPage();
    for (const slug of ALL_PAGES) {
      await page.goto(`http://127.0.0.1:${port}/${slug}`);
      const result = await page.evaluate(() => ({
        overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
        mainVisible: Boolean(document.querySelector("main")?.getClientRects().length),
        linksVisible: Array.from(document.querySelectorAll("a")).some(
          (link) => link.getClientRects().length && getComputedStyle(link).visibility === "visible"
        ),
      }));
      if (result.overflow) failures.push(`${slug} @ forced colours: page-level horizontal overflow`);
      if (!result.mainVisible || !result.linksVisible) {
        failures.push(`${slug} @ forced colours: main content or links are not visible`);
      }
    }
    await context.close();
  }

  // Global link hover styles must not make a menu item's label illegible
  // against its hover background (regression: Download PDF label
  // disappeared when a hover colour matched the hover background). The
  // link now lives inside the Page tools menu, so open that first.
  {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    await page.goto(`http://127.0.0.1:${port}/clause-1-scope.html`);
    await page.locator(".page-tools > summary").click();
    const download = page.getByRole("link", { name: "Download the official ETSI standard as a PDF" });
    await download.hover();
    const visible = await download.evaluate((element) => {
      const style = getComputedStyle(element);
      return element.getClientRects().length > 0 &&
        style.visibility === "visible" &&
        style.color === "rgb(26, 26, 26)" &&
        style.backgroundColor === "rgb(243, 242, 241)" &&
        element.textContent.trim() === "Download PDF";
    });
    if (!visible) failures.push("Download PDF label is not visible on hover inside the Page tools menu");
    await context.close();
  }

  // Contents links need a clear hover state, including the current page and
  // current subsection whose aria-current styles otherwise win the cascade.
  {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    await page.goto(`http://127.0.0.1:${port}/clause-1-scope.html`);
    const contentsLink = page.locator(".site-nav a").first();
    await contentsLink.hover();
    const hoverStyle = await contentsLink.evaluate((element) => {
      const style = getComputedStyle(element);
      return { color: style.color, background: style.backgroundColor };
    });
    if (hoverStyle.color !== "rgb(255, 255, 255)" ||
        hoverStyle.background !== "rgb(0, 61, 110)") {
      failures.push("left contents link has no clear high-contrast hover state");
    }
    await context.close();
  }

  // The responsive-table helper may remove only attributes it added itself.
  {
    const context = await browser.newContext({ viewport: { width: 320, height: 900 } });
    const page = await context.newPage();
    await page.goto(`http://127.0.0.1:${port}/clause-9-web.html`);
    const preserved = await page.evaluate(async () => {
      const wrap = document.querySelector(".table-wrap");
      if (!wrap) return null;
      wrap.setAttribute("tabindex", "-1");
      wrap.setAttribute("role", "group");
      wrap.setAttribute("aria-label", "Authored table label");
      wrap.style.overflow = "visible";
      wrap.style.width = "100000px";
      window.dispatchEvent(new Event("resize"));
      await new Promise((resolve) => requestAnimationFrame(resolve));
      return {
        tabindex: wrap.getAttribute("tabindex"),
        role: wrap.getAttribute("role"),
        label: wrap.getAttribute("aria-label"),
      };
    });
    if (!preserved || preserved.tabindex !== "-1" ||
        preserved.role !== "group" || preserved.label !== "Authored table label") {
      failures.push("responsive table helper removed author-provided accessibility attributes");
    }
    await context.close();
  }

  // Companion guidance uses the browser's native disclosure semantics and
  // remains operable from the keyboard without JavaScript.
  {
    const context = await browser.newContext({
      viewport: { width: 1280, height: 900 },
      forcedColors: "active",
    });
    const page = await context.newPage();
    await page.goto(`http://127.0.0.1:${port}/clause-1-scope.html`);
    const details = page.locator(".companion-guidance details");
    const summary = details.locator("summary");
    const disclaimer = page.locator(".companion-guidance__disclaimer");
    if (await details.getAttribute("open") !== null || await disclaimer.isVisible()) {
      failures.push("companion guidance is not initially collapsed");
    }
    await summary.focus();
    await page.keyboard.press("Enter");
    if (await details.getAttribute("open") === null || !(await disclaimer.isVisible())) {
      failures.push("companion guidance did not open with Enter");
    }
    if (!(await summary.evaluate((element) => element === document.activeElement))) {
      failures.push("companion guidance summary lost keyboard focus after opening");
    }
    await page.keyboard.press("Space");
    if (await details.getAttribute("open") !== null || await disclaimer.isVisible()) {
      failures.push("companion guidance did not close with Space");
    }
    const semantics = await summary.evaluate((element) => ({
      details: element.parentElement?.tagName,
      label: element.textContent.trim(),
      visible: Boolean(element.getClientRects().length),
      labelCase: getComputedStyle(element.querySelector(".companion-guidance__label")).textTransform,
      display: getComputedStyle(element).display,
      titleWidth: element.querySelector(".companion-guidance__title").getBoundingClientRect().width,
    }));
    if (semantics.details !== "DETAILS" || !semantics.visible || semantics.labelCase !== "none" ||
        semantics.display !== "block" || semantics.titleWidth < 120 ||
        !semantics.label.includes("Website-authored guidance") ||
        !semantics.label.includes("Companion guidance")) {
      failures.push("companion guidance disclosure semantics or visible label are incomplete");
    }
    await context.close();
  }

  // The content column must grow meaningfully with the viewport — this is
  // the regression test for the old 46rem cap that wasted wide screens.
  for (const slug of PAGES) {
    const w = contentWidths[slug];
    if (!(w[1280] > w[1024] && w[1440] > w[1280] && w[1920] > w[1440])) {
      failures.push(`${slug}: main content column does not grow with the viewport (1024→${w[1024]}px, 1280→${w[1280]}px, 1440→${w[1440]}px, 1920→${w[1920]}px)`);
    }
    if (w[1920] < 1000) {
      failures.push(`${slug}: main content column only ${w[1920]}px wide at 1920px viewport — wide screens are still mostly blank`);
    }
  }

  await browser.close();
  server.close();

  if (runtimeProblems.length) {
    console.error(`\n${runtimeProblems.length} unexpected runtime problem(s):`);
    for (const p of runtimeProblems) console.error(`  ${p}`);
    failures.push(`${runtimeProblems.length} unexpected runtime problem(s)`);
  }
  if (failures.length) {
    console.error(`\n${failures.length} layout failure(s):\n`);
    for (const f of failures) console.error(`  FAIL ${f}`);
    process.exit(1);
  }
  console.log(`Layout OK: ${PAGES.length} pages × ${WIDTHS.length} widths — no page overflow, no sidebar overlap, no avoidable table scrollbars, content column grows with the viewport.`);
}

main().catch((err) => { console.error(err); process.exit(1); });
