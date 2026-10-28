# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project intends to
use semantic versioning from its first published release.

## 0.2.0 — unreleased

Source-licensing change plus an offline-report and graph redesign. JSON
(`nhi-blast-report/1.0`), SARIF and the analysis semantics are unchanged. Versions 0.1.0
and 0.1.1 were published under the MIT License and remain under those terms. This source
tree and future releases are proprietary.

### Changed

- Replaced the MIT licence with an all-rights-reserved proprietary licence. No use,
  copying, modification or distribution is permitted without prior written permission
  from the copyright holder; viewing or forking the repository on GitHub does not grant
  those rights.
- Updated package metadata to `LicenseRef-Proprietary` and removed the MIT classifier.
- Bumped the source version to 0.2.0 so unreleased builds cannot be confused with the
  MIT-licensed 0.1.1 artifacts.
- Removed the vendored Cytoscape, dagre and cytoscape-dagre scripts. The authority graph
  is now deterministic layered SVG computed in Python, so screen, print and PDF share
  one layout and no browser layout engine runs. The CSP hashes three inline scripts
  (report data, the vendored Motion runtime and application code); the embedded
  Instrument Serif, Geist and Geist Mono fonts remain under SIL OFL 1.1.
- Rebuilt the offline report interface around the Vermilion Noir identity: near-black
  surfaces, warm ivory editorial typography, vermilion accents, rounded panels, a report
  header with scenario scope, a sticky section bar with a persistent active indicator, a
  four-part summary, an R/E/Z survival rail with distinct zero and unavailable states,
  scoped findings, responsive tables and print-safe light tokens.
- Vendored the official Motion 14.7.1 UMD build (MIT, SHA-256 pinned in
  `report/assets/MANIFEST.json`) and used it for the orchestrated title and metadata
  entrance, the atmospheric header introduction, first-view analytical panel reveals,
  real summary-value transitions and graph detail presence. Simple hover state uses CSS;
  `prefers-reduced-motion` disables ambient movement, reveals and count transitions while
  keeping every value and interaction available. The report still makes no network
  requests and adds no runtime Python dependency.
- Added graph node buttons with roving focus, spatial arrow navigation, Enter selection,
  Escape clear, zoom, pan, fit, wheel and pinch support, and print expansion of details.
- Added a print layout with an A3 landscape graph page, automatic table layout and
  wrapping, and page-break control. A fresh Chromium PDF was generated and the graph
  page inspected.
- Added `tests/test_graph_layout.py` and extended the HTML and report-security suites
  for deterministic geometry, confidence styles, accessible node metadata, the boot
  failure state, navigation state and print rules.

## 0.1.1 — 2026-10-27

Patch release focused on the offline HTML report. The analysis pipeline, CLI surface
and report schemas are unchanged; JSON (`nhi-blast-report/1.0`) and SARIF 2.1.0 output
from 0.1.0 remain compatible. Published as the GitHub Release
[`v0.1.1`](https://github.com/DKtech-dev/nhi-blast/releases/tag/v0.1.1) (wheel, sdist
and SHA-256 sums). No package-index upload or deployment.

### Changed

- Rebuilt the single-file HTML report around an achromatic-ledger layout: a compact
  viewer bar, report header with entrypoint selector, table of contents, summary
  figures, survival panel, rotation plan, cross-scenario matrix, graph, findings,
  assumptions, data files and diagnostics in one printable document.
- Embedded Geist and Geist Mono variable fonts as WOFF2 data URIs under the SIL Open
  Font License 1.1, so typography is identical offline on every platform and the
  report still makes no external request.
- Added zoom-out, zoom-in and fit controls for the authority graph, per-edge dimming
  for off-path inspection, optional label backgrounds with ellipsis, and a brighter
  edge token in the dark theme.
- Added the `--timestamp`-free boot gate: the document stays hidden until the first
  hydrated render to eliminate cumulative layout shift, with a no-script override and
  notice so the report remains readable without JavaScript.
- Wrapped long identifiers at word boundaries, made wide tables keyboard-scrollable
  with visible hints, and shortened matrix column labels while retaining full names in
  the accessible table headers.
- Removed the only `assert` in the Terraform JSON parser; malformed input now returns
  a diagnostic on every path.
- Recorded Bandit's B105 skip in `pyproject.toml` with its justification: the flagged
  strings are credential-kind names, not credential values.

### Security

- Kept the report self-contained: a restrictive CSP hashes all five inline scripts,
  embedded JSON escapes `<`, `>`, `&`, U+2028 and U+2029, DOM construction uses only
  `textContent` and `setAttribute`, and hostile strings render inert.
- Extended the report tests to 24 cases, including the boot gate, no-script fallback,
  font embedding, CSP coverage and external-resource rejection.
- Verified the final report in headless Chrome: zero axe-core WCAG 2.2 AA violations in
  dark, light and mobile views, zero console errors, zero external requests, and
  Lighthouse 98 performance / 100 accessibility / 100 best practices with CLS 0 in the
  desktop profile.

## 0.1.0 — 2026-10-27

Initial release, published as the GitHub Release
[`v0.1.0`](https://github.com/DKtech-dev/nhi-blast/releases/tag/v0.1.0) (wheel, sdist
and SHA-256 sums).
No package-index upload or deployment. The verification record is in
`docs/production-readiness.md`; the internal audit is in `docs/security-audit.md`.
Independent human audit has not been performed and is not claimed.

### Added

- `nhi-blast scan`, `rank`, `explain`, `export`, `schema` and `version` commands with
  exit codes 0–4 and a `rich`-optional console renderer.
- Offline discovery of GitHub Actions workflows, local composite actions, Terraform
  plan/state JSON, a best-effort Terraform HCL fallback and IAM policy documents.
- Marked YAML loading with duplicate-key detection, YAML 1.1 `on` normalisation,
  document and alias limits, and diagnostics instead of exceptions on hostile input.
- Authority graph with per-node and per-edge evidence, deterministic identifiers and
  the `DECLARED > DERIVED > ASSUMED > UNKNOWN` confidence ordering.
- Scenario analysis for compromise selectors: potentially reachable credentials,
  revocation partitioning into R (ends with the entrypoint), E (expires on its own)
  and Z (survives), a separate UNKNOWN-authority potential set, bounded closure and a
  rotation plan with containment, generation ordering, SCC batches and verification
  steps.
- Trust audit and 16 evidence-honest findings (`NHB-OIDC-*`, `NHB-GHA-*`,
  `NHB-CRED-*`, `NHB-SURV-*`, `NHB-ROT-*`) with per-rule documentation under
  `docs/rules/`.
- `rank` for mutable third-party actions ordered by potential blast radius;
  `all-mutable-actions` now also expands `scan` into one deterministic scenario per
  mutable action, sharing the same predicate as `rank`.
- Terraform `.tf.json` configuration reading (resource, data, variable and provider
  blocks) without requiring the optional HCL parser.
- Deterministic JSON (`nhi-blast-report/1.0`), SARIF 2.1.0 and a single-file offline
  HTML report with escaped embedded data, text-only DOM construction, a restrictive
  CSP with inline-script hashes and vendored, hash-recorded JavaScript libraries.
- Cross-scenario exposure matrix, deterministic shortest-path trace with graph
  highlighting, scenario-aware summary, and findings search/severity/scenario filters
  in the offline HTML report.
- Accessible, responsive HTML layout: skip link, labelled navigation and table regions,
  captions and column scopes, wrapping identifiers, narrow-width spacing, a text
  alternative for the pointer-only graph, and keyboard-operable trace controls.
- `nhi-blast.toml` configuration with strict unknown-key rejection, identity
  precedence and limit overrides.
- Exact version lock files for runtime and development dependencies, a CI workflow
  pinned to full action commit SHAs and covering Python 3.12, 3.13 and 3.14 on Ubuntu
  and Windows, an allowlisted artifact-content checker that rejects scratch trees, and
  a three-build digest reproducibility check.
- Unit, integration, property-based, security, golden and performance tests with
  coverage gates, plus a deterministic large-repository fixture generator.

### Changed

- Policy-document references found in Terraform inputs are retained for cross-file
  resolution instead of being reduced to an unresolved string.

### Fixed

- A valid `.tf.json` Terraform configuration was incorrectly reported as
  `D-TF-HCL-PARSE`; it now parses as JSON configuration, while malformed JSON still
  produces the diagnostic.
- A long rotation-plan identifier widened the HTML page on narrow viewports; the step
  grid now uses `minmax(0, 1fr)` and allows its children to shrink.
- Finding cards inherited severity colours across all body text, and the light-theme
  medium colour missed the 4.5:1 contrast threshold; body text now uses the normal ink
  colour and the medium palette is darker.

### Security

- The tool makes no network calls, executes no scanned content and evaluates no
  GitHub expressions.
- Path containment is enforced for every read; escaping symlinks and junctions are
  rejected.
- Credential values are never stored or printed. Literal-credential findings report
  kind and length only.
- Hostile strings are rendered inert in every output format.
- CI checkouts do not persist credentials, workflow tokens are read-only, actions are
  pinned to full commit SHAs and the repository requires SHA pinning. Dependabot alerts
  and security updates are enabled, and `main` is protected against deletion and
  force-pushes.
- An internal security audit with third-party scanners found no open high or critical
  issue; results and residual risk are in `docs/security-audit.md`. It is not an
  independent audit.

### Known limitations

- The analysis describes potential authority from the supplied files. It does not
  prove compromise, exploitation or that any credential was obtained.
- Unmodelled controls (SCPs, permission boundaries, KMS key policies, environment
  protection, branch rules and live state) are listed in the report assumptions and
  in `docs/known-limitations.md`.
- The HCL parser is a best-effort fallback for literal configuration; unresolved
  expressions stay unknown.
- Release gates, packaging checks, remote CI runs, clean-environment installation and
  audit results are recorded in `docs/production-readiness.md`. No independent human
  audit has been performed; the external audit package is prepared but unaudited.
