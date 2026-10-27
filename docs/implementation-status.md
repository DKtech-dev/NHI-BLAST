# Implementation status

Living record of what is actually built and verified. Every row must correspond to a
command that was run, with its real result. When a gate is not met, it says so.

Last updated: 2026-10-27
Overall verdict: **0.1.1 RELEASED; 0.1.0 remains available.**
M0–M8 are implemented and verified locally and in remote CI, including packaging,
clean-environment installation, documentation, CI policy, dependency and secret audits,
three-build reproducibility, Python 3.12/3.13/3.14 suites on Ubuntu and Windows, a
10-repository real-world corpus, an adversarial soak, real-browser/axe verification, an
internal security audit with third-party scanners, and the 0.1.1 report redesign with
Lighthouse, html-validate and design-inspector verification. Version 0.1.0 was
published on 2026-10-27 from commit `0269100`; version 0.1.1 was published the same day
from commit `c702d9d` as the GitHub Release `v0.1.1`, after green CI run 40509205221 and
audit run 40509205137, with all assets re-downloaded and verified against `SHA256SUMS`.
The independent human audit has not been performed and is not claimed; it is the one
open assurance gate.

## Environment used for every recorded result

| Item | Value |
| --- | --- |
| OS | Windows 10.0.26200 (x64), Git Bash |
| Python | 3.12.14 (`C:/Cyber/.venv/Scripts/python.exe`); also 3.13.17 and 3.14.7 in isolated environments for the final matrix |
| pip | 26.2.2 |
| CLI dependencies | Typer 0.20.1, Click 8.4.2 (Click pinned below 8.5 because Typer imports deprecated `click.utils` shims and tests treat warnings as errors) |
| Repository state | private GitHub repository `DKtech-dev/nhi-blast`, branch `main`; commits pushed and CI/audit workflows active |

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
| Repository settings | `gh api` on 2026-10-27 | Default workflow token read-only; SHA pinning required; Dependabot alerts and security updates enabled; `protect-main` ruleset blocks deletion and non-fast-forward pushes; secret scanning and CodeQL unavailable without Advanced Security |
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

## Next action

No implementation or publication task remains for 0.1.1. Remote CI, Linux execution,
advisory automation, the internal audit and the authorized 0.1.0 and 0.1.1 GitHub
Releases are complete. The remaining actions are:

1. **Independent human audit.** This cannot be supplied by the implementation agent.
   `docs/external-audit-package.md` defines the target and materials; until a reviewer
   completes a report, the project must not be described as independently audited.
2. **Release maintenance.** Review Dependabot updates after `0.1.1`, refresh the lock
   files on a deliberate cadence, and re-run the full gate set before any later
   release. Secret scanning and CodeQL remain unavailable on the private repository
   unless GitHub Advanced Security is enabled.
