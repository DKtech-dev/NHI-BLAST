# Testing NHI-Blast

This document records what the test suite proves, how to run every gate, and the
measured results used for milestone acceptance. It is descriptive, not normative; the
requirements remain in `docs/SPEC.md` and the operating rules in `AGENTS.md`.

## 1. Setup

```sh
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev,hcl]"
```

On POSIX use `.venv/bin/python`. All commands below are run from the repository root.
Tests make no network calls and execute no scanned content.

## 2. Gates

| Gate | Command | Result on 2026-10-27 |
| --- | --- | --- |
| Full suite | `./.venv/Scripts/python.exe -m pytest -q` | 418 passed, 1 skipped in 23.23 s |
| Remote suite | GitHub Actions CI, Ubuntu and Windows, Python 3.12–3.14 | The 0.1.1 run 40509205221 passed the package job and all six test jobs: `417 passed, 2 deselected` plus `2 passed` for the slow suite, 0 skipped, coverage 86.73–86.74% |
| Adversarial | `./.venv/Scripts/python.exe -m pytest -q -m security` | 37 passed, 1 skipped |
| Golden | `./.venv/Scripts/python.exe -m pytest -q -m golden` | 2 passed |
| Performance | `./.venv/Scripts/python.exe -m pytest -q -m slow` | 2 passed in 9.22 s |
| Coverage | `./.venv/Scripts/python.exe scripts/check_coverage.py` | 86.67% locally with slow tests deselected; 86.73–86.74% in the remote full-suite run; gate passed |
| Schema | `./.venv/Scripts/python.exe scripts/gen_schema.py --check` | clean |
| Artifacts | `./.venv/Scripts/python.exe scripts/check_artifacts.py dist` | clean; wheel 92 files, sdist 242 files |
| Reproducibility | three hatchling builds into separate directories, then `sha256sum` | identical wheel and sdist digests |
| Dependency audit | pip-audit 2.10.1; OSV-Scanner 2.7.0; Grype 0.121.0 on both SBOMs | no known advisories; no vulnerabilities |
| Secret scans | gitleaks 8.30.1 on 9 commits / 2.32 MB; TruffleHog 3.99.7 on 460 chunks / 2,320,652 bytes without verification | 0 leaks; 0 verified and 0 unverified secrets |
| Internal audit | zizmor 1.31.1, actionlint 1.7.12, Semgrep 1.182.1, Bandit 1.9.4 | 0 workflow findings; 0 actionlint diagnostics; 0 Semgrep findings on `p/ci` and `p/python`; 0 Bandit findings |
| Browser QA | Chrome via CDP at 1440×900, 768×1024 and 390×844; axe-core 4.10.3 | 0 axe violations in desktop dark, desktop light, mobile dark; 0 console/log errors; 0 external requests; 0 overflow; boot gate clears after hydration |
| HTML validation | html-validate 11.17.0 | clean |
| Lighthouse | Lighthouse 13.5.0, desktop profile | performance 98, accessibility 100, best-practices 100; FCP/LCP 0.9 s, TBT 10 ms, CLS 0 |
| Design inspector | `design-taste-frontend` inspector at 1440, 768 and 390 px | 0 findings |
| Python 3.13 | isolated environment; `-m pytest -q -m "not slow"` and `-m slow` | 416 passed, 1 skipped, 2 deselected; 2 slow passed |
| Python 3.14 | isolated environment; `-m pytest -q -m "not slow"` and `-m slow` | 416 passed, 1 skipped, 2 deselected; 2 slow passed |
| Lint | `./.venv/Scripts/python.exe -m ruff check .` | clean |
| Format | `./.venv/Scripts/python.exe -m ruff format --check .` | clean (113 files) |
| Types | `./.venv/Scripts/python.exe -m mypy src` | clean (71 files) |

Coverage runs exclude the `slow` marker because tracing inflates wall-clock time and
would invalidate the 12.8 measurement. The performance gate must be run without
coverage instrumentation.

The single skip is a real filesystem symlink that Windows refuses to create without
elevation. Directory-junction escape coverage always runs on Windows and is not
skipped.

## 3. Test matrix

### Parsers and hostile input

| File | What it proves |
| --- | --- |
| `tests/test_workflows.py` | Workflow shape, triggers, permissions, inheritance and job parsing |
| `tests/test_composite.py` | Local composite expansion, cycle and depth limits |
| `tests/test_conditions.py` | Condition operator truth table, dead keys, variables |
| `tests/test_glob.py` | Glob matching and intersection, including brute-force equivalence |
| `tests/test_security.py` | Malformed JSON/HCL/YAML, limits, traversal, link escape, secret leakage |

Adversarial cases include duplicate YAML keys after `on`/`true` normalisation,
multi-document streams, node/depth/alias limits at and over the boundary, deeply
nested Terraform JSON, malformed Terraform, oversized and non-UTF-8 files, exact file
counts, path traversal, escaping file symlinks, escaping directory junctions, and a
synthetic literal plus Terraform-sensitive canary checked across console, model JSON,
SARIF and HTML.

### Resolution, graph and analysis

| File | What it proves |
| --- | --- |
| `tests/test_roles.py` | Terraform/IAM role and sink resolution |
| `tests/test_solver.py`, `test_subjects.py`, `test_trust.py` | OIDC subjects, trust evaluation and conservative filters |
| `tests/test_graph_builder.py`, `test_graph_store.py` | Rules R1-R14, deduplication, deterministic ordering |
| `tests/test_selectors.py` | Selector parsing and start-set resolution |
| `tests/test_reach.py`, `test_partition.py`, `test_scenario.py` | Reachability, R/E/Z partition and closure |
| `tests/test_rotation.py`, `test_rank.py`, `test_findings.py` | Rotation ordering, ranking and rule output |
| `tests/test_policy_eval.py` | Allow/deny precedence, boundaries, resource policies, KMS |
| `tests/test_properties.py` | Prefilter soundness, selector round-trips, identifier stability, condition truth |

The prefilter properties are the important ones: for generated resource patterns and
candidate ARNs, `CandidateFilter` must admit every pair for which
`evaluate_action` returns ALLOW or CONDITIONAL_ALLOW. The same implication is checked
for `TrustSubjectFilter` against generated subjects and trust statements. These tests
can discover false negatives but do not claim completeness of either filter.

### Reporters, CLI and end-to-end behavior

| File | What it proves |
| --- | --- |
| `tests/test_console.py`, `test_json_report.py`, `test_sarif.py`, `test_html.py` | Artifact shape, schema, CSP, accessible table/heading structure, scrollable table regions, and graph focus mapping |
| `tests/test_report_security.py` | Injection and secret-leak checks at every output boundary |
| `tests/test_cli.py` | Commands, options, exit codes and error paths |
| `tests/test_pipeline.py` | Discovery through reporting, configuration and strictness |
| `tests/test_fixtures.py` | Reviewed end-to-end counts and diagnostics for fx01-fx15 |
| `tests/test_golden.py` | Exact reviewed fx07 console and semantic summary |
| `tests/test_determinism.py` | Byte-identical repeated runs and an offline socket guard |
| `tests/test_performance.py` | Spec 12.8 budgets at full scale |
| `tests/test_ci_pins.py` | Full-SHA action pins, read-only CI token, lock-file policy, advisory-free pytest |
| `tests/test_artifacts.py` | Artifact checker regressions: optional extras, markers, dot-directory normalisation |
| `tests/test_docs.py` | Local documentation links, rule-page coverage, CLI command coverage |

## 4. Fixtures

`tests/fixtures/fx01..fx15` are deterministic repositories. `tests/fixtures/README.md`
is the inventory of verified counts, R/E/Z sizes, potential findings and diagnostics.
Each fixture directory also has a short README stating its purpose.

The scale fixture is reproducible:

```sh
./.venv/Scripts/python.exe scripts/gen_fixtures.py tests/fixtures/fx15-scale-smoke \
  --workflows 4 --resources 40 --actions-per-workflow 2

./.venv/Scripts/python.exe scripts/gen_fixtures.py "$TEMP/nhi-blast-fx15" \
  --workflows 200 --resources 2000 --actions-per-workflow 2
```

No fixture contains a real or realistic credential value. Placeholder canaries are
clearly synthetic and exist only so leak tests can search for them.

## 5. Goldens

`tests/golden/fx07-console.txt` and `tests/golden/fx07-summary.json` are the exact
reviewed output for the incident fixture. They were checked against the semantic
requirements in spec 14.4: role findings, R/E/Z membership, rotation order and
assumption set.

The console sketch in spec 14.4 is illustrative rather than byte-normative. Its
`[1/4]` progress headings and its single warning are not reproduced; the current
console is a single deterministic report, and the fixture produces no warning. The
golden records the exact reviewed bytes. Never regenerate a golden and accept it
without reviewing the semantic change; a failing golden is a behavior change first and
a file update second.

## 6. Determinism and offline behavior

`tests/test_determinism.py` runs the same scan twice into different output
directories and requires identical console text and identical JSON, SARIF and HTML
bytes. It repeats this for reversed selector order and for rank/export artifacts. A
separate test replaces socket entry points with failures and runs a full scan, proving
the runtime path makes no network call.

Artifacts contain no wall-clock time unless `--timestamp` is passed. When it is, only
`generated_at` changes; every other field remains identical.

## 7. Performance

Measured on 2026-10-26 with the full generated fixture:

- Machine: Windows 11 (10.0.26200), 12th Gen Intel Core i5-12450H, 15.7 GiB RAM,
  Python 3.12.14 (64-bit), local SSD, project virtual environment.
- Fixture: 200 workflows, 200 jobs, 2,000 Terraform resources, 400 mutable action use
  sites.
- Load only: 0.623 s.
- Graph build plus one `repo-write` scenario: 1.568 s (budget 5 s).
- Resulting graph: 4,202 nodes, 4,199 edges; R=400, E=200, Z=1,000.
- Full `rank`: 6.285 s for 400 mutable actions (budget 60 s).

These are observations on one machine, not a portability claim. The test asserts the
spec budget and fails with the measured duration in the message.

## 8. Coverage policy

`scripts/check_coverage.py` enforces:

- at least 80% overall line coverage;
- at least 80% line coverage for every module under `nhi_blast/aws/`,
  `nhi_blast/analysis/` and `nhi_blast/report/`.

The second rule covers the decision procedure and all artifact writers. Parser and
discovery safety is enforced by adversarial behavior tests rather than by a line
percentage, because OS-error and hostile-shape branches are not meaningfully measured
by line count alone.

Measured result: 86.67% overall line coverage, 89.47% statement coverage (6,372 of
7,122), 78.87% branch coverage (2,019 of 2,560). Every enforced module is at or above
80%; the lowest is `report/explain.py` at 83.78%, followed by `aws/sinks.py` at
87.88% and `aws/policy_eval.py` at 88.81%. Both `report/html.py` and
`report/ui.py` are at 100%.

## 9. Packaging and release checks

The test suite does not build distributions. The release procedure adds checks that
must be run separately; their results are recorded in
`docs/production-readiness.md`.

- Build one wheel and one sdist with the pinned hatchling version, then run
  `scripts/check_artifacts.py dist`. It requires all eight platform data files, the
  three vendored scripts, both font files, `OFL.txt` and `MANIFEST.json`, rejects test
  tooling in runtime requirements, rejects caches, scratch files and the private
  research cache in either artifact, and rejects any sdist top-level entry outside an
  explicit allowlist.
- Install the wheel into a fresh virtual environment with `requirements.lock` and
  exercise all six CLI commands on fx07. The 0.1.1 record found
  `version`, `version --data`, `schema`, `scan`, `rank`, `export` and `explain`
  successful, fx07 producing JSON, SARIF and HTML, and repeated installed-wheel scans
  byte-identical. Repeat without the `hcl` extra and confirm fx10 reports
  `D-TF-HCL-UNAVAILABLE` while JSON input still works; with the extra, fx10 parses HCL
  (14 graph nodes versus 8 without it). Install and scan from the sdist in a third
  clean environment.
- Audit both lock files with `pip-audit`. The current record used pip-audit 2.10.1 in
  an isolated environment; both locks reported no known vulnerabilities.
- Build the wheel and sdist three times into separate directories and compare SHA-256
  digests. The final record produced identical wheel and sdist digests from an
  unchanged tree and the same toolchain; cross-machine reproducibility is not claimed.
- Open a freshly generated report from `file:///` in a real browser at desktop,
  tablet and mobile widths. The 0.1.1 record used headless Chrome through CDP at
  1440×900, 768×1024 and 390×844: zero horizontal overflow, zero console or log
  errors, zero external requests, both embedded fonts loaded and Geist measurably in
  use, the boot gate cleared after hydration, and the no-script override kept the
  document visible with its notice. axe-core 4.10.3 reported zero WCAG 2.2 AA
  violations in desktop dark, desktop light and mobile dark. The same run exercised
  scenario switching, graph zoom/fit, trace highlighting, table scroll regions and
  finding filters.
- Validate the report with `html-validate` 11.17.0 (clean) and run Lighthouse 13.5.0
  in the desktop profile: performance 98, accessibility 100, best-practices 100,
  FCP/LCP 0.9 s, TBT 10 ms and CLS 0. Under simulated mobile throttling the same
  841 KiB single file scores 65 on performance because of the 1.6 Mbps download cap;
  that profile is not representative of opening an offline file from disk, so the
  desktop profile is the recorded UI budget. Both results are reported rather than
  choosing only the favourable one.
- Run the design inspector at 1440, 768 and 390 px. The 0.1.1 record reports zero
  findings.
- Run the suite on Python 3.13 and 3.14 in CI and locally. The local pre-audit runs
  produced 393 passed, 1 skipped and 2 deselected for the non-slow suite, and 2 passed
  for the slow suite; the remote CI jobs on Python 3.13 and 3.14 passed the complete
  suite including the two tests added during the audit.
- Run the adversarial soak and real-world corpus harnesses outside the repository. The
  ten-repository corpus produced 21 scenarios matching 21 rank rows, 37 findings, 1,149
  nodes and 2,181 edges with no failures and byte-identical repeats; the 16-case soak
  produced no failures.
- The CI workflow is statically checked by `tests/test_ci_pins.py` and has run green on
  GitHub-hosted Ubuntu and Windows runners for Python 3.12–3.14, with a separate
  advisory workflow. Run URLs and results are recorded in
  `docs/production-readiness.md`.
- The audit added two documentation-level checks: the assumption registry must contain
  unique, fully populated entries that match `docs/assumptions.md`, and report
  templates must not assert proof, guarantee, exploitability or takeover. These close
  the two previously partial traceability rows without changing runtime behaviour.

## 10. Known deviations and limits

- Creating a real file symlink requires Windows Developer Mode or elevation in this
  environment; that one test skips. Directory junctions are created without elevation
  and prove the escaping-link pruning path. On POSIX the symlink test runs.
- The performance numbers above are a single-machine observation and will vary.
- Coverage is line-oriented for the gate; branch coverage is reported but not gated.
- The browser pass uses headless Chrome and device emulation. It verifies rendering,
  graph initialization and zoom, keyboard focus, matrix/trace/filter interactions, the
  boot gate and no-script fallback, embedded-font use and the absence of
  console/network activity; it is not a manual screen-reader or assistive-technology
  audit. axe-core also cannot compute contrast over a few decorative gradients; the
  affected text pairs were checked manually. Lighthouse's simulated mobile profile is
  reported separately and is not the UI budget for an offline file.
- Python 3.13 and 3.14 have passed locally on Windows. Linux, remote CI and an
  independent audit remain external gates; no local run substitutes for them.
- No test claims an independent security audit, production deployment, or external
  certification.
