# Browser tests for the themed HTML report

These tests open the generated single-file report through `file://` in real browsers and check the
light/dark theme, the System / Light / Dark switcher and safe storage. They are dev-time tooling:
the report itself makes no network requests, and the tests abort every non-`file:` request.

## Run

One-time setup (downloads packages and browsers; needs network access once):

```
cd tests/ui
npm install
npx playwright install chromium firefox webkit
```

Run everything (the global setup generates the fx07 and fx14 reports with the real CLI into a
temporary directory):

```
cd tests/ui
npx playwright test                    # chromium, firefox, webkit; one worker by default
npx playwright test --project=chromium # one engine
```

From the Python suite: `python -m pytest tests/ui -q -p no:cacheprovider`. That wrapper runs the
engines that are installed and is skipped, with a reason, if Node or Playwright chromium is missing
(`NHB_SKIP_UI_TESTS=1` skips it explicitly). Set `NHB_PYTHON` to choose the interpreter used to
generate the reports; by default it is `.venv` at the repository root.

## What is covered

- default theme follows the emulated `prefers-color-scheme` (light, dark) and updates live while the
  choice is System;
- each switcher option sets `data-theme` / `data-theme-choice` and survives a reload;
- storage failure: `sessionStorage` getter throwing `SecurityError`, `setItem` throwing
  `QuotaExceededError`, `getItem` throwing; no uncaught error and no console error;
- offline: every non-`file:` request is aborted; zero such requests are made and the report renders;
- content is visible when `window.Motion` is missing;
- reduced motion: no transition class and a 0 s transition; otherwise at most 140 ms;
- keyboard only: Tab into the group, arrows / Home / End move and select, Space and Enter select,
  the focus ring is drawn;
- axe-core 4.x reports no automated violations in both themes (wcag2a/aa, 2.1, 2.2 AA and
  best-practice tags). This is an automated check, not a statement of WCAG conformance;
- the hostile fixture (fx14) renders inert in both themes.

`completeness.spec.js` covers the analysis completeness panel: counts match the embedded data, text status
badges, group order, keyboard-toggled collapsed groups, links to assumption/diagnostic rows, the
zero-findings scope notice (fx01), no percentage or completeness wording, axe-core in both themes with
groups collapsed and expanded, and the hostile fixture.

`node screenshots.js` re-creates the review screenshots in `docs/usability/screens/`.
