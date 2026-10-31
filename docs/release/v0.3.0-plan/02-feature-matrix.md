# 2. Existing feature completion matrix

Status key:
- **DONE**: implemented and tested.
- **PARTIAL**: exists, but with a gap.
- **ABSENT**: no code.

| Capability | Evidence (path:line) | Status | Gap for v0.3.0 |
|---|---|---|---|
| CLI scan/rank/explain/export/schema/version | `cli/app.py:21-26`, `cli/commands.py` | DONE | No `diff` or `whatif` command |
| Exit codes 0–4, `--fail-on`, `--strict` | `pipeline.py:637` | DONE | Needs diff exit semantics |
| Evidence classes DECLARED>DERIVED>ASSUMED>UNKNOWN | `core/evidence.py:17`; edge confidence = weakest | DONE | — |
| R/E/Z partition + bounded Z closure (depth 3) | `analysis/partition.py:114-164` | DONE | E TTL defaults to 3600 s unless declared |
| UNKNOWN outside R/E/Z (`potential`) | `partition.py:69`, `reach.potential_reach` | DONE | — |
| Rotation plan (SCC batches) | `analysis/rotation.py:296`; containment text `:211-270` | PARTIAL | Containment is prose, not a model |
| Scenario graph transforms | `analysis/scenario.py:74-212` | DONE | Reusable for what-if |
| Selectors (action, job, workflow, secret, role, repo-write, fork-pr, all-mutable) | `analysis/selectors.py` | DONE | — |
| Condition operators: String/Arn/negatives/Bool/Null/IfExists/ForAny/ForAll | `aws/conditions.py:39-54` | PARTIAL | Numeric/Date/IpAddress/Binary → UNRESOLVED |
| Explicit-deny precedence | `aws/policy_eval.py` | DONE | — |
| Permissions boundary (when supplied) | `policy_eval.py:228-265` | PARTIAL | Missing boundary reported as `A-NO-SCP` (mislabelled) |
| KMS caller-side `kms:Decrypt` | `policy_eval.py:355-378` | PARTIAL | Key policies/grants unmodelled (`A-KMS-UNMODELLED`) |
| SCP/RCP, session, resource policies | — | ABSENT | Assumption only |
| Role chaining | `docs/known-limitations.md:55` | ABSENT (out of scope) | Defer, with a design note |
| OIDC classic + immutable subjects | `oidc/github_subject.py:185-186` | PARTIAL | Immutable IDs wildcarded (`@*`); no ID binding |
| `configure-aws-credentials` inputs (`role-duration-seconds`, session policies) | grep: no matches | ABSENT | Declared TTL and session narrowing ignored |
| Reusable workflows, local composites, `secrets: inherit` | `resolvers/`; fx06, fx13 | DONE | Remote callees use the caller grant only |
| Environment / branch protection | `A-ENV-UNPROTECTED`, `A-REPO-WRITE` | ABSENT | No offline context input |
| Terraform plan/state JSON, child modules, unknown/sensitive | `parsers/terraform/tfjson.py:102,241,265` | DONE | — |
| HCL fallback | `tfhcl.py:378-437` | PARTIAL | `module` blocks only flagged |
| Typed diagnostics, limits, truncation | `core/diagnostics`, `core/limits.py:19`, `GraphBuild.truncated` | DONE | No per-input-family view |
| Completeness model | grep: none | ABSENT | Stage A |
| Report diff / baseline | grep: none | ABSENT | Stage B |
| What-if / playbook | grep: none | ABSENT | Stage C |
| Stable IDs | `core/ids.py` | PARTIAL | Edge/finding IDs include line numbers (`evidence.py:75-86`) |
| SARIF 2.1.0 + partialFingerprint | `report/sarif.py:78-88` | DONE | Fingerprint ignores scenario |
| HTML report (CSP hashes, JSON island, search/filters, graph zoom, matrix, trace) | `report/html.py:151-198`, `report/ui.py` (3,078 lines) | DONE | Dark theme only; no graph list fallback; no completeness panel |
| Labelled harness | `tests/fixtures/labelled/cases.json` (14 cases / 8 rules), `scripts/evaluate_labelled.py` | PARTIAL | Small, synthetic, rules-only |
| Pinned public corpus | `scripts/corpus_manifest.json` (14 repos + self), `scripts/benchmark_corpus.py` | PARTIAL | No labels; not published in docs |
| No-network test | `tests/test_determinism.py:116-126` | DONE | — |
| No-subprocess runtime test | — | ABSENT | Static claim only |
| Browser/a11y automation | — | ABSENT | Only one-off manual runs |
| CI: ubuntu+windows × 3.12–3.14, audit, Windows exe | `.github/workflows/ci.yml`, `audit.yml`, `build-windows.yml` | DONE | No macOS; no release workflow |
| PyPI, SBOM in CI, attestations, signing | — | ABSENT | Stage E (name `nhi-blast` currently returns 404 on PyPI) |
| GitHub Action | — | ABSENT | Stage F |
