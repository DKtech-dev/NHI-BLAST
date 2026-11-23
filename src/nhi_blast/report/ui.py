"""Markup, styles and the inline application script for the offline report."""

from __future__ import annotations

import json
from importlib import resources as _resources

from nhi_blast.core.completeness import FAMILY_LABELS
from nhi_blast.report.effects import EFFECTS_CSS

# Theme model: the effective theme lives
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


_TEMPLATES = _resources.files("nhi_blast.report.templates")


def _load_template_text(name: str) -> str:
    return _TEMPLATES.joinpath(name).read_text(encoding="utf-8")


THEME_JS: str = _load_template_text("theme.js")

_REPORT_CSS: str = _load_template_text("report.css") + "\n" + EFFECTS_CSS
_TEMPLATE_SOURCE: str = _load_template_text("report.html").replace("__REPORT_CSS__", _REPORT_CSS, 1)

TEMPLATE: str = _TEMPLATE_SOURCE.replace("__THEME_TOKENS__", THEME_TOKENS_CSS, 1).replace(
    "__THEME_SWITCH_CSS__", THEME_SWITCH_CSS, 1
)

_FAMILY_LABELS_JSON: str = (
    json.dumps(
        {family.value: label for family, label in FAMILY_LABELS.items()},
        sort_keys=True,
        separators=(",", ":"),
    )
    .replace("<", "\\u003c")
    .replace(">", "\\u003e")
)

_APP_JS_SOURCE: str = _load_template_text("app.js")
APP_JS: str = _APP_JS_SOURCE.replace("__FAMILY_LABELS__", _FAMILY_LABELS_JSON)

__all__ = ["APP_JS", "TEMPLATE", "THEME_JS", "THEME_SWITCH_CSS", "THEME_TOKENS_CSS"]
