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
import { createServer } from "node:http";
import { readFile } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DOCS_DIR = path.join(ROOT, "docs");

const MIME = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".woff2": "font/woff2", ".pdf": "application/pdf" };

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

function startServer() {
  return new Promise((resolve) => {
    const server = createServer((req, res) => {
      const urlPath = decodeURIComponent(req.url.split("?")[0]);
      const filePath = path.join(DOCS_DIR, urlPath === "/" ? "/index.html" : urlPath);
      readFile(filePath, (err, data) => {
        if (err) { res.writeHead(404); res.end("Not found"); return; }
        res.writeHead(200, { "Content-Type": MIME[path.extname(filePath)] || "application/octet-stream" });
        res.end(data);
      });
    });
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

async function main() {
  const server = await startServer();
  const port = server.address().port;
  const launchOptions = process.env.PLAYWRIGHT_CHROMIUM_PATH
    ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH }
    : {};
  const browser = await chromium.launch(launchOptions);

  const failures = [];
  const contentWidths = {}; // slug -> { width: contentClientWidth }

  for (const width of WIDTHS) {
    const context = await browser.newContext({ viewport: { width, height: 900 }, reducedMotion: "reduce" });
    const page = await context.newPage();

    for (const slug of PAGES) {
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

  if (failures.length) {
    console.error(`\n${failures.length} layout failure(s):\n`);
    for (const f of failures) console.error(`  FAIL ${f}`);
    process.exit(1);
  }
  console.log(`Layout OK: ${PAGES.length} pages × ${WIDTHS.length} widths — no page overflow, no sidebar overlap, no avoidable table scrollbars, content column grows with the viewport.`);
}

main().catch((err) => { console.error(err); process.exit(1); });
