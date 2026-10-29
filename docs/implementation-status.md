# Implementation status

Living record of what is actually built and verified. Every row must correspond to a
command that was run, with its real result. When a gate is not met, it says so.
Entries are chronological: earlier dated sections describe the implementation of that
date, including components that later changed or were removed.

Last updated: 2026-10-28
Overall verdict: **0.1.1 RELEASED; 0.1.0 remains available; `main` is a public,
proprietary 0.2.0 source tree with no published 0.2.0 artifact.** The 0.2.0 report and
graph redesign is implemented, tested and verified locally but is not committed or
released.
M0–M8 are implemented and verified locally and in remote CI, including packaging,
clean-environment installation, documentation, CI policy, dependency and secret audits,
three-build reproducibility, Python 3.12/3.13/3.14 suites on Ubuntu and Windows, a
10-repository real-world corpus, an adversarial soak, real-browser/axe verification, an
internal security audit with third-party scanners, and the 0.1.1 report redesign with
Lighthouse, html-validate and design-inspector verification. Version 0.1.0 was
published on 2026-10-27 from commit `0269100`; version 0.1.1 was published the same day
from commit `c702d9d` as the GitHub Release `v0.1.1`, after green CI run 40509205221 and
audit run 40509205137, with all assets re-downloaded and verified against `SHA256SUMS`.
On 2026-10-27 the repository was made public and the source tree was relicensed as
proprietary 0.2.0 in commit `e00cf81`; the published 0.1.0 and 0.1.1 releases remain
MIT. The independent human audit has not been performed and is not claimed; it is the
one open assurance gate.

## Environment used for every recorded result

| Item | Value |
| --- | --- |
| OS | Windows 10.0.26200 (x64), Git Bash |
| Python | 3.12.14 (`C:/Cyber/.venv/Scripts/python.exe`); also 3.13.17 and 3.14.7 in isolated environments for the final matrix |
| pip | 26.2.2 |
| CLI dependencies | Typer 0.20.1, Click 8.4.2 (Click pinned below 8.5 because Typer imports deprecated `click.utils` shims and tests treat warnings as errors) |
| Repository state | public GitHub repository `DKtech-dev/nhi-blast` since 2026-10-27, branch `main`; commits pushed and CI/audit workflows active |

Commands (run from `C:/Cyber`):

```sh
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m ruff check src tests scripts
./.venv/Scripts/python.exe -m ruff format --check src tests scripts
./.venv/Scripts/python.exe -m mypy src
```

## Milestones

| Milestone | Status | Evidence |
| --- | --- | --- |
| M0 baseline repair | Complete | Existing parser/resolver modules import; lint and type checks green after fixes |
| M1 OIDC and trust conformance | Complete | 112 tests pass; solver, subject, trust, condition and glob unit suites |
| M2 resolvers | Complete | 24 resolver tests (roles/composite/workflows); full suite 136 passed |
| M3 graph | Complete | 21 store/builder tests; full suite 157 passed; lint, format, mypy green |
| M4 analysis | Complete | 51 analysis tests; full suite 208 passed; lint, format, mypy green |
| M5 reporters | Complete | 30 reporter tests; full suite 238 passed; lint, format, mypy and schema check green |
| M6 CLI and pipeline | Complete | 37 pipeline/CLI tests; full suite 275 passed; lint, format, mypy green; installed console script exercised |
| M7 full test programme | Complete | 364 passed, 1 skipped; security 21 passed, 1 skipped; goldens 2 passed; slow 2 passed; coverage 85.36%; full-scale graph+scenario 1.568 s against the 5 s budget |
| M8 packaging, docs, CI | Complete (local + remote CI) | 403 passed, 1 skipped locally; 404 passed per job in remote CI on Ubuntu and Windows for 3.12–3.14; security 37/1; goldens 2; slow 2; coverage 86.47% local and 86.53% CI; ruff/format/mypy/schema clean; wheel and sdist artifact check passed; clean installs with and without the HCL extra plus sdist install; both locks clean under pip-audit and OSV; gitleaks/TruffleHog clean on history and artifacts; internal audit complete with zizmor, actionlint, Semgrep, Bandit, Grype and license inventory; CI pinned, SHA-pinning enforced, advisory workflow scheduled; documentation set complete; three builds digest-identical; 10-repository corpus and adversarial soak clean; real-browser and axe pass at 1440×900 and 390×844. Independent audit remains not performed and not claimed; publication authorized as GitHub Release assets |

## Verification log

### 2026-10-25 — M1

| Check | Command | Actual result |
| --- | --- | --- |
| M1 unit/property tests | `pytest -q tests/test_glob.py tests/test_conditions.py tests/test_trust.py tests/test_subjects.py tests/test_solver.py` | **112 passed** in 1.67 s |
| Full current suite | `pytest -q` | **112 passed** (no other tests exist yet) |
| Lint | `ruff check src tests` | **All checks passed** |
| Format | `ruff format --check src tests` | 49 files checked, all formatted |
| Types | `mypy src` | **Success: no issues found in 41 source files** |

Defects found and fixed while making M1 pass:

1. `oidc/github_subject.py` used `audience` outside the audience loop; the function
   could raise `UnboundLocalError` for every non-`workflow_call` trigger. The loop is
   now explicit and the assembly is split into small helpers.
2. `oidc/solver.py` deduplicated `SubjectCandidate` through a `set`; the model carries
   a `claims` dict and is not hashable. Deduplication now uses the candidate's
   identity fields.
3. `aws/glob.py` long-pattern fallback returned true whenever either pattern had a
   `*`, which could fabricate authority. Oversized pairs now fail closed, duplicate
   stars are collapsed, literal prefixes/suffixes are stripped, and trivial cases are
   decided without the quadratic table.

Coverage was **not measured** in this milestone. No integration, golden, security or
performance suite exists yet.

### 2026-10-25 — M2

| Check | Command | Actual result |
| --- | --- | --- |
| Resolver suites | `pytest -q tests/test_roles.py tests/test_composite.py tests/test_workflows.py` | **24 passed** in 0.95 s |
| Full suite | `pytest -q` | **136 passed** in 2.00 s |
| Lint | `ruff check src tests` | **All checks passed** |
| Format | `ruff format --check src tests` | 55 files already formatted |
| Types | `mypy src` | **Success: no issues found in 44 source files** |

Fixture evidence used by the tests:

- fx02: exact trust (`repo:acme/shop:ref:refs/tags/v*`), one SSM sink (`live_key`,
  API_KEY/70), provider host and audience, account/region inferred from ARNs.
- fx03: four roles preserving wildcard, missing-subject, dead-condition and
  missing-audience variants; `repo:acme/*` retained verbatim.
- fx07: four sinks; only `prod/app-config` is scheduled (30 days); Deploy role reads
  both Secrets Manager secrets and the SSM live key; the state sentinel
  `FIXTURE_ONLY_PLACEHOLDER_DB_MASTER_VALUE` appears in no resolved fact.
- fx10: HCL facts are DERIVED; `for_each` role trust stays unresolved with
  `D-TF-UNKNOWN`; the attached inline policy resolves; no placeholder value leaks.
- fx06: nested expansion (setup → nested, depth 2), cycle terminates after three
  steps, deep chain stops at depth 5, missing/invalid/non-composite references are
  diagnosed.
- fx13: local reusable call indexed with caller provenance; caller grant does not
  change this fixture's result; multiple-caller synthesis yields the per-scope most
  permissive bound with `A-REUSABLE-CALLER` and `D-GHA-REUSABLE-MULTI-CALLER`.

Defects found and fixed while making M2 pass:

1. `local_action_dir` used `lstrip("./")`, which stripped the leading dot from
   `./.github/...` and broke every hidden-directory composite path.
2. `effective_job_permissions` initialised the combined level map to `NONE`, so every
   bounded result collapsed to `NONE`; it now starts from the first caller.
3. `most_permissive_level` treated an explicit `NONE` as stronger than `WRITE`,
   contradicting the documented per-call-site rule; the ranking is now
   `WRITE > READ > UNKNOWN > NONE`.
4. Managed-policy bodies without a `resolved` flag were treated as unresolved even
   when the body was a valid empty policy; `_PolicyBody` now records resolution.

Deliberate contract additions (recorded in `docs/DECISIONS.md`):

- `CallSite` carries `caller_path`; a job id alone is not unique across workflows.
- `D-GHA-REMOTE-OPAQUE` is emitted for remote actions nested inside composites only;
  top-level remote actions are modelled by R2/RUNS_IN and do not need the
  blanket `A-STEP-SHARE` assumption.

Coverage was **not measured** in this milestone.

### 2026-10-25 — M3

| Check | Command | Actual result |
| --- | --- | --- |
| M3 suites | `pytest -q tests/test_graph_store.py tests/test_graph_builder.py` | **21 passed** in 0.80 s |
| Full suite | `pytest -q` | **157 passed** in 2.13 s |
| Lint | `ruff check src tests` | **All checks passed** |
| Format | `ruff format --check src tests` | 60 files already formatted |
| Types | `mypy src` | **Success: no issues found in 47 source files** |

Store coverage: duplicate node and edge merging, conflicting node kinds and edge
lifetimes, mandatory evidence, confidence-equals-weakest, content-derived edge ids,
missing-endpoint rejection, dangling-edge pruning, index/successor ordering,
`max_graph_nodes` truncation, and deterministic sorted serialisation.

Builder coverage and fixture evidence:

- fx07: repository/workflow/job structure, checkout and mutable-action use sites,
  GITHUB_TOKEN and OIDC request token, the Slack webhook secret, provider and both
  roles, STS session credentials with `ttl_seconds=3600`, `CAN_ASSUME` with
  `intended` true for deploy-prod and false for legacy-ci, all four reachable sinks,
  read edges for both roles (including the SSM live key), and rotation lifetimes.
- fx09: `permissions: read-all` and `permissions: {}` produce no OIDC identity,
  CAN_MINT, CAN_ASSUME or OIDC request token; both jobs still hold GITHUB_TOKEN.
- fx11: `[bindings.credentials]` produces the stored-key → role edges that close the
  key-a → role-b → key-b → role-a rotation cycle, with ASSUMED confidence.
- fx06: local and nested composite actions are attributed to the calling job, and a
  secret referenced only inside a composite is held by that job.
- Synthetic workflows: literal credentials keep kind/length only and their value is
  absent from the serialised graph; static access keys bind to
  `ext:aws-identity-unbound` and wildcard secrets yield an UNKNOWN HOLDS edge;
  unresolved trust yields an UNKNOWN CAN_ASSUME with A-TRUST-UNMODELLED; unresolved
  policy bodies yield an UNKNOWN CAN_READ_VALUE with A-POLICY-UNMODELLED; an
  expression permissions block yields an UNKNOWN CAN_MINT without claiming
  A-OIDC-ENV; node-budget truncation leaves no dangling edges; two builds are
  byte-identical.

Defects found and fixed while making M3 pass:

1. `permissions: read-all` and `write-all` were compared against the *level* names
   (`read`/`write`) instead of the GHA keywords. Both were treated as unrecognised
   expressions, which fabricated an UNKNOWN id-token writability and an OIDC
   identity in fx09. The parser now recognises the documented keywords.
2. `sinks_catalog.yaml` lacked the SSM default KMS alias (`alias/aws/ssm`), so every
   SSM read was suppressed as "customer-managed key is not readable". The platform
   fact is added; deploy-prod's SSM read now appears as DERIVED.
3. R4 read only `JobFact.refs`, ignoring `ExpandedJob.refs`; secrets referenced
   solely inside local composite actions were never materialised.
4. `[bindings.credentials]` entries whose target is an IAM role produced no
   AUTHENTICATES_AS edge, leaving the fx11 rotation cycle disconnected. R12 now
   applies these configuration bindings to role and external targets.
5. R6 attached the `A-OIDC-ENV` attribute to CAN_MINT even when id-token
   writability was UNKNOWN; it is now present only when write access is definite.

Deliberate contract additions:

- A `[bindings.credentials]` target may name an IAM role. The edge carries DECLARED
  `CONFIG.credential-binding` evidence and an ASSUMED `R12.credential-binding` link
  (holding the value grants the identity), so the cycle does not overstate proof.
- `GraphBuild` contains only graph-stage diagnostics. Parser, discovery and
  expansion diagnostics remain separate inputs that the M6 pipeline must merge; the
  builder does not re-emit them.

Known limitation: the spec-derived fx07 fixture contains no literal credential, so
the BUILD-PLAN phrase "literal nodes on fx07" cannot be satisfied without altering a
fixture whose contents mirror specification 14.4. R5 is instead verified with a
synthetic workflow that proves kind/length retention and value absence.

Coverage was **not measured** in this milestone.

### 2026-10-26 — M4

| Check | Command | Actual result |
| --- | --- | --- |
| M4 analysis suites | `pytest -q tests/test_selectors.py tests/test_reach.py tests/test_partition.py tests/test_rotation.py tests/test_rank.py tests/test_findings.py tests/test_scenario.py` | **51 passed** in 1.03 s |
| Full suite | `pytest -q` | **208 passed** in 2.35 s |
| Lint | `ruff check src tests` | **All checks passed** |
| Format | `ruff format --check src tests` | 75 files already formatted |
| Types | `mypy src` | **Success: no issues found in 55 source files** |
| Unscoped repository lint | `ruff check .` | **Failed: 6 pre-existing violations in preserved `_t.py`** (4 T201, 2 E501) |

Analysis coverage:

- Selectors resolve jobs, actions, roles, credentials and repositories; `repo-write`
  and `fork-pr` selectors apply their specified trust entrypoints.
- Reach prefers the strongest weakest-edge evidence class, then fewer hops, then the
  lexicographically smallest edge-id path. UNKNOWN authority edges feed `potential`
  only and never R/E/Z.
- fx07 produces R=3, E=2 and Z=5, five ordered rotation steps and the expected
  survivor finding. fx11's credential cycle produces one SCC rotation batch.
- Closure follows AUTHENTICATES_AS, CAN_READ_VALUE/CAN_MODIFY and STORES within the
  configured depth; survivor ordering and rotation dependencies are deterministic.
- Mutable-action ranking uses survivor counts, expiring-credential counts and use-site
  counts with action-name tie-breaking.
- All 16 finding rules have behavioural tests, including dynamic severity, evidence
  paths, deterministic ids, deduplication, rule/path ignores and strict ignore
  diagnostics. Literal-credential findings contain kind and length, not values.
- Scenario-local `repo-write` augmentation adds only ASSUMED paths accepted by the
  role trust policy; it does not mutate the input graph or displace stronger existing
  paths. A zero-time budget returns partial empty results with `D-ANALYSIS-TIME`, no
  findings and no rotation plan.

Deliberate contract decisions:

- NHB-SURV-001 maps highest Z criticality to CRITICAL at 90 or above, HIGH at 70,
  MEDIUM at 40 and LOW below 40; the specification names the input but not thresholds.
- `rank_mutable_actions` accepts resolved `Inputs` directly; pipeline orchestration is
  deferred to M6.
- Closure remains in `analysis/partition.py`; no separate cache or closure module was
  needed.
- Role nodes retain graph-backed trust-audit facts so dead-condition findings remain
  available when trust evaluation produces no CAN_ASSUME edge.
- `repo-write` additions are scenario-local and ASSUMED, with `A-REPO-WRITE` marked
  VERIFY in the assumption registry.

Defects found and fixed while making M4 pass:

1. Findings evidence groups were nested inconsistently, causing tuple attribute
   errors; finding construction now flattens evidence groups at one boundary.
2. Dead-condition audit data disappeared when no trust edge matched; role-node audit
   facts now preserve the graph evidence needed by NHB-OIDC-004.
3. Scenario-local repo-write evaluation initially omitted the `SubFormat` import;
   the regression test now exercises synthetic ASSUMED role/session reach directly.

The preserved scratch file `_t.py` was not changed. It blocks only unscoped
repository-wide Ruff; the maintained `src`/`tests` lint and format gates are clean.
Coverage and the specification's performance budget were **not measured**. Reporter,
CLI, golden, integration and output-security verification remain pending.

### 2026-10-26 — M5

| Check | Command | Actual result |
| --- | --- | --- |
| M5 reporter suites | `pytest -q tests/test_json_report.py tests/test_console.py tests/test_sarif.py tests/test_html.py tests/test_report_security.py` | **30 passed** in 1.26 s |
| Full suite | `pytest -q` | **238 passed** in 2.87 s |
| Lint | `ruff check src tests scripts` | **All checks passed** |
| Format | `ruff format --check src tests scripts` | 90 files already formatted |
| Types | `mypy src` | **Success: no issues found in 63 source files** |
| Committed report schema | `python scripts/gen_schema.py --check` | **exit 0**, schema is current |

Reporter coverage:

- **JSON.** Canonical serialisation uses Pydantic aliases, omits `None`, sorts keys and
  uses compact separators with one trailing newline. The generator in
  `scripts/gen_schema.py` owns `docs/schema/report.schema.json`; the test fails if the
  checked-in schema differs, validates a rendered report against it and proves that a
  required-field deletion is rejected. Report dicts are byte-stable across renders.
- **SARIF.** One run, all 16 catalog rules with descriptions, help, tags, precision and
  default levels. Results carry severity-to-level/security-score mapping, confidence,
  assumptions, stable fingerprints (`nhiBlast/v1`, rule + sorted node ids + primary
  evidence file) and code-flow locations. Absolute and traversal paths are omitted.
  Output is capped at 5,000 results with a `toolExecutionNotifications` warning that
  states the dropped count. Every emitted document validates against the official
  SARIF 2.1.0 schema (112,469 bytes, SHA-256
  `c96eb2d311c37b0a38cbd18c52d79a68f778bbd2d831abed7412d9850740f785`); the report
  schema file has SHA-256
  `26104832566445d6900a5a27f9e14555c57e55e7996b766d11ed0910fda1ca4c`.
- **Console.** Parse, trust audit, scenario, survival, rotation plan, findings,
  assumptions/unknowns and diagnostics. R/E/Z are labelled with their survival meaning.
  Every node, credential and evidence suffix uses the strongest sorted evidence.
  ANSI escapes are emitted only with `color=True`; all report-derived strings pass
  through `safe_text`, which strips ANSI/OSC, bidi controls and C0/C1 bytes, flattens
  newlines and caps length.
- **HTML.** Single file, no external resources, data in
  `<script type="application/json">` with `<`, `>`, `&`, U+2028 and U+2029 escaped.
  A restrictive CSP lists the SHA-256 hash of every inline script (five total:
  data, three vendored libraries, application code); `default-src 'none'`,
  `base-uri 'none'` and `form-action 'none'` are set. Application code builds DOM only
  through `createElement`, `textContent`, `replaceChildren` and `setAttribute`; there is
  no `innerHTML`, `eval`, `new Function`, `document.write` or network API. The graph
  uses pinned Cytoscape 3.30.4, dagre 0.8.5 and cytoscape-dagre 2.5.0 (MIT) from
  `report/assets/vendor`; every load verifies its SHA-256 against
  `assets/MANIFEST.json`. No raw asset text containing `</script` is accepted.
- **Output security.** A synthetic report containing a literal credential, terminal
  escapes, NUL, bidi controls and HTML/JS injection payloads is rendered through all
  four formats. The credential value appears in no output; hostile text remains data;
  the HTML contains exactly five scripts and no injected element/event attribute; no
  NUL or ESC reaches the HTML shell.
- **Determinism.** All four renderers produce byte-identical output on equal input.

Browser verification (honest limits): the fx07 report rendered to a 751,334-byte local
file. The browser loaded it from `file:///`, `list_console_messages` returned no
messages (no CSP or JavaScript errors), and the accessibility snapshot showed the
populated summary (26 nodes, 24 edges, 7 findings), R=3/E=2/Z=5, rotation steps,
findings and diagnostics. A visual screenshot could not be captured because the
in-app browser reported a 0x0 hidden viewport; pixel-level graph appearance is
therefore **not** verified. Structural rendering and script execution are.

Defects found and fixed while making M5 pass:

1. The HTML inline-script guard tested asset *names* for `</script` instead of the
   loaded asset *text*. It now rejects any vendored content containing that sequence.
2. Removed a no-op `heading.textContent = heading.textContent` and a dead `__DATA__`
   template placeholder; asset text is now loaded once per render.
3. Console rendering was split into section helpers to meet the configured complexity
   limit. Output was unchanged and all console assertions still pass.

Known limitations at M5 close: reporters had no dot export yet (added in M6;
opengraph remains Phase 2); HTML is verified structurally and through the browser's
accessibility tree, not by screenshot; the 5,000-result SARIF cap is tested, but no
full-repository performance run exists yet.

### 2026-10-26 — M6

| Check | Command | Actual result |
| --- | --- | --- |
| M6 pipeline/CLI suites | `pytest -q tests/test_pipeline.py tests/test_cli.py` | **37 passed** in 2.43 s |
| Full suite | `pytest -q` | **275 passed** in 4.36 s |
| Lint | `ruff check src tests` | **All checks passed** |
| Format | `ruff format --check src tests` | **98 files already formatted** |
| Types | `mypy src` | **Success: no issues found in 70 source files** |
| Installed console script | `.venv/Scripts/nhi-blast.exe version` | **exit 0**, prints tool and report schema versions |
| Manual fx07 scan | `nhi-blast scan tests/fixtures/fx07-incident --simulate-compromise "action:tj-actions/changed-files@v45"` | **R=3, E=2, Z=5**, one scenario, 7 findings, rotation plan, exit 0 |
| Manual fx03 gate | `nhi-blast scan tests/fixtures/fx03-wildcard-trust --fail-on high` | **exit 1**, finding line names `tfstate.json:23` |
| Manual partial result | malformed workflow + `--strict` | **exit 3** with `D-YAML-PARSE` |
| Manual usage error | `scan … --format xml` | **exit 2**, no traceback |
| Manual output error | `--out` pointing at an existing file | **exit 4**, no traceback |

Pipeline and CLI coverage:

- Discovery, parsing, composite expansion, cloud resolution and graph construction are
  now exercised through the real filesystem rather than hand-built facts. fx07 loads
  two workflows, two jobs, nine Terraform resources and the `.git/config` identity.
- Identity precedence is tested end to end: `--repo-slug` > `nhi-blast.toml` >
  `.git/config`; only inputs that actually contribute identity appear in the digest.
- HCL is auto-enabled only when no Terraform JSON is discovered, and both overrides
  (`--tf-hcl`, `--no-tf-hcl`) are covered on fx07/fx10.
- Scenarios, merged trust findings, ignore filtering, assumptions, scope lines and
  stale-data warnings are assembled into one report. Every reported assumption has at
  least one attributed node, edge, finding or scenario.
- `scan` defaults to console only and writes nothing unless a file format is requested;
  JSON, SARIF and HTML artifacts are byte-deterministic. `--timestamp` is the only
  source of wall-clock data, and data-staleness diagnostics appear only with it.
- Exit codes are covered at the pipeline and CLI layers: 0 success, 1 fail-on, 2 usage,
  3 strict partial results, 4 output/internal failure. Tests prove 4 beats 1 and 3
  beats 1. Internal exceptions print only their type name; messages and tracebacks are
  not leaked.
- `rank` reproduces the fx07 reference row (TAG, 2 use sites, 1 OIDC job, R=3, E=2,
  Z=5, criticality 100) and writes canonical `rank.json`.
- `export` writes self-describing JSON and Graphviz DOT. DOT uses numeric vertex ids
  and escapes quotes/backslashes, so a hostile workflow name cannot inject DOT syntax.
  `opengraph` is rejected as a Phase 2 usage error.
- `explain` re-validates a saved report, checks its schema and renders finding, node
  and edge evidence chains. `schema` matches the checked-in report schema;
  `version --data` prints all eight data files with provenance and age.

Defects found and fixed while making M6 pass:

1. The walker's workflow predicate required four path components, so
   `.github/workflows/*.yml` (three components) was never discovered. Every pipeline
   scan saw zero workflows and zero findings while unit tests passed because they
   built facts directly. The predicate is corrected and the load test now asserts the
   discovered workflow paths.
2. The assumption collector read only the plural `assumptions` edge attribute, missing
   the singular `assumption` used for `A-OIDC-ENV`; and trust evaluation recorded
   `A-REPO-AGE` as used without attributing it to any edge. The collector accepts both
   forms and trust edges now carry `A-REPO-AGE`, so no assumption is reported without
   a user.
3. Typer 0.20.1 imports deprecated `click.utils` shims; Click 8.5 warns on import and
   the warning-as-error test policy aborted collection. Click is pinned to `<8.5` in
   the project dependencies rather than suppressing the warning gate.
4. New code failed strict typing/linting on an unexported `Evidence` import, a
   `TypedDict` default, `datetime.UTC` usage and invalid-type exception classes; all
   were corrected at the source.

Known limitations at M6 close: `opengraph` export is intentionally not implemented
(Phase 2); `.tf.json` configuration parsing remains the recorded open question;
`all-mutable-actions` was initially expanded only by `rank` and rejected by `scan`
(since corrected; see the M8 hardening log); the installed-script check covers
`version`, while a fresh-venv install, coverage thresholds, goldens, adversarial file
fixtures and the performance budget remain M7/M8 work. No independent security audit
has been performed.

### 2026-10-26 — M7

| Check | Command | Actual result |
| --- | --- | --- |
| Full suite | `pytest -q` | **364 passed, 1 skipped** in 14.87 s |
| Adversarial marker | `pytest -q -m security` | **21 passed, 1 skipped**, 343 deselected |
| Golden marker | `pytest -q -m golden` | **2 passed**, 363 deselected |
| Performance marker | `pytest -q -m slow` | **2 passed** in 8.54 s, 363 deselected |
| Coverage gate | `python scripts/check_coverage.py` | **passed**; overall line coverage **85.36%** (minimum 80%) |
| Lint | `ruff check src tests scripts` | **All checks passed** |
| Format | `ruff format --check src tests scripts` | **108 files already formatted** |
| Types | `mypy src` | **Success: no issues found in 70 source files** |
| Scale load | `load_repository` on generated fx15 (200 workflows, 2,000 resources) | **0.623 s**; 200 jobs, 2,000 resources |
| Scale build + scenario | `build_repository_graph` + one `repo-write` scenario | **1.568 s** (budget 5 s); **4,202 nodes, 4,199 edges**; R=400, E=200, Z=1,000 |
| Scale rank | `run_rank` on the same fixture | **6.285 s** (budget 60 s); **400 rows** |
| Smoke fixture | `repo-write` scan of `tests/fixtures/fx15-scale-smoke` | **86 nodes, 83 edges, 33 findings**; R=8, E=4, Z=20; only `D-TF-ROTATION-UNBOUND` |

Test programme delivered in M7:

- **Fixture inventory.** All fifteen fixture directories have a README, and
  `tests/fixtures/README.md` records the verified workflows/jobs/resources, node and
  edge counts, finding counts, R/E/Z sizes, potential paths and diagnostics.
  `tests/test_fixtures.py` asserts those values through discovery, graph construction
  and a `repo-write` scan. `scripts/gen_fixtures.py` regenerates the smoke and
  full-scale variants deterministically with no clock, randomness, network or
  credential values.
- **Reviewed goldens.** `tests/golden/fx07-console.txt` and `fx07-summary.json` are the
  exact reviewed incident output; `tests/test_golden.py` compares bytes and semantics.
  The spec 14.4 console sketch is illustrative and not byte-normative; its `[1/4]`
  headings and one warning are not reproduced, which is documented in
  `docs/testing.md`.
- **Adversarial input.** `tests/test_security.py` covers duplicate and YAML 1.1
  normalised keys, multi-document streams (only the first is read), node/depth/alias
  limits at and beyond the boundary, malformed and deeply nested Terraform JSON,
  malformed HCL, exact byte limits, non-UTF-8 files, exact file-count boundaries,
  relative traversal, escaping file symlinks, escaping directory junctions, and a
  synthetic literal plus Terraform-sensitive canary checked across console, JSON,
  SARIF and HTML.
- **Property tests.** `tests/test_properties.py` proves prefilter soundness:
  `CandidateFilter.could_apply` and `TrustSubjectFilter.may_match` must admit every
  pair that the evaluators accept. It also covers selector round-trips and malformed
  rejection, identifier stability and order independence, digest pair ordering and
  condition truth for the implemented operators. These properties can find false
  negatives; they do not claim filter completeness.
- **Determinism and offline behavior.** `tests/test_determinism.py` requires identical
  console text and identical JSON/SARIF/HTML bytes across output directories and
  reversed selector order, proves `--timestamp` is the only wall-clock source, repeats
  the check for rank/export artifacts, and runs a full scan with socket entry points
  replaced by failures.
- **Performance.** `tests/test_performance.py` (marker `slow`) generates 200 workflows
  and 2,000 resources, measures graph build plus one scenario against 5 s and rank
  against 60 s, and asserts graph/partition sizes. Coverage runs exclude `slow`
  because tracing inflates wall-clock time.
- **Coverage policy.** `scripts/check_coverage.py` enforces 80% overall line coverage
  and 80% for every module under `nhi_blast/aws/`, `nhi_blast/analysis/` and
  `nhi_blast/report/`. Actual: 85.36% overall, 88.35% statement, 77.02% branch; the
  lowest enforced module is `policy_eval.py` at 88.81%. Branch coverage is reported,
  not gated.

Performance defect and resolution (recorded honestly):

The first M7 full-scale build took **236.169 s** and produced **83,799 edges**. The
cause was not an unsound graph: the generated fixture had no concrete AWS account or
region, so SSM/Secrets Manager candidate ARNs were `arn:aws:ssm:*:*:parameter/...`
and IAM `*` may absorb `:`, making many patterns genuinely intersect. An earlier
prefix-only prefilter briefly reached 3.684 s but silently dropped wildcard candidate
edges and was rejected.

The fix was to make identity concrete, not to weaken checks:

1. `scripts/gen_fixtures.py` now writes a concrete account, region, provider ARN,
   role ARNs, secret ARNs and `aws-region` inputs throughout the generated fixture.
2. `resolvers/roles.py` builds a `PolicyContext` from configured values or, when they
   are absent, from the sorted region/account found in role, sink and managed-policy
   ARNs.
3. `aws/sinks.py` constructs SSM/Secrets Manager/KMS candidate ARNs from that context
   instead of leaving region and account as `*`.

The sound `CandidateFilter` remains: concrete candidates use literal-prefix filtering,
and candidate ARNs that are themselves globs are still compared with exact
`glob_match`/`glob_intersects`. With realistic concrete identity the graph has 4,199
edges and the measured build plus scenario is 1.568 s.

Defects found and fixed while making M7 pass:

1. `parsers/yaml_marked.py` used `yaml.compose`, which reports a parse error for a
   multi-document stream. It now composes the first document only and closes the
   generator without reading the rest.
2. Deep Terraform JSON crashed `_iter_modules`, `_flatten_unknown` and `_strip_paths`
   with `RecursionError`. Traversal and stripping are iterative, and a decoder-level
   `RecursionError` becomes `D-TF-PARSE`.
3. `_walk` reported truncation at exactly `max_files`; it now emits `D-IO-LIMIT` only
   when another file actually exists beyond the limit.
4. Escaping `.json` symlinks could be opened during content sniffing before the
   containment check. Containment is now checked before `classify_path`, and a test
   records every `Path.open` call to prove the link is never opened.
5. Windows directory junctions were not recognised as links and could be traversed.
   `is_link_like` covers symlinks and junctions; link-like directories are pruned and
   escaping ones produce `D-IO-SYMLINK`.

Known limitations at M7 close:

- Creating a real file symlink requires Developer Mode or elevation on this Windows
  host, so that one test skips; the directory-junction escape test runs and covers the
  same pruning path. On POSIX the symlink test runs.
- Performance numbers are single-machine observations, not a portability claim.
- Coverage is line-oriented; branch coverage is reported but not gated.
- `opengraph` export remains a documented Phase 2 exclusion.
- No independent security audit, certification or external benchmark has been
  performed. The test suite is the evidence; it is not an audit.

### 2026-10-26 — M8

This is the close-of-milestone record. Later work and the current gate results are in
the post-M8 section below; the counts and timings here are historical.

| Check | Command | Actual result |
| --- | --- | --- |
| Full suite | `pytest -q` | **381 passed, 1 skipped** in 15.25 s (the skip is the Windows symlink-privilege case) |
| Adversarial marker | `pytest -q -m security` | **32 passed, 1 skipped** |
| Golden marker | `pytest -q -m golden` | **2 passed** |
| Performance marker | `pytest -q -m slow` | **2 passed** in 10.19 s |
| Coverage gate | `python scripts/check_coverage.py` | **passed**; 85.36% overall, 88.34% statements, 77.02% branches; lowest enforced module `report/html.py` at 83.10% |
| Lint | `ruff check src tests scripts` | **All checks passed** |
| Format | `ruff format --check src tests scripts` | 112 files already formatted |
| Types | `mypy src` | **Success: no issues found in 70 source files** |
| Report schema | `python scripts/gen_schema.py --check` | **exit 0** |
| Build | `python -m hatchling build -t wheel -d dist` and `-t sdist -d dist` | wheel and sdist produced from the source tree |
| Artifact contents | `python scripts/check_artifacts.py dist` | **passed**; wheel 88 files, sdist 234 files; required data, vendor assets and release documents present; no caches, scratch files, research cache or test tooling in runtime requirements; every sdist top-level entry is on an explicit allowlist |
| Clean install with HCL | fresh venv, `pip install -c requirements.lock dist/*.whl[hcl]` | `pip check` clean; `version`, `version --data`, `schema`, `scan`, `rank`, `export` and `explain` exercised on fx07; fx10 HCL facts parsed; installed-wheel fx07 JSON, SARIF and HTML byte-identical to the source CLI's |
| Clean install without HCL | fresh venv, runtime lock only | fx07 scan works; fx10 emits `D-TF-HCL-UNAVAILABLE` with installation guidance; `--strict` returns 3 |
| Two-build reproducibility | two consecutive hatchling builds into separate output directories, then `sha256sum` | **identical SHA-256 digests** for wheel and sdist across both builds; the tree was unchanged between builds and no archive metadata varied |
| Browser rendering | Chrome 156.0.8078.47, headless via CDP, 1440×900 and 390×844 mobile emulation | graph rendered at both sizes (3 canvases; 1061×520 and 341×488); `scrollWidth == clientWidth` at both widths; screenshots reviewed; in-app browser reported no console messages and no network requests; skip link and focus outline verified by keyboard |
| Dependency audit | `pip-audit 2.10.1 -r requirements.lock` and `-r requirements-dev.lock` | **no known vulnerabilities** in either lock; `pytest` is 9.1.1, above the advisory-affected 8.4.2 |
| CI static policy | `pytest -q tests/test_ci_pins.py` | **7 passed**; actions pinned to full commit SHAs with version comments, read-only permissions, exact-version locks, no `pull_request_target` |
| Documentation checks | `pytest -q tests/test_docs.py` | **3 passed**; local links resolve, every catalog rule has a page, README documents every CLI command |
| Artifact regression checks | `pytest -q tests/test_artifacts.py` | **4 passed**; optional-extra requirements are not treated as runtime, marker without extra remains runtime, path normalisation preserves leading dots, unexpected sdist top-level roots are rejected |
| HTML accessibility (static) | `pytest -q tests/test_html.py` | structural test passed; language, title, skip link, labelled navigation, live region, captions and column scopes, focus-visible styling, graph text alternative; fx07 report 755 KB, below the 3 MB target |

M8 delivered:

- **Packaging.** Wheel and sdist are built with hatchling. The wheel contains all eight
  platform-data files, the report assets and their manifest; the sdist additionally
  contains the specification, tests, documentation, locks and release documents.
  Optional extras (`rich`, `hcl`, `dev`) do not leak into runtime requirements.
- **Missing HCL dependency.** When the optional HCL parser is not installed, the parser
  now returns `D-TF-HCL-UNAVAILABLE` with an actionable installation message instead of
  a generic parse failure. HCL files are reported as discovered but unparsed, and
  `--strict` correctly yields exit 3.
- **Reproducible installs.** Both clean-environment installations used the exact-version
  runtime lock and were exercised through the installed console script, not the source
  tree. `pip check` reported no broken requirements.
- **Supply chain.** Both lock files are exact pins, contain no git, URL or editable
  requirements, and audit clean. The pytest pin is above the advisory-affected 8.4.2.
  CI pins its two third-party actions to full commit SHAs verified older than 14 days
  and uses a read-only token.
- **Documentation set.** `README.md` (rewritten from the stub to the exercised command
  surface), `docs/architecture.md`, `docs/rules/README.md`, `docs/assumptions.md`,
  `docs/known-limitations.md`, `docs/production-readiness.md`, `docs/release.md`,
  `docs/research/sources.md`, `SECURITY.md`, `CONTRIBUTING.md`, `NOTICE` and
  `CHANGELOG.md`. `docs/testing.md` and this file were brought in line with the
  measured results. `HANDOVER.md` is marked superseded.
- **Documentation freshness tests.** A local-link checker, a rule-catalog/page
  cross-check and a README command check now fail the suite if the documentation rots.
- **HTML accessibility and responsive layout.** Text tables gained captions and column
  scopes; heading levels no longer skip; focus-visible styling and a text alternative
  for the pointer-only graph are present. Long identifiers wrap, narrow viewports use
  reduced spacing, and each table sits in a labelled, keyboard-focusable horizontal
  scroll region so a six-column table cannot widen the whole document.
- **Real-browser verification.** A fresh fx07 report was opened from `file:///` in
  Chrome 156.0.8078.47 through CDP at 1440×900 and 390×844. The graph rendered at both
  sizes, no horizontal overflow occurred, and the screenshots were inspected. The
  in-app browser reported no console messages and no network requests; keyboard
  traversal reached the skip link first with a visible focus outline.
- **Two-build reproducibility.** Two consecutive builds into separate directories
  produced identical SHA-256 digests for the wheel and the sdist. This is a same-tree,
  same-toolchain observation; cross-machine reproducibility is not claimed.

Defects found and fixed while making M8 pass:

1. `scripts/check_artifacts.py` counted `Requires-Dist` lines for optional extras as
   runtime dependencies, so the legitimate `dev` extra (`pytest`) failed the wheel
   check. Runtime filtering now ignores requirements whose marker names an extra; a
   marker without an extra still counts. Regression tests cover both.
2. `_normalise` in the artifact checker stripped every leading `.` and `/` via
   `lstrip("./")`, which would have hidden `.venv/` and `.taste-skill/` instead of
   rejecting them. It now strips only repeated `./` prefixes; a regression test pins
   the behaviour.
3. A missing optional HCL dependency surfaced as `D-TF-HCL-PARSE` with
   `ModuleNotFoundError`, which does not tell a user what to install. Import failure and
   document-parse failure are now separate diagnostics.
4. The new documentation link test initially failed because
   `docs/production-readiness.md` did not exist; the readiness document was written
   rather than the test being relaxed.
5. Ruff flagged prints in the release-check script. `scripts/**` now permits `T201`
   because printing is that script's interface; runtime and report code remain
   restricted.
6. `NOTICE` initially carried guessed copyright years for vendored libraries. The
   vendored header was inspected and the Cytoscape years corrected; unverifiable years
   for the other two packages were removed.
7. README examples used a comma-separated `--format` value, which the CLI rejects with
   exit 2. Every example now repeats `--format` per output, and the restriction is
   documented.
8. The HTML graph never initialized: the scenario focus set added `id` for the E
   partition, but `id` is not defined in that callback, so `renderGraph` raised a
   `ReferenceError` before Cytoscape ran. The focus set now uses
   `entry.credential`, and a regression test pins all three partition mappings. The
   real-browser pass found this; the previous 0×0 viewport had hidden it.
9. The HTML report had no narrow-width layout: a 64-character digest and wide
   multi-column tables forced the document wider than a 390px viewport. Long
   identifiers now wrap, small screens use reduced spacing, and tables scroll inside a
   labelled, focusable region. Verified with CDP device emulation at 390px.
10. Cytoscape emitted a console warning for the custom `wheelSensitivity: 0.2`
    override. The override was removed so the report loads without warnings; zoom
    uses the library default.
11. An sdist rebuild swept the untracked `.buildcheck/` verification scratch tree
    (including a consumer virtual environment) into the archive: 566 files instead of
    234. The artifact checker passed because it only looked for known forbidden
    markers. `.buildcheck/` is now ignored and excluded from the sdist, and the
    checker requires every sdist top-level entry to be on an explicit allowlist, with
    a regression test. The clean rebuild is 234 files, and two fresh builds remain
    byte-identical.

Open M8 gates: remote CI execution, execution on Linux and Python 3.13, an explicit
decision on automating advisory scans in CI, and independent audit/publication. None of
these has been performed or is claimed. Two-build reproducibility and browser rendering
are complete for this environment only.

### 2026-10-26/27 — Post-M8 hardening and final local verification

| Check | Command | Actual result |
| --- | --- | --- |
| Full suite, Python 3.12 | `pytest -q` | **395 passed, 1 skipped** in 20.35 s (the skip is the Windows symlink-privilege case) |
| Python 3.13 suite | `%TEMP%/nhb-py313/Scripts/python.exe -m pytest -q -m "not slow"` | **393 passed, 1 skipped, 2 deselected** in 9.45 s; slow: **2 passed** in 9.89 s |
| Python 3.14 suite | `%TEMP%/nhb-py314/Scripts/python.exe -m pytest -q -m "not slow"` | **393 passed, 1 skipped, 2 deselected** in 9.47 s; slow: **2 passed** in 12.17 s |
| Adversarial marker | `pytest -q -m security` | **32 passed, 1 skipped** |
| Golden marker | `pytest -q -m golden` | **2 passed** |
| Coverage gate | `python scripts/check_coverage.py` | **passed**; overall line coverage **86.47%**; 6,327/7,085 statements (89.30%); 2,001/2,546 branches (78.59%); lowest enforced module `report/html.py` at 83.10% |
| Coverage run | `pytest -q -m "not slow" --cov=src/nhi_blast --cov-branch` | **393 passed, 1 skipped, 2 deselected**; totals independently re-measured from the coverage JSON |
| Lint | `ruff check src tests scripts` | **All checks passed** |
| Format | `ruff format --check src tests scripts` | **112 files already formatted** |
| Types | `mypy src` | **Success: no issues found in 70 source files** |
| Report schema | `python scripts/gen_schema.py --check` | **exit 0** |
| Final artifact check | `python scripts/check_artifacts.py` | **passed**; wheel 88 files, sdist 234 files; required data, vendor assets and release documents present; no caches, scratch files or test tooling in runtime requirements; sizes and digests are recorded in `dist/SHA256SUMS` beside the frozen artifacts |
| Three-build reproducibility | three hatchling builds into separate directories, then `sha256sum` | **identical** wheel and sdist SHA-256 digests across all three builds; the values for the frozen candidate are recorded in `dist/SHA256SUMS` rather than in this document, because the sdist packages this document |
| Clean install, HCL extra | fresh venv, final wheel plus `hcl` | `version`, `version --data`, `schema`, `scan`, `rank`, `export` and `explain` all exit 0; fx07 produces JSON, SARIF and HTML |
| Clean install, base wheel | fresh venv, final wheel without extras | `version` works; fx10 with `--tf-hcl` emits `D-TF-HCL-UNAVAILABLE` with installation guidance and exits 0 (exit 3 only under `--strict`) |
| Clean install, sdist | fresh venv, final sdist | wheel builds from sdist; `version` and a scenario scan of fx01 exit 0 |
| Real-world corpus | 10 public repositories, 1,959 files (163 workflow files, 101 Terraform files) | **0 failures**; 21 all-mutable-actions scenarios, exactly matching 21 rank rows; 37 findings, 1,149 nodes, 2,181 edges, 451 diagnostics; repeated scan/SARIF/HTML bytes identical; max scan 1.92 s, max rank 1.82 s, max export 1.87 s |
| Adversarial soak | 16 generated cases: hostile YAML, traversal, Terraform JSON, Terraform plan, HCL, 80-finding repository, bad config and CLI negatives | **0 failures**; no traceback, no unbounded run, no exit code outside the documented set; tf-hostile produces 1 role, 403 credentials and 400 sinks; tf-plan-hostile produces 400 roles and only conservative policy diagnostics |
| Secret-leak audit | corpus candidate values checked against all corpus artifacts, final wheel/sdist and final report outputs | 15 candidate values from 8 source files; **0 leaks** in 68 corpus artifacts and 44 release/report artifacts, including the refreshed wheel, sdist and clean-install outputs; values were never printed |
| Browser UI | Chrome 156.0.8078.47 via CDP, 10-scenario corpus report and 2-scenario fx07 report at 1440×900 and 390×844 | 3 graph canvases; 48 matrix status buttons on the 10-scenario report; no desktop or mobile horizontal overflow (`scrollWidth == clientWidth`); 0 console messages, 0 exceptions, 0 external requests; scenario switch, 2-hop survival trace, 8-hop matrix trace, text filter 3/7, LOW filter 4/7, shared-credential filter 5 of 10 |
| Accessibility | axe-core 4.10.3, light and dark schemes | **0 violations**, 52 passes in each scheme; the one remaining `incomplete` is gradient-background contrast on the header, whose text/background pairs were manually computed at ≥4.86:1 |
| Dependency audit | `pip-audit 2.10.1 -r requirements.lock` and `-r requirements-dev.lock` | **no known vulnerabilities** in either lock |

Post-M8 defects found and fixed:

1. `scan --simulate-compromise all-mutable-actions` was rejected as an unknown
   selector even though `rank` already ranked mutable actions. The mutable-action
   predicate moved to `analysis/selectors.py`, the pipeline expands the selector into
   one deterministic, deduplicated scenario per action (zero targets yields no
   scenarios and exit 0), and `rank` uses the same predicate. The corpus verifies that
   scan scenario counts equal rank row counts on all ten repositories.
2. A valid `.tf.json` Terraform configuration produced a false `D-TF-HCL-PARSE` because
   the HCL adapter accepted only `.tf`. The adapter now reads JSON configuration with
   `json`, handles `resource`, `data`, `variable` and provider blocks, preserves
   policy-document references for cross-file resolution, and still reports malformed
   JSON as `D-TF-HCL-PARSE`.
3. Policy documents referenced by Terraform resources were resolved only when the
   referenced document happened to be in the same expression shape. Referenced policy
   documents are now retained as references so the role resolver can evaluate them
   across files; unresolved references remain conservative diagnostics.
4. The HTML rotation-plan grid used an implicit grid column sized to max-content, so a
   long identifier in one step widened the whole page at 390 px. The grid now uses
   `minmax(0, 1fr)` and `.step` has `min-width: 0`; a regression test pins both rules.
5. The HTML finding card applied the severity class to the whole article, and the
   light-theme medium colour was #9a6700 at 4.32:1 on the card background. Finding text
   now explicitly uses `var(--ink)`, and the medium colour is #8a5a00 (5.27:1 on the
   card and 5.93:1 on white). axe reports zero violations in both colour schemes.

Post-M8 features added:

- **Cross-scenario exposure matrix.** A deterministic union of credentials across all
  selected scenarios, with R/E/Z status per scenario, sticky headers and row labels,
  a shared-credential filter and clickable status cells that switch to the relevant
  scenario and trace the credential.
- **Shortest-path trace.** A deterministic breadth-first trace from the selected
  scenario's entry nodes to a credential, with ordered hops, edge kind and confidence,
  first evidence, an explicit UNKNOWN warning and graph highlighting. Trace controls
  are keyboard-operable.
- **Findings filtering.** Text, severity and scenario filters with an `aria-live`
  result count.
- **Scenario-aware summary.** The R/E/Z/P summary and claim-hygienic brief follow the
  selected scenario instead of always describing the first one.
- **Python 3.13/3.14 support evidence and CI matrix rows** for both interpreters on
  Ubuntu and Windows. The classifiers now list 3.12, 3.13 and 3.14.

The final local release artifacts are byte-reproducible for this source tree and
toolchain; cross-machine reproducibility is not claimed. After the documentation
edits, the candidate was rebuilt from the documentation-final tree on 2026-10-27 and
`dist/SHA256SUMS` records the digests of that frozen set. The digests are not copied
into a packaged document because the sdist packages the release documentation.
Fresh-environment installation and the secret audit were repeated against the
refreshed artifacts: all six commands exited 0, fx07 produced JSON, SARIF and HTML,
the base wheel reported the documented HCL diagnostic with exit 3 under `--strict`,
the sdist installed and scanned, and the 15 corpus candidates showed no leaks in 44
release/report artifacts. The corpus and soak are observations on this host and are
not external benchmarks or an audit.

### 2026-10-27 — remote CI, Linux, advisory automation and internal audit

| Check | Command / run | Actual result |
| --- | --- | --- |
| Remote CI matrix | https://github.com/DKtech-dev/nhi-blast/actions/runs/40432137207 | Package job and all six test jobs passed with `404 passed` each and coverage 86.53–86.54% on `ubuntu-latest` and `windows-latest` for Python 3.12, 3.13 and 3.14 |
| Linux execution | Ubuntu jobs in the run above | Python 3.12, 3.13 and 3.14 passed, including the real-symlink security test that is skipped on the local Windows host |
| Advisory workflow | https://github.com/DKtech-dev/nhi-blast/actions/runs/40432137192 | Passed: pip-audit on both locks, Bandit, hash-verified OSV-Scanner 2.7.0 and gitleaks 8.30.1; workflow also runs weekly |
| Internal audit | Commands and versions in `docs/security-audit.md` | zizmor 1.31.1: 0 findings; actionlint 1.7.12: 0; Semgrep 1.182.1: 2 triaged false positives; Bandit 1.9.4: 0 medium/high, 11 low triaged; pip-audit 2.10.1: 0; OSV 2.7.0: 0 across 60 instances; Grype 0.121.0: 0 on both SBOMs; pip-licenses: 41 packages, no strong copyleft; gitleaks: 0 in history; TruffleHog 3.99.7: 0 in 96 MB; 42 pins with minimum age 15 days and none yanked |
| Audit fixes | Commits on `main` | Checkout credential persistence removed; broken pip-audit invocation fixed; tomlkit held inside the age policy; fixture identity materialised for clean checkouts; console-script path resolved with `sysconfig`; Python 3.14 JSON test broadened without relaxing the facts check; editable build helper pinned |
| Repository settings | `gh api` on 2026-10-27 | Default workflow token read-only; SHA pinning required; Dependabot alerts and security updates enabled; `protect-main` ruleset blocks deletion and non-fast-forward pushes. After the repository was made public, secret scanning and push protection were enabled, CodeQL default setup was configured, and private vulnerability reporting was enabled; validity checks and non-provider patterns remained disabled at the account level |
| New traceability tests | `pytest tests/test_docs.py tests/test_report_security.py` | 13 passed: assumption registry integrity and documentation match; report templates reject proof/guarantee/exploitability/takeover wording |

### 2026-10-27 — publication record

| Item | Value |
| --- | --- |
| Release | https://github.com/DKtech-dev/nhi-blast/releases/tag/v0.1.0; not a draft, not a pre-release |
| Tag | annotated `v0.1.0` → commit `0269100` (`Pin release evidence to the final CI and audit runs`) |
| Assets | `nhi_blast-0.1.0-py3-none-any.whl`, `nhi_blast-0.1.0.tar.gz`, `SHA256SUMS` |
| Pre-publication gates | remote CI run 40432467328 and audit run 40432467231 passed on `0269100` |
| Verification | assets re-downloaded from the release; `sha256sum -c SHA256SUMS` passed; the digests reported by the release API matched the locally built artifacts and the checksum asset |
| Distribution scope | GitHub Release only; no package-index upload, deployment or SaaS |

### 2026-10-27 — 0.1.1 offline report redesign

| Check | Command / run | Actual result |
| --- | --- | --- |
| Report redesign | `src/nhi_blast/report/ui.py`, `report/html.py`, embedded WOFF2 fonts | Achromatic-ledger layout with viewer bar, entrypoint selector, summary, survival panel, rotation plan, cross-scenario matrix, graph, findings, assumptions, data files and diagnostics; dark/light themes; print layout; Geist and Geist Mono embedded under OFL-1.1; no external request |
| Graph readability | Browser capture at 1440×900 | Dark-theme edge token brightened, per-edge off-path dimming, label backgrounds with ellipsis, zoom-out/zoom-in/fit controls; 24 nodes and 22 edges rendered at 0.843 zoom with readable labels |
| Layout stability | Lighthouse 13.5.0 desktop; CDP performance trace | CLS 0 after the boot gate; FCP 0.9 s, LCP 0.9 s, TBT 10 ms; performance 98, accessibility 100, best-practices 100. Simulated mobile performance 65 is disclosed and attributed to the 841 KiB document over a 1.6 Mbps throttle |
| Accessibility | axe-core 4.10.3 in desktop dark, desktop light and mobile dark | 0 WCAG 2.2 AA violations in all three views; Lighthouse accessibility 100; brand-link accessible name fixed after a label/name mismatch |
| Browser QA | CDP at 1440×900, 768×1024 and 390×844 | 0 overflow, 0 console/log errors, 0 external requests; both fonts loaded and Geist in use; boot gate clears; no-script fallback visible with notice; scenario switching, graph zoom/fit, trace, table scroll and filters exercised |
| HTML validation | html-validate 11.17.0 | Clean |
| Design inspector | 1440, 768 and 390 px | 0 findings |
| Report tests | `pytest tests/test_html.py tests/test_report_security.py` | 24 report tests; CSP hashes five scripts, boot-gate/no-script ordering, font embedding, no external resources, inert hostile strings and secret-leak checks pass; `report/html.py` and `report/ui.py` at 100% coverage |
| Full suite | `pytest -q` | 418 passed, 1 skipped in 23.23 s |
| Python 3.13/3.14 | isolated environments | 416 passed, 1 skipped, 2 deselected plus 2 slow passed on each |
| Coverage gate | `scripts/check_coverage.py` | 86.67% overall; every enforced module ≥80%; lowest `report/explain.py` 83.78% |
| Lint, format, types | ruff 0.15.22, mypy 1.20.2 strict | Clean; 113 files formatted; 71 source files typed |
| Scanners | zizmor 1.31.1, actionlint 1.7.12, Semgrep 1.182.1, Bandit 1.9.4, pip-audit 2.10.1, Grype 0.121.0 | 0 findings in each; B105 skip documented; B101 assert removed; 0 vulnerabilities |
| Remote CI | `ci.yml` run 40509205221 on Ubuntu and Windows, Python 3.12–3.14 | Package job passed; all six test jobs reported `417 passed, 2 deselected` plus `2 passed` for the slow suite, 0 skipped; coverage 86.73–86.74% |
| Remote advisory audit | `audit.yml` run 40509205137 | Passed: both lock audits, Bandit, OSV-Scanner and secret scan |
| Secret scans | gitleaks 8.30.1 history and tree; TruffleHog 3.99.7 | 9 commits / 2.32 MB with no history leaks; 0 verified and 0 unverified TruffleHog secrets; 6 tree hits all triaged to AWS documentation examples inside the gitignored research cache and absent from tracked files |
| Build and artifacts | three hatchling builds; `scripts/check_artifacts.py dist` | Identical wheel and sdist digests across three builds; wheel 92 files, sdist 242 files, including fonts, `OFL.txt` and vendor manifest |
| Clean installs | wheel, wheel with `[hcl]`, sdist | All six commands exit 0; fx10 parses HCL with the extra (14 nodes) and reports `D-TF-HCL-UNAVAILABLE` without it (8 nodes); repeated installed-wheel scans are byte-identical |
| Publication | GitHub Release `v0.1.1` | Published 2026-10-27 from commit `c702d9d`; annotated tag `v0.1.1`; wheel, sdist and `SHA256SUMS` re-downloaded and all checksums verified |

### 2026-10-27 — public repository and proprietary 0.2.0 source

| Check | Command / run | Actual result |
| --- | --- | --- |
| Licence | `LICENSE`, `NOTICE`, `pyproject.toml` | MIT replaced with an all-rights-reserved proprietary licence for this source tree and future releases; the published 0.1.0 and 0.1.1 releases remain MIT; built metadata reports `License-Expression: LicenseRef-Proprietary` with `License-File: LICENSE` and `NOTICE` |
| Version | `src/nhi_blast/__init__.py`, `pyproject.toml`, `tests/golden/fx07-console.txt` | Bumped to 0.2.0; the console golden header updated; JSON schema `nhi-blast-report/1.0` unchanged |
| Local gates | pytest, ruff check, ruff format, mypy strict, schema check | 419 passed, 1 skipped in 15.27 s (the skip is the Windows real-symlink privilege case); ruff clean and 113 files formatted; mypy strict clean over 71 source files; `scripts/gen_schema.py --check` exit 0 |
| 0.2.0 build check | hatchling build to a temporary directory; `scripts/check_artifacts.py` | Wheel 92 files and 1,366,403 bytes; sdist 242 files; proprietary metadata present; no 0.2.0 artifact published. Exact sdist bytes are not pinned because documentation edits change the archive |
| Clean install (0.2.0 wheel) | Fresh venv, `pip install -c requirements.lock`; `version` and `scan` | `nhi-blast 0.2.0`; `fx07-incident` produced JSON (36,953 bytes), SARIF (26,486 bytes) and HTML (858,222 bytes); exit 0 |
| Visibility | `gh repo edit --visibility public`; anonymous HTTP request | `visibility: public`; the repository and the `v0.1.1` release page return HTTP 200 without authentication |
| Secret scanning | `gh api` repository security settings | Secret scanning and push protection enabled; 0 open secret-scanning alerts; validity checks and non-provider patterns remain disabled at the account level |
| CodeQL | `code-scanning/default-setup` and `code-scanning/analyses` | Default setup configured for Actions and Python; analyses on `e00cf81` reported 1 Python result (`py/bad-tag-filter`), fixed in the test helper; analyses on `d26dd14` report 0 results for both languages and 0 open alerts |
| CodeQL fix | `tests/test_html.py` | The regex extractor behind the CSP and injection assertions was replaced with an `HTMLParser` collector that follows browser tag parsing, with `test_script_extractor_matches_browser_tag_syntax` as regression coverage |
| Portability failure and fix | CI run 40514772712; commit `d26dd14` | The synthetic end-tag case failed only on `windows-latest` Python 3.12.10, whose `HTMLParser` rejects junk in end tags; the regression case now uses a whitespace-only end tag that every supported patch level accepts, and all seven jobs passed in run 40515346396 |
| Remote CI (public repository) | https://github.com/DKtech-dev/nhi-blast/actions/runs/40515346396 | Package job and all six test jobs passed on `ubuntu-latest` and `windows-latest`, Python 3.12–3.14: `420 passed` each, coverage 86.73–86.74%; slow suite `2 passed` in every job |
| Remote advisory audit (public repository) | https://github.com/DKtech-dev/nhi-blast/actions/runs/40515346468 | Passed: both lock audits, Bandit, OSV-Scanner and the secret scan |
| Remote CodeQL | https://github.com/DKtech-dev/nhi-blast/actions/runs/40515346395 | Analyze (actions) and Analyze (python) passed; 0 results and 0 open alerts |
| Evidence commit verification | CI 40515887344, audit 40515887316, CodeQL 40515887763 on `074f2ce` | All passed; CodeQL still reported 0 open alerts |
| Dependabot | Pull request #1 | `actions/setup-python` 7.0.0 → 7.1.0 pinned by SHA; all eight checks green; squash-merged as `0d86433` |
| Private vulnerability reporting | `gh api` PUT and GET | Enabled; `SECURITY.md` directs reports there; secret-scanning and Dependabot alert counts are both 0 |

### 2026-10-28 — 0.2.0 report, graph and print redesign

Scope: replace the browser graph layout with deterministic, Python-computed SVG;
redesign the report shell, summary, survival rail, findings and tables; repair print/PDF;
retain the CSP, output escaping, evidence semantics and R/E/Z classifications. This
working tree is not committed or released.

| Check | Command / run | Actual result |
| --- | --- | --- |
| Report, security and graph tests | `pytest -q tests/test_html.py tests/test_report_security.py tests/test_graph_layout.py` | 52 passed in 0.86 s |
| Full suite | `pytest -q` | 436 passed, 1 skipped in 15.71 s; the skip is the Windows real-symlink privilege case |
| Slow suite | `pytest -q -m slow` | 2 passed, 435 deselected in 9.08 s |
| Coverage | `scripts/check_coverage.py` | 87.21% overall; every enforced package ≥80%; `report/ui.py` and `report/html.py` at 100% |
| Lint | `ruff check .` | All checks passed |
| Format | `ruff format --check .` | 115 files already formatted |
| Types | `mypy --strict src` | Success: no issues found in 72 source files |
| Graph layout | `pytest -q tests/test_graph_layout.py` | 10 passed; deterministic byte-stable JSON, stage ordering, no node overlap, confidence classes, entrypoint metadata, no active SVG content, explicit empty state and render-limit message |
| Browser accessibility | `node nhi-blast-out/pw/audit-current.mjs` on the current `nhi-blast-out/readme-shots/report.html` | `AXE clean`, `NAV clean`, `TOUCH clean`, `RUNTIME clean` at 1440×900, 1024×768, 768×1024 and 390×844 with dark and light color-scheme emulation; 0 shown hidden links; no console errors and no external requests. The screen theme is dark-only; light tokens are print-only |
| Graph interaction | `node nhi-blast-out/pw/interact.mjs` | `ALL PASS`: roving focus, spatial arrow navigation, Enter selection, Escape clear, zoom, pan, fit, wheel zoom, pinch and reduced-motion handling; no outbound requests |
| Viewport sweep | `node nhi-blast-out/pw/viewports.mjs` | `ALL VIEWPORTS CLEAN` |
| Multi-scenario report | `node nhi-blast-out/pw/multi.mjs` on `nhi-blast-out/multi07/report.html` | Both scenarios switch correctly; the exposure matrix has a sticky header and first column; axe clean at 1440 light and 390 dark |
| Boot failure | `node nhi-blast-out/pw/bootfail.mjs` on a copy with corrupted embedded JSON | Status shown: "The embedded report data could not be read. Regenerate the report from the NHI-Blast CLI."; `main` hidden; exactly the expected JSON parse console error |
| Print/PDF | Playwright with system Chrome; inspected with PyMuPDF | `report-final.pdf` 16 pages; graph page 8 is A3 landscape with 127 vector drawings; title, summary, survival and rotation text present; print palette and forced-visible reveal states applied |
| HTML validation | `npx html-validate@11.17.0` on the current report | Exit 0, no validation errors |
| Dependency and secret audit | pip-audit 2.10.1 on both locks; gitleaks 8.30.1 on history and the working tree; Bandit 1.9.4 on `src` and `scripts` | No known vulnerabilities; no leaks in 19 commits or the 1.90 MB tracked/untracked non-ignored tree; Bandit 0 medium/high and 2 low (`B404`/`B603` in `scripts/check_coverage.py`, a fixed `subprocess.run` without a shell), reviewed as accepted |
| Document reduction | renderer, manifest and artifact-check tests | Cytoscape, dagre and cytoscape-dagre removed; the authority graph is Python-computed SVG; `MANIFEST.json` pins the fonts and the Motion runtime; the CSP hashes three inline scripts (embedded data, Motion runtime and application code) |
| Motion vendor | `src/nhi_blast/report/assets/vendor`, `MANIFEST.json`, `report/html.py` | Official Motion 14.7.1 UMD, 176,646 bytes, SHA-256 `9d626ab329c703b3fa824651166973900fd425a84b752f2f53411ad85b3e923e`, MIT licence shipped; embedded inline under its own CSP hash; validator rejects an unpinned asset set, version, global, licence, source host, digest, non-UTF-8 payload or closing script tag |
| Motion runtime checks | `node motionverify.mjs`; `node kpiverify.mjs`; `node presenceverify.mjs` | `window.Motion.animate` is a function; title opacity 0→1 with 8px displacement; header atmosphere CSS variables 0→0.6/0.55; three first-view reveals 0→1; real scenario change called `Motion.animate` numerically with value callbacks; graph detail panel faded and translated in; zero console errors and zero external requests |
| Reduced motion | `node motionverify.mjs` with `reducedMotion: 'reduce'` | Media query matches, `MotionGlobalConfig.skipAnimations` true, title and atmosphere at final values, zero reveal targets hidden, no overflow at 390×844 |
| Keyboard and navigation | `node keyboardnav2.mjs`; `node navcheck2.mjs` | Keyboard focus reached the Findings nav link with a 2px visible outline; Enter activated `#findings`; the persistent indicator tracked every section at 1440, 1024, 768 and 390; graph arrow navigation and Enter selection still pass |
| Motion tooling | `npx motion-ai` installer | The installer does not offer Qoder; the official Motion skill content was copied manually into the gitignored `.agents/skills/motion` directory and used for guidance. The report vendors only the free core runtime, with no Motion+ features and no duplicate animation library |
| Header spacing | Browser measurement at 1440, 1024, 768 and 390 px | `#finding-lead { margin-top: 20px; }` adds exactly 20 px between the "Review rotation order" button and the critical-finding banner at every width, with no overlap and no horizontal overflow |
| Identity artwork | `assets/readme`, `node render.mjs` with system Chrome | Banner in dark and light; both README report screenshots were recaptured from the final 502,204-byte fx07 report (input digest `bfa811ede0aa`): the 1600×1500 summary/survival view and a 1600×1200 graph view. The recaptured files are byte-identical to the reviewed assets. The social preview is 1280×640 (126,310 bytes) and composes a genuine summary/survival crop of that report inside the typographic card; the stale light social variant and old report image were removed. The social card audited clean at 1280×640 with three fonts loaded, no overflow and no console errors |
| Build and artifacts | hatchling wheel/sdist into scratch directories; `scripts/check_artifacts.py` | Final tree: wheel 94 files (997,889 bytes uncompressed, SHA-256 `47ead0ee400a…`), sdist 246 files; both digests identical across three builds from the frozen tree; artifact check passed. The sdist digest is not pinned because this file is itself part of the archive. The checker found the Motion runtime, its MIT licence and every font; the sdist allowlist permits the intentional `assets/` tree and still rejects scratch roots; no forbidden cache, scratch or private-cache content |
| Clean install | fresh venvs: wheel with and without the HCL extra, and sdist with HCL; `version`, `scan`, `rank`, `export`, `explain`, `schema` | `nhi-blast 0.2.0`; fx07 generated a 502,204-byte HTML report that is byte-identical across repeated runs (SHA-256 `62cec746268b…`); JSON and SARIF were also byte-identical; fx10 produced 14 nodes with HCL versus 8 without, and the strict no-HCL run exited 3; `pip check` clean in every environment |

Known limitations at this checkpoint: the Vermilion Noir and Motion changes are
uncommitted; no 0.2.0 artifact has been published; the independent human audit remains
not performed and is not claimed. Browser checks used headless Chromium (including a
390×844 mobile emulation and reduced-motion emulation), not Firefox, Safari or a
physical printer; the Chromium PDFs were inspected programmatically and as images. The
refreshed identity artwork is present in the working tree, but the GitHub social preview
has not been uploaded and no repository metadata has been changed; those are external
actions requiring owner authorization.

## Next action

No implementation or publication task remains for 0.1.1. Remote CI, Linux execution,
advisory automation, the internal audit and the authorized 0.1.0 and 0.1.1 GitHub
Releases are complete. The repository was made public and the source tree relicensed as
proprietary 0.2.0 on 2026-10-27; no 0.2.0 artifact has been published. The 0.2.0 report
and graph redesign passed the local gates recorded above and still needs a reviewed
commit, a rebuilt artifact set and, if the owner authorizes a release, a new tag. The
remaining assurance actions are:

1. **Independent human audit.** This cannot be supplied by the implementation agent.
   `docs/external-audit-package.md` defines the target and materials; until a reviewer
   completes a report, the project must not be described as independently audited.
2. **Release maintenance.** Review Dependabot updates, refresh the lock files on a
   deliberate cadence, and re-run the full gate set before any later release. Platform
   secret scanning, push protection, CodeQL default setup and private vulnerability
   reporting are enabled; secret-scanning validity checks and non-provider patterns
   remain disabled at the account level and are not claimed.

## Final continuation evidence — 2026-10-29

Final working tree based on `7ea7c19`: four boundary/analytical defects were repaired
with regression tests — export confirmation path redaction, per-statement trust-audit
provenance (policy-wide flags no longer broaden matched edges), corpus harness
referential integrity, and an explicit interpreter-independent JSON nesting limit
because CPython 3.14 no longer raises `RecursionError` for hostile deep input. The
repairs are covered by `tests/test_output_redaction.py`,
`tests/test_trust_boundary_regressions.py`, `tests/test_benchmark_corpus.py` and
`tests/test_cloud_parser_regressions.py`.

Executed on this tree: full suite **751 passed, 2 skipped** on Python 3.12.14, 3.13.17
and 3.14.7; slow suite **2 passed**; ruff check/format clean; `mypy --strict` clean in 80
files; schema check exit 0; coverage **88.73%**; Bandit 0 medium/high (23 low, triaged);
pip-audit 0 on both locks; Semgrep `p/ci`+`p/python` 0 findings; zizmor 0 (2 disclosed
suppressions) and actionlint 0 on production workflows; wheel/sdist artifact check passed
(wheel 97 files, SHA-256 `97bc7238c09c…`); fresh wheel `[hcl]` install with clean
`pip check`; installed CLI **42/42** expected exits and 14 labelled synthetic cases
(TP 8, FP 0, FN 0, TN 6); **15/15** corpus datasets deterministic over two repeats
(3,620 files, 0 errors); headless Chrome/axe **44/44** checks with 0 violations in eight
viewport/theme views and a 609,273-byte PDF.

Known gaps: Linux/macOS were not executed locally for this tree and the recorded remote
CI predates it; browser verification used headless Chrome only; the labelled sample is
small and synthetic, not public-corpus ground truth; the independent human audit remains
not performed and is not claimed; no release was published. This tree was committed to
`audit/nhi-blast-2026-10-29` after verification.

## Independent audit continuation — 2026-10-29

A further independent pass reproduced two defects and fixed both with failing-first
regression tests. **F-01**: a `nhi-blast.toml` containing an integer literal longer than
CPython's 4,300-digit conversion limit raised a bare `ValueError` through `tomllib`,
surfacing as `internal error: ValueError` (exit 4); `Config.from_file` now maps every
parser-level `ValueError`/`RecursionError` to the sanitized `ConfigError`, so the CLI
returns exit 2 (`tests/test_input_limit_regressions.py`). **F-02**: axe-core found the
report utility bar outside every landmark; the viewer bar is now
`role="region" aria-label="Report controls"` (`tests/test_html.py`). A synthetic PEM
header in a redaction test was assembled at runtime so gitleaks stays strict without an
allowlist.

Re-executed on the final tree: full suite **752 passed, 2 skipped** on Python 3.12.14,
3.13.17 and 3.14.7; slow suite **2 passed**; ruff/format clean; `mypy src` clean (75
files); schema exit 0; coverage **88.73%** and gate passed; Bandit, pip-audit (both
locks), Semgrep (`p/ci`+`p/python`), zizmor, actionlint and gitleaks (276 files) all
clean; two wheel/sdist builds byte-identical (wheel SHA-256 `ec2c02a6…`, sdist
`5f6378b2…`); wheel and sdist installs both reject the hostile config with exit 2;
installed verification 42 commands and 14 labelled cases (TP 8, FP 0, FN 0, TN 6);
installed and working-tree reports byte-identical; corpus **15/15** datasets
deterministic; axe 0 violations in light and dark; headless Chrome no console errors,
exceptions or network requests at 1440×900 and 390×844; PDF 10 pages, 888,067 bytes.

Gaps unchanged: no Linux/macOS execution for this tree, remote CI predates it, browser
verification is headless Chrome only, the labelled sample is synthetic, no human audit
was performed, and no release was published. This tree is recorded on
`audit/nhi-blast-2026-10-29`.

## Low-severity remediation — 2026-10-29

The independent review of `b85f012` reported no confirmed vulnerabilities or
release-blocking defects and three low-severity observations. All three are addressed
with failing-first regression tests on `audit/nhi-blast-2026-10-29`.

**AUD-01 — reproducible labelled evaluation.** The 14 labelled synthetic cases and
their expected results were recovered verbatim from the audit harness
(`verify_installed_final_r2.py`, case table at lines 48-75) and are now static scan
roots under `tests/fixtures/labelled/`. `cases.json` records each rule, expectation,
rationale and the provenance; expectations are never regenerated from scanner output.
The synthetic-literal token is stored as YAML `\u005A` escapes, so the repository
holds no token-shaped text while YAML decoding still supplies the harness value.
`scripts/evaluate_labelled.py` runs the real pipeline in-process with the harness
settings, prints one result per case plus TP/FP/FN/TN, exits 1 on any mismatch and
writes a deterministic JSON summary with `--json-out`. `tests/test_labelled_evaluation.py`
requires TP 8 / FP 0 / FN 0 / TN 6 twice with identical summaries. A deliberate
expectation flip makes the script exit 1, so the check is not self-fulfilling.
`docs/testing.md` records that the sample is synthetic, covers 8 rules, asserts one
rule per case and is not real-world precision, recall or ground truth.

**AUD-03 — redaction recursion.** `redact_payload` traversed payloads recursively; a
5,000-level payload raised `RecursionError`, and a non-string mapping key raised
`TypeError` from the literal regex. Collection and rewriting are now iterative,
preserving identifier cross-references, hashed keys, idempotence and non-JSON value
identity. Tests cover 5,000-level nesting, non-string keys and opaque objects, and a
200-level normal payload (`tests/test_output_redaction.py`).

**AUD-04 — diagnostic quoting.** Permission diagnostics interpolated `scope_name` into
warning text. Every reachable value is a known data-file scope because unknown keys
take a generic diagnostic, so this was defence in depth; `_scope_label` now returns
plain scope names bare and quotes/escapes everything else to ASCII, including control,
bidi and non-ASCII characters. Tests cover plain names, quotes, backslashes, control
characters, non-ASCII text, the empty string and repeated-diagnostic consistency
(`tests/test_permission_diagnostics.py`).

Re-executed on this tree: full suite **770 passed, 2 skipped** on Python 3.12.14,
3.13.17 and 3.14.7; security subset **182 passed, 1 skipped**; slow suite **2 passed**;
ruff check/format clean (130 files); `mypy src` clean (75 files); schema exit 0;
coverage **88.76%** and gate passed; Bandit 0 (all severities, 16,838 LOC), pip-audit
0 on both locks, Semgrep `p/ci`+`p/python` 0 findings (164 rules, 86 files), zizmor
1.31.1 0, actionlint exit 0, gitleaks 0 leaks across 300 committable files (2.86 MB);
wheel and sdist built twice byte-identically (wheel SHA-256 `eba5a1cfffad…`, 97 files;
sdist `b9dddabdc7ac…`, 284 files) and the artifact check passed; fresh wheel install
with clean `pip check`, CLI version/version --data/schema/scan/rank/export/explain
exercised; installed verification **42/42** expected exits and **14/14** recovered
labelled cases through the installed CLI; the evaluation script also passes against the
installed wheel (TP 8, FP 0, FN 0, TN 6); corpus **15/15** datasets deterministic over
two repeats (3,620 files, 0 failures).

Gaps unchanged: no Linux/macOS execution for this tree, remote CI predates it, browser
verification was not re-run because no report serialization or UI code changed, the
labelled sample is synthetic and is not real-world accuracy, no human audit was
performed, and no release was published.

## Windows CI entrypoint resolution — 2026-10-29

The `cli` fixture in `tests/test_benchmark_corpus.py` derived the installed console
script from `Path(sys.executable).parent`. That assumption only holds in virtual
environments, where `python.exe` itself lives in `Scripts`. GitHub-hosted runners use
the python.org layout: `python.exe` sits at the toolcache prefix root and pip installs
console scripts into `<prefix>/Scripts`. Run 40806824836 (`pull_request`, SHA
`820549d`) therefore ended with 744 passed and 28 fixture errors on every Windows job
while all Ubuntu jobs passed. `tests/test_cli.py::test_installed_console_script_runs`
already resolved through `sysconfig.get_path("scripts")` and passed on those same
runs, which confirms the entrypoint was installed at
`C:/hostedtoolcache/windows/Python/<version>/x64/Scripts/nhi-blast.exe`; the workflow
install step needed no change. A wheel installed into a temporary nt-scheme prefix
reproduced the same location (`Scripts/nhi-blast.exe`, nothing beside the interpreter).

`tests/entrypoint_support.py` now provides one resolver: the interpreter's configured
scripts directory (sysconfig), then `shutil.which`, then the legacy directory beside
`python.exe`. It accepts only an existing regular file and raises
`EntrypointNotFoundError` naming the interpreter and every searched path. The corpus
fixture and `tests/test_cli.py` both use it. Seven regression tests cover the
toolcache layout, the POSIX layout, precedence, the PATH fallback, the
interpreter-adjacent fallback, the missing-entrypoint diagnostic (including a
directory bearing the entrypoint name) and Windows `.exe` naming
(`tests/test_entrypoint_support.py`). No Windows skip, weakened assertion or
source-import substitution was introduced.

Re-executed on this tree: full suite **777 passed, 2 skipped** on Python 3.12.14,
3.13.17 and 3.14.7; security subset **182 passed, 1 skipped**; slow suite **2 passed**;
ruff check/format clean (132 files); `mypy src` clean (75 files); schema exit 0;
coverage **89%** and gate passed; wheel rebuilt byte-identically (`eba5a1cfffad…`,
97 files; unchanged because no runtime code changed), sdist `887d485e…` (286 files),
artifact check passed; a fresh consumer install passed `pip check`, `version`,
`version --data`, `schema` and an fx07 scan producing JSON, SARIF and HTML. CI run
40881803232 on commit `6559488` then passed all six test jobs (Ubuntu and Windows,
Python 3.12-3.14), including the installed-CLI integration tests that had failed in
run 40806824836, and the package job; the advisory workflow (run 40881803387) also
passed. The GitHub-hosted Windows toolcache was not reproduced locally; that remote
run is the evidence for the toolcache layout.
