# NHI-Blast 0.1.1

Prepared for release on 2026-10-27 as a GitHub Release with the wheel, sdist and
`SHA256SUMS`. No package-index upload, deployment or SaaS was performed. This is a
report-focused patch; the analysis pipeline, CLI commands, JSON schema
(`nhi-blast-report/1.0`) and SARIF 2.1.0 output are unchanged from 0.1.0. The release
record and asset verification are appended after publication.

## What changed

- The single-file offline HTML report was rebuilt around an achromatic-ledger layout:
  viewer bar, entrypoint selector, table of contents, summary, survival panel, rotation
  plan, cross-scenario matrix, graph, findings, assumptions, data files and diagnostics
  in one printable document.
- Geist and Geist Mono are embedded as WOFF2 data URIs under the SIL Open Font License
  1.1. The report remains fully offline and renders the same typography on every
  platform.
- The authority graph gained zoom-out, zoom-in and fit controls, off-path dimming,
  label backgrounds with ellipsis and a brighter dark-theme edge token.
- A boot gate hides the document until the first hydrated render, removing cumulative
  layout shift. A no-script override keeps the document visible and shows a notice
  that the report needs JavaScript.
- Long identifiers wrap at word boundaries, wide tables are keyboard-scrollable with
  visible hints, and matrix column labels are shortened while full names remain in the
  accessible table headers.
- `scripts/check_artifacts.py` now requires the embedded fonts and their OFL licence
  file in the wheel.
- The Terraform JSON parser no longer uses an `assert`; malformed input returns a
  diagnostic on every path. Bandit's B105 skip is recorded with its justification:
  the flagged strings are credential-kind names, not credential values.

## Verification

Recorded on Windows 11 (10.0.26200, x64), CPython 3.12.14, unless a GitHub Actions run
is cited. The complete release-gate record is in `docs/production-readiness.md`.

- Full suite: 418 passed, 1 skipped (a real Windows symlink needs an unheld privilege;
  Linux CI executes it).
- Adversarial suite: 37 passed, 1 skipped. Golden: 2 passed. Performance: 2 passed
  (graph build plus scenario 1.57 s of a 5 s budget; rank 6.29 s of a 60 s budget).
- Coverage: 86.67% overall line coverage; every enforced module at or above 80%;
  `report/html.py` and `report/ui.py` at 100%.
- `ruff check`, `ruff format --check`, `mypy --strict src` and
  `scripts/gen_schema.py --check`: clean.
- Three consecutive hatchling builds produced identical wheel and sdist SHA-256
  digests. The wheel (92 files) and sdist (242 files) passed
  `scripts/check_artifacts.py`.
- Clean installs: the wheel with `requirements.lock` and the wheel with the `hcl` extra
  both ran all six commands; the minimal wheel reported `D-TF-HCL-UNAVAILABLE` for HCL
  input while JSON input still worked; the sdist installed and scanned fx01. Repeated
  scans produced byte-identical JSON, SARIF and HTML.
- Browser QA in headless Chrome: zero axe-core WCAG 2.2 AA violations on desktop dark,
  desktop light and mobile dark; zero console errors or warnings; zero external
  requests; no horizontal overflow at 1440, 768 or 390 px; fonts loaded and Geist was
  actually used; the boot gate clears after hydration.
- Lighthouse 13.5.0, desktop profile: performance 98, accessibility 100,
  best-practices 100, FCP 0.9 s, LCP 0.9 s, TBT 10 ms, CLS 0. The same report under
  simulated mobile throttling scores 65 because the 841 KiB single file is downloaded
  at 1.6 Mbps; that profile does not represent opening an offline file from disk.
- html-validate 11.17.0: clean. Design inspector: 0 findings at 1440, 768 and 390 px.
- zizmor 1.31.1: 0 findings. actionlint 1.7.12: 0 diagnostics. Semgrep 1.182.1
  (`p/ci`, `p/python`): 0 findings. Bandit 1.9.4: 0 findings. pip-audit 2.10.1 and
  Grype 0.121.0: no known vulnerabilities. pip-licenses: only permissive and
  documented weak-copyleft licences, including the fonts' OFL-1.1.

## Security and assurance limits

The report keeps the same security properties as 0.1.0: restrictive CSP hashing all
five inline scripts, Unicode-escaped embedded JSON, text-only DOM construction, no
network requests and no credential values. Hostile strings are covered by tests and
render inert.

No independent human security audit has been performed, and none is claimed. The
internal audit and the external-audit package define what an independent reviewer
would receive. Cross-machine byte reproducibility and non-Windows/Linux platform
coverage are not claimed.

## Upgrade

Replace the 0.1.0 wheel with `nhi_blast-0.1.1-py3-none-any.whl`; there is no data or
schema migration. Verify the download against `SHA256SUMS` attached to the release.
