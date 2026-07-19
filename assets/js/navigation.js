// Site chrome navigation present on every page: the mobile contents
// disclosure, the mobile header-search disclosure, Escape-to-close for the
// Page tools menu, the back-to-top visibility toggle, and the contents
// sidebar's active-subsection scroll-spy. Bundled into the main script.
(function () {
  "use strict";

  // ---------- Mobile contents disclosure ----------
  // A plain in-flow disclosure: the Contents bar sits directly above the
  // panel it expands, so focus stays on the button when it opens — the
  // panel is the very next thing in reading order. Escape closes and
  // keeps focus on the button.
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
  // On narrow screens the header search collapses to a magnifier icon
  // button (CSS shows it only with .js); tapping it opens the form
  // full-width and moves focus into the input. Escape closes and hands
  // focus back. Without JavaScript the plain form is always visible.
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

  // ---------- Page tools menu ----------
  // Native details/summary opens/closes on its own; this only adds
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

  // ---------- Contents sidebar: active subsection highlight ----------
  // Scroll-spy: the active heading is the last one whose top has scrolled
  // past a fixed line near the top of the viewport. Simpler and more
  // reliable than IntersectionObserver threshold-crossing here, since
  // headings can be far apart (long sections) and a narrow observer band
  // can end up with nothing "visible" between them. Throttled to one
  // update per animation frame, with a passive scroll listener.
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
