#!/usr/bin/env node
// End-to-end checks for the theme system: automatic (OS) themes, explicit
// Light/Dark overrides, persistence, pre-paint application, theme-color
// metadata sync, native control color-scheme, forced-colours mode, and
// the forced-light print palette. Requires a Chromium install (same as
// test-a11y.mjs). Usage: node scripts/test-theme.mjs
import { chromium } from "playwright";
import { startDocsServer, trackAllPages, chromiumLaunchOptions } from "./test-helpers.mjs";

const LIGHT_BG = "rgb(255, 255, 255)";
const DARK_BG = "rgb(22, 25, 29)";
// The expected browser-chrome colours are read from the generated page's
// own metas (in auto mode they carry the build's per-scheme defaults), so
// this test cannot drift in lockstep with a broken implementation the way
// a re-hardcoded pair could.
let LIGHT_CHROME, DARK_CHROME;

const server = await startDocsServer();
const port = server.address().port;
const base = `http://127.0.0.1:${port}`;
const browser = await chromium.launch(chromiumLaunchOptions());
const runtimeProblems = trackAllPages(browser);
const fails = [];
const check = (ok, msg) => { console.log((ok ? "ok   " : "FAIL ") + msg); if (!ok) fails.push(msg); };

async function state(page) {
  return page.evaluate(() => ({
    theme: document.documentElement.dataset.theme || null,
    bg: getComputedStyle(document.body).backgroundColor,
    metaLight: document.getElementById("theme-colour-light").content,
    metaDark: document.getElementById("theme-colour-dark").content,
    inputScheme: getComputedStyle(document.querySelector(".site-search input")).colorScheme,
    stored: (() => { try { return JSON.parse(localStorage.getItem("accessibleDocs.readerPrefs.v1")); } catch (e) { return null; } })(),
  }));
}
async function openThemeControls(page) {
  await page.click(".page-tools > summary");
  await page.click(".reader-tools > summary");
}

// ---- 0. Read the build's chrome colours from a fresh page ----
{
  const ctx = await browser.newContext({ colorScheme: "light" });
  const page = await ctx.newPage();
  await page.goto(`${base}/index.html`);
  ({ LIGHT_CHROME, DARK_CHROME } = await page.evaluate(() => ({
    LIGHT_CHROME: document.getElementById("theme-colour-light").content,
    DARK_CHROME: document.getElementById("theme-colour-dark").content,
  })));
  check(/^#[0-9a-f]{6}$/i.test(LIGHT_CHROME) && /^#[0-9a-f]{6}$/i.test(DARK_CHROME) && LIGHT_CHROME !== DARK_CHROME,
    `chrome colours read from the page are two distinct hex values (${LIGHT_CHROME}, ${DARK_CHROME})`);
  await ctx.close();
}

// ---- 1. Automatic themes (no stored preference) ----
for (const [scheme, wantBg] of [["light", LIGHT_BG], ["dark", DARK_BG]]) {
  const ctx = await browser.newContext({ colorScheme: scheme });
  const page = await ctx.newPage();
  await page.goto(`${base}/clause-9-web.html`);
  const s = await state(page);
  check(s.theme === null && s.bg === wantBg, `auto follows OS ${scheme} (bg ${s.bg}, no data-theme)`);
  check(s.metaLight === LIGHT_CHROME && s.metaDark === DARK_CHROME, `auto keeps both theme-color metas at their own values (OS ${scheme})`);
  check(s.inputScheme.includes(scheme), `native controls use color-scheme ${scheme} in auto`);
  // auto responds when the emulated OS scheme changes mid-session
  const flipped = scheme === "light" ? "dark" : "light";
  await page.emulateMedia({ colorScheme: flipped });
  const bgAfter = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  check(bgAfter === (flipped === "dark" ? DARK_BG : LIGHT_BG), `auto responds to OS change ${scheme}→${flipped}`);
  await ctx.close();
}

// ---- 2. Explicit overrides beat the OS, persist, and sync theme-color ----
{
  const ctx = await browser.newContext({ colorScheme: "light" });
  const page = await ctx.newPage();
  await page.goto(`${base}/clause-9-web.html`);
  await openThemeControls(page);
  const autoChecked = await page.evaluate(() => document.querySelector("input[name='colour-theme'][value='auto']").checked);
  check(autoChecked, "Auto radio is checked by default");
  await page.check("input[name='colour-theme'][value='dark']");
  let s = await state(page);
  check(s.theme === "dark" && s.bg === DARK_BG, "explicit Dark overrides light OS");
  check(s.stored && s.stored.theme === "dark", "explicit choice written to localStorage");
  check(s.metaLight === DARK_CHROME && s.metaDark === DARK_CHROME, "theme-color metas both dark after explicit Dark");
  check(s.inputScheme.includes("dark"), "native controls follow explicit Dark");
  const menusOpen = await page.evaluate(() => document.querySelector(".page-tools").open && document.querySelector(".reader-tools").open);
  check(menusOpen, "Page tools and Reading options stay open across a theme change");
  // survives navigation, applied pre-paint (attribute present at domcontentloaded)
  await page.goto(`${base}/clause-4-functional-performance.html`, { waitUntil: "domcontentloaded" });
  const early = await page.evaluate(() => document.documentElement.dataset.theme || null);
  check(early === "dark", "explicit theme is already present by DOMContentLoaded on the next page "
    + "(synchronous head-script ordering is asserted statically in scripts/test_build.py)");
  await page.waitForLoadState("load");
  s = await state(page);
  check(s.bg === DARK_BG && s.metaLight === DARK_CHROME, "explicit Dark persists across navigation with synced theme-color");
  // survives reload
  await page.reload();
  s = await state(page);
  check(s.bg === DARK_BG, "explicit Dark survives reload");
  // radio reflects the stored choice
  await openThemeControls(page);
  const darkChecked = await page.evaluate(() => document.querySelector("input[name='colour-theme'][value='dark']").checked);
  check(darkChecked, "Dark radio reflects the stored choice after reload");
  // reset restores Auto
  await page.click("[data-reader-reset]");
  s = await state(page);
  check(s.theme === null && s.bg === LIGHT_BG, "reset restores Auto (OS light)");
  check(s.metaLight === LIGHT_CHROME && s.metaDark === DARK_CHROME, "reset restores both theme-color metas");
  await ctx.close();
}
{
  const ctx = await browser.newContext({ colorScheme: "dark" });
  const page = await ctx.newPage();
  await page.goto(`${base}/clause-9-web.html`);
  await openThemeControls(page);
  await page.check("input[name='colour-theme'][value='light']");
  const s = await state(page);
  check(s.theme === "light" && s.bg === LIGHT_BG, "explicit Light overrides dark OS");
  check(s.metaLight === LIGHT_CHROME && s.metaDark === LIGHT_CHROME, "theme-color metas both light after explicit Light");
  check(s.inputScheme.includes("light"), "native controls follow explicit Light");
  await ctx.close();
}

// ---- 3. Malformed and legacy stored preferences ----
{
  const cases = [
    ["malformed JSON", "'{oops"],
    ["non-object value", "42"],
    ["legacy prefs without theme", JSON.stringify({ width: "comfortable", spacing: true })],
    ["invalid width, valid theme", JSON.stringify({ width: "huge", spacing: false, theme: "dark" })],
    ["invalid theme, valid width", JSON.stringify({ width: "comfortable", spacing: false, theme: "sepia" })],
  ];
  for (const [label, raw] of cases) {
    const ctx = await browser.newContext({ colorScheme: "light" });
    await ctx.addInitScript((value) => localStorage.setItem("accessibleDocs.readerPrefs.v1", value), raw);
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    await page.goto(`${base}/clause-9-web.html`);
    const s = await page.evaluate(() => ({
      width: document.documentElement.dataset.readingWidth,
      theme: document.documentElement.dataset.theme || null,
      bg: getComputedStyle(document.body).backgroundColor,
    }));
    check(errors.length === 0, `${label}: no script errors`);
    if (label === "legacy prefs without theme") {
      check(s.width === "comfortable" && s.theme === null, `${label}: keeps width, defaults theme to auto`);
    } else if (label === "invalid width, valid theme") {
      check(s.width === "wide" && s.theme === "dark", `${label}: resets width, keeps theme`);
    } else if (label === "invalid theme, valid width") {
      check(s.width === "comfortable" && s.theme === null, `${label}: keeps width, resets theme`);
    } else {
      check(s.width === "wide" && s.theme === null && s.bg === LIGHT_BG, `${label}: falls back to defaults`);
    }
    await ctx.close();
  }
}

// ---- 4. Print is always ink on paper, whatever the screen theme ----
// Computed styles of the actual child elements, not just inherited
// parents: the h1 and current breadcrumb carry their own fixed white for
// the screen's blue band and previously stayed white in print.
{
  const ctx = await browser.newContext({ colorScheme: "dark" });
  const page = await ctx.newPage();
  const BLACK = "rgb(0, 0, 0)";
  await page.goto(`${base}/clause-8-hardware.html`);
  await page.emulateMedia({ media: "print", colorScheme: "dark" });
  const p8 = await page.evaluate(() => {
    const style = (sel) => {
      const el = document.querySelector(sel);
      return el ? { color: getComputedStyle(el).color, bg: getComputedStyle(el).backgroundColor } : null;
    };
    return {
      body: style("body"),
      para: style(".content p"),
      h1: style(".doc-header h1"),
      crumbCurrent: style('.breadcrumb li[aria-current="page"]'),
      crumbLink: style(".breadcrumb a"),
      th: style(".content thead th"),
    };
  });
  check(p8.body.color === BLACK && p8.body.bg === LIGHT_BG, `print body is black on white in dark mode (got ${p8.body.color} on ${p8.body.bg})`);
  check(p8.para.color === BLACK, "print paragraphs are black in dark mode");
  check(p8.h1.color === BLACK, `print page title (h1) is black (got ${p8.h1.color})`);
  check(p8.crumbCurrent.color === BLACK, `print current breadcrumb is black (got ${p8.crumbCurrent.color})`);
  check(p8.crumbLink.color === BLACK, "print breadcrumb links are black");
  check(p8.th.color === BLACK && p8.th.bg === LIGHT_BG, "print table headers are black on white");
  // callout text (clause 2 has reproduced NOTE callouts)
  await page.goto(`${base}/clause-2-references.html`);
  await page.emulateMedia({ media: "print", colorScheme: "dark" });
  const callout = await page.evaluate(() => getComputedStyle(document.querySelector(".callout p")).color);
  check(callout === BLACK, `print callout text is black (got ${callout})`);
  // companion guidance (clause 5 carries one)
  await page.goto(`${base}/clause-5-generic-requirements.html`);
  await page.emulateMedia({ media: "print", colorScheme: "dark" });
  const guidance = await page.evaluate(() => {
    const el = document.querySelector(".companion-guidance p");
    return { color: getComputedStyle(el).color, bg: getComputedStyle(document.querySelector(".companion-guidance")).backgroundColor };
  });
  check(guidance.color === BLACK && guidance.bg === LIGHT_BG, `print companion guidance is black on white (got ${guidance.color} on ${guidance.bg})`);
  await ctx.close();
}

// ---- 5. Forced colours (Windows high contrast) stays usable ----
// Mobile: the Contents disclosure must remain discoverable and operable.
{
  const ctx = await browser.newContext({ forcedColors: "active", colorScheme: "dark", viewport: { width: 375, height: 812 } });
  const page = await ctx.newPage();
  await page.goto(`${base}/clause-9-web.html`);
  const bar = page.locator(".toc-toggle");
  check(await bar.isVisible(), "forced colours mobile: Contents toggle is displayed");
  const name = await page.evaluate(() => document.querySelector(".toc-toggle").textContent.trim());
  check(name === "Contents", `forced colours mobile: toggle has an accessible name ("${name}")`);
  await bar.focus();
  const barOutline = await page.evaluate(() => getComputedStyle(document.querySelector(".toc-toggle")).outlineStyle);
  check(barOutline !== "none", "forced colours mobile: focused toggle keeps a visible outline");
  await bar.click();
  const opened = await page.evaluate(() => ({
    expanded: document.querySelector(".toc-toggle").getAttribute("aria-expanded"),
    navVisible: getComputedStyle(document.querySelector(".site-nav")).display !== "none",
  }));
  check(opened.expanded === "true" && opened.navVisible, "forced colours mobile: activating the toggle opens the contents panel");
  const firstLink = page.locator(".site-nav a").first();
  check(await firstLink.isVisible(), "forced colours mobile: contents links remain visible");
  await firstLink.focus();
  const linkFocused = await page.evaluate(() => document.activeElement.closest(".site-nav") !== null);
  check(linkFocused, "forced colours mobile: first contents link can receive focus");
  await bar.click();
  const closed = await page.evaluate(() => getComputedStyle(document.querySelector(".site-nav")).display === "none");
  check(closed, "forced colours mobile: the panel collapses again");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  check(!overflow, "forced colours mobile: no page-level horizontal overflow");
  await ctx.close();
}
// Desktop: sidebar, Page tools, Reading options and search stay usable.
{
  const ctx = await browser.newContext({ forcedColors: "active", colorScheme: "dark", viewport: { width: 1280, height: 800 } });
  const page = await ctx.newPage();
  await page.goto(`${base}/clause-5-generic-requirements.html`);
  check(await page.locator(".site-nav").isVisible(), "forced colours desktop: sidebar is visible");
  const toggleHidden = await page.evaluate(() => getComputedStyle(document.querySelector(".toc-toggle")).display === "none");
  check(toggleHidden, "forced colours desktop: mobile Contents toggle is not displayed");
  const sideLink = page.locator(".site-nav a").first();
  check(await sideLink.isVisible(), "forced colours desktop: sidebar links are visible");
  await sideLink.focus();
  check(await page.evaluate(() => document.activeElement.closest(".site-nav") !== null), "forced colours desktop: sidebar links are focusable");
  await page.click(".page-tools > summary");
  check(await page.locator(".page-tools__panel").isVisible(), "forced colours desktop: Page tools opens");
  await page.click(".reader-tools > summary");
  check(await page.locator(".reader-tools__panel").isVisible(), "forced colours desktop: Reading options opens");
  const radios = await page.locator("input[name='colour-theme']").count();
  check(radios === 3, "forced colours desktop: theme radios are present and identifiable");
  await page.check("input[name='colour-theme'][value='dark']");
  check(await page.evaluate(() => document.documentElement.dataset.theme === "dark"), "forced colours desktop: theme radios remain operable");
  check(await page.locator(".companion-guidance summary").isVisible(), "forced colours desktop: companion guidance remains visible");
  check(await page.locator(".site-search input").isVisible(), "forced colours desktop: search input remains visible");
  await page.focus(".site-search input");
  const inputOutline = await page.evaluate(() => getComputedStyle(document.querySelector(".site-search input")).outlineStyle);
  check(inputOutline !== "none", "forced colours desktop: focus indicator remains on the search input");
  const paraVisible = await page.evaluate(() => {
    const para = document.querySelector(".content p");
    return para.getClientRects().length > 0 && getComputedStyle(para).visibility === "visible";
  });
  check(paraVisible, "forced colours desktop: content remains visible");
  await ctx.close();
}

await browser.close();
server.close();
if (runtimeProblems.length) {
  console.error(`\n${runtimeProblems.length} unexpected runtime problem(s):`);
  for (const p of runtimeProblems) console.error(`  ${p}`);
  fails.push(`${runtimeProblems.length} unexpected runtime problem(s)`);
}
if (fails.length) { console.error(`\n${fails.length} THEME CHECK(S) FAILED`); process.exit(1); }
console.log("\nALL THEME CHECKS PASS");
