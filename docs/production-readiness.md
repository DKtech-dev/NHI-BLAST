# Production readiness

**Verdict: NOT RELEASE READY.** The implementation and the local release gates are
complete: tests on Python 3.12/3.13/3.14, coverage, packaging, three-build
reproducibility, clean installs, dependency audit, CI policy, documentation, a
10-repository corpus, an adversarial soak, and real-browser plus axe verification of
single- and multi-scenario reports. Remote CI execution, execution on Linux, the CI
advisory automation decision, independent audit, and publication remain open. Nothing
has been published, tagged, deployed or independently audited, and this document must
not be cited as such.

This page is the release-gate record. It states what was actually executed on the
recorded environment and what remains open. The milestone history is in
`docs/implementation-status.md`; the requirement mapping is in
`docs/requirements-traceability.md`.

## Environment

| Item | Value |
| --- | --- |
| Date of the recorded gates | 2026-10-26 to 2026-10-27 (local) |
| OS | Windows 11 (10.0.26200), x64 |
| Python | CPython 3.12.14 primary; 3.13.17 and 3.14.7 in isolated environments |
| Machine | 12th Gen Intel Core i5-12450H, 15.7 GiB RAM, local SSD |
| Runtime dependencies | `requirements.lock` exact versions |
| Development dependencies | `requirements-dev.lock` exact versions |
| Distribution under test | locally built `nhi_blast-0.1.0-py3-none-any.whl` and sdist; SHA-256 values are recorded beside the artifacts in `dist/SHA256SUMS`, not embedded here because this document is packaged in the sdist |

## Gate matrix

| Gate | Requirement | Actual result | Status |
| --- | --- | --- | --- |
| Specification implementation | M0–M7 pipeline and CLI complete | Implemented and exercised end to end; see `docs/implementation-status.md` | Pass |
| Full test suite | All tests pass; warnings are errors | 395 passed, 1 skipped in 20.35 s (the skip is the real-symlink case described below) | Pass |
| Python 3.13 suite | Same suite on CPython 3.13 | 393 passed, 1 skipped, 2 deselected in 9.45 s (non-slow); slow: 2 passed in 9.89 s | Pass (local) |
| Python 3.14 suite | Same suite on CPython 3.14 | 393 passed, 1 skipped, 2 deselected in 9.47 s (non-slow); slow: 2 passed in 12.17 s | Pass (local) |
| Adversarial suite | Security-marked hostile-input tests pass | 32 passed, 1 skipped (real symlink creation requires a Windows privilege) | Pass |
| Golden output | Reviewed fx07 console and semantic summary | 2 passed | Pass |
| Performance | SPEC 12.8 budgets | 2 passed in 10.40 s; graph build + scenario 1.568 s (budget 5 s), rank 6.285 s (budget 60 s), using the documented 200-workflow/2,000-resource fixture | Pass |
| Coverage | ≥80% overall; ≥80% in `aws/`, `analysis/`, `report/` | 86.47% overall line coverage; 89.30% statements; 78.59% branches; lowest enforced module is `report/html.py` at 83.10%; gate passed | Pass |
| Lint | `ruff check` | Clean over `src`, `tests`, `scripts` | Pass |
| Format | `ruff format --check` | 112 files already formatted | Pass |
| Types | `mypy --strict src` | Clean, 70 source files | Pass |
| Report schema | Committed schema matches generated schema | `scripts/gen_schema.py --check` exit 0 | Pass |
| Determinism and offline | Byte-identical repeats; no socket use | Covered by `tests/test_determinism.py` in the full suite; the corpus harness also required byte-identical JSON/SARIF/HTML across repeated scans for all ten repositories | Pass |
| Artifact contents | Required data/assets/docs present; no caches, scratch or research cache | `scripts/check_artifacts.py` passed: wheel 88 files, sdist 234 files; every sdist top-level entry is on an explicit allowlist; sizes and digests are recorded in `dist/SHA256SUMS` beside the frozen artifacts | Pass |
| Clean install (HCL extra) | Wheel installs with runtime lock; all six commands work | `version`, `version --data`, `schema`, `scan`, `rank`, `export` and `explain` all exit 0 on the final wheel; fx07 JSON/SARIF/HTML produced; HCL fixture fx10 parsed | Pass |
| Clean install (minimal) | Wheel without HCL extra degrades clearly | `version` works; fx10 with `--tf-hcl` reports `D-TF-HCL-UNAVAILABLE` with install guidance; `--strict` returns 3 | Pass |
| Clean install (sdist) | The sdist builds and installs | Fresh venv install from the final sdist; `version` and an fx01 scenario scan exit 0 | Pass |
| Dependency audit | No known advisories in locked sets | `pip-audit 2.10.1` on `requirements.lock` and `requirements-dev.lock`: no known vulnerabilities | Pass |
| Real-world corpus | Ten public repositories, including workflows and Terraform | 0 failures; 1,959 files, 163 workflow files, 101 Terraform files; 21 all-mutable-actions scenarios exactly matching 21 rank rows; 37 findings, 1,149 nodes, 2,181 edges, 451 diagnostics; max scan 1.92 s, max rank 1.82 s, max export 1.87 s | Pass (sample) |
| Adversarial soak | Hostile and boundary inputs terminate within documented exit codes | 16 cases, 0 failures; hostile YAML, traversal, Terraform JSON/plan/HCL, 80-finding repository, bad config and CLI negatives all handled without traceback | Pass (sample) |
| CI policy | Actions pinned to full SHAs; read-only token; locks used | 7 policy tests pass; checkout v7.0.1 and setup-python v7.0.0 pinned to commit SHAs older than 14 days; CI matrix includes Python 3.13 and 3.14 on Ubuntu and Windows | Pass (static) |
| CLI exit codes | 0, 1, 2, 3 and 4 observed | 0 success and `--fail-on never`; 1 on `--fail-on critical`; 2 for bad selector/format/path/config; 3 for strict partial results; 4 covered by CLI tests | Pass |
| HTML structure and accessibility | Language, title, headings, labels, skip link, table semantics, graph text alternative | Static tests pass; CSP, escaping and inert-hostile-string tests pass; axe-core 4.10.3 reports 0 violations and 52 passes in both light and dark schemes; the only incomplete check is gradient-background contrast, whose text pairs were manually computed at ≥4.86:1 | Pass |
| Documentation set | README, architecture, rules, assumptions, provenance, benchmark, limitations, release, security, contributing, changelog, NOTICE | Present; local-link and rule-coverage tests included in the suite | Pass |
| Three-build reproducibility | Repeated clean builds produce identical artifact digests | Three consecutive builds from the same unmodified tree produced identical SHA-256 digests for both the wheel and the sdist; cross-machine and cross-toolchain byte reproducibility is not claimed | Pass (local) |
| Remote CI execution | The defined matrix runs green on GitHub-hosted runners | Workflow exists and is statically checked; it has not run because this repository has no configured remote | Open |
| Cross-platform runtime | Linux and Python 3.13/3.14 | Python 3.13.17 and 3.14.7 pass locally on Windows; the CI matrix covers Python 3.12–3.14 on Ubuntu and Windows; Linux has not executed | Partial |
| Browser rendering | Report renders, graph initializes and interactive analysis works at desktop and mobile widths | Chrome 156.0.8078.47, 1440×900 and 390×844 via CDP on 10-scenario and 2-scenario reports: 3 graph canvases, 48 matrix status buttons, no horizontal overflow (`scrollWidth == clientWidth`), 0 console messages, 0 exceptions, 0 external requests; scenario switch, 2-hop and 8-hop traces, filters and shared-credential view exercised | Pass |
| Independent audit | External security review | None performed and none claimed | Not claimed |
| Publication | Tag, package-index upload, deployment | None performed; requires explicit authorization | Not performed |

## Open gates and next actions

1. **Run the CI workflow on a hosted remote.** Push the source to an authorized
   repository only after explicit authorization, let the OS/Python test matrix and
   package job run, and record the run URLs and logs in this document. Do not treat the
   local Windows run as evidence for Linux.
2. **Execute on Linux.** The CI matrix covers Ubuntu/Windows and Python 3.12–3.14;
   Python 3.13.17 and 3.14.7 have now passed locally on Windows, but no Linux host has
   executed the suite. Record the first successful Linux run.
3. **Decide whether to automate advisory scanning in CI.** The current release
   procedure audits both locks with `pip-audit` in a separate environment; CI does not
   yet run it because audit tooling is not part of the locked development set.
4. **Authorization for publication.** Tagging, uploading to a package index, deploying,
   or announcing a release requires explicit authorization. No such action was taken.

The browser/axe pass, three-build comparison and local artifact checks are recorded
above and are complete for this environment. They remain single-machine observations.

## Release decision

A release candidate may be declared only when every gate above is marked Pass or is
explicitly accepted as a documented limitation by the maintainer. The current source
tree and locally built artifacts must not be described as a release candidate, and
must not be uploaded or deployed, while any gate marked Open or Pending remains.

The tool's own analysis is evidence-honest by design: it reports potential authority,
conditional survival and rotation order. This readiness document makes the same
distinction about the project itself. Local tests demonstrate behaviour on the
recorded environment; they do not prove the absence of defects or constitute an
independent security audit.
