"""Markup, styles and the inline application script for the offline report."""

from __future__ import annotations

import json

from nhi_blast.core.completeness import FAMILY_LABELS
from nhi_blast.report.effects import EFFECTS_CSS

# Theme model (docs/release/v0.3.0-plan/11-ui-direction.md, section G5): the effective theme lives
# on <html data-theme="light|dark">, the user's choice on data-theme-choice="system|light|dark".
# Every palette is one mapping with the same keys, so the CSS blocks cannot drift apart. Keys in
# _DP_NAMES become the owner design-system properties (--dp-*); the others are plain tokens.
# Old selectors keep working through the mapping block below. A "passage" is one of the two dark
# bands of the page; it re-declares the palette for everything inside it.
_DP_NAMES = frozenset(
    {
        "ground",
        "ground-muted",
        "panel",
        "raised",
        "hover",
        "rule",
        "rule-strong",
        "ink",
        "ink-secondary",
        "ink-muted",
        "accent",
        "accent-hover",
        "accent-soft",
        "on-accent",
        "field",
        "on-field",
        "on-field-secondary",
    }
)

_PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "ground": "#fcfcfd",
        "ground-muted": "#f3f4f6",
        "panel": "#ffffff",
        "raised": "#e8eaee",
        "hover": "#e2e5ea",
        "rule": "#dde0e6",
        "rule-strong": "#7d8595",
        "ink": "#16191f",
        "ink-secondary": "#454c58",
        "ink-muted": "#596171",
        "accent": "#074ce0",
        "accent-hover": "#053ab5",
        "accent-soft": "#e6edff",
        "on-accent": "#ffffff",
        "field": "#16191f",
        "on-field": "#fcfcfd",
        "on-field-secondary": "#d0d4dd",
        "critical": "#a8201a",
        "critical-ink": "#7c1712",
        "critical-soft": "#fdecea",
        "high": "#8a4a12",
        "high-ink": "#6f3a0c",
        "high-soft": "#fdf0e0",
        "warning": "#6e5200",
        "warning-ink": "#5a4300",
        "warning-soft": "#faf2d4",
        "low": "#4a505b",
        "low-ink": "#3a404a",
        "low-soft": "#eef0f3",
        "positive": "#1f6b43",
        "neutral-ink": "#3a404a",
        "neutral-soft": "#eef0f3",
        "R": "#3a404a",
        "E": "#a8770f",
        "Z": "#a8201a",
        "graph-edge": "#4b5260",
        "node-structure": "#5d6573",
        "node-workflow": "#272c35",
        "node-oidc": "#4a5568",
        "node-role": "#5a6070",
        "node-sink": "#6b7280",
        "node-credential": "#3f4652",
        "node-fill": "#ffffff",
        "selection-bg": "rgba(7, 76, 224, .16)",
        "shadow-card": "0 1px 2px rgba(22, 25, 31, .05), 0 12px 28px -16px rgba(22, 25, 31, .2)",
        "shadow-lift": "0 2px 4px rgba(22, 25, 31, .06), 0 10px 20px -12px rgba(22, 25, 31, .28)",
        "pill-border-critical": "rgba(168, 32, 26, .4)",
        "pill-border-high": "rgba(138, 74, 18, .4)",
        "pill-border-warning": "rgba(110, 82, 0, .4)",
        "pill-border-low": "rgba(74, 80, 91, .32)",
        "pill-border-info": "rgba(58, 64, 74, .28)",
        "seg-e-stripe": "#f4e7bd",
        "grid-dot": "rgba(22, 25, 31, .09)",
        "fx-ink": "#16191f",
        "fx-alpha": ".14",
        "fx-spot": "rgba(7, 76, 224, .07)",
        "hero-from": "#16191f",
        "hero-to": "#666666",
        "nav-surface": "rgba(255, 255, 255, .74)",
        "nav-panel": "rgba(252, 252, 253, .94)",
    },
    "dark": {
        "ground": "#0e1116",
        "ground-muted": "#151922",
        "panel": "#181c24",
        "raised": "#202632",
        "hover": "#272e3b",
        "rule": "#2a303b",
        "rule-strong": "#6b7588",
        "ink": "#f3f5f8",
        "ink-secondary": "#b4bcc9",
        "ink-muted": "#9aa3b2",
        "accent": "#6f9bff",
        "accent-hover": "#92b3ff",
        "accent-soft": "#17233f",
        "on-accent": "#0b1020",
        "field": "#07090d",
        "on-field": "#f3f5f8",
        "on-field-secondary": "#b4bcc9",
        "critical": "#ff6b5e",
        "critical-ink": "#ff9a90",
        "critical-soft": "#2d1613",
        "high": "#f3a06a",
        "high-ink": "#f5ad7e",
        "high-soft": "#2a1b13",
        "warning": "#e9b665",
        "warning-ink": "#efc37c",
        "warning-soft": "#2a2114",
        "low": "#b4bcc9",
        "low-ink": "#c5ccd7",
        "low-soft": "#1f242d",
        "positive": "#75c99a",
        "neutral-ink": "#b4bcc9",
        "neutral-soft": "#1f242d",
        "R": "#b4bcc9",
        "E": "#e9b665",
        "Z": "#ff6b5e",
        "graph-edge": "#7a8394",
        "node-structure": "#8a93a3",
        "node-workflow": "#c9d0db",
        "node-oidc": "#b3bdd0",
        "node-role": "#9fa9bd",
        "node-sink": "#8f98a9",
        "node-credential": "#d3d9e3",
        "node-fill": "#10141b",
        "selection-bg": "rgba(111, 155, 255, .32)",
        "shadow-card": "0 1px 2px rgba(0, 0, 0, .35), 0 14px 30px -18px rgba(0, 0, 0, .8)",
        "shadow-lift": "0 2px 4px rgba(0, 0, 0, .4), 0 12px 24px -14px rgba(0, 0, 0, .85)",
        "pill-border-critical": "rgba(255, 107, 94, .45)",
        "pill-border-high": "rgba(243, 160, 106, .4)",
        "pill-border-warning": "rgba(233, 182, 101, .36)",
        "pill-border-low": "rgba(180, 188, 201, .32)",
        "pill-border-info": "rgba(180, 188, 201, .26)",
        "seg-e-stripe": "#57431f",
        "grid-dot": "rgba(243, 245, 248, .07)",
        "fx-ink": "#dbe0eb",
        "fx-alpha": ".16",
        "fx-spot": "rgba(111, 155, 255, .12)",
        "hero-from": "#ffffff",
        "hero-to": "#9b9b9b",
        "nav-surface": "rgba(24, 28, 36, .72)",
        "nav-panel": "rgba(14, 17, 22, .94)",
    },
    "passage-light": {
        "ground": "#16191f",
        "ground-muted": "#1d222b",
        "panel": "#1e232c",
        "raised": "#2a3140",
        "hover": "#323a4a",
        "rule": "#333b49",
        "rule-strong": "#7f899c",
        "ink": "#fcfcfd",
        "ink-secondary": "#d0d4dd",
        "ink-muted": "#aeb6c4",
        "accent": "#7fa8ff",
        "accent-hover": "#a2c0ff",
        "accent-soft": "#1a2748",
        "on-accent": "#0b1020",
        "field": "#16191f",
        "on-field": "#fcfcfd",
        "on-field-secondary": "#d0d4dd",
        "critical": "#ff6b5e",
        "critical-ink": "#ff9a90",
        "critical-soft": "#32191a",
        "high": "#f3a06a",
        "high-ink": "#f5ad7e",
        "high-soft": "#2f2016",
        "warning": "#e9b665",
        "warning-ink": "#efc37c",
        "warning-soft": "#2c2416",
        "low": "#c5ccd7",
        "low-ink": "#d0d4dd",
        "low-soft": "#262c37",
        "positive": "#75c99a",
        "neutral-ink": "#d0d4dd",
        "neutral-soft": "#262c37",
        "R": "#d0d4dd",
        "E": "#e9b665",
        "Z": "#ff6b5e",
        "graph-edge": "#8a93a3",
        "node-structure": "#9aa3b2",
        "node-workflow": "#d0d4dd",
        "node-oidc": "#b3bdd0",
        "node-role": "#a8b1c2",
        "node-sink": "#9aa3b2",
        "node-credential": "#d3d9e3",
        "node-fill": "#1a1f27",
        "selection-bg": "rgba(127, 168, 255, .34)",
        "shadow-card": "none",
        "shadow-lift": "none",
        "pill-border-critical": "rgba(255, 107, 94, .45)",
        "pill-border-high": "rgba(243, 160, 106, .4)",
        "pill-border-warning": "rgba(233, 182, 101, .36)",
        "pill-border-low": "rgba(180, 188, 201, .32)",
        "pill-border-info": "rgba(180, 188, 201, .26)",
        "seg-e-stripe": "#57431f",
        "grid-dot": "rgba(243, 245, 248, .07)",
        "fx-ink": "#dbe0eb",
        "fx-alpha": ".16",
        "fx-spot": "rgba(127, 168, 255, .14)",
        "hero-from": "#ffffff",
        "hero-to": "#9b9b9b",
        "nav-surface": "rgba(30, 35, 44, .72)",
        "nav-panel": "rgba(22, 25, 31, .94)",
    },
    "passage-dark": {
        "ground": "#07090d",
        "ground-muted": "#0c0f15",
        "panel": "#0f1319",
        "raised": "#171c25",
        "hover": "#1e2430",
        "rule": "#242b36",
        "rule-strong": "#6b7588",
        "ink": "#f3f5f8",
        "ink-secondary": "#b4bcc9",
        "ink-muted": "#9aa3b2",
        "accent": "#6f9bff",
        "accent-hover": "#92b3ff",
        "accent-soft": "#111b33",
        "on-accent": "#0b1020",
        "field": "#07090d",
        "on-field": "#f3f5f8",
        "on-field-secondary": "#b4bcc9",
        "critical": "#ff6b5e",
        "critical-ink": "#ff9a90",
        "critical-soft": "#2a1513",
        "high": "#f3a06a",
        "high-ink": "#f5ad7e",
        "high-soft": "#251a12",
        "warning": "#e9b665",
        "warning-ink": "#efc37c",
        "warning-soft": "#251f13",
        "low": "#b4bcc9",
        "low-ink": "#c5ccd7",
        "low-soft": "#181d26",
        "positive": "#75c99a",
        "neutral-ink": "#b4bcc9",
        "neutral-soft": "#181d26",
        "R": "#b4bcc9",
        "E": "#e9b665",
        "Z": "#ff6b5e",
        "graph-edge": "#7a8394",
        "node-structure": "#8a93a3",
        "node-workflow": "#c9d0db",
        "node-oidc": "#b3bdd0",
        "node-role": "#9fa9bd",
        "node-sink": "#8f98a9",
        "node-credential": "#d3d9e3",
        "node-fill": "#0b0e14",
        "selection-bg": "rgba(111, 155, 255, .32)",
        "shadow-card": "none",
        "shadow-lift": "none",
        "pill-border-critical": "rgba(255, 107, 94, .45)",
        "pill-border-high": "rgba(243, 160, 106, .4)",
        "pill-border-warning": "rgba(233, 182, 101, .36)",
        "pill-border-low": "rgba(180, 188, 201, .32)",
        "pill-border-info": "rgba(180, 188, 201, .26)",
        "seg-e-stripe": "#57431f",
        "grid-dot": "rgba(243, 245, 248, .07)",
        "fx-ink": "#dbe0eb",
        "fx-alpha": ".12",
        "fx-spot": "rgba(111, 155, 255, .12)",
        "hero-from": "#ffffff",
        "hero-to": "#9b9b9b",
        "nav-surface": "rgba(15, 19, 25, .72)",
        "nav-panel": "rgba(7, 9, 13, .94)",
    },
    "print": {
        "ground": "#ffffff",
        "ground-muted": "#f4f4f5",
        "panel": "#ffffff",
        "raised": "#ececee",
        "hover": "#ffffff",
        "rule": "#b7bcc6",
        "rule-strong": "#6b7280",
        "ink": "#16191f",
        "ink-secondary": "#454c58",
        "ink-muted": "#596171",
        "accent": "#074ce0",
        "accent-hover": "#053ab5",
        "accent-soft": "#e6edff",
        "on-accent": "#ffffff",
        "field": "#ffffff",
        "on-field": "#16191f",
        "on-field-secondary": "#454c58",
        "critical": "#a8201a",
        "critical-ink": "#7c1712",
        "critical-soft": "#fdecea",
        "high": "#8a4a12",
        "high-ink": "#6f3a0c",
        "high-soft": "#fdf0e0",
        "warning": "#6e5200",
        "warning-ink": "#5a4300",
        "warning-soft": "#faf2d4",
        "low": "#4a505b",
        "low-ink": "#3a404a",
        "low-soft": "#eef0f3",
        "positive": "#1f6b43",
        "neutral-ink": "#3a404a",
        "neutral-soft": "#eef0f3",
        "R": "#3a404a",
        "E": "#a8770f",
        "Z": "#a8201a",
        "graph-edge": "#4b5260",
        "node-structure": "#5d6573",
        "node-workflow": "#272c35",
        "node-oidc": "#4a5568",
        "node-role": "#5a6070",
        "node-sink": "#6b7280",
        "node-credential": "#3f4652",
        "node-fill": "#ffffff",
        "selection-bg": "rgba(7, 76, 224, .16)",
        "shadow-card": "none",
        "shadow-lift": "none",
        "pill-border-critical": "rgba(168, 32, 26, .4)",
        "pill-border-high": "rgba(138, 74, 18, .4)",
        "pill-border-warning": "rgba(110, 82, 0, .4)",
        "pill-border-low": "rgba(74, 80, 91, .32)",
        "pill-border-info": "rgba(58, 64, 74, .28)",
        "seg-e-stripe": "#f3e6c8",
        "grid-dot": "transparent",
        "fx-ink": "#16191f",
        "fx-alpha": "0",
        "fx-spot": "transparent",
        "hero-from": "#16191f",
        "hero-to": "#16191f",
        "nav-surface": "rgba(255, 255, 255, 1)",
        "nav-panel": "rgba(255, 255, 255, 1)",
    },
}

_SHARED_TOKENS_CSS = """:root {
  --dp-gap: 24px;
  --dp-hairline: 1px;
  --dp-radius-panel: 12px;
  --dp-motion: 300ms cubic-bezier(.22, 1, .36, 1);
  --r-panel: var(--dp-radius-panel);
  --r-card: var(--dp-radius-panel);
  --r-banner: var(--dp-radius-panel);
  --r-control: 10px;
  --r-button: 8px;
  --r-badge: 6px;
  --r-pill: 999px;
  --dur-1: 200ms;
  --dur-2: 300ms;
  --dur-3: 500ms;
  --ease: cubic-bezier(.22, 1, .36, 1);
  --ease-out: cubic-bezier(.22, 1, .36, 1);
  --fs-body: 16px;
  --fs-ui: 15px;
  --fs-small: 14px;
  --fs-meta: 13px;
  --fs-label: 12px;
  --sans: "Instrument Sans", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  --display: "Host Grotesk", "Instrument Sans", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: "Geist Mono", ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
}"""

_TOKEN_MAPPING_CSS = """:root, .passage {
  --bg: var(--dp-ground);
  --header: var(--dp-ground);
  --surface: var(--dp-panel);
  --surface-2: var(--dp-ground-muted);
  --raised: var(--dp-raised);
  --hover: var(--dp-hover);
  --border: var(--dp-rule);
  --border-strong: var(--dp-rule-strong);
  --ink: var(--dp-ink);
  --ink-2: var(--dp-ink-secondary);
  --muted: var(--dp-ink-muted);
  --accent: var(--dp-accent);
  --accent-hover: var(--dp-accent-hover);
  --accent-ink: var(--dp-on-accent);
  --accent-soft: var(--dp-accent-soft);
  --focus: var(--dp-accent);
  --fx-blue: var(--dp-accent);
  --fx-rule: var(--dp-rule-strong);
  --fx-ground: var(--dp-ground);
  --fx-dot: var(--fx-ink);
  --fx-accent: var(--dp-accent);
  --fx-spot-color: var(--fx-spot);
}"""


def _property(key: str) -> str:
    return f"--dp-{key}" if key in _DP_NAMES else f"--{key}"


def _declarations(values: dict[str, str], indent: str = "  ") -> str:
    return "\n".join(f"{indent}{_property(key)}: {value};" for key, value in values.items())


def _block(selector: str, scheme: str, palette: str) -> str:
    return f"{selector} {{\n  color-scheme: {scheme};\n{_declarations(_PALETTES[palette])}\n}}"


_ALL_ROOTS = ":root, :root[data-theme], :root .passage, :root[data-theme] .passage"
_SYSTEM_COLOURS = {
    "ground": "Canvas",
    "ground-muted": "Canvas",
    "panel": "Canvas",
    "raised": "Canvas",
    "hover": "Canvas",
    "rule": "CanvasText",
    "rule-strong": "CanvasText",
    "ink": "CanvasText",
    "ink-secondary": "CanvasText",
    "ink-muted": "CanvasText",
    "accent": "Highlight",
    "accent-hover": "Highlight",
    "accent-soft": "Canvas",
    "on-accent": "HighlightText",
    "field": "Canvas",
    "on-field": "CanvasText",
    "on-field-secondary": "CanvasText",
}


def _forced_colours() -> str:
    lines = []
    for key in _PALETTES["light"]:
        name = _property(key)
        if key in _SYSTEM_COLOURS:
            value = _SYSTEM_COLOURS[key]
        elif key.endswith("-soft") or key in {"node-fill"}:
            value = "Canvas"
        elif key in {"selection-bg"}:
            value = "Highlight"
        elif key in {"shadow-card", "shadow-lift"}:
            value = "none"
        elif key in {"grid-dot", "seg-e-stripe"}:
            value = "transparent"
        elif key == "fx-alpha":
            value = "0"
        elif key in {"nav-surface", "nav-panel"}:
            value = "Canvas"
        elif key == "fx-spot":
            value = "transparent"
        elif key.startswith("pill-border"):
            value = "CanvasText"
        else:
            value = "CanvasText"
        lines.append(f"    {name}: {value};")
    body = "\n".join(lines)
    return (
        "@media (forced-colors: active) {\n"
        f"  {_ALL_ROOTS} {{\n    color-scheme: light dark;\n{body}\n  }}\n}}"
    )


_PRINT_TOKENS_CSS = (
    "@media print {\n"
    f"  {_ALL_ROOTS} {{\n    color-scheme: light;\n"
    f"{_declarations(_PALETTES['print'], '    ')}\n  }}\n}}"
)

THEME_TOKENS_CSS = "\n".join(
    (
        _SHARED_TOKENS_CSS,
        _block(':root, :root[data-theme="dark"]', "dark", "dark"),
        _block(':root[data-theme="light"]', "light", "light"),
        _block(':root .passage, :root[data-theme="dark"] .passage', "dark", "passage-dark"),
        _block(':root[data-theme="light"] .passage', "dark", "passage-light"),
        _TOKEN_MAPPING_CSS,
        _forced_colours(),
        _PRINT_TOKENS_CSS,
    )
)

THEME_SWITCH_CSS = """.theme-host { display: flex; flex: none; align-items: center; }
.theme-switch {
  display: inline-flex; align-items: center; gap: 2px; padding: 3px;
  border: 1px solid var(--border-strong); border-radius: var(--r-pill);
  background: var(--surface-2);
}
.theme-option {
  display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 12px;
  border: 0; border-radius: var(--r-pill);
  background: transparent; color: var(--muted);
  font-size: var(--fs-label); font-weight: 600; line-height: 1; cursor: pointer;
}
.theme-option:hover { background: var(--hover); color: var(--ink); }
.theme-option[aria-checked="true"] { background: var(--surface); color: var(--ink); box-shadow: inset 0 0 0 1px var(--border-strong); }
.theme-option:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.motion-switch {
  display: inline-flex; align-items: center; gap: 8px; height: 34px; padding: 0 12px 0 8px;
  border: 1px solid var(--border-strong); border-radius: var(--r-pill);
  background: var(--surface-2); color: var(--ink-2);
  font-size: var(--fs-label); font-weight: 600; line-height: 1; cursor: pointer;
}
.motion-switch:hover { background: var(--hover); color: var(--ink); }
.motion-switch:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.motion-track { position: relative; flex: none; width: 24px; height: 14px; border-radius: 999px; background: var(--border-strong); }
.motion-track::after { content: ""; position: absolute; top: 2px; left: 2px; width: 10px; height: 10px; border-radius: 50%; background: var(--surface); }
.motion-switch[aria-checked="true"] .motion-track { background: var(--accent); }
.motion-switch[aria-checked="true"] .motion-track::after { left: 12px; }
.motion-state { min-width: 20px; color: var(--ink); }
html[data-motion="on"] .motion-track, html[data-motion="on"] .motion-track::after { transition: background-color 140ms ease-out, left 140ms ease-out; }
.theme-icon { flex: none; width: 11px; height: 11px; border: 1.5px solid currentColor; border-radius: 50%; }
.theme-option[aria-checked="true"] .theme-icon { color: var(--accent); }
.theme-icon-system { background: linear-gradient(90deg, currentColor 50%, transparent 50%); }
.theme-icon-light { background: currentColor; }
html.theme-switching, html.theme-switching *, html.theme-switching *::before, html.theme-switching *::after {
  transition: background-color 200ms cubic-bezier(.22, 1, .36, 1), color 200ms cubic-bezier(.22, 1, .36, 1), border-color 200ms cubic-bezier(.22, 1, .36, 1), fill 200ms cubic-bezier(.22, 1, .36, 1), stroke 200ms cubic-bezier(.22, 1, .36, 1) !important;
}
@media (prefers-reduced-motion: reduce) {
  html.theme-switching, html.theme-switching *, html.theme-switching *::before, html.theme-switching *::after { transition: none !important; }
}
@media (pointer: coarse) {
  .theme-option { height: 36px; }
}
@media (forced-colors: active) {
  .motion-track { forced-color-adjust: none; background: ButtonText; }
  .motion-switch[aria-checked="true"] .motion-track { background: Highlight; }
  .theme-option[aria-checked="true"] { forced-color-adjust: none; background: Highlight; color: HighlightText; }
  .theme-option:focus-visible { outline-color: Highlight; }
}"""

THEME_JS = r"""(function () {
  "use strict";
  var KEY = "nhb-theme";
  var CHOICES = ["system", "light", "dark"];
  var LABELS = {system: "System", light: "Light", dark: "Dark"};
  var CHROME = {light: "#fcfcfd", dark: "#0e1116"};
  var root = document.documentElement;
  var memory = new Map();
  var subscribers = [];
  var timer = 0;

  function sessionStore() {
    try { return window.sessionStorage; } catch (error) { return null; }
  }
  var safeStorage = {
    get: function (key) {
      if (memory.has(key)) { return memory.get(key); }
      try {
        var store = sessionStore();
        return store ? store.getItem(key) : null;
      } catch (error) {
        return null;
      }
    },
    set: function (key, value) {
      memory.set(key, value);
      try {
        var store = sessionStore();
        if (store) { store.setItem(key, value); }
      } catch (error) {
        // Storage is a convenience; the in-memory copy keeps the choice for this page view.
      }
    }
  };

  function query(text) {
    try { return window.matchMedia ? window.matchMedia(text) : null; } catch (error) { return null; }
  }
  var lightQuery = query("(prefers-color-scheme: light)");
  var motionQuery = query("(prefers-reduced-motion: reduce)");

  var stored = safeStorage.get(KEY);
  var choice = CHOICES.indexOf(stored) >= 0 ? stored : "system";
  var MOTION_KEY = "nhb-motion";
  var motionStored = safeStorage.get(MOTION_KEY);
  var motionChoice = motionStored === "on" || motionStored === "off" ? motionStored : null;
  var motionOn = motionChoice ? motionChoice === "on" : !(motionQuery && motionQuery.matches);
  var motionSubscribers = [];

  function resolve() {
    if (choice === "light" || choice === "dark") { return choice; }
    return lightQuery && lightQuery.matches ? "light" : "dark";
  }

  function apply() {
    var theme = resolve();
    root.setAttribute("data-theme", theme);
    root.setAttribute("data-theme-choice", choice);
    root.setAttribute("data-motion", motionOn ? "on" : "off");
    var chrome = document.querySelector('meta[name="theme-color"]');
    if (chrome) { chrome.setAttribute("content", CHROME[theme]); }
    subscribers.forEach(function (notify) { notify(theme, choice); });
  }

  function setChoice(next) {
    if (CHOICES.indexOf(next) < 0) { return; }
    var before = root.getAttribute("data-theme");
    choice = next;
    safeStorage.set(KEY, next);
    var fx = window.NHBEffects;
    var viaEffects = motionOn && fx && typeof fx.transitionTheme === "function";
    if (resolve() !== before && motionOn && !viaEffects) {
      root.classList.add("theme-switching");
      window.clearTimeout(timer);
      timer = window.setTimeout(function () { root.classList.remove("theme-switching"); }, 260);
    }
    if (viaEffects) {
      fx.transitionTheme(apply, document.querySelector(".theme-switch"));
    } else {
      apply();
    }
  }

  function applyMotion(next) {
    motionOn = Boolean(next);
    root.setAttribute("data-motion", motionOn ? "on" : "off");
    var fx = window.NHBEffects;
    if (fx && typeof fx.setMotion === "function") { fx.setMotion(motionOn); }
    motionSubscribers.forEach(function (notify) { notify(motionOn); });
  }

  function setMotion(next) {
    motionChoice = next ? "on" : "off";
    safeStorage.set(MOTION_KEY, motionChoice);
    applyMotion(next);
  }

  function onSystemMotionChange() {
    if (motionChoice === null) { applyMotion(!(motionQuery && motionQuery.matches)); }
  }
  if (motionQuery) {
    if (typeof motionQuery.addEventListener === "function") {
      motionQuery.addEventListener("change", onSystemMotionChange);
    } else if (typeof motionQuery.addListener === "function") {
      motionQuery.addListener(onSystemMotionChange);
    }
  }

  function mountMotion(host) {
    if (!host) { return; }
    var button = document.createElement("button");
    button.setAttribute("type", "button");
    button.setAttribute("role", "switch");
    button.className = "motion-switch";
    var track = document.createElement("span");
    track.className = "motion-track";
    track.setAttribute("aria-hidden", "true");
    var label = document.createElement("span");
    label.className = "motion-label";
    label.textContent = "Motion";
    var state = document.createElement("span");
    state.className = "motion-state";
    button.appendChild(track);
    button.appendChild(label);
    button.appendChild(state);
    function sync() {
      button.setAttribute("aria-checked", motionOn ? "true" : "false");
      state.textContent = motionOn ? "On" : "Off";
    }
    button.addEventListener("click", function () { setMotion(!motionOn); });
    motionSubscribers.push(sync);
    sync();
    host.appendChild(button);
  }

  function onSystemChange() {
    if (choice === "system") { apply(); }
  }
  if (lightQuery) {
    if (typeof lightQuery.addEventListener === "function") {
      lightQuery.addEventListener("change", onSystemChange);
    } else if (typeof lightQuery.addListener === "function") {
      lightQuery.addListener(onSystemChange);
    }
  }

  function mount(host) {
    if (!host) { return; }
    var group = document.createElement("div");
    group.className = "theme-switch";
    group.setAttribute("role", "radiogroup");
    group.setAttribute("aria-label", "Colour theme");
    var options = CHOICES.map(function (value) {
      var button = document.createElement("button");
      button.setAttribute("type", "button");
      button.setAttribute("role", "radio");
      button.setAttribute("data-theme-value", value);
      button.className = "theme-option";
      var icon = document.createElement("span");
      icon.className = "theme-icon theme-icon-" + value;
      icon.setAttribute("aria-hidden", "true");
      var label = document.createElement("span");
      label.className = "theme-label";
      label.textContent = LABELS[value];
      button.appendChild(icon);
      button.appendChild(label);
      group.appendChild(button);
      return button;
    });
    function sync() {
      options.forEach(function (button) {
        var selected = button.getAttribute("data-theme-value") === choice;
        button.setAttribute("aria-checked", selected ? "true" : "false");
        button.setAttribute("tabindex", selected ? "0" : "-1");
      });
    }
    group.addEventListener("click", function (event) {
      var button = event.target && event.target.closest ? event.target.closest(".theme-option") : null;
      if (button && group.contains(button)) { setChoice(button.getAttribute("data-theme-value")); }
    });
    group.addEventListener("keydown", function (event) {
      var current = event.target && event.target.closest ? event.target.closest(".theme-option") : null;
      var index = options.indexOf(current);
      if (index < 0) { return; }
      var target = -1;
      if (event.key === "ArrowRight" || event.key === "ArrowDown") { target = (index + 1) % options.length; }
      else if (event.key === "ArrowLeft" || event.key === "ArrowUp") { target = (index + options.length - 1) % options.length; }
      else if (event.key === "Home") { target = 0; }
      else if (event.key === "End") { target = options.length - 1; }
      else if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        setChoice(current.getAttribute("data-theme-value"));
        return;
      }
      if (target < 0) { return; }
      event.preventDefault();
      setChoice(options[target].getAttribute("data-theme-value"));
      options[target].focus();
    });
    subscribers.push(sync);
    sync();
    host.appendChild(group);
  }

  apply();
  window.NHBTheme = Object.freeze({
    mount: mount,
    mountMotion: mountMotion,
    setChoice: setChoice,
    setMotion: setMotion,
    getMotion: function () { return motionOn; },
    subscribeMotion: function (notify) { motionSubscribers.push(notify); },
    getChoice: function () { return choice; },
    getTheme: resolve
  });
}).call(window);
"""

_TEMPLATE_SOURCE = """<!DOCTYPE html>
<html lang="en" class="booting">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="__CSP__">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<meta name="description" content="Offline incident exposure report: what a compromised CI entrypoint could reach, what survives its revocation and the order to rotate.">
<meta name="theme-color" content="#0e1116">
__THEME_SCRIPT__
<title>NHI-Blast report</title>
<style>
__FONT_CSS__
/* The data sections are hydrated from the embedded JSON; keep the shell hidden
   until the first render so nothing below reflows after paint. The boot status is
   the only thing visible, and only while that real render is in progress. */
html.booting body > :not(#boot-status):not(script) { visibility: hidden; }
html.boot-failed body > :not(#boot-status):not(script) { visibility: hidden; }
__THEME_TOKENS__
*, *::before, *::after { box-sizing: border-box; }
html { scroll-behavior: smooth; -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 400 var(--fs-body)/1.6 var(--sans);
  font-variant-numeric: tabular-nums;
  text-rendering: optimizeLegibility;
}
::selection { background: var(--selection-bg); color: var(--ink); }
h1, h2, h3, h4, p, dl, dd, figure { margin: 0; }
h1, h2, h3 { font-family: var(--display); font-weight: 700; letter-spacing: -.03em; color: var(--ink); }
h1 { font-size: clamp(40px, 5.2vw, 66px); line-height: 1.04; letter-spacing: -.04em; text-wrap: balance; }
h2 { font-size: clamp(28px, 3.3vw, 40px); line-height: 1.06; letter-spacing: -.035em; text-wrap: balance; }
h3 { font-size: 20px; line-height: 1.2; letter-spacing: -.02em; }
h4 { font-size: var(--fs-ui); font-weight: 600; line-height: 1.35; }
a { color: inherit; text-decoration: underline; text-decoration-color: var(--border-strong); text-underline-offset: 3px; }
a:hover { text-decoration-color: currentColor; }
button { font: inherit; color: inherit; }
.mono, code, pre { font-family: var(--mono); }
.mono { font-size: var(--fs-meta); overflow-wrap: anywhere; }
.muted { color: var(--muted); }
.sr-only {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0;
}
.empty {
  margin: 14px 0; padding: 18px; border: 1px dashed var(--border-strong); border-radius: var(--r-banner);
  background: var(--surface-2); color: var(--muted);
}
.note { margin: 12px 0; padding-left: 12px; border-left: 2px solid var(--warning); color: var(--muted); }
li.note { margin: 4px 0; padding-left: 0; border-left: 0; }
.wrap { max-width: 1200px; margin: 0 auto; padding: 0 32px; }
.skip-link { position: absolute; left: -999px; }
.skip-link:focus {
  left: 16px; top: 12px; z-index: 100; padding: 8px 12px;
  background: var(--surface); color: var(--ink); border: 1px solid var(--border-strong);
  border-radius: var(--r-button);
}
:focus-visible { outline: 2px solid var(--focus); outline-offset: 3px; }
#boot-status { display: none; }
html.booting #boot-status, html.boot-failed #boot-status {
  display: block; max-width: 1200px; margin: 0 auto; padding: 48px 32px;
  color: var(--muted); font-size: var(--fs-meta);
}
.boot-skeleton { display: grid; gap: 16px; max-width: 720px; margin-top: 24px; }
.sk { display: block; border-radius: 8px; background: var(--raised); }
.sk-title { height: 48px; width: 70%; }
.sk-title.short { width: 46%; }
.sk-line { height: 16px; width: 60%; }
.sk-row { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 16px; margin-top: 16px; }
.sk-stat { height: 80px; }
html.boot-failed .boot-skeleton { display: none; }
html.boot-failed #boot-status { color: var(--critical-ink); }

/* Viewer bar */
.viewer-bar { position: sticky; top: 0; z-index: 50; background: var(--header); border-bottom: var(--dp-hairline) solid var(--border); }
.viewer-inner { display: flex; align-items: center; gap: 16px; max-width: 1200px; height: 60px; margin: 0 auto; padding: 0 32px; }
.brand { display: flex; align-items: center; gap: 10px; min-width: 0; text-decoration: none; }
.brand-mark { flex: none; width: 24px; height: 24px; color: var(--accent); }
.brand-name { font-family: var(--display); font-size: 17px; font-weight: 700; letter-spacing: -.02em; white-space: nowrap; }
.brand-sub { padding-left: 12px; border-left: var(--dp-hairline) solid var(--border); color: var(--muted); font-size: var(--fs-meta); white-space: nowrap; }
.viewer-meta { display: flex; align-items: center; gap: 12px; margin-left: auto; color: var(--muted); font-size: var(--fs-label); }
.viewer-chip {
  display: inline-flex; align-items: center; gap: 7px; height: 26px; padding: 0 10px;
  border: var(--dp-hairline) solid var(--border-strong); border-radius: var(--r-pill);
  background: var(--surface); color: var(--ink-2); font-size: var(--fs-label); font-weight: 600;
}
.viewer-chip::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--positive); }
.viewer-schema { color: var(--muted); font-size: var(--fs-label); white-space: nowrap; }
__THEME_SWITCH_CSS__

/* Buttons */
.button {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  min-height: 40px; padding: 0 18px;
  border: var(--dp-hairline) solid var(--border-strong); border-radius: var(--r-button);
  background: var(--surface); color: var(--ink);
  font-size: var(--fs-ui); font-weight: 600; line-height: 1; text-decoration: none; white-space: nowrap;
  cursor: pointer;
  transition: transform var(--dp-motion), background-color var(--dp-motion), border-color var(--dp-motion), box-shadow var(--dp-motion), color var(--dp-motion);
}
.button:hover { transform: translateY(-1px); background: var(--hover); box-shadow: var(--shadow-lift); }
.button:active { transform: translateY(0); box-shadow: none; }
.button.primary { border-color: var(--accent); background: var(--accent); color: var(--accent-ink); }
.button.primary:hover { border-color: var(--accent-hover); background: var(--accent-hover); }
.button.secondary { background: var(--surface); border-color: var(--border-strong); }
.button.quiet { background: transparent; }
.button.quiet:hover { background: var(--hover); }
.button[hidden] { display: none; }
.viewer-inner .button { min-height: 36px; padding: 0 14px; font-size: var(--fs-small); flex: none; }

/* Hero */
.page-head { position: relative; isolation: isolate; padding: 80px 0 64px; background: var(--bg); overflow: clip; }
.hero-field {
  position: absolute; inset: 0; z-index: -1; pointer-events: none; opacity: var(--fx-alpha);
  -webkit-mask-image: linear-gradient(90deg, transparent 0, transparent 54%, #000 92%), linear-gradient(180deg, #000 0, #000 58%, transparent 100%);
  -webkit-mask-composite: source-in;
  mask-image: linear-gradient(90deg, transparent 0, transparent 54%, #000 92%), linear-gradient(180deg, #000 0, #000 58%, transparent 100%);
  mask-composite: intersect;
}
.hero { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(0, 1fr); gap: 64px; align-items: center; }
.hero-copy { min-width: 0; }
.hero-copy h1 {
  width: fit-content; max-width: 680px; padding-bottom: 4px;
  font: 600 60px/60px var(--display); letter-spacing: -.035em; text-wrap: balance;
  background-image: linear-gradient(90deg, var(--hero-from), var(--hero-to));
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent; color: transparent;
}
.hero-sub { max-width: 680px; margin-top: 24px; color: var(--ink-2); font: 400 18px/28px var(--sans); text-wrap: pretty; }
.scan-facts { display: flex; flex-wrap: wrap; gap: 8px; margin: 24px 0 0; padding: 0; list-style: none; }
.scan-fact {
  display: inline-flex; align-items: center; gap: 8px; min-height: 32px; padding: 4px 12px;
  border: var(--dp-hairline) solid var(--border); border-radius: 9999px; background: var(--surface);
  color: var(--ink-2); font-size: var(--fs-meta); line-height: 20px;
}
.scan-fact .k { color: var(--muted); font-size: var(--fs-label); font-weight: 600; letter-spacing: .04em; }
.scan-fact .v { color: var(--ink); font-family: var(--mono); font-size: var(--fs-label); font-weight: 500; overflow-wrap: anywhere; }
.copy-button {
  display: inline-flex; align-items: center; gap: 4px; height: 24px; margin: -2px -8px -2px 0; padding: 0 8px;
  border: 0; border-radius: 9999px; background: transparent; color: var(--ink-2);
  font: 600 12px/16px var(--sans); cursor: pointer;
  transition: background-color var(--dur-2) var(--ease), color var(--dur-2) var(--ease), transform var(--dur-3) var(--ease);
}
.copy-button:hover { background: var(--hover); color: var(--ink); }
.copy-button:active { transform: translateY(1px); }
.copy-button .icon { width: 14px; height: 14px; }
.icon { display: inline-block; width: 16px; height: 16px; flex: none; fill: currentColor; }
.icon-sprite { position: absolute; width: 0; height: 0; overflow: hidden; }
#finding-lead { margin-top: 32px; }
#finding-lead > * + * { margin-top: 16px; }
.lead {
  display: flex; align-items: center; gap: 12px 12px; flex-wrap: wrap;
  padding: 16px 24px;
  border: var(--dp-hairline) solid var(--border);
  border-radius: var(--r-banner); background: var(--surface); box-shadow: var(--shadow-card);
  position: relative;
}
.lead::before { content: ""; position: absolute; left: 0; top: 16px; bottom: 16px; width: 4px; border-radius: 0 4px 4px 0; background: var(--sev, var(--border-strong)); }
.lead-title { font-family: var(--display); font-size: 18px; font-weight: 600; letter-spacing: -.015em; line-height: 28px; min-width: 0; overflow-wrap: anywhere; }
.lead-meta { flex-basis: 100%; color: var(--muted); font-family: var(--mono); font-size: var(--fs-label); overflow-wrap: anywhere; }
.lead-empty { padding: 16px 24px; border: 1px dashed var(--border-strong); border-radius: var(--r-banner); color: var(--muted); }
.notice {
  display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap;
  margin-top: 12px; padding: 12px 16px;
  border: var(--dp-hairline) solid var(--pill-border-warning); border-radius: var(--r-control);
  background: var(--warning-soft); color: var(--warning-ink);
  font-size: var(--fs-small);
}
.notice strong { font-weight: 600; }
.hero-actions { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 16px 12px; margin-top: 32px; }
.pick { display: flex; flex-direction: column; gap: 8px; flex: 1 1 100%; min-width: 0; max-width: 560px; }
.field-label { color: var(--ink-2); font-size: var(--fs-label); font-weight: 600; letter-spacing: .01em; }
.field-hint { color: var(--muted); font-size: var(--fs-label); }
select, input[type="search"] {
  width: 100%; height: 48px; padding: 0 16px;
  border: var(--dp-hairline) solid var(--border-strong); border-radius: var(--r-control);
  background: var(--surface); color: var(--ink);
  font-family: inherit; font-size: var(--fs-ui);
  transition: border-color var(--dur-2) var(--ease), box-shadow var(--dur-2) var(--ease);
}
.select-wrap { position: relative; min-width: 0; }
.select-wrap select { appearance: none; -webkit-appearance: none; padding-right: 48px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
.select-wrap::after {
  content: ""; position: absolute; right: 20px; top: 50%; width: 8px; height: 8px; pointer-events: none;
  border-right: 2px solid var(--ink-2); border-bottom: 2px solid var(--ink-2);
  transform: translateY(-75%) rotate(45deg);
}
select:hover, input[type="search"]:hover { border-color: var(--ink-2); }
select:focus-visible, input[type="search"]:focus-visible { border-color: var(--accent); }
select:disabled { background: var(--raised); color: var(--muted); }
input[type="search"]::placeholder { color: var(--muted); }
.hero-actions .button { min-height: 48px; }
.hero-figure {
  position: relative; min-width: 0; max-width: 560px; width: 100%; justify-self: center; padding: 24px;
  border: var(--dp-hairline) solid var(--border); border-radius: 24px;
  background: var(--surface); box-shadow: var(--shadow-card);
}
.hero-figure::before {
  content: ""; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
  background-image: radial-gradient(circle, var(--grid-dot) 1px, transparent 1px);
  background-size: 24px 24px; opacity: .9;
}
.hero-svg { position: relative; display: block; width: 100%; height: auto; }
.hd-orbit { fill: none; stroke: var(--border-strong); stroke-width: 1; opacity: .38; }
.hd-line { fill: none; stroke: var(--border-strong); stroke-width: 1.5; stroke-linecap: round; opacity: .7; }
.hd-tile { fill: var(--surface); stroke: var(--border-strong); stroke-width: 1; }
.hd-tile-shadow { fill: var(--ink); opacity: .06; }
.hd-label { fill: var(--ink-2); font-family: var(--sans); font-size: 13px; font-weight: 500; }
.hd-value { fill: var(--ink); font-family: var(--display); font-size: 32px; font-weight: 700; letter-spacing: -.03em; }
.hd-value-R { fill: var(--R); }
.hd-value-E { fill: var(--warning-ink); }
.hd-value-Z { fill: var(--critical-ink); }
.hd-code { fill: var(--muted); font-family: var(--mono); font-size: 12px; font-weight: 600; }
.hd-core-text { fill: var(--accent-ink); font-family: var(--display); font-size: 15px; font-weight: 700; letter-spacing: -.02em; }
.hd-core-sub { fill: var(--accent-ink); font-family: var(--sans); font-size: 12px; opacity: .92; }
.hd-tile-group { transform-box: fill-box; transform-origin: center; }

/* Bands: each band is a sheet that overlaps the one before it */
#main { position: relative; }
.journey-svg { position: absolute; top: 0; left: 4px; width: 56px; height: 100%; z-index: 6; overflow: visible; pointer-events: none; color: var(--accent); }
.band { position: relative; }
.band-plain { background: var(--bg); }
.band-pale { background: var(--surface-2); border-block: var(--dp-hairline) solid var(--border); }
.band + .band { margin-top: -24px; padding-top: 24px; border-radius: 24px 24px 0 0; }
.band-facts { background: var(--bg); }
.passage { background: var(--bg); color: var(--ink); }
.passage a { text-decoration-color: var(--border-strong); }
.band.passage { border-block: var(--dp-hairline) solid var(--border); overflow: hidden; }
.band.passage > .wrap { position: relative; z-index: 1; }
.passage-field { position: absolute; inset: 0; z-index: 0; pointer-events: none; opacity: var(--fx-alpha); -webkit-mask-image: radial-gradient(90% 60% at 92% 0, #000 0, transparent 70%); mask-image: radial-gradient(90% 60% at 92% 0, #000 0, transparent 70%); }
.band-dark { padding: 0; }
main { padding-bottom: 0; }
section { position: relative; padding: 96px 0 24px; scroll-margin-top: 136px; }
.band > .wrap > section:last-child { padding-bottom: 96px; }
.band > .wrap > section + section { border-top: var(--dp-hairline) solid var(--border); margin-top: 48px; padding-top: 80px; }
.band-plain > .wrap > section:first-child { padding-top: 80px; }

/* Section heads: oversized numeral, small caps label, hairline rule */
.section-head {
  display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: end; column-gap: 24px; row-gap: 8px;
  margin-bottom: 48px; padding-bottom: 24px; border-bottom: var(--dp-hairline) solid var(--border-strong);
}
.sec-no { font-family: var(--display); font-size: 72px; line-height: 1; font-weight: 700; letter-spacing: -.05em; color: var(--ink); font-variant-numeric: tabular-nums; }
.sec-title { min-width: 0; }
.sec-label { display: block; margin-bottom: 8px; color: var(--muted); font-size: 12px; line-height: 16px; font-weight: 600; letter-spacing: .14em; font-variant-caps: all-small-caps; }
.section-head h2, .sec-title h2 { font: 600 48px/48px var(--display); letter-spacing: -.035em; text-wrap: balance; overflow-wrap: anywhere; }
.section-meta { color: var(--muted); font-size: var(--fs-meta); line-height: 20px; text-align: right; max-width: 56ch; overflow-wrap: anywhere; text-wrap: pretty; }
.section-lede { max-width: 66ch; margin: -24px 0 32px; color: var(--ink-2); font-size: var(--fs-body); text-wrap: pretty; }

/* Floating section nav: a compact translucent pill that sits off the top edge */
.nav-bar { position: sticky; top: 72px; z-index: 45; display: flex; justify-content: center; align-items: flex-start; height: 56px; padding: 0 16px; pointer-events: none; }
.toc {
  pointer-events: auto; position: relative; display: flex; align-items: center; max-width: 100%; min-width: 0; margin-top: 4px; padding: 4px;
  border: var(--dp-hairline) solid var(--border); border-radius: 9999px;
  background: var(--nav-surface); box-shadow: var(--shadow-card);
  -webkit-backdrop-filter: blur(16px) saturate(1.5); backdrop-filter: blur(16px) saturate(1.5);
}
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) { .toc { background: var(--nav-panel); } }
.toc-track {
  position: relative; display: flex; gap: 2px; min-width: 0; overflow-x: auto; scrollbar-width: none; border-radius: 9999px;
  -webkit-mask-image: linear-gradient(90deg, transparent 0, #000 var(--fade-l, 0px), #000 calc(100% - var(--fade-r, 0px)), transparent 100%);
  mask-image: linear-gradient(90deg, transparent 0, #000 var(--fade-l, 0px), #000 calc(100% - var(--fade-r, 0px)), transparent 100%);
}
.toc-track::-webkit-scrollbar { display: none; }
.toc a {
  position: relative; z-index: 1; display: inline-flex; align-items: center; flex: none;
  height: 36px; padding: 0 12px; border-radius: 9999px;
  color: var(--ink-2); font-size: var(--fs-small); line-height: 20px; font-weight: 500; text-decoration: none; white-space: nowrap;
  transition: color var(--dur-2) var(--ease), background-color var(--dur-2) var(--ease), transform var(--dur-3) var(--ease);
}
.toc a:hover { background: var(--hover); color: var(--ink); }
.toc a:active { transform: translateY(1px); }
.toc a[hidden] { display: none; }
.toc a:focus-visible { outline-offset: -2px; }
.toc a[aria-current="location"] { color: var(--ink); font-weight: 600; }
.nav-indicator {
  position: absolute; left: 0; bottom: 3px; width: 1px; height: 2px; z-index: 2;
  border-radius: 2px; background: var(--accent); opacity: 0; transform-origin: 0 50%;
  transition: transform var(--dur-3) var(--ease), opacity var(--dur-2) var(--ease);
  pointer-events: none;
}
.nav-indicator.is-active { opacity: 1; }
.nav-toggle { display: none; }

/* Facts strip */
#summary { padding: 0; margin-top: 0; }
.band-facts { background: var(--bg); border-bottom: var(--dp-hairline) solid var(--border); }
.summary-band {
  display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 0;
  border: 0; background: none;
}
.stat { position: relative; min-width: 0; padding: 36px 28px 36px 28px; border-left: var(--dp-hairline) solid var(--border); }
.stat:first-child { padding-left: 0; border-left: 0; }
.stat-label { display: flex; align-items: center; gap: 8px; color: var(--ink-2); font-size: var(--fs-small); font-weight: 500; }
.stat-label .code { height: 20px; min-width: 20px; font-size: 11px; }
.stat-value {
  display: block; margin-top: 14px;
  font-family: var(--display); font-size: clamp(44px, 4.6vw, 64px); font-weight: 700; line-height: 1; letter-spacing: -.045em;
  color: var(--ink);
}
.stat-value.is-data { color: var(--Z); }
.stat-value.is-critical { color: var(--critical); }
.stat-note { display: block; margin-top: 10px; color: var(--muted); font-size: var(--fs-meta); }
.summary-head { padding-top: 40px; }
.summary-brief { max-width: 78ch; padding: 0 0 36px; color: var(--ink-2); font-size: var(--fs-small); }
.summary-band-wrap { border-top: var(--dp-hairline) solid var(--border); margin-top: 28px; }

/* Pills, codes, status */
.pill {
  display: inline-flex; align-items: center; height: 24px; padding: 0 10px;
  border: var(--dp-hairline) solid var(--pill-border, var(--border-strong)); border-radius: var(--r-pill);
  background: var(--pill-bg, var(--neutral-soft)); color: var(--pill-ink, var(--neutral-ink));
  font-size: var(--fs-label); font-weight: 600; letter-spacing: .04em;
}
.sev-CRITICAL { --sev: var(--critical); --pill-bg: var(--critical-soft); --pill-ink: var(--critical-ink); --pill-border: var(--pill-border-critical); }
.sev-HIGH { --sev: var(--high); --pill-bg: var(--high-soft); --pill-ink: var(--high-ink); --pill-border: var(--pill-border-high); }
.sev-MEDIUM { --sev: var(--warning); --pill-bg: var(--warning-soft); --pill-ink: var(--warning-ink); --pill-border: var(--pill-border-warning); }
.sev-LOW { --sev: var(--low); --pill-bg: var(--low-soft); --pill-ink: var(--low-ink); --pill-border: var(--pill-border-low); }
.sev-INFO { --sev: var(--neutral-ink); --pill-bg: var(--neutral-soft); --pill-ink: var(--neutral-ink); --pill-border: var(--pill-border-info); }
.code {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 22px; height: 22px; padding: 0 6px;
  border-radius: var(--r-badge);
  font-family: var(--mono); font-size: 11.5px; font-weight: 600;
}
.code-R, .status-R { background: var(--raised); color: var(--R); }
.code-E, .status-E { background: var(--warning-soft); color: var(--warning-ink); }
.code-Z, .status-Z { background: var(--accent-soft); color: var(--critical-ink); }
.code-P, .status-P { background: var(--raised); color: var(--muted); }

/* How to read */
.guide-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--dp-gap); }
.guide-card { min-width: 0; padding: 28px; border: var(--dp-hairline) solid var(--border); border-radius: var(--r-panel); background: var(--surface); box-shadow: var(--shadow-card); }
.guide-card h3 { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; font-size: 20px; }
.guide-card p { color: var(--ink-2); font-size: var(--fs-ui); }
.evidence-guide { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 2fr); gap: 56px; margin-top: 72px; }
.evidence-guide > div > p { margin-top: 14px; color: var(--ink-2); font-size: var(--fs-ui); max-width: 40ch; }
.class-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 var(--dp-gap); margin: 0; padding: 0; list-style: none; }
.class-list li { padding: 18px 0; border-top: var(--dp-hairline) solid var(--border-strong); }
.class-list strong { display: block; margin-bottom: 4px; font-family: var(--mono); font-size: var(--fs-meta); font-weight: 600; letter-spacing: .02em; }
.class-list span { color: var(--ink-2); font-size: var(--fs-ui); }

/* Survival */
.survival-rail { display: flex; gap: 3px; height: 14px; overflow: hidden; border-radius: 7px; background: transparent; }
.survival-rail span { display: block; height: 100%; border-radius: 3px; }
.seg-R { background: var(--R); }
.seg-E { background: repeating-linear-gradient(135deg, var(--E) 0 4px, var(--seg-e-stripe) 4px 8px); }
.seg-Z { background: var(--Z); }
.survival-legend { display: flex; flex-wrap: wrap; gap: 8px 28px; margin-top: 16px; color: var(--ink-2); font-size: var(--fs-small); }
.legend-item { display: inline-flex; align-items: center; gap: 8px; }
.legend-swatch { display: inline-block; width: 12px; height: 12px; border-radius: 3px; }
.legend-count { color: var(--ink); font-weight: 700; }
.outcome-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--dp-gap); margin-top: 32px; }
.outcome {
  position: relative; min-width: 0; padding: 24px;
  border: var(--dp-hairline) solid var(--border); border-radius: var(--r-panel); background: var(--surface);
}
.outcome::before { content: ""; position: absolute; top: -1px; left: 24px; width: 36px; height: 3px; border-radius: 0 0 3px 3px; background: var(--outcome-color, var(--R)); }
.outcome-R { --outcome-color: var(--R); }
.outcome-E { --outcome-color: var(--E); }
.outcome-Z { --outcome-color: var(--Z); }
.outcome-head { display: flex; align-items: center; gap: 10px; }
.outcome-title { color: var(--ink-2); font-size: var(--fs-ui); font-weight: 600; }
.outcome-count { margin-left: auto; font-family: var(--display); font-size: 30px; font-weight: 700; line-height: 1; letter-spacing: -.03em; color: var(--ink); }
.outcome-list { margin: 16px 0 0; padding: 0; list-style: none; }
.outcome-list li { padding: 12px 0; border-top: var(--dp-hairline) solid var(--border); }
.outcome-list li:first-child { padding-top: 0; border-top: 0; }
.outcome-list .empty { margin: 0; padding: 0; border: 0; background: none; font-size: var(--fs-small); }
.trace-link {
  display: inline-flex; align-items: center; min-height: 24px; padding: 0; border: 0; background: none;
  color: var(--ink); font-family: inherit; font-size: var(--fs-ui); font-weight: 600; line-height: 1.4;
  text-align: left; text-decoration: underline; text-decoration-color: var(--border-strong); text-underline-offset: 3px;
  cursor: pointer; overflow-wrap: anywhere;
  transition: color var(--dp-motion), text-decoration-color var(--dp-motion);
}
.trace-link:hover { color: var(--accent); text-decoration-color: currentColor; }
.outcome-meta { display: block; margin-top: 2px; color: var(--muted); font-size: var(--fs-small); overflow-wrap: anywhere; }
.outcome-where { display: block; margin-top: 1px; color: var(--muted); font-family: var(--mono); font-size: var(--fs-label); overflow-wrap: anywhere; }
.outcome-more { margin-top: 12px; font-size: var(--fs-small); }
.table-hint { margin-top: 32px; color: var(--muted); font-size: var(--fs-small); }
.table-heading { display: flex; align-items: center; gap: 10px; margin: 36px 0 12px; font-size: 18px; }
.table-wrap {
  max-width: 100%; overflow-x: auto;
  border: var(--dp-hairline) solid var(--border); border-radius: var(--r-banner); background: var(--surface);
}
.table-wrap:focus-visible { outline: 2px solid var(--focus); outline-offset: 3px; }
.scroll-hint { margin: 0 0 6px; color: var(--muted); font-size: var(--fs-label); text-align: right; }
table { width: 100%; min-width: 660px; border-collapse: collapse; table-layout: fixed; font-size: var(--fs-small); }
caption {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0;
}
thead th {
  padding: 11px 14px; border-bottom: var(--dp-hairline) solid var(--border);
  background: var(--surface-2); color: var(--ink-2); font-size: var(--fs-label); font-weight: 600; letter-spacing: .02em; text-align: left;
  white-space: nowrap;
}
tbody td, tbody th {
  padding: 12px 14px; border-bottom: var(--dp-hairline) solid var(--border); text-align: left; vertical-align: top;
  transition: background-color var(--dp-motion);
}
tbody tr:hover td, tbody tr:hover th { background: var(--surface-2); }
tbody tr:last-child td, tbody tr:last-child th { border-bottom: 0; }
td.num, th.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
td.wrap, th.wrap { overflow-wrap: anywhere; }
td.nowrap { white-space: nowrap; }
.table-wrap table.wide { min-width: 860px; }
.cell-id { display: block; margin-top: 2px; color: var(--muted); font-family: var(--mono); font-size: var(--fs-label); overflow-wrap: anywhere; }
.evidence { color: var(--muted); font-size: var(--fs-meta); overflow-wrap: anywhere; }
.evidence-list { margin: 6px 0 0; padding-left: 18px; color: var(--muted); font-size: var(--fs-meta); }
.evidence-list li { margin: 2px 0; overflow-wrap: anywhere; }

/* Disclosures */
details { margin-top: 10px; }
summary {
  display: inline-flex; align-items: center; gap: 10px;
  padding: 7px 12px; border: var(--dp-hairline) solid var(--border); border-radius: var(--r-button);
  background: var(--surface); color: var(--ink-2); font-size: var(--fs-small); font-weight: 500; cursor: pointer; list-style: none;
  transition: color var(--dp-motion), border-color var(--dp-motion), background-color var(--dp-motion);
}
summary::-webkit-details-marker { display: none; }
summary::before {
  content: "+"; display: inline-block; width: 12px; color: var(--accent); font-family: var(--mono); font-size: 16px; font-weight: 600; line-height: 1; text-align: center;
  transition: transform var(--dp-motion);
}
details[open] > summary::before { transform: rotate(45deg); }
summary:hover { color: var(--ink); border-color: var(--border-strong); background: var(--hover); }
details[open] > summary { margin-bottom: 10px; color: var(--ink); }
.details-body { padding-top: 2px; }
pre {
  margin: 8px 0 0; padding: 14px; overflow-wrap: anywhere; white-space: pre-wrap;
  background: var(--surface-2); border: var(--dp-hairline) solid var(--border); border-radius: var(--r-control);
  font-size: var(--fs-meta); line-height: 1.5;
}
.disclosure { margin: 0; border-top: var(--dp-hairline) solid var(--border-strong); }
.disclosure > summary {
  display: grid; grid-template-columns: auto minmax(0, 1fr) auto auto; align-items: center; column-gap: 24px; row-gap: 8px;
  width: 100%; margin: 0; padding: 40px 0; border: 0; border-radius: 0; background: none; color: var(--ink);
}
.disclosure > summary:hover { background: none; }
.disclosure > summary .sec-no { font-size: 48px; }
.disclosure > summary h2 { font: 600 36px/40px var(--display); letter-spacing: -.03em; }
.disclosure > summary .section-meta { text-align: right; }
.disclosure > summary::before { display: none; }
.disclosure[open] > summary { margin-bottom: 0; }
.disclosure-body { padding: 0 0 64px; }
.section-disclosure { padding: 0; }
.band > .wrap > section.section-disclosure + section.section-disclosure { border-top: 0; margin-top: 0; padding-top: 0; }
.band > .wrap > section.section-disclosure:first-child { padding-top: 48px; }
.band > .wrap > section.section-disclosure:last-child { padding-bottom: 48px; }
.band > .wrap > section.section-disclosure:last-child .disclosure { border-bottom: var(--dp-hairline) solid var(--border-strong); }
details[data-fx-disclosure] > summary::before { display: none; }

/* Rotation: numbered process steps */
.rotation-group { margin-top: 48px; }
.rotation-group:first-child { margin-top: 0; }
.rotation-group h3 { display: flex; align-items: baseline; gap: 12px; margin: 0 0 28px; font-size: 22px; }
.steps { --cols: 4; margin: 0; padding: 0; list-style: none; display: grid; grid-template-columns: repeat(var(--cols), minmax(0, 1fr)); gap: 48px 32px; }
.steps.cols-1 { --cols: 1; }
.steps.cols-2 { --cols: 2; }
.steps.cols-3 { --cols: 3; }
.step { position: relative; min-width: 0; padding-top: 56px; }
.step-no {
  position: absolute; top: 0; left: 0; z-index: 1;
  display: inline-flex; align-items: center; justify-content: center;
  width: 36px; height: 36px;
  border: var(--dp-hairline) solid var(--border-strong); border-radius: 50%; background: var(--bg);
  color: var(--ink); font-family: var(--display); font-size: 14px; font-weight: 700;
}
.step-link { position: absolute; top: 0; left: 36px; width: calc(100% - 8px); height: 36px; overflow: visible; pointer-events: none; }
.step-link path { fill: none; stroke: var(--border-strong); stroke-width: 1px; vector-effect: non-scaling-stroke; }
.step-link .sl-v { display: none; }
.steps.cols-4 .step:nth-child(4n) .step-link, .steps.cols-3 .step:nth-child(3n) .step-link, .steps.cols-2 .step:nth-child(2n) .step-link,
.steps .step:last-child .step-link { display: none; }
.step-body { min-width: 0; }
.step-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.phase-pill { background: transparent; color: var(--ink-2); border-style: solid; border-color: var(--border-strong); }
.step-title { font-family: var(--display); font-size: 17px; font-weight: 700; letter-spacing: -.02em; }
.step-body > .muted { margin-top: 6px; font-size: var(--fs-small); }
.step-actions { margin: 10px 0 0; padding-left: 18px; font-size: var(--fs-small); color: var(--ink-2); }
.step-actions li { margin: 5px 0; }
.step-cred { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
.cred-chip {
  display: inline-flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 3px 9px;
  border: var(--dp-hairline) solid var(--border); border-radius: var(--r-badge); background: var(--surface);
  color: var(--ink); font-size: var(--fs-label); overflow-wrap: anywhere;
}
.cred-chip .mono { color: var(--muted); font-size: 11px; }
.notes-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 var(--dp-gap); margin: 0; padding: 0; list-style: none; }
.notes-list li.note { margin: 0; padding: 16px 0; border-top: var(--dp-hairline) solid var(--border-strong); color: var(--ink-2); font-size: var(--fs-small); }
.notes-title { margin: 56px 0 8px; font-size: 20px; }
.fact-grid {
  display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; gap: 24px;
  padding: 20px 24px; border: var(--dp-hairline) solid var(--border); border-radius: var(--r-panel); background: var(--surface);
}
.fact { min-width: 0; }
.fact-label { display: block; color: var(--muted); font-size: var(--fs-label); }
.fact-value { display: block; margin-top: 5px; font-size: 17px; font-weight: 600; }
.chip-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.text-chip {
  display: inline-flex; align-items: center; padding: 3px 10px;
  border: var(--dp-hairline) solid var(--border); border-radius: var(--r-badge); background: var(--surface-2);
  font-size: var(--fs-label); overflow-wrap: anywhere;
}

/* Graph */
.graph-toolbar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px 16px; margin-bottom: 14px; }
.graph-legend { display: flex; flex-wrap: wrap; gap: 6px 18px; color: var(--ink-2); font-size: var(--fs-label); }
.graph-legend span { display: inline-flex; align-items: center; gap: 8px; padding: 4px 12px; border: var(--dp-hairline) solid var(--border); border-radius: 9999px; background: var(--surface); }
.graph-legend i { display: inline-block; width: 24px; border-top: 2px solid currentColor; }
.graph-legend .solid i { color: var(--graph-edge); }
.graph-legend .dashed i { color: var(--warning); border-top-style: dashed; }
.graph-legend .dotted i { color: var(--muted); border-top-style: dotted; }
.graph-legend .entry i { width: 14px; height: 10px; border: 1px dashed var(--accent); border-radius: 3px; }
.graph-actions { display: flex; align-items: center; gap: 6px; }
.graph-actions .button { min-width: 36px; min-height: 36px; padding: 0 10px; border-radius: var(--r-button); font-family: var(--mono); font-size: var(--fs-label); }
#graph-zoom-level { min-width: 60px; }
#graph {
  position: relative; left: 50%;
  width: min(1520px, calc(100vw - 32px));
  margin-left: calc(min(1520px, calc(100vw - 32px)) / -2);
}
.graph-head { width: min(1136px, calc(100vw - 64px)); margin: 0 auto; }
.graph-frame {
  position: relative; overflow: hidden;
  border: var(--dp-hairline) solid var(--border); border-radius: var(--r-panel); background: var(--surface); box-shadow: var(--shadow-card);
}
.graph-stage {
  position: relative; height: clamp(28rem, 84vh, 54rem); overflow: hidden;
  cursor: grab; touch-action: pan-y;
  background-color: var(--surface);
  background-image: radial-gradient(circle, var(--grid-dot) 1px, transparent 1px);
  background-size: 18px 18px;
}
.graph-stage:focus-within { outline: 2px solid var(--focus); outline-offset: -2px; }
.graph-stage.is-panning { cursor: grabbing; }
.graph-stage.is-pannable { touch-action: none; }
.graph-viewport { position: absolute; left: 0; top: 0; transform-origin: 0 0; }
.graph-viewport.is-animated { transition: transform var(--dur-3) var(--ease-out); }
.graph-svg { display: block; overflow: visible; font-family: var(--sans); }
.gstage-band { fill: var(--surface-2); stroke: var(--border); stroke-width: 1; }
.gstage-title { fill: var(--ink-2); font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; }
.gstage-index { fill: var(--muted); font-family: var(--mono); font-size: 10px; letter-spacing: .04em; }
.gstage-count { fill: var(--muted); font-family: var(--mono); font-size: 12px; }
.gedge-hit { fill: none; stroke: transparent; stroke-width: 16; pointer-events: stroke; cursor: pointer; }
.gedge-line { fill: none; stroke: var(--graph-edge); stroke-width: 1.5; stroke-linecap: round; marker-end: url(#graph-arrow); transition: stroke var(--dur-2) var(--ease), stroke-width var(--dur-2) var(--ease); }
.gedge { transition: opacity var(--dur-2) var(--ease); }
.gedge.conf-assumed .gedge-line { stroke: var(--warning); stroke-dasharray: 7 4; }
.gedge.conf-unknown .gedge-line { stroke: var(--muted); stroke-dasharray: 2 4; }
.gedge:hover .gedge-line, .gedge.is-selected-edge .gedge-line { stroke-width: 2.6; }
.gedge.is-selected-edge .gedge-line { stroke: var(--accent); }
.gedge.is-traced .gedge-line { stroke: var(--accent); stroke-width: 2.6; stroke-dasharray: none; }
.gedge.is-outside { opacity: .35; }
.graph-arrow-head { fill: context-stroke; }
.gnode { cursor: pointer; outline: none; transition: opacity var(--dur-2) var(--ease); }
.gnode-shape { fill: var(--node-fill); stroke: var(--graph-edge); stroke-width: 1.6; transition: stroke var(--dur-2) var(--ease), stroke-width var(--dur-2) var(--ease), fill var(--dur-2) var(--ease); }
.gnode.kind-repository .gnode-shape, .gnode.kind-workflow .gnode-shape, .gnode.kind-job .gnode-shape { stroke: var(--node-workflow); }
.gnode.kind-action-ref .gnode-shape, .gnode.kind-external-target .gnode-shape { stroke: var(--node-structure); }
.gnode.kind-oidc-identity .gnode-shape, .gnode.kind-aws-oidc-provider .gnode-shape { stroke: var(--node-oidc); }
.gnode.kind-aws-role .gnode-shape { stroke: var(--node-role); }
.gnode.kind-sink .gnode-shape { stroke: var(--node-sink); }
.gnode.kind-credential .gnode-shape { stroke: var(--node-credential); }
.gnode-label { fill: var(--ink); font-size: 14px; font-weight: 500; }
.gnode-meta { fill: var(--muted); font-size: 11.5px; }
.gnode-badges { font-size: 9.5px; font-weight: 600; letter-spacing: .06em; }
.badge-entry { fill: var(--accent); }
.badge-critical { fill: var(--critical); }
.badge-sep { fill: var(--muted); }
.gnode-halo { fill: var(--focus); opacity: 0; pointer-events: none; transition: opacity var(--dur-2) var(--ease); }
.gnode-entry-frame { fill: none; stroke: var(--accent); stroke-width: 1.2; stroke-dasharray: 3 3; }
.gnode:hover .gnode-shape { stroke-width: 2.4; }
.gnode:focus .gnode-shape, .gnode:focus-visible .gnode-shape { stroke: var(--focus); stroke-width: 2.8; }
.gnode:focus .gnode-halo, .gnode:focus-visible .gnode-halo { opacity: .14; }
.gnode.is-critical .gnode-shape { stroke-width: 2.2; }
.gnode.is-selected .gnode-shape { stroke: var(--accent); stroke-width: 3; }
.gnode.is-selected .gnode-halo { opacity: .18; }
.gnode.is-neighbor .gnode-shape { stroke-width: 2.4; }
.gnode.is-traced .gnode-shape { stroke: var(--accent); stroke-width: 3; }
.gnode.is-outside { opacity: .45; }
.graph-stage.is-tracing .gnode:not(.is-traced) { opacity: .28; }
.graph-stage.is-tracing .gedge:not(.is-traced) { opacity: .15; }
.graph-stage.has-selection .gnode:not(.is-selected):not(.is-neighbor) { opacity: .42; }
.graph-stage.has-selection .gedge:not(.is-incident) { opacity: .3; }
.graph-empty { fill: var(--muted); font-size: 14px; }
#graph .graph-frame { z-index: 7; }
#graph-note, #entity-details { width: min(1136px, calc(100vw - 64px)); margin-left: auto; margin-right: auto; }
#graph-note { max-width: 92ch; margin-top: 14px; color: var(--muted); font-size: var(--fs-small); }
#entity-details { margin-top: 18px; padding-top: 18px; border-top: var(--dp-hairline) solid var(--border); }
#entity-details h3 { margin: 0; font-size: 20px; }
.entity-sub { margin-top: 3px; color: var(--muted); font-family: var(--mono); font-size: var(--fs-label); overflow-wrap: anywhere; }
.entity-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.entity-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
.entity-block { margin-top: 16px; }
.entity-block h4 { margin-bottom: 4px; color: var(--muted); font-size: var(--fs-label); font-weight: 600; }
.entity-links { margin: 0; padding: 0; list-style: none; }
.entity-links li { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; padding: 8px 0; border-top: var(--dp-hairline) solid var(--border); }
.entity-links li:first-child { border-top: 0; }
.entity-link-meta { color: var(--muted); font-family: var(--mono); font-size: var(--fs-label); overflow-wrap: anywhere; }
.entity-placeholder { color: var(--muted); }

/* Findings */
.toolbar { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px 14px; margin-bottom: 14px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field label { color: var(--ink-2); font-size: var(--fs-label); font-weight: 600; }
.field-search { width: 280px; }
.toolbar .field-select { width: 200px; }
.field-select { width: 190px; }
.toolbar-status { margin-left: auto; padding-bottom: 12px; color: var(--muted); font-size: var(--fs-meta); }
.toolbar .button { min-height: 48px; }
#findings .toolbar { position: sticky; top: 124px; z-index: 20; margin: 0 0 16px; padding: 16px 0; background: var(--bg); border-bottom: var(--dp-hairline) solid var(--border); }
.finding {
  position: relative; margin-top: 16px; padding: 24px 24px 24px 32px;
  border: var(--dp-hairline) solid var(--border); border-radius: var(--r-banner); background: var(--surface); box-shadow: var(--shadow-card);
  transition: border-color var(--dp-motion), box-shadow var(--dp-motion), transform var(--dur-3) var(--ease);
}
.finding::before { content: ""; position: absolute; left: 0; top: 24px; bottom: 24px; width: 4px; border-radius: 0 4px 4px 0; background: var(--sev, var(--border-strong)); }
.finding:hover { border-color: var(--border-strong); }
.finding-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.finding-head h3 { font-size: 18px; font-weight: 600; letter-spacing: -.015em; }
.finding-rule { margin-top: 8px; color: var(--muted); font-family: var(--mono); font-size: var(--fs-label); overflow-wrap: anywhere; }
.finding-message { margin-top: 10px; color: var(--ink-2); overflow-wrap: anywhere; }
.finding, .finding-head h3, .lead-title { min-width: 0; overflow-wrap: anywhere; }
.finding-meta { margin-top: 8px; color: var(--muted); font-size: var(--fs-meta); }
.finding-path { margin-top: 10px; color: var(--muted); font-family: var(--mono); font-size: var(--fs-label); overflow-wrap: anywhere; }
.matrix-summary { margin-bottom: 8px; color: var(--ink-2); }
.matrix-legend { display: flex; flex-wrap: wrap; gap: 6px 18px; margin: 14px 0; color: var(--ink-2); font-size: var(--fs-label); }
.matrix-legend span { display: inline-flex; align-items: center; gap: 6px; }
.matrix-wrap {
  max-height: 42rem; overflow: auto;
  border: var(--dp-hairline) solid var(--border); border-radius: var(--r-banner); background: var(--surface);
}
.matrix { min-width: max-content; border-collapse: separate; border-spacing: 0; font-size: var(--fs-label); }
.matrix thead th { position: sticky; top: 0; z-index: 2; background: var(--raised); border-bottom: var(--dp-hairline) solid var(--border); }
.matrix tbody th { position: sticky; left: 0; z-index: 1; min-width: 14rem; background: var(--surface); font-weight: 600; }
.matrix thead th:first-child { left: 0; z-index: 3; }
.matrix td { padding: 8px 10px; border-bottom: var(--dp-hairline) solid var(--border); text-align: center; }
.matrix .active-row th { box-shadow: inset 3px 0 0 var(--accent); }
button.status {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 28px; height: 28px; padding: 0 6px;
  border: 1px solid transparent; border-radius: var(--r-badge);
  font-family: var(--mono); font-size: 12px; font-weight: 600;
  cursor: pointer;
  transition: border-color var(--dur-1) var(--ease), background-color var(--dur-1) var(--ease);
}
button.status:hover { border-color: currentColor; }
.kv { position: relative; }
.kv div { display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 16px; padding: 14px 0; border-bottom: var(--dp-hairline) solid var(--border); }
.kv div:first-child { border-top: var(--dp-hairline) solid var(--border); }
.kv dt { color: var(--muted); font-size: var(--fs-small); }
.kv dd { margin: 0; overflow-wrap: anywhere; }
#scope-content > .kv { padding: 0; background: none; border: 0; border-radius: 0; }
#scope-content > .kv div:first-child { border-top: var(--dp-hairline) solid var(--border-strong); }
#scope-content > .kv div { border-bottom-color: var(--border); }
#scope-content > h3, #scenario-content > h3, #assumptions-content > h3,
#rotation-content > h3, #trace-content > h3 { margin-bottom: 12px; }
#scope-content > h3:not(:first-child), #scenario-content > h3:not(:first-child),
#assumptions-content > h3:not(:first-child), #rotation-content > h3:not(:first-child),
#trace-content > h3:not(:first-child) { margin-top: 40px; }
ul.plain { margin: 8px 0 0; padding-left: 20px; }
ul.plain li { margin: 5px 0; }
.trace { margin: 16px 0 0; padding: 0 0 0 16px; border-left: var(--dp-hairline) solid var(--border-strong); list-style: none; }
.trace li { position: relative; padding: 0 0 14px 12px; }
.trace li::before { content: ""; position: absolute; left: -22px; top: 7px; width: 8px; height: 8px; border: 1px solid var(--border-strong); border-radius: 50%; background: var(--surface); }
.trace .hop { font-size: var(--fs-ui); font-weight: 600; overflow-wrap: anywhere; }
.trace .muted { margin-top: 2px; font-size: var(--fs-small); }

/* Analysis completeness */
.cmp-counts { display: flex; flex-wrap: wrap; gap: 10px; margin: 0 0 20px; padding: 0; list-style: none; }
.cmp-counts li { display: inline-flex; align-items: center; gap: 10px; padding: 8px 14px; border: var(--dp-hairline) solid var(--border); border-radius: var(--r-pill); background: var(--surface); }
.cmp-count-num { font-family: var(--display); font-size: 22px; font-weight: 700; line-height: 1; letter-spacing: -.03em; color: var(--ink); }
.cmp-note { max-width: 74ch; margin: 0 0 8px; padding: 16px 20px; border: var(--dp-hairline) solid var(--pill-border-warning); border-radius: var(--r-control); background: var(--warning-soft); color: var(--warning-ink); font-size: var(--fs-small); text-wrap: pretty; }
.cmp-group { margin-top: 36px; }
.cmp-group > h3 { display: flex; align-items: center; gap: 8px; margin: 0 0 12px; font-size: 20px; }
.cmp-list { margin: 0; padding: 0; list-style: none; overflow: hidden; border: var(--dp-hairline) solid var(--border); border-radius: var(--r-panel); background: var(--surface); box-shadow: var(--shadow-card); }
.cmp-item { padding: 18px 24px; border-top: var(--dp-hairline) solid var(--border); }
.cmp-item:first-child { border-top: 0; }
.cmp-item-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; }
.cmp-family { font-size: 17px; font-weight: 600; letter-spacing: -.01em; }
.cmp-status {
  display: inline-flex; align-items: center; height: 24px; padding: 0 11px;
  border: var(--dp-hairline) solid var(--border-strong); border-radius: var(--r-pill);
  background: transparent; color: var(--ink-2); font-size: var(--fs-label); font-weight: 600; letter-spacing: .03em;
}
.cmp-status-partially_analysed { color: var(--warning-ink); border-color: var(--pill-border-warning); background: var(--warning-soft); }
.cmp-status-not_provided { color: var(--high-ink); border: 1px dashed var(--pill-border-high); background: var(--high-soft); }
.cmp-status-not_supported { color: var(--low-ink); border: 1px dashed var(--pill-border-low); background: var(--low-soft); }
.cmp-status-analysed { color: var(--ink-2); background: var(--surface-2); }
.cmp-status-not_applicable { color: var(--muted); border: 1px dashed var(--border-strong); background: transparent; }
.cmp-explanation { margin-top: 8px; color: var(--ink-2); font-size: var(--fs-ui); overflow-wrap: anywhere; }
.cmp-facts { display: grid; gap: 8px; margin: 12px 0 0; }
.cmp-fact { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 12px; }
.cmp-fact dt { color: var(--muted); font-size: var(--fs-label); font-weight: 600; }
.cmp-fact dd { margin: 0; min-width: 0; }
.cmp-sources { margin: 0; padding: 0; list-style: none; font-size: var(--fs-label); }
.cmp-sources li { margin: 0 0 4px; overflow-wrap: anywhere; }
.cmp-hash { margin-left: 8px; color: var(--muted); font-family: var(--mono); }
.cmp-links { display: flex; flex-wrap: wrap; gap: 4px 14px; font-family: var(--mono); font-size: var(--fs-label); }
.cmp-group details { margin-top: 0; }
.cmp-group details > .cmp-list { margin-top: 10px; }
tr[id] { scroll-margin-top: 140px; }

/* Text styles: sizes snap to the Tailwind scale, defined once and reused */
.heading-1 { font: 600 60px/60px var(--display); letter-spacing: -.035em; text-wrap: balance; }
.heading-2 { font: 600 48px/48px var(--display); letter-spacing: -.035em; text-wrap: balance; }
.heading-3 { font: 600 36px/40px var(--display); letter-spacing: -.03em; text-wrap: balance; }
.heading-4 { font: 600 30px/36px var(--display); letter-spacing: -.025em; text-wrap: balance; }
.heading-5 { font: 600 24px/32px var(--display); letter-spacing: -.02em; text-wrap: balance; }
.heading-6 { font: 600 20px/28px var(--display); letter-spacing: -.015em; text-wrap: balance; }
.title-1 { font: 500 20px/28px var(--sans); }
.title-2 { font: 500 18px/28px var(--sans); }
.title-3 { font: 500 16px/24px var(--sans); }
.title-4 { font: 500 14px/20px var(--sans); }
.title-5 { font: 500 12px/16px var(--sans); }
.body-1 { font: 600 16px/24px var(--sans); text-wrap: pretty; }
.body-2 { font: 500 16px/24px var(--sans); text-wrap: pretty; }
.body-3 { font: 400 16px/24px var(--sans); text-wrap: pretty; }
.body-4 { font: 600 14px/20px var(--sans); text-wrap: pretty; }
.body-5 { font: 500 14px/20px var(--sans); text-wrap: pretty; }
.body-6 { font: 400 14px/20px var(--sans); text-wrap: pretty; }
.button-lg { font: 600 18px/28px var(--sans); }
.button-md { font: 600 16px/24px var(--sans); }
.button-sm { font: 600 14px/20px var(--sans); }
.button-xsm { font: 600 12px/16px var(--sans); }
.caption-1 { font: 500 14px/20px var(--sans); }
.caption-2 { font: 400 14px/20px var(--sans); }
.caption-3 { font: 600 12px/16px var(--sans); }
.caption-4 { font: 500 12px/16px var(--sans); }
.caption-5 { font: 400 12px/16px var(--sans); }
p { text-wrap: pretty; }

/* Tagline reveal */
.band-tagline { background: var(--bg); overflow: hidden; }
.tagline { padding: 128px 0 96px; }
.tagline-grid { position: relative; display: grid; grid-template-columns: minmax(0, 680px) minmax(0, 1fr); gap: 64px; align-items: center; }
.tagline-text { max-width: 680px; font: 600 48px/48px var(--display); letter-spacing: -.03em; text-wrap: balance; color: var(--ink); }
.tagline-rings { width: 100%; max-width: 360px; height: auto; justify-self: end; overflow: visible; }
.tagline-rings circle { fill: none; stroke: var(--border-strong); stroke-width: 1; opacity: .5; vector-effect: non-scaling-stroke; }
.tagline-rings circle.core { fill: var(--accent); stroke: none; opacity: 1; }
.js-words .tl-w { opacity: .3; transition: opacity 700ms cubic-bezier(.22, 1, .36, 1); transition-delay: var(--wd, 0ms); }
.js-words .tl-w.is-on { opacity: 1; }

/* Survival timeline: the product's own picture of what outlasts revocation */
.timeline { margin-top: 64px; --tl-label: 240px; }
.tl-head { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 8px 24px; margin-bottom: 24px; }
.tl-head h3 { font: 600 24px/32px var(--display); letter-spacing: -.02em; }
.tl-caption { color: var(--muted); font-size: var(--fs-meta); line-height: 20px; max-width: 56ch; }
.tl-axis { position: relative; height: 48px; margin-left: var(--tl-label); border-bottom: var(--dp-hairline) solid var(--border-strong); }
.tl-tick { position: absolute; bottom: 0; padding-bottom: 12px; color: var(--ink-2); font: 600 12px/16px var(--sans); white-space: nowrap; transform: translateX(-50%); }
.tl-tick::after { content: ""; position: absolute; left: 50%; bottom: 0; width: 1px; height: 8px; background: var(--border-strong); }
.tl-tick.is-first { transform: none; }
.tl-tick.is-first::after { left: 0; }
.tl-tick.is-last { transform: translateX(-100%); }
.tl-tick.is-last::after { left: 100%; }
.tl-group { margin-top: 32px; }
.tl-group-title { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; color: var(--ink-2); font: 600 14px/20px var(--sans); }
.tl-row {
  position: relative; display: grid; grid-template-columns: var(--tl-label) minmax(0, 1fr); align-items: center; min-height: 40px;
  border-radius: 8px; outline-offset: 0; cursor: default;
  transition: background-color var(--dur-2) var(--ease);
}
.tl-row:hover, .tl-row:focus-visible, .tl-row.is-active { background: var(--surface-2); }
.tl-name { min-width: 0; padding: 0 16px 0 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font: 500 14px/20px var(--sans); }
.tl-track { position: relative; height: 40px; }
.tl-track::before { content: ""; position: absolute; left: 0; right: 0; top: 50%; height: 1px; background: var(--border); }
.tl-job { position: absolute; top: 0; bottom: 0; width: 1px; background: var(--border-strong); opacity: .5; }
.tl-bar { position: absolute; left: 0; top: 12px; height: 16px; border-radius: 9999px; min-width: 16px; }
.tl-bar-e { background: repeating-linear-gradient(135deg, var(--E) 0 4px, var(--seg-e-stripe) 4px 8px); }
.tl-bar-z { right: 0; background: var(--Z); -webkit-mask-image: linear-gradient(90deg, #000 0, #000 55%, transparent 100%); mask-image: linear-gradient(90deg, #000 0, #000 55%, transparent 100%); }
.tl-window { display: block; color: var(--ink-2); font: 400 12px/16px var(--sans); white-space: normal; overflow-wrap: anywhere; }
.tl-name:has(.tl-window) { white-space: normal; padding-top: 4px; padding-bottom: 4px; }
.tl-bar-z.is-bounded { right: auto; -webkit-mask-image: none; mask-image: none; }
.tl-bar-z::after { content: ""; position: absolute; inset: 0; border-radius: inherit; background: repeating-linear-gradient(135deg, transparent 0 4px, var(--bg) 4px 6px); opacity: .5; }
.tl-arrow { position: absolute; right: 0; top: 10px; width: 20px; height: 20px; color: var(--Z); }
.tl-mark { position: absolute; top: 10px; width: 20px; height: 20px; border-radius: 50%; background: var(--R); transform: translateX(-50%); box-shadow: 0 0 0 4px var(--surface-2); }
.tl-ttl { position: absolute; top: 50%; margin-left: 12px; color: var(--ink-2); font: 500 12px/16px var(--sans); white-space: nowrap; transform: translateY(-50%); }
.tl-detail { min-height: 48px; margin-top: 24px; padding: 12px 16px; border: var(--dp-hairline) solid var(--border); border-radius: var(--r-control); background: var(--surface); color: var(--ink-2); font-size: var(--fs-small); line-height: 20px; overflow-wrap: anywhere; }
.tl-more { margin-top: 8px; padding-left: 12px; color: var(--muted); font-size: var(--fs-meta); }

/* Footer: closing passage */
.site-footer { border-top: 0; color: var(--ink-2); font-size: var(--fs-small); position: relative; }
.footer-top { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 64px; padding: 96px 0 64px; align-items: start; }
.final-cta h2 { max-width: 680px; font: 600 36px/40px var(--display); letter-spacing: -.03em; color: var(--ink); }
.final-cta p { max-width: 56ch; margin-top: 16px; color: var(--ink-2); font-size: var(--fs-body); line-height: 24px; }
.final-cta .button { margin-top: 32px; min-height: 48px; }
.footer-questions { margin: 0; padding: 0; list-style: none; }
.footer-questions li { border-top: var(--dp-hairline) solid var(--border-strong); }
.footer-questions li:last-child { border-bottom: var(--dp-hairline) solid var(--border-strong); }
.footer-questions a {
  display: grid; grid-template-columns: 48px minmax(0, 1fr); align-items: baseline; padding: 24px 0; color: var(--ink); text-decoration: none;
  font: 600 24px/32px var(--display); letter-spacing: -.02em; text-wrap: balance;
  transition: color var(--dur-2) var(--ease), transform var(--dur-3) var(--ease);
}
.footer-questions a:hover { color: var(--accent); transform: translateX(8px); }
.fq-no { color: var(--muted); font: 600 14px/20px var(--mono); }
.footer-mark { padding: 24px 0 0; color: var(--ink); font: 700 128px/1 var(--display); letter-spacing: -.04em; white-space: nowrap; overflow: hidden; user-select: none; grid-column: 1 / -1; }
.footer-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 32px 24px; padding: 48px 0 40px; border-top: var(--dp-hairline) solid var(--border-strong); }
.footer-group { min-width: 0; }
.footer-group h2 { margin-bottom: 16px; font: 600 12px/16px var(--sans); letter-spacing: .14em; font-variant-caps: all-small-caps; color: var(--muted); }
.footer-group p, .footer-group li { margin: 0 0 8px; overflow-wrap: anywhere; }
.footer-group ul { margin: 0; padding: 0; list-style: none; }
.footer-group .mono { color: var(--ink-2); }
.footer-links { display: flex; flex-wrap: wrap; align-items: center; gap: 12px 16px; }
.footer-links .button { min-height: 40px; font-size: var(--fs-small); }
.footer-note { padding: 24px 0 48px; border-top: var(--dp-hairline) solid var(--border); color: var(--muted); font-size: var(--fs-meta); }
.footer-note p { max-width: 86ch; }

/* Micro level: only under html[data-motion="on"], each at most 500 ms on the base curve */
html[data-motion="on"] .button.primary { position: relative; overflow: hidden; }
html[data-motion="on"] .button.primary::after {
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background: linear-gradient(105deg, transparent 35%, var(--accent-ink) 50%, transparent 65%); opacity: .28;
  transform: translateX(-120%); transition: transform var(--dur-3) var(--ease);
}
html[data-motion="on"] .button.primary:hover::after { transform: translateX(120%); }
html[data-motion="on"] .cred-chip, html[data-motion="on"] .scan-fact, html[data-motion="on"] .pill { transition: transform var(--dur-2) var(--ease), border-color var(--dur-2) var(--ease); }
html[data-motion="on"] .cred-chip:hover, html[data-motion="on"] .scan-fact:hover { transform: translateY(-1px); border-color: var(--border-strong); }
html[data-motion="on"] .finding:hover { transform: translateY(-2px); }
html[data-motion="on"] #findings-count.is-bump { animation: count-bump var(--dur-3) var(--ease) 1; }
html[data-motion="on"] .gnode.is-traced .gnode-halo { animation: trace-pulse 900ms cubic-bezier(.22, 1, .36, 1) 1; }
html[data-motion="on"] #trace-content > h3 { animation: rise-in var(--dur-3) var(--ease) 1; }
@keyframes count-bump { from { opacity: .4; transform: translateY(4px); } to { opacity: 1; transform: none; } }
@keyframes trace-pulse { from { opacity: .5; } to { opacity: .18; } }
@keyframes rise-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
html[data-motion="off"] *, html[data-motion="off"] *::before, html[data-motion="off"] *::after {
  transition: none !important; animation: none !important; scroll-behavior: auto !important;
}
html[data-motion="off"] .button:hover, html[data-motion="off"] .button:active, html[data-motion="off"] .footer-questions a:hover { transform: none !important; }
html[data-motion="off"] .js-words .tl-w { opacity: 1; }

@media (pointer: coarse) {
  .button, .graph-actions .button, .toolbar .button { min-height: 48px; }
  button.status { min-width: 36px; height: 36px; }
}
@media (min-width: 1051px) and (max-width: 1319px) {
  .band > .wrap, .page-head > .wrap { padding-left: 64px; }
}
@media (min-width: 1320px) {
  .journey-svg { left: max(4px, calc((100% - 1200px) / 2 - 64px)); }
}
@media (max-width: 1050px) {
  .wrap, .viewer-inner { padding-left: 32px; padding-right: 32px; }
  .viewer-schema { display: none; }
  .journey-svg { left: 2px; width: 14px; }
  .hero { gap: 40px; grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr); }
  .page-head { padding: 64px 0 48px; }
  .hero-copy h1 { font-size: 48px; line-height: 48px; }
  .stat { padding: 32px 16px; }
  .guide-card { padding: 24px; }
  .evidence-guide { gap: 40px; margin-top: 64px; }
  .steps { --cols: 3; gap: 48px 24px; }
  .steps.cols-4 { --cols: 3; }
  .steps.cols-4 .step:nth-child(4n) .step-link { display: block; }
  .steps.cols-4 .step:nth-child(3n) .step-link, .steps.cols-4 .step:nth-child(4n):last-child .step-link { display: none; }
  .footer-top { gap: 40px; }
  .footer-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .fact-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  section { padding-top: 80px; }
  .sec-no { font-size: 60px; }
  .section-head h2, .sec-title h2 { font-size: 36px; line-height: 40px; }
  .tagline-grid { gap: 32px; }
  .tagline-text { font-size: 36px; line-height: 40px; }
  .timeline { --tl-label: 200px; }
}
@media (max-width: 760px) {
  .wrap, .viewer-inner { padding-left: 24px; padding-right: 24px; }
  .brand-sub { display: none; }
  .hero { grid-template-columns: minmax(0, 1fr); gap: 40px; }
  .hero-copy { display: flex; flex-direction: column; }
  .hero-actions { order: 1; margin-top: 32px; }
  #finding-lead { order: 2; }
  .page-head { padding: 48px 0 40px; }
  .section-head, .disclosure > summary { grid-template-columns: auto minmax(0, 1fr); }
  .section-head .section-meta, .disclosure > summary .section-meta { grid-column: 1 / -1; text-align: left; max-width: none; }
  .sec-no { font-size: 48px; }
  .section-head h2, .sec-title h2 { font-size: 30px; line-height: 36px; }
  .disclosure > summary { padding: 24px 0; column-gap: 16px; }
  .disclosure > summary h2 { font-size: 24px; line-height: 32px; }
  .summary-band { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .stat, .stat:first-child { padding: 24px 16px 24px 0; border-left: 0; border-top: var(--dp-hairline) solid var(--border); }
  .stat:nth-child(2n) { padding-left: 16px; border-left: var(--dp-hairline) solid var(--border); }
  .stat:nth-child(-n+2) { border-top: 0; }
  .guide-grid { grid-template-columns: minmax(0, 1fr); }
  .evidence-guide { grid-template-columns: minmax(0, 1fr); gap: 24px; }
  .outcome-grid { grid-template-columns: minmax(0, 1fr); }
  .steps, .steps.cols-4, .steps.cols-3, .steps.cols-2 { --cols: 1; gap: 32px; }
  .steps .step { padding: 0 0 0 64px; min-height: 48px; }
  .steps .step .step-link, .steps.cols-4 .step:nth-child(4n) .step-link, .steps.cols-4 .step:nth-child(3n) .step-link { display: block; left: 0; top: 36px; width: 36px; height: calc(100% - 4px); }
  .steps .step:last-child .step-link, .steps.cols-4 .step:nth-child(4n):last-child .step-link { display: none; }
  .step-link .sl-h { display: none; }
  .step-link .sl-v { display: block; }
  .notes-list { grid-template-columns: minmax(0, 1fr); }
  .fact-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .kv div { grid-template-columns: minmax(0, 1fr); gap: 4px; }
  .field-search, .field-select { width: 100%; }
  .field { flex: 1 1 100%; }
  .toolbar-status { margin-left: 0; padding-bottom: 0; }
  section { padding-top: 64px; }
  .band > .wrap > section + section { margin-top: 32px; padding-top: 64px; }
  .tagline { padding: 96px 0 64px; }
  .tagline-grid { grid-template-columns: minmax(0, 1fr); }
  .tagline-text { font-size: 30px; line-height: 36px; }
  .tagline-rings { justify-self: start; max-width: 240px; }
  .footer-top { grid-template-columns: minmax(0, 1fr); padding: 64px 0 40px; }
  .footer-mark { font-size: 96px; }
  .timeline { --tl-label: 0px; }
  .tl-axis { margin-left: 0; }
  .tl-row { grid-template-columns: minmax(0, 1fr); padding-top: 8px; }
  .tl-name { padding: 0 12px; white-space: normal; }
  /* Menu toggle and full height panel */
  .nav-bar { top: 68px; height: 48px; }
  .nav-toggle {
    pointer-events: auto; position: relative; z-index: 80; display: inline-flex; align-items: center; gap: 12px; height: 40px; margin-top: 4px; padding: 0 16px 0 20px;
    border: var(--dp-hairline) solid var(--border); border-radius: 9999px; background: var(--nav-surface); color: var(--ink); box-shadow: var(--shadow-card);
    -webkit-backdrop-filter: blur(16px) saturate(1.5); backdrop-filter: blur(16px) saturate(1.5);
    font: 600 14px/20px var(--sans); cursor: pointer;
    transition: transform var(--dur-3) var(--ease);
  }
  .nav-toggle:active { transform: translateY(1px); }
  .nav-current { max-width: 52vw; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .nav-burger { position: relative; width: 18px; height: 12px; flex: none; }
  .nav-burger i { position: absolute; left: 0; width: 18px; height: 2px; border-radius: 2px; background: currentColor; transition: transform var(--dur-3) var(--ease), opacity var(--dur-2) var(--ease); }
  .nav-burger i:nth-child(1) { top: 0; }
  .nav-burger i:nth-child(2) { top: 5px; }
  .nav-burger i:nth-child(3) { top: 10px; }
  .nav-bar.is-open .nav-burger i:nth-child(1) { transform: translateY(5px) rotate(45deg); }
  .nav-bar.is-open .nav-burger i:nth-child(2) { opacity: 0; }
  .nav-bar.is-open .nav-burger i:nth-child(3) { transform: translateY(-5px) rotate(-45deg); }
  .toc {
    position: fixed; inset: 0; z-index: 70; display: block; margin: 0; padding: 96px 24px 48px; overflow-y: auto;
    border: 0; border-radius: 0; box-shadow: none; background: var(--nav-panel);
    -webkit-backdrop-filter: blur(24px); backdrop-filter: blur(24px);
    opacity: 0; visibility: hidden; pointer-events: none;
    transition: opacity var(--dur-2) var(--ease), visibility 0s linear var(--dur-2);
  }
  .nav-bar.is-open .toc { opacity: 1; visibility: visible; pointer-events: auto; transition-delay: 0s; }
  .toc-track { display: flex; flex-direction: column; gap: 0; overflow: visible; -webkit-mask-image: none; mask-image: none; }
  .toc a {
    height: auto; padding: 16px 0; border-radius: 0; border-bottom: var(--dp-hairline) solid var(--border);
    font: 600 24px/32px var(--display); letter-spacing: -.02em;
    opacity: 0; transform: translateY(24px);
    transition: transform var(--dur-3) var(--ease), opacity var(--dur-3) var(--ease);
  }
  .nav-bar.is-open .toc a { opacity: 1; transform: none; transition-delay: min(calc(var(--i, 0) * 60ms), 400ms); }
  .toc a:hover { background: none; color: var(--accent); }
  .toc a[aria-current="location"] { color: var(--accent); }
  .toc a:nth-of-type(1) { --i: 0; }
  .toc a:nth-of-type(2) { --i: 1; }
  .toc a:nth-of-type(3) { --i: 2; }
  .toc a:nth-of-type(4) { --i: 3; }
  .toc a:nth-of-type(5) { --i: 4; }
  .toc a:nth-of-type(6) { --i: 5; }
  .toc a:nth-of-type(7) { --i: 6; }
  .toc a:nth-of-type(8) { --i: 7; }
  .toc a:nth-of-type(9) { --i: 8; }
  .toc a:nth-of-type(10) { --i: 9; }
  .toc a:nth-of-type(11) { --i: 10; }
  .toc a:nth-of-type(12) { --i: 11; }
  .nav-indicator { display: none; }
  html.nav-locked { overflow: hidden; }
}
@media (max-width: 560px) {
  .wrap, .viewer-inner { padding-left: 20px; padding-right: 20px; }
  .viewer-meta, #print-button { display: none; }
  .brand-name { display: none; }
  .scan-facts { flex-wrap: nowrap; overflow-x: auto; margin-right: -20px; padding-right: 20px; scrollbar-width: none; }
  .scan-facts::-webkit-scrollbar { display: none; }
  .scan-fact { flex: none; }
  .theme-host { margin-left: auto; }
  .theme-icon { display: none; }
  .theme-option { padding: 0 8px; }
  .graph-head { width: calc(100vw - 40px); }
  .graph-stage { height: 30rem; }
  .graph-actions { order: 2; }
  .graph-legend { order: 1; }
  .footer-mark { font-size: 72px; }
  .nav-bar { padding: 0 20px; }
}
@media (max-width: 480px) {
  .wrap, .viewer-inner { padding-left: 16px; padding-right: 16px; }
  .graph-head { width: calc(100vw - 32px); }
  .hero-copy h1 { font-size: 36px; line-height: 40px; }
  .section-head h2, .sec-title h2 { font-size: 24px; line-height: 32px; }
  .sec-no { font-size: 36px; }
  .cmp-item { padding: 16px; }
  .cmp-fact { grid-template-columns: minmax(0, 1fr); gap: 2px; }
  .guide-card { padding: 24px; }
  .class-list { grid-template-columns: minmax(0, 1fr); }
  .stat-value { font-size: 40px; }
  .stat, .stat:first-child { padding: 24px 12px 24px 0; }
  .stat:nth-child(2n) { padding-left: 12px; }
  .outcome { padding: 16px; }
  .fact-grid { grid-template-columns: minmax(0, 1fr); gap: 16px; }
  thead th, tbody td, tbody th { padding: 8px; }
  .footer-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 32px 16px; padding-top: 48px; }
  .hero-actions .button, .pick { flex: 1 1 100%; max-width: none; }
  .hero-figure { padding: 16px; border-radius: 16px; }
  .footer-mark { font-size: 48px; }
  .footer-questions a { font-size: 20px; line-height: 28px; grid-template-columns: 40px minmax(0, 1fr); }
  .tagline-text { font-size: 24px; line-height: 32px; }
  .nav-bar { padding: 0 16px; }
}
@media (max-width: 400px) {
  .motion-label { position: absolute; width: 1px; height: 1px; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
  .motion-switch { padding: 0 12px 0 8px; }
}
@media (max-width: 360px) {
  .footer-grid { grid-template-columns: minmax(0, 1fr); }
  .theme-option { padding: 0 6px; font-size: 11.5px; }
  .viewer-inner { gap: 8px; }
}
@media (prefers-reduced-motion: reduce) {
  :root { --dur-1: 1ms; --dur-2: 1ms; --dur-3: 1ms; --dp-motion: 1ms linear; }
  html { scroll-behavior: auto; }
  .button, .button:hover, .button:active { transition: none; transform: none; }
  summary::before { transition: none; }
}
@media (forced-colors: active) {
  .hero-copy h1 { background: none; -webkit-text-fill-color: currentColor; color: CanvasText; }
}
__EFFECTS_CSS__
@page { size: A4 portrait; margin: 13mm 11mm; }
@page graph { size: A3 landscape; margin: 10mm; }
@media print {
  .viewer-bar { position: static; border-bottom: 1px solid #000; }
  .viewer-meta, .theme-host, .motion-host, #print-button, .hero-actions, .hero-figure, .nav-bar, .journey-svg, .hero-field, .passage-field, .tagline-rings, .footer-mark, .timeline, #boot-status, .toolbar, .skip-link, .outcome-more, .scroll-hint, .graph-actions, #graph-note, #entity-details, .footer-links { display: none; }
  .wrap { max-width: none; padding: 0; }
  body { font-size: 10pt; background: #fff; color: #000; }
  h1 { font-size: 26pt; }
  h2 { font-size: 17pt; }
  .page-head { padding: 0 0 12pt; }
  .hero { display: block; }
  section, .band > .wrap > section:last-child, .band > .wrap > section + section { padding: 18pt 0 0; margin: 0; border-top: 1px solid #ddd; scroll-margin-top: 0; }
  .band, .band-pale, .band.passage, .passage { background: #fff; border: 0; }
  .lead, .guide-card, .stat, .outcome, .finding, .cmp-list, .graph-frame, .hero-figure { box-shadow: none; }
  #rotation { break-inside: avoid; }
  h2, h3, h4 { break-after: avoid; }
  .section-head { break-inside: avoid; break-after: avoid; }
  .section-head + div { break-before: avoid; }
  summary { border: 1px solid #bbb; list-style: none; cursor: default; }
  .stat, .step, .outcome, .kv, .guide-card { break-inside: avoid; }
  #survival { break-before: page; }
  .finding { break-inside: auto; }
  .finding-head, .finding-rule, .finding-message { break-after: avoid; }
  .table-wrap { break-inside: auto; }
  #survival .table-wrap, #matrix .table-wrap { break-inside: avoid; }
  thead { break-after: avoid; }
  .outcome-grid, .table-hint, .scroll-hint { display: none; }
  .finding:hover, tbody tr:hover td, tbody tr:hover th { background: transparent; }
  .stat-value { font-size: 28pt; }
  .steps { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .survival-rail span { transform: none; opacity: 1; }
  .table-wrap, .matrix-wrap { overflow: visible; max-height: none; }
  #graph { page: graph; break-before: page; break-after: page; position: static; left: auto; width: auto; margin-left: 0;
    display: flex; flex-direction: column; min-height: 250mm; }
  .graph-head { width: auto; margin: 0; }
  .graph-frame { overflow: visible; border: 0; border-radius: 0; margin-block: auto; background: #fff; }
  .graph-stage { height: auto; overflow: visible; background: none; cursor: default; }
  .graph-viewport { position: static; transform: none !important; }
  .graph-svg { width: 100% !important; height: auto !important; max-height: 260mm; }
  .gnode.is-outside, .gnode.is-selected, .gnode.is-neighbor, .gnode.is-traced { opacity: 1 !important; }
  .gedge.is-outside, .gedge.is-selected-edge, .gedge.is-traced { opacity: 1 !important; }
  .graph-stage.is-tracing .gnode:not(.is-traced),
  .graph-stage.is-tracing .gedge:not(.is-traced),
  .graph-stage.has-selection .gnode:not(.is-selected):not(.is-neighbor),
  .graph-stage.has-selection .gedge:not(.is-incident) { opacity: 1 !important; }
  table, .table-wrap table.wide { min-width: 0; font-size: 8.5pt; }
  thead { display: table-header-group; }
  tr { break-inside: avoid; }
  th, td { padding: 6px 8px; white-space: normal; overflow-wrap: anywhere; }
  td.nowrap { white-space: normal; }
  a { text-decoration: none; }
}
</style>
<noscript><style>html.booting body > :not(#boot-status):not(script) { visibility: visible; } #boot-status { display: none; }</style></noscript>
</head>
<body>
__ICON_SPRITE__
<div id="boot-status" role="status" aria-live="polite">Reading the embedded report data…<div class="boot-skeleton" aria-hidden="true"><i class="sk sk-title"></i><i class="sk sk-title short"></i><i class="sk sk-line"></i><div class="sk-row"><i class="sk sk-stat"></i><i class="sk sk-stat"></i><i class="sk sk-stat"></i><i class="sk sk-stat"></i><i class="sk sk-stat"></i></div></div></div>
<a class="skip-link" href="#main">Skip to report content</a>
<div class="viewer-bar" role="region" aria-label="Report controls">
  <div class="viewer-inner">
    <a class="brand" href="#top">
      <svg class="brand-mark" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <circle cx="12" cy="12" r="2.2" fill="currentColor"></circle>
        <path d="M12 5.4a6.6 6.6 0 0 1 0 13.2M12 2.2a9.8 9.8 0 0 1 0 19.6" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" opacity=".55"></path>
      </svg>
      <span class="brand-name">NHI-Blast</span>
      <span class="brand-sub">Incident exposure report</span>
    </a>
    <div class="viewer-meta">
      <span class="viewer-chip">Offline</span>
      <span class="viewer-schema mono" id="schema-line"></span>
    </div>
    <div class="theme-host" id="theme-switch-host"></div>
    <div class="motion-host" id="motion-switch-host"></div>
    <button type="button" class="button quiet" id="print-button">Print / PDF</button>
  </div>
</div>
<header class="page-head" id="top">
  <div class="hero-field" data-fx-halftone="hero" aria-hidden="true"></div>
  <div class="wrap">
    <div class="hero">
      <div class="hero-copy">
        <h1>Incident exposure report</h1>
        <p class="hero-sub">What a compromised entrypoint could reach, what survives its revocation and the order to rotate.</p>
        <ul class="scan-facts" id="source-line" aria-label="Scan facts"></ul>
        <div id="finding-lead"></div>
        <div class="hero-actions">
          <div class="pick">
            <label class="field-label" for="scenario-picker">Entrypoint</label>
            <div class="select-wrap"><select id="scenario-picker"></select></div>
            <span class="field-hint" id="scenario-count"></span>
          </div>
          <a class="button primary" href="#rotation">Review rotation order</a>
          <a class="button secondary" id="all-findings" href="#findings" hidden>All findings</a>
        </div>
      </div>
      <figure class="hero-figure" id="hero-diagram" aria-labelledby="hero-diagram-text">
        <div id="hero-diagram-host"></div>
        <figcaption class="sr-only" id="hero-diagram-text"></figcaption>
      </figure>
    </div>
  </div>
</header>
<div class="nav-bar" id="nav-bar">
  <button type="button" class="nav-toggle" id="nav-toggle" aria-expanded="false" aria-controls="nav-panel">
    <span class="nav-current" id="nav-current">Summary</span>
    <span class="nav-burger" aria-hidden="true"><i></i><i></i><i></i></span>
    <span class="sr-only">Menu</span>
  </button>
  <nav class="toc" id="nav-panel" aria-label="Report sections">
    <div class="toc-track" id="toc-track">
        <a href="#summary">Summary</a>
        <a href="#read-guide">How to read</a>
        <a id="completeness-link" href="#completeness" hidden>Completeness</a>
        <a href="#survival">Survival</a>
        <a href="#rotation">Rotation</a>
        <a id="matrix-link" href="#matrix" hidden>Exposure matrix</a>
        <a href="#graph">Graph</a>
        <a href="#findings">Findings</a>
        <a href="#scenario">Scenario</a>
        <a href="#assumptions">Assumptions</a>
        <a href="#diagnostics">Diagnostics</a>
        <a href="#scope">Scope</a>
        <span class="nav-indicator" aria-hidden="true"></span>
    </div>
  </nav>
</div>
<main id="main">
  <svg class="journey-svg" data-fx-journey aria-hidden="true" focusable="false"></svg>
  <noscript><p class="notice">This report needs JavaScript enabled to display its embedded data. It makes no network requests.</p></noscript>
  <div class="band band-facts"><div class="wrap">
    <section id="summary" aria-labelledby="summary-title">
      <h2 class="sr-only" id="summary-title">Summary</h2>
      <p class="sr-only" id="summary-context"></p>
      <div class="summary-band" id="summary-grid" data-light></div>
      <p class="summary-brief" id="summary-brief"></p>
    </section>
  </div></div>
  <div class="band band-pale"><div class="wrap">
    <section id="read-guide" aria-labelledby="read-guide-title">
      <div class="section-head" data-fx-stop>
        <span class="sec-no" aria-hidden="true">01</span>
        <div class="sec-title"><span class="sec-label">Orientation</span><h2 id="read-guide-title">How to read this report</h2></div>
        <p class="section-meta">Three outcomes, four evidence classes</p>
      </div>
      <div class="guide-grid">
        <div class="guide-card">
          <h3><span class="code code-R">R</span>Ends with the entrypoint</h3>
          <p>Credentials tied to the compromised job or run. They end with the job or at token expiry, not necessarily when entrypoint access is revoked.</p>
        </div>
        <div class="guide-card">
          <h3><span class="code code-E">E</span>Expires on its own</h3>
          <p>Credentials with a recorded lifetime, such as a role session with a time-to-live. They lapse without action, but stay usable until they do.</p>
        </div>
        <div class="guide-card">
          <h3><span class="code code-Z">Z</span>Potentially survives</h3>
          <p>Stored credentials that are potentially reachable from the entrypoint and stay valid after it is revoked, if the recorded path was exercised. The rotation plan is ordered around these.</p>
        </div>
      </div>
      <div class="evidence-guide">
        <div>
          <h3>Evidence classes</h3>
          <p>Every node and edge carries an evidence class. Severity is a label for ordering, not a verdict. In the graph, solid lines are declared or derived, dashed lines are assumed and dotted lines are unknown.</p>
        </div>
        <ul class="class-list">
          <li><strong>DECLARED</strong><span>Stated directly in a scanned file such as a workflow, Terraform or IAM document.</span></li>
          <li><strong>DERIVED</strong><span>Computed from declared facts by a documented rule, for example by evaluating a trust policy as written.</span></li>
          <li><strong>ASSUMED</strong><span>Filled in from a listed assumption where the files are silent. Assumptions are listed in the report.</span></li>
          <li><strong>UNKNOWN</strong><span>Could not be resolved. Shown separately as potential and never counted in R, E or Z.</span></li>
        </ul>
      </div>
    </section>
    <section id="completeness" aria-labelledby="completeness-title" hidden>
      <div class="section-head" data-fx-stop>
        <span class="sec-no" aria-hidden="true">02</span>
        <div class="sec-title"><span class="sec-label">Coverage</span><h2 id="completeness-title">Analysis completeness</h2></div>
        <p class="section-meta">Which inputs each family of checks could read</p>
      </div>
      <div id="completeness-content"></div>
    </section>
  </div></div>
  <div class="band band-plain band-tagline"><div class="wrap">
    <section id="tagline" class="tagline" aria-label="What this report is for">
      <div class="tagline-grid">
        <p class="tagline-text" id="tagline-text">Know what survives revocation. Rotate in the order that keeps the next secret safe. Every claim carries its evidence, and every gap is listed.</p>
        <svg class="tagline-rings" viewBox="0 0 360 360" aria-hidden="true" focusable="false"><circle cx="180" cy="180" r="172"></circle><circle cx="180" cy="180" r="128"></circle><circle cx="180" cy="180" r="84"></circle><circle class="core" cx="180" cy="180" r="12"></circle></svg>
      </div>
    </section>
  </div></div>
  <div class="band band-dark passage" id="passage-survival" data-fx-spotlight><div class="passage-field" data-fx-halftone="field" aria-hidden="true"></div><div class="wrap">
    <section id="survival" aria-labelledby="survival-title">
      <div class="section-head" data-fx-stop>
        <span class="sec-no" aria-hidden="true">03</span>
        <div class="sec-title"><span class="sec-label">Outcome</span><h2 id="survival-title">Survival panel</h2></div>
        <p class="section-meta">R / E / Z as recorded by the analysis</p>
      </div>
      <div id="survival-content"></div>
    </section>
    <section id="rotation" aria-labelledby="rotation-title">
      <div class="section-head" data-fx-stop>
        <span class="sec-no" aria-hidden="true">04</span>
        <div class="sec-title"><span class="sec-label">Action plan</span><h2 id="rotation-title">Rotation plan</h2></div>
        <p class="section-meta">Contain, rotate, verify</p>
      </div>
      <div id="rotation-content"></div>
    </section>
    <section id="matrix" aria-labelledby="matrix-title" hidden>
      <div class="section-head">
        <div class="sec-title"><span class="sec-label">Across entrypoints</span><h2 id="matrix-title">Cross-scenario exposure</h2></div>
        <p class="section-meta">One credential per row, one entrypoint per column</p>
      </div>
      <p class="muted matrix-summary" id="matrix-summary"></p>
      <div class="matrix-legend" role="group" aria-label="Credential status codes">
        <span><b class="code code-R">R</b> ends with the revoked entrypoint</span>
        <span><b class="code code-E">E</b> expires on its own</span>
        <span><b class="code code-Z">Z</b> potentially survives revocation</span>
        <span><b class="code code-P">P</b> potential only through an UNKNOWN-class edge</span>
      </div>
      <div class="toolbar">
        <label class="field-label">
          <input type="checkbox" id="matrix-shared">
          Only credentials listed in more than one scenario
        </label>
      </div>
      <div id="matrix-content"></div>
    </section>
  </div></div>
  <div class="band band-plain"><div class="wrap">
    <section id="graph" aria-labelledby="graph-title">
      <div class="graph-head">
        <div class="section-head" data-fx-stop>
        <span class="sec-no" aria-hidden="true">05</span>
        <div class="sec-title"><span class="sec-label">Map</span><h2 id="graph-title">Graph</h2></div>
          <p class="section-meta" id="graph-count">Authority paths by stage</p>
        </div>
        <div class="graph-toolbar">
          <div class="graph-legend" role="group" aria-label="Evidence line styles and entrypoints">
            <span class="solid"><i></i>DECLARED / DERIVED</span>
            <span class="dashed"><i></i>ASSUMED</span>
            <span class="dotted"><i></i>UNKNOWN</span>
            <span class="entry"><i></i>ENTRYPOINT</span>
          </div>
          <div class="graph-actions" role="group" aria-label="Graph view controls">
            <button class="button quiet" id="graph-zoom-out" type="button" aria-label="Zoom out">&minus;</button>
            <button class="button quiet" id="graph-zoom-level" type="button" aria-label="Reset zoom to 100 percent">100%</button>
            <button class="button quiet" id="graph-zoom-in" type="button" aria-label="Zoom in">+</button>
            <button class="button quiet" id="graph-fit" type="button">Fit</button>
          </div>
        </div>
      </div>
      <div class="graph-frame">
        <div class="graph-stage" id="graph-stage" role="group"
          aria-label="Authority graph. Keyboard: arrow keys move between nodes, Enter selects, Escape clears.">
          __GRAPH_SVG__
        </div>
      </div>
      <p id="graph-note">The selected entrypoint's reachable path is highlighted; unrelated nodes are dimmed. Tab into the graph; arrow keys move, Enter selects, Escape clears. Drag or pinch to pan and zoom; Ctrl + wheel also zooms; the controls set an exact level. Fit shows the whole graph; dense graphs open at 100% on the first entrypoint. The graph is a visual aid; the scenario, survival and findings sections carry the same evidence as text.</p>
      <div id="entity-details" aria-live="polite"></div>
    </section>
    <section id="findings" aria-labelledby="findings-title">
      <div class="section-head" data-fx-stop>
        <span class="sec-no" aria-hidden="true">06</span>
        <div class="sec-title"><span class="sec-label">Triage</span><h2 id="findings-title">Findings</h2></div>
        <p class="section-meta">Ordered by severity, then rule and identifier</p>
      </div>
      <div class="toolbar" role="group" aria-label="Filter findings">
        <div class="field field-search">
          <label for="finding-search">Filter</label>
          <input type="search" id="finding-search" autocomplete="off" spellcheck="false"
            placeholder="Rule, title, scenario, evidence">
        </div>
        <div class="field field-select">
          <label for="finding-severity">Severity</label>
          <select id="finding-severity"></select>
        </div>
        <div class="field field-select">
          <label for="finding-scenario">Scenario</label>
          <select id="finding-scenario"></select>
        </div>
        <button type="button" class="button quiet" id="finding-clear">Clear filters</button>
        <span id="findings-count" class="toolbar-status" role="status" aria-live="polite"></span>
      </div>
      <div id="findings-content"></div>
    </section>
  </div></div>
  <div class="band band-pale"><div class="wrap">
    <section id="scenario" class="section-disclosure" aria-labelledby="scenario-title">
      <details class="disclosure">
        <summary data-fx-stop>
          <span class="sec-no" aria-hidden="true">07</span>
          <span class="sec-title"><span class="sec-label">Inputs</span><h2 id="scenario-title">Scenario</h2></span>
          <span class="section-meta">Start nodes and recorded inputs</span>
        </summary>
        <div class="disclosure-body">

          <div id="scenario-content"></div>
          <div id="trace-content" aria-live="polite"></div>
        </div>
      </details>
    </section>
    <section id="assumptions" class="section-disclosure" aria-labelledby="assumptions-title">
      <details class="disclosure">
        <summary data-fx-stop>
          <span class="sec-no" aria-hidden="true">08</span>
          <span class="sec-title"><span class="sec-label">Limits</span><h2 id="assumptions-title">Assumptions and Unknowns</h2></span>
          <span class="section-meta">VERIFY items remain assumed until confirmed</span>
        </summary>
        <div class="disclosure-body">

          <div id="assumptions-content"></div>
        </div>
      </details>
    </section>
    <section id="diagnostics" class="section-disclosure" aria-labelledby="diagnostics-title">
      <details class="disclosure">
        <summary data-fx-stop>
          <span class="sec-no" aria-hidden="true">09</span>
          <span class="sec-title"><span class="sec-label">Parser notes</span><h2 id="diagnostics-title">Diagnostics</h2></span>
          <span class="section-meta">Parse and analysis messages</span>
        </summary>
        <div class="disclosure-body">

          <div id="diagnostics-content"></div>
        </div>
      </details>
    </section>
  </div></div>
  <div class="band band-dark passage" id="passage-scope" data-fx-spotlight><div class="passage-field" data-fx-halftone="field" aria-hidden="true"></div><div class="wrap">
    <section id="scope" aria-labelledby="scope-title">
      <div class="section-head" data-fx-stop>
        <span class="sec-no" aria-hidden="true">10</span>
        <div class="sec-title"><span class="sec-label">Boundary</span><h2 id="scope-title">Scope and Limits</h2></div>
        <p class="section-meta">Inputs, coverage and the analysis boundary</p>
      </div>
      <div id="scope-content"></div>
    </section>
  </div></div>
</main>
<footer class="site-footer passage">
  <div class="wrap">
    <div class="footer-top">
      <div class="final-cta">
        <h2>Start with the credentials that survive.</h2>
        <p>The rotation plan orders them so that a surviving credential cannot re-read a freshly rotated one.</p>
        <a class="button primary" href="#rotation">Review rotation order</a>
      </div>
      <ol class="footer-questions" aria-label="What the report answers">
        <li><a href="#graph"><span class="fq-no" aria-hidden="true">A</span>What could the compromised entrypoint reach?</a></li>
        <li><a href="#survival"><span class="fq-no" aria-hidden="true">B</span>What survives its revocation?</a></li>
        <li><a href="#rotation"><span class="fq-no" aria-hidden="true">C</span>In what order do I rotate?</a></li>
      </ol>
      <div class="footer-mark" aria-hidden="true">NHI-Blast</div>
    </div>
    <div class="footer-grid">
      <div class="footer-group">
        <h2>Report</h2>
        <p id="tool-line"></p>
        <p id="repo-line"></p>
        <p class="mono" id="footer-schema"></p>
      </div>
      <div class="footer-group">
        <h2>Inputs digest</h2>
        <p class="mono" id="footer-digest"></p>
        <p id="footer-copy-host"></p>
        <p>Offline: no network requests. The theme and motion choices stay in this tab only.</p>
      </div>
      <div class="footer-group">
        <h2>Data files</h2>
        <ul id="footer-data"></ul>
      </div>
      <div class="footer-group">
        <h2>Go to</h2>
        <div class="footer-links">
          <a href="#completeness" id="footer-completeness" hidden>Analysis completeness</a>
          <button type="button" class="button quiet" id="footer-print">Print / PDF</button>
          <a href="#top" class="button secondary">Back to top</a>
        </div>
      </div>
    </div>
    <div class="footer-note">
      <p>Offline report generated by NHI-Blast. Evidence classes are labels, not proof of exploitation.</p>
    </div>
  </div>
</footer>
__SCRIPTS__
</body>
</html>
"""

TEMPLATE = (
    _TEMPLATE_SOURCE.replace("__THEME_TOKENS__", THEME_TOKENS_CSS)
    .replace("__THEME_SWITCH_CSS__", THEME_SWITCH_CSS)
    .replace("__EFFECTS_CSS__", EFFECTS_CSS)
)

_APP_JS_SOURCE = r"""(function () {
  "use strict";
  let bootComplete = false;
  function reportBootFailure() {
    if (bootComplete) { return; }
    bootComplete = true;
    const status = document.getElementById("boot-status");
    if (status) {
      status.textContent =
        "The embedded report data could not be read. Regenerate the report from the NHI-Blast CLI.";
    }
    document.documentElement.classList.remove("booting");
    document.documentElement.classList.add("boot-failed");
  }
  window.addEventListener("error", reportBootFailure);
  const bootFallback = window.setTimeout(reportBootFailure, 4000);
  try {
    if (window.NHBTheme && typeof window.NHBTheme.mount === "function") {
      window.NHBTheme.mount(document.getElementById("theme-switch-host"));
      window.NHBTheme.mountMotion(document.getElementById("motion-switch-host"));
    }
  } catch (error) {
    // The theme control is optional chrome; the report content must not depend on it.
  }
  const report = JSON.parse(document.getElementById("report-data").textContent);
  const nodes = new Map((report.graph.nodes || []).map((item) => [item.id, item]));
  const edges = new Map((report.graph.edges || []).map((item) => [item.id, item]));
  const adjacency = new Map();
  (report.graph.edges || []).forEach((edge) => {
    if (!adjacency.has(edge.src)) { adjacency.set(edge.src, []); }
    adjacency.get(edge.src).push(edge);
  });
  adjacency.forEach((outgoing) => {
    outgoing.sort((left, right) => left.id < right.id ? -1 : left.id > right.id ? 1 : 0);
  });
  const scenarios = report.scenarios || [];
  const severityOrder = {CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, INFO: 4};
  const findings = (report.findings || []).slice().sort((left, right) => {
    const order = severityOrder[left.severity] - severityOrder[right.severity];
    if (order !== 0) { return order; }
    if (left.rule !== right.rule) { return left.rule < right.rule ? -1 : 1; }
    return left.id < right.id ? -1 : left.id > right.id ? 1 : 0;
  });
  let currentScenarioIndex = 0;
  let graphView = null;
  let graphSelection = null;
  const entryIds = new Set();
  scenarios.forEach((scenario) => {
    (scenario.start_nodes || []).forEach((id) => entryIds.add(id));
  });

  function prefersReducedMotion() {
    return Boolean(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  const motion = window.Motion && typeof window.Motion.animate === "function"
    ? window.Motion
    : null;
  function motionEnabled() {
    return window.NHBTheme ? window.NHBTheme.getMotion() : !prefersReducedMotion();
  }

  const presenceAnimations = new Map();
  function clearPresence(item) {
    const running = presenceAnimations.get(item);
    if (running) { running.cancel(); presenceAnimations.delete(item); }
    item.style.opacity = "";
    item.style.transform = "";
  }
  function syncMotion(on) {
    if (motion && motion.MotionGlobalConfig) { motion.MotionGlobalConfig.skipAnimations = !on; }
    if (!on) { Array.from(presenceAnimations.keys()).forEach(clearPresence); }
  }
  syncMotion(motionEnabled());
  if (window.NHBTheme) { window.NHBTheme.subscribeMotion(syncMotion); }

  function animatePresence(item) {
    clearPresence(item);
    if (!motion || !motionEnabled()) { return; }
    item.style.opacity = "0";
    const control = motion.animate(item, {
      opacity: [0, 1],
      transform: ["translateY(6px)", "translateY(0px)"]
    }, {
      duration: 0.2,
      ease: [0.22, 1, 0.36, 1],
      onComplete: () => {
        presenceAnimations.delete(item);
        item.style.opacity = "";
        item.style.transform = "";
      }
    });
    presenceAnimations.set(item, control);
  }

  function clear(container) {
    container.replaceChildren();
  }

  function writeText(item, className, value) {
    const text = String(value);
    if (
      className &&
      /(?:^|\s)(?:mono|wrap|evidence|cell-id|finding-rule)(?:\s|$)/.test(className) &&
      text.length > 18
    ) {
      let start = 0;
      for (let index = 0; index < text.length; index += 1) {
        const separator = ":/#_-".indexOf(text[index]) !== -1;
        const nextIsSeparator = index + 1 < text.length && ":/#_-".indexOf(text[index + 1]) !== -1;
        if (separator && !nextIsSeparator && index + 1 < text.length) {
          item.appendChild(document.createTextNode(text.slice(start, index + 1)));
          item.appendChild(document.createElement("wbr"));
          start = index + 1;
        }
      }
      item.appendChild(document.createTextNode(text.slice(start)));
      return;
    }
    item.textContent = text;
  }

  function element(tag, className, text) {
    const item = document.createElement(tag);
    if (className) { item.className = className; }
    if (text !== undefined && text !== null) { writeText(item, className, text); }
    return item;
  }

  function append(parent, tag, className, text) {
    const item = element(tag, className, text);
    parent.appendChild(item);
    return item;
  }

  function textOf(value) {
    return value === undefined || value === null ? "" : String(value);
  }

  function safeId(value) {
    return textOf(value).replace(/[^A-Za-z0-9_-]/g, "_");
  }

  function plural(count, singular, pluralForm) {
    return count + " " + (count === 1 ? singular : pluralForm || singular + "s");
  }

  function evidenceLabel(evidence) {
    const cls = textOf(evidence.cls);
    const rule = textOf(evidence.rule);
    const file = textOf(evidence.file);
    const line = evidence.line === undefined || evidence.line === null ? "" : ":" + evidence.line;
    const detail = textOf(evidence.detail);
    const parts = [cls, rule];
    if (file) { parts.push(file + line); }
    if (detail) { parts.push(detail); }
    return parts.filter(Boolean).join(" ");
  }

  function evidenceList(container, evidence) {
    if (!evidence || evidence.length === 0) {
      append(container, "p", "empty", "No evidence record is attached.");
      return;
    }
    const list = append(container, "ul", "evidence-list");
    evidence.forEach((item) => append(list, "li", "evidence", evidenceLabel(item)));
  }

  function nodeLabel(id) {
    const item = nodes.get(id);
    return item ? item.label + " (" + item.id + ")" : textOf(id);
  }

  function nodeEvidence(id) {
    const item = nodes.get(id);
    if (!item || !item.evidence || !item.evidence.length) { return ""; }
    return evidenceLabel(item.evidence[0]);
  }

  function addColumns(table, widths) {
    const columns = append(table, "colgroup");
    widths.forEach((width) => {
      append(columns, "col").style.width = width;
    });
  }

  function watchOverflow(scroll) {
    const hint = element("p", "scroll-hint", "Scroll sideways for all columns");
    hint.hidden = true;
    scroll.parentNode.insertBefore(hint, scroll);
    let resize = null;
    let mutations = null;
    const sync = () => {
      if (!scroll.isConnected) {
        if (resize) { resize.disconnect(); }
        if (mutations) { mutations.disconnect(); }
        return;
      }
      const more = scroll.scrollWidth - scroll.clientWidth > 2;
      const atEnd = scroll.scrollLeft + scroll.clientWidth >= scroll.scrollWidth - 2;
      hint.hidden = !more || atEnd;
    };
    scroll.addEventListener("scroll", sync, { passive: true });
    if (window.ResizeObserver) {
      resize = new ResizeObserver(sync);
      resize.observe(scroll);
    }
    if (window.MutationObserver && scroll.firstElementChild) {
      mutations = new MutationObserver(sync);
      mutations.observe(scroll.firstElementChild, { childList: true, subtree: true });
    }
    sync();
  }

  function tableRegion(container, caption) {
    const scroll = append(container, "div", "table-wrap");
    scroll.tabIndex = 0;
    scroll.setAttribute("role", "region");
    scroll.setAttribute("aria-label", caption);
    const table = append(scroll, "table");
    watchOverflow(scroll);
    return table;
  }

  function addTable(container, caption, headings, rows, aligns, widths) {
    if (!rows.length) {
      append(container, "p", "empty", "No entries.");
      return;
    }
    const table = tableRegion(container, caption);
    table.className = headings.length >= 6 ? "wide" : "";
    append(table, "caption", "", caption);
    if (widths) { addColumns(table, widths); }
    const head = append(table, "thead");
    const headRow = append(head, "tr");
    headings.forEach((heading, index) => {
      const numeric = aligns && aligns[index] === "num";
      const cell = append(headRow, "th", numeric ? "num" : "", heading);
      cell.scope = "col";
    });
    const body = append(table, "tbody");
    rows.forEach((row) => {
      const tr = append(body, "tr");
      row.forEach((value, index) => {
        const align = aligns && aligns[index] ? aligns[index] : "";
        const suffix = align === "num" ? " num" : align === "nowrap" ? " nowrap" : "";
        const cell = append(tr, "td", "wrap" + suffix);
        if (value && typeof value === "object" && typeof value.nodeType === "number") {
          cell.appendChild(value);
        } else {
          writeText(cell, cell.className, textOf(value));
        }
      });
    });
  }

  function credentialCell(id) {
    const item = nodes.get(id);
    const wrap = element("div");
    wrap.appendChild(traceButton(id, item ? item.label : id));
    const line = append(wrap, "span", "cell-id");
    String(id).split(/([/_.:])/).forEach((part) => {
      if (!part) { return; }
      line.appendChild(document.createTextNode(part));
      if (/^[/_.:]$/.test(part)) { line.appendChild(document.createElement("wbr")); }
    });
    return wrap;
  }

  function joinParts(parts) {
    return parts.map(textOf).filter((part) => part.length > 0).join(" · ");
  }

  function nodeWhere(id) {
    const item = nodes.get(id);
    if (!item || !item.attrs) { return ""; }
    if (item.attrs.job) { return textOf(item.attrs.job).replace(/^job:/, ""); }
    return textOf(item.attrs.sink);
  }

  function credentialHeading(id) {
    const item = nodes.get(id);
    const label = item ? item.label : textOf(id);
    const job = item && item.attrs ? textOf(item.attrs.job) : "";
    if (!job) { return label; }
    const path = job.replace(/^job:/, "");
    return label + " · " + path.slice(path.lastIndexOf("/") + 1);
  }

  function fallbackCopy(text) {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    let done = false;
    try { done = document.execCommand("copy"); } catch (error) { done = false; }
    area.remove();
    return done;
  }

  function copyText(text) {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      return navigator.clipboard.writeText(text).then(() => true, () => fallbackCopy(text));
    }
    return Promise.resolve(fallbackCopy(text));
  }

  function copyButton(parent, text, label) {
    const button = append(parent, "button", "copy-button");
    button.setAttribute("type", "button");
    button.setAttribute("aria-label", label);
    const icon = svgNode(button, "svg", { "class": "icon", "aria-hidden": "true", focusable: "false" });
    const use = svgNode(icon, "use", { href: "#i-copy" });
    const word = append(button, "span", "", "Copy");
    const status = append(parent, "span", "sr-only");
    status.setAttribute("role", "status");
    let timer = 0;
    button.addEventListener("click", () => {
      copyText(text).then((done) => {
        word.textContent = done ? "Copied" : "Copy failed";
        use.setAttribute("href", done ? "#i-check" : "#i-info");
        status.textContent = done ? "Copied to the clipboard." : "The browser blocked copying. Select the text instead.";
        window.clearTimeout(timer);
        timer = window.setTimeout(() => {
          word.textContent = "Copy";
          use.setAttribute("href", "#i-copy");
          status.textContent = "";
        }, 1800);
      });
    });
    return button;
  }

  function renderSourceLine() {
    const target = document.getElementById("source-line");
    clear(target);
    const digest = textOf(report.inputs.digest);
    const files = (report.inputs.files || []).length;
    const verified = (report.data_files || []).map((item) => textOf(item.verified_on)).filter(Boolean).sort();
    const facts = [
      ["Repository", textOf(report.inputs.repo_slug), null],
      ["Inputs", plural(files, "file"), null],
      verified.length ? ["Data verified", verified[verified.length - 1], null] : null,
      ["Schema", textOf(report.schema), null],
      ["Snapshot", report.generated_at ? "generated " + report.generated_at : "no timestamp", null],
      ["Digest", digest.length > 12 ? digest.slice(0, 12) + "…" : digest, digest]
    ].filter(Boolean);
    facts.forEach((fact) => {
      const item = append(target, "li", "scan-fact");
      append(item, "span", "k", fact[0]);
      append(item, "span", "v", fact[1]);
      if (fact[2]) { copyButton(item, fact[2], "Copy inputs digest"); }
    });
  }

  function renderScope() {
    const target = document.getElementById("scope-content");
    clear(target);
    const details = append(target, "dl", "kv");
    [
      ["Repository", report.inputs.repo_slug, false],
      ["Repository identity source", report.inputs.repo_slug_source, false],
      ["Inputs digest", report.inputs.digest, true],
      ["Tool", report.tool.name + " " + report.tool.version, false],
      ["Generated at", report.generated_at || "Not recorded (deterministic artifact)", false]
    ].forEach((pair) => {
      const row = append(details, "div");
      append(row, "dt", "", pair[0]);
      append(row, "dd", pair[2] ? "mono" : "", pair[1]);
    });
    append(target, "h3", "", "Limits");
    if (report.scope_and_limits && report.scope_and_limits.length) {
      const limits = append(target, "ul", "plain");
      report.scope_and_limits.forEach((item) => append(limits, "li", "", item));
    } else {
      append(target, "p", "empty", "No scope limits are recorded.");
    }
    append(target, "h3", "", "Input files");
    addTable(
      target,
      "Input files",
      ["Path", "Kind", "SHA-256"],
      (report.inputs.files || []).map((item) => [
        item.path,
        item.kind,
        element("span", "mono", item.sha256)
      ]),
      ["", "nowrap", ""],
      ["42%", "22%", "36%"]
    );
    append(target, "h3", "", "Data files");
    addTable(
      target,
      "Platform data files",
      ["Name", "Verified", "Entries", "Source"],
      (report.data_files || []).map((item) => [
        item.name,
        item.verified_on,
        item.entry_count,
        element("span", "mono", item.source_url)
      ]),
      ["", "nowrap", "num", ""],
      ["20%", "16%", "11%", "53%"]
    );
  }

  let lastMetrics = {};
  let firstSummaryRender = true;

  const readoutAnimations = new WeakMap();

  function animateReadout(item, from, to) {
    if (!Number.isFinite(from) || !Number.isFinite(to) || from === to) {
      item.textContent = String(to);
      return;
    }
    const running = readoutAnimations.get(item);
    if (running) { running.stop(); }
    if (!motion || !motionEnabled() || window.NHBEffects) {
      item.textContent = String(to);
      return;
    }
    const control = motion.animate(from, to, {
      duration: 0.19,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (value) => {
        item.textContent = String(Math.round(value));
      },
      onComplete: () => {
        item.textContent = String(to);
        readoutAnimations.delete(item);
      }
    });
    readoutAnimations.set(item, control);
  }

  function renderSummary(scenario) {
    const target = document.getElementById("summary-grid");
    const brief = document.getElementById("summary-brief");
    const context = document.getElementById("summary-context");
    clear(target);
    clear(brief);
    if (context) { clear(context); }
    const partition = scenario ? scenario.partition : {R: [], E: [], Z: []};
    const total = partition.R.length + partition.E.length + partition.Z.length;
    const critical = findings.filter((finding) => finding.severity === "CRITICAL").length;
    const metrics = [
      {
        label: "Potentially surviving",
        code: "Z",
        value: scenario ? partition.Z.length : null,
        note: scenario ? "of " + plural(total, "listed credential") : "no entrypoint selected",
        data: true
      },
      {
        label: "Ends with entrypoint",
        code: "R",
        value: scenario ? partition.R.length : null,
        note: "job end or token expiry",
        data: false
      },
      {
        label: "Expires on its own",
        code: "E",
        value: scenario ? partition.E.length : null,
        note: "expire without rotation",
        data: false
      },
      {
        label: "Findings",
        code: "",
        value: findings.length,
        note: findings.length
          ? (scenarios.length > 1 ? "across all entrypoints" : "in this report")
          : "none recorded",
        data: false
      },
      {
        label: "Critical findings",
        code: "critical",
        value: findings.length ? critical : null,
        note: findings.length ? "of " + plural(findings.length, "finding") : "none recorded",
        data: false,
        tone: "is-critical"
      }
    ];
    metrics.forEach((metric) => {
      const card = append(target, "div", "stat" + (metric.data ? " is-data" : ""));
      const label = append(card, "span", "stat-label");
      if (metric.code && metric.code.length === 1) { append(label, "span", "code code-" + metric.code, metric.code); }
      append(label, "span", "", metric.label);
      const value = append(
        card, "strong", "stat-value" + (metric.data ? " is-data" : "") + (metric.tone ? " " + metric.tone : "")
      );
      const previous = lastMetrics[metric.code || "findings"];
      if (typeof metric.value === "number") {
        value.textContent = String(metric.value);
        if (!firstSummaryRender && previous !== undefined && previous !== metric.value) {
          animateReadout(value, previous, metric.value);
        }
      } else {
        value.textContent = "—";
      }
      lastMetrics[metric.code || "findings"] = metric.value;
      append(card, "span", "stat-note", metric.note);
    });
    firstSummaryRender = false;
    if (context) {
      context.textContent = scenario
        ? scenario.selector
        : "No entrypoint scenario is available";
    }
    if (!scenario) {
      brief.textContent =
        "No entrypoint scenario is available in this report. The counts describe the parsed graph and findings only.";
      return;
    }
    const unresolved = (scenario.unresolved_inputs || []).length;
    const parts = ["Selected entrypoint " + scenario.selector + "."];
    if (scenario.truncated) {
      parts.push("The traversal was truncated at the configured limit; the counts are a lower bound.");
    }
    if (unresolved) {
      parts.push("The result is a lower bound: " + plural(unresolved, "input") + " could not be resolved.");
    } else if (!scenario.truncated) {
      parts.push("All inputs were resolved.");
    }
    brief.textContent = parts.join(" ");
  }

  function renderLead(scenario) {
    const target = document.getElementById("finding-lead");
    clear(target);
    if (!scenarios.length) {
      const notice = append(target, "p", "notice");
      append(notice, "strong", "", "No entrypoint scenario");
      append(
        notice,
        "span",
        "",
        "Survival and rotation are unavailable in this report. The graph, findings and scope are still shown."
      );
    }
    if (!findings.length) {
      if (scenarios.length) {
        append(target, "p", "lead-empty", "No findings were generated for this report.");
      }
      return;
    }
    const scoped = scenario
      ? findings.filter((finding) => !finding.scenario || finding.scenario === scenario.selector)
      : findings;
    const finding = scoped[0] || findings[0];
    const row = append(target, "div", "lead sev-" + finding.severity);
    append(row, "span", "pill sev-" + finding.severity, finding.severity);
    append(row, "span", "lead-title", finding.title);
    append(
      row,
      "span",
      "lead-meta",
      finding.rule + (finding.scenario ? " · " + finding.scenario : "")
    );
  }

  function renderFindingsLink() {
    const link = document.getElementById("all-findings");
    if (!link) { return; }
    link.hidden = !findings.length;
    link.textContent = findings.length === 1 ? "View the finding" : "All " + plural(findings.length, "finding");
  }

  function renderScenarioPicker() {
    const picker = document.getElementById("scenario-picker");
    clear(picker);
    const items = report.scenarios || [];
    if (!items.length) {
      const option = append(picker, "option", "", "No scenarios selected");
      option.value = "";
      picker.disabled = true;
    } else {
      picker.disabled = false;
      items.forEach((scenario, index) => {
        const option = append(picker, "option", "", scenario.selector);
        option.value = String(index);
      });
      picker.addEventListener("change", () => {
        selectScenario(Number(picker.value));
      });
    }
    selectScenario(0);
  }

  function selectScenario(index) {
    currentScenarioIndex = index;
    const picker = document.getElementById("scenario-picker");
    if (picker && !picker.disabled) { picker.value = String(index); }
    const scenario = scenarios[index] || null;
    const count = document.getElementById("scenario-count");
    if (count) {
      count.textContent = scenarios.length
        ? (index + 1) + " of " + plural(scenarios.length, "entrypoint")
        : "No entrypoints";
    }
    renderLead(scenario);
    renderFindingsLink();
    renderHeroDiagram(scenario);
    renderSummary(scenario);
    renderScenario(index);
    renderMatrix();
    if (effectsReady) { refreshEffects(); }
  }

  function renderScenario(index) {
    const scenario = scenarios[index];
    const target = document.getElementById("scenario-content");
    clear(target);
    renderTrace(null);
    if (!scenario) {
      append(target, "p", "empty", "No scenario is available.");
      renderSurvival(null);
      renderRotation(null);
      renderGraph(null);
      return;
    }
    const facts = append(target, "div", "fact-grid");
    const start = append(facts, "div", "fact");
    append(start, "span", "fact-label", "Start nodes");
    const chips = append(start, "div", "chip-row");
    (scenario.start_nodes || []).forEach((id) => {
      const item = nodes.get(id);
      const chip = append(chips, "span", "text-chip", item ? item.label : id);
      chip.title = id;
    });
    [
      ["UNKNOWN-class potential edges", scenario.potential.length],
      ["Unresolved inputs", (scenario.unresolved_inputs || []).length],
      ["Traversal truncated", scenario.truncated ? "yes" : "no"]
    ].forEach((pair) => {
      const fact = append(facts, "div", "fact");
      append(fact, "span", "fact-label", pair[0]);
      append(fact, "span", "fact-value", pair[1]);
    });
    if (scenario.notes && scenario.notes.length) {
      append(target, "h3", "", "Notes");
      const notes = append(target, "ul", "plain");
      scenario.notes.forEach((note) => append(notes, "li", "note", note));
    }
    renderSurvival(scenario);
    renderRotation(scenario);
    renderGraph(scenario);
  }

  function traceButton(id, text) {
    const item = nodes.get(id);
    const label = text || (item ? item.label : textOf(id));
    const button = element("button", "trace-link", label);
    button.type = "button";
    button.title = "Trace one shortest path from this scenario's entrypoint";
    button.setAttribute("aria-label", "Trace a path from the entrypoint to " + nodeLabel(id));
    button.addEventListener("click", () => traceTo(id));
    return button;
  }

  function renderSurvival(scenario) {
    const target = document.getElementById("survival-content");
    clear(target);
    if (!scenario) {
      append(target, "p", "empty", "No scenario partition is available.");
      return;
    }
    const partition = scenario.partition;
    const total = partition.R.length + partition.E.length + partition.Z.length;
    if (!total) {
      append(target, "p", "empty", "No credentials are listed in this scenario.");
      return;
    }
    const rail = append(target, "div", "survival-rail");
    rail.setAttribute("role", "img");
    rail.setAttribute(
      "aria-label",
      "Credential outcomes: " + partition.R.length + " end with the entrypoint, " +
        partition.E.length + " expire on their own, " + partition.Z.length +
        " potentially survive revocation."
    );
    [
      ["R", partition.R.length],
      ["E", partition.E.length],
      ["Z", partition.Z.length]
    ].forEach((pair) => {
      if (!pair[1]) { return; }
      const segment = append(rail, "span", "seg-" + pair[0]);
      segment.style.width = (pair[1] / total * 100).toFixed(4) + "%";
      segment.title = plural(pair[1], "credential") + " in " + pair[0];
    });
    const legend = append(target, "div", "survival-legend");
    [
      ["R", "Ends with entrypoint", partition.R.length],
      ["E", "Expires on its own", partition.E.length],
      ["Z", "Potentially survives revocation", partition.Z.length]
    ].forEach((pair) => {
      const item = append(legend, "span", "legend-item");
      append(item, "i", "legend-swatch seg-" + pair[0]);
      append(item, "span", "", pair[1]);
      append(item, "span", "legend-count", pair[2]);
    });
    renderTimeline(target, scenario);
    const grid = append(target, "div", "outcome-grid");
    renderOutcome(grid, "R", "Ends with entrypoint", partition.R.map((id) => ({
      id,
      label: nodes.get(id) ? nodes.get(id).label : id,
      meta: joinParts([
        nodes.get(id) ? textOf(nodes.get(id).attrs.credential_kind) : "",
        nodes.get(id) ? textOf(nodes.get(id).attrs.lifetime) : ""
      ]),
      where: nodeWhere(id)
    })));
    renderOutcome(grid, "E", "Expires on its own", partition.E.map((entry) => ({
      id: entry.credential,
      label: nodes.get(entry.credential) ? nodes.get(entry.credential).label : entry.credential,
      meta: joinParts([
        nodes.get(entry.credential) ? textOf(nodes.get(entry.credential).attrs.credential_kind) : "",
        "TTL " + entry.ttl_seconds + " s"
      ]),
      where: nodeWhere(entry.credential)
    })));
    renderOutcome(grid, "Z", "Potentially survives revocation", partition.Z.map((entry) => ({
      id: entry.credential,
      label: nodes.get(entry.credential) ? nodes.get(entry.credential).label : entry.credential,
      meta: joinParts([
        entry.lifetime,
        entry.survival_window,
        "criticality " + entry.criticality
      ]),
      where: nodeWhere(entry.credential)
    })));
    append(
      target,
      "p",
      "table-hint",
      "Select a credential name to trace one shortest directed path from this scenario's entrypoint."
    );
    const headingR = append(target, "h3", "table-heading");
    append(headingR, "span", "code code-R", "R");
    append(headingR, "span", "", "Credentials that end with the revoked entrypoint");
    headingR.id = "survival-r";
    addTable(
      target,
      "Credentials that end with the revoked entrypoint",
      ["Credential", "Kind", "Lifetime", "Evidence"],
      partition.R.map((id) => [
        credentialCell(id),
        nodes.get(id) ? textOf(nodes.get(id).attrs.credential_kind) : "",
        nodes.get(id) ? textOf(nodes.get(id).attrs.lifetime) : "",
        nodeEvidence(id)
      ]),
      ["", "nowrap", "nowrap", ""],
      ["38%", "15%", "14%", "33%"]
    );
    const headingE = append(target, "h3", "table-heading");
    append(headingE, "span", "code code-E", "E");
    append(headingE, "span", "", "Credentials that expire on their own");
    headingE.id = "survival-e";
    addTable(
      target,
      "Credentials that expire on their own",
      ["Credential", "TTL (seconds)", "Kind", "Evidence"],
      partition.E.map((entry) => [
        credentialCell(entry.credential),
        entry.ttl_seconds,
        nodes.get(entry.credential) ? textOf(nodes.get(entry.credential).attrs.credential_kind) : "",
        nodeEvidence(entry.credential)
      ]),
      ["", "num", "nowrap", ""],
      ["36%", "12%", "16%", "36%"]
    );
    const headingZ = append(target, "h3", "table-heading");
    append(headingZ, "span", "code code-Z", "Z");
    append(headingZ, "span", "", "Credentials that survive revocation");
    headingZ.id = "survival-z";
    addTable(
      target,
      "Credentials that survive revocation",
      ["Credential", "Depth", "Lifetime", "Survival window", "Criticality", "Evidence"],
      partition.Z.map((entry) => [
        credentialCell(entry.credential),
        entry.depth,
        entry.lifetime,
        entry.survival_window,
        entry.criticality,
        nodeEvidence(entry.credential)
      ]),
      ["", "num", "nowrap", "nowrap", "num", ""],
      ["28%", "7%", "12%", "16%", "11%", "26%"]
    );
  }

  function renderOutcome(grid, code, title, entries) {
    const column = append(grid, "div", "outcome outcome-" + code + (code === "Z" ? " is-Z" : ""));
    const head = append(column, "div", "outcome-head");
    append(head, "span", "code code-" + code, code);
    append(head, "span", "outcome-title", title);
    append(head, "span", "outcome-count", entries.length);
    const list = append(column, "ul", "outcome-list");
    if (!entries.length) {
      append(list, "li", "empty", "None listed.");
      return;
    }
    entries.slice(0, 4).forEach((entry) => {
      const item = append(list, "li");
      item.appendChild(traceButton(entry.id, entry.label));
      if (entry.meta) { append(item, "span", "outcome-meta", entry.meta); }
      if (entry.where) { append(item, "span", "outcome-where", entry.where); }
    });
    if (entries.length > 4) {
      const more = append(column, "p", "outcome-more");
      const link = append(more, "a", "", "+ " + (entries.length - 4) + " more in the table");
      link.href = "#survival-" + code.toLowerCase();
    }
  }

  function shortestPath(starts, target) {
    if (!starts || !starts.length) { return null; }
    if (starts.includes(target)) { return []; }
    const depth = new Map();
    const previous = new Map();
    const queue = [];
    starts.slice().sort().forEach((id) => {
      if (depth.has(id)) { return; }
      depth.set(id, 0);
      queue.push(id);
    });
    for (let head = 0; head < queue.length; head += 1) {
      const current = queue[head];
      const outgoing = adjacency.get(current) || [];
      for (const edge of outgoing) {
        if (depth.has(edge.dst)) { continue; }
        depth.set(edge.dst, depth.get(current) + 1);
        previous.set(edge.dst, edge);
        if (edge.dst === target) {
          const path = [];
          let cursor = target;
          while (previous.has(cursor)) {
            const step = previous.get(cursor);
            path.push(step);
            cursor = step.src;
          }
          return path.reverse();
        }
        queue.push(edge.dst);
      }
    }
    return null;
  }

  function clearGraphTrace() {
    if (!graphView) { return; }
    graphView.stage.classList.remove("is-tracing");
    graphView.nodes.forEach((node) => node.classList.remove("is-traced"));
    graphView.edges.forEach((edge) => edge.classList.remove("is-traced"));
  }

  function highlightGraphTrace(path) {
    if (!graphView) { return; }
    clearGraphTrace();
    graphView.stage.classList.add("is-tracing");
    const tracedEdges = new Set(path.map((edge) => edge.id));
    const tracedNodes = new Set();
    path.forEach((edge) => {
      tracedNodes.add(edge.src);
      tracedNodes.add(edge.dst);
    });
    tracedNodes.forEach((id) => {
      const node = graphView.nodes.get(id);
      if (node) { node.classList.add("is-traced"); }
    });
    tracedEdges.forEach((id) => {
      const edge = graphView.edges.get(id);
      if (edge) { edge.classList.add("is-traced"); }
    });
  }

  function renderTrace(path, targetId) {
    const target = document.getElementById("trace-content");
    clear(target);
    if (!targetId) {
      clearGraphTrace();
      return;
    }
    append(target, "h3", "", "Path trace: " + nodeLabel(targetId));
    append(
      target,
      "p",
      "muted",
      "One shortest directed path in the report graph. This is a visual aid; " +
        "R/E/Z membership comes from the analysis, not from this trace."
    );
    if (path === null) {
      append(
        target,
        "p",
        "empty",
        "No directed path from the selected entrypoint to this entity is recorded."
      );
      clearGraphTrace();
      return;
    }
    if (!path.length) {
      append(target, "p", "empty", "This entity is itself a start node of the scenario.");
      clearGraphTrace();
      return;
    }
    const hasUnknown = path.some((edge) => edge.confidence === "unknown");
    if (hasUnknown) {
      append(
        target,
        "p",
        "note",
        "This trace includes UNKNOWN-class edges; it is a potential path only."
      );
    }
    const list = append(target, "ol", "trace");
    path.forEach((edge) => {
      const item = append(list, "li");
      const hop = append(item, "p", "hop mono");
      hop.textContent = nodeLabel(edge.src) + " -> " + nodeLabel(edge.dst);
      append(item, "p", "muted", edge.kind + " edge; confidence " + edge.confidence);
      const evidence = append(item, "div");
      evidenceList(evidence, (edge.evidence || []).slice(0, 1));
    });
    const clearButton = element("button", "button quiet", "Clear trace");
    clearButton.type = "button";
    clearButton.addEventListener("click", () => renderTrace(null, null));
    append(target, "p").appendChild(clearButton);
    highlightGraphTrace(path);
  }

  function traceTo(targetId) {
    const scenario = scenarios[currentScenarioIndex] || null;
    if (!scenario) {
      renderTrace(null, null);
      return;
    }
    renderTrace(shortestPath(scenario.start_nodes || [], targetId), targetId);
    const target = document.getElementById("trace-content");
    if (target) {
      revealDisclosure(target);
      target.scrollIntoView({block: "nearest"});
    }
  }

  function renderProcess(container, entries) {
    const list = append(container, "ol", "steps cols-" + Math.min(entries.length, 4));
    entries.forEach((entry) => {
      const step = entry.step;
      const row = append(list, "li", "step");
      append(row, "span", "step-no", String(step.order).padStart(2, "0"));
      const link = svgNode(row, "svg", {
        "class": "step-link", viewBox: "0 0 100 100", preserveAspectRatio: "none",
        "aria-hidden": "true", focusable: "false"
      });
      svgNode(link, "path", { "class": "sl-h", "data-fx-draw": "", d: "M0 50 H100" });
      svgNode(link, "path", { "class": "sl-v", "data-fx-draw": "", d: "M50 0 V100" });
      const body = append(row, "div", "step-body");
      const head = append(body, "div", "step-head");
      append(head, "span", "step-title", "Step " + step.order);
      append(head, "span", "pill phase-pill", entry.phase);
      if (step.generation !== null && step.generation !== undefined) {
        append(head, "span", "pill", "generation " + step.generation);
      }
      if (step.batch) { append(head, "span", "pill", "batch"); }
      if (step.depends_on && step.depends_on.length) {
        append(body, "p", "muted", "Depends on: " + step.depends_on.join(", "));
      }
      const actions = append(body, "ol", "step-actions");
      (step.actions || []).forEach((action) => append(actions, "li", "", action));
      if (step.credentials && step.credentials.length) {
        const chips = append(body, "div", "step-cred");
        step.credentials.forEach((credential) => {
          const chip = append(chips, "span", "cred-chip", credential.label);
          append(chip, "span", "mono", credential.id);
        });
      }
      const details = append(body, "details");
      append(details, "summary", "", "Evidence");
      const evidence = append(details, "div", "details-body");
      evidenceList(evidence, step.evidence || []);
    });
  }

  function renderRotation(scenario) {
    const target = document.getElementById("rotation-content");
    clear(target);
    if (!scenario) {
      append(target, "p", "empty", "No rotation plan is available.");
      return;
    }
    const plan = scenario.rotation_plan;
    const entries = [];
    [["Containment", plan.containment], ["Rotation", plan.rotation], ["Verify", plan.verify]].forEach((phase) => {
      (phase[1] || []).forEach((step) => entries.push({ phase: phase[0], step: step }));
    });
    if (entries.length) {
      renderProcess(target, entries);
    } else {
      append(target, "p", "empty", "No steps.");
    }
    if (plan.notes && plan.notes.length) {
      append(target, "h3", "notes-title", "Plan notes");
      const notes = append(target, "ul", "notes-list");
      plan.notes.forEach((note) => append(notes, "li", "note", note));
    }
  }

  function renderFindingCard(target, finding) {
    const card = append(target, "article", "finding sev-" + finding.severity);
    const head = append(card, "div", "finding-head");
    append(head, "span", "pill sev-" + finding.severity, finding.severity);
    append(head, "h3", "", finding.title);
    append(
      card,
      "p",
      "finding-rule",
      finding.rule + " " + finding.id + " · confidence " + finding.confidence
    );
    append(card, "p", "finding-message", finding.message);
    if (finding.scenario) { append(card, "p", "finding-meta", "Scenario: " + finding.scenario); }
    if (finding.assumptions && finding.assumptions.length) {
      append(card, "p", "finding-meta", "Assumptions: " + finding.assumptions.join(", "));
    }
    const details = append(card, "details");
    append(details, "summary", "", "Evidence and path");
    const body = append(details, "div", "details-body");
    evidenceList(body, finding.evidence || []);
    if (finding.path && finding.path.length) {
      append(body, "p", "finding-path", finding.path.map(nodeLabel).join(" -> "));
    }
  }

  function findingHaystack(finding) {
    const parts = [
      finding.title,
      finding.rule,
      finding.id,
      finding.severity,
      finding.message,
      finding.scenario,
      (finding.assumptions || []).join(" "),
      (finding.path || []).map(nodeLabel).join(" "),
      (finding.evidence || []).map(evidenceLabel).join(" ")
    ];
    return parts.map(textOf).join(" ").toLowerCase();
  }

  function renderFindings() {
    const target = document.getElementById("findings-content");
    const search = document.getElementById("finding-search");
    const severity = document.getElementById("finding-severity");
    const scenarioSelect = document.getElementById("finding-scenario");
    const count = document.getElementById("findings-count");
    const clearButton = document.getElementById("finding-clear");

    const severityNames = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];
    clear(severity);
    const allSeverities = append(severity, "option", "", "All severities");
    allSeverities.value = "";
    severityNames.forEach((name) => {
      const option = append(severity, "option", "", name);
      option.value = name;
    });

    const scenarioNames = Array.from(
      new Set(findings.map((finding) => textOf(finding.scenario)).filter(Boolean))
    ).sort();
    clear(scenarioSelect);
    const allScenarios = append(scenarioSelect, "option", "", "All scenarios");
    allScenarios.value = "";
    scenarioNames.forEach((name) => {
      const option = append(scenarioSelect, "option", "", name);
      option.value = name;
    });

    function apply() {
      clear(target);
      const needle = search.value.trim().toLowerCase();
      const wantedSeverity = severity.value;
      const wantedScenario = scenarioSelect.value;
      const matches = findings.filter((finding) => {
        if (wantedSeverity && finding.severity !== wantedSeverity) { return false; }
        if (wantedScenario && textOf(finding.scenario) !== wantedScenario) { return false; }
        return !needle || findingHaystack(finding).includes(needle);
      });
      if (!matches.length && !findings.length && completenessGaps().length) {
        const note = append(target, "p", "empty empty-scope");
        note.appendChild(document.createTextNode("No findings in the analysed scope - see "));
        const link = append(note, "a", "", "Analysis completeness");
        link.setAttribute("href", "#completeness");
      } else if (!matches.length) {
        append(
          target,
          "p",
          "empty",
          findings.length
            ? "No findings match the current filters."
            : "No findings were generated."
        );
      } else {
        matches.forEach((finding) => renderFindingCard(target, finding));
      }
      count.textContent = matches.length + " of " + plural(findings.length, "finding") + " shown.";
      if (effectsReady) {
        count.classList.remove("is-bump");
        void count.offsetWidth;
        count.classList.add("is-bump");
        refreshEffects();
      }
    }

    search.addEventListener("input", apply);
    severity.addEventListener("change", apply);
    scenarioSelect.addEventListener("change", apply);
    if (clearButton) {
      clearButton.addEventListener("click", () => {
        search.value = "";
        severity.value = "";
        scenarioSelect.value = "";
        apply();
        search.focus();
      });
    }
    apply();
  }

  function scenarioCredentialStatuses(scenario) {
    const statuses = new Map();
    function add(id, code) {
      if (!id) { return; }
      const current = statuses.get(id);
      if (!current) {
        statuses.set(id, [code]);
      } else if (!current.includes(code)) {
        current.push(code);
      }
    }
    const partition = scenario.partition || {R: [], E: [], Z: []};
    (partition.R || []).forEach((id) => add(id, "R"));
    (partition.E || []).forEach((entry) => add(entry.credential, "E"));
    (partition.Z || []).forEach((entry) => add(entry.credential, "Z"));
    (scenario.potential_nodes || []).forEach((id) => {
      const node = nodes.get(id);
      if (node && node.kind === "CREDENTIAL") { add(id, "P"); }
    });
    return statuses;
  }

  function statusLabel(code) {
    if (code === "R") { return "ends with the revoked entrypoint"; }
    if (code === "E") { return "expires on its own"; }
    if (code === "Z") { return "potentially survives revocation"; }
    return "potential only through an UNKNOWN-class edge";
  }

  function renderMatrix() {
    const items = scenarios;
    const section = document.getElementById("matrix");
    const link = document.getElementById("matrix-link");
    const target = document.getElementById("matrix-content");
    const summary = document.getElementById("matrix-summary");
    const toggle = document.getElementById("matrix-shared");
    clear(target);
    clear(summary);
    if (scenarios.length < 2) {
      section.hidden = true;
      link.hidden = true;
      return;
    }
    section.hidden = false;
    link.hidden = false;
    const statuses = items.map(scenarioCredentialStatuses);
    const allIds = new Set();
    statuses.forEach((map) => map.forEach((_, id) => allIds.add(id)));
    const ids = Array.from(allIds).sort();
    const visible = toggle.checked
      ? ids.filter((id) => statuses.filter((map) => map.has(id)).length > 1)
      : ids;
    const sharedSurvivors = ids.filter(
      (id) => statuses.filter((map) => (map.get(id) || []).includes("Z")).length > 1
    ).length;
    const unique = ids.filter(
      (id) => statuses.filter((map) => map.has(id)).length === 1
    ).length;
    let widestIndex = -1;
    let widestCount = -1;
    statuses.forEach((map, index) => {
      if (map.size > widestCount) {
        widestCount = map.size;
        widestIndex = index;
      }
    });
    if (ids.length) {
      summary.textContent =
        plural(ids.length, "credential") + (ids.length === 1 ? " is" : " are") +
        " listed across " + plural(items.length, "scenario") + "; " +
        sharedSurvivors + " potentially survive revocation in more than one scenario; " +
        unique + (unique === 1 ? " appears" : " appear") + " in only one. Widest listed coverage: " +
        (widestIndex >= 0 ? items[widestIndex].selector : "none") +
        " (" + plural(Math.max(widestCount, 0), "credential") + ").";
    } else {
      summary.textContent = "No credentials are listed in any scenario.";
    }
    append(
      target,
      "p",
      "muted",
      "R/E/Z come from the analysis. P marks a credential that appears only on UNKNOWN-class " +
        "potential edges in that scenario. Select a status to switch scenario and trace a path."
    );
    if (!ids.length) {
      append(target, "p", "empty", "No credentials are listed in any scenario.");
      return;
    }
    if (!visible.length) {
      append(
        target,
        "p",
        "empty",
        "No credential is listed in more than one scenario."
      );
      return;
    }
    const wrap = append(target, "div", "table-wrap matrix-wrap");
    wrap.tabIndex = 0;
    wrap.setAttribute("role", "region");
    wrap.setAttribute("aria-label", "Cross-scenario credential exposure matrix");
    const table = append(wrap, "table", "matrix");
    append(
      table,
      "caption",
      "",
      "Credential status by scenario. R = ends with the revoked entrypoint; " +
        "E = expires on its own; Z = potentially survives revocation; " +
        "P = potential only through an UNKNOWN-class edge."
    );
    const headRow = append(append(table, "thead"), "tr");
    const corner = append(headRow, "th", "", "Scenario");
    corner.scope = "col";
    visible.forEach((id) => {
      const cell = append(headRow, "th", "", credentialHeading(id));
      cell.scope = "col";
      cell.title = id;
    });
    const body = append(table, "tbody");
    items.forEach((scenario, index) => {
      const row = append(body, "tr", index === currentScenarioIndex ? "active-row" : "");
      const rowHead = append(row, "th", "wrap", scenario.selector);
      rowHead.scope = "row";
      visible.forEach((id) => {
        const cell = append(row, "td");
        const codes = statuses[index].get(id);
        if (!codes || !codes.length) {
          cell.textContent = "-";
          cell.setAttribute("aria-label", "Not listed in this scenario");
          return;
        }
        const button = element("button", "status status-" + codes[0], codes.join("+"));
        button.type = "button";
        button.title = codes.map(statusLabel).join("; ");
        button.setAttribute(
          "aria-label",
          nodeLabel(id) + ": " + codes.map(statusLabel).join("; ") +
            " in scenario " + scenario.selector
        );
        button.addEventListener("click", () => {
          selectScenario(index);
          traceTo(id);
        });
        cell.appendChild(button);
      });
    });
    watchOverflow(wrap);
  }

  function renderAssumptions() {
    const target = document.getElementById("assumptions-content");
    clear(target);
    const assumptions = report.assumptions || [];
    if (assumptions.length) {
      append(target, "h3", "", "Assumptions");
      const caption = "Assumptions attached to this report";
      const table = tableRegion(target, caption);
      append(table, "caption", "", caption);
      addColumns(table, ["16%", "36%", "10%", "38%"]);
      const head = append(append(table, "thead"), "tr");
      ["ID", "Statement", "Verify", "Used by"].forEach((heading) => {
        const cell = append(head, "th", "", heading);
        cell.scope = "col";
      });
      const body = append(table, "tbody");
      assumptions.forEach((assumption) => {
        const row = append(body, "tr");
        row.setAttribute("id", "assumption-" + safeId(assumption.id));
        append(row, "td", "mono nowrap", assumption.id);
        append(row, "td", "wrap", assumption.statement);
        append(row, "td", "", assumption.verify ? "yes" : "no");
        append(row, "td", "mono wrap", (assumption.used_by || []).join(", "));
      });
    } else {
      append(target, "p", "empty", "No assumptions were recorded.");
    }
    append(target, "h3", "", "Unknown inputs");
    const items = report.scenarios || [];
    if (!items.some((item) => item.unresolved_inputs.length)) {
      append(target, "p", "empty", "No unresolved inputs are recorded.");
    }
    items.forEach((scenario) => {
      if (!scenario.unresolved_inputs.length) { return; }
      append(target, "h4", "", scenario.selector);
      const list = append(target, "ul", "plain");
      scenario.unresolved_inputs.forEach((item) => append(list, "li", "mono wrap", item));
    });
  }

  function renderDiagnostics() {
    const target = document.getElementById("diagnostics-content");
    clear(target);
    const diagnostics = (report.diagnostics || []).slice();
    if (!diagnostics.length) {
      append(target, "p", "empty", "No diagnostics were recorded.");
      return;
    }
    const caption = "Parse and analysis diagnostics";
    const table = tableRegion(target, caption);
    append(table, "caption", "", caption);
    addColumns(table, ["10%", "14%", "48%", "28%"]);
    const head = append(append(table, "thead"), "tr");
    ["Level", "Code", "Message", "Location"].forEach((heading) => {
      const cell = append(head, "th", "", heading);
      cell.scope = "col";
    });
    const body = append(table, "tbody");
    const seenCodes = new Set();
    diagnostics.forEach((item) => {
      const row = append(body, "tr");
      if (!seenCodes.has(item.code)) {
        seenCodes.add(item.code);
        row.setAttribute("id", "diagnostic-" + safeId(item.code));
      }
      append(row, "td", "", item.level);
      append(row, "td", "mono", item.code);
      append(row, "td", "wrap", item.message);
      append(row, "td", "mono wrap", textOf(item.file) +
        (item.line === undefined || item.line === null ? "" : ":" + item.line));
    });
  }

  const FAMILY_LABELS = __FAMILY_LABELS__;
  const COMPLETENESS_GROUPS = [
    { key: "partially_analysed", label: "Partially analysed", collapsed: false },
    { key: "not_provided", label: "Not provided", collapsed: false },
    { key: "not_supported", label: "Not supported", collapsed: false },
    { key: "analysed", label: "Analysed", collapsed: true },
    { key: "not_applicable", label: "Not applicable", collapsed: true }
  ];
  const GAP_STATUSES = ["partially_analysed", "not_provided", "not_supported"];

  function completenessItems() {
    const block = report.completeness;
    return block && Array.isArray(block.items) ? block.items : [];
  }

  function completenessGaps() {
    return completenessItems().filter((item) => GAP_STATUSES.indexOf(item.status) !== -1);
  }

  function statusBadge(parent, status, label) {
    const badge = append(parent, "span", "cmp-status cmp-status-" + safeId(status), label);
    return badge;
  }

  function completenessLinks(parent, title, values, prefix) {
    if (!values || !values.length) { return; }
    const row = append(parent, "div", "cmp-fact");
    append(row, "dt", "", title);
    const cell = append(row, "dd", "cmp-links");
    values.forEach((value) => {
      const targetId = prefix + safeId(value);
      if (document.getElementById(targetId)) {
        const link = append(cell, "a", "", value);
        link.setAttribute("href", "#" + targetId);
      } else {
        append(cell, "span", "", value);
      }
    });
  }

  function renderCompletenessItem(list, item) {
    const row = append(list, "li", "cmp-item");
    const head = append(row, "div", "cmp-item-head");
    const label = FAMILY_LABELS[item.family] || textOf(item.family);
    append(head, "h4", "cmp-family", label);
    const group = COMPLETENESS_GROUPS.find((entry) => entry.key === item.status);
    statusBadge(head, item.status, group ? group.label : textOf(item.status).replace(/_/g, " "));
    if (item.explanation) { append(row, "p", "cmp-explanation", item.explanation); }
    const facts = append(row, "dl", "cmp-facts");
    const sources = item.sources || [];
    if (sources.length) {
      const fact = append(facts, "div", "cmp-fact");
      append(fact, "dt", "", "Sources");
      const cell = append(fact, "dd");
      const listing = append(cell, "ul", "cmp-sources");
      const addSource = (target, source) => {
        const entry = append(target, "li");
        append(entry, "span", "mono", textOf(source.path));
        append(entry, "span", "cmp-hash", "sha256 " + textOf(source.sha256).slice(0, 12));
      };
      sources.slice(0, 3).forEach((source) => addSource(listing, source));
      if (sources.length > 3) {
        const more = append(cell, "details");
        append(more, "summary", "", plural(sources.length - 3, "more source"));
        const rest = append(more, "ul", "cmp-sources");
        sources.slice(3).forEach((source) => addSource(rest, source));
      }
    }
    completenessLinks(facts, "Diagnostics", item.diagnostics, "diagnostic-");
    completenessLinks(facts, "Assumptions", item.assumptions, "assumption-");
    if (!facts.childNodes.length) { facts.remove(); }
  }

  function renderCompleteness() {
    const items = completenessItems();
    const section = document.getElementById("completeness");
    const link = document.getElementById("completeness-link");
    if (!items.length) { return; }
    section.hidden = false;
    link.hidden = false;
    const target = document.getElementById("completeness-content");
    clear(target);
    const counts = append(target, "ul", "cmp-counts");
    counts.setAttribute("aria-label", "Items by status");
    const known = new Set(COMPLETENESS_GROUPS.map((entry) => entry.key));
    const buckets = new Map(COMPLETENESS_GROUPS.map((entry) => [entry.key, []]));
    const other = [];
    items.forEach((item) => {
      if (known.has(item.status)) { buckets.get(item.status).push(item); } else { other.push(item); }
    });
    COMPLETENESS_GROUPS.forEach((entry) => {
      const entryRow = append(counts, "li");
      statusBadge(entryRow, entry.key, entry.label);
      append(entryRow, "span", "cmp-count-num", String(buckets.get(entry.key).length));
    });
    append(
      target,
      "p",
      "cmp-note",
      "Not provided and not supported mean the report says nothing about that family, not that " +
        "nothing is there. Partially analysed results are a lower bound. A status lists which " +
        "inputs were read; it is not a score and not a verdict."
    );
    const groups = COMPLETENESS_GROUPS.map((entry) => ({
      label: entry.label, collapsed: entry.collapsed, items: buckets.get(entry.key)
    }));
    if (other.length) { groups.push({ label: "Other status", collapsed: false, items: other }); }
    groups.forEach((groupInfo) => {
      if (!groupInfo.items.length) { return; }
      const group = append(target, "div", "cmp-group");
      append(group, "h3", "", groupInfo.label + " (" + groupInfo.items.length + ")");
      let host = group;
      if (groupInfo.collapsed) {
        host = append(group, "details");
        append(host, "summary", "", "Show " + plural(groupInfo.items.length, "item"));
      }
      const list = append(host, "ul", "cmp-list");
      groupInfo.items.forEach((item) => renderCompletenessItem(list, item));
    });
  }

  function revealDisclosure(item) {
    let node = item;
    while (node) {
      if (node.tagName === "DETAILS") { node.open = true; }
      node = node.parentElement;
    }
    if (item && item.classList && item.classList.contains("section-disclosure")) {
      const own = item.querySelector("details.disclosure");
      if (own) { own.open = true; }
    }
  }

  function revealHash() {
    const id = window.location.hash.slice(1);
    const target = id ? document.getElementById(id) : null;
    if (target) {
      revealDisclosure(target);
      target.scrollIntoView();
    }
  }

  const svgNamespace = document.querySelector(".brand-mark").namespaceURI;

  function svgNode(parent, tag, attributes, text) {
    const node = document.createElementNS(svgNamespace, tag);
    Object.keys(attributes || {}).forEach((name) => node.setAttribute(name, String(attributes[name])));
    if (text !== undefined && text !== null) { node.textContent = text; }
    if (parent) { parent.appendChild(node); }
    return node;
  }

  function inputTileCounts() {
    const files = (report.inputs && report.inputs.files) || [];
    const count = (kinds) => files.filter((file) => kinds.indexOf(file.kind) !== -1).length;
    return [
      { label: "Workflows", lines: ["Workflows"], value: count(["workflow"]) },
      { label: "Composite actions", lines: ["Composite", "actions"], value: count(["composite_action"]) },
      { label: "Terraform", lines: ["Terraform", "files"], value: count(["tf_json", "tf_hcl"]) },
      { label: "IAM policy files", lines: ["IAM policy", "files"], value: count(["iam_json"]) }
    ].filter((tile) => tile.value > 0);
  }

  const narrowDiagram = window.matchMedia ? window.matchMedia("(max-width: 560px)") : null;

  function drawTile(svg, layout, x, top, width, height, lines, value, valueClass, code) {
    const group = svgNode(svg, "g", { "class": "hd-tile-group", "data-fx-tilt": "" });
    svgNode(group, "rect", { "class": "hd-tile-shadow", x: x, y: top + 4, width: width, height: height, rx: 12 });
    svgNode(group, "rect", { "class": "hd-tile", x: x, y: top, width: width, height: height, rx: 12 });
    const shown = value === null ? "—" : String(value);
    if (layout === "row") {
      svgNode(group, "text", { "class": "hd-value " + valueClass, x: x + 16, y: top + height / 2 + 11 }, shown);
      lines.forEach((line, row) => {
        svgNode(group, "text", {
          "class": "hd-label", x: x + 62,
          y: top + height / 2 + (lines.length > 1 ? (row ? 15 : -3) : 5)
        }, line);
      });
    } else {
      svgNode(group, "text", { "class": "hd-value " + valueClass, x: x + 14, y: top + 38 }, shown);
      lines.forEach((line, row) => {
        svgNode(group, "text", { "class": "hd-label", x: x + 14, y: top + 58 + row * 16 }, line);
      });
    }
    if (code) {
      svgNode(group, "text", { "class": "hd-code", x: x + width - 12, y: top + 20, "text-anchor": "end" }, code);
    }
  }

  function renderHeroDiagram(scenario) {
    const host = document.getElementById("hero-diagram-host");
    const caption = document.getElementById("hero-diagram-text");
    if (!host || !caption) { return; }
    clear(host);
    const tiles = inputTileCounts();
    const partition = scenario ? scenario.partition : null;
    const outputs = [
      { code: "R", lines: ["Ends with", "entrypoint"], value: partition ? partition.R.length : null },
      { code: "E", lines: ["Expires on", "its own"], value: partition ? partition.E.length : null },
      { code: "Z", lines: ["Potentially", "survives"], value: partition ? partition.Z.length : null }
    ];
    const narrow = Boolean(narrowDiagram && narrowDiagram.matches);
    const defs = (svg) => {
      const holder = svgNode(svg, "defs");
      const fill = svgNode(holder, "linearGradient", { id: "hd-core-fill", x1: "0", y1: "0", x2: "1", y2: "1" });
      svgNode(fill, "stop", { offset: "0", style: "stop-color: var(--accent)" });
      svgNode(fill, "stop", { offset: "1", style: "stop-color: var(--accent-hover)" });
    };
    const core = (svg, cx, cy, radius) => {
      svgNode(svg, "circle", { cx: cx, cy: cy, r: radius, fill: "url(#hd-core-fill)" });
      svgNode(svg, "text", { "class": "hd-core-text", x: cx, y: cy + 2, "text-anchor": "middle" }, "NHI-Blast");
      svgNode(svg, "text", { "class": "hd-core-sub", x: cx, y: cy + 18, "text-anchor": "middle" }, "offline scan");
    };
    const line = (svg, d) => svgNode(svg, "path", { "class": "hd-line", "data-fx-draw": "", d: d });
    if (!narrow) {
      const cx = 230;
      const cy = 200;
      const radius = 42;
      const place = (count, index) => (400 * (index + 1)) / (count + 1);
      const svg = svgNode(host, "svg", {
        "class": "hero-svg", viewBox: "0 0 460 400", role: "img",
        "aria-labelledby": "hero-diagram-text", focusable: "false"
      });
      defs(svg);
      [64, 92, 124].forEach((ring) => svgNode(svg, "circle", { "class": "hd-orbit", cx: cx, cy: cy, r: ring }));
      tiles.forEach((item, index) => {
        const y = place(tiles.length, index);
        line(svg, "M156 " + y + " C 176 " + y + ", 172 " + cy + ", " + (cx - radius) + " " + cy);
      });
      outputs.forEach((item, index) => {
        const y = place(outputs.length, index);
        line(svg, "M" + (cx + radius) + " " + cy + " C 284 " + cy + ", 288 " + y + ", 304 " + y);
      });
      core(svg, cx, cy, radius);
      tiles.forEach((item, index) => {
        drawTile(svg, "row", 8, place(tiles.length, index) - 32, 148, 64, item.lines, item.value, "", "");
      });
      outputs.forEach((item, index) => {
        drawTile(svg, "row", 304, place(outputs.length, index) - 32, 148, 64, item.lines, item.value, "hd-value-" + item.code, item.code);
      });
    } else {
      const rows = Math.max(1, Math.ceil(tiles.length / 2));
      const inputsBottom = rows * 64 + (rows - 1) * 16;
      const cy = inputsBottom + 64;
      const outputsTop = cy + 80;
      const svg = svgNode(host, "svg", {
        "class": "hero-svg", viewBox: "0 0 320 " + (outputsTop + 84), role: "img",
        "aria-labelledby": "hero-diagram-text", focusable: "false"
      });
      defs(svg);
      [64, 92].forEach((ring) => svgNode(svg, "circle", { "class": "hd-orbit", cx: 160, cy: cy, r: ring }));
      tiles.forEach((item, index) => {
        const column = tiles.length === 1 ? 0.5 : index % 2;
        const x = tiles.length === 1 ? 84 : column * 168;
        const top = Math.floor(index / 2) * 80;
        line(svg, "M" + (x + 76) + " " + (top + 64) + " C " + (x + 76) + " " + (top + 100) + ", 160 " + (cy - 78) + ", 160 " + (cy - 40));
      });
      outputs.forEach((item, index) => {
        const x = index * 112;
        line(svg, "M160 " + (cy + 40) + " C 160 " + (cy + 62) + ", " + (x + 48) + " " + (outputsTop - 30) + ", " + (x + 48) + " " + outputsTop);
      });
      core(svg, 160, cy, 40);
      tiles.forEach((item, index) => {
        const x = tiles.length === 1 ? 84 : (index % 2) * 168;
        drawTile(svg, "row", x, Math.floor(index / 2) * 80, 152, 64, item.lines, item.value, "", "");
      });
      outputs.forEach((item, index) => {
        drawTile(svg, "column", index * 112, outputsTop, 96, 84, item.lines, item.value, "hd-value-" + item.code, item.code);
      });
    }
    const read = tiles.length
      ? tiles.map((item) => item.value + " " + item.label.toLowerCase()).join(", ")
      : "no input files";
    caption.textContent = "Diagram. Inputs read: " + read + ". " + (scenario
      ? "For entrypoint " + scenario.selector + ": " + partition.R.length + " end with the entrypoint (R), " +
        partition.E.length + " expire on their own (E), " + partition.Z.length +
        " potentially survive revocation (Z)."
      : "No entrypoint scenario is available, so no R, E or Z counts are shown.");
  }

  if (narrowDiagram && narrowDiagram.addEventListener) {
    narrowDiagram.addEventListener("change", () => {
      renderHeroDiagram(scenarios[currentScenarioIndex] || null);
      if (effectsReady) { refreshEffects(); }
    });
  }

  function ttlText(seconds) {
    const n = Number(seconds);
    if (!Number.isFinite(n) || n <= 0) { return textOf(seconds) + " s"; }
    if (n % 86400 === 0) { return (n / 86400) + (n === 86400 ? " day" : " days"); }
    if (n % 3600 === 0) { return (n / 3600) + " h"; }
    if (n % 60 === 0) { return (n / 60) + " min"; }
    return n + " s";
  }

  function renderTimeline(container, scenario) {
    const partition = scenario.partition;
    const nodeLabelOf = (id) => (nodes.get(id) ? nodes.get(id).label : textOf(id));
    const attrOf = (id, name) => (nodes.get(id) && nodes.get(id).attrs ? textOf(nodes.get(id).attrs[name]) : "");
    const wrap = append(container, "div", "timeline");
    wrap.setAttribute("data-fx-reveal", "");
    const head = append(wrap, "div", "tl-head");
    append(head, "h3", "", "Survival timeline");
    append(
      head,
      "p",
      "tl-caption",
      "Marks follow the order of events after revocation. Distances between marks are not to scale. " +
        "R and E marks show job end or token expiry. Z bands indicate potential survival after revocation; " +
        "each row states its recorded survival window, not a shared expiry time."
    );
    const jobX = 16;
    const ttls = partition.E.map((entry) => Number(entry.ttl_seconds)).filter((value) => value > 0);
    const longest = ttls.length ? Math.max.apply(null, ttls) : 0;
    const xTtl = (seconds) => (longest > 0
      ? 24 + 60 * (Math.log(1 + seconds / 60) / Math.log(1 + longest / 60))
      : 60);
    const axis = append(wrap, "div", "tl-axis");
    axis.setAttribute("aria-hidden", "true");
    const tick = (text, left, extra) => {
      const item = append(axis, "span", "tl-tick" + (extra ? " " + extra : ""), text);
      item.style.left = left + "%";
    };
    tick("Revoked now", 0, "is-first");
    tick("Job ends", jobX, "");
    Array.from(new Set(ttls)).sort((left, right) => left - right).forEach((seconds) => {
      tick(ttlText(seconds), xTtl(seconds), "");
    });
    tick("After revocation", 100, "is-last");
    const detail = element("p", "tl-detail", "Hover or focus a row for its details. The tables below hold the same rows.");
    detail.setAttribute("role", "status");
    const group = (code, title, entries, build) => {
      if (!entries.length) { return; }
      const section = append(wrap, "div", "tl-group");
      const heading = append(section, "div", "tl-group-title");
      append(heading, "span", "code code-" + code, code);
      append(heading, "span", "", title + " (" + entries.length + ")");
      const list = append(section, "ul", "tl-list");
      list.style.listStyle = "none";
      list.style.margin = "0";
      list.style.padding = "0";
      entries.slice(0, 8).forEach((entry) => {
        const row = append(list, "li", "tl-row");
        const summary = build(row, entry);
        row.setAttribute("tabindex", "0");
        row.setAttribute("aria-label", summary);
        const show = () => {
          detail.textContent = summary;
          row.classList.add("is-active");
        };
        const hide = () => row.classList.remove("is-active");
        row.addEventListener("mouseenter", show);
        row.addEventListener("focus", show);
        row.addEventListener("mouseleave", hide);
        row.addEventListener("blur", hide);
      });
      if (entries.length > 8) {
        append(section, "p", "tl-more", "+ " + (entries.length - 8) + " more in the table below");
      }
    };
    const track = (row, name) => {
      append(row, "span", "tl-name", name).title = name;
      const lane = append(row, "div", "tl-track");
      const job = append(lane, "span", "tl-job");
      job.style.left = jobX + "%";
      return lane;
    };
    group("R", "Ends with the entrypoint", partition.R, (row, id) => {
      const lane = track(row, nodeLabelOf(id));
      const mark = append(lane, "span", "tl-mark");
      mark.style.left = jobX + "%";
      return nodeLabelOf(id) + ". Ends with the entrypoint, when the job ends. " +
        [attrOf(id, "credential_kind"), attrOf(id, "lifetime")].filter(Boolean).join(", ");
    });
    group("E", "Expires on its own", partition.E, (row, entry) => {
      const lane = track(row, nodeLabelOf(entry.credential));
      const x = xTtl(Number(entry.ttl_seconds));
      const bar = append(lane, "span", "tl-bar tl-bar-e");
      bar.style.width = x + "%";
      const label = append(lane, "span", "tl-ttl", "up to " + ttlText(entry.ttl_seconds));
      label.style.left = x + "%";
      return nodeLabelOf(entry.credential) + ". Expires on its own, up to " + ttlText(entry.ttl_seconds) + ". " +
        attrOf(entry.credential, "credential_kind");
    });
    group("Z", "Potentially survives revocation", partition.Z, (row, entry) => {
      const lane = track(row, nodeLabelOf(entry.credential));
      const windowText = entry.survival_window || "Survival window not recorded";
      append(row.querySelector(".tl-name"), "span", "tl-window", windowText);
      const bounded = entry.lifetime === "persistent_rotating";
      append(lane, "span", "tl-bar tl-bar-z" + (bounded ? " is-bounded" : "")).style.width = bounded ? "84%" : "100%";
      if (!bounded) {
        const arrow = svgNode(lane, "svg", { "class": "tl-arrow", "aria-hidden": "true", focusable: "false" });
        svgNode(arrow, "use", { href: "#i-arrow-right", fill: "currentColor" });
      }
      return nodeLabelOf(entry.credential) + ". Potentially survives entrypoint revocation if the path was exercised. " +
        [windowText, entry.lifetime, "criticality " + entry.criticality].filter(Boolean).join(", ");
    });
    wrap.appendChild(detail);
  }

  function bindTagline() {
    const text = document.getElementById("tagline-text");
    if (!text) { return; }
    const words = text.textContent.trim().split(/\s+/);
    clear(text);
    const spans = words.map((word, index) => {
      const span = append(text, "span", "tl-w", word);
      if (index < words.length - 1) { text.appendChild(document.createTextNode(" ")); }
      return span;
    });
    const syncClass = () => {
      text.classList.toggle("js-words", document.documentElement.getAttribute("data-motion") === "on");
    };
    syncClass();
    new MutationObserver(syncClass).observe(document.documentElement, { attributes: true, attributeFilter: ["data-motion"] });
    if (!("IntersectionObserver" in window)) {
      spans.forEach((span) => span.classList.add("is-on"));
      return;
    }
    const observer = new IntersectionObserver((records) => {
      let order = 0;
      records
        .filter((record) => {
          const top = record.rootBounds ? record.rootBounds.top : 0;
          return record.isIntersecting || record.boundingClientRect.bottom < top;
        })
        .sort((left, right) => spans.indexOf(left.target) - spans.indexOf(right.target))
        .forEach((record) => {
          record.target.style.setProperty("--wd", Math.min(order * 40, 360) + "ms");
          record.target.classList.add("is-on");
          observer.unobserve(record.target);
          order += 1;
        });
    }, { rootMargin: "0px 0px -30% 0px", threshold: 0 });
    spans.forEach((span) => observer.observe(span));
  }

  let effectsReady = false;

  function tagAll(selector, name, value, stagger) {
    document.querySelectorAll(selector).forEach((item, index) => {
      if (!item.hasAttribute(name)) { item.setAttribute(name, value); }
      if (stagger && !item.hasAttribute("data-fx-delay")) {
        item.setAttribute("data-fx-delay", String(Math.min((index % 6) * 70, 420)));
      }
    });
  }

  function decorate() {
    tagAll("details", "data-fx-disclosure", "");
    const readable = ".guide-card, .stat, .outcome, .notes-list li, .evidence-guide, .class-list li";
    tagAll(readable, "data-fx-readable", "", true);
    tagAll(readable, "data-fx-reveal", "", true);
    tagAll(".hero-figure, .guide-card, .outcome, .finding, .cmp-list, .tl-detail", "data-fx-spotlight", "");
    tagAll(".button.primary", "data-fx-magnetic", "");
  }

  function refreshEffects() {
    decorate();
    const fx = window.NHBEffects;
    if (fx && typeof fx.refresh === "function") {
      try { fx.refresh(); } catch (error) { /* the effects layer is decoration only */ }
    }
  }

  function startEffects() {
    decorate();
    const fx = window.NHBEffects;
    if (fx && typeof fx.init === "function") {
      try {
        fx.init(document.documentElement, { motion: window.NHBTheme ? window.NHBTheme.getMotion() : null });
        effectsReady = true;
      } catch (error) { /* the effects layer is decoration only */ }
    }
  }

  function renderFooter() {
    document.getElementById("footer-schema").textContent = "schema " + report.schema;
    document.getElementById("footer-digest").textContent = textOf(report.inputs.digest);
    const list = document.getElementById("footer-data");
    clear(list);
    const files = report.data_files || [];
    if (!files.length) { append(list, "li", "", "No data files recorded."); }
    files.forEach((item) => {
      const row = append(list, "li");
      append(row, "span", "", item.name);
      append(row, "span", "muted", " · verified " + item.verified_on);
    });
    const copyHost = document.getElementById("footer-copy-host");
    if (copyHost) { clear(copyHost); copyButton(copyHost, textOf(report.inputs.digest), "Copy inputs digest from the footer"); }
    document.getElementById("footer-completeness").hidden = !completenessItems().length;
    document.getElementById("footer-print").addEventListener("click", () => window.print());
  }

  function humanKind(kind) {
    return textOf(kind).replace(/_/g, " ").toLowerCase();
  }

  function showGraphPlaceholder() {
    const target = document.getElementById("entity-details");
    clear(target);
    append(
      target,
      "p",
      "entity-placeholder",
      "Select a node or edge to inspect its full identifier, evidence and relationships."
    );
  }

  function setGraphTabStop(target) {
    if (!graphView) { return; }
    graphView.nodes.forEach((node) => node.setAttribute("tabindex", node === target ? "0" : "-1"));
  }

  function selectGraphNode(id, options) {
    const item = nodes.get(id);
    if (!item || !graphView) { return; }
    clearGraphTrace();
    graphSelection = {type: "node", id: id};
    graphView.stage.classList.add("has-selection");
    graphView.nodes.forEach((node) => node.classList.remove("is-selected", "is-neighbor"));
    graphView.edges.forEach((edge) => edge.classList.remove("is-selected-edge", "is-incident"));
    const selected = graphView.nodes.get(id);
    if (!selected) {
      graphView.stage.classList.remove("has-selection");
      showNode(id);
      return;
    }
    selected.classList.add("is-selected");
    setGraphTabStop(selected);
    (report.graph.edges || []).forEach((edge) => {
      if (edge.src !== id && edge.dst !== id) { return; }
      const other = graphView.nodes.get(edge.src === id ? edge.dst : edge.src);
      if (other) { other.classList.add("is-neighbor"); }
      const edgeElement = graphView.edges.get(edge.id);
      if (edgeElement) { edgeElement.classList.add("is-incident"); }
    });
    if (options && options.focus) { selected.focus({preventScroll: true}); }
    showNode(id);
  }

  function selectGraphEdge(id) {
    const item = edges.get(id);
    if (!item || !graphView) { return; }
    clearGraphTrace();
    graphSelection = {type: "edge", id: id};
    graphView.stage.classList.add("has-selection");
    graphView.nodes.forEach((node) => node.classList.remove("is-selected", "is-neighbor"));
    graphView.edges.forEach((edge) => edge.classList.remove("is-selected-edge", "is-incident"));
    const selected = graphView.edges.get(id);
    if (!selected) {
      graphView.stage.classList.remove("has-selection");
      showEdge(id);
      return;
    }
    selected.classList.add("is-selected-edge");
    [item.src, item.dst].forEach((nodeId) => {
      const node = graphView.nodes.get(nodeId);
      if (node) { node.classList.add("is-neighbor"); }
    });
    showEdge(id);
  }

  function clearGraphSelection() {
    graphSelection = null;
    if (graphView) {
      graphView.stage.classList.remove("has-selection");
      graphView.nodes.forEach((node) => node.classList.remove("is-selected", "is-neighbor"));
      graphView.edges.forEach((edge) => edge.classList.remove("is-selected-edge", "is-incident"));
    }
    showGraphPlaceholder();
  }

  function showEvidenceBlock(target, evidence) {
    const block = append(target, "div", "entity-block");
    append(block, "h4", "", "Evidence");
    evidenceList(block, evidence || []);
  }

  function attributeRows(item) {
    const attrs = item.attrs || {};
    return Object.keys(attrs).sort().map((key) => {
      const value = attrs[key];
      let text;
      if (value === null || value === undefined) {
        text = "null";
      } else if (Array.isArray(value)) {
        text = value.length
          ? value.map((entry) => (typeof entry === "object" ? JSON.stringify(entry) : String(entry))).join(", ")
          : "none";
      } else if (typeof value === "object") {
        text = JSON.stringify(value);
      } else {
        text = String(value);
      }
      if (text.length > 220) { text = text.slice(0, 217) + "…"; }
      return [key, text];
    });
  }

  function showAttributes(target, item) {
    const rows = attributeRows(item);
    const block = append(target, "div", "entity-block");
    append(block, "h4", "", "Attributes");
    if (!rows.length) {
      append(block, "p", "empty", "No attributes are recorded.");
      return;
    }
    const list = append(block, "dl", "kv");
    rows.forEach(([key, value]) => {
      const row = append(list, "div");
      append(row, "dt", "mono", key);
      append(row, "dd", "mono", value);
    });
    const details = append(block, "details");
    append(details, "summary", "", "Full attributes (JSON)");
    const pre = append(details, "pre");
    pre.textContent = JSON.stringify(item.attrs || {}, null, 2);
  }

  function relationshipRow(list, edge, otherId, direction) {
    const item = append(list, "li");
    const other = nodes.get(otherId);
    const button = element("button", "trace-link", other ? other.label : otherId);
    button.type = "button";
    button.title = "Select " + nodeLabel(otherId);
    button.addEventListener("click", () => selectGraphNode(otherId, {focus: true}));
    item.appendChild(button);
    append(item, "span", "entity-link-meta", edge.kind + " " + direction + " · confidence " + edge.confidence);
    const edgeButton = element("button", "trace-link", "edge evidence");
    edgeButton.type = "button";
    edgeButton.title = "Show the evidence for this edge";
    edgeButton.addEventListener("click", () => selectGraphEdge(edge.id));
    item.appendChild(edgeButton);
  }

  function showRelationships(target, id) {
    const block = append(target, "div", "entity-block");
    append(block, "h4", "", "Relationships");
    const outgoing = (report.graph.edges || []).filter((edge) => edge.src === id);
    const incoming = (report.graph.edges || []).filter((edge) => edge.dst === id);
    if (!outgoing.length && !incoming.length) {
      append(block, "p", "empty", "No edges touch this entity.");
      return;
    }
    const list = append(block, "ul", "entity-links");
    outgoing.forEach((edge) => relationshipRow(list, edge, edge.dst, "to"));
    incoming.forEach((edge) => relationshipRow(list, edge, edge.src, "from"));
  }

  function entityActions(target, id) {
    const actions = append(target, "div", "entity-actions");
    const trace = element("button", "button quiet", "Trace from the selected entrypoint");
    trace.type = "button";
    trace.addEventListener("click", () => traceTo(id));
    actions.appendChild(trace);
    const clearButton = element("button", "button quiet", "Clear selection");
    clearButton.type = "button";
    clearButton.addEventListener("click", () => {
      clearGraphSelection();
      clearGraphTrace();
    });
    actions.appendChild(clearButton);
  }

  function showNode(id) {
    const item = nodes.get(id);
    if (!item) { showGraphPlaceholder(); return; }
    const target = document.getElementById("entity-details");
    clear(target);
    append(target, "h3", "", item.label);
    append(target, "p", "entity-sub", humanKind(item.kind) + " · " + item.id);
    const tags = append(target, "div", "entity-tags");
    append(tags, "span", "text-chip", humanKind(item.kind));
    if (entryIds.has(id)) { append(tags, "span", "text-chip", "Entrypoint"); }
    if (item.attrs && Number(item.attrs.criticality) >= 80) {
      append(tags, "span", "text-chip", "Critical resource");
    }
    entityActions(target, id);
    showEvidenceBlock(target, item.evidence);
    showRelationships(target, id);
    showAttributes(target, item);
    animatePresence(target);
  }

  function showEdge(id) {
    const item = edges.get(id);
    if (!item) { return; }
    const target = document.getElementById("entity-details");
    clear(target);
    append(target, "h3", "", humanKind(item.kind) + " edge");
    append(target, "p", "entity-sub", item.src + " -> " + item.dst);
    const tags = append(target, "div", "entity-tags");
    append(tags, "span", "text-chip", "Confidence " + item.confidence);
    if (item.lifetime) { append(tags, "span", "text-chip", "Lifetime " + item.lifetime); }
    const actions = append(target, "div", "entity-actions");
    [["Source", item.src], ["Target", item.dst]].forEach(([label, nodeId]) => {
      const button = element("button", "button quiet", label + ": " + (nodes.get(nodeId) || {label: nodeId}).label);
      button.type = "button";
      button.addEventListener("click", () => selectGraphNode(nodeId, {focus: true}));
      actions.appendChild(button);
    });
    const clearButton = element("button", "button quiet", "Clear selection");
    clearButton.type = "button";
    clearButton.addEventListener("click", () => {
      clearGraphSelection();
      clearGraphTrace();
    });
    actions.appendChild(clearButton);
    if (item.confidence === "unknown") {
      append(
        target,
        "p",
        "note",
        "UNKNOWN-class edges are potential only; they do not contribute to R, E or Z."
      );
    }
    animatePresence(target);
    showEvidenceBlock(target, item.evidence);
    append(
      target,
      "p",
      "muted",
      "Edge confidence is the weakest evidence class recorded on this edge."
    );
    showAttributes(target, item);
  }

  function moveGraphFocus(current, horizontal, vertical) {
    if (!graphView) { return; }
    const centre = (node) => ({
      x: Number(node.getAttribute("data-x")) + Number(node.getAttribute("data-width")) / 2,
      y: Number(node.getAttribute("data-y")) + Number(node.getAttribute("data-height")) / 2
    });
    const origin = centre(current);
    let best = null;
    let bestScore = Infinity;
    graphView.nodes.forEach((candidate) => {
      if (candidate === current) { return; }
      const point = centre(candidate);
      const dx = point.x - origin.x;
      const dy = point.y - origin.y;
      const primary = dx * horizontal + dy * vertical;
      if (primary <= 4) { return; }
      const secondary = Math.abs(dx * vertical - dy * horizontal);
      const score = primary + secondary * 1.6;
      if (score < bestScore) { bestScore = score; best = candidate; }
    });
    if (best) {
      setGraphTabStop(best);
      best.focus({preventScroll: true});
    }
  }

  function applyGraphTransform(animate) {
    if (!graphView) { return; }
    graphView.viewport.classList.toggle(
      "is-animated",
      Boolean(animate) && motionEnabled()
    );
    graphView.viewport.style.transform =
      "translate(" + graphView.x + "px, " + graphView.y + "px) scale(" + graphView.scale + ")";
    const rect = graphView.stage.getBoundingClientRect();
    const pannable =
      graphView.width * graphView.scale > rect.width + 1 ||
      graphView.height * graphView.scale > rect.height + 1;
    graphView.stage.classList.toggle("is-pannable", pannable);
    const level = document.getElementById("graph-zoom-level");
    if (level) {
      const percent = Math.round(graphView.scale * 100);
      level.textContent = percent + "%";
      level.setAttribute(
        "aria-label",
        "Zoom " + percent + " percent. Activate to reset to 100 percent."
      );
    }
  }

  function clampGraphView() {
    if (!graphView) { return; }
    const rect = graphView.stage.getBoundingClientRect();
    const width = graphView.width * graphView.scale;
    const height = graphView.height * graphView.scale;
    if (width <= rect.width) {
      graphView.x = (rect.width - width) / 2;
    } else {
      graphView.x = Math.min(0, Math.max(rect.width - width, graphView.x));
    }
    if (height <= rect.height) {
      graphView.y = (rect.height - height) / 2;
    } else {
      graphView.y = Math.min(0, Math.max(rect.height - height, graphView.y));
    }
  }

  function fitGraph(animate) {
    if (!graphView) { return; }
    const rect = graphView.stage.getBoundingClientRect();
    if (!rect.width || !rect.height) { return; }
    const pad = rect.width < 640 ? 16 : 28;
    const scale = Math.min(
      (rect.width - pad * 2) / graphView.width,
      (rect.height - pad * 2) / graphView.height,
      1.2
    );
    graphView.scale = Math.max(0.08, scale);
    graphView.x = (rect.width - graphView.width * graphView.scale) / 2;
    graphView.y = (rect.height - graphView.height * graphView.scale) / 2;
    graphView.adjusted = false;
    applyGraphTransform(animate);
  }

  function initialGraphView(animate) {
    if (!graphView) { return; }
    const rect = graphView.stage.getBoundingClientRect();
    if (!rect.width || !rect.height) { return; }
    const pad = rect.width < 640 ? 16 : 28;
    const fit = Math.min(
      (rect.width - pad * 2) / graphView.width,
      (rect.height - pad * 2) / graphView.height,
      1.2
    );
    if (fit >= 0.62) { fitGraph(animate); return; }
    const scenario = scenarios[currentScenarioIndex] || null;
    const candidates = (scenario && scenario.start_nodes) || Array.from(entryIds);
    let anchor = null;
    for (const id of candidates) {
      const node = graphView.nodes.get(id);
      if (node) { anchor = node; break; }
    }
    graphView.scale = 1;
    const centerX = anchor
      ? Number(anchor.getAttribute("data-x")) + Number(anchor.getAttribute("data-width")) / 2
      : graphView.width / 2;
    const centerY = anchor
      ? Number(anchor.getAttribute("data-y")) + Number(anchor.getAttribute("data-height")) / 2
      : graphView.height / 2;
    graphView.x = rect.width / 2 - centerX;
    graphView.y = rect.height / 2 - centerY;
    graphView.adjusted = true;
    clampGraphView();
    applyGraphTransform(animate);
  }

  function zoomAt(clientX, clientY, factor, animate) {
    if (!graphView) { return; }
    const rect = graphView.stage.getBoundingClientRect();
    const pointX = clientX === null || clientX === undefined ? rect.width / 2 : clientX - rect.left;
    const pointY = clientY === null || clientY === undefined ? rect.height / 2 : clientY - rect.top;
    const next = Math.min(3, Math.max(0.08, graphView.scale * factor));
    if (next === graphView.scale) { return; }
    const ratio = next / graphView.scale;
    graphView.x = pointX - (pointX - graphView.x) * ratio;
    graphView.y = pointY - (pointY - graphView.y) * ratio;
    graphView.scale = next;
    graphView.adjusted = true;
    clampGraphView();
    applyGraphTransform(animate);
  }

  function resetGraphZoom(animate) {
    if (!graphView) { return; }
    const rect = graphView.stage.getBoundingClientRect();
    graphView.scale = 1;
    graphView.x = (rect.width - graphView.width) / 2;
    graphView.y = (rect.height - graphView.height) / 2;
    graphView.adjusted = true;
    clampGraphView();
    applyGraphTransform(animate);
  }

  function applyGraphFocus(scenario) {
    if (!graphView) { return; }
    graphView.nodes.forEach((node) => node.classList.remove("is-outside"));
    graphView.edges.forEach((edge) => edge.classList.remove("is-outside"));
    const focus = new Set();
    if (scenario) {
      const queue = (scenario.start_nodes || []).slice();
      queue.forEach((id) => focus.add(id));
      while (queue.length) {
        const id = queue.shift();
        (adjacency.get(id) || []).forEach((edge) => {
          if (!focus.has(edge.dst)) {
            focus.add(edge.dst);
            queue.push(edge.dst);
          }
        });
      }
    }
    if (!focus.size) { return; }
    graphView.nodes.forEach((node, id) => {
      if (!focus.has(id)) { node.classList.add("is-outside"); }
    });
    graphView.edges.forEach((edgeElement, id) => {
      const item = edges.get(id);
      if (item && !focus.has(item.src)) {
        edgeElement.classList.add("is-outside");
      }
    });
  }

  function updateGraphCount() {
    const target = document.getElementById("graph-count");
    if (!target) { return; }
    const totalNodes = (report.graph.nodes || []).length;
    const totalEdges = (report.graph.edges || []).length;
    const drawnNodes = graphView ? graphView.nodes.size : totalNodes;
    const drawnEdges = graphView ? graphView.edges.size : totalEdges;
    if (drawnNodes < totalNodes) {
      target.textContent = "Rendering " + drawnNodes + " of " + totalNodes + " nodes · " +
        drawnEdges + " of " + totalEdges + " edges";
      return;
    }
    target.textContent = plural(totalNodes, "node") + " · " + plural(totalEdges, "edge") + " · grouped by authority stage";
  }

  function renderGraph(scenario) {
    applyGraphFocus(scenario);
    clearGraphTrace();
    if (graphSelection) {
      clearGraphSelection();
    } else {
      showGraphPlaceholder();
    }
    updateGraphCount();
  }

  function endGraphPointer(event) {
    if (!graphView) { return; }
    graphView.pointers.delete(event.pointerId);
    if (graphView.stage.hasPointerCapture(event.pointerId)) {
      graphView.stage.releasePointerCapture(event.pointerId);
    }
    if (graphView.pointers.size === 0) {
      const tap = graphView.tap && !graphView.moved && event.type === "pointerup";
      graphView.panning = false;
      graphView.pinch = null;
      graphView.moved = false;
      graphView.tap = null;
      graphView.stage.classList.remove("is-panning");
      if (tap) { selectAt(event.clientX, event.clientY); }
    } else if (graphView.pointers.size === 1) {
      graphView.panning = false;
      graphView.pinch = null;
    }
  }

  function selectAt(clientX, clientY) {
    const hit = document.elementFromPoint(clientX, clientY);
    if (!hit || !graphView.stage.contains(hit)) { return; }
    const node = hit.closest ? hit.closest(".gnode") : null;
    if (node) { selectGraphNode(node.getAttribute("data-id"), {focus: false}); return; }
    const edge = hit.closest ? hit.closest(".gedge") : null;
    if (edge) { selectGraphEdge(edge.getAttribute("data-id")); return; }
    clearGraphSelection();
  }

  function bindGraphEvents() {
    const stage = graphView.stage;
    const svg = graphView.svg;
    stage.addEventListener("dblclick", (event) => {
      const hit = document.elementFromPoint(event.clientX, event.clientY);
      const node = hit && hit.closest ? hit.closest(".gnode") : null;
      if (node) { return; }
      zoomAt(event.clientX, event.clientY, 1.5, true);
    });
    svg.addEventListener("keydown", (event) => {
      const current = event.target.closest ? event.target.closest(".gnode") : null;
      if (!current) { return; }
      if (event.key === "Enter" || event.key === " " || event.key === "Spacebar") {
        event.preventDefault();
        selectGraphNode(current.getAttribute("data-id"), {focus: true});
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        clearGraphSelection();
        clearGraphTrace();
        return;
      }
      if (event.key === "Home" || event.key === "End") {
        event.preventDefault();
        const all = Array.from(graphView.nodes.values());
        const target = event.key === "Home" ? all[0] : all[all.length - 1];
        if (target) { setGraphTabStop(target); target.focus({preventScroll: true}); }
        return;
      }
      const directions = {
        ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]
      };
      const direction = directions[event.key];
      if (direction) {
        event.preventDefault();
        moveGraphFocus(current, direction[0], direction[1]);
      }
    });
    stage.addEventListener("pointerdown", (event) => {
      if (event.pointerType === "mouse" && event.button !== 0) { return; }
      graphView.pointers.set(event.pointerId, {x: event.clientX, y: event.clientY});
      if (graphView.pointers.size === 1) {
        graphView.panning = true;
        graphView.panStart = {x: event.clientX, y: event.clientY, x0: graphView.x, y0: graphView.y};
        graphView.moved = false;
        graphView.tap = true;
        stage.setPointerCapture(event.pointerId);
      } else if (graphView.pointers.size === 2) {
        const points = Array.from(graphView.pointers.values());
        graphView.pinch = {distance: Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y)};
        graphView.tap = false;
        graphView.panning = false;
      }
    });
    stage.addEventListener("pointermove", (event) => {
      if (!graphView.pointers.has(event.pointerId)) { return; }
      graphView.pointers.set(event.pointerId, {x: event.clientX, y: event.clientY});
      if (graphView.pointers.size >= 2 && graphView.pinch) {
        const points = Array.from(graphView.pointers.values());
        const distance = Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y);
        if (graphView.pinch.distance > 0 && distance > 0) {
          const factor = distance / graphView.pinch.distance;
          zoomAt(
            (points[0].x + points[1].x) / 2,
            (points[0].y + points[1].y) / 2,
            factor,
            false
          );
          graphView.pinch.distance = distance;
        }
        return;
      }
      if (!graphView.panning || !graphView.panStart) { return; }
      const dx = event.clientX - graphView.panStart.x;
      const dy = event.clientY - graphView.panStart.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) {
        graphView.moved = true;
        stage.classList.add("is-panning");
      }
      graphView.x = graphView.panStart.x0 + dx;
      graphView.y = graphView.panStart.y0 + dy;
      graphView.adjusted = true;
      clampGraphView();
      applyGraphTransform(false);
    });
    stage.addEventListener("pointerup", endGraphPointer);
    stage.addEventListener("pointercancel", endGraphPointer);
    stage.addEventListener("wheel", (event) => {
      if (!event.ctrlKey && !event.metaKey) { return; }
      event.preventDefault();
      zoomAt(event.clientX, event.clientY, event.deltaY < 0 ? 1.12 : 0.9, false);
    }, {passive: false});
  }

  function initGraph() {
    const svg = document.getElementById("graph-svg");
    const stage = document.getElementById("graph-stage");
    if (!svg || !stage) { return; }
    const viewport = svg.querySelector(".graph-viewport");
    const nodeElements = new Map();
    svg.querySelectorAll(".gnode").forEach((node) => {
      const id = node.getAttribute("data-id");
      if (id !== null) { nodeElements.set(id, node); }
    });
    const edgeElements = new Map();
    svg.querySelectorAll(".gedge").forEach((edge) => {
      const id = edge.getAttribute("data-id");
      if (id !== null) { edgeElements.set(id, edge); }
    });
    const width = Number(svg.getAttribute("data-width")) || (svg.viewBox.baseVal && svg.viewBox.baseVal.width) || 640;
    const height = Number(svg.getAttribute("data-height")) || (svg.viewBox.baseVal && svg.viewBox.baseVal.height) || 160;
    graphView = {
      svg: svg,
      stage: stage,
      viewport: viewport,
      nodes: nodeElements,
      edges: edgeElements,
      width: width,
      height: height,
      scale: 1,
      x: 0,
      y: 0,
      adjusted: false,
      pointers: new Map(),
      panning: false,
      pinch: null,
      panStart: null,
      moved: false,
      tap: false
    };
    svg.style.width = width + "px";
    svg.style.height = height + "px";
    if (!nodeElements.size) {
      ["graph-zoom-out", "graph-zoom-level", "graph-zoom-in", "graph-fit"].forEach((id) => {
        const control = document.getElementById(id);
        if (control) { control.disabled = true; }
      });
      showGraphPlaceholder();
      updateGraphCount();
      return;
    }
    const first = nodeElements.values().next().value;
    if (first) { first.setAttribute("tabindex", "0"); }
    bindGraphEvents();
    initialGraphView(false);
    window.requestAnimationFrame(() => initialGraphView(false));
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(() => {
        if (graphView && !graphView.adjusted) { fitGraph(false); }
      });
    }
    if (window.ResizeObserver) {
      const observer = new window.ResizeObserver(() => {
        if (!graphView) { return; }
        if (!graphView.adjusted) {
          fitGraph(false);
        } else {
          clampGraphView();
          applyGraphTransform(false);
        }
      });
      observer.observe(stage);
    }
    applyGraphFocus(scenarios[currentScenarioIndex] || null);
    showGraphPlaceholder();
    updateGraphCount();
  }

  function bindSectionNav() {
    const nav = document.querySelector(".toc");
    if (!nav) { return; }
    const track = nav.querySelector(".toc-track") || nav;
    const bar = document.querySelector(".nav-bar");
    const toggle = document.getElementById("nav-toggle");
    const currentLabel = document.getElementById("nav-current");
    const phone = window.matchMedia ? window.matchMedia("(max-width: 760px)") : null;
    const entries = [];
    nav.querySelectorAll('a[href^="#"]').forEach((link) => {
      if (link.hidden) { return; }
      const target = document.getElementById(link.getAttribute("href").slice(1));
      if (!target || target.hidden) { return; }
      entries.push({ id: target.id, link: link, target: target });
    });
    if (!entries.length) { return; }
    const indicator = nav.querySelector(".nav-indicator");
    const placeIndicator = (link) => {
      if (!indicator) { return; }
      const left = link.offsetLeft + 12;
      const width = Math.max(link.offsetWidth - 24, 8);
      indicator.style.transform = "translateX(" + left + "px) scaleX(" + width + ")";
      indicator.classList.add("is-active");
    };
    const updateFades = () => {
      const overflowing = track.scrollWidth > track.clientWidth + 2;
      track.style.setProperty("--fade-l", overflowing && track.scrollLeft > 2 ? "24px" : "0px");
      track.style.setProperty(
        "--fade-r",
        overflowing && track.scrollLeft + track.clientWidth < track.scrollWidth - 2 ? "24px" : "0px"
      );
    };
    let current = "";
    const setCurrent = (id) => {
      if (!id || id === current) { return; }
      current = id;
      entries.forEach((entry) => {
        if (entry.id === id) {
          entry.link.setAttribute("aria-current", "location");
        } else {
          entry.link.removeAttribute("aria-current");
        }
      });
      const active = entries.find((entry) => entry.id === id);
      if (!active) { return; }
      if (currentLabel) { currentLabel.textContent = active.link.textContent; }
      placeIndicator(active.link);
      if (track.scrollWidth > track.clientWidth + 2 && !(phone && phone.matches)) {
        const left = active.link.offsetLeft - (track.clientWidth - active.link.offsetWidth) / 2;
        track.scrollTo({ left: Math.max(left, 0), behavior: motionEnabled() ? "smooth" : "auto" });
      }
    };
    const update = () => {
      const navBottom = bar ? bar.getBoundingClientRect().bottom : 0;
      const line = navBottom + 28;
      let active = entries[0].id;
      entries.forEach((entry) => {
        if (entry.target.getBoundingClientRect().top <= line) {
          active = entry.id;
        }
      });
      if (window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2) {
        active = entries[entries.length - 1].id;
      }
      setCurrent(active);
    };
    let frame = 0;
    const schedule = () => {
      if (frame) { return; }
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        update();
      });
    };
    const reposition = () => {
      const entry = entries.find((item) => item.id === current);
      if (entry) { placeIndicator(entry.link); }
      updateFades();
    };
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", () => { schedule(); reposition(); });
    track.addEventListener("scroll", updateFades, { passive: true });
    if (document.fonts && document.fonts.ready) { document.fonts.ready.then(reposition); }

    const setOpen = (open) => {
      if (!bar || !toggle) { return; }
      bar.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      document.documentElement.classList.toggle("nav-locked", open);
      if (open) {
        const first = nav.querySelector("a:not([hidden])");
        if (first) { first.focus(); }
      }
    };
    if (toggle) {
      toggle.addEventListener("click", () => setOpen(!bar.classList.contains("is-open")));
      nav.addEventListener("click", (event) => {
        if (event.target && event.target.closest && event.target.closest("a")) { setOpen(false); }
      });
      document.addEventListener("keydown", (event) => {
        if (!bar.classList.contains("is-open")) { return; }
        if (event.key === "Escape") {
          setOpen(false);
          toggle.focus();
          return;
        }
        if (event.key !== "Tab") { return; }
        // The cycle is explicit: browsers differ on whether links are Tab stops.
        const stops = [toggle].concat(Array.from(nav.querySelectorAll("a:not([hidden])")));
        const at = stops.indexOf(document.activeElement);
        const step = event.shiftKey ? -1 : 1;
        const next = stops[(at + step + stops.length) % stops.length];
        event.preventDefault();
        next.focus();
      });
      if (phone && phone.addEventListener) {
        phone.addEventListener("change", () => { if (!phone.matches) { setOpen(false); } });
      }
    }
    updateFades();
    update();
  }

  function bindPointerLighting() {
    if (prefersReducedMotion()) { return; }
    if (!window.matchMedia || !window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
      return;
    }
    document.querySelectorAll("[data-light]").forEach((target) => {
      let frame = 0;
      let point = null;
      const paint = () => {
        frame = 0;
        if (!point) { return; }
        const rect = target.getBoundingClientRect();
        target.style.setProperty("--light-x", Math.round(point.x - rect.left) + "px");
        target.style.setProperty("--light-y", Math.round(point.y - rect.top) + "px");
      };
      target.addEventListener("pointermove", (event) => {
        if (event.pointerType && event.pointerType !== "mouse") { return; }
        point = {x: event.clientX, y: event.clientY};
        target.classList.add("is-lit");
        if (!frame) { frame = window.requestAnimationFrame(paint); }
      });
      target.addEventListener("pointerleave", () => {
        if (frame) { window.cancelAnimationFrame(frame); frame = 0; }
        point = null;
        target.classList.remove("is-lit");
      });
    });
  }

  document.getElementById("schema-line").textContent = "schema " + report.schema;
  document.getElementById("tool-line").textContent =
    report.tool.name + " " + report.tool.version + " · report schema " + report.schema;
  document.getElementById("repo-line").textContent = "Repository " + report.inputs.repo_slug;
  renderSourceLine();
  renderScope();
  renderFindings();
  renderAssumptions();
  renderDiagnostics();
  renderCompleteness();
  renderFooter();
  document.getElementById("matrix-shared").addEventListener("change", renderMatrix);
  document.getElementById("graph-zoom-in").addEventListener("click", () => zoomAt(null, null, 1.25, true));
  document.getElementById("graph-zoom-out").addEventListener("click", () => zoomAt(null, null, 0.8, true));
  document.getElementById("graph-zoom-level").addEventListener("click", () => resetGraphZoom(true));
  document.getElementById("graph-fit").addEventListener("click", () => fitGraph(true));
  renderScenarioPicker();
  initGraph();
  bindSectionNav();
  bindPointerLighting();
  const printOpened = [];
  window.addEventListener("beforeprint", () => {
    printOpened.length = 0;
    document.querySelectorAll("details:not([open])").forEach((item) => {
      item.open = true;
      printOpened.push(item);
    });
  });
  window.addEventListener("afterprint", () => {
    printOpened.forEach((item) => { item.open = false; });
    printOpened.length = 0;
  });
  document.getElementById("print-button").addEventListener("click", () => window.print());
  document.addEventListener("click", (event) => {
    const link = event.target && event.target.closest ? event.target.closest('a[href^="#"]') : null;
    if (!link || link.getAttribute("href").length < 2) { return; }
    const target = document.getElementById(link.getAttribute("href").slice(1));
    if (target) { revealDisclosure(target); }
  });
  window.addEventListener("hashchange", revealHash);
  if (window.location.hash.length > 1) { revealHash(); }
  bootComplete = true;
  window.clearTimeout(bootFallback);
  bindTagline();
  window.requestAnimationFrame(() => {
    document.documentElement.classList.remove("booting");
    startEffects();
  });
}).call(window);
"""

# The labels are fixed product wording (core.completeness.FAMILY_LABELS), not report data. They are
# embedded as JSON with markup characters escaped, like the data island.
_FAMILY_LABELS_JSON = (
    json.dumps({family.value: label for family, label in FAMILY_LABELS.items()}, sort_keys=True)
    .replace("<", "\\u003c")
    .replace(">", "\\u003e")
    .replace("&", "\\u0026")
)
APP_JS = _APP_JS_SOURCE.replace("__FAMILY_LABELS__", _FAMILY_LABELS_JSON)
