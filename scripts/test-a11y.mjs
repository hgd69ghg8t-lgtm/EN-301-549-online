#!/usr/bin/env node
// Runs axe-core (WCAG 2.0 A/AA, 2.1 AA, 2.2 AA rule sets) against every
// generated page in docs/. Requires a Chromium install:
//   npx playwright install --with-deps chromium
//
// Usage: node scripts/test-a11y.mjs

import { chromium } from "playwright";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { startDocsServer, trackRuntimeErrors, chromiumLaunchOptions } from "./test-helpers.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sitemap = JSON.parse(readFileSync(path.join(ROOT, "scripts", "sitemap.json"), "utf8"));
const axeSource = readFileSync(
  fileURLToPath(import.meta.resolve("axe-core/axe.min.js")),
  "utf8"
);

async function main() {
  const server = await startDocsServer();
  const port = server.address().port;
  const browser = await chromium.launch(chromiumLaunchOptions());

  let totalViolations = 0;
  const failures = [];
  const runtimeProblems = [];

  // Every page is swept twice: once per colour theme. The dark palette is
  // applied the same way the OS would (prefers-color-scheme emulation),
  // so colour-contrast rules check both sets of tokens.
  for (const colorScheme of ["light", "dark"]) {
    const context = await browser.newContext({ colorScheme });
    const page = await context.newPage();
    const problems = trackRuntimeErrors(page);
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
    runtimeProblems.push(...problems);
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
    const problems = trackRuntimeErrors(page);
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
    runtimeProblems.push(...problems);
    await context.close();
  }

  await browser.close();
  server.close();

  console.log(`\n${sitemap.length} pages checked in both automatic themes plus ${representative.length} representative pages under both explicit overrides — ${totalViolations} violation type(s) across ${failures.length} combination(s).`);
  if (runtimeProblems.length) {
    console.error(`\n${runtimeProblems.length} unexpected runtime problem(s):`);
    for (const p of runtimeProblems) console.error(`  ${p}`);
  }
  if (totalViolations > 0 || runtimeProblems.length > 0) {
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
