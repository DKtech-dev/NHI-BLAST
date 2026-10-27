# Production readiness

**Verdict: RELEASE READY for the authorized GitHub Releases distribution scope.** Every
automated and internal gate below passes on the recorded environments, including the
remote CI matrix on Linux and Windows. The independent human security audit has not
been performed and is not claimed; it remains the one open assurance gate and is
disclosed in `docs/security-audit.md` and `docs/external-audit-package.md`.
Version 0.1.1 is the release candidate for this evidence record; publication to the
private repository's GitHub Releases (wheel, sdist and `SHA256SUMS`) is the final
authorized step and is recorded here after verification. Version 0.1.0 was published
on 2026-10-27 as
https://github.com/DKtech-dev/nhi-blast/releases/tag/v0.1.0. No package-index upload,
deployment or SaaS was performed.

This page is the release-gate record. It states what was actually executed on the
recorded environments and what remains open. The milestone history is in
`docs/implementation-status.md`; the requirement mapping is in
`docs/requirements-traceability.md`; the audit is in `docs/security-audit.md`.

## Environment

| Item | Value |
| --- | --- |
| Date of the recorded gates | 2026-10-27 |
| Local OS | Windows 11 (10.0.26200), x64 |
| Remote OS and Python | GitHub Actions `ubuntu-latest` and `windows-latest`; CPython 3.12, 3.13 and 3.14 |
| Local Python | CPython 3.12.14 primary; 3.13.17 and 3.14.7 in isolated environments |
| Machine | 12th Gen Intel Core i5-12450H, 15.7 GiB RAM, local SSD |
| Repository | `DKtech-dev/nhi-blast`, private, branch `main` |
| Runtime dependencies | `requirements.lock` exact versions |
| Development dependencies | `requirements-dev.lock` exact versions |
| Distribution under test | `nhi_blast-0.1.1-py3-none-any.whl` and `nhi_blast-0.1.1.tar.gz`; SHA-256 values are in `dist/SHA256SUMS` and the release assets, not embedded here because this document is packaged in the sdist |
| UI tooling | Headless Chrome through CDP; axe-core 4.10.3; Lighthouse 13.5.0 (desktop and simulated mobile profiles); html-validate 11.17.0; design inspector at 1440, 768 and 390 px |

## Remote CI evidence

| Workflow | Run | Result |
| --- | --- | --- |
| CI 0.1.1 (`ci.yml`) | Run URL recorded after the release commit is pushed; see the repository Actions history | Pending at this pre-release commit; the local gate set below is complete |
| Advisory audit 0.1.1 (`audit.yml`) | Scheduled and push-triggered run after the release commit | Pending at this pre-release commit; the equivalent local scanner runs are recorded below |
| CI 0.1.0 (`ci.yml`) | https://github.com/DKtech-dev/nhi-blast/actions/runs/40432137207 | Package job passed; all six test jobs passed with `404 passed` each and coverage 86.53–86.54% on Ubuntu and Windows, Python 3.12–3.14 |
| Advisory audit 0.1.0 (`audit.yml`) | https://github.com/DKtech-dev/nhi-blast/actions/runs/40432137192 | Passed: both lock files audited, Bandit, OSV-Scanner and gitleaks |
| First fully green CI | https://github.com/DKtech-dev/nhi-blast/actions/runs/40427815113 | Package and six test jobs passed after the toolchain fixes |

The CI jobs ran `ruff check`, `mypy`, the full suite, the coverage gate, the performance
tests and the package build. The release run includes the two documentation/claim tests
added with the audit. Windows runners can create the real symlink used by the security
suite, so the local Windows skip does not appear there.

## Gate matrix

| Gate | Requirement | Actual result | Status |
| --- | --- | --- | --- |
| Specification implementation | M0–M7 pipeline and CLI complete | Implemented and exercised end to end; see `docs/implementation-status.md` | Pass |
| Full test suite (local) | All tests pass; warnings are errors | 418 passed, 1 skipped in 16.56 s (the skip is the real-symlink case described below) | Pass |
| Full test suite (remote) | Linux and Windows, Python 3.12–3.14 | 0.1.0 run 40432137207: 404 passed per job on six GitHub-hosted jobs; the 0.1.1 run is recorded after publication | Pass (0.1.0 run); 0.1.1 pending |
| Python 3.13 suite | Same suite on CPython 3.13 | Local 3.13.17: 416 passed, 1 skipped, 2 deselected plus 2 slow passed; remote 0.1.0 job passed | Pass |
| Python 3.14 suite | Same suite on CPython 3.14 | Local 3.14.7: 416 passed, 1 skipped, 2 deselected plus 2 slow passed; remote 0.1.0 job passed | Pass |
| Adversarial suite | Security-marked hostile-input tests pass | 37 passed, 1 skipped locally (real symlink creation requires a Windows privilege); the Linux CI job executes the skipped case | Pass |
| Golden output | Reviewed fx07 console and semantic summary | 2 passed | Pass |
| Performance | SPEC 12.8 budgets | 2 passed in 9.22 s; previously measured graph build + scenario 1.568 s (budget 5 s), rank 6.285 s (budget 60 s) on the documented 200-workflow/2,000-resource fixture | Pass |
| Coverage | ≥80% overall; ≥80% in `aws/`, `analysis/`, `report/` | 86.67% overall line coverage; 89.47% statements, 78.87% branches; every enforced module ≥80%; `report/html.py` and `report/ui.py` at 100% | Pass |
| Lint | `ruff check` | Clean over `src`, `tests`, `scripts` locally and in CI | Pass |
| Format | `ruff format --check` | 113 files already formatted | Pass |
| Types | `mypy --strict src` | Clean, 71 source files locally and in CI | Pass |
| Report schema | Committed schema matches generated schema | `scripts/gen_schema.py --check` exit 0 | Pass |
| Determinism and offline | Byte-identical repeats; no socket use | `tests/test_determinism.py`; corpus byte comparison; three-build digest comparison; no network-capable module imported by `src` | Pass |
| Artifact contents | Required data/assets/docs present; no caches, scratch or research cache | `scripts/check_artifacts.py` passed: wheel 92 files, sdist 242 files; includes both fonts, `OFL.txt`, vendor scripts and `MANIFEST.json`; every sdist top-level entry is on an explicit allowlist | Pass |
| Clean install (HCL extra) | Wheel installs with runtime lock; all six commands work | `version`, `version --data`, `schema`, `scan`, `rank`, `export` and `explain` all exit 0 on the final wheel; fx07 JSON/SARIF/HTML produced; HCL fixture fx10 parsed (14 nodes vs 8 without the extra) | Pass |
| Clean install (minimal) | Wheel without HCL extra degrades clearly | `version` works; fx10 reports `D-TF-HCL-UNAVAILABLE` and still scans JSON inputs | Pass |
| Clean install (sdist) | The sdist builds and installs | Fresh venv install from the final sdist; `version` and an fx01 scenario scan exit 0 | Pass |
| Clean-install determinism | Repeated install-run artifacts are byte-identical | Two fx07 scans from the installed wheel produced identical JSON, SARIF and HTML digests | Pass |
| Dependency audit | No known advisories in locked sets | pip-audit 2.10.1 on the runtime lock: no known vulnerabilities; OSV-Scanner 2.7.0: no issues across 60 package instances; Grype 0.121.0 on the dev lock and dependency SBOM: 0 matches | Pass |
| Dependency age and yanks | Minimum 14-day release age; no yanked pins | 42 unique pins, minimum age 15 days, 0 yanked, 0 violations on 2026-10-27; locks unchanged since 0.1.0 | Pass |
| License inventory | Permissive or documented weak copyleft only | 41 locked packages: MIT 27, Apache-2.0 family 6, BSD 4, ISC 1, MPL-2.0 2, PSF-2.0 1; no GPL/AGPL/SSPL/proprietary. Embedded Geist fonts are OFL-1.1 with the licence text shipped in the wheel | Pass |
| Secret scans | No credential values in tracked history, tree or artifacts | gitleaks 8.30.1 and TruffleHog 3.99.7 on the committed 0.1.1 tree and history; results are appended after the release commit | Pending commit |
| Real-world corpus | Ten public repositories, including workflows and Terraform | 0 failures; 1,959 files, 163 workflow files, 101 Terraform files; 21 all-mutable-actions scenarios exactly matching 21 rank rows; 37 findings, 1,149 nodes, 2,181 edges, 451 diagnostics; max scan 1.92 s, max rank 1.82 s, max export 1.87 s | Pass (sample) |
| Adversarial soak | Hostile and boundary inputs terminate within documented exit codes | 16 cases, 0 failures; hostile YAML, traversal, Terraform JSON/plan/HCL, 80-finding repository, bad config and CLI negatives all handled without traceback | Pass (sample) |
| CI policy | Actions pinned to full SHAs; read-only token; locks used; no credential persistence | 12 policy tests pass; SHA pinning enforced by repository setting; checkout steps set `persist-credentials: false`; workflows are read-only and never use `pull_request_target` | Pass |
| Advisory automation | Both locks and secrets scanned on a schedule | `audit.yml` runs on push, pull request and weekly cron; pip-audit on both locks, Bandit, hash-verified OSV-Scanner 2.7.0 and gitleaks 8.30.1; run 40429850149 passed | Pass |
| CLI exit codes | 0, 1, 2, 3 and 4 observed | 0 success and `--fail-on never`; 1 on `--fail-on critical`; 2 for bad selector/format/path/config; 3 for strict partial results; 4 covered by CLI tests | Pass |
| HTML structure and accessibility | Language, title, headings, labels, skip link, table semantics, graph text alternative, no-script fallback | Static tests pass (24 report tests); CSP, escaping and inert-hostile-string tests pass; axe-core 4.10.3 reports 0 WCAG 2.2 AA violations on desktop dark, desktop light and mobile dark; the boot gate clears after hydration and the no-script override keeps the document visible | Pass |
| Browser QA | Offline rendering, fonts, interactions, external requests | Headless Chrome at 1440×900, 768×1024 and 390×844: 0 overflow, 0 console/log errors, 0 external requests; both fonts loaded and Geist in use; scenario switching, graph zoom/fit, trace, table scroll and filters exercised | Pass |
| Lighthouse | Performance, accessibility and best-practices budgets | 13.5.0 desktop profile: 98 / 100 / 100; FCP 0.9 s, LCP 0.9 s, TBT 10 ms, CLS 0. Simulated mobile: 65 / 100 / 100 because the 841 KiB single file is throttled to 1.6 Mbps; reported, not used as the offline UI budget | Pass (desktop); mobile result disclosed |
| HTML validation | Report markup validity | html-validate 11.17.0: clean | Pass |
| Design inspector | Layout, typography and density checks at 1440, 768 and 390 px | 0 findings | Pass |
| Documentation set | README, architecture, rules, assumptions, provenance, benchmark, limitations, release, security, audit, external audit package, contributing, changelog, NOTICE | Present; local-link, rule-coverage and assumption-registry tests pass | Pass |
| Three-build reproducibility | Repeated clean builds produce identical artifact digests | Three consecutive builds from the same unmodified tree produced identical SHA-256 digests for both the wheel and the sdist; cross-machine and cross-toolchain byte reproducibility is not claimed | Pass (local) |
| Remote CI execution | The defined matrix runs green on GitHub-hosted runners | Run 40432137207: package job and all six test jobs passed | Pass |
| Linux execution | The suite runs on Linux | Ubuntu jobs for Python 3.12, 3.13 and 3.14 passed, including the symlink security test and the performance tests | Pass |
| Internal security audit | Manual review and third-party automated scanners | Completed 2026-10-27; no high/critical finding open; report in `docs/security-audit.md` | Pass (internal) |
| Repository security settings | Least-privilege automation and protected main branch | Workflow token read-only; SHA pinning required; Dependabot alerts and security updates enabled; `protect-main` ruleset blocks deletion and non-fast-forward pushes | Pass |
| Independent audit | External human security review | None performed and none claimed; package prepared in `docs/external-audit-package.md` | Not claimed |
| Publication (0.1.0) | GitHub Release with wheel, sdist and SHA-256 sums | `v0.1.0` published 2026-10-27 from commit `0269100`; all three assets were re-downloaded and verified against `SHA256SUMS`; no package-index upload, deployment or SaaS | Published |
| Publication (0.1.1) | GitHub Release with wheel, sdist and SHA-256 sums | Authorized for the private repository; the release is created from the verified commit after the recorded local gates and a green remote CI run, then the assets are re-downloaded and checked against `SHA256SUMS` | Pending final step |

## Open gates and limitations

1. **Independent audit.** No external human reviewer has assessed the project. This is
   disclosed in every readiness claim and is the main residual assurance gap. The
   external audit package defines the target, materials and focus areas.
2. **GitHub Advanced Security features.** Secret scanning and CodeQL are unavailable on
   this private repository without Advanced Security. Gitleaks, TruffleHog, OSV,
   pip-audit, Bandit and Semgrep provide compensating coverage locally and in the
   advisory workflow.
3. **Cross-machine reproducibility.** Three builds on one toolchain are identical.
   Independent rebuilds on other machines are not claimed.
4. **Platform coverage.** Runtime testing covers Windows 11 and Ubuntu GitHub runners.
   Other platforms are untested.

The browser/axe pass, three-build comparison, corpus and soak are single-environment
observations. They are not external benchmarks and not an independent audit.

## Release decision

The maintainer authorized publication as GitHub Release assets. Version `0.1.0` was
published on 2026-10-27 from commit `0269100`. Version `0.1.1` is prepared from the
verified release commit; after a green remote CI run the annotated tag `v0.1.1`, wheel,
sdist and `SHA256SUMS` are published, and the downloaded assets are checked against the
sums. Any later source or artifact change requires a fresh gate run before it can be
described as released. Every statement must keep the distinction between internal
verification and independent audit. The tool's own analysis is evidence-honest by
design: it reports potential authority, conditional survival and rotation order. This
readiness document makes the same distinction about the project itself. Local and CI
tests demonstrate behaviour on the recorded environments; they do not prove the absence
of defects or constitute an independent security audit.
