# 11. UI direction: themed report (light and dark) with a theme switcher

Status: Phase P output (plan revision 2, C13). Written 2026-11-02.

## 1. Inputs and process (what was actually done)

- `npx -y inspo-mcp@0.2.0 install --dry-run` then `install` were run. The npm integrity matched the registry value (`sha512-JkLQhzfG…aQdXFQ==`). The installer configured Claude Code (user scope) and Windsurf only. It added no dependency to this repository. DSH is not one of the clients it configures, so the research used the hosted read-only endpoint (`https://inspomcp.dev/api/mcp`, JSON-RPC over HTTP): `initialize`, `tools/list`, `recommend`.
- `recommend` brief: "offline security incident-response report: dense data tables, graphs, evidence and severity states, light and dark themes with a theme switcher, accessible, calm and serious, developer tools / security". Result: 24 sites measured; display class grotesk-sans 79%; paper band split dark 54% / mid 46%; accent hue warm/cool/other roughly evenly split. Inspo reports its own macrostructure pick (marquee-hero) as a landing-page pattern. It is not applied to the report, which is an information-first tool page.
- Owner reference: `C:/Users/DK/Downloads/DESIGN-tracebit-com.md` (an Inspo extraction of tracebit.com, captured 2026-09-10). It is used as a mood and ratio reference only: warm off-white paper, near-black ink, tight negative tracking on headings, light body weight, hairline borders, 4 px spacing base, radii 0/8/12 px, 1440 px container.

## 2. Adapt, do not copy (binding)

- No Tracebit logo, illustration, copy, layout clone or typeface. TWK Lausanne Pan is commercial and is not used. Typography stays on the embedded OFL families (Geist, Geist Mono, Instrument Serif).
- The accent stays in NHI-Blast's existing red family, which is a different hue from Tracebit's orange (`#ea6f53`).
- The report keeps its information-first layout. No marketing hero is added to the report.
- Nothing is fetched at runtime. No third-party URL, font or image is referenced by generated HTML.

## 3. Theme model

- Three user choices: **System**, **Light**, **Dark**. The effective theme is stored as `data-theme="light|dark"` on `<html>`. The user's choice is stored as `data-theme-choice="system|light|dark"`.
- Resolution order: stored choice, then `prefers-color-scheme`, then dark (current behaviour). When the choice is System, a `matchMedia` change listener updates the effective theme live.
- First paint: a tiny inline script in `<head>` sets the attributes before the body renders, so there is no flash. It is covered by the CSP script hashes like every other inline script.
- Storage goes through `safeStorage()` (plan C8). It wraps access to `window.sessionStorage` (the getter itself can throw SecurityError on `file:`, MDN S16), `getItem` and `setItem` in try/catch, with an in-memory fallback for the life of the page. The key is `nhb-theme`. The page works fully with storage unavailable, and the choice then lasts for that page view only.
- Print always uses the light palette (the existing `@media print` block is kept and aligned to the light tokens).
- `forced-colors: active` falls back to system colours. `color-scheme` is set per theme so native controls match.

## 4. The switcher control

- A segmented control with three options, rendered as a `role="radiogroup"` labelled "Colour theme", in the existing viewer bar. It is built with `textContent` and `setAttribute` only.
- Native keyboard behaviour: Tab to the group, arrow keys move and select, Space/Enter select. Focus ring uses `--focus`. Each option has a visible text label ("System", "Light", "Dark"); icons are decorative (`aria-hidden`).
- The control is also present on the diff and what-if companion pages (step G1).
- Reduced motion: no animated transition on theme change when `prefers-reduced-motion: reduce`. Otherwise a ≤140 ms colour transition at most.

## 5. Tokens

Dark (existing, kept; the accent and ink pairs already pass): `--bg #050505`, `--surface #111010`, `--raised #201b19`, `--ink #f5f0dc`, `--ink-2 #c7c0b5`, `--muted #a7a096`, `--accent #ff382f`.

Light (new; derived from the existing print palette, warmed toward the reference paper tone):

| Token | Value | Token | Value |
|---|---|---|---|
| `--bg` | `#f6f3ee` | `--ink` | `#1b1816` |
| `--header` | `#fbf9f6` | `--ink-2` | `#3b352e` |
| `--surface` | `#fffdfa` | `--muted` | `#5c544a` |
| `--surface-2` | `#f0ebe3` | `--accent` | `#a8201a` |
| `--raised` | `#e9e3d9` | `--accent-hover` | `#8f1a15` |
| `--hover` | `#e4ddd1` | `--accent-ink` | `#ffffff` |
| `--border` | `#d3cabb` | `--accent-soft` | `#f7e4e1` |
| `--border-strong` | `#8f8576` | `--focus` | `#a8201a` |

Severity (light): critical `#a8201a` / ink `#7c1712` / soft `#f7e4e1`; high `#8a4a12` / `#6f3a0c` / `#f6e8da`; warning `#6e5200` / `#5a4300` / `#f5efd8`; low `#4a443d` / `#3a352f` / `#f1eee7`; positive `#1f6b43`. Graph and node colours use the print values for light.

Measured contrast (WCAG 2.x relative luminance, computed 2026-11-02):

- Light: `ink` on `bg` 15.96, `ink-2` on `bg` 10.94, `muted` on `raised` 5.83, `accent` on `raised` 5.70, critical-ink on `accent-soft` 8.62, high-ink on its soft fill 7.64, warning-ink on its soft fill 8.14, positive on `raised` 5.07. `border-strong` on `bg` is 3.28 (UI component bound, 3:1).
- Dark: `muted` on `raised` 6.58, `accent` on `raised` 4.75, critical-ink on `surface` 8.63.
- A token test (G3') recomputes every text and background pair actually used and fails below 4.5:1 for text (3:1 for large text and UI components), in both themes.
- Severity never relies on colour alone: every badge keeps its text label.

Shape and rhythm: 4 px spacing base, radii kept at the current tokens (6/9/10/12/14/16), container max width unchanged. Heading tracking tightens slightly (the reference's ratio, not its pixels). Body stays Geist 14–15 px.

## 6. Acceptance for G4

- Switcher present, keyboard-operable, labelled, works with storage blocked (`file://`, getter throws SecurityError, `setItem` throws QuotaExceeded).
- No flash of the wrong theme on load (the early script is hashed in the CSP).
- Both themes pass the token contrast test and the axe check (reported as "no automated violations", not as WCAG conformance).
- Hostile-string rendering, CSP, size budget (≤600 KB on fx07) and offline behaviour are unchanged.
- No third-party brand asset or URL in generated HTML (grep test for `tracebit`).
- Screenshots at 375, 768 and 1440 px for each theme are saved under `docs/usability/screens/` for review.


## G6 effects

Source: `src/nhi_blast/report/effects.py` exports `EFFECTS_CSS` (about 6.4 KB) and `EFFECTS_JS` (about 27.8 KB, one IIFE, the only global is `window.NHBEffects`). Nothing runs before `NHBEffects.init()`. No network, no `eval`, no `innerHTML`, no inline style attributes (CSSOM and WAAPI only), so the strings are safe under a hash-only CSP. Tests: `tests/test_effects.py` (string contract) and `tests/ui/effects.spec.js` (Chromium, Firefox and WebKit on a hash-CSP harness built by `tests/ui/effects-fixture.js`).

### API

`init(root, {motion: true|false|null})` is idempotent; pass `document.documentElement`. It adds `html.js-fx` only after setup succeeded. `refresh()` rescans, prunes removed hosts and re-measures. `setMotion(bool)` sets `html[data-motion]` (also before init). `motionEnabled()`. `transitionTheme(applyFn, originEl)` runs a radial View Transition reveal (500 ms, base curve) when supported and motion is on, otherwise just `applyFn()`; `applyFn` always runs exactly once. `destroy()` removes everything added.

### Motion state

`html[data-motion="on|off"]`. Default off under `prefers-reduced-motion: reduce` when `motion` is `null`. Every CSS animation or transition rule is keyed to `html[data-motion="on"]` (a unit test parses the CSS). With motion off every effect has its static end state: one halftone frame at a fixed time and no rAF afterwards, journey fully drawn with all nodes active, draw lines drawn, counts and reveals untouched, words at full colour, no progress bar.

### Motion rules applied (landing-page-design B7, motion skill)

- One curve: `--fx-ease: cubic-bezier(.22,1,.36,1)` in CSS and `BASE` in JS. No default keyword curves (tested).
- Durations: position and layout 500 ms, opacity and colour 300 to 500 ms, nothing shorter than 200 ms (tested). Reveals rise 32 px and fade over 700 ms once (`IntersectionObserver`, unobserved after the first time). The hidden state has no transition; only the revealed state carries it, so nothing flashes out at start.
- Only `transform` family (`translate`, `rotate`, `scale`, `transform`), `opacity` and discrete `visibility`, plus colour on journey nodes. Magnetic buttons, reveals, the nav indicator (`translateX` plus `scaleX`) and the progress bar (`scaleX`) animate transforms only. Active state of magnetic buttons is `scale(.98)`.
- Scroll linked work (journey, progress bar, nav scrollspy, pill nav sync) runs from one passive scroll and resize listener that coalesces into a single `requestAnimationFrame`. No unthrottled scroll work. CSS `animation-timeline` is not used; the rAF path is the only path.
- Documented exceptions, none avoidable without changing the requirement: the journey line and `[data-fx-draw]` animate `stroke-dashoffset` (the owner asked for a line that draws itself; it is not a layout property); the animated `details` uses WAAPI on `height` because the following content must move with it and a native `details` has no wrapper to apply a grid rows trick to (500 ms, base curve, native open/close semantics and keyboard unchanged, skipped when motion is off); the theme reveal animates `clip-path` on the View Transition pseudo element.

### Halftone (`[data-fx-halftone="hero|field"]`)

WebGL1 fragment shader. Shared preamble: `hash11`, `hash21`, value noise, a six octave `fbm`, `warp` and `warp2 = warp(warp(p))`. Body: `cell = floor(uv * CELLS)` with `CELLS = 34` along the shorter side of the host, `centre = (cell + .5) / CELLS`, one `fbm` per cell centre sets the radius, radius is multiplied by `1 + uIntensity * pointerFalloff(centre)`, dot edge is anti aliased, a third value only draws a thin rim. Colours come from computed style of the fallback panel inside the host: dot is `--fx-dot` else `--fx-ink`, ground is `--fx-ground`, rim is `--fx-accent`. Defaults (zero specificity): dark `#08090d`, `#dbe0eb`, `#080a0d`; light `#fcfcfd`, ink `#16191f` at 20% alpha, `#074ce0`. The palette is re-read on `html[data-theme]` changes and on `refresh()`.

Pointer: `uIntensity` eases towards 1 inside the host and 0 outside or when the pointer leaves the window (critically damped smoothing, 220 ms); `uPointer` is host relative and smoothed. Performance: canvas at `min(devicePixelRatio, 1.5)` and at most 1.6 megapixels, about 30 fps, paused offscreen (`IntersectionObserver`) and in hidden tabs, adaptive resolution after sustained slow frames, context loss and restore handled, `preserveDrawingBuffer: true`, at most three live hosts per page (extra hosts get the fallback). The fallback panel is a CSS dot pattern in page tokens, shown only when `data-fx-state="fallback"` (no context, lost context, compile or link failure, or extra host). Host, canvas and fallback are `aria-hidden` and `pointer-events: none`; the canvas and fallback are `display: none` in print.

### Other effects

- `svg[data-fx-journey]` inside a positioned container: stops are `[data-fx-stop]` elements of the container; geometry is computed relative to the svg's own box. Wide viewports (1050 px and up) get a spine in the left gutter with smooth cubic elbows to a node per stop; narrower viewports get a 5 px spine with nodes on it. Base and ink paths share one `d`; ink uses `stroke-dasharray = length` and `stroke-dashoffset = length * (1 - progress)` with `progress = clamp((vh * .55 - containerTop) / containerHeight)`, forced to 1 at the bottom of the page. Nodes get `is-active` once the drawn length passes them. Variables to override: `--fx-blue` (the single effects accent), `--fx-rule`, `--fx-node-bg`.
- `[data-fx-draw]`: dashed and hidden only while motion is on and the element is not already 60% visible; draws once (700 ms). Handles `vector-effect: non-scaling-stroke`.
- `[data-fx-count]`: integer text counts up once (900 ms, ease out cubic). The real text is kept in a visually hidden span, the animated clone is `aria-hidden`, the original text nodes are restored exactly. Non integer text is left alone.
- `[data-fx-reveal]` with `[data-fx-delay]`, `[data-fx-spotlight]`, `[data-fx-magnetic]` (4 px, `translate` property, rests on press), `[data-fx-tilt]` (3 deg perspective on HTML, up to 3 px parallax through `translate` on SVG elements; fine pointers only), scroll progress bar (`.fx-progress`, created by init), `[data-fx-nav]` (sliding `.fx-nav-indicator`, `aria-current="true"` via scrollspy), `details[data-fx-disclosure]` (plus rotates 45 degrees when open).
- `[data-fx-words]`: each word becomes a `span.fx-w`; all words stay real text with no aria attributes. With motion on and `js-fx`, words start at 30% opacity and each lights once (`is-lit`) when it crosses a trigger line at 65% of the viewport height, using one `IntersectionObserver` for all words; words already above the line at load are lit immediately. Motion off shows full colour.
- `[data-fx-pillnav]` containing `[data-fx-pillnav-toggle]` (a button) and `[data-fx-pillnav-panel]` (links): the helper adds a hamburger icon (`.fx-burger`, two lines that rotate into a cross on the base curve) when the toggle has none, sets `aria-expanded`, toggles `is-open` on the root, detects overlay mode when the panel is `position: fixed` (class `fx-overlay`), hides the closed overlay with `visibility: hidden`, staggers links in at 60 ms steps (index capped at 6, so the stagger spread never exceeds 360 ms; each link rises 24 px over 400 ms), locks page scroll with `html.fx-menu-open`, traps Tab and Shift+Tab inside the root, closes on Escape (focus returns to the toggle), on link click, and when the viewport leaves overlay mode. The page owns the pill surface, blur and breakpoint. The fixed panel must not sit inside an element that has `backdrop-filter` or `transform`, because that element would become its containing block.

### Test results (this environment)

Recorded in the G6 report to the lead: Playwright 1.64.1 with Chromium, Firefox and WebKit, 40 tests per engine, all three engines created a real WebGL context and ran the shader path, the fallback path was verified by forcing `getContext` to return `null`.

## 7. G5 owner design system

The owner supplied a design system after the G4 release of this document. It replaces the warm palette and the Geist and Instrument Serif pairing in sections 2 and 5; the theme model, the switcher and the storage rules of sections 3 and 4 are unchanged.

### 7.1 Tokens

The owner values are exposed as `--dp-*` custom properties. Every older token name (`--bg`, `--surface`, `--ink`, `--accent` and so on) is mapped from them in one block, so existing selectors keep working. Colours that the design system does not define (severity, R/E/Z, graph) keep their meaning and are tuned per theme.

| Token | Light | Dark | Passage in light | Passage in dark |
|---|---|---|---|---|
| `--dp-ground` | #fcfcfd | #0e1116 | #16191f | #07090d |
| `--dp-ground-muted` | #f3f4f6 | #151922 | #1d222b | #0c0f15 |
| `--dp-panel` | #ffffff | #181c24 | #1e232c | #0f1319 |
| `--dp-rule` | #dde0e6 | #2a303b | #333b49 | #242b36 |
| `--dp-ink` | #16191f | #f3f5f8 | #fcfcfd | #f3f5f8 |
| `--dp-ink-secondary` | #454c58 | #b4bcc9 | #d0d4dd | #b4bcc9 |
| `--dp-accent` | #074ce0 | #6f9bff | #7fa8ff | #6f9bff |
| `--dp-on-accent` | #ffffff | #0b1020 | #0b1020 | #0b1020 |
| `--dp-field` | #16191f | #07090d | #16191f | #07090d |
| `--dp-on-field` | #fcfcfd | #f3f5f8 | #fcfcfd | #f3f5f8 |
| `--dp-on-field-secondary` | #d0d4dd | #b4bcc9 | #d0d4dd | #b4bcc9 |

Layout and motion tokens: `--dp-gap` 24 px, `--dp-radius-panel` 12 px, `--dp-hairline` 1 px, `--dp-motion` 300 ms on cubic-bezier(.22, 1, .36, 1). Sizes: body 16 px, interface 15 px, small 14 px, metadata 13 px, label 12 px.

Derived values that the owner did not specify (documented, not invented): `--dp-rule-strong` for control borders (3:1 against the surfaces), `--dp-ink-muted` for metadata (4.5:1 on every surface), `--dp-raised` and `--dp-hover` as the two steps between the pale field and the rule, and the accent hover and soft tints.

A "passage" is one of the two dark bands. It re-declares the whole palette for everything inside it, so tables, badges and focus rings work on dark without per component rules. In the dark theme the passages are deeper than the page and carry a hairline border.

`tests/test_theme.py` recomputes WCAG contrast from the generated CSS for all four palettes (text at 4.5:1, controls and graphics at 3:1), checks that every palette defines the same tokens, and checks the hero heading gradient and the halftone worst case.

### 7.2 Type

Host Grotesk (display, headings, figures), Instrument Sans (body, labels, controls) and Geist Mono (code, digests, paths only), all embedded under the SIL Open Font License with hashes in `MANIFEST.json`. Geist and Instrument Serif were removed with their licence file and notice.

### 7.3 What was adapted to report content

- The hero diagram is built from the report: input tiles are the real input file kinds (omitted when zero), the right hand tiles are the selected entrypoint's R, E and Z counts.
- "How to read" explains R, E, Z and the four evidence classes with wording from the product contract.
- The ruled facts strip holds the summary figures; the survival panel and the rotation plan share one dark passage; the scope and limits share the other with the footer.
- No logos, quotes, statistics or product screens were invented.

## 8. G6 recomposition and effects

G6 answers the owner review ("looks simple, I need modern and more superb"). The dependency order is: effects module (`report/effects.py`, written by effects-dev), then the integration in `report/ui.py`.

- **Halftone field.** A WebGL halftone behind the hero and inside both dark passages (at most three hosts, CSS masked so the title side stays quiet; falls back to a CSS dot pattern without WebGL). The worst case dot colour is part of the contrast test.
- **Scroll journey.** A line in the left gutter (thin spine at 1050 px and below) joins the section stops 01 to 10 and draws as the page scrolls. Rotation steps carry their own connector that draws once.
- **Editorial rhythm.** Oversized section numerals, a small caps label and a hairline rule for every section, sheets that overlap with rounded edges where a pale band meets a dark one, and a tagline section whose words light up one at a time.
- **Survival timeline.** A data driven picture in the survival panel: R credentials at "job ends", E credentials as bars that end at their real `ttl_seconds`, Z credentials as bars that run off the right edge. The real tables stay as the accessible equivalent.
- **Navigation.** A floating translucent pill with a sliding indicator; on phones a menu toggle opens a full height panel with a focus trap. The pill does not use the effects layer's `data-fx-nav` and `data-fx-pillnav` modes, because the existing scroll spy and `aria-current="location"` are tested.
- **Motion switch.** A header control (`role="switch"`) next to the theme switcher. It defaults from `prefers-reduced-motion`, persists through the same safe storage (key `nhb-motion`) and sets `html[data-motion]`. With Motion off every transition collapses to 1 ms and nothing moves.
- **Skill rules adopted.** Base curve for every transition, durations from 200 ms, only transform and opacity animated for movement (colour on hover is the exception), reveals once, scroll work throttled or observer based, named text styles on the Tailwind scale, no italics, nothing heavier than 700, Phosphor regular icons as an inline sprite (six icons, hashes in the manifest, MIT notice in THIRD_PARTY_NOTICES.md).
- **Not done.** A favicon: the CSP has no `img-src`, and adding `img-src data:` would loosen it, so the report has none. The page keeps its existing section order for completeness (directly after the summary) because tests and the earlier spec require it.
