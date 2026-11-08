"""Static contract tests for the report effects module (plan G6).

The behaviour is covered in real browsers by tests/ui/effects.spec.js; these tests pin the strings
that the page embeds inline (CSP hashed) and the rules the owner set for them.
"""

from __future__ import annotations

import re

import pytest

from nhi_blast.report.effects import EFFECTS_CSS, EFFECTS_JS

ALLOWED_TRANSITION_PROPERTIES = {
    "opacity",
    "transform",
    "translate",
    "rotate",
    "scale",
    "visibility",
    "fill",
    "stroke",
}
DEFAULT_CURVES = {"ease", "ease-in", "ease-out", "ease-in-out", "linear"}


def _rules(css: str) -> list[tuple[str, str]]:
    """Flat (selector, body) pairs; @media is unwrapped, @keyframes bodies are skipped."""
    rules: list[tuple[str, str]] = []

    def walk(text: str) -> None:
        index = 0
        while index < len(text):
            brace = text.find("{", index)
            if brace < 0:
                return
            selector = text[index:brace].strip()
            depth = 1
            end = brace + 1
            while depth and end < len(text):
                depth += {"{": 1, "}": -1}.get(text[end], 0)
                end += 1
            body = text[brace + 1 : end - 1]
            if selector.startswith("@media"):
                walk(body)
            elif not selector.startswith("@keyframes"):
                rules.append((selector, body))
            index = end

    walk(css)
    return rules


def _declarations(body: str) -> list[tuple[str, str]]:
    pairs = []
    for part in body.split(";"):
        name, sep, value = part.partition(":")
        if sep:
            pairs.append((name.strip(), value.strip()))
    return pairs


def _motion_declarations() -> list[tuple[str, str, str]]:
    found = []
    for selector, body in _rules(EFFECTS_CSS):
        for name, value in _declarations(body):
            if re.fullmatch(r"(transition|animation)(-[a-z-]+)?", name):
                found.append((selector, name, value))
    return found


def test_public_contract_is_present() -> None:
    for name in ("init", "refresh", "setMotion", "motionEnabled", "transitionTheme", "destroy"):
        assert re.search(rf"\b{name}\s*:", EFFECTS_JS), name
    assert "W.NHBEffects=" in EFFECTS_JS
    assert EFFECTS_JS.lstrip().startswith("(function(){")
    assert EFFECTS_JS.rstrip().endswith("})();")
    assert "data-motion" in EFFECTS_JS
    assert "startViewTransition" in EFFECTS_JS


def test_only_one_global_is_assigned() -> None:
    assigned = set(re.findall(r"\b(?:window|W)\.([A-Za-z_]\w*)\s*=(?!=)", EFFECTS_JS))
    assert assigned == {"NHBEffects"}


@pytest.mark.parametrize(
    "attribute",
    [
        "data-fx-halftone",
        "data-fx-journey",
        "data-fx-stop",
        "data-fx-draw",
        "data-fx-count",
        "data-fx-reveal",
        "data-fx-delay",
        "data-fx-spotlight",
        "data-fx-magnetic",
        "data-fx-tilt",
        "data-fx-nav",
        "data-fx-words",
        "data-fx-pillnav",
        "data-fx-pillnav-toggle",
        "data-fx-pillnav-panel",
        "data-fx-disclosure",
    ],
)
def test_every_data_attribute_is_handled(attribute: str) -> None:
    assert attribute in EFFECTS_JS


def test_class_names_of_the_contract() -> None:
    for name in ("fx-halftone__canvas", "fx-halftone__fallback", "fx-nav-indicator", "js-fx"):
        assert name in EFFECTS_JS or name in EFFECTS_CSS, name


def test_glsl_lattice_noise_and_warp() -> None:
    assert "hash11" in EFFECTS_JS
    assert "hash21" in EFFECTS_JS
    assert "float vnoise" in EFFECTS_JS
    fbm = re.search(r"float fbm\(vec2 p\)\{.*?\}return s;\}", EFFECTS_JS, re.S)
    assert fbm is not None
    assert re.search(r"for\(int i=0;i<6;i\+\+\)", fbm.group(0))
    assert "vec2 warp(" in EFFECTS_JS
    assert "warp(warp(" in EFFECTS_JS
    assert re.search(r"const float CELLS=34\.0;", EFFECTS_JS)
    assert "floor(uv*CELLS)" in EFFECTS_JS
    assert "(cell+.5)/CELLS" in EFFECTS_JS
    assert EFFECTS_JS.count("fbm(warp2(") == 1
    for uniform in ("uIntensity", "uPointer", "uTime", "uRes", "uGround", "uDot", "uAccent"):
        assert re.search(rf"uniform [^;]*\b{uniform}\b", EFFECTS_JS), uniform
    assert "GL_FRAGMENT_PRECISION_HIGH" in EFFECTS_JS
    assert "precision mediump float" in EFFECTS_JS
    assert "preserveDrawingBuffer:true" in EFFECTS_JS
    assert "webglcontextlost" in EFFECTS_JS
    assert "webglcontextrestored" in EFFECTS_JS


def test_halftone_palette_defaults() -> None:
    assert "--fx-ground:#08090d" in EFFECTS_CSS
    assert "--fx-dot-d:#dbe0eb" in EFFECTS_CSS
    assert "--fx-accent:#080a0d" in EFFECTS_CSS
    assert "--fx-accent:#074ce0" in EFFECTS_CSS
    assert "--fx-ground:#fcfcfd" in EFFECTS_CSS
    assert "rgba(22,25,31,.2)" in EFFECTS_CSS


@pytest.mark.parametrize(
    "forbidden",
    [
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "eval",
        "Function(",
        "http",
        "fetch(",
        "XMLHttpRequest",
        "WebSocket",
        "sendBeacon",
        "importScripts",
        "localStorage",
        "sessionStorage",
        "</script",
        "<!--",
        'setAttribute("style"',
        'setTimeout("',
    ],
)
def test_no_unsafe_or_networking_constructs(forbidden: str) -> None:
    assert forbidden not in EFFECTS_JS
    assert forbidden not in EFFECTS_CSS


def test_strings_are_plain_ascii_and_inline_safe() -> None:
    assert EFFECTS_JS.isascii()
    assert EFFECTS_CSS.isascii()
    assert "\r" not in EFFECTS_JS
    assert "\r" not in EFFECTS_CSS
    assert "url(" not in EFFECTS_CSS
    assert "@import" not in EFFECTS_CSS


def test_size_budgets() -> None:
    assert len(EFFECTS_JS.encode()) <= 28 * 1024
    assert len(EFFECTS_CSS.encode()) <= 8 * 1024


def test_every_animation_rule_is_keyed_to_motion_on() -> None:
    declarations = _motion_declarations()
    assert declarations
    for selector, name, _ in declarations:
        assert 'data-motion="on"' in selector, f"{name} outside data-motion=on: {selector}"
    for selector, body in _rules(EFFECTS_CSS):
        assert "scroll-behavior" not in body, selector


def test_motion_uses_only_the_base_curve_and_owner_durations() -> None:
    assert "--fx-ease:cubic-bezier(.22,1,.36,1)" in EFFECTS_CSS
    assert 'BASE="cubic-bezier(.22,1,.36,1)"' in EFFECTS_JS
    for selector, name, value in _motion_declarations():
        tokens = set(re.findall(r"[a-z-]+", re.sub(r"var\([^)]*\)", "", value)))
        assert not tokens & DEFAULT_CURVES, f"default curve in {selector}: {value}"
        if name == "transition-delay":
            continue
        for part in value.split(","):
            times = re.findall(r"(?<![\w.-])(\d*\.?\d+)(m?s)\b", part)
            if not times:
                continue
            seconds = float(times[0][0]) / (1000 if times[0][1] == "ms" else 1)
            assert seconds == 0 or seconds >= 0.2, f"{name} shorter than 200 ms in {selector}"
    for easing in re.findall(r"easing:([^,}]+)", EFFECTS_JS):
        assert easing == "BASE", easing


def test_css_transitions_only_animate_transform_family_opacity_and_colour() -> None:
    for selector, name, value in _motion_declarations():
        if name not in {"transition", "transition-property"}:
            continue
        for part in value.split(","):
            prop = part.strip().split(" ")[0]
            if prop.startswith("var("):
                continue
            assert prop in ALLOWED_TRANSITION_PROPERTIES, f"{prop} animated in {selector}"
    assert not re.search(r"(?<![-\w])(width|height|top|left|margin)\s+\.?\d", EFFECTS_CSS)


def test_reveal_rises_32px_once_and_needs_js_fx() -> None:
    assert re.search(
        r'html\.js-fx\[data-motion="on"\] \[data-fx-reveal\]\{opacity:0;translate:0 32px\}',
        EFFECTS_CSS,
    )
    assert "unobserve" in EFFECTS_JS
    for selector, body in _rules(EFFECTS_CSS):
        if "data-fx-reveal" in selector and "opacity:0" in body:
            assert "js-fx" in selector


def test_no_italics_and_no_heavy_weights() -> None:
    assert "italic" not in EFFECTS_CSS
    assert "oblique" not in EFFECTS_CSS
    for weight in re.findall(r"font-weight:\s*(\d+)", EFFECTS_CSS):
        assert int(weight) <= 700


def test_focus_rings_are_never_removed() -> None:
    assert not re.search(r"outline\s*:\s*(none|0)", EFFECTS_CSS)
    assert "outline" not in EFFECTS_JS


def test_decorative_layers_are_inert_for_assistive_tech_and_pointers() -> None:
    assert 'setAttribute("aria-hidden","true")' in EFFECTS_JS
    assert "pointer-events:none" in EFFECTS_CSS
    # words keep their real text in the DOM: no aria attribute is set while wrapping them
    words = EFFECTS_JS[EFFECTS_JS.index("function words(") : EFFECTS_JS.index("function unwords(")]
    assert "aria-" not in words


def test_print_hides_the_canvas_and_decor() -> None:
    block = re.search(r"@media print\{(.*)\}\s*$", EFFECTS_CSS.strip(), re.S)
    assert block is not None
    rules = _rules(block.group(1))
    hidden = [selector for selector, body in rules if "display:none!important" in body]
    assert any(".fx-halftone__canvas" in selector for selector in hidden)
    assert any(".fx-halftone__fallback" in selector for selector in hidden)
    assert any("data-fx-journey" in selector for selector in hidden)


def test_halftone_fallback_is_hidden_unless_the_state_says_so() -> None:
    assert re.search(r"\.fx-halftone__fallback\{display:none;", EFFECTS_CSS)
    assert '[data-fx-state="fallback"]>.fx-halftone__fallback{display:block}' in EFFECTS_CSS
    assert '[data-fx-state="fallback"]>.fx-halftone__canvas{display:none}' in EFFECTS_CSS
    assert "MAXH=3" in EFFECTS_JS
    assert "Math.min(W.devicePixelRatio||1,1.5)" in EFFECTS_JS
    assert "IntersectionObserver" in EFFECTS_JS
    assert "visibilitychange" in EFFECTS_JS


def test_nothing_runs_before_init() -> None:
    assert "NHBEffects.init(" not in EFFECTS_JS
    assert "function init(" in EFFECTS_JS
    assert "S=null" in EFFECTS_JS
    assert "if(S){safe(refresh);return}" in EFFECTS_JS
