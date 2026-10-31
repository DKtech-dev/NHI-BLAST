# 4. Proposed architecture

**Principles:**
- Keep the existing pipeline: discovery → parsers → resolvers → graph → analysis → reporters.
- Add three thin layers on top of the existing report model: completeness, diff and what-if.
- No new runtime dependencies.
- One source of truth per concept.

### 4.1 Schema strategy: additive `nhi-blast-report/1.1`

- `src/nhi_blast/__init__.py`: `SCHEMA_VERSION = "nhi-blast-report/1.1"` and `READABLE_SCHEMAS = {".../1.0", ".../1.1"}`.
- New optional `Report` fields in `core/models.py:504`:
  - `completeness: Completeness | None`
  - `context: ReportContext | None`. `ReportContext` holds `config_digest`, `ignore_rules`, `ignore_paths`, `limits`, `max_depth`, `selectors`, `data_versions`.
- New optional `ScenarioReport` field: `completeness_refs: tuple[str, ...]`.
- `extra="forbid"` stays. The 1.0 semantics are unchanged.
- `scope_and_limits` stays as human prose, but is generated from `completeness` so the two cannot disagree.
- New `report/loader.py` takes over `explain.load_report` (`explain.py:24-53`) and accepts `READABLE_SCHEMAS`. It is used by explain, diff and whatif.
- Freeze `docs/schema/report-1.0.json` and add a golden 1.0 fixture load test. Regenerate the 1.1 schema with `scripts/gen_schema.py`.

### 4.2 Evidence-completeness model (Stage A)

New module `core/completeness.py`. Frozen pydantic models:
- `CompletenessStatus`: `analysed | partially_analysed | not_provided | not_supported | not_applicable` (the brief's exact five states).
- `InputFamily`:

  | Group | Families |
  |---|---|
  | GitHub Actions | `gha_workflows`, `gha_local_composites`, `gha_remote_callees` |
  | GitHub context | `gh_environment_protection`, `gh_branch_protection`, `oidc_subject_binding` |
  | Terraform | `tf_plan_state`, `tf_hcl`, `tf_local_modules` |
  | IAM policies | `iam_identity_policies`, `iam_managed_policy_bodies`, `iam_permission_boundaries`, `iam_session_policies` |
  | Organisation / resource | `aws_org_policies` (SCP/RCP), `aws_resource_policies`, `kms_key_policies` |
  | Not supported offline | `aws_role_chaining`, `live_cloud_state` |

- `CompletenessItem{id, family, status, sources: [{path, sha256}], parser_version, diagnostics: [code], assumptions: [id], scope: "report" | scenario selectors, explanation}`.
- `Completeness{items, digest}`, where the digest is SHA-256 over canonical items.

The derivation is a pure function, `derive_completeness(loaded, parsed, build, assumptions, diagnostics) -> Completeness`. It is called in `pipeline.run_scan` next to `_collect_assumptions` (`pipeline.py:671-721`).

Mapping table: `CODE_TO_FAMILY` in `core/completeness.py`, keyed by `D-*` and `A-*` code. A test fails if any code that is registered or emitted is unmapped. Examples:

| Code | Result |
|---|---|
| `A-POLICY-UNMODELLED` | `iam_managed_policy_bodies` → `partially_analysed` |
| `A-KMS-UNMODELLED` | `kms_key_policies` → `not_provided` |
| `D-TF-HCL-LIMIT` | `tf_hcl` → `partially_analysed` |
| Missing boundary | `iam_permission_boundaries` → `not_provided`. The `A-NO-SCP` misuse is split into new `A-NO-BOUNDARY`; the old id is kept registered for 1.0 reports. |
| Role chaining | always `not_supported` |

Scope honesty:
- Items are report-level by default.
- A scenario references a family only when its reached edges depend on it, using an edge-kind → family map (for example `CAN_ASSUME` → IAM families and `oidc_subject_binding`).
- No percentages and no "complete" badge.

### 4.3 Canonical diff and reviewed baseline (Stage B)

New package `src/nhi_blast/diff/`:
- `keys.py`: logical finding key `lk = sha256(rule | scenario selector | sorted path node ids | primary evidence file)`.
  - Node IDs are semantic, so the key is line-insensitive.
  - Findings sharing an `lk` are paired deterministically by (evidence snippet hash, line). Any unmatched surplus is reported with `ambiguous_match: true`.
  - Never pair across rule or scenario.
  - Graph diff: nodes by ID, edges by `(kind, src, dst)`. Edge IDs are not used.
- `compare.py`: comparability classification.
  - `incomparable`: unreadable or major schema mismatch, a different `repo_slug`, or disjoint selector sets.
  - `comparable_with_drift`: tool or data version change, a completeness digest or status change, a config digest change, a selector added or removed, or 1.0 compared with 1.1.
  - `comparable`: none of the above.
- **"Resolved" rule:** a finding is `resolved` only if all of the following hold. Otherwise it is `not_observed`, with reasons.
  1. The pair is `comparable`, or its drift is limited to tool/data version.
  2. HEAD has the same scenario.
  3. That scenario has `truncated = false` and no new `unresolved_inputs`.
  4. No family the finding depends on dropped to `not_provided`, `partially_analysed` or `not_supported`.
- Classes:
  - Findings: `new`, `resolved`, `not_observed`, `unchanged`, `changed` (severity, confidence, evidence or path).
  - Paths: added, removed, changed.
  - Per scenario: R/E/Z membership in and out, survival-window changes, rotation-dependency changes.
  - `context_drift[]`.
- `render.py`: canonical JSON (`nhi-blast-diff/1.0`), console and HTML (see section 8).
- Baseline file `nhi-blast-baseline/1.0`: `{created_from_report_digest, entries[{lk, rule, scenario, reason, reviewer, expires?}]}`, sorted with no timestamps.
  - Baseline entries suppress only `new` findings in exit-code evaluation. They never suppress diagnostics, completeness or drift.
  - An expired entry stops suppressing and produces a diagnostic.
  - The baseline is never auto-written. Entries are added with `nhi-blast baseline accept LK --reason ...`. `nhi-blast baseline prune` removes only `resolved` entries.
- CLI: `nhi-blast diff BASE.json HEAD.json [--baseline F] [--fail-on SEVERITY] [--format console|json|html] [--out DIR]`. Exit codes:

  | Code | Meaning |
  |---|---|
  | 0 | No new findings at or above the threshold after baseline suppression |
  | 1 | New findings at or above the threshold |
  | 2 | Usage or input error |
  | 3 | Incomparable |
  | 4 | Internal error |

### 4.4 Offline containment what-if and playbook (Stage C)

**Approach:** run on a saved 1.1 report. No re-parse is needed, because `GraphData` serialises node attrs (lifetime, ttl_seconds, criticality) and edge confidence (`core/models.py:184-220`). `analyze_scenario(graph, ...)` (`analysis/scenario.py:215`) needs only the graph, start nodes, limits and config. Config comes from `ReportContext`. A 1.0 report is rejected with exit 2 and the message "re-scan with ≥0.3.0".

New package `src/nhi_blast/whatif/`:
- `plan.py`: intervention plan file `nhi-blast-interventions/1.0` (JSON or YAML via SafeLoader). It contains an ordered list. Unknown types fail closed with `{type, reason: "unsupported"}`.
- `engine.py`, `apply(graph, plan) -> (GraphData, InterventionLog)`:
  - First, a replay self-check: re-running the untouched graph must reproduce the saved partitions exactly. If not, emit `D-WHATIF-REPLAY-MISMATCH` and abort.
  - Then re-run `analyze_scenario`, `partition_graph` and `plan_rotation` per scenario.

| Intervention | Model effect | Explicitly not changed |
|---|---|---|
| `disable_entrypoint(node)` | Removes trigger/execution edges from the entrypoint for future runs | E sessions stay, labelled `issued_before_containment` with ≤TTL remaining. Z is unchanged. |
| `remove_trust(role, principal/edge)` | Deletes that `CAN_ASSUME`/`AUTHENTICATES_AS` edge | Already-issued sessions stay `issued_before_containment` |
| `revoke_role_sessions(role)` | E entries for that role become `revoked` (AWSRevokeOlderSessions / `aws:TokenIssueTime` semantics, A2) | Future assumption (needs `remove_trust`); persistent keys |
| `rotate_credential(cred)` | The Z credential becomes `rotated` | If any surviving path still reaches its store (`CAN_READ_VALUE`→`STORES`), it stays in Z with `re_exposure_risk` |

- Rejected for v0.3.0, with reasons:
  - Arbitrary deny-policy injection. The evaluator cannot compose SCP/RCP yet.
  - Min-cut suggestions.
  - Anything mutating live systems.
- Output: `nhi-blast-whatif/1.0` = `{source_report_digest, plan_digest, steps[], per_scenario[{selector, before{R,E,Z}, after{R,E,Z, issued_before_containment, revoked, re_exposure_risk}, residual_paths, potential, completeness_refs}], rejected[], warnings[]}`.
- `playbook.py`: a Markdown playbook in this order:
  1. Revoke sessions.
  2. Remove trust or disable the entrypoint.
  3. Rotate in `plan_rotation` SCC order.
  4. Verify.

  Each step has an owner placeholder, evidence references, a human verification task, and rollback/validation notes. The header says: "Offline model. Not executed. Verify in your account."
- CLI: `nhi-blast whatif REPORT.json --plan PLAN.json [--format json|md|html] [--out DIR]`. The original report is never modified.

### 4.5 Targeted semantic depth (Stage D): decided cut

**MUST:**
1. **Condition operators** Numeric*, Date*, IpAddress/NotIpAddress, Binary* in `aws/conditions.py`.
   - Three-valued logic per A4/A4b: missing key, IfExists, negation, Null and malformed operand (→ UNRESOLVED plus diagnostic).
   - The concrete context remains empty unless declared, so most results stay conditional. The gain is correctness and explicit reasons.
2. **`configure-aws-credentials` declared inputs** (`resolvers/roles.py` and builder):
   - `role-duration-seconds` sets a DECLARED E TTL instead of the `A-STS-TTL` default.
   - `inline-session-policy` / `managed-session-policies` are intersection-only narrowing, feeding `iam_session_policies`.
   - `role-chaining: true` is recorded as `not_supported`.
3. **Immutable OIDC binding:** config `[github] owner_id`, `repo_id` (integers) makes `oidc/github_subject.py` emit definite immutable subjects and clears `A-REPO-AGE`.
4. **Offline GitHub context file** `nhi-blast-gh-context/1.0` via `--github-context FILE` or config. It holds environments (required reviewers, deployment branch policy), branch-protection presence, `captured_at` and source.
   - It feeds `A-ENV-UNPROTECTED` and the `gh_environment_protection` / `gh_branch_protection` items.
   - It is never fetched by the tool. The docs give a manual `gh api` recipe for the user to run.

**DEFER to v0.4**, recorded in `docs/roadmap.md` and marked `not_supported` in completeness:
- SCP/RCP composition.
- Resource policies.
- Remote reusable-workflow snapshots.
- HCL local-module expansion. Plan JSON already covers modules correctly, and partial HCL expansion risks confident wrong edges.
- Role chaining. A design note is included: caller-side `sts:AssumeRole` plus target trust, the 1 h chained cap, depth/cycle budget, and IAMVulnerable-derived fixtures.

### 4.6 Packaging and provenance (Stage E)

- Version `0.3.0b1` (PEP 440). Tag `v0.3.0-beta.1`. Label "v0.3.0 Beta".
- New `.github/workflows/release.yml`, triggered on tag or dispatch:
  1. `build`: wheel and sdist with `SOURCE_DATE_EPOCH`, `check_artifacts.py`, clean-venv smoke (scan fx07 → JSON/SARIF/HTML), `SHA256SUMS`, CycloneDX SBOM via `cyclonedx-py`.
  2. `windows-exe`: reuse `build-windows.yml` via `workflow_call`.
  3. `attest`: `actions/attest-build-provenance` (`id-token: write` and `attestations: write` in this job only).
  4. `publish-testpypi` (environment `testpypi`), then `publish-pypi` (environment `pypi`, required reviewer), both via `pypa/gh-action-pypi-publish` with Trusted Publishing and default PEP 740 attestations.
  5. `github-release`: a draft only.
- Every action is pinned to a full SHA. `tests/test_ci_pins.py` is extended to cover the new workflows.
- Docs: `docs/install.md` (`pipx` / `uvx` / `pip`) and `docs/verify-release.md` (`gh attestation verify`, `sha256sum -c`, SBOM).
- Owner-only steps: register pending trusted publishers on PyPI and TestPyPI, create the protected environments, approve the publish.

### 4.7 GitHub Action (Stage F): `action/action.yml` in this repository

- A composite action used as `DKtech-dev/nhi-blast/action@<full-sha>`.
- Inputs: `path`, `version` (exact `nhi-blast` version, required), `fail-on`, `selector`, `baseline`, `sarif` (bool), `artifact` (bool).
- Steps:
  1. `setup-python` pinned by SHA.
  2. `pip install nhi-blast==<version>` with a hash-pinned requirements file shipped per release (`action/requirements-<version>.txt`).
  3. Run `nhi-blast scan` (and `diff` when a baseline is given).
  4. Optionally `codeql-action/upload-sarif`, pinned by SHA, skipped when `github.event.pull_request.head.repo.fork == true`.
  5. Optionally `upload-artifact`, with a sensitivity warning.
- The CLI exit code is preserved.
- No `id-token: write`, no `pull_request_target`, no PR comments.
- Documented permissions: `contents: read`, plus `security-events: write` only for SARIF.
- Example workflows and `docs/github-action.md`.
- A Marketplace listing would need a separate root-`action.yml` repo; that is deferred to the owner.
