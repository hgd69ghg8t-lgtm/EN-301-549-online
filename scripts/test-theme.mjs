#!/usr/bin/env node
// End-to-end checks for the theme system: automatic (OS) themes, explicit
// Light/Dark overrides, persistence, pre-paint application, theme-color
// metadata sync, native control color-scheme, forced-colours mode, and
// the forced-light print palette. Requires a Chromium install (same as
// test-a11y.mjs). Usage: node scripts/test-theme.mjs
import { chromium } from "playwright";
import { createServer } from "node:http";
import { readFile } from "node:fs";
import path from "node:path";

const DOCS_DIR = path.resolve("docs");
const MIME = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2" };
const LIGHT_BG = "rgb(255, 255, 255)";
const DARK_BG = "rgb(22, 25, 29)";
const LIGHT_CHROME = "#14245a";
const DARK_CHROME = "#16191d";

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

const server = await startServer();
const port = server.address().port;
const base = `http://127.0.0.1:${port}`;
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH });
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
  check(early === "dark", "explicit theme present at domcontentloaded on the next page (pre-paint)");
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
{
  const ctx = await browser.newContext({ colorScheme: "dark" });
  const page = await ctx.newPage();
  await page.goto(`${base}/clause-8-hardware.html`);
  await page.emulateMedia({ media: "print", colorScheme: "dark" });
  const p = await page.evaluate(() => {
    const th = document.querySelector(".content thead th");
    const para = document.querySelector(".content p");
    return {
      bodyColor: getComputedStyle(document.body).color,
      bodyBg: getComputedStyle(document.body).backgroundColor,
      paraColor: getComputedStyle(para).color,
      thColor: getComputedStyle(th).color,
      thBg: getComputedStyle(th).backgroundColor,
    };
  });
  check(p.bodyColor === "rgb(0, 0, 0)" && p.bodyBg === LIGHT_BG, `print body is black on white in dark mode (got ${p.bodyColor} on ${p.bodyBg})`);
  check(p.paraColor === "rgb(0, 0, 0)", "print paragraphs are black in dark mode");
  check(p.thColor === "rgb(0, 0, 0)" && p.thBg === LIGHT_BG, "print table headers are black on white");
  await ctx.close();
}

// ---- 5. Forced colours (Windows high contrast) stays usable ----
{
  const ctx = await browser.newContext({ forcedColors: "active", colorScheme: "dark" });
  const page = await ctx.newPage();
  await page.goto(`${base}/clause-9-web.html`);
  const f = await page.evaluate(() => {
    const para = document.querySelector(".content p");
    const bar = document.querySelector(".toc-toggle");
    return {
      paraVisible: para.getClientRects().length > 0 && getComputedStyle(para).visibility === "visible",
      barVisible: bar ? getComputedStyle(bar).display !== "none" || true : true,
      guidanceVisible: Boolean(document.querySelector(".companion-guidance summary")?.getClientRects().length),
    };
  });
  check(f.paraVisible, "forced colours: content remains visible");
  check(f.guidanceVisible, "forced colours: companion guidance remains identifiable");
  await page.focus(".site-search input");
  const outline = await page.evaluate(() => getComputedStyle(document.querySelector(".site-search input")).outlineStyle);
  check(outline !== "none", "forced colours: focus indicator remains");
  await openThemeControls(page);
  await page.check("input[name='colour-theme'][value='dark']");
  const themed = await page.evaluate(() => document.documentElement.dataset.theme);
  check(themed === "dark", "forced colours: theme radios remain operable");
  await ctx.close();
}

await browser.close();
server.close();
if (fails.length) { console.error(`\n${fails.length} THEME CHECK(S) FAILED`); process.exit(1); }
console.log("\nALL THEME CHECKS PASS");
