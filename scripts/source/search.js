/*
  search.js — everything search, in one optional bundle.

  Loaded eagerly (deferred) only on search.html; on every other page
  core.js injects it the first time the header search field receives
  focus or two typed characters. The header's plain GET form works
  before and without it.

  Two indexes, both generated and content-hashed by the build:
    search-suggestions.<hash>.json — tiny; titles/numbers only; powers
                                     header autocomplete. No Web Worker:
                                     scoring a few hundred titles is
                                     cheap enough for the main thread.
    search-index.<hash>.json       — full body text; only the search
                                     page fetches it, and ranking runs
                                     in a Web Worker so typing and
                                     scrolling stay responsive on
                                     low-powered devices. A synchronous
                                     main-thread fallback covers
                                     browsers without workers and
                                     worker start-up failures.

  URLs come from data attributes on <body> (data-suggest-index,
  data-search-index, data-search-worker) so nothing here hardcodes a
  content hash. Each resource is fetched at most once per page: the
  promise, not the payload, is cached.

  NOTE: the scoring here must stay in step with scripts/source/
  search-worker.js — the worker carries its own copy so it can run
  standalone, and the fallback in this file must rank identically.
*/
(function () {
  "use strict";

  var shared = window.AccessibleDocs || {};
  var announce = shared.announce || function () {};
  var ds = document.body.dataset;

  // ---------- Fetch caching ----------
  // One promise per URL for the lifetime of the page, created on first
  // use — so the suggestions index is fetched at most once no matter how
  // many keystrokes arrive, and never during initial page render.
  var resourcePromises = {};
  function loadJson(url) {
    if (!url) return Promise.reject(new Error("no index URL on this page"));
    if (!resourcePromises[url]) {
      resourcePromises[url] = fetch(url).then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status + " loading " + url);
        }
        return response.json();
      });
    }
    return resourcePromises[url];
  }

  // ---------- Scoring (keep identical to search-worker.js) ----------
  function searchTokens(q) {
    return q.toLowerCase().split(/\s+/).filter(Boolean);
  }
  function scoreSearchEntry(entry, toks, q) {
    var t = entry.t.toLowerCase();
    var b = (entry.b || "").toLowerCase();
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
    // Exact clause-number lookup against the suggestions index's number
    // field ("9.1.1.1" typed exactly) pins that requirement to the top.
    if (entry.n && entry.n === q) score += 100;
    return score;
  }
  function searchHits(index, q) {
    var toks = searchTokens(q);
    var ql = q.toLowerCase();
    var hits = [];
    for (var i = 0; i < index.length; i++) {
      var s = scoreSearchEntry(index[i], toks, ql);
      if (s > 0) hits.push({ s: s, e: index[i] });
    }
    hits.sort(function (a, b) { return b.s - a.s; });
    return hits;
  }

  // Result links carry the query as ?h=…, so the destination page can
  // highlight the matched words on arrival (the highlight block at the
  // bottom of this file; core.js loads this module whenever a page
  // arrives with ?h= in its URL).
  function withHighlightParam(u, q) {
    var hashAt = u.indexOf("#");
    var base = hashAt === -1 ? u : u.slice(0, hashAt);
    var hash = hashAt === -1 ? "" : u.slice(hashAt);
    return base + (base.indexOf("?") === -1 ? "?" : "&") + "h=" + encodeURIComponent(q) + hash;
  }

  // ---------- Site search (search.html) ----------
  // The header's search form is a plain GET form to search.html, so
  // reaching this page needs no JavaScript — only the filtering itself
  // does, and the page says so when JS is unavailable (see .search-nojs).
  var searchInput = document.getElementById("search-input");
  var searchResults = document.getElementById("search-results");
  var searchCount = document.getElementById("search-count");
  if (searchInput && searchResults) {
    var SEARCH_LIMIT = 50;

    // -- Query engine: Web Worker preferred, main thread as fallback. --
    // The worker fetches and holds the full index off the main thread
    // and returns only the top results (with a pre-cut snippet window),
    // so the page never touches the whole index in its own thread.
    var worker = null;
    var workerFailed = false;
    var queryId = 0;
    var pendingRender = null; // latest query wins; stale replies dropped
    var fallbackIndex = null;

    function describeFailure() {
      searchCount.textContent =
        "Search couldn’t load its index. Check your connection and reload the page to try again. " +
        "Everything on this website is still reachable from the contents list on any page.";
    }

    function startWorker() {
      if (workerFailed || !window.Worker || !ds.searchWorker || !ds.searchIndex) return null;
      try {
        var w = new Worker(ds.searchWorker);
        w.onmessage = function (e) {
          var msg = e && e.data;
          if (!msg || typeof msg !== "object") return;
          if (msg.type === "results" && pendingRender && msg.id === pendingRender.id) {
            renderResults(pendingRender.q, msg.total, msg.results);
            pendingRender = null;
          } else if (msg.type === "error") {
            // The worker started but its index fetch/parse failed —
            // retrying on the main thread would hit the same problem,
            // so say so plainly instead.
            describeFailure();
          }
        };
        w.onerror = function () {
          // The worker script itself failed to load or crashed: fall
          // back to the synchronous main-thread engine, re-running the
          // outstanding query if there is one.
          workerFailed = true;
          worker = null;
          var q = pendingRender && pendingRender.q;
          pendingRender = null;
          if (q) runQuery(q);
        };
        // Resolve against the page URL: inside the worker a relative
        // path would resolve against the worker script's own directory.
        w.postMessage({
          type: "init",
          url: new URL(ds.searchIndex, window.location.href).href,
          bodyCut: SNIPPET_BODY_WINDOW
        });
        return w;
      } catch (err) {
        workerFailed = true;
        return null;
      }
    }

    // Snippet window the engine returns per hit (characters of body text
    // around the first matched token). Rendering marks the tokens inside.
    var SNIPPET_BODY_WINDOW = { before: 70, after: 130 };

    function mainThreadResults(q) {
      loadJson(ds.searchIndex).then(function (index) {
        fallbackIndex = index;
        if (!pendingRender || pendingRender.q !== q) return;
        var hits = searchHits(index, q);
        var results = hits.slice(0, SEARCH_LIMIT).map(function (hit) {
          return { u: hit.e.u, t: hit.e.t, p: hit.e.p, snip: cutSnippet(hit.e.b || "", searchTokens(q)) };
        });
        renderResults(q, hits.length, results);
        pendingRender = null;
      }).catch(function () {
        describeFailure();
      });
    }

    // Mirrors the worker's snippet cutting so both paths render alike.
    function cutSnippet(b, toks) {
      if (!b) return { text: "", pre: false, post: false };
      var lower = b.toLowerCase();
      var pos = -1;
      for (var i = 0; i < toks.length; i++) {
        pos = lower.indexOf(toks[i]);
        if (pos !== -1) break;
      }
      if (pos === -1) pos = 0;
      var start = Math.max(0, pos - SNIPPET_BODY_WINDOW.before);
      var end = Math.min(b.length, pos + SNIPPET_BODY_WINDOW.after);
      return { text: b.slice(start, end), pre: start > 0, post: end < b.length };
    }

    function runQuery(q) {
      q = q.trim();
      searchResults.textContent = "";
      if (!q) { searchCount.textContent = ""; return; }
      pendingRender = { id: ++queryId, q: q };
      if (!workerFailed && ds.searchWorker && window.Worker) {
        if (!worker) worker = startWorker();
        if (worker) {
          worker.postMessage({ type: "query", id: pendingRender.id, q: q, limit: SEARCH_LIMIT });
          return;
        }
      }
      mainThreadResults(q);
    }

    // Builds "…text <mark>match</mark> text…" safely via DOM nodes.
    function snippetNodes(snip, toks) {
      var frag = document.createDocumentFragment();
      if (!snip || !snip.text) return frag;
      var slice = snip.text;
      var sliceLower = slice.toLowerCase();
      if (snip.pre) frag.appendChild(document.createTextNode("… "));
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
      if (snip.post) frag.appendChild(document.createTextNode(" …"));
      return frag;
    }

    function renderResults(q, total, results) {
      var toks = searchTokens(q);
      searchResults.textContent = "";
      searchCount.textContent = total === 0
        ? "No results for “" + q + "”. Try fewer or different words, or a clause number."
        : (total > SEARCH_LIMIT
            ? total + " results for “" + q + "” — showing the first " + SEARCH_LIMIT + "."
            : total + (total === 1 ? " result" : " results") + " for “" + q + "”.");
      results.forEach(function (r) {
        var li = document.createElement("li");
        var a = document.createElement("a");
        a.href = withHighlightParam(r.u, q);
        a.textContent = r.t;
        var where = document.createElement("span");
        where.className = "search-result__page";
        where.textContent = r.p;
        var p = document.createElement("p");
        p.className = "search-result__snippet";
        p.appendChild(snippetNodes(r.snip, toks));
        li.appendChild(a);
        li.appendChild(where);
        li.appendChild(p);
        searchResults.appendChild(li);
      });
    }

    // Start the worker (and its index download) as soon as the search
    // page's script runs: the reader came here to search, so the index
    // is wanted, and the worker keeps every byte of it — download, parse
    // and ranking — off the main thread while they type. Ordinary pages
    // never reach this branch (no #search-input), so this never preloads
    // the index during normal reading.
    if (!workerFailed && ds.searchWorker && window.Worker) {
      worker = startWorker();
    }

    var initialQ = new URLSearchParams(window.location.search).get("q") || "";
    searchInput.value = initialQ;
    if (initialQ) runQuery(initialQ);

    var timer = null;
    searchInput.addEventListener("input", function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        runQuery(searchInput.value);
        var url = new URL(window.location.href);
        if (searchInput.value.trim()) url.searchParams.set("q", searchInput.value.trim());
        else url.searchParams.delete("q");
        window.history.replaceState(null, "", url);
      }, 150);
    });
    searchInput.closest("form").addEventListener("submit", function (e) {
      e.preventDefault();
      runQuery(searchInput.value);
    });
  }

  // ---------- Header search suggestions ----------
  // Progressive enhancement over the header's plain GET form: typing
  // shows the top matches as a listbox so a reader can jump straight to
  // a clause without the results page. Backed by the small suggestions
  // index only (titles, clause numbers, page names — no body text), so
  // it stays a light download and needs no worker. ARIA combobox
  // pattern: arrow keys move through options, Enter follows the active
  // one (or submits the form when none is active), Escape closes.
  var headerForm = document.querySelector(".site-search");
  var headerInput = headerForm && headerForm.querySelector("input[type='search']");
  if (headerForm && headerInput && !document.getElementById("search-input") && ds.suggestIndex) {
    var SUGGEST_LIMIT = 7;
    var suggestList = document.createElement("ul");
    suggestList.id = "search-suggestions";
    suggestList.className = "search-suggest";
    suggestList.setAttribute("role", "listbox");
    suggestList.setAttribute("aria-label", "Search suggestions");
    suggestList.hidden = true;
    headerForm.appendChild(suggestList);
    headerInput.setAttribute("role", "combobox");
    headerInput.setAttribute("aria-expanded", "false");
    headerInput.setAttribute("aria-controls", "search-suggestions");
    headerInput.setAttribute("aria-autocomplete", "list");
    var activeIndex = -1;

    function closeSuggest() {
      suggestList.hidden = true;
      suggestList.textContent = "";
      headerInput.setAttribute("aria-expanded", "false");
      headerInput.removeAttribute("aria-activedescendant");
      activeIndex = -1;
    }

    function setActive(next) {
      var options = suggestList.children;
      if (!options.length) return;
      if (activeIndex >= 0) options[activeIndex].removeAttribute("aria-selected");
      activeIndex = (next + options.length) % options.length;
      var opt = options[activeIndex];
      opt.setAttribute("aria-selected", "true");
      headerInput.setAttribute("aria-activedescendant", opt.id);
    }

    function renderSuggestions(q) {
      loadJson(ds.suggestIndex).then(function (data) {
        if (headerInput.value.trim() !== q) return; // stale response
        var shown = searchHits(data, q).slice(0, SUGGEST_LIMIT);
        closeSuggest();
        if (!shown.length) return;
        shown.forEach(function (hit, i) {
          var li = document.createElement("li");
          li.id = "search-suggestion-" + i;
          li.setAttribute("role", "option");
          li.dataset.href = withHighlightParam(hit.e.u, q);
          var title = document.createElement("span");
          title.className = "search-suggest__title";
          title.textContent = hit.e.t;
          var where = document.createElement("span");
          where.className = "search-suggest__page";
          where.textContent = hit.e.p;
          li.appendChild(title);
          li.appendChild(where);
          // mousedown, not click: click fires after the input's blur has
          // already closed and emptied the list.
          li.addEventListener("mousedown", function (e) {
            e.preventDefault();
            window.location.href = li.dataset.href;
          });
          suggestList.appendChild(li);
        });
        suggestList.hidden = false;
        headerInput.setAttribute("aria-expanded", "true");
        announce(shown.length + (shown.length === 1 ? " suggestion" : " suggestions") +
                 " available. Use up and down arrows to review them.");
      }).catch(function () { /* suggestions are optional; the form still submits */ });
    }

    var suggestTimer = null;
    headerInput.addEventListener("input", function () {
      window.clearTimeout(suggestTimer);
      var q = headerInput.value.trim();
      if (q.length < 2) { closeSuggest(); return; }
      suggestTimer = window.setTimeout(function () { renderSuggestions(q); }, 150);
    });
    // Warm the (small) suggestions index on focus so the first keystrokes
    // don't wait on the network. This module itself only loads after
    // clear intent, so this never runs during initial page render.
    headerInput.addEventListener("focus", function () {
      loadJson(ds.suggestIndex).catch(function () { /* same failure path as above */ });
    });
    headerInput.addEventListener("keydown", function (e) {
      if (suggestList.hidden) return;
      if (e.key === "ArrowDown") { e.preventDefault(); setActive(activeIndex + 1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); setActive(activeIndex - 1); }
      else if (e.key === "Enter" && activeIndex >= 0) {
        e.preventDefault();
        window.location.href = suggestList.children[activeIndex].dataset.href;
      } else if (e.key === "Escape") {
        // Close the list but keep the typed text (the browser's default
        // for Escape in a search input is to clear it) — a second Escape,
        // with the list already closed, still clears as normal.
        e.preventDefault();
        closeSuggest();
      }
    });
    headerInput.addEventListener("blur", function () {
      window.setTimeout(closeSuggest, 100);
    });

    // core.js loads this module on focus/typing, which can mean the
    // reader already has two or more characters waiting — show their
    // suggestions right away rather than waiting for the next keystroke.
    if (headerInput.value.trim().length >= 2) {
      renderSuggestions(headerInput.value.trim());
    } else if (document.activeElement === headerInput) {
      loadJson(ds.suggestIndex).catch(function () {});
    }
  }

  // ---------- Search-term highlighting on arrival ----------
  // A link followed from search results or suggestions carries the query
  // as ?h=…; this wraps its occurrences in the page body in <mark> so the
  // reader can see why they landed here. core.js loads this module on any
  // page whose URL carries ?h=. Client-side presentation only — the
  // generated HTML on disk never changes — and the parameter is removed
  // from the address bar afterwards so a copied link stays clean.
  var highlightQuery = new URLSearchParams(window.location.search).get("h");
  var contentRoot = document.querySelector(".content");
  if (highlightQuery && contentRoot) {
    var highlightToks = searchTokens(highlightQuery).filter(function (t) { return t.length >= 2; });
    var MARK_CAP = 200;
    var marked = 0;
    var walker = document.createTreeWalker(contentRoot, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        var parent = node.parentNode;
        if (!parent || /^(SCRIPT|STYLE|MARK)$/.test(parent.tagName)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);
    textNodes.forEach(function (node) {
      if (marked >= MARK_CAP) return;
      var text = node.nodeValue;
      var lower = text.toLowerCase();
      var pieces = [];
      var cursor = 0;
      while (cursor < text.length && marked < MARK_CAP) {
        var next = -1, tok = null;
        for (var i = 0; i < highlightToks.length; i++) {
          var at = lower.indexOf(highlightToks[i], cursor);
          if (at !== -1 && (next === -1 || at < next)) { next = at; tok = highlightToks[i]; }
        }
        if (next === -1) break;
        pieces.push(document.createTextNode(text.slice(cursor, next)));
        var mark = document.createElement("mark");
        mark.className = "search-highlight";
        mark.textContent = text.slice(next, next + tok.length);
        pieces.push(mark);
        cursor = next + tok.length;
        marked++;
      }
      if (!pieces.length) return;
      pieces.push(document.createTextNode(text.slice(cursor)));
      var frag = document.createDocumentFragment();
      pieces.forEach(function (p) { frag.appendChild(p); });
      node.parentNode.replaceChild(frag, node);
    });
    var cleanUrl = new URL(window.location.href);
    cleanUrl.searchParams.delete("h");
    window.history.replaceState(null, "", cleanUrl);
  }
})();
