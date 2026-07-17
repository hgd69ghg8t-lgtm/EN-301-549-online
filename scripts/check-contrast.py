#!/usr/bin/env python3
"""Verify the WCAG contrast of every meaningful colour pair in BOTH themes.

The pairs below mirror how the tokens are actually used in
docs/assets/css/style.css — text-on-surface pairs need >= 4.5:1
(WCAG 1.4.3), UI-component/focus pairs need >= 3:1 (1.4.11). Exits
non-zero listing any failure. Run directly, or via npm test.
"""
import sys


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


LIGHT = {
    "text": "#1a1a1a", "background": "#ffffff", "muted": "#505a5f",
    "link": "#005ea2", "link-hover": "#003d6e", "focus-dark": "#1a1a1a",
    "header-bg": "#ffffff", "brand-navy": "#14245a", "brand-blue": "#2472dd",
    "panel-bg": "#f3f2f1", "note-bg": "#e8f1fa", "table-header-bg": "#1a1a1a",
    "accent-bar": "#005ea2", "border-strong": "#7d848a",
    "guidance-slate": "#2a2a2a", "guidance-mid-grey": "#595959",
    "guidance-link": "#005dbb", "guidance-bg": "#ffffff", "guidance-focus": "#b53cde",
}
DARK = {
    "text": "#e8e9eb", "background": "#16191d", "muted": "#a9b1b8",
    "link": "#8fbdf5", "link-hover": "#b8d6fa", "focus-dark": "#ffdd00",
    "header-bg": "#1b1f24", "brand-navy": "#dbe6ff", "brand-blue": "#6ea8fe",
    "panel-bg": "#22262c", "note-bg": "#1c2a3a", "table-header-bg": "#272b30",
    "accent-bar": "#1d70b8", "border-strong": "#6a727b",
    "guidance-slate": "#e4e6e8", "guidance-mid-grey": "#a9b1b8",
    "guidance-link": "#8fbdf5", "guidance-bg": "#1b1f24", "guidance-focus": "#d78ef2",
}
CONSTANT = {
    "white": "#ffffff", "yellow": "#ffdd00", "dark-ink": "#1a1a1a",
    "doc-header-bg": "#003d6e", "doc-header-muted": "#9ecae5",
    "toolbar-btn-bg": "#004b86", "nav-hover-bg": "#003d6e",
    "nav-current-bg": "#005ea2", "site-footer-bg-light": "#1a1a1a",
    "site-footer-bg-dark": "#0e1013", "footer-link": "#d3d3d3",
}

# (description, foreground, background, minimum ratio)
def pairs(theme, footer_bg):
    t = lambda k: theme[k]
    c = lambda k: CONSTANT[k]
    return [
        ("body text on page", t("text"), t("background"), 4.5),
        ("muted text on page", t("muted"), t("background"), 4.5),
        ("links on page", t("link"), t("background"), 4.5),
        ("hovered links on page", t("link-hover"), t("background"), 4.5),
        ("links on panel", t("link"), t("panel-bg"), 4.5),
        ("text on panel", t("text"), t("panel-bg"), 4.5),
        ("muted text on panel", t("muted"), t("panel-bg"), 4.5),
        ("text on note tint", t("text"), t("note-bg"), 4.5),
        ("links on note tint", t("link"), t("note-bg"), 4.5),
        ("wordmark on header", t("brand-navy"), t("header-bg"), 4.5),
        ("wordmark accent on header", t("brand-blue"), t("header-bg"), 4.5),
        ("focus ring on page", t("focus-dark"), t("background"), 3.0),
        ("focus ring on panel", t("focus-dark"), t("panel-bg"), 3.0),
        ("input border on header", t("border-strong"), t("header-bg"), 3.0),
        ("white on table header", c("white"), t("table-header-bg"), 4.5),
        ("white on accent/search button", c("white"), t("accent-bar"), 4.5),
        ("white on current-page row", c("white"), c("nav-current-bg"), 4.5),
        ("white on hover row / contents bar", c("white"), c("nav-hover-bg"), 4.5),
        ("white on title band", c("white"), c("doc-header-bg"), 4.5),
        ("white on band button", c("white"), c("toolbar-btn-bg"), 4.5),
        ("band muted text", c("doc-header-muted"), c("doc-header-bg"), 4.5),
        ("yellow focus on title band", c("yellow"), c("doc-header-bg"), 3.0),
        ("dark ink on yellow mark/skip-link", c("dark-ink"), c("yellow"), 4.5),
        ("footer links", c("footer-link"), footer_bg, 4.5),
        ("white on footer", c("white"), footer_bg, 4.5),
        ("guidance text", t("guidance-slate"), t("guidance-bg"), 4.5),
        ("guidance muted", t("guidance-mid-grey"), t("guidance-bg"), 4.5),
        ("guidance links", t("guidance-link"), t("guidance-bg"), 4.5),
        ("guidance focus ring", t("guidance-focus"), t("guidance-bg"), 3.0),
    ]


failures = []
for name, theme, footer in (("light", LIGHT, CONSTANT["site-footer-bg-light"]),
                            ("dark", DARK, CONSTANT["site-footer-bg-dark"])):
    for desc, fg, bg, minimum in pairs(theme, footer):
        r = ratio(fg, bg)
        if r < minimum:
            failures.append(f"{name}: {desc} — {fg} on {bg} = {r:.2f}:1 (needs {minimum}:1)")

if failures:
    print("Contrast failures:")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print(f"All {2 * len(pairs(LIGHT, '#1a1a1a'))} theme colour pairs meet their WCAG thresholds.")
