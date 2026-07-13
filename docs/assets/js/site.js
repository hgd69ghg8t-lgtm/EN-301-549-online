(function () {
  "use strict";

  // ---------- Mobile contents toggle ----------
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

  // ---------- Toolbar: print / copy link ----------
  var printBtn = document.querySelector("[data-action='print']");
  if (printBtn) {
    printBtn.addEventListener("click", function () { window.print(); });
  }
  var copyBtn = document.querySelector("[data-action='copy-link']");
  if (copyBtn) {
    var copyLabel = copyBtn.querySelector(".doc-toolbar__btn-label");
    copyBtn.addEventListener("click", function () {
      navigator.clipboard.writeText(window.location.href).then(function () {
        if (copyLabel) {
          var original = copyLabel.textContent;
          copyLabel.textContent = "Link copied!";
          setTimeout(function () { copyLabel.textContent = original; }, 2000);
        }
      });
    });
  }

  // ---------- Back to top ----------
  var backToTop = document.querySelector(".back-to-top");
  if (backToTop) {
    window.addEventListener("scroll", function () {
      if (window.scrollY > 400) {
        backToTop.classList.add("is-visible");
      } else {
        backToTop.classList.remove("is-visible");
      }
    }, { passive: true });
    backToTop.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
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
