#!/usr/bin/env node
// Optional-module failure testing: every lazily-loaded bundle and every
// search resource is deliberately broken in turn, and the page must stay
// readable, navigable and error-free (the baseline experience never
// depends on an optional module arriving). The success paths are covered
// by the other suites; this one covers the failures. Usage:
//   node scripts/test-modules.mjs
import { chromium } from "playwright";
import { startDocsServer, trackRuntimeErrors, chromiumLaunchOptions } from "./test-helpers.mjs";

const server = await startDocsServer();
const port = server.address().port;
const base = `http://127.0.0.1:${port}`;
const browser = await chromium.launch(chromiumLaunchOptions());
const fails = [];
const check = (ok, msg) => { console.log((ok ? "ok   " : "FAIL ") + msg); if (!ok) fails.push(msg); };

async function withPage({ block = [], allowUrls = [] }, fn) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const problems = trackRuntimeErrors(page, { allowUrls: [...block, ...allowUrls] });
  for (const pattern of block) {
    await page.route((url) => url.href.includes(pattern), (route) => route.abort());
  }
  await fn(page);
  await context.close();
  return problems;
}

// 1. search.js blocked: header search stays a working plain GET form.
{
  const problems = await withPage({ block: ["assets/js/search."] }, async (page) => {
    await page.goto(`${base}/clause-9-web.html`);
    await page.locator(".site-search input").fill("target size");
    await page.waitForTimeout(400); // give the (blocked) module load a beat
    check(await page.locator(".content h1, h1").first().isVisible(), "search.js blocked: page content still renders");
    check((await page.locator(".search-suggest li").count()) === 0, "search.js blocked: no half-rendered suggestions");
    await page.locator(".site-search button").click();
    await page.waitForURL(/search\.html\?q=target\+size/);
    check(true, "search.js blocked: plain GET form still reaches search.html");
  });
  check(problems.length === 0, `search.js blocked: no unexpected runtime errors (${problems.join("; ")})`);
}

// 2. tables.js blocked: tables remain plain, readable tables.
{
  const problems = await withPage({ block: ["assets/js/tables."] }, async (page) => {
    await page.goto(`${base}/clause-9-web.html`);
    check(await page.locator(".table-wrap table").first().isVisible(), "tables.js blocked: tables still visible");
    check(await page.locator("#main-content").isVisible(), "tables.js blocked: page readable");
  });
  check(problems.length === 0, `tables.js blocked: no unexpected runtime errors (${problems.join("; ")})`);
}

// 3. reader-library.js blocked: Reading options still fully usable —
//    preferences apply, focus is not stranded, lists keep placeholders.
{
  const problems = await withPage({ block: ["assets/js/reader-library."] }, async (page) => {
    await page.goto(`${base}/clause-9-web.html`);
    await page.locator(".page-tools > summary").click();
    await page.locator(".reader-tools summary").click();
    await page.waitForTimeout(300);
    check(await page.locator("[data-bookmarks-list]").isVisible(), "reader-library blocked: panel opens");
    const placeholder = await page.locator("[data-bookmarks-list] li").first().textContent();
    check(placeholder.includes("No bookmarks yet"), "reader-library blocked: list keeps its static placeholder");
    await page.locator('input[name="reading-width"][value="comfortable"]').check();
    const width = await page.evaluate(() => document.documentElement.dataset.readingWidth);
    check(width === "comfortable", "reader-library blocked: preferences still apply");
    const focusVisible = await page.evaluate(() => document.activeElement !== document.body);
    check(focusVisible, "reader-library blocked: focus not stranded");
  });
  check(problems.length === 0, `reader-library blocked: no unexpected runtime errors (${problems.join("; ")})`);
}

// 4. search-worker.js blocked on the search page: the synchronous
//    main-thread fallback still returns full results.
{
  const problems = await withPage({ block: ["assets/js/search-worker."] }, async (page) => {
    await page.goto(`${base}/search.html?q=target+size`);
    await page.waitForFunction(() => document.querySelectorAll("#search-results li").length > 0, null, { timeout: 10000 });
    const first = await page.locator("#search-results li a").first().textContent();
    check(first.includes("Target size"), `worker blocked: fallback search still ranks correctly (got "${first}")`);
  });
  check(problems.length === 0, `worker blocked: no unexpected runtime errors (${problems.join("; ")})`);
}

// 5. Full search index blocked: an understandable failure message, and
//    the page itself stays intact.
{
  const problems = await withPage({ block: ["search-index."] }, async (page) => {
    await page.goto(`${base}/search.html?q=keyboard`);
    await page.waitForFunction(() => /couldn.t load its index/i.test(document.getElementById("search-count").textContent), null, { timeout: 10000 });
    check(true, "index blocked: understandable failure message shown");
    check(await page.locator("#search-input").isVisible(), "index blocked: search page still renders");
  });
  check(problems.length === 0, `index blocked: no unexpected runtime errors (${problems.join("; ")})`);
}

// 6. Malformed index JSON: same clear failure message, no crash.
{
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const problems = trackRuntimeErrors(page, { allowUrls: ["search-index."] });
  await page.route((url) => url.pathname.match(/search-index\./), (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "{not json!" }));
  await page.goto(`${base}/search.html?q=keyboard`);
  await page.waitForFunction(() => /couldn.t load its index/i.test(document.getElementById("search-count").textContent), null, { timeout: 10000 });
  check(true, "malformed index JSON: understandable failure message shown");
  check(problems.length === 0, `malformed index JSON: no unexpected runtime errors (${problems.join("; ")})`);
  await context.close();
}

// 7. Suggestions index blocked: typing in the header shows no broken
//    UI and the form still submits.
{
  const problems = await withPage({ block: ["search-suggestions."] }, async (page) => {
    await page.goto(`${base}/clause-4-functional-performance.html`);
    await page.locator(".site-search input").click();
    await page.keyboard.type("reflow");
    await page.waitForTimeout(600);
    check((await page.locator(".search-suggest li").count()) === 0, "suggestions blocked: no broken suggestion list");
    await page.keyboard.press("Enter");
    await page.waitForURL(/search\.html\?q=reflow/);
    check(true, "suggestions blocked: form submit still works");
  });
  check(problems.length === 0, `suggestions blocked: no unexpected runtime errors (${problems.join("; ")})`);
}

// 8. The worker ignores malformed messages and still answers real ones.
{
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const problems = trackRuntimeErrors(page);
  await page.goto(`${base}/search.html`);
  const result = await page.evaluate(async () => {
    const ds = document.body.dataset;
    const w = new Worker(ds.searchWorker);
    const replies = [];
    w.onmessage = (e) => replies.push(e.data);
    w.postMessage("garbage");
    w.postMessage({ type: "query" }); // missing q — must be ignored
    w.postMessage(null);
    w.postMessage({ type: "init", url: new URL(ds.searchIndex, location.href).href });
    w.postMessage({ type: "query", id: 1, q: "keyboard", limit: 5 });
    await new Promise((resolve) => {
      const t0 = Date.now();
      (function poll() {
        if (replies.some((r) => r && r.type === "results") || Date.now() - t0 > 10000) resolve();
        else setTimeout(poll, 50);
      })();
    });
    const results = replies.find((r) => r && r.type === "results");
    return { replyTypes: replies.map((r) => r && r.type), got: Boolean(results), count: results ? results.results.length : 0 };
  });
  check(result.got && result.count > 0, `worker: malformed messages ignored, real query answered (${JSON.stringify(result.replyTypes)})`);
  check(problems.length === 0, `worker malformed messages: no unexpected runtime errors (${problems.join("; ")})`);
  await context.close();
}

await browser.close();
server.close();
if (fails.length) { console.error("FAILURES:", fails); process.exit(1); }
console.log("ALL MODULE-FAILURE CHECKS PASS");
