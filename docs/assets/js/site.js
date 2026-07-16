(function () {
  "use strict";

  // Marks JS as available so CSS can gate JS-only behaviour (the collapsed-
  // by-default mobile contents panel and its toggle button) behind it. Set
  // as early as possible, and before anything else below runs. Without
  // this class, .site-nav and its contents stay in their plain, always-
  // visible no-JS state — see the CSS comment above ".js .site-nav".
  document.documentElement.classList.add("js");

  // ---------- Shared: polite status announcements ----------
  // One live region per page (in the template). Clearing then re-setting
  // the text (via rAF) makes repeated identical announcements re-fire,
  // which a naive textContent-only update would not.
  var liveRegion = document.getElementById("status-live");
  function announce(message) {
    if (!liveRegion) return;
    liveRegion.textContent = "";
    window.requestAnimationFrame(function () {
      liveRegion.textContent = message;
    });
  }

  // ---------- Reader preferences, bookmarks and recent pages ----------
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
  function initReaderFeatures() {
    var prefs = storageRead(PREFS_KEY, { width: "wide", spacing: false });
    if (!prefs || !["wide", "comfortable"].includes(prefs.width)) {
      prefs = { width: "wide", spacing: false };
    }
    function applyPrefs() {
      document.documentElement.dataset.readingWidth = prefs.width;
      if (prefs.spacing) document.documentElement.dataset.textSpacing = "enhanced";
      else delete document.documentElement.dataset.textSpacing;
      document.querySelectorAll('input[name="reading-width"]').forEach(function (input) {
        input.checked = input.value === prefs.width;
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
    var spacing = document.querySelector("[data-reading-spacing]");
    if (spacing) spacing.addEventListener("change", function () {
      prefs.spacing = spacing.checked;
      applyPrefs();
      storageWrite(PREFS_KEY, prefs);
    });
    var reset = document.querySelector("[data-reader-reset]");
    if (reset) reset.addEventListener("click", function () {
      prefs = { width: "wide", spacing: false };
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
  }
  initReaderFeatures();

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

  // ---------- Mobile contents disclosure ----------
  // An in-flow expand/collapse panel (not a full-screen overlay), so
  // opening it never hides other page content behind it and keyboard
  // focus is never trapped or lost. Both the header toggle and the
  // in-panel close button flip the same aria-expanded/is-open state.
  var toggle = document.querySelector(".toc-toggle");
  var nav = document.querySelector(".site-nav");
  var closeBtn = document.querySelector(".site-nav__close");

  function openNav() {
    if (!nav) return;
    nav.classList.add("is-open");
    if (toggle) toggle.setAttribute("aria-expanded", "true");
    if (closeBtn) closeBtn.focus();
  }
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
      var expanded = toggle.getAttribute("aria-expanded") === "true";
      if (expanded) { closeNav(); } else { openNav(); }
    });
  }
  if (closeBtn) {
    closeBtn.addEventListener("click", closeNav);
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
    // Named distinctly from the search page's own searchInput below —
    // both share this function scope, so a duplicate var would collide.
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
  // copy-to-clipboard enhancement on top — it does not prevent the
  // default navigation, so keyboard/no-JS users still get a fully
  // working direct link.
  document.querySelectorAll(".heading-link[data-copy-link]").forEach(function (link) {
    link.addEventListener("click", function () {
      var url = window.location.origin + window.location.pathname + link.getAttribute("href");
      copyText(url).then(function () {
        announce("Link to this heading copied.");
      }, function () {
        announce("Couldn't copy the link automatically. The address bar now shows it instead.");
      });
    });
  });

  // ---------- Site search (search.html) ----------
  // Entirely static: the build writes docs/search-index.json (one entry
  // per heading section, glossary term, and page intro), and this filters
  // it in the browser. No search service, no third-party library. The
  // header's search form is a plain GET form to search.html, so reaching
  // this page needs no JavaScript — only the filtering itself does, and
  // the page says so when JS is unavailable (see .search-nojs).
  var searchInput = document.getElementById("search-input");
  var searchResults = document.getElementById("search-results");
  var searchCount = document.getElementById("search-count");
  if (searchInput && searchResults) {
    var SEARCH_LIMIT = 50;
    var index = null;

    function tokens(q) {
      return q.toLowerCase().split(/\s+/).filter(Boolean);
    }

    function scoreEntry(entry, toks, q) {
      var t = entry.t.toLowerCase();
      var b = entry.b.toLowerCase();
      var score = 0;
      for (var i = 0; i < toks.length; i++) {
        var inTitle = t.indexOf(toks[i]) !== -1;
        var inBody = b.indexOf(toks[i]) !== -1;
        if (!inTitle && !inBody) return 0; // every word must match somewhere
        score += inTitle ? 3 : 1;
      }
      // A query that looks like a clause number ("9.1.4.4") should surface
      // that exact heading first.
      if (t.indexOf(q) === 0) score += 10;
      else if (t.indexOf(q) !== -1) score += 4;
      return score;
    }

    // Builds "…text <mark>match</mark> text…" safely via DOM nodes.
    function snippetFor(entry, toks) {
      var frag = document.createDocumentFragment();
      var b = entry.b;
      if (!b) return frag;
      var lower = b.toLowerCase();
      var pos = -1;
      for (var i = 0; i < toks.length; i++) {
        pos = lower.indexOf(toks[i]);
        if (pos !== -1) break;
      }
      if (pos === -1) { pos = 0; }
      var start = Math.max(0, pos - 70);
      var end = Math.min(b.length, pos + 130);
      var slice = b.slice(start, end);
      var sliceLower = slice.toLowerCase();
      if (start > 0) frag.appendChild(document.createTextNode("… "));
      var cursor = 0;
      while (cursor < slice.length) {
        var next = -1, nextTok = null;
        for (var j = 0; j < toks.length; j++) {
          var at = sliceLower.indexOf(toks[j], cursor);
          if (at !== -1 && (next === -1 || at < next)) { next = at; nextTok = toks[j]; }
        }
        if (next === -1) {
          frag.appendChild(document.createTextNode(slice.slice(cursor)));
          break;
        }
        frag.appendChild(document.createTextNode(slice.slice(cursor, next)));
        var mark = document.createElement("mark");
        mark.textContent = slice.slice(next, next + nextTok.length);
        frag.appendChild(mark);
        cursor = next + nextTok.length;
      }
      if (end < b.length) frag.appendChild(document.createTextNode(" …"));
      return frag;
    }

    function runSearch(q) {
      q = q.trim();
      searchResults.textContent = "";
      if (!q) { searchCount.textContent = ""; return; }
      var toks = tokens(q);
      var ql = q.toLowerCase();
      var hits = [];
      for (var i = 0; i < index.length; i++) {
        var s = scoreEntry(index[i], toks, ql);
        if (s > 0) hits.push({ s: s, e: index[i] });
      }
      hits.sort(function (a, b) { return b.s - a.s; });
      var shown = hits.slice(0, SEARCH_LIMIT);
      searchCount.textContent = hits.length === 0
        ? "No results for “" + q + "”. Try fewer or different words, or a clause number."
        : (hits.length > SEARCH_LIMIT
            ? hits.length + " results for “" + q + "” — showing the first " + SEARCH_LIMIT + "."
            : hits.length + (hits.length === 1 ? " result" : " results") + " for “" + q + "”.");
      shown.forEach(function (hit) {
        var li = document.createElement("li");
        var a = document.createElement("a");
        a.href = hit.e.u;
        a.textContent = hit.e.t;
        var where = document.createElement("span");
        where.className = "search-result__page";
        where.textContent = hit.e.p;
        var p = document.createElement("p");
        p.className = "search-result__snippet";
        p.appendChild(snippetFor(hit.e, toks));
        li.appendChild(a);
        li.appendChild(where);
        li.appendChild(p);
        searchResults.appendChild(li);
      });
    }

    var initialQ = new URLSearchParams(window.location.search).get("q") || "";
    searchInput.value = initialQ;

    fetch("search-index.json").then(function (r) { return r.json(); }).then(function (data) {
      index = data;
      if (initialQ) runSearch(initialQ);
      var timer = null;
      searchInput.addEventListener("input", function () {
        window.clearTimeout(timer);
        timer = window.setTimeout(function () {
          runSearch(searchInput.value);
          var url = new URL(window.location.href);
          if (searchInput.value.trim()) url.searchParams.set("q", searchInput.value.trim());
          else url.searchParams.delete("q");
          window.history.replaceState(null, "", url);
        }, 150);
      });
      searchInput.closest("form").addEventListener("submit", function (e) {
        e.preventDefault();
        runSearch(searchInput.value);
      });
    }).catch(function () {
      searchCount.textContent = "Search couldn’t load its index. Reload the page to try again.";
    });
  }

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
  // respects prefers-reduced-motion via CSS scroll-behavior). JS only
  // toggles its visibility based on scroll position.
  var backToTop = document.querySelector(".back-to-top");
  if (backToTop) {
    window.addEventListener("scroll", function () {
      if (window.scrollY > 400) {
        backToTop.classList.add("is-visible");
      } else {
        backToTop.classList.remove("is-visible");
      }
    }, { passive: true });
  }

  // ---------- Scrollable tables: keyboard access + visible cue ----------
  // A .table-wrap that overflows horizontally is only reachable by mouse
  // drag/trackpad unless it's in the tab order, so make it focusable and
  // scrollable via arrow keys whenever it's actually scrollable — and add
  // a visible "scroll sideways" hint so sighted users know more columns
  // exist even on platforms with hidden overlay scrollbars. Everything is
  // removed again the moment the table stops overflowing (e.g. after a
  // resize), so a table that fits is just a table.
  function updateScrollableTables() {
    document.querySelectorAll(".table-wrap").forEach(function (wrap) {
      var scrollable = wrap.scrollWidth > wrap.clientWidth;
      var hint = wrap.querySelector(".table-wrap__hint");
      if (scrollable) {
        if (!wrap.hasAttribute("tabindex")) {
          wrap.setAttribute("tabindex", "0");
          wrap.dataset.siteTableTabindex = "true";
        }
        if (!wrap.hasAttribute("role")) {
          wrap.setAttribute("role", "region");
          wrap.dataset.siteTableRole = "true";
        }
        if (!wrap.hasAttribute("aria-label")) {
          var caption = wrap.querySelector("caption");
          wrap.setAttribute("aria-label", caption ? caption.textContent.trim() : "Scrollable table");
          wrap.dataset.siteTableLabel = "true";
        }
        if (!hint) {
          hint = document.createElement("p");
          hint.className = "table-wrap__hint";
          hint.dataset.siteTableHint = "true";
          // aria-hidden: screen-reader users already hear the wrapper's
          // role and label; this line is the sighted-user equivalent.
          hint.setAttribute("aria-hidden", "true");
          hint.textContent = "This table scrolls sideways →";
          wrap.insertBefore(hint, wrap.firstChild);
        }
      } else {
        if (wrap.dataset.siteTableTabindex === "true") {
          wrap.removeAttribute("tabindex");
          delete wrap.dataset.siteTableTabindex;
        }
        if (wrap.dataset.siteTableRole === "true") {
          wrap.removeAttribute("role");
          delete wrap.dataset.siteTableRole;
        }
        if (wrap.dataset.siteTableLabel === "true") {
          wrap.removeAttribute("aria-label");
          delete wrap.dataset.siteTableLabel;
        }
        if (hint && hint.dataset.siteTableHint === "true") hint.remove();
      }
    });
  }
  if (document.querySelector(".table-wrap")) {
    updateScrollableTables();
    window.addEventListener("resize", updateScrollableTables);
    if (document.fonts) {
      document.fonts.ready.then(updateScrollableTables);
    }
  }

  // ---------- Contents sidebar: active subsection highlight ----------
  // Scroll-spy: the active heading is the last one whose top has scrolled
  // past a fixed line near the top of the viewport. Simpler and more
  // reliable than IntersectionObserver threshold-crossing here, since
  // headings can be far apart (long sections) and a narrow observer band
  // can end up with nothing "visible" between them.
  var tocLinks = document.querySelectorAll(".site-nav__subsections a[data-subsection]");
  if (tocLinks.length) {
    var headings = [];
    tocLinks.forEach(function (link) {
      var id = link.getAttribute("href").slice(1);
      var heading = document.getElementById(id);
      if (heading) headings.push({ link: link, el: heading });
    });

    var ACTIVE_LINE = 120; // px from top of viewport
    var ticking = false;

    function updateActive() {
      ticking = false;
      var active = headings[0];
      for (var i = 0; i < headings.length; i++) {
        if (headings[i].el.getBoundingClientRect().top <= ACTIVE_LINE) {
          active = headings[i];
        } else {
          break;
        }
      }
      tocLinks.forEach(function (link) { link.removeAttribute("aria-current"); });
      if (active) active.link.setAttribute("aria-current", "location");
    }

    function onScroll() {
      if (!ticking) {
        ticking = true;
        window.requestAnimationFrame(updateActive);
      }
    }

    if (headings.length) {
      updateActive();
      window.addEventListener("scroll", onScroll, { passive: true });
      window.addEventListener("resize", onScroll);
    }
  }
})();
