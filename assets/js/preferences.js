// Reader preferences (text width, colour theme, extra spacing), bookmarks
// and recently-viewed pages, plus the "Saved pages" reader library. The
// reading-options panel is part of every page's Page tools, so this loads
// on every page (bundled into the main script). All state is per-browser
// localStorage; nothing leaves the device.
(function () {
  "use strict";

  var announce = (window.__site && window.__site.announce) || function () {};

  var PREFS_KEY = "accessibleDocs.readerPrefs.v1";
  var BOOKMARKS_KEY = "accessibleDocs.bookmarks.v1";
  var RECENT_KEY = "accessibleDocs.recent.v1";

  function storageRead(key, fallback) {
    try {
      var value = JSON.parse(window.localStorage.getItem(key));
      return value === null ? fallback : value;
    } catch (err) {
      return fallback;
    }
  }
  function storageWrite(key, value) {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (err) {
      announce("This browser could not save that change.");
      return false;
    }
  }
  function pageRecord() {
    var body = document.body;
    return {
      slug: body.dataset.pageSlug,
      title: body.dataset.pageTitle,
      href: body.dataset.pageSlug + ".html"
    };
  }
  function renderReaderList(selector, items, emptyText) {
    var list = document.querySelector(selector);
    if (!list) return;
    list.textContent = "";
    if (!items.length) {
      var empty = document.createElement("li");
      empty.textContent = emptyText;
      list.appendChild(empty);
      return;
    }
    items.forEach(function (item) {
      var li = document.createElement("li");
      var a = document.createElement("a");
      a.href = item.href;
      a.textContent = item.title;
      li.appendChild(a);
      list.appendChild(li);
    });
  }

  // Each preference is validated independently, so one malformed (or
  // simply older) value never discards the others — prefs saved before
  // dark mode existed have no theme property and must keep their width
  // and spacing choices.
  var defaults = { width: "wide", spacing: false, theme: "auto" };
  var stored = storageRead(PREFS_KEY, {});
  if (typeof stored !== "object" || stored === null) stored = {};
  var prefs = {
    width: ["wide", "comfortable"].includes(stored.width) ? stored.width : defaults.width,
    spacing: typeof stored.spacing === "boolean" ? stored.spacing : defaults.spacing,
    theme: ["auto", "light", "dark"].includes(stored.theme) ? stored.theme : defaults.theme
  };
  function applyPrefs() {
    document.documentElement.dataset.readingWidth = prefs.width;
    if (prefs.spacing) document.documentElement.dataset.textSpacing = "enhanced";
    else delete document.documentElement.dataset.textSpacing;
    // "auto" removes the attribute so the prefers-color-scheme media
    // query decides; the head's pre-paint script mirrors this so an
    // explicit choice applies before first paint on the next page.
    if (prefs.theme === "auto") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = prefs.theme;
    // Keep the browser-chrome colour in step with the resolved theme
    // (defined by the pre-paint script in the page head).
    if (window.__syncThemeColour) window.__syncThemeColour(prefs.theme);
    document.querySelectorAll('input[name="reading-width"]').forEach(function (input) {
      input.checked = input.value === prefs.width;
    });
    document.querySelectorAll('input[name="colour-theme"]').forEach(function (input) {
      input.checked = input.value === prefs.theme;
    });
    var spacing = document.querySelector("[data-reading-spacing]");
    if (spacing) spacing.checked = Boolean(prefs.spacing);
  }
  applyPrefs();
  document.querySelectorAll('input[name="reading-width"]').forEach(function (input) {
    input.addEventListener("change", function () {
      if (!input.checked) return;
      prefs.width = input.value;
      applyPrefs();
      storageWrite(PREFS_KEY, prefs);
    });
  });
  document.querySelectorAll('input[name="colour-theme"]').forEach(function (input) {
    input.addEventListener("change", function () {
      if (!input.checked) return;
      prefs.theme = input.value;
      applyPrefs();
      storageWrite(PREFS_KEY, prefs);
    });
  });
  var spacing = document.querySelector("[data-reading-spacing]");
  if (spacing) spacing.addEventListener("change", function () {
    prefs.spacing = spacing.checked;
    applyPrefs();
    storageWrite(PREFS_KEY, prefs);
  });
  var reset = document.querySelector("[data-reader-reset]");
  if (reset) reset.addEventListener("click", function () {
    prefs = { width: "wide", spacing: false, theme: "auto" };
    applyPrefs();
    storageWrite(PREFS_KEY, prefs);
    announce("Reading options reset.");
  });

  var record = pageRecord();
  var bookmarks = storageRead(BOOKMARKS_KEY, []);
  if (!Array.isArray(bookmarks)) bookmarks = [];
  var bookmark = document.querySelector("[data-action='bookmark']");
  function updateBookmark() {
    if (!bookmark) return;
    var saved = bookmarks.some(function (item) { return item.slug === record.slug; });
    bookmark.setAttribute("aria-pressed", String(saved));
    bookmark.querySelector(".bookmark-label").textContent = saved ? "Remove bookmark" : "Bookmark page";
  }
  if (bookmark) bookmark.addEventListener("click", function () {
    var index = bookmarks.findIndex(function (item) { return item.slug === record.slug; });
    if (index === -1) {
      bookmarks.unshift(record);
      bookmarks = bookmarks.slice(0, 50);
      announce("Page bookmarked.");
    } else {
      bookmarks.splice(index, 1);
      announce("Bookmark removed.");
    }
    storageWrite(BOOKMARKS_KEY, bookmarks);
    updateBookmark();
    renderReaderList("[data-bookmarks-list]", bookmarks, "No bookmarks yet.");
  });
  updateBookmark();
  renderReaderList("[data-bookmarks-list]", bookmarks, "No bookmarks yet.");

  var recent = storageRead(RECENT_KEY, []);
  if (!Array.isArray(recent)) recent = [];
  if (document.body.dataset.pageGroup) {
    recent = recent.filter(function (item) { return item.slug !== record.slug; });
    recent.unshift(record);
    recent = recent.slice(0, 10);
    storageWrite(RECENT_KEY, recent);
  }
  renderReaderList("[data-recent-list]", recent, "No recently viewed pages yet.");
})();
