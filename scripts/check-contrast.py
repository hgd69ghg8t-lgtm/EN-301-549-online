#!/usr/bin/env python3
"""Verify WCAG contrast for the site's light and dark themes.

The palettes are parsed straight from assets/css/style.css (and the
favicon's from assets/img/favicon.svg), so this checker cannot drift
from the values actually shipped. It fails when:

  * a required token is missing or not a 6-digit hex colour,
  * the OS dark palette (inside the prefers-color-scheme media query) and
    the explicit [data-theme="dark"] palette are not identical, or
  * any of the colour pairings listed in pairs() falls below its WCAG 2.2
    AA threshold (4.5:1 text, 3:1 UI components/focus indicators).

Scope is deliberately explicit: the pairings below are the combinations
the design actually produces, maintained by hand alongside the CSS — not
an automatic sweep of every possible combination. Stdlib only. Runs via
npm test and as its own CI step.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS_PATH = ROOT / "assets" / "css" / "style.css"
FAVICON_PATH = ROOT / "assets" / "img" / "favicon.svg"

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
DECL_RE = re.compile(r"(--[a-z-]+)\s*:\s*([^;]+);")

problems = []


def srgb(channel):
    channel /= 255
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def luminance(hex_colour):
    hex_colour = hex_colour.lstrip("#")
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * srgb(r) + 0.7152 * srgb(g) + 0.0722 * srgb(b)


def ratio(fg, bg):
    l1, l2 = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def strip_media_print(css):
    """Remove @media print blocks so their forced-light palette is never
    mistaken for the screen palettes."""
    out = []
    i = 0
    while True:
        at = css.find("@media print", i)
        if at == -1:
            out.append(css[i:])
            break
        out.append(css[i:at])
        brace = css.index("{", at)
        depth = 1
        j = brace + 1
        while depth and j < len(css):
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
            j += 1
        i = j
    return "".join(out)


def block_after(css, header_regex, label):
    """The declaration text of the first CSS block whose opening matches
    header_regex (brace-balanced, so nested blocks stay intact)."""
    m = re.search(header_regex, css)
    if not m:
        problems.append(f"could not find the {label} block in style.css")
        return ""
    brace = css.index("{", m.end() - 1)
    depth = 1
    j = brace + 1
    while depth and j < len(css):
        if css[j] == "{":
            depth += 1
        elif css[j] == "}":
            depth -= 1
        j += 1
    return css[brace + 1:j - 1]


def tokens_in(block_text, label):
    found = {}
    for name, value in DECL_RE.findall(block_text):
        value = value.strip()
        if HEX_RE.match(value):
            found[name.replace("--colour-", "").replace("--guidance-", "guidance-")] = value.lower()
    if not found:
        problems.append(f"no hex colour tokens found in the {label} block")
    return found


css = strip_media_print(CSS_PATH.read_text(encoding="utf-8"))

light_root = tokens_in(block_after(css, r":root \{", "light :root"), "light :root")
media_dark = tokens_in(
    block_after(
        block_after(css, r"@media \(prefers-color-scheme: dark\) \{", "dark media query"),
        r':root:not\(\[data-theme="light"\]\) \{', "OS dark :root"),
    "OS dark :root")
explicit_dark = tokens_in(block_after(css, r'\n:root\[data-theme="dark"\] \{', "explicit dark :root"),
                          "explicit dark :root")

guidance_light = tokens_in(block_after(css, r"\n\.companion-guidance \{", "guidance light"), "guidance light")
guidance_media_dark = tokens_in(
    block_after(css, r':root:not\(\[data-theme="light"\]\) \.companion-guidance \{', "guidance OS dark"),
    "guidance OS dark")
guidance_explicit_dark = tokens_in(
    block_after(css, r'\n:root\[data-theme="dark"\] \.companion-guidance \{', "guidance explicit dark"),
    "guidance explicit dark")

# The two dark palettes must be byte-for-byte the same set of colours —
# CSS forces the duplication, this stops it drifting.
if media_dark and explicit_dark and media_dark != explicit_dark:
    problems.append("site dark palettes differ between the media query and [data-theme=dark] blocks: "
                    + str(sorted(set(media_dark.items()) ^ set(explicit_dark.items()))))
if guidance_media_dark and guidance_explicit_dark and guidance_media_dark != guidance_explicit_dark:
    problems.append("companion-guidance dark palettes differ between the media query and "
                    "[data-theme=dark] blocks")

REQUIRED = [
    "text", "background", "heading", "muted", "border", "border-strong",
    "link", "link-hover", "focus-default", "header-bg",
    "panel-bg", "note-bg", "note-border", "table-header-bg",
    "brand-navy", "brand-blue", "accent-bar", "site-header-bg",
]
# Fixed across themes, declared once in :root and deliberately absent
# from the dark blocks.
REQUIRED_LIGHT_ONLY = ["nav-hover-bg", "nav-current-bg", "on-yellow", "focus-yellow",
                       "doc-header-bg", "doc-header-muted", "toolbar-btn-bg"]
for name in REQUIRED:
    for palette, label in ((light_root, "light"), (media_dark, "OS dark"), (explicit_dark, "explicit dark")):
        if palette and name not in palette:
            problems.append(f"required token --colour-{name} missing from the {label} palette")
for name in REQUIRED_LIGHT_ONLY:
    if light_root and name not in light_root:
        problems.append(f"required fixed token --colour-{name} missing from :root")

GUIDANCE_REQUIRED = ["guidance-slate", "guidance-mid-grey", "guidance-light-grey",
                     "guidance-link", "guidance-link-active", "guidance-focus", "guidance-bg"]
for name in GUIDANCE_REQUIRED:
    for palette, label in ((guidance_light, "light"), (guidance_media_dark, "OS dark")):
        if palette and name not in palette:
            problems.append(f"required token --{name.replace('guidance-', 'guidance-')} missing "
                            f"from the guidance {label} palette")

# Favicon: base classes and their dark overrides, parsed from the SVG.
svg = FAVICON_PATH.read_text(encoding="utf-8")
def favicon_palette(text, label):
    colours = {}
    for cls, prop in (("background", "fill"), ("document", "stroke"), ("lines", "stroke")):
        m = re.search(r"\." + cls + r"\s*\{\s*" + prop + r":\s*(#[0-9a-fA-F]{6})", text)
        if m:
            colours[cls] = m.group(1).lower()
        else:
            problems.append(f"favicon {label}: no {prop} for .{cls}")
    return colours
dark_at = svg.find("@media (prefers-color-scheme: dark)")
if dark_at == -1:
    problems.append("favicon.svg has no dark-scheme media query")
    favicon_light = favicon_palette(svg, "light")
    favicon_dark = {}
else:
    favicon_light = favicon_palette(svg[:dark_at], "light")
    favicon_dark = favicon_palette(svg[dark_at:], "dark")


def pairs(t, g, footer_bg):
    """(description, foreground, background, minimum). t = theme palette,
    g = guidance palette, both parsed from the CSS."""
    c = light_root  # fixed surfaces only ever declared in :root
    return [
        # running text and links on the page's own surfaces
        ("body text on page", t["text"], t["background"], 4.5),
        ("muted text on page", t["muted"], t["background"], 4.5),
        ("links on page", t["link"], t["background"], 4.5),
        ("hovered links on page", t["link-hover"], t["background"], 4.5),
        ("text on panel (incl. table captions, striped rows, reader options)", t["text"], t["panel-bg"], 4.5),
        ("muted text on panel", t["muted"], t["panel-bg"], 4.5),
        ("links on panel", t["link"], t["panel-bg"], 4.5),
        ("text on note tint (incl. target-heading highlight)", t["text"], t["note-bg"], 4.5),
        ("links on note tint (incl. current subsection, selected suggestion)", t["link"], t["note-bg"], 4.5),
        ("current-subsection border against note tint", t["link"], t["note-bg"], 3.0),
        ("note/callout border against page", t["note-border"], t["background"], 3.0),
        # header brand
        ("wordmark on header", t["brand-navy"], t["header-bg"], 4.5),
        ("wordmark accent on header", t["brand-blue"], t["header-bg"], 4.5),
        # focus indicators on theme-following surfaces
        ("focus ring on page (incl. page-tools panel items)", t["focus-default"], t["background"], 3.0),
        ("focus ring on panel (incl. reader options)", t["focus-default"], t["panel-bg"], 3.0),
        ("focus ring on header", t["focus-default"], t["header-bg"], 3.0),
        # control boundaries
        ("input border on header", t["border-strong"], t["header-bg"], 3.0),
        ("control borders on panel (reader options)", t["border-strong"], t["panel-bg"], 3.0),
        ("scrollbar thumb against its track", t["border-strong"], t["panel-bg"], 3.0),
        ("panel border (page tools/suggestions) against page", t["link"], t["background"], 3.0),
        # fixed white-text surfaces
        ("white on table header", "#ffffff", t["table-header-bg"], 4.5),
        ("white on accent/search button", "#ffffff", t["accent-bar"], 4.5),
        ("white on current-page row", "#ffffff", c["nav-current-bg"], 4.5),
        ("white on hover row / contents bar", "#ffffff", c["nav-hover-bg"], 4.5),
        ("white on title band", "#ffffff", c["doc-header-bg"], 4.5),
        ("white on band button", "#ffffff", c["toolbar-btn-bg"], 4.5),
        ("band muted text", c["doc-header-muted"], c["doc-header-bg"], 4.5),
        ("yellow focus on title band", c["focus-yellow"], c["doc-header-bg"], 3.0),
        # yellow surfaces
        ("on-yellow ink (skip link, marks)", c["on-yellow"], c["focus-yellow"], 4.5),
        ("skip-link focus outline against yellow", c["on-yellow"], c["focus-yellow"], 3.0),
        # footer
        ("footer links", "#d3d3d3", footer_bg, 4.5),
        ("white on footer", "#ffffff", footer_bg, 4.5),
        # companion guidance
        ("guidance text", g["guidance-slate"], g["guidance-bg"], 4.5),
        ("guidance muted", g["guidance-mid-grey"], g["guidance-bg"], 4.5),
        ("guidance links", g["guidance-link"], g["guidance-bg"], 4.5),
        ("guidance hovered/active title", g["guidance-link-active"], g["guidance-bg"], 4.5),
        ("guidance focus ring", g["guidance-focus"], g["guidance-bg"], 3.0),
        ("guidance border against page", g["guidance-light-grey"], t["background"], 1.2),
    ]


failures = list(problems)
checked = 0
if not problems:
    themes = (
        ("light", light_root, guidance_light, light_root["site-header-bg"]),
        ("dark", {**light_root, **media_dark}, {**guidance_light, **guidance_media_dark},
         media_dark["site-header-bg"]),
    )
    for name, t, g, footer_bg in themes:
        for desc, fg, bg, minimum in pairs(t, g, footer_bg):
            checked += 1
            r = ratio(fg, bg)
            if r < minimum:
                failures.append(f"{name}: {desc} — {fg} on {bg} = {r:.2f}:1 (needs {minimum}:1)")
    # favicon: foreground/background distinction is a graphic, 3:1
    for name, pal in (("light", favicon_light), ("dark", favicon_dark)):
        for cls in ("document", "lines"):
            if cls in pal and "background" in pal:
                checked += 1
                r = ratio(pal[cls], pal["background"])
                if r < 3.0:
                    failures.append(f"favicon {name}: .{cls} {pal[cls]} on {pal['background']} "
                                    f"= {r:.2f}:1 (needs 3.0:1)")

if failures:
    print("Contrast/palette failures:")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print(f"Palettes parsed from CSS and favicon; dark blocks identical; "
      f"{checked} listed colour pairings meet their WCAG thresholds.")
