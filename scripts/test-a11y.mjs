#!/usr/bin/env node
// Runs axe-core (WCAG 2.0 A/AA, 2.1 AA, 2.2 AA rule sets) against every
// generated page in docs/ — every sitemap page in both automatic themes
// and representative pages under explicit overrides, plus the generated
// 404 page (which is deliberately absent from the sitemap) in both
// colour schemes. Every sweep also fails on unexpected runtime errors or
// failed same-origin requests (shared browser-test-lib). Requires a
// Chromium install:
//   npx playwright install --with-deps chromium
//
// Usage: node scripts/test-a11y.mjs

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import {
  ROOT, startServer, launchBrowser, routeSiteBaseUrl,
  trackRuntimeIssues, reportRuntimeIssues,
} from "./browser-test-lib.mjs";

const sitemap = JSON.parse(readFileSync(path.join(ROOT, "scripts", "sitemap.json"), "utf8"));
const axeSource = readFileSync(
  fileURLToPath(import.meta.resolve("axe-core/axe.min.js")),
  "utf8"
);

async function runAxe(page) {
  await page.evaluate(axeSource);
  return page.evaluate(async () => {
    // eslint-disable-next-line no-undef
    return axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] } });
  });
}

async function main() {
  const server = await startServer();
  const port = server.address().port;
  const browser = await launchBrowser();

  let totalViolations = 0;
  const failures = [];
  const issues = [];

  // Every page is swept twice: once per colour theme. The dark palette is
  // applied the same way the OS would (prefers-color-scheme emulation),
  // so colour-contrast rules check both sets of tokens.
  for (const colorScheme of ["light", "dark"]) {
    const context = await browser.newContext({ colorScheme });
    const page = await context.newPage();
    trackRuntimeIssues(page, issues, { label: colorScheme });
    for (const entry of sitemap) {
      const url = `http://127.0.0.1:${port}/${entry.slug}.html`;
      await page.goto(url, { waitUntil: "networkidle", timeout: 30000 });
      const results = await runAxe(page);
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
    trackRuntimeIssues(page, issues, { label: `${colorScheme}/${storedTheme}` });
    for (const slug of representative) {
      await page.goto(`http://127.0.0.1:${port}/${slug}.html`, { waitUntil: "networkidle", timeout: 30000 });
      const results = await runAxe(page);
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

  // The generated 404 page is deliberately absent from the sitemap
  // (it's not a destination), so the sitemap sweeps above never see it.
  // Sweep it explicitly in both colour schemes. Its links/assets are
  // absolute under the production baseUrl, so requests to that origin
  // are routed onto the same docs/ tree (routeSiteBaseUrl).
  for (const colorScheme of ["light", "dark"]) {
    const context = await browser.newContext({ colorScheme });
    await routeSiteBaseUrl(context);
    const page = await context.newPage();
    trackRuntimeIssues(page, issues, { label: `404/${colorScheme}` });
    await page.goto(`http://127.0.0.1:${port}/404.html`, { waitUntil: "networkidle", timeout: 30000 });
    const results = await runAxe(page);
    if (results.violations.length) {
      totalViolations += results.violations.length;
      failures.push({ slug: "404", colorScheme, violations: results.violations });
      console.log(`FAIL 404.html (${colorScheme}) — ${results.violations.length} violation type(s)`);
      for (const v of results.violations) {
        console.log(`  [${v.impact}] ${v.id}: ${v.help} (${v.nodes.length} node(s))`);
      }
    } else {
      console.log(`ok   404.html (${colorScheme})`);
    }
    await context.close();
  }

  await browser.close();
  server.close();

  console.log(`\n${sitemap.length} pages checked in both automatic themes plus ${representative.length} representative pages under both explicit overrides, plus the 404 page in both schemes — ${totalViolations} violation type(s) across ${failures.length} combination(s).`);
  if (totalViolations > 0) {
    process.exit(1);
  }
  reportRuntimeIssues(issues);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
