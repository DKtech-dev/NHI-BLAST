# NHI-Blast

NHI-Blast is a local-first, offline command-line tool for reasoning about non-human
identity authority in repository configuration. It reads GitHub Actions workflows,
local composite actions, Terraform plan/state JSON, Terraform `.tf.json` configuration
(with a best-effort HCL fallback) and IAM policy JSON, then answers three
incident-response questions:

1. **Reach** — from a hypothetical compromised entrypoint (a mutable action, a job,
   a leaked secret or a repository writer), which AWS roles, credential stores and
   credentials are potentially reachable?
2. **Revocation survival** — if that entrypoint is revoked now, which credentials end
   with the job (**R**), which temporary sessions expire on their own (**E**), and
   which persistent credentials survive (**Z**)?
3. **Rotation order** — in what order should surviving credentials be rotated so a
   surviving credential cannot re-read a freshly rotated one?

Everything is evidence-labelled: `DECLARED > DERIVED > ASSUMED > UNKNOWN`. Edge
confidence is the weakest class among its evidence. UNKNOWN-class edges never count
as reachable authority; they feed a separate `potential` set. The tool does not claim
proof of compromise, exploitability or takeover, and it never prints a credential
value.

> **Status: 0.1.0 pre-release, not published.** No package, tag or deployment exists.
> The implementation and local release gates are complete, including Python 3.12/3.13/
> 3.14 suites, packaging, clean installs, three-build reproducibility, a 10-repository
> corpus, an adversarial soak and real-browser/axe verification. Remote CI, Linux,
> independent audit and publication remain open. Read
> [production readiness](docs/production-readiness.md) for the current gate results and
> [known limitations](docs/known-limitations.md) before relying on a report.

## Install from a source checkout

Requires **Python 3.12+** (tested on 3.12, 3.13 and 3.14). The tool itself needs no
cloud credentials and makes no network requests while scanning.

```
python -m venv .venv
.venv/bin/python -m pip install ".[hcl]"
```

On Windows use `.venv\Scripts\python.exe`. The `hcl` extra enables the optional
Terraform HCL fallback. `rich` is an optional console-rendering extra; the CLI works
without it. For development, install `".[dev,hcl]"` instead.

Confirm the installation:

```
.venv/bin/nhi-blast version --data
```

For exact dependency versions, add `-c requirements.lock` to the install command.
The tool runs offline, but installing it needs access to a package index or a local
wheelhouse.

## Quickstart

Scan a repository and run the incident scenario from its reference fixture:

```
nhi-blast scan tests/fixtures/fx07-incident \
  --simulate-compromise action:tj-actions/changed-files@v45 \
  --format console \
  --format json \
  --format html \
  --fail-on high \
  --out nhi-blast-out
```

`--format` is repeatable; comma-separated values are rejected. The command prints the
console summary and writes `report.json` and `report.html` to `--out`. It exits `1`
when a finding meets the `--fail-on` threshold.

Typical use against your own checkout:

```
nhi-blast scan . --simulate-compromise repo-write --fail-on high
nhi-blast rank .
nhi-blast export . --format dot --out nhi-blast-out
nhi-blast explain NHB-OIDC-002-ebd9705d --report nhi-blast-out/report.json
```

A scan with no `--simulate-compromise` selector still builds the graph, audits OIDC
trust and reports findings, but runs no survival scenario.

## Commands

| Command | Purpose | Artifacts |
| --- | --- | --- |
| `scan PATH` | Parse, audit trust, run scenarios, emit findings | `report.json`, `report.sarif`, `report.html` depending on `--format` |
| `rank PATH` | Rank mutable third-party actions by potential blast radius | `rank.json` with `--format json` |
| `explain ID --report FILE` | Print the evidence chain for a finding, node or edge | none |
| `export PATH --format json\|dot` | Export the authority graph | `graph.json` or `graph.dot` |
| `schema` | Print the report JSON Schema to stdout | none |
| `version [--data]` | Print tool, schema and data-file versions and ages | none |

Exit codes: `0` success, `1` findings at or above `--fail-on`, `2` usage or input
error, `3` partial results when error diagnostics exist and `--strict` is set, `4`
unexpected internal error.

Common options include `--tf-json`, `--tf-hcl/--no-tf-hcl`, `--iam-json`,
`--repo-slug`, `--default-branch`, `--aws-account`, `--aws-region`, `--config`,
`--max-depth`, `--strict`, `--timestamp` and `--no-color`. Run
`nhi-blast <command> --help` for the exact surface.

## Compromise selectors

| Selector | Meaning |
| --- | --- |
| `action:OWNER/REPO[/PATH]@REF` | A mutable third-party action at a specific reference, at all of its use sites. |
| `action-any:OWNER/REPO` | The same action at any reference. |
| `job:RELPATH#JOB_ID` | One job in one workflow file. |
| `workflow:RELPATH` | Every job in a workflow file. |
| `secret:NAME` | A job and the secret reference it holds. |
| `role:ROLE_ID_OR_TF_ADDRESS` | An AWS role identified by its graph id, ARN or Terraform address. |
| `repo-write` | A repository writer who can push a branch and edit a workflow. |
| `fork-pr` | A fork pull-request author whose code runs in a pull-request context. |
| `all-mutable-actions` | One scenario per mutable third-party action; also drives `rank`. |

Selectors are repeatable. An invalid selector is a usage error. The analysis derives
candidate OIDC subjects from the trigger profile, repository identity and default
branch; it does not evaluate `${{ ... }}` expressions.

## Configuration

`nhi-blast.toml` in the scan root is loaded automatically. `--config` selects another
file inside the root. Unknown keys are rejected so a typo cannot silently change a
result.

```toml
repo_slug = "acme/shop"
default_branch = "main"
aws_account = "111122223333"
aws_region = "us-east-1"

# Resolve a workflow's expression-based role reference to a modelled role.
[bindings.roles]
AWS_ROLE_ARN = "arn:aws:iam::111122223333:role/deploy-prod"

# Attribute a static access-key secret to the principal that owns it.
[bindings.credentials]
AWS_ACCESS_KEY_ID = "arn:aws:iam::111122223333:role/legacy-ci"

# Override the OIDC subject layout: repository prefix, then trigger context.
[oidc]
sub_template = ["repo", "context"]

[ignore]
rules = ["NHB-GHA-003"]
paths = ["docs/examples/**"]

[limits]
max_closure_depth = 4
```

Bindings contain role identifiers, never credential values. `[ignore].paths` matches
a finding's evidence file or path elements with shell-style globs; `--strict` reports
suppressed findings as diagnostics instead of silently dropping them.

## Outputs

- **Console** — parse summary, trust audit, scenario partition, rotation plan and
  findings, with optional colour.
- **JSON** — schema `nhi-blast-report/1.0`: tool and input provenance, scope and
  limits, assumptions, diagnostics, findings, graph nodes and edges, scenarios with
  R/E/Z, potential, rotation plan and data-file versions. Equal inputs produce
  byte-identical artifacts unless `--timestamp` is used.
- **SARIF 2.1.0** — one run, rule metadata, security severity levels and thread-flow
  evidence for scanner ingestion; capped at 5,000 results with a notification.
- **HTML** — a single offline file. Embedded JSON is escaped as Unicode escapes, the
  DOM is built without HTML-string concatenation, the CSP allows only hashed inline
  scripts and vendored assets are inlined with hashes recorded in
  `src/nhi_blast/report/assets/MANIFEST.json`. Hostile strings render inert. The report
  includes a cross-scenario R/E/Z/P exposure matrix, deterministic shortest-path
  tracing with graph highlighting, scenario-aware summaries, and search/severity/
  scenario filters over findings.
- **DOT** — the authority graph for Graphviz.

## Safety model

- No execution of scanned content: no Terraform, OpenTofu, Git or shell commands, no
  provider or module downloads and no evaluation of GitHub expressions.
- No network access at analysis time, including the HTML report.
- Every read is resolved and must stay inside the scan root. Escaping symlinks and
  junctions are rejected.
- Credential values are never stored, printed, logged or embedded. A literal
  credential finding reports only its kind and length.
- Hostile YAML, oversized files, deep nesting, malformed JSON/HCL and pathological
  graphs produce diagnostics or a clean failure, not unbounded work.

## Documentation

| Document | Contents |
| --- | --- |
| [Architecture](docs/architecture.md) | Layers, graph rules, analysis and reporter design |
| [Specification](docs/SPEC.md) | Normative requirements source |
| [Implementation status](docs/implementation-status.md) | Milestone state and actual gate results |
| [Production readiness](docs/production-readiness.md) | Release-gate matrix and verdict |
| [Known limitations](docs/known-limitations.md) | What is not modelled, and what a result means |
| [Assumptions](docs/assumptions.md) | Every `A-*` and `H-*` assumption and heuristic |
| [Data provenance](docs/data-provenance.md) | Platform-data sources and verification dates |
| [Rules](docs/rules/README.md) | All 16 finding rules and remediation guidance |
| [Benchmark](docs/benchmark.md) | Performance budgets, measured results and environment |
| [Testing](docs/testing.md) | Test programme, markers, coverage and gates |
| [Requirements traceability](docs/requirements-traceability.md) | Specification requirement to code and test mapping |
| [Release procedure](docs/release.md) | Build, artifact check, clean install and publish gate |
| [Research sources](docs/research/sources.md) | Primary documents used for platform facts |
| [Security policy](SECURITY.md) | Supported versions, reporting and in-scope properties |
| [Contributing](CONTRIBUTING.md) | Setup, checks, architecture boundaries and rules |
| [Changelog](CHANGELOG.md) | Unreleased changes |

## Development

```
.venv/bin/python -m pytest
.venv/bin/python -m pytest -m security
.venv/bin/python -m ruff check src tests scripts
.venv/bin/python -m ruff format --check src tests scripts
.venv/bin/python -m mypy src
```

The tests treat warnings as errors. See [testing](docs/testing.md) for coverage gates,
the deterministic performance fixture and the current environment.

## Licence

MIT. See [LICENSE](LICENSE) and [NOTICE](NOTICE) for vendored asset attribution.
