/*
  tables.js — scrollable-table access, only on pages that have tables.

  The build emits this bundle's script tag only on pages whose content
  contains a .table-wrap (13 of the site's 38 pages) — table-free pages
  never download or run any of it.

  A .table-wrap that overflows horizontally is only reachable by mouse
  drag/trackpad unless it's in the tab order, so make it focusable and
  scrollable via arrow keys whenever it's actually scrollable — and add
  a visible "scroll sideways" hint so sighted users know more columns
  exist even on platforms with hidden overlay scrollbars. Everything is
  removed again the moment the table stops overflowing (e.g. after a
  resize), so a table that fits is just a table.

  Sizing work is observation-driven: one ResizeObserver watches every
  wrapper and only re-evaluates the wrappers that actually changed size,
  batched to a single animation frame with all layout reads performed
  before any DOM write (never an interleaved read/write loop). Browsers
  without ResizeObserver get one debounced window-resize handler with the
  same read-then-write batching.
*/
(function () {
  "use strict";

  var wraps = Array.prototype.slice.call(document.querySelectorAll(".table-wrap"));
  if (!wraps.length) return;

  // Apply accessibility state to one wrapper from an already-measured
  // scrollable flag — this function only writes, never measures.
  function applyState(wrap, scrollable) {
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
  }

  // Read-then-write update for a batch of wrappers, at most once per
  // animation frame no matter how many resize notifications arrive.
  var pending = new Set();
  var frame = null;
  function scheduleUpdate(changed) {
    changed.forEach(function (wrap) { pending.add(wrap); });
    if (frame !== null) return;
    frame = window.requestAnimationFrame(function () {
      frame = null;
      var batch = Array.from(pending);
      pending.clear();
      // Phase 1: read every measurement...
      var measured = batch.map(function (wrap) {
        return { wrap: wrap, scrollable: wrap.scrollWidth > wrap.clientWidth };
      });
      // ...phase 2: apply every DOM change. No reads past this point.
      measured.forEach(function (m) { applyState(m.wrap, m.scrollable); });
    });
  }

  if ("ResizeObserver" in window) {
    var observer = new ResizeObserver(function (entries) {
      scheduleUpdate(entries.map(function (entry) { return entry.target; }));
    });
    wraps.forEach(function (wrap) { observer.observe(wrap); });
    // ResizeObserver fires once on observe, so no separate initial pass
    // is needed.
  } else {
    scheduleUpdate(wraps);
    var timer = null;
    window.addEventListener("resize", function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(function () { scheduleUpdate(wraps); }, 150);
    });
  }
})();
