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

  // ---------- Heading permalinks ----------
  // Each numbered heading has a small, always-visible "#" link whose
  // href already works as a normal same-page anchor with no JS at all.
  // This only adds a copy-to-clipboard enhancement on top — it does not
  // prevent the default navigation, so keyboard/no-JS users still get a
  // fully working direct link.
  document.querySelectorAll(".heading-permalink[data-copy-link]").forEach(function (link) {
    link.addEventListener("click", function () {
      var url = window.location.origin + window.location.pathname + link.getAttribute("href");
      copyText(url).then(function () {
        announce("Link to this heading copied.");
      }, function () {
        announce("Couldn't copy the link automatically. The address bar now shows it instead.");
      });
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
        wrap.setAttribute("tabindex", "0");
        wrap.setAttribute("role", "region");
        if (!wrap.hasAttribute("aria-label")) {
          var caption = wrap.querySelector("caption");
          wrap.setAttribute("aria-label", caption ? caption.textContent.trim() : "Scrollable table");
        }
        if (!hint) {
          hint = document.createElement("p");
          hint.className = "table-wrap__hint";
          // aria-hidden: screen-reader users already hear the wrapper's
          // role and label; this line is the sighted-user equivalent.
          hint.setAttribute("aria-hidden", "true");
          hint.textContent = "This table scrolls sideways →";
          wrap.insertBefore(hint, wrap.firstChild);
        }
      } else {
        wrap.removeAttribute("tabindex");
        wrap.removeAttribute("role");
        wrap.removeAttribute("aria-label");
        if (hint) hint.remove();
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
