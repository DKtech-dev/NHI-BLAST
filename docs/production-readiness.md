# Production readiness

**Verdict: RELEASED for the authorized GitHub Releases distribution scope.** Every
automated and internal gate below passed on the recorded environments, including the
remote CI matrix on Linux and Windows. Version 0.1.1 was published on 2026-10-27 as
https://github.com/DKtech-dev/nhi-blast/releases/tag/v0.1.1 from commit `c702d9d`; all
three assets were re-downloaded and verified against `SHA256SUMS`. Version 0.1.0
remains available at https://github.com/DKtech-dev/nhi-blast/releases/tag/v0.1.0. No
package-index upload, deployment or SaaS was performed. The independent human security
audit has not been performed and is not claimed; it remains the one open assurance gate
and is disclosed in `docs/security-audit.md` and `docs/external-audit-package.md`.

The source line is version 0.2.0 under the MIT License and is a public beta. The 0.2.0
beta was published on 2026-10-30 as a GitHub pre-release at
https://github.com/DKtech-dev/nhi-blast/releases/tag/v0.2.0 from commit `41d08a8`. This
page's release verdict applies to `0.1.1` and the 0.2.0 pre-release distribution only;
it is not a production-readiness claim for 0.2.0. Versions `0.1.0` and `0.1.1` remain
the published GitHub Releases under the MIT License they were distributed with. The
0.2.0 beta's verification results and published artifact are recorded below and in the
release notes; no independent audit has been performed for any version.

This page is the release-gate record. It states what was actually executed on the
recorded environments and what remains open. The audit is in
`docs/security-audit.md`.

## Environment

| Item | Value |
| --- | --- |
| Date of the recorded gates | 2026-10-27 for the published 0.1.1 gates; 2026-10-30 for the 0.2.0 beta gates, the Windows build and the `v0.2.0` pre-release |
| Local OS | Windows 11 (10.0.26200), x64 |
| Remote OS and Python | GitHub Actions `ubuntu-latest` and `windows-latest`; CPython 3.12, 3.13 and 3.14 |
| Local Python | CPython 3.12.14 primary; 3.13.17 and 3.14.7 in isolated environments |
| Machine | 12th Gen Intel Core i5-12450H, 15.7 GiB RAM, local SSD |
| Repository | `DKtech-dev/nhi-blast`, public since 2026-10-27, branch `main`; the 0.2.0 beta gates were run on branch `cleanup`, merged through PR #4 and released from `main` at `41d08a8` |
| Runtime dependencies | `requirements.lock` exact versions |
| Development dependencies | `requirements-dev.lock` exact versions |
| Distribution published | `nhi_blast-0.1.1-py3-none-any.whl` and `nhi_blast-0.1.1.tar.gz`; SHA-256 values are in the release's `SHA256SUMS` asset, not embedded here because this document is packaged in the sdist. The 0.2.0 beta is published as the GitHub pre-release `v0.2.0` with five assets: `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.md`, `nhi-blast-windows-x64.exe` and `nhi-blast-windows-x64.exe.sha256`; no wheel or sdist is published for 0.2.0 and no package index is used |
| Beta executable | PyInstaller 6.22.3 one-file console executable for Windows x64, unsigned; built by `build-windows` run 40993757326 from commit `41d08a8`, published as 20,749,434 bytes with SHA-256 `fe8fd0e129af7ed2353d53189cf4730a03cfcc0019f86f871b03c6a4625c9350`, and re-downloaded and verified after publication |
| UI tooling | Headless Chrome through CDP; axe-core 4.10.3; Lighthouse 13.5.0 (desktop and simulated mobile profiles); html-validate 11.17.0; design inspector at 1440, 768 and 390 px |

## Remote CI evidence

| Workflow | Run | Result |
| --- | --- | --- |
| CI 0.1.1 (`ci.yml`) | https://github.com/DKtech-dev/nhi-blast/actions/runs/40509205221 | Package job passed; all six test jobs passed with `417 passed, 2 deselected` plus `2 passed` for the slow suite, 0 skipped, and coverage 86.73–86.74% on Ubuntu and Windows, Python 3.12–3.14 |
| Advisory audit 0.1.1 (`audit.yml`) | https://github.com/DKtech-dev/nhi-blast/actions/runs/40509205137 | Passed: runtime and development lock audits, Bandit, OSV-Scanner and the secret scan |
| CI 0.2.0 source, public repository (`ci.yml`) | https://github.com/DKtech-dev/nhi-blast/actions/runs/40515346396 | Package job passed; all six test jobs passed with `420 passed` each on Ubuntu and Windows, Python 3.12–3.14, coverage 86.73–86.74%, plus `2 passed` for the slow suite in each job |
| Advisory audit 0.2.0 source (`audit.yml`) | https://github.com/DKtech-dev/nhi-blast/actions/runs/40515346468 | Passed: both lock audits, Bandit, OSV-Scanner and the secret scan |
| CI 0.2.0 final beta tree, PR #4 (`ci.yml`) | https://github.com/DKtech-dev/nhi-blast/actions/runs/40993460388 | All required checks passed on head `7f7bea4`: package job and six test jobs on Ubuntu and Windows, Python 3.12–3.14; merged to `main` as `41d08a8` |
| Advisory audit 0.2.0 final beta tree, PR #4 (`audit.yml`) | https://github.com/DKtech-dev/nhi-blast/actions/runs/40993460275 | Passed alongside the PR's CodeQL checks |
| Windows build 0.2.0 (`build-windows.yml`) | https://github.com/DKtech-dev/nhi-blast/actions/runs/40993757326 | Passed on `main` at `41d08a8`; produced the executable and checksum published in the `v0.2.0` pre-release |
| CodeQL default setup | https://github.com/DKtech-dev/nhi-blast/actions/runs/40515346395 | Analyze (actions) and Analyze (python) passed; 0 results and 0 open alerts |
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
| Specification implementation | M0–M7 pipeline and CLI complete | Implemented and exercised end to end; see `docs/SPEC.md` and the test suite | Pass |
| Full test suite (local) | All tests pass; warnings are errors | 418 passed, 1 skipped in 23.23 s (the skip is the real-symlink case described below) | Pass |
| Full test suite (remote) | Linux and Windows, Python 3.12–3.14 | 0.1.1 run 40509205221: every test job reported `417 passed, 2 deselected` plus `2 passed` for the slow suite and 0 skipped; coverage 86.73% (86.74% on Ubuntu 3.14); package job passed | Pass |
| Python 3.13 suite | Same suite on CPython 3.13 | Local 3.13.17: 416 passed, 1 skipped, 2 deselected plus 2 slow passed; remote 0.1.1 job passed | Pass |
| Python 3.14 suite | Same suite on CPython 3.14 | Local 3.14.7: 416 passed, 1 skipped, 2 deselected plus 2 slow passed; remote 0.1.1 job passed | Pass |
| Adversarial suite | Security-marked hostile-input tests pass | 37 passed, 1 skipped locally (real symlink creation requires a Windows privilege); the Linux CI job executes the skipped case | Pass |
| Golden output | Reviewed fx07 console and semantic summary | 2 passed | Pass |
| Performance | SPEC 12.8 budgets | 2 passed in 9.22 s; previously measured graph build + scenario 1.568 s (budget 5 s), rank 6.285 s (budget 60 s) on the documented 200-workflow/2,000-resource fixture | Pass |
| Coverage | ≥80% overall; ≥80% in `aws/`, `analysis/`, `report/` | Local 86.67% overall line coverage with the two slow tests deselected under instrumentation; remote full-suite coverage 86.73% (86.74% on Ubuntu 3.14); 89.47% statements, 78.87% branches; every enforced module ≥80%; `report/html.py` and `report/ui.py` at 100% | Pass |
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
| Secret scans | No credential values in tracked history, tree or artifacts | gitleaks 8.30.1: 9 commits and 2.32 MB of history scanned, no leaks. TruffleHog 3.99.7: 460 chunks and 2,320,652 bytes scanned without verification, 0 verified and 0 unverified secrets. Both cover the 0.1.1 release commit; the advisory workflow repeats gitleaks on every push | Pass |
| Real-world corpus | Ten public repositories, including workflows and Terraform | 0 failures; 1,959 files, 163 workflow files, 101 Terraform files; 21 all-mutable-actions scenarios exactly matching 21 rank rows; 37 findings, 1,149 nodes, 2,181 edges, 451 diagnostics; max scan 1.92 s, max rank 1.82 s, max export 1.87 s | Pass (sample) |
| Adversarial soak | Hostile and boundary inputs terminate within documented exit codes | 16 cases, 0 failures; hostile YAML, traversal, Terraform JSON/plan/HCL, 80-finding repository, bad config and CLI negatives all handled without traceback | Pass (sample) |
| CI policy | Actions pinned to full SHAs; read-only token; locks used; no credential persistence | 12 policy tests pass; SHA pinning enforced by repository setting; checkout steps set `persist-credentials: false`; workflows are read-only and never use `pull_request_target` | Pass |
| Advisory automation | Both locks and secrets scanned on a schedule | `audit.yml` runs on push, pull request and weekly cron; pip-audit on both locks, Bandit, hash-verified OSV-Scanner 2.7.0 and gitleaks 8.30.1; 0.1.1 run 40509205137 passed | Pass |
| CLI exit codes | 0, 1, 2, 3 and 4 observed | 0 success and `--fail-on never`; 1 on `--fail-on critical`; 2 for bad selector/format/path/config; 3 for strict partial results; 4 covered by CLI tests | Pass |
| HTML structure and accessibility | Language, title, headings, labels, skip link, table semantics, graph text alternative, no-script fallback | Static tests pass (24 report tests); CSP, escaping and inert-hostile-string tests pass; axe-core 4.10.3 reports 0 WCAG 2.2 AA violations on desktop dark, desktop light and mobile dark; the boot gate clears after hydration and the no-script override keeps the document visible | Pass |
| Browser QA | Offline rendering, fonts, interactions, external requests | Headless Chrome at 1440×900, 768×1024 and 390×844: 0 overflow, 0 console/log errors, 0 external requests; both fonts loaded and Geist in use; scenario switching, graph zoom/fit, trace, table scroll and filters exercised | Pass |
| Lighthouse | Performance, accessibility and best-practices budgets | 13.5.0 desktop profile: 98 / 100 / 100; FCP 0.9 s, LCP 0.9 s, TBT 10 ms, CLS 0. Simulated mobile: 65 / 100 / 100 because the 841 KiB single file is throttled to 1.6 Mbps; reported, not used as the offline UI budget | Pass (desktop); mobile result disclosed |
| HTML validation | Report markup validity | html-validate 11.17.0: clean | Pass |
| Design inspector | Layout, typography and density checks at 1440, 768 and 390 px | 0 findings | Pass |
| Documentation set | README, architecture, rules, assumptions, provenance, benchmark, limitations, release, security, audit, external audit package, contributing, changelog, NOTICE | Present; local-link, rule-coverage and assumption-registry tests pass | Pass |
| Three-build reproducibility | Repeated clean builds produce identical artifact digests | Three consecutive builds from the same unmodified tree produced identical SHA-256 digests for both the wheel and the sdist; cross-machine and cross-toolchain byte reproducibility is not claimed | Pass (local) |
| Remote CI execution | The defined matrix runs green on GitHub-hosted runners | 0.1.1 run 40509205221: package job and all six test jobs passed | Pass |
| Linux execution | The suite runs on Linux | 0.1.1 Ubuntu jobs for Python 3.12, 3.13 and 3.14 passed, including the symlink security test and the performance tests | Pass |
| Internal security audit | Manual review and third-party automated scanners | Completed 2026-10-27; no high/critical finding open; report in `docs/security-audit.md` | Pass (internal) |
| Repository security settings | Least-privilege automation, protected main branch and platform security features | Workflow token read-only; SHA pinning required; Dependabot alerts and security updates enabled; `protect-main` ruleset blocks deletion and non-fast-forward pushes; secret scanning and push protection enabled with 0 open alerts; CodeQL default setup configured with 0 open alerts; private vulnerability reporting enabled | Pass |
| Visibility and licensing | Public repository; MIT licence for this source line; published releases keep their original terms | The repository is public; package metadata reports `License-Expression: MIT` and ships `LICENSE`, `NOTICE` and `THIRD_PARTY_NOTICES.md`; the `v0.1.0` and `v0.1.1` assets are unchanged and remain MIT | Pass |
| Independent audit | External human security review | None performed and none claimed; package prepared in `docs/external-audit-package.md` | Not claimed |
| Publication (0.1.0) | GitHub Release with wheel, sdist and SHA-256 sums | `v0.1.0` published 2026-10-27 from commit `0269100`; all three assets were re-downloaded and verified against `SHA256SUMS`; no package-index upload, deployment or SaaS | Published |
| Publication (0.1.1) | GitHub Release with wheel, sdist and SHA-256 sums | `v0.1.1` published 2026-10-27 from commit `c702d9d` after green CI run 40509205221 and audit run 40509205137; the wheel, sdist and `SHA256SUMS` were re-downloaded and all checksums verified | Published |
| Publication (0.2.0) | GitHub pre-release with the Windows executable, checksum, licence and notices | `v0.2.0` published 2026-10-30 as a pre-release from commit `41d08a8` after PR #4's required checks and `build-windows` run 40993757326 succeeded; five assets: `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.md`, `nhi-blast-windows-x64.exe`, `nhi-blast-windows-x64.exe.sha256`; published executable 20,749,434 bytes, SHA-256 `fe8fd0e129af7ed2353d53189cf4730a03cfcc0019f86f871b03c6a4625c9350`; no wheel, sdist or package-index upload | Published |

## 0.2.0 public beta verification (2026-10-30)

These gates were run on branch `cleanup` in the recorded Windows environment. They
support the beta pre-release only; they are not a production-readiness or audit
conclusion for 0.2.0.

| Gate | Command | Result |
| --- | --- | --- |
| Lint | `python -m ruff check src tests scripts` | All checks passed |
| Format | `python -m ruff format --check src tests scripts` | 136 files already formatted |
| Types | `python -m mypy src` | Success, no issues in 75 source files |
| Report schema | `python scripts/gen_schema.py --check` | Exit 0 |
| Full suite | `python -m pytest` | 805 passed, 10 skipped in 73.41 s. Eight skips are the Windows-executable tests, which ran separately with `NHI_BLAST_WINDOWS_EXE` against the built binary: 8 passed in 96.69 s. Two skips are real-symlink cases blocked by the local Windows privilege; Linux CI executes the symlink case |
| Adversarial suite | `python -m pytest -m security` | 209 passed, 1 skipped (the same symlink-privilege case) |
| Golden output | `python -m pytest -m golden` | 2 passed |
| Performance | `python -m pytest -m slow` | 2 passed in 12.17 s |
| Coverage | `python scripts/check_coverage.py` | 803 passed, 10 skipped, 2 deselected; 88.76% overall line coverage (minimum 80%); every enforced package at or above 80% |
| Wheel | Hatchling build plus `python scripts/check_artifacts.py` | 98 files; `License-Expression: MIT` with `LICENSE`, `NOTICE` and `THIRD_PARTY_NOTICES.md`; notices name every frozen package; checker passed |
| Sdist | Hatchling build plus `python scripts/check_artifacts.py` | 289 files; the same licence expression and files; checker passed |
| Windows executable (local pre-publication build, historical) | PyInstaller build, `Get-FileHash`, `check_artifacts.py --windows-exe` | 20,240,054 bytes; SHA-256 `b718517912473d31878cd3f243c14fe9bf070bb825ebe26a3fccabd9c78a32e5`, matched independently with PowerShell `Get-FileHash`; artifact checker passed including embedded notices and the secret scan; the executable is unsigned and no SmartScreen reputation is claimed. This is the earlier local build, not the published CI artifact |
| Published Windows executable (CI) | `build-windows` run 40993757326 on `main` at `41d08a8`; downloaded release asset; PowerShell `Get-FileHash`; `check_artifacts.py --windows-exe`; `pytest tests/test_windows_executable.py` | 20,749,434 bytes; SHA-256 `fe8fd0e129af7ed2353d53189cf4730a03cfcc0019f86f871b03c6a4625c9350`; the download matched the published `.sha256` record and GitHub's computed digest; artifact checker passed; 8 executable tests passed against the downloaded binary; the executable is unsigned |
| GitHub pre-release | GitHub REST API and downloaded assets | `v0.2.0` is a pre-release (draft false) targeting commit `41d08a8`; five assets: `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.md`, `nhi-blast-windows-x64.exe`, `nhi-blast-windows-x64.exe.sha256`; all five were re-downloaded and verified |
| Executable outside the repository | `pytest tests/test_windows_executable.py` with the built binary | A standalone copy in a temporary directory with spaces, a clean environment and no Python on `PATH` ran `--help`, `version`, `version --data`, `schema`, `scan` in JSON/SARIF/HTML, `rank`, `export`, `explain` and the HCL fallback; exit codes and artifacts matched the installed CLI, and no proxy-mediated network request was observed |
| Remote CI | PR #4 required checks and the manual Windows workflow | PR #4 (https://github.com/DKtech-dev/nhi-blast/pull/4) passed its required checks on head `7f7bea4` (CI 40993460388, audit 40993460275, CodeQL) and merged to `main` as `41d08a8`; `build-windows` run 40993757326 then passed on `main` at `41d08a8` |

The 0.2.0 beta was published on 2026-10-30 as a GitHub pre-release at
https://github.com/DKtech-dev/nhi-blast/releases/tag/v0.2.0, targeting commit
`41d08a8`. The source was merged through
https://github.com/DKtech-dev/nhi-blast/pull/4 after its required checks passed, and
the executable was produced by the manual `build-windows` workflow at
https://github.com/DKtech-dev/nhi-blast/actions/runs/40993757326 on `main` at
`41d08a8`. Five assets are attached: `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.md`,
`nhi-blast-windows-x64.exe` and `nhi-blast-windows-x64.exe.sha256`. The downloaded
executable matched its published checksum record, passed the artifact checker and
passed the executable tests outside the repository. No wheel, sdist, package-index
upload or deployment is part of the 0.2.0 beta, and the executable is unsigned. The
release notes are `docs/release-notes-0.2.0.md`.

## Open gates and limitations

1. **Independent audit.** No external human reviewer has assessed the project. This is
   disclosed in every readiness claim and is the main residual assurance gap. The
   external audit package defines the target, materials and focus areas.
2. **Platform security features.** The repository is public and now has GitHub secret
   scanning with push protection and CodeQL default setup. Validity checks and
   non-provider secret patterns remain disabled at the account level, so they are not
   claimed. Gitleaks, TruffleHog, OSV, pip-audit, Bandit and Semgrep continue to
   provide compensating coverage locally and in the advisory workflow.
3. **Forking.** GitHub does not allow a public repository to prevent forking. Under the
   MIT License forks are permitted; redistributions must retain the copyright and
   permission notice.
4. **Cross-machine reproducibility.** Three builds on one toolchain are identical.
   Independent rebuilds on other machines are not claimed.
5. **Platform coverage.** Runtime testing covers Windows 11 and Ubuntu GitHub runners.
   Other platforms are untested. The Windows executable is built only for Windows x64.
6. **Unsigned binary.** The Windows executable carries no code-signing certificate.
   Windows SmartScreen or antivirus products may warn about an unknown publisher. No
   reputation, signing identity or absence of warnings is claimed, and the release notes
   and `docs/beta-testing.md` disclose this.
7. **Beta assurance.** The 0.2.0 beta has local and remote automated verification but no
   independent audit and no production-readiness conclusion. Testers must use synthetic
   fixtures or repositories they are authorised to test.

The browser/axe pass, three-build comparison, corpus and soak are single-environment
observations. They are not external benchmarks and not an independent audit.

## Release decision

The maintainer authorized publication as GitHub Release assets. Version `0.1.0` was
published on 2026-10-27 from commit `0269100`; version `0.1.1` was published the same
day from commit `c702d9d` with the annotated tag `v0.1.1`. The wheel, sdist and
`SHA256SUMS` were downloaded again after publication and verified. Any later source or
artifact change requires a fresh gate run before it can be described as released. The
repository was made public on 2026-10-27. The current 0.2.0 source line is MIT and is a
public beta; that does not alter the published 0.1.0 and 0.1.1 releases, which remain
under the MIT License. No production-readiness or independent-audit conclusion is made
for the 0.2.0 beta.

Version 0.2.0 was published on 2026-10-30 as the GitHub pre-release `v0.2.0` at
https://github.com/DKtech-dev/nhi-blast/releases/tag/v0.2.0, targeting commit
`41d08a8`. The published executable is 20,749,434 bytes with SHA-256
`fe8fd0e129af7ed2353d53189cf4730a03cfcc0019f86f871b03c6a4625c9350`; it was downloaded
after publication and matched the published `.sha256` record, passed the artifact
checker and passed the executable tests outside the repository. The earlier local
build (20,240,054 bytes, SHA-256
`b718517912473d31878cd3f243c14fe9bf070bb825ebe26a3fccabd9c78a32e5`) is recorded above
as a historical local-build result only and is not the published artifact. No wheel,
sdist, package-index upload or deployment is part of the 0.2.0 beta; the executable is
unsigned, and no production-readiness or independent-audit conclusion is made for
0.2.0.

Every statement must keep the distinction between internal verification and independent
audit. The tool's own analysis is evidence-honest by
design: it reports potential authority, conditional survival and rotation order. This
readiness document makes the same distinction about the project itself. Local and CI
tests demonstrate behaviour on the recorded environments; they do not prove the absence
of defects or constitute an independent security audit.
