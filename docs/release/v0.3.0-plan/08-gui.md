# 8. GUI and usability improvement plan

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
