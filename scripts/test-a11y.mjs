#!/usr/bin/env node
// Runs axe-core (WCAG 2.0 A/AA, 2.1 AA, 2.2 AA rule sets) against every
// generated page in docs/. Requires a Chromium install:
//   npx playwright install --with-deps chromium
//
// Usage: node scripts/test-a11y.mjs

import { chromium } from "playwright";
import { createServer } from "node:http";
import { readFile, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DOCS_DIR = path.join(ROOT, "docs");
const sitemap = JSON.parse(readFileSync(path.join(ROOT, "scripts", "sitemap.json"), "utf8"));
const axeSource = readFileSync(
  fileURLToPath(import.meta.resolve("axe-core/axe.min.js")),
  "utf8"
);

const MIME = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".woff2": "font/woff2", ".pdf": "application/pdf" };

function startServer() {
  return new Promise((resolve) => {
    const server = createServer((req, res) => {
      const urlPath = decodeURIComponent(req.url.split("?")[0]);
      const filePath = path.join(DOCS_DIR, urlPath === "/" ? "/index.html" : urlPath);
      readFile(filePath, (err, data) => {
        if (err) {
          res.writeHead(404);
          res.end("Not found");
          return;
        }
        const ext = path.extname(filePath);
        res.writeHead(200, { "Content-Type": MIME[ext] || "application/octet-stream" });
        res.end(data);
      });
    });
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

async function main() {
  const server = await startServer();
  const port = server.address().port;
  // PLAYWRIGHT_CHROMIUM_PATH lets a local/CI environment point at an
  // already-installed Chromium binary instead of the one Playwright's own
  // browser manager would download. Unset by default — normal usage is
  // `npx playwright install --with-deps chromium` and a plain launch().
  const launchOptions = process.env.PLAYWRIGHT_CHROMIUM_PATH
    ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH }
    : {};
  const browser = await chromium.launch(launchOptions);

  let totalViolations = 0;
  const failures = [];

  // Every page is swept twice: once per colour theme. The dark palette is
  // applied the same way the OS would (prefers-color-scheme emulation),
  // so colour-contrast rules check both sets of tokens.
  for (const colorScheme of ["light", "dark"]) {
    const context = await browser.newContext({ colorScheme });
    const page = await context.newPage();
    for (const entry of sitemap) {
      const url = `http://127.0.0.1:${port}/${entry.slug}.html`;
      await page.goto(url, { waitUntil: "networkidle", timeout: 30000 });
      await page.evaluate(axeSource);
      const results = await page.evaluate(async () => {
        // eslint-disable-next-line no-undef
        return axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] } });
      });
      if (results.violations.length) {
        totalViolations += results.violations.length;
        failures.push({ slug: entry.slug, colorScheme, violations: results.violations });
        console.log(`FAIL ${entry.slug}.html (${colorScheme}) — ${results.violations.length} violation type(s)`);
        for (const v of results.violations) {
          console.log(`  [${v.impact}] ${v.id}: ${v.help} (${v.nodes.length} node(s))`);
        }
      } else {
        console.log(`ok   ${entry.slug}.html (${colorScheme})`);
      }
    }
    await context.close();
  }

  // Explicit theme overrides: the stored preference beats the OS setting,
  // so the token set under test differs from plain emulation. Full
  // four-way sweeps of every page would double CI again for the same
  // tokens, so overrides run against representative pages: homepage,
  // About (companion to none, but statement + front matter), a long
  // clause, an ordinary-tables clause, Annex B's wide matrix, a
  // companion-guidance page, and search.
  const representative = ["index", "about", "clause-9-web", "clause-8-hardware",
    "annex-b-functional-performance-relationship", "clause-5-generic-requirements", "search"];
  for (const [colorScheme, storedTheme] of [["light", "dark"], ["dark", "light"]]) {
    const context = await browser.newContext({ colorScheme });
    await context.addInitScript((theme) => {
      localStorage.setItem("accessibleDocs.readerPrefs.v1",
        JSON.stringify({ width: "wide", spacing: false, theme }));
    }, storedTheme);
    const page = await context.newPage();
    for (const slug of representative) {
      await page.goto(`http://127.0.0.1:${port}/${slug}.html`, { waitUntil: "networkidle", timeout: 30000 });
      await page.evaluate(axeSource);
      const results = await page.evaluate(async () => {
        // eslint-disable-next-line no-undef
        return axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] } });
      });
      const label = `${slug} (OS ${colorScheme}, explicit ${storedTheme})`;
      if (results.violations.length) {
        totalViolations += results.violations.length;
        failures.push({ slug, colorScheme, storedTheme, violations: results.violations });
        console.log(`FAIL ${label} — ${results.violations.length} violation type(s)`);
        for (const v of results.violations) {
          console.log(`  [${v.impact}] ${v.id}: ${v.help} (${v.nodes.length} node(s))`);
        }
      } else {
        console.log(`ok   ${label}`);
      }
    }
    await context.close();
  }

  await browser.close();
  server.close();

  console.log(`\n${sitemap.length} pages checked in both automatic themes plus ${representative.length} representative pages under both explicit overrides — ${totalViolations} violation type(s) across ${failures.length} combination(s).`);
  if (totalViolations > 0) {
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
