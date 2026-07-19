// Core: the tiny shared layer loaded on every page (bundled first into
// the main script). It marks JavaScript as available, owns the single
// polite live region, and exposes a small window.__site namespace the
// other feature modules build on. Deliberately minimal — page-specific
// features live in their own modules, not here.
(function () {
  "use strict";

  // Marks JS as available so CSS can gate JS-only behaviour (the
  // collapsed-by-default mobile contents panel and its toggle button)
  // behind it. Set as early as possible. Without this class, .site-nav
  // and its contents stay in their plain, always-visible no-JS state —
  // see the CSS comment above ".js .site-nav".
  document.documentElement.classList.add("js");

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

  window.__site = { announce: announce };
})();
