"""Themes, owner design system tokens, switchers and the early script (plan G0, G4, G5, G6)."""

from __future__ import annotations

import base64
import hashlib
import html as html_module
import json
import re
from functools import cache
from html.parser import HTMLParser
from pathlib import Path

import pytest

from nhi_blast.pipeline import ScanOptions, run_scan
from nhi_blast.report.effects import EFFECTS_CSS, EFFECTS_JS
from nhi_blast.report.html import html_report
from nhi_blast.report.ui import APP_JS, THEME_JS, THEME_SWITCH_CSS, THEME_TOKENS_CSS
from tests.report_support import make_report

FX07 = Path(__file__).parent / "fixtures" / "fx07-incident"
ASSETS = Path(__file__).resolve().parents[1] / "src" / "nhi_blast" / "report" / "assets"
ACTION = "action:tj-actions/changed-files@v45"
# G6: the budget rose from 600 KB to 650 KB for the effects script and stylesheet, the new
# sections and the two fonts that replaced Geist and Instrument Serif.
SIZE_BUDGET_BYTES = 650 * 1024


class _Scripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.scripts: list[tuple[dict[str, str | None], str]] = []
        self._open: tuple[dict[str, str | None], list[str]] | None = None
        self.in_head = False
        self.head_scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "head":
            self.in_head = True
        if tag == "script":
            self._open = (dict(attrs), [])

    def handle_endtag(self, tag: str) -> None:
        if tag == "head":
            self.in_head = False
        if tag == "script" and self._open is not None:
            attrs, parts = self._open
            body = "".join(parts)
            self.scripts.append((attrs, body))
            if self.in_head:
                self.head_scripts.append(body)
            self._open = None

    def handle_data(self, data: str) -> None:
        if self._open is not None:
            self._open[1].append(data)


@cache
def _fx07_document() -> str:
    outcome = run_scan(ScanOptions(root=FX07, selectors=(ACTION,)))
    return html_report(outcome.report)


def _style(document: str) -> str:
    return document.split("<style>", 1)[1].split("</style>", 1)[0]


def _block(css: str, opening: str) -> str:
    start = css.index(opening + " {")
    end = css.index("\n}", start)
    return css[start : end + 2]


def _properties(block: str) -> dict[str, str]:
    return {
        name: value.strip()
        for name, value in re.findall(r"^\s*(--[A-Za-z0-9-]+):\s*([^;]+);", block, re.MULTILINE)
    }


def _resolve(props: dict[str, str]) -> dict[str, str]:
    """Palette properties plus the mapped old token names, keyed without the leading dashes."""
    mapping = _properties(_block(THEME_TOKENS_CSS, ":root, .passage"))
    resolved = {name[2:]: value for name, value in props.items()}
    for name in list(resolved):
        if name.startswith("dp-"):
            resolved.setdefault(name[3:], resolved[name])
    for name, value in mapping.items():
        match = re.fullmatch(r"var\((--[A-Za-z0-9-]+)\)", value)
        assert match is not None, f"{name}: {value}"
        resolved[name[2:]] = props[match.group(1)]
    return resolved


def _raw(opening: str, scope: str | None = None) -> dict[str, str]:
    css = THEME_TOKENS_CSS if scope is None else scope
    return _properties(_block(css, opening))


def _print_css() -> str:
    return THEME_TOKENS_CSS[THEME_TOKENS_CSS.index("@media print") :]


def _forced_css() -> str:
    start = THEME_TOKENS_CSS.index("@media (forced-colors: active)")
    return THEME_TOKENS_CSS[start : THEME_TOKENS_CSS.index("@media print")]


ROOTS = ":root, :root[data-theme], :root .passage, :root[data-theme] .passage"
RAW = {
    "dark": _raw(':root, :root[data-theme="dark"]'),
    "light": _raw(':root[data-theme="light"]'),
    "passage-dark": _raw(':root .passage, :root[data-theme="dark"] .passage'),
    "passage-light": _raw(':root[data-theme="light"] .passage'),
}
PALETTES = {name: _resolve(props) for name, props in RAW.items()}


def _luminance(colour: str) -> float:
    text = colour.lstrip("#")
    if len(text) == 3:
        text = "".join(char * 2 for char in text)
    channels = [int(text[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [
        value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(foreground: str, background: str) -> float:
    first, second = _luminance(foreground), _luminance(background)
    high, low = max(first, second), min(first, second)
    return (high + 0.05) / (low + 0.05)


def _mix(top: str, bottom: str, alpha: float) -> str:
    a = top.lstrip("#")
    b = bottom.lstrip("#")
    parts = [
        round(int(a[i : i + 2], 16) * alpha + int(b[i : i + 2], 16) * (1 - alpha))
        for i in (0, 2, 4)
    ]
    return "#" + "".join(f"{part:02x}" for part in parts)


def _is_hex(value: str) -> bool:
    return re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", value) is not None


SURFACES = ("bg", "surface", "surface-2", "raised")
# (foreground token, background tokens, minimum ratio, what the pair is used for)
PAIRS: tuple[tuple[str, tuple[str, ...], float, str], ...] = (
    *((role, SURFACES, 4.5, "body and secondary text") for role in ("ink", "ink-2", "muted")),
    ("ink", ("hover",), 4.5, "text on hovered controls"),
    ("ink-2", ("hover",), 4.5, "text on hovered controls"),
    ("muted", ("hover",), 4.5, "metadata on hovered controls"),
    ("accent", (*SURFACES, "accent-soft"), 4.5, "accent text and selected states"),
    ("accent-ink", ("accent", "accent-hover"), 4.5, "primary button label"),
    ("critical-ink", ("critical-soft", "accent-soft", "surface", "bg", "raised"), 4.5, "critical"),
    ("high-ink", ("high-soft", "surface", "bg", "raised"), 4.5, "high badge"),
    ("warning-ink", ("warning-soft", "surface", "bg", "raised"), 4.5, "medium badge and notice"),
    ("low-ink", ("low-soft", "surface", "bg", "raised"), 4.5, "low badge"),
    ("neutral-ink", ("neutral-soft", "surface"), 4.5, "info badge"),
    ("warning", ("warning-soft",), 4.5, "E code chip"),
    ("R", ("raised", "surface"), 4.5, "R code chip and figures"),
    ("Z", ("surface", "raised"), 4.5, "Z figures and chips"),
    ("positive", ("raised", "surface-2", "surface"), 4.5, "positive state text"),
    ("critical", ("node-fill", "surface"), 4.5, "graph critical badge text"),
    ("accent", ("node-fill",), 4.5, "graph entry badge text"),
    ("muted", ("node-fill",), 4.5, "graph separators and meta text"),
    ("ink", ("node-fill",), 4.5, "graph node labels"),
    ("on-field", ("field",), 4.5, "text on the dark field"),
    ("on-field-secondary", ("field",), 4.5, "secondary text on the dark field"),
    # UI components and graphics: 3:1 (WCAG 2.x 1.4.11).
    ("border-strong", ("bg", "surface", "surface-2"), 3.0, "input and control boundaries"),
    ("focus", ("bg", "surface", "surface-2", "raised"), 3.0, "focus ring"),
    ("E", ("surface",), 3.0, "E bars"),
    ("graph-edge", ("node-fill", "surface"), 3.0, "graph edges"),
    ("node-structure", ("node-fill",), 3.0, "graph node strokes"),
    ("node-workflow", ("node-fill",), 3.0, "graph node strokes"),
    ("node-oidc", ("node-fill",), 3.0, "graph node strokes"),
    ("node-role", ("node-fill",), 3.0, "graph node strokes"),
    ("node-sink", ("node-fill",), 3.0, "graph node strokes"),
    ("node-credential", ("node-fill",), 3.0, "graph node strokes"),
)


def test_contrast_helper_matches_wcag_reference_values() -> None:
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast("#777777", "#ffffff") == pytest.approx(4.48, abs=0.01)
    assert contrast("#ffffff", "#ffffff") == pytest.approx(1.0)


@pytest.mark.parametrize("palette", sorted(PALETTES))
def test_token_pairs_meet_contrast_minimums_in_every_palette(palette: str) -> None:
    tokens = PALETTES[palette]
    failures: list[str] = []
    for foreground, backgrounds, minimum, usage in PAIRS:
        for background in backgrounds:
            fg_value, bg_value = tokens[foreground], tokens[background]
            assert _is_hex(fg_value), f"{palette} {foreground} is not a hex colour: {fg_value}"
            assert _is_hex(bg_value), f"{palette} {background} is not a hex colour: {bg_value}"
            ratio = contrast(fg_value, bg_value)
            if ratio < minimum:
                failures.append(
                    f"{palette}: {foreground} {fg_value} on {background} {bg_value} = "
                    f"{ratio:.2f} < {minimum} ({usage})"
                )
    assert not failures, "\n".join(failures)


def test_contrast_test_reads_tokens_from_the_generated_document() -> None:
    style = _style(html_report(make_report()))
    assert _properties(_block(style, ':root[data-theme="light"]')) == RAW["light"]
    assert _properties(_block(style, ':root, :root[data-theme="dark"]')) == RAW["dark"]


def test_every_palette_defines_the_same_tokens() -> None:
    reference = set(RAW["light"])
    for name, props in RAW.items():
        assert set(props) == reference, name
    assert set(_raw(ROOTS, _print_css())) == reference
    dp = {name for name in reference if name.startswith("--dp-")}
    assert dp >= {
        "--dp-ground",
        "--dp-ink",
        "--dp-ink-secondary",
        "--dp-ground-muted",
        "--dp-rule",
        "--dp-accent",
        "--dp-field",
        "--dp-on-field",
        "--dp-on-field-secondary",
        "--dp-panel",
        "--dp-on-accent",
    }


def test_light_theme_uses_the_owner_design_system_values() -> None:
    light = RAW["light"]
    owner = {
        "--dp-ground": "#fcfcfd",
        "--dp-ink": "#16191f",
        "--dp-ink-secondary": "#454c58",
        "--dp-ground-muted": "#f3f4f6",
        "--dp-rule": "#dde0e6",
        "--dp-accent": "#074ce0",
        "--dp-field": "#16191f",
        "--dp-on-field": "#fcfcfd",
        "--dp-on-field-secondary": "#d0d4dd",
        "--dp-panel": "#ffffff",
        "--dp-on-accent": "#ffffff",
    }
    for name, value in owner.items():
        assert light[name] == value, name
    shared = _raw(":root", _block(THEME_TOKENS_CSS, ":root") + "\n")
    assert shared["--dp-gap"] == "24px"
    assert shared["--dp-radius-panel"] == "12px"
    assert shared["--dp-hairline"] == "1px"
    assert shared["--dp-motion"].startswith("300ms cubic-bezier(.22, 1, .36, 1)")


def test_dark_theme_follows_the_owner_dark_brief() -> None:
    dark = RAW["dark"]
    assert dark["--dp-ground"] == "#0e1116"
    assert dark["--dp-ground-muted"] == "#151922"
    assert dark["--dp-panel"] == "#181c24"
    assert dark["--dp-ink"] == "#f3f5f8"
    assert dark["--dp-ink-secondary"] == "#b4bcc9"
    assert dark["--dp-rule"] == "#2a303b"
    assert dark["--dp-accent"] == "#6f9bff"
    assert dark["--dp-field"] == "#07090d"
    # The two dark passages: deeper than the page in the dark theme, a dark field in the light one.
    assert PALETTES["passage-dark"]["bg"] == "#07090d"
    assert PALETTES["passage-light"]["bg"] == "#16191f"
    assert _luminance(PALETTES["passage-dark"]["bg"]) < _luminance(dark["--dp-ground"])


def test_each_theme_sets_color_scheme_and_print_forces_the_light_palette() -> None:
    assert "color-scheme: dark;" in _block(THEME_TOKENS_CSS, ':root, :root[data-theme="dark"]')
    assert "color-scheme: light;" in _block(THEME_TOKENS_CSS, ':root[data-theme="light"]')
    printed = _block(_print_css(), "  " + ROOTS)
    assert "color-scheme: light;" in printed
    props = _properties(printed)
    assert props["--dp-ground"] == "#ffffff"
    assert props["--dp-panel"] == "#ffffff"
    assert props["--dp-field"] == "#ffffff"
    assert props["--fx-alpha"] == "0"


def test_forced_colors_fallback_uses_system_colours_for_every_token() -> None:
    forced = _properties(_block(_forced_css(), "  " + ROOTS))
    assert set(forced) == set(RAW["light"])
    allowed = {"Canvas", "CanvasText", "Highlight", "HighlightText", "transparent", "none", "0"}
    assert set(forced.values()) <= allowed
    assert "forced-colors: active" in THEME_SWITCH_CSS


def test_no_colour_literals_outside_theme_blocks_and_print() -> None:
    css = _style(html_report(make_report()))
    css = re.sub(r"@font-face \{.*?\n\}", "", css, flags=re.DOTALL)
    css = css.replace(THEME_TOKENS_CSS, "").replace(EFFECTS_CSS, "")
    css = css[: css.index("@media print {")]
    css = re.sub(r"(?:-webkit-)?mask-image:[^;]*;", "", css)
    offenders = re.findall(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(", css)
    assert not offenders, f"hard-coded colours must be theme tokens: {offenders[:10]}"
    for script in (APP_JS, THEME_SWITCH_CSS):
        assert not re.findall(r"rgba?\(|hsla?\(|#[0-9a-fA-F]{6}\b", script)


def test_theme_colour_meta_values_follow_the_theme_backgrounds() -> None:
    match = re.search(
        r"var CHROME = \{light: \"(#[0-9a-f]{6})\", dark: \"(#[0-9a-f]{6})\"\};", THEME_JS
    )
    assert match is not None
    assert match.group(1) == RAW["light"]["--dp-ground"]
    assert match.group(2) == RAW["dark"]["--dp-ground"]
    assert '<meta name="theme-color" content="' + match.group(2) + '">' in html_report(
        make_report()
    )


def test_halftone_dots_cannot_reduce_text_contrast_below_the_minimum() -> None:
    # Worst case: the dot colour at the host opacity fully covers the pixel behind the text.
    for name, tokens in PALETTES.items():
        alpha = float(tokens["fx-alpha"])
        worst = _mix(tokens["fx-ink"], tokens["bg"], alpha)
        for text in ("ink", "ink-2", "muted"):
            ratio = contrast(tokens[text], worst)
            assert ratio >= 4.5, f"{name}: {text} on halftone worst case {worst} = {ratio:.2f}"
    css = _style(html_report(make_report()))
    hero = css[css.index(".hero-field {") :].split("}", 1)[0]
    assert "opacity: var(--fx-alpha)" in hero
    assert "transparent 54%" in hero, "the title side of the hero field must stay quiet"


def test_hero_heading_gradient_stays_readable_in_both_themes() -> None:
    for theme in ("light", "dark"):
        props = RAW[theme]
        ground = props["--dp-ground"]
        assert contrast(props["--hero-from"], ground) >= 4.5, theme
        assert contrast(props["--hero-to"], ground) >= 4.5, theme
    assert (RAW["light"]["--hero-from"], RAW["light"]["--hero-to"]) == ("#16191f", "#666666")
    assert (RAW["dark"]["--hero-from"], RAW["dark"]["--hero-to"]) == ("#ffffff", "#9b9b9b")
    css = _style(html_report(make_report()))
    assert "linear-gradient(90deg, var(--hero-from), var(--hero-to))" in css
    assert "background-clip: text" in css


def test_early_head_script_is_hashed_in_the_csp_and_runs_before_the_body() -> None:
    document = html_report(make_report())
    collector = _Scripts()
    collector.feed(document)
    policy_match = re.search(
        r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">', document
    )
    assert policy_match is not None
    policy = html_module.unescape(policy_match.group(1))

    assert collector.head_scripts == [THEME_JS]
    for body in (THEME_JS, EFFECTS_JS, APP_JS):
        digest = base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode("ascii")
        assert f"'sha256-{digest}'" in policy
    assert document.index(THEME_JS) < document.index("<style>") < document.index("<body>")
    assert document.index('http-equiv="Content-Security-Policy"') < document.index(THEME_JS)
    script_src = next(part for part in policy.split(";") if part.strip().startswith("script-src"))
    assert len(re.findall(r"'sha256-", script_src)) == 5
    assert "'unsafe-inline'" not in script_src
    assert '<html lang="en" class="booting">' in document
    assert "data-theme=" not in document.split("<body>", 1)[0].split("<style>", 1)[0].replace(
        THEME_JS, ""
    )


def test_theme_script_resolves_stored_choice_then_system_then_dark_without_hard_dependency() -> (
    None
):
    assert 'var KEY = "nhb-theme";' in THEME_JS
    assert '"(prefers-color-scheme: light)"' in THEME_JS
    assert 'return lightQuery && lightQuery.matches ? "light" : "dark";' in THEME_JS
    assert 'root.setAttribute("data-theme", theme);' in THEME_JS
    assert 'root.setAttribute("data-theme-choice", choice);' in THEME_JS
    assert 'lightQuery.addEventListener("change", onSystemChange)' in THEME_JS
    assert "lightQuery.addListener(onSystemChange)" in THEME_JS
    assert 'if (choice === "system") { apply(); }' in THEME_JS
    assert 'CHOICES.indexOf(stored) >= 0 ? stored : "system"' in THEME_JS


def test_safe_storage_guards_the_getter_and_both_accessors_with_a_memory_fallback() -> None:
    assert "try { return window.sessionStorage; } catch (error) { return null; }" in THEME_JS
    assert "var memory = new Map();" in THEME_JS
    get_part = THEME_JS[THEME_JS.index("get: function") : THEME_JS.index("set: function")]
    set_part = THEME_JS[THEME_JS.index("set: function") : THEME_JS.index("function query(")]
    for part, call in ((get_part, "store.getItem(key)"), (set_part, "store.setItem(key, value)")):
        assert "try {" in part
        assert call in part
        assert "catch" in part
    assert "memory.set(key, value);" in set_part
    assert "localStorage" not in THEME_JS
    assert THEME_JS.count("sessionStorage") == 1
    assert "sessionStorage" not in APP_JS


def test_switcher_is_a_labelled_radiogroup_built_without_markup_strings() -> None:
    for fragment in (
        'group.setAttribute("role", "radiogroup");',
        'group.setAttribute("aria-label", "Colour theme");',
        'button.setAttribute("role", "radio");',
        'var LABELS = {system: "System", light: "Light", dark: "Dark"};',
        "label.textContent = LABELS[value];",
        'icon.setAttribute("aria-hidden", "true");',
        'button.setAttribute("aria-checked", selected ? "true" : "false");',
        'button.setAttribute("tabindex", selected ? "0" : "-1");',
        '"ArrowRight"',
        '"ArrowLeft"',
        '"Home"',
        '"End"',
        "options[target].focus();",
    ):
        assert fragment in THEME_JS, fragment
    for forbidden in (
        "innerHTML",
        "insertAdjacentHTML",
        "outerHTML",
        "document.write",
        "eval(",
        "new Function",
    ):
        assert forbidden not in THEME_JS
    document = html_report(make_report())
    assert '<div class="theme-host" id="theme-switch-host"></div>' in document
    assert '<div class="motion-host" id="motion-switch-host"></div>' in document
    assert 'window.NHBTheme.mount(document.getElementById("theme-switch-host"))' in APP_JS
    assert ".theme-option:focus-visible { outline: 2px solid var(--focus);" in document


def test_motion_switch_is_a_labelled_switch_with_a_stored_default_from_reduced_motion() -> None:
    for fragment in (
        'var MOTION_KEY = "nhb-motion";',
        'button.setAttribute("role", "switch");',
        'button.setAttribute("aria-checked", motionOn ? "true" : "false");',
        'state.textContent = motionOn ? "On" : "Off";',
        'label.textContent = "Motion";',
        "!(motionQuery && motionQuery.matches)",
        'root.setAttribute("data-motion", motionOn ? "on" : "off");',
        "fx.setMotion(motionOn)",
        "safeStorage.set(MOTION_KEY",
    ):
        assert fragment in THEME_JS, fragment
    assert 'window.NHBTheme.mountMotion(document.getElementById("motion-switch-host"))' in APP_JS


def test_theme_change_uses_the_base_curve_for_at_most_240ms_and_never_when_motion_is_off() -> None:
    assert "transition: background-color 200ms cubic-bezier(.22, 1, .36, 1)" in THEME_SWITCH_CSS
    assert not re.search(r"transition:[^;]*\b(?:2[5-9]\d|[3-9]\d\d|\d{4,})ms", THEME_SWITCH_CSS)
    assert not re.search(r"transition:[^;]*\b(?:ease|linear)\b[,;]", THEME_SWITCH_CSS)
    reduced = THEME_SWITCH_CSS[THEME_SWITCH_CSS.index("@media (prefers-reduced-motion: reduce)") :]
    assert "transition: none !important;" in reduced
    assert 'query("(prefers-reduced-motion: reduce)")' in THEME_JS
    assert "&& motionOn && !viaEffects" in THEME_JS
    assert "fx.transitionTheme(apply," in THEME_JS


def test_page_content_does_not_depend_on_the_animation_runtime_or_storage() -> None:
    assert 'window.Motion && typeof window.Motion.animate === "function"' in APP_JS
    assert "catch (error)" in THEME_JS
    css = _style(html_report(make_report()))
    assert 'html[data-motion="off"] *' in css
    # A 1 ms duration is not "off": WebKit still starts a transition
    # and the page reads as hidden for a frame.
    assert "transition: none !important" in css


def test_details_marker_plus_rotates_instead_of_swapping_glyphs() -> None:
    css = _style(html_report(make_report()))
    assert 'content: "+"' in css
    assert "details[open] > summary::before { transform: rotate(45deg); }" in css
    assert "\x91" not in css


def test_generated_html_has_no_brand_assets_and_no_urls_outside_embedded_data() -> None:
    document = _fx07_document()
    assert "tracebit" not in document.lower()
    shell = re.sub(
        r'<script type="application/json" id="report-data">.*?</script>',
        "",
        document,
        flags=re.DOTALL,
    )
    motion = (ASSETS / "vendor" / "motion-14.7.1.min.js").read_text(encoding="utf-8")
    assert motion in shell
    shell = shell.replace(motion, "")
    assert not re.findall(r"https?://", shell)
    assert "url(" not in shell.replace('url("data:font/woff2;base64,', "").replace("url(#", "")
    for source in (THEME_JS, THEME_SWITCH_CSS, THEME_TOKENS_CSS, EFFECTS_JS, EFFECTS_CSS):
        assert "http" not in source
        assert "tracebit" not in source.lower()


def test_fx07_report_stays_within_the_size_budget() -> None:
    size = len(_fx07_document().encode("utf-8"))
    assert size <= SIZE_BUDGET_BYTES, f"{size} bytes exceeds {SIZE_BUDGET_BYTES}"


def test_template_placeholders_in_report_text_are_not_substituted() -> None:
    report = make_report()
    nodes = list(report.graph.nodes)
    marker = "__SCRIPTS__ __GRAPH_SVG__ __THEME_SCRIPT__ __CSP__ __FONT_CSS__ __ICON_SPRITE__"
    nodes[0] = nodes[0].model_copy(update={"label": marker})
    graph = report.graph.model_copy(update={"nodes": tuple(nodes)})
    document = html_report(report.model_copy(update={"graph": graph}))
    collector = _Scripts()
    collector.feed(document)

    assert document.count(marker) >= 1
    assert len(collector.scripts) == 5
    assert document.count('class="graph-svg"') == 1
    assert document.count('class="icon-sprite"') == 1


def test_the_three_embedded_fonts_are_the_owner_families_and_no_old_face_remains() -> None:
    manifest = json.loads((ASSETS / "MANIFEST.json").read_text(encoding="utf-8"))
    families = {entry["family"] for entry in manifest["fonts"]}
    assert families == {"Host Grotesk", "Instrument Sans", "Geist Mono"}
    document = html_report(make_report())
    style = _style(document)
    faces = re.findall(r'font-family: "([^"]+)";\n  font-style', style)
    assert sorted(faces) == ["Geist Mono", "Host Grotesk", "Instrument Sans"]
    for entry in manifest["fonts"]:
        payload = (ASSETS / "fonts" / entry["name"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"]
        assert entry["license"] == "OFL-1.1"
    assert not (ASSETS / "fonts" / "geist-latin.woff2").exists()
    assert not (ASSETS / "fonts" / "instrument-serif-latin.woff2").exists()
    assert "Instrument Serif" not in style
    assert '"Geist",' not in style


def test_phosphor_icons_are_a_hash_checked_inline_sprite() -> None:
    manifest = json.loads((ASSETS / "MANIFEST.json").read_text(encoding="utf-8"))
    names = {entry["name"] for entry in manifest["icons"]}
    assert names == {
        "arrow-right.svg",
        "arrow-up.svg",
        "check.svg",
        "copy.svg",
        "info.svg",
        "printer.svg",
    }
    for entry in manifest["icons"]:
        payload = (ASSETS / "icons" / entry["name"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"]
        assert entry["license"] == "MIT"
        assert entry["source_url"].startswith(
            "https://raw.githubusercontent.com/phosphor-icons/core/main/assets/regular/"
        )
    assert "MIT License" in (ASSETS / "icons" / "MIT-Phosphor.txt").read_text(encoding="utf-8")
    document = html_report(make_report())
    assert len(re.findall(r"<symbol id=\"i-", document)) == 6
    assert "xmlns" not in document.split('class="icon-sprite"', 1)[1].split("</svg>", 1)[0]


def test_dom_contract_for_the_effects_layer() -> None:
    document = _fx07_document()
    hosts = re.findall(r'data-fx-halftone="(hero|field)"', document)
    assert sorted(hosts) == ["field", "field", "hero"]
    assert len(hosts) <= 3
    assert document.count('<svg class="journey-svg" data-fx-journey aria-hidden="true"') == 1
    assert document.count("data-fx-stop") >= 10
    for attribute in (
        "data-fx-spotlight",
        "data-fx-disclosure",
    ):
        assert attribute in document
    for attribute in (
        "data-fx-draw",
        "data-fx-reveal",
        "data-fx-magnetic",
        "data-fx-tilt",
    ):
        assert attribute in APP_JS
    assert "data-fx-count" in EFFECTS_JS
    assert "startEffects();" in APP_JS
    assert "refreshEffects()" in APP_JS
    assert "NHBEffects" in APP_JS


def test_type_and_copy_rules_of_the_landing_page_skill() -> None:
    css = _style(html_report(make_report()))
    assert not re.search(r"font-style:\s*italic|<i>|<em>", css + APP_JS)
    assert not re.search(r"font-weight:\s*[89]00|font:\s*[89]00\b", css)
    for name in ("heading-1", "heading-6", "title-1", "body-1", "body-6", "button-md", "caption-5"):
        assert f".{name} {{" in css
    sizes = {
        int(size)
        for size in re.findall(
            r"\.(?:heading|title|body|button|caption)-\w+ \{ font: \d+ (\d+)px", css
        )
    }
    assert sizes <= {12, 14, 16, 18, 20, 24, 30, 36, 48, 60, 72, 96, 128}
    assert "text-wrap: balance" in css
    assert "text-wrap: pretty" in css
    banned = (
        "revolutionize",
        "supercharge",
        "cutting edge",
        "effortless",
        "transform your workflow",
        "next level",
        "harness the power",
        "world class",
    )
    page = html_report(make_report()).lower()
    for word in banned:
        assert word not in page
