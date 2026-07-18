#!/usr/bin/env node
// End-to-end checks for the static site search: header form navigation,
// clause-number ranking, glossary-term hits, result navigation, the
// no-results message, and the no-JavaScript fallback. Requires a Chromium
// install (same as test-a11y.mjs). Usage: node scripts/test-search.mjs
import {
  startServer, launchBrowser, trackRuntimeIssues, reportRuntimeIssues,
} from "./browser-test-lib.mjs";

const server = await startServer();
const port = server.address().port;
const browser = await launchBrowser();
const fails = [];
const issues = [];

// 1. Header form navigates to search page with query, results render
let context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
let page = await context.newPage();
trackRuntimeIssues(page, issues, { label: "search-main" });
await page.goto(`http://127.0.0.1:${port}/clause-5-generic-requirements.html`);
await page.locator(".site-search input").fill("target size");
await page.locator(".site-search button").click();
await page.waitForURL(/search\.html\?q=target\+size/);
await page.waitForFunction(() => document.querySelectorAll("#search-results li").length > 0, null, { timeout: 5000 });
const count1 = await page.locator("#search-count").textContent();
const first1 = await page.locator("#search-results li a").first().textContent();
console.log("header->search 'target size':", count1, "| first:", first1);
if (!/results for/.test(count1)) fails.push("no results for 'target size'");

// 2. Clause number query ranks the exact heading first
await page.locator("#search-input").fill("9.1.4.4");
await page.waitForTimeout(400);
const first2 = await page.locator("#search-results li a").first().textContent();
console.log("'9.1.4.4' first result:", first2);
if (!first2.startsWith("9.1.4.4")) fails.push("clause-number query didn't rank 9.1.4.4 first");

// 3. Glossary term query
await page.locator("#search-input").fill("audio description");
await page.waitForTimeout(400);
const links3 = await page.locator("#search-results li a").allTextContents();
console.log("'audio description' top results:", links3.slice(0, 3));
if (!links3.some((t) => t.trim() === "audio description")) fails.push("glossary term not found");

// 4. First result navigates correctly
await page.locator("#search-input").fill("9.1.4.4");
await page.waitForTimeout(400);
await page.locator("#search-results li a").first().click();
await page.waitForURL(/clause-9-web\.html#9-1-4-4/);
console.log("result click navigated to:", page.url().split("/").pop());

// 5. No-results state
await page.goto(`http://127.0.0.1:${port}/search.html?q=zzzzqqq`);
await page.waitForFunction(() => /No results/.test(document.getElementById("search-count").textContent), null, { timeout: 5000 });
console.log("no-results message OK");
await context.close();

// 6. No-JS: fallback text visible, results machinery quiet
context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 1440, height: 900 } });
page = await context.newPage();
trackRuntimeIssues(page, issues, { label: "no-js" });
await page.goto(`http://127.0.0.1:${port}/search.html`);
const nojsVisible = await page.locator(".search-nojs").isVisible();
console.log("no-JS fallback visible:", nojsVisible);
if (!nojsVisible) fails.push("no-JS fallback not visible");
await context.close();

// 7. Header suggestions: combobox appears, exact clause ranked first,
//    arrow+Enter navigates with the ?h= highlight handshake
context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
page = await context.newPage();
trackRuntimeIssues(page, issues, { label: "header-suggest" });
await page.goto(`http://127.0.0.1:${port}/clause-4-functional-performance.html`);
await page.locator(".site-search input").click();
await page.keyboard.type("reflow");
await page.waitForSelector(".search-suggest li", { timeout: 5000 });
const suggest = await page.evaluate(() => ({
  expanded: document.querySelector(".site-search input").getAttribute("aria-expanded"),
  role: document.querySelector(".site-search input").getAttribute("role"),
  first: document.querySelector(".search-suggest li .search-suggest__title").textContent,
}));
console.log("header suggestions:", JSON.stringify(suggest));
if (suggest.expanded !== "true" || suggest.role !== "combobox") fails.push("suggestions combobox attributes wrong");
if (!suggest.first.includes("Reflow")) fails.push("'reflow' didn't suggest a Reflow heading first");
await page.keyboard.press("ArrowDown");
await page.keyboard.press("Enter");
await page.waitForURL(/clause-9-web\.html/);
await page.waitForFunction(() => document.querySelectorAll("mark.search-highlight").length > 0, null, { timeout: 5000 });
const highlight = await page.evaluate(() => ({
  marks: document.querySelectorAll("mark.search-highlight").length,
  hParamGone: !new URLSearchParams(window.location.search).has("h"),
}));
console.log("arrival highlight:", JSON.stringify(highlight));
if (!highlight.hParamGone) fails.push("?h= param not cleaned from the URL after highlighting");

// 8. Escape closes suggestions but keeps the typed query
await page.goto(`http://127.0.0.1:${port}/clause-9-web.html`);
await page.locator(".site-search input").click();
await page.keyboard.type("keyboard");
await page.waitForSelector(".search-suggest li", { timeout: 5000 });
await page.keyboard.press("Escape");
const afterEsc = await page.evaluate(() => ({
  hidden: document.getElementById("search-suggestions").hidden,
  value: document.querySelector(".site-search input").value,
}));
console.log("after Escape:", JSON.stringify(afterEsc));
if (!afterEsc.hidden || afterEsc.value !== "keyboard") fails.push("Escape should close suggestions and keep the query");
await context.close();

await browser.close();
server.close();
if (fails.length) { console.error("FAILURES:", fails); process.exit(1); }
reportRuntimeIssues(issues);
console.log("ALL SEARCH CHECKS PASS");
