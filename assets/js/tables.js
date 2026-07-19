// Scrollable-table keyboard access and a visible cue. Loaded ONLY on
// pages that actually contain a .table-wrap (the build includes this
// module conditionally), so table-free pages download none of it. A
// .table-wrap that overflows horizontally is only reachable by mouse
// drag/trackpad unless it is in the tab order, so make it focusable and
// arrow-key scrollable whenever it is actually scrollable — and add a
// visible "scroll sideways" hint. Everything is removed again the moment
// the table stops overflowing (e.g. after a resize), so a table that fits
// is just a table. Standalone (no shared dependencies).
(function () {
  "use strict";

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
})();
