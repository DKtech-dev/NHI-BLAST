# 8. GUI and usability improvement plan

> **Revised 2026-11-02.** Where this part conflicts with [12-revision-2.md](12-revision-2.md) (final design review: corrections, deviations, verified sources) or [11-ui-direction.md](11-ui-direction.md), those documents win. See the implementation log for what was built.

### Modality decision

- **Keep the CLI** as the automation interface.
- **Keep the single-file offline HTML report** as the GUI. It already has a strict CSP, a JSON island, search and filters, graph zoom, the exposure matrix and tracing (`report/ui.py`, `html.py`).
- **No desktop app, Electron/Tauri or local server.** There is no user problem the portable file cannot meet, and each adds attack surface and maintenance.

### Main report (`report/ui.py`)

1. **Analysis completeness panel**, placed right after the summary.
   - Groups: analysed / partially analysed / not provided / not supported / not applicable.
   - Each item shows its family, sources, linked diagnostics and assumptions, and an explanation of what cannot be concluded.
   - The summary shows counts by status. There is no percentage and no "complete" badge.
2. **Graph list/table fallback**: a sortable node/edge table with the same filters.
   - It is the default when the node count is over the render cap or `prefers-reduced-motion` is set.
   - It is always reachable by keyboard. This also provides the accessible graph alternative.
3. **Light theme** via `prefers-color-scheme`, reusing the print tokens, plus a manual toggle that persists in `sessionStorage` only. Contrast is checked (WCAG AA) for both themes.
4. **Evidence class legend and R/E/Z explainer**, expandable, with `issued_before_containment` terminology reserved for what-if.
5. **Findings:** add filters for evidence class and "depends on missing context". Show completeness refs per finding.
6. **Empty and partial states:**
   - "No findings" plus any `not_provided`/`partially_analysed` item renders a "No findings in analysed scope — see Analysis completeness" notice. It never shows a bare success.
7. **Motion:** keep Motion (already vendored). Every animation is gated by `prefers-reduced-motion`, and content never waits on an animation.

### New companion HTML

Built via a refactored `render_document()`: same CSP hashing, escaping and fonts, no Motion.
- **Diff view** (`report/diff_html.py`):
  - Top banner: comparability state with reasons. An incomparable report is shown prominently, never as a success.
  - Tabs: Security changes / Context drift / Not observed / Unchanged.
  - Per-scenario R/E/Z deltas.
- **What-if view** (`report/whatif_html.py`):
  - Ordered interventions.
  - Before/after R/E/Z columns.
  - `issued_before_containment`, `revoked` and `re_exposure_risk` badges with tooltips.
  - Residual paths, rejected interventions, completeness refs.
  - A printable playbook section.

### Verification (`tests/ui/`, `.github/workflows/ui.yml`)

- Playwright with pinned browsers, plus axe-core vendored for tests only (dev dependency).
  - ubuntu: Chromium and Firefox, blocking.
  - ubuntu: WebKit, non-blocking.
  - windows: Chromium.
  - macos: WebKit, if the runner passes.
- Viewports 375, 768 and 1440 px, plus 200% zoom.
- Keyboard-only flows; focus order and visibility.
- Forced-colors and reduced-motion emulation.
- Fixtures: hostile strings (fx14), large graph (fx15), long paths, Unicode, empty and partial states.
- A check that every control works (no dead buttons): click, filter, sort, search, tab, toggle, print and copy each have an assertion.
- Axe results are reported as "no automated violations". That is not claimed as WCAG conformance.

### Scripted task walkthroughs (Playwright scripts, recorded steps and outcomes)

Tasks:
1. Install, then scan fx07 and open the report.
2. Find which credentials survive and why.
3. Find what was not analysed.
4. Run the diff between two fx07 variants and identify a false "resolved" guard.
5. Run a what-if containment and read the playbook.
6. Export the SARIF and JSON.

Each script records its steps, success, and any defects fixed. These are described as scripted task walkthroughs.

**Real-user sessions:** `docs/usability/test-script.md` and `feedback-form.md` are prepared for 3–5 target users. Status stays "not yet conducted" until people take part. No results are written in advance.

## Implemented: themed report (steps G0 and G4)

- The report has a light and a dark theme (`data-theme` on `<html>`, user choice in `data-theme-choice`) and a System / Light / Dark switcher in the viewer bar. Tokens follow `11-ui-direction.md`; a `forced-colors: active` fallback and the print palette are defined. Shared CSS/JS live in `THEME_TOKENS_CSS`, `THEME_SWITCH_CSS` and `THEME_JS` in `src/nhi_blast/report/ui.py` for reuse on companion pages.
- An inline script in `<head>` applies the theme before first paint and is covered by the CSP script hashes. Storage goes through `safeStorage()` (`sessionStorage`, key `nhb-theme`, in-memory fallback).
- Checks: `tests/test_theme.py` (token parity, WCAG contrast recomputed from the generated CSS, CSP hash, no brand string, size budget) and `tests/ui/` (Playwright on chromium, firefox and webkit over `file://`, including storage failure, offline, reduced motion, keyboard and axe-core). axe-core reports no automated violations in both themes; that is not a statement of WCAG conformance. See `tests/ui/README.md`.
- Deviations: dark `--border-strong` moved from `#49403c` to `#70665f` to reach 3:1 for control borders; graph node accessible names now begin with the drawn text (WCAG 2.5.3); the details-marker minus sign was a stray control character and is now a CSS escape. Review screenshots are in `docs/usability/screens/`.

## Implemented: analysis completeness panel (step A3, HTML)

- `Report.completeness` renders as an "Analysis completeness" section right after Summary (nav link hidden when the report has no completeness block). Counts by status come first, then groups in the order partially analysed, not provided, not supported, analysed, not applicable; the last two are collapsed `<details>`. Each item shows the family label, a text status badge, sources (path and first 12 hex of sha256), diagnostic codes and assumption ids (linked to `#diagnostic-<code>` / `#assumption-<id>` rows when present) and the explanation. No percentage and no "complete" wording; a note states that not provided / not supported means the report says nothing about it.
- With zero findings and any partially analysed, not provided or not supported item, the findings section reads "No findings in the analysed scope - see Analysis completeness" instead of a bare empty state.
- Family labels are embedded from `core.completeness.FAMILY_LABELS`; everything from the report is written with `textContent` / `setAttribute`. Checks: `tests/test_html_completeness.py` and `tests/ui/completeness.spec.js`. Screenshots: `docs/usability/screens/completeness-*.png`, `findings-empty-*.png`.

## Implemented: owner design system and recomposition (steps G5 and G6)

- The report uses the owner design system (`--dp-*` tokens, Host Grotesk and Instrument Sans, blue accent, two dark passages) and the composition described in `11-ui-direction.md` sections 7 and 8: hero with a data built diagram, scan facts, ruled facts strip, how to read, tagline reveal, survival panel with a timeline, rotation as numbered process steps, graph, findings, disclosures, scope and a closing footer.
- The effects layer (halftone field, scroll journey, reveals, count ups, pointer effects) lives in `report/effects.py` and is initialised from `startEffects()`; the page reads in full with Motion off or without the layer.
- Checks: `tests/test_theme.py`, `tests/test_html*.py` and the Playwright specs `theme`, `completeness`, `g6` and `effects` in `tests/ui/`. The fx07 report budget rose from 600 KB to 650 KB for the effects layer and the new sections.
