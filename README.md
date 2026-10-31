<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/readme/banner-dark.png">
    <img src="assets/readme/banner-light.png" alt="NHI-Blast — which credentials survive the revocation?" width="100%">
  </picture>
</p>

<h1 align="center">NHI-Blast</h1>

<p align="center">
  <strong>Offline blast-radius analysis for non-human identity in CI.</strong><br>
  GitHub Actions, Terraform and IAM policy in. Reach, revocation survival and rotation order out —
  with no execution, no network and no credential values.
</p>

<p align="center">
  <a href="https://github.com/DKtech-dev/nhi-blast/actions/workflows/ci.yml"><img src="https://github.com/DKtech-dev/nhi-blast/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI status"></a>
  <img src="https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-a8201a?style=flat-square&amp;labelColor=111010" alt="Python 3.12, 3.13 and 3.14">
  <img src="https://img.shields.io/badge/licence-MIT-a8201a?style=flat-square&amp;labelColor=111010" alt="MIT licence">
  <img src="https://img.shields.io/badge/release-v0.2.0%20beta-a8201a?style=flat-square&amp;labelColor=111010" alt="v0.2.0 public beta">
</p>

<p align="center">
  <a href="#quickstart"><img src="https://img.shields.io/badge/Quickstart-Install-a8201a?style=for-the-badge&amp;labelColor=111010" alt="Quickstart"></a>
  <a href="#commands"><img src="https://img.shields.io/badge/Commands-Reference-a8201a?style=for-the-badge&amp;labelColor=111010" alt="Commands"></a>
  <a href="#the-offline-report"><img src="https://img.shields.io/badge/Report-Offline%20HTML-a8201a?style=for-the-badge&amp;labelColor=111010" alt="Offline report"></a>
  <a href="#documentation"><img src="https://img.shields.io/badge/Docs-Guides-a8201a?style=for-the-badge&amp;labelColor=111010" alt="Documentation"></a>
</p>

> [!IMPORTANT]
> Version 0.2.0 is a public beta for testing and evaluation, not a production security
> control. No independent security audit has been performed or is claimed.

## Why NHI-Blast

When a CI entrypoint is revoked — a mutable third-party action, a leaked secret, a repository
writer — some credentials end with the job, some expire on their own, and some survive. Working
that out by hand is slow, and live cloud calls are often unavailable during an incident. NHI-Blast
reconstructs the authority those files describe, offline, and answers three questions:

| | Question | What you get |
| --- | --- | --- |
| **01** | **Reach** | Which AWS roles, credential stores and credentials are potentially reachable? |
| **02** | **Revocation survival** | Which credentials end with the job (**R**), expire on their own (**E**) or survive (**Z**)? |
| **03** | **Rotation order** | In what order must survivors be rotated so none can re-read a fresh credential? |

It reads GitHub Actions workflows, local composites and reusable workflows, Terraform plan/state
JSON with an HCL fallback, and IAM policy JSON. Remote reusable workflows use the caller grant;
expressions are never evaluated.

## The offline report

<p align="center"><img src="assets/readme/report-dark.png" alt="Offline HTML report for the synthetic fx07-incident fixture, showing the summary and R/E/Z survival panel" width="100%"></p>

<p align="center"><sub>The offline HTML report for the synthetic <code>fx07-incident</code> fixture: summary, R/E/Z survival panel, rotation plan, findings and evidence detail.</sub></p>

<p align="center"><img src="assets/readme/report-graph-dark.png" alt="Authority graph from the same fx07-incident report, grouped by stage with evidence-coded edges and a highlighted entrypoint" width="100%"></p>

<p align="center"><sub>The same report's authority graph, grouped by authority stage; line style encodes evidence class and the selected entrypoint's reachable path is highlighted.</sub></p>

## Quickstart

Requires **Python 3.12+** (tested on 3.12, 3.13 and 3.14). Version 0.2.0 is a public beta,
available from this source tree and, for Windows, as a pre-release executable on
[GitHub Releases](https://github.com/DKtech-dev/nhi-blast/releases/tag/v0.2.0). No
package-index publication is made. The tool needs no cloud credentials and makes no network
requests.

```bash
python -m venv .venv
.venv/bin/python -m pip install ".[hcl]"
```

On Windows use `.venv\Scripts\python.exe`. `[hcl]` adds the optional Terraform HCL fallback and
`-c requirements.lock` pins exact versions; installation needs an index, but runs are offline.

### Windows executable

The standalone Windows x64 build, `nhi-blast-windows-x64.exe`, does not require Python, pip or
administrator rights. Download the executable and its `.sha256` record from the
[`v0.2.0` release](https://github.com/DKtech-dev/nhi-blast/releases/tag/v0.2.0):
[`nhi-blast-windows-x64.exe`](https://github.com/DKtech-dev/nhi-blast/releases/download/v0.2.0/nhi-blast-windows-x64.exe)
and
[`nhi-blast-windows-x64.exe.sha256`](https://github.com/DKtech-dev/nhi-blast/releases/download/v0.2.0/nhi-blast-windows-x64.exe.sha256).
Verify a download before running it:

```powershell
$record = (Get-Content .\nhi-blast-windows-x64.exe.sha256 -Raw).Trim()
$actual = (Get-FileHash .\nhi-blast-windows-x64.exe -Algorithm SHA256).Hash.ToLower()
if ($record -ne "$actual  nhi-blast-windows-x64.exe") { throw "checksum mismatch" }
```

```powershell
nhi-blast-windows-x64.exe --help
nhi-blast-windows-x64.exe version
nhi-blast-windows-x64.exe scan . --format html --out nhi-blast-out
```

`--help` lists the commands and `version` reports the tool and schema versions; a scan writes
`nhi-blast-out\report.html`. The one-file executable bundles Python, the optional HCL parser and
the report assets, runs offline and needs no source checkout. It is unsigned, so Windows may show
a reputation-based SmartScreen warning; no code-signing certificate is used.

### Run a scan

From the repository root, scan the reference fixture and run its incident scenario:

```bash
nhi-blast scan tests/fixtures/fx07-incident \
  --simulate-compromise action:tj-actions/changed-files@v45 \
  --format console \
  --format html \
  --fail-on high \
  --out nhi-blast-out
```

`--format` is repeatable. The command prints the console summary and writes `report.html` to
`--out`. It exits `1` because findings meet the `--fail-on high` threshold. Trimmed output:

```text
Survival
  action:tj-actions/changed-files@v45
  R (ends with entrypoint): 3
  E (expires on its own): 2
  Z (survives): 5
    Z prod/db-master (cred:aws:secret:prod/db-master:stored) [declared tfstate.json:77]; depth 0; until rotated; criticality 100
Rotation plan
  action:tj-actions/changed-files@v45 - Rotation
  step 1 generation 0:
    prod/db-master: Rotate the database master password, update the credential store, then terminate existing database sessions so the old password cannot be reused. [declared tfstate.json:77]
Findings
  [CRITICAL] NHB-OIDC-002 NHB-OIDC-002-f3384765: Organisation-wide or global wildcard in sub [declared tfstate.json:43]
  [CRITICAL] NHB-SURV-001 NHB-SURV-001-233ec620: Credentials survive revocation of the entrypoint [declared .github/workflows/release.yml:7]
```

Each credential line names the credential, its graph id, evidence class and source location; the
rotation plan orders survivors after containment. Severity orders findings; it is not a verdict.
JSON and HTML carry the full graph, evidence and assumptions. SARIF carries findings and evidence
but not the full graph; use `nhi-blast export` for JSON or DOT.

## Commands

| Command | Purpose | Artifacts |
| --- | --- | --- |
| `nhi-blast scan PATH` | Parse, audit trust, run scenarios and emit findings | `report.json`, `report.sarif` or `report.html` per `--format` |
| `nhi-blast rank PATH` | Rank mutable third-party actions by potential blast radius | `rank.json` with `--format json` |
| `nhi-blast explain ID --report FILE` | Print the evidence chain for a finding, node or edge | none |
| `nhi-blast export PATH --format json\|dot` | Export the authority graph | `graph.json` or `graph.dot` |
| `nhi-blast schema` | Print the report JSON Schema to stdout | none |
| `nhi-blast version [--data]` | Print tool, schema and data-file versions | none |

| Exit code | Meaning |
| --- | --- |
| `0` | Success |
| `1` | Findings at or above `--fail-on` |
| `2` | Usage or input error |
| `3` | Partial results when error diagnostics exist and `--strict` is set |
| `4` | Unexpected internal error |

<details>
<summary><strong>Selectors</strong></summary>

| Selector | Meaning |
| --- | --- |
| `action:OWNER/REPO[/PATH]@REF` | A mutable third-party action at a specific reference, at all use sites. |
| `action-any:OWNER/REPO` | The same action at any reference. |
| `job:RELPATH#JOB_ID` | One job in one workflow file. |
| `workflow:RELPATH` | Every job in a workflow file. |
| `secret:NAME` | A job and the secret reference it holds. |
| `role:ROLE_ID_OR_TF_ADDRESS` | An AWS role identified by graph id, ARN or Terraform address. |
| `repo-write` | A repository writer who can push a branch and edit a workflow. |
| `fork-pr` | A fork pull-request author whose code runs in a pull-request context. |
| `all-mutable-actions` | One scenario per mutable third-party action; also drives `rank`. |

Selectors are repeatable; an invalid selector is a usage error.

</details>

<details>
<summary><strong>Configuration</strong></summary>

`nhi-blast.toml` in the scan root loads automatically; `--config` selects another file inside the
root. Unknown keys are rejected so a typo cannot silently change a result.

```toml
repo_slug = "acme/shop"
default_branch = "main"
aws_account = "111122223333"
aws_region = "us-east-1"
[bindings.roles]
AWS_ROLE_ARN = "arn:aws:iam::111122223333:role/deploy-prod"
[ignore]
rules = ["NHB-GHA-003"]
paths = ["docs/examples/**"]
```

Bindings hold role identifiers, never credential values. `[ignore].paths` matches a finding's
evidence path with shell-style globs; `--strict` reports suppressed findings as diagnostics.

</details>

## Public beta

Version 0.2.0 is a public beta for testing and evaluation, not a production security control. Its
analysis supports an incident response; it is not a substitute for an independent cloud security
assessment. Treat every result as evidence to verify against your own environment, and read the
known limitations before relying on a finding.

External testers are welcome. Test only synthetic fixtures such as
`tests/fixtures/fx07-incident` or repositories you are authorised to assess. Do not send
credential values, secrets, private repository contents or live cloud data. Report reproducible
problems through the repository's beta bug report issue form with the operating system, version,
exact command, expected result, actual result and sanitised logs. The full process is in
[beta testing](docs/beta-testing.md).

## Security and limitations

- No execution of scanned content and no network access: no Terraform, Git or shell commands, no downloads, no `${{ ... }}` evaluation.
- Reads stay inside the scan root; escaping symlinks and junctions are rejected. Credential values are never stored, printed, logged or embedded.
- Evidence is ordered `DECLARED` > `DERIVED` > `ASSUMED` > `UNKNOWN`; UNKNOWN authority feeds only the `potential` set, never R, E or Z.
- Not modelled: SCPs, permission boundaries, KMS key policies, environment protection, branch rules and live AWS state.

> [!NOTE]
> See [known limitations](docs/known-limitations.md) for the full boundary, including unsupported
> inputs and what a result does and does not mean. No independent security audit has been performed
> or is claimed.

## Documentation

| Guide | Contents |
| --- | --- |
| [Architecture](docs/architecture.md) | Module boundaries and data flow |
| [Specification](docs/SPEC.md) | Normative requirements |
| [Rules](docs/rules/README.md) | Finding rules and severities |
| [Assumptions](docs/assumptions.md) | Platform and analysis assumptions |
| [Known limitations](docs/known-limitations.md) | Unsupported inputs and result boundaries |
| [Security audit](docs/security-audit.md) | Internal review and findings |
| [Beta testing](docs/beta-testing.md) | Test scope and reporting |
| [Release procedure](docs/release.md) | Release gates and artifacts |
| [Contributing](CONTRIBUTING.md) | Development workflow |

## Licence

MIT License; see [LICENSE](LICENSE). The published `0.1.0` and `0.1.1` releases remain under the
MIT License. Third-party components keep their own licences: the embedded Instrument Serif, Geist
and Geist Mono fonts are SIL Open Font License 1.1; see [NOTICE](NOTICE) and
[third-party notices](THIRD_PARTY_NOTICES.md).
