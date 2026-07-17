/*
  core.js — the one script loaded on every page (deferred, from <head>).

  Contains only behaviour used on almost every page: the mobile Contents
  and search disclosures, Page-tools Escape handling, print, copy-link,
  heading-permalink copying, reading preferences, bookmark/recent
  recording, glossary fragment focus, Back-to-top visibility, and
  intent-based same-origin prefetching.

  Everything heavier is a separate bundle, loaded only when it can
  actually be used:
    search.js         — injected when the header search field first
                        receives focus or two characters (the plain GET
                        form works before/without it); loaded eagerly by
                        the build only on search.html.
    tables.js         — emitted by the build only on pages that contain
                        a .table-wrap.
    reader-library.js — injected the first time Reading options opens.

  Every dynamic load fails safely: the page's baseline behaviour (native
  form submit, native details/summary, plain anchors) never depends on a
  module arriving. The hashed module/index URLs are injected by the build
  as data attributes on <body> — nothing here hardcodes an asset hash.

  This is readable source (scripts/source/); the build minifies it into
  the content-hashed production file under docs/assets/js/.
*/
(function () {
  "use strict";

  // Marks JS as available so CSS can gate JS-only behaviour (the collapsed-
  // by-default mobile contents panel and its toggle button) behind it.
  document.documentElement.classList.add("js");

  var ds = document.body.dataset;

  // ---------- Shared: polite status announcements ----------
  // One live region per page (in the template). Clearing then re-setting
  // the text (via rAF) makes repeated identical announcements re-fire.
  var liveRegion = document.getElementById("status-live");
  function announce(message) {
    if (!liveRegion) return;
    liveRegion.textContent = "";
    window.requestAnimationFrame(function () {
      liveRegion.textContent = message;
    });
  }

  // ---------- Shared: safe storage ----------
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

  // ---------- Shared: load an optional module at most once ----------
  // Deduplicates against both earlier dynamic loads and script tags the
  // build emitted directly (search.js on search.html). A load failure
  // calls back so callers can degrade, and never breaks the page.
  var loadedModules = {};
  function loadModule(src, onFail) {
    if (!src) { if (onFail) onFail(); return; }
    if (loadedModules[src] || document.querySelector('script[src="' + src + '"]')) return;
    loadedModules[src] = true;
    var script = document.createElement("script");
    script.src = src;
    script.defer = true;
    if (onFail) script.onerror = onFail;
    document.head.appendChild(script);
  }

  // ---------- Shared: copy text to the clipboard ----------
  // Clipboard API first; a legacy execCommand fallback for browsers/
  // contexts where it's unavailable or the permission is denied.
  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var input = document.createElement("textarea");
      input.value = text;
      input.setAttribute("readonly", "");
      input.style.position = "fixed";
      input.style.top = "-1000px";
      input.style.left = "-1000px";
      document.body.appendChild(input);
      input.select();
      input.setSelectionRange(0, text.length);
      var ok = false;
      try {
        ok = document.execCommand("copy");
      } catch (err) {
        ok = false;
      }
      document.body.removeChild(input);
      if (ok) { resolve(); } else { reject(new Error("execCommand copy failed")); }
    });
  }

  // Small namespace so the optional bundles reuse these helpers instead
  // of carrying their own copies. Each bundle still guards against the
  // namespace being absent, so a bundle arriving without core (or before
  // it, which defer ordering prevents anyway) fails safe.
  window.AccessibleDocs = {
    announce: announce,
    copyText: copyText,
    storageRead: storageRead,
    storageWrite: storageWrite
  };

  // ---------- Reader preferences, bookmark button, recent pages ----------
  // The full saved-pages interface (list rendering, library management)
  // lives in reader-library.js and only loads when Reading options is
  // first opened; core only applies preferences, records the visit, and
  // keeps the one always-visible control (the bookmark button) working.
  var PREFS_KEY = "accessibleDocs.readerPrefs.v1";
  var BOOKMARKS_KEY = "accessibleDocs.bookmarks.v1";
  var RECENT_KEY = "accessibleDocs.recent.v1";

  function pageRecord() {
    return {
      slug: ds.pageSlug,
      title: ds.pageTitle,
      href: ds.pageSlug + ".html"
    };
  }
  function libraryChanged() {
    // reader-library.js re-renders its lists on this event (if loaded).
    try {
      document.dispatchEvent(new CustomEvent("accessibledocs:library-change"));
    } catch (err) { /* CustomEvent unavailable: lists refresh on next open */ }
  }

  function initReaderFeatures() {
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
    var bookmark = document.querySelector("[data-action='bookmark']");
    function updateBookmark(bookmarks) {
      if (!bookmark) return;
      var saved = bookmarks.some(function (item) { return item.slug === record.slug; });
      bookmark.setAttribute("aria-pressed", String(saved));
      bookmark.querySelector(".bookmark-label").textContent = saved ? "Remove bookmark" : "Bookmark page";
    }
    if (bookmark) {
      updateBookmark(storageRead(BOOKMARKS_KEY, []) || []);
      bookmark.addEventListener("click", function () {
        var bookmarks = storageRead(BOOKMARKS_KEY, []);
        if (!Array.isArray(bookmarks)) bookmarks = [];
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
        updateBookmark(bookmarks);
        libraryChanged();
      });
    }

    // Record the visit (clause/annex pages only) so "Recently viewed" is
    // accurate even though its list only renders when the panel opens.
    if (ds.pageGroup) {
      var recent = storageRead(RECENT_KEY, []);
      if (!Array.isArray(recent)) recent = [];
      recent = recent.filter(function (item) { return item.slug !== record.slug; });
      recent.unshift(record);
      recent = recent.slice(0, 10);
      storageWrite(RECENT_KEY, recent);
    }

    // The saved-pages interface loads the first time Reading options is
    // opened. Native details/summary means opening never depends on this
    // module arriving — the lists just keep their static placeholder text
    // if it fails, and everything else in the panel still works.
    var readerTools = document.querySelector(".reader-tools");
    if (readerTools) {
      readerTools.addEventListener("toggle", function () {
        if (readerTools.open) loadModule(ds.readerJs);
      });
      if (readerTools.open) loadModule(ds.readerJs);
    }
  }
  initReaderFeatures();

  // ---------- Mobile contents disclosure ----------
  // A plain in-flow disclosure: the Contents bar sits directly above the
  // panel it expands (top of the page body on narrow screens), so focus
  // stays on the button when it opens — the panel is the very next thing
  // in reading order. Escape closes and keeps focus on the button.
  var toggle = document.querySelector(".toc-toggle");
  var nav = document.querySelector(".site-nav");

  function closeNav() {
    if (!nav) return;
    nav.classList.remove("is-open");
    if (toggle) {
      toggle.setAttribute("aria-expanded", "false");
      toggle.focus();
    }
  }
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && nav && nav.classList.contains("is-open")) {
      closeNav();
    }
  });

  // ---------- Mobile search disclosure ----------
  // Mirrors the contents toggle above: on narrow screens the header
  // search collapses to a magnifier icon button (CSS shows it only with
  // .js); tapping it opens the form full-width and moves focus into the
  // input. Escape closes and hands focus back. Without JavaScript the
  // plain form is always visible, so search never depends on script.
  var searchToggle = document.querySelector(".search-toggle");
  var searchForm = document.querySelector(".site-search");
  if (searchToggle && searchForm) {
    var headerSearchInput = searchForm.querySelector("input[type='search']");
    searchToggle.addEventListener("click", function () {
      var open = searchForm.classList.toggle("is-open");
      searchToggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (open && headerSearchInput) headerSearchInput.focus();
    });
    searchForm.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && searchForm.classList.contains("is-open")) {
        searchForm.classList.remove("is-open");
        searchToggle.setAttribute("aria-expanded", "false");
        searchToggle.focus();
      }
    });
  }

  // ---------- Header search: load the search module on first intent ----------
  // The plain GET form submits to search.html with no JavaScript at all;
  // suggestions are an enhancement, so their code (search.js) is only
  // fetched once the reader shows intent: focusing the field or having
  // at least two characters in it. If the module fails to load, the form
  // simply keeps its native behaviour.
  var headerInput = searchForm && searchForm.querySelector("input[type='search']");
  if (headerInput && ds.searchJs) {
    var loadSearch = function () {
      if (headerInput.value.length >= 2 || document.activeElement === headerInput) {
        loadModule(ds.searchJs);
        headerInput.removeEventListener("focus", loadSearch);
        headerInput.removeEventListener("input", loadSearch);
      }
    };
    headerInput.addEventListener("focus", loadSearch);
    headerInput.addEventListener("input", loadSearch);
  }

  // Arriving from a search result or suggestion (?h=query in the URL)
  // means the search bundle's arrival-highlighter is wanted right away.
  if (window.location.search.indexOf("h=") !== -1 &&
      new URLSearchParams(window.location.search).get("h")) {
    loadModule(ds.searchJs);
  }

  // ---------- Page tools menu ----------
  // Native details/summary does open/close on its own; this only adds
  // Escape-to-close with focus handed back to the Page tools button.
  var pageTools = document.querySelector(".page-tools");
  if (pageTools) {
    pageTools.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && pageTools.open) {
        pageTools.open = false;
        pageTools.querySelector("summary").focus();
      }
    });
  }

  // ---------- Document toolbar: print ----------
  var printBtn = document.querySelector("[data-action='print']");
  if (printBtn) {
    printBtn.addEventListener("click", function () { window.print(); });
  }

  // ---------- Document toolbar: copy page link ----------
  // The button's own label never changes (a stable, predictable
  // accessible name); success/failure is reported through the shared
  // polite live region, plus a small aria-hidden visual status glyph so
  // sighted users get more than a colour-only cue.
  var copyBtn = document.querySelector("[data-action='copy-link']");
  if (copyBtn) {
    var copyStatus = copyBtn.querySelector(".doc-toolbar__btn-status");
    copyBtn.addEventListener("click", function () {
      copyText(window.location.href).then(function () {
        if (copyStatus) copyStatus.textContent = "✓";
        announce("Link copied.");
      }, function () {
        if (copyStatus) copyStatus.textContent = "⚠";
        announce("Couldn't copy the link automatically. You can copy it from the address bar.");
      });
      if (copyStatus) {
        window.setTimeout(function () { copyStatus.textContent = ""; }, 3000);
      }
    });
  }

  // ---------- Heading links ----------
  // Each numbered heading's own text is a self-referencing link (one tab
  // stop whose accessible name is the heading text itself), and its href
  // already works as a normal same-page anchor with no JS at all — after
  // activating it, the address bar holds the deep link. This only adds a
  // copy-to-clipboard enhancement on top. One delegated listener instead
  // of one per heading: some pages carry hundreds of headings.
  document.addEventListener("click", function (e) {
    var link = e.target.closest && e.target.closest(".heading-link[data-copy-link]");
    if (!link) return;
    var url = window.location.origin + window.location.pathname + link.getAttribute("href");
    copyText(url).then(function () {
      announce("Link to this heading copied.");
    }, function () {
      announce("Couldn't copy the link automatically. The address bar now shows it instead.");
    });
  });

  // ---------- Glossary term focus-on-navigate ----------
  // Baseline (no JS): a fragment link to a <dt id="..."> already scrolls it
  // into view via normal browser anchor behaviour. This only adds keyboard
  // focus on top of that, so screen reader and keyboard users landing on a
  // definition get it announced/positioned as the current point, both on
  // page load with a fragment already in the URL and when a same-page
  // A-Z index or permalink is activated afterwards. tabindex="-1" (set at
  // build time) makes each <dt> focusable-by-script without adding it to
  // normal Tab order.
  function focusFragmentTarget() {
    var hash = window.location.hash;
    if (!hash || hash.length < 2) return;
    var target;
    try {
      target = document.getElementById(decodeURIComponent(hash.slice(1)));
    } catch (err) {
      target = document.getElementById(hash.slice(1));
    }
    if (target && target.tagName === "DT") {
      target.focus();
    }
  }
  if (document.querySelector(".az-index")) {
    focusFragmentTarget();
    window.addEventListener("hashchange", focusFragmentTarget);
  }

  // ---------- Back to top ----------
  // A real <a href="#top"> link (works with no JS, keyboard-only, and
  // respects prefers-reduced-motion via CSS scroll-behavior). Visibility
  // comes from an IntersectionObserver watching a zero-cost sentinel
  // spanning the top of the page — no per-scroll JavaScript at all. The
  // fallback for browsers without IntersectionObserver is the old
  // passive scroll listener.
  var backToTop = document.querySelector(".back-to-top");
  var sentinel = document.querySelector(".top-sentinel");
  if (backToTop) {
    if (sentinel && "IntersectionObserver" in window) {
      new IntersectionObserver(function (entries) {
        backToTop.classList.toggle("is-visible", !entries[entries.length - 1].isIntersecting);
      }).observe(sentinel);
    } else {
      window.addEventListener("scroll", function () {
        backToTop.classList.toggle("is-visible", window.scrollY > 400);
      }, { passive: true });
    }
  }

  // ---------- Contents sidebar: active subsection highlight ----------
  // Scroll-spy without a per-scroll handler: every subsection heading is
  // observed against a root whose top edge is pulled down to the active
  // line (rootMargin -120px). Each observer callback records whether that
  // heading sits above or below the line; the active entry is the last
  // heading above it. The observer fires only when a heading crosses the
  // line or the viewport edge — nothing runs on ordinary scrolling
  // between headings. Browsers without IntersectionObserver simply keep
  // no highlight (a cosmetic enhancement only).
  var tocLinks = document.querySelectorAll(".site-nav__subsections a[data-subsection]");
  if (tocLinks.length && "IntersectionObserver" in window) {
    var ACTIVE_LINE = 120; // px from top of viewport
    var spied = [];
    var byElement = new Map();
    tocLinks.forEach(function (link) {
      var heading = document.getElementById(link.getAttribute("href").slice(1));
      if (heading) {
        var item = { link: link, above: false };
        spied.push(item);
        byElement.set(heading, item);
      }
    });
    var current = null;
    function updateActive() {
      var active = null;
      for (var i = 0; i < spied.length; i++) {
        if (spied[i].above) active = spied[i];
      }
      if (!active) active = spied[0];
      if (active === current) return;
      if (current) current.link.removeAttribute("aria-current");
      if (active) active.link.setAttribute("aria-current", "location");
      current = active;
    }
    if (spied.length) {
      var spy = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          var item = byElement.get(entry.target);
          if (item) item.above = entry.boundingClientRect.top < ACTIVE_LINE + 1;
        });
        updateActive();
      }, { rootMargin: "-" + ACTIVE_LINE + "px 0px 0px 0px" });
      byElement.forEach(function (item, heading) { spy.observe(heading); });
    }
  }

  // ---------- Intent-based same-origin prefetching ----------
  // Prefetches the HTML of an internal link the reader is clearly about
  // to follow (sustained hover, keyboard focus) and, once they have
  // started paging sequentially, the previous/next clause during idle
  // time. Never on data-saver or slow connections, never external URLs
  // or PDFs, never the current page, each URL at most once, bounded
  // overall. Uses <link rel="prefetch">, which browsers fetch at idle
  // priority and which never moves focus or announces anything. Failures
  // are silent by design.
  var PREFETCH_LIMIT = 12;
  var HOVER_DELAY = 120; // ms of sustained hover before it counts as intent
  var SEQ_KEY = "accessibleDocs.sequentialNav.v1";
  var prefetched = {};
  var prefetchCount = 0;
  var connection = navigator.connection || {};
  var prefetchAllowed = !connection.saveData &&
    !/(^|-)2g$/.test(connection.effectiveType || "") &&
    document.createElement("link").relList &&
    document.createElement("link").relList.supports &&
    document.createElement("link").relList.supports("prefetch");

  function prefetchTarget(a) {
    if (!prefetchAllowed || prefetchCount >= PREFETCH_LIMIT) return;
    if (!a || !a.href || a.origin !== window.location.origin) return;
    if (!/\.html$/.test(a.pathname)) return; // never PDFs, JSON or indexes
    if (a.pathname === window.location.pathname) return;
    if (prefetched[a.pathname]) return;
    prefetched[a.pathname] = true;
    prefetchCount++;
    var link = document.createElement("link");
    link.rel = "prefetch";
    link.href = a.pathname;
    link.as = "document";
    document.head.appendChild(link);
  }

  if (prefetchAllowed) {
    var hoverTimer = null;
    document.addEventListener("mouseover", function (e) {
      var a = e.target.closest && e.target.closest("a[href]");
      if (!a) return;
      window.clearTimeout(hoverTimer);
      hoverTimer = window.setTimeout(function () { prefetchTarget(a); }, HOVER_DELAY);
    });
    document.addEventListener("mouseout", function () {
      window.clearTimeout(hoverTimer);
    });
    document.addEventListener("focusin", function (e) {
      var a = e.target.closest && e.target.closest("a[href]");
      if (a) prefetchTarget(a);
    });

    // Sequential reading: after two pager navigations in a session, the
    // reader is clearly moving clause to clause, so warm the previous and
    // next pages during browser idle time.
    document.addEventListener("click", function (e) {
      var a = e.target.closest && e.target.closest(".page-pager__link");
      if (!a) return;
      try {
        var n = parseInt(window.sessionStorage.getItem(SEQ_KEY), 10) || 0;
        window.sessionStorage.setItem(SEQ_KEY, String(n + 1));
      } catch (err) { /* private mode: sequential warming just stays off */ }
    });
    var sequential = 0;
    try {
      sequential = parseInt(window.sessionStorage.getItem(SEQ_KEY), 10) || 0;
    } catch (err) { sequential = 0; }
    if (sequential >= 2 && "requestIdleCallback" in window) {
      window.requestIdleCallback(function () {
        document.querySelectorAll(".page-pager__link").forEach(prefetchTarget);
      }, { timeout: 4000 });
    }
  }
})();
