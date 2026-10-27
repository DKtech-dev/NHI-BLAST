# Internal security audit

**Status: internal audit completed on 2026-10-27. This is not an independent audit.**
It was performed by the implementation agent using manual review and third-party
automated scanners. No external human reviewer has assessed this codebase, and no
independent audit is claimed. The package prepared for such a review is
`docs/external-audit-package.md`.

This report covers the source tree that became release `v0.1.0` in the private
repository `DKtech-dev/nhi-blast`. It records what was executed, what was found, and
what remains unverified. It is written to the same evidence standard the tool applies
to its own reports: absence of a finding is not proof of absence.

## 1. Scope

In scope:

- Parsing of hostile repository input: GitHub Actions YAML, composite actions,
  Terraform plan/state JSON, Terraform JSON configuration, best-effort HCL and IAM
  policy documents.
- Path discovery and containment, resource limits and diagnostics.
- OIDC/trust evaluation, graph construction, reachability, R/E/Z partitioning,
  rotation planning and finding generation.
- Console, JSON, SARIF and single-file HTML reporters, including the embedded report
  script and CSP.
- CLI behaviour, exit codes and configuration handling.
- Packaging, lock files, built artifacts and release automation.
- CI workflows, action pinning, token permissions and advisory automation.

Out of scope:

- Live GitHub, AWS, Terraform or cloud state; the tool never contacts them.
- Correctness of the analysed repository's real-world permissions.
- GitHub platform security, runner image integrity and GitHub-hosted infrastructure.
- Maintainer workstation and account security beyond the release settings recorded in
  section 7.
- Independent human review and formal verification.

## 2. Threat model

The scanned repository is treated as hostile. The properties an attacker must not be
able to break, derived from `docs/SPEC.md` section 2.5 and `AGENTS.md` section 5, are:

| Property | Failure mode being defended against |
| --- | --- |
| No execution | A crafted workflow, action, Terraform file or expression causes the tool to run code or shell commands |
| No network at analysis time | A parsed value causes an outbound request, beacon or credential verification attempt |
| Path containment | Traversal, symlinks or Windows junctions read files outside the scan root |
| No secret values | Credential literals are retained or emitted in console, JSON, SARIF, HTML, diagnostics or logs |
| Inert hostile strings | A label or path injects markup, script, event handlers or escapes the embedded JSON block |
| Bounded processing | Alias expansion, nesting, oversized files or pathological graphs exhaust memory, stack or CPU |
| Evidence honesty | UNKNOWN authority silently contributes to R, E or Z, or severity is presented as proof |
| Supply chain | A dependency, build tool or CI action is compromised, unpinned or outdated |
| Release integrity | Artifacts are modified after verification, or CI credentials leak into the workspace |

## 3. Controls verified

| Control | Mechanism | Verification |
| --- | --- | --- |
| No execution of scanned content | No `subprocess`, `os.system`, `os.popen`, `eval` or `exec` call exists in `src/nhi_blast`; Terraform and HCL are parsed, never invoked | Static search of `src`; `tests/test_security.py`; runtime contains no process-spawning code |
| No network at analysis time | No `socket`, `urllib.request`, `http.client`, `requests` or `httpx` import in `src`; only `urllib.parse` is used for quoting and URL splitting | Static search; `tests/test_determinism.py`; HTML browser run recorded zero external requests |
| Path containment | Every read resolves inside the scan root; symlinks and junctions are checked before content classification; escaping links are diagnosed and skipped | `tests/test_pipeline.py` outside-root arguments; `tests/test_security.py` traversal, symlink and junction cases |
| Safe YAML | `yaml.compose` plus `SafeLoader`; duplicate keys detected; only the first document read; node, depth and alias limits fail closed | `tests/test_security.py` and `tests/test_workflows.py` |
| Resource limits | Byte, file-count, YAML node/depth/alias, graph-node, closure-depth and time budgets from `core/limits.py` | `tests/test_security.py` boundary cases; performance and slow tests |
| No secret values | Literal credentials are represented as kind plus length; Terraform sensitive leaves are skipped; renderers never receive values | `tests/test_report_security.py` proves a synthetic token is absent from JSON, console, SARIF and HTML while the finding remains; corpus artifact audit |
| Inert hostile strings | HTML data is escaped as Unicode escapes inside `application/json`; DOM built with `textContent` and `setAttribute`; restrictive CSP with inline hashes; vendored assets recorded in `MANIFEST.json` | `tests/test_report_security.py`, `tests/test_html_security.py`, browser and axe runs |
| Deterministic output | Sorted traversal, stable identifiers and no wall-clock content unless requested | `tests/test_determinism.py`; corpus byte-comparison; three-build digest comparison |
| Claim hygiene | Report templates contain no proof, guarantee, exploitability or takeover assertion; the HTML footer states evidence is not proof of exploitation | `tests/test_report_security.py::test_report_templates_do_not_assert_claims`; `tests/test_docs.py` |
| Evidence honesty | Weakest-class edge confidence; UNKNOWN excluded from R/E/Z and reported as potential | `tests/test_solver.py`, `tests/test_trust.py`, `tests/test_reach.py`, `tests/test_partition.py` |
| Assumption registry | Every `A-*`/`H-*` entry has an ID, kind, statement, verify flag and impact, and is documented | `tests/test_docs.py::test_assumption_registry_matches_its_documentation` |
| CI least privilege | `permissions: contents: read`; no `pull_request_target`; checkout does not persist credentials; default workflow token is read-only | `tests/test_ci_pins.py`; repository settings in section 7 |
| Supply chain | Runtime and development pins; hash-locked audit tooling; actions pinned to full commit SHAs; SHA pinning enforced by repository policy; 14-day minimum release age | `tests/test_ci_pins.py`; dependency-age audit below |
| Release integrity | Artifact allowlist checker; SHA-256 sums; secret scan of source history and artifacts; three-build comparison | `scripts/check_artifacts.py`; `dist/SHA256SUMS`; sections 5 and 6 |

Runtime dependencies are limited to PyYAML, Pydantic, NetworkX, Typer/Click, rich and
python-hcl2 (optional). The tool does not use a database, a web server, a browser
engine or a network client at runtime.

## 4. Findings

No high or critical security defect was identified by manual review or by the
automated scanners. The findings below were found and resolved during the audit; none
was closed by weakening a test, and each fix has a regression test where the behaviour
is testable.

| ID | Severity | Finding | Resolution | Status |
| --- | --- | --- | --- | --- |
| AUD-01 | Medium | Both CI workflows used `actions/checkout` with default credential persistence, leaving `GITHUB_TOKEN` in the workspace `.git/config` (zizmor `artipacked`) | Added `persist-credentials: false` to all three checkout steps and a policy test that enforces it | Fixed |
| AUD-02 | Low | The audit workflow invoked `python -m pip-audit`, which is not an importable module, so advisory scanning failed instead of running | Changed to `python -m pip_audit` and added a policy test that rejects the broken form | Fixed |
| AUD-03 | Low | `tomlkit==0.15.2` was 10 days old, violating the project's 14-day minimum release-age policy | Held `tomlkit` at `0.15.1` (101 days old), rebuilt artifacts and re-ran all dependency gates | Fixed |
| AUD-04 | Low | Fixture `.git` identity files cannot be tracked by Git, so a clean checkout scanned a different repository identity and produced different results | Recreated the reviewed identity from `tests/conftest.py` and added a per-fixture regression test | Fixed |
| AUD-05 | Informational | The installed-console-script test assumed a POSIX script layout and failed on Windows runners | Resolve the script through `sysconfig.get_path("scripts")` | Fixed |
| AUD-06 | Informational | CPython 3.14 accepts deeper JSON nesting than earlier versions, so the deep-nesting test expected the wrong diagnostic | The test now accepts the parse or format diagnostic while still requiring `facts is None`; no safety assertion was relaxed | Fixed |
| AUD-07 | Informational | `--no-build-isolation` skipped installation of the editable build helper, breaking the CI install | Install pinned `hatchling` and `editables` first; the editable install and coverage measurement are restored | Fixed |

Triage of scanner output that did not become findings:

| Tool | Output | Triage |
| --- | --- | --- |
| Semgrep | 2 × `python37-compatibility-importlib2` on `importlib.resources` imports | False positive: the package requires Python 3.12 or newer; the rule targets Python 3.7 compatibility |
| Bandit | 10 × B105 "hardcoded password" on credential-kind enum names such as `GITHUB_TOKEN` and `DATABASE_PASSWORD` | False positive: these are type names, not credential values; no value is stored |
| Bandit | 1 × B101 `assert` in the Terraform JSON parser | Reviewed: the assertion documents a helper contract (`document is None` implies a diagnostic); it does not validate untrusted input and is not the only failure path |
| Gitleaks | 6 × `generic-api-key` in `docs/research/_cache/*.raw` | False positives in the gitignored, unpublished primary-source cache: AWS documentation examples of `BinaryEquals` keys and an example access-key ID. The tracked history and a clean tree export scan clean |
| zizmor | "2 suppressed" in an otherwise clean report | The repository has no zizmor configuration or ignore annotations; no project-level suppression was introduced |

## 5. Tool results

All commands were run on Windows 11 (10.0.26200, x64) on 2026-10-27 unless a GitHub
Actions run is cited. Tools were downloaded from their official release pages or
installed from the hash-locked audit requirements; versions are recorded so the
results can be reproduced or superseded.

| Check | Tool and version | Command / target | Result |
| --- | --- | --- | --- |
| Workflow static analysis | zizmor 1.31.1 | `zizmor --offline .github/workflows` | 0 findings (output: "No findings to report. Good job! (2 suppressed)") |
| Workflow syntax | actionlint 1.7.12 | `actionlint` at repository root | Exit 0, no diagnostics |
| SAST | Semgrep 1.182.1, `p/default` | `semgrep --config p/default --metrics=off src scripts` | 2 findings, both triaged false positives |
| Python SAST | Bandit 1.9.4 | `bandit -q -r src` (all severities) | 0 medium, 0 high; 11 low, all triaged |
| Python dependency advisories | pip-audit 2.10.1 | `pip-audit -r requirements.lock` and `-r requirements-dev.lock` | No known vulnerabilities in either set |
| OSV advisories | OSV-Scanner 2.7.0 | `osv-scanner scan source -r <copied locks>` | 18 runtime and 42 development package instances; "No issues found" |
| SBOM | syft 1.55.0 | CycloneDX JSON from each lock (copied as `requirements.txt`) | 18 runtime libraries; 41 development libraries |
| SBOM vulnerability match | Grype 0.121.0 | `grype sbom:<runtime|dev>.cdx.json` | No vulnerabilities found in either SBOM |
| License inventory | pip-licenses 5.5.5 | Development environment, 41 packages | MIT 27, Apache-2.0 family 6, BSD 4, ISC 1, MPL-2.0 2, PSF-2.0 1; no GPL, AGPL, SSPL or proprietary licenses |
| Release age and yanks | PyPI JSON API | 42 unique pins across both locks | Minimum age 15 days; 0 yanked; 0 policy violations |
| Secret scan (history) | gitleaks 8.30.1 | `gitleaks git . --redact --config .gitleaks.toml` | 5 commits, 0 leaks |
| Secret scan (tree) | gitleaks 8.30.1 | `gitleaks dir . --redact --config .gitleaks.toml` | 6 findings, all triaged false positives in the ignored research cache |
| Secret scan (independent) | TruffleHog 3.99.7 | `trufflehog filesystem C:/Cyber --no-verification` excluding `.venv`, `dist` and `.git` | 11,220 chunks / 96,290,905 bytes; 0 verified and 0 unverified secrets |
| Security tests | pytest | `pytest -q -m security` | 37 passed, 1 skipped (real symlink creation needs a Windows privilege; Linux CI runs it) |
| Full suite (local) | pytest | `pytest -q` | 403 passed, 1 skipped |
| Full suite (remote) | GitHub Actions | CI run on Ubuntu and Windows, Python 3.12–3.14 | 404 passed per job; package job passed |

The scan of the ignored research cache is intentionally reported rather than
suppressed: adding an allowlist entry for that directory would also hide a real
credential accidentally placed there. The authoritative checks for distributed
content are the tracked-history scan, the clean-export scan and the artifact scan.

## 6. Artifact and release verification

- The final wheel and sdist were built from the release commit and checked with
  `scripts/check_artifacts.py`, which enforces the file allowlist and excludes caches,
  scratch trees, the private research cache and local output.
- Three consecutive builds from the same tree and toolchain produced identical SHA-256
  digests. Cross-machine and cross-toolchain byte reproducibility is not claimed.
- `dist/SHA256SUMS` records the digests of the frozen wheel and sdist. The digests are
  not copied into a packaged document because the sdist contains this document.
- The extracted wheel and sdist contents were scanned for secret-shaped strings; no
  credential value from the test fixtures or the research cache is present.
- A clean environment installed the wheel with the runtime lock, and all six CLI
  commands, JSON/SARIF/HTML export and the HCL fixture were exercised; the sdist was
  installed and scanned in a second clean environment.

## 7. Repository settings

| Setting | State on 2026-10-27 |
| --- | --- |
| Visibility | Private |
| Default workflow token permissions | Read-only; pull-request approval disabled |
| Actions policy | All actions allowed, **SHA pinning required** |
| Dependabot alerts | Enabled |
| Dependabot security updates | Enabled |
| Branch ruleset `protect-main` | Active: deletion and non-fast-forward pushes blocked for `refs/heads/main` |
| Secret scanning | Unavailable: the API returns "Secret scanning is not available for this repository" for this private repository without GitHub Advanced Security |
| Code scanning | Not configured; CodeQL for private repositories requires GitHub Advanced Security |
| Two-factor authentication | Not verifiable through the authenticated API response; not claimed |

Secret scanning and code scanning being unavailable is a platform-plan limitation, not a
claim that the repository is free of secrets or flaws. Gitleaks, TruffleHog, OSV,
pip-audit, Bandit and Semgrep provide compensating coverage in local runs and in the
advisory workflow.

## 8. Residual risk

1. **No independent human audit.** This is the principal open assurance gap. The
   external audit package defines what such a review would receive.
2. **Static analysis cannot prove absence.** Tool results are time-stamped and depend
   on the rules and advisory databases available on the audit date.
3. **Scanner coverage differs by platform.** The local Windows environment cannot
   create real file symlinks without elevation, so one security test is skipped
   locally; the Linux CI job executes it. Windows directory junctions are always
   covered.
4. **No build provenance or signature.** Release authenticity rests on the GitHub
   account, TLS and published SHA-256 sums, not on a signed attestation or Sigstore
   bundle.
5. **Private-repository platform features are limited.** GitHub secret scanning and
   CodeQL are unavailable without Advanced Security, as recorded above.
6. **Third-party action trust.** CI actions are pinned to full commit SHAs and SHA
   pinning is enforced, but their upstream code was not independently reviewed.
7. **Model scope.** Findings describe potential authority from static inputs. They do
   not establish that a compromise occurred, that a credential was read, or that a
   role can be taken over. `docs/known-limitations.md` lists the unmodelled controls.

## 9. Conclusion

For the recorded environment and inputs, the audited source tree satisfies the
security properties in section 2, and the automated gates in
`docs/production-readiness.md` pass. This conclusion is limited to the evidence above.
It is an internal engineering conclusion, not an independent security certification,
and it must not be cited as one.
