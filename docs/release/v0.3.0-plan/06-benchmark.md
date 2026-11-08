# 6. Benchmark and dataset methodology: NHI-Blast Open Evaluation Corpus v1

> **Revised 2026-11-02.** Where this part conflicts with [12-revision-2.md](12-revision-2.md) (final design review: corrections, deviations, verified sources) or [11-ui-direction.md](11-ui-direction.md), those documents win. See the implementation log for what was built.

Name and status: a project-created benchmark. It is not an official or industry-standard benchmark, because none exists (section 3.4).

### Tier T0: semantic oracle conformance (fast, in the default suite)

- `tests/oracles/aws_conditions.json` contains hand-written vectors derived from AWS docs A4/A4b. Each vector is `{operator, qualifier, policy_values, context|missing, expected: true|false|unresolved, source_url}`.
- It covers every supported operator plus IfExists, Null, negation, ForAll/ForAny with an empty or missing key, and malformed operands.
- Metric: exact agreement. Every mismatch is a failure.

### Tier T1: synthetic labelled regression (existing harness, extended)

- Extend `tests/fixtures/labelled/cases.json` from 14 to ≥40 cases. Cover all 16 rules (`data/rules.yaml`) with at least 1 positive and 1 negative each, plus:
  - Near-miss cases.
  - Conditional or unresolved conditions.
  - Explicit-deny precedence.
  - OIDC classic vs immutable subjects.
  - Job-bound, session and persistent credentials.
  - Rotation cycle.
  - Terraform unknown/sensitive values.
  - Missing boundary/KMS/session context.
  - Benign workflows and unreachable roles.
- Labels gain an `expected_outcome: definite | conditional | unknown` field and a `rationale` that cites the source line.
- Labels are written before running the scanner and are never copied from scanner output. The order is recorded in git history.
- Rename the "AUD-01" tag to `LAB-*` IDs.
- Reported as "synthetic regression results". This is never a real-world accuracy claim.

### Tier T2: public corpus with held-out labels

- **Base:** the existing `scripts/corpus_manifest.json` (14 public repos plus self, pinned SHA, archive SHA-256, per-file hashes, licences).
- **Expansion:** stratified to about 30 repos:
  - Workflow-only.
  - OIDC + Terraform.
  - Multi-account.
  - Monorepo.
  - Benign or no-cloud.
  - Large scale.

  Selection runs from a GitHub code-search query recorded in the manifest. Repos are not chosen by known findings.
- **Layout:** move to `benchmarks/`:
  - `README.md`, `manifest.json`
  - `scripts/fetch.py`: opt-in, network, size/time caps, verifies hashes, never executes content.
  - `scripts/scan.py`, `scripts/aggregate.py`
  - `labels/` with the rubric
  - `results/`
  - `data/`: gitignored raw archives.
- **Licence policy:** only redistribute fixture excerpts from permissively licensed repos. Everything else is manifest plus fetch script only.
- **Splits:** dev (40%), validation (20%), held-out test (40%), fixed by a hashed assignment recorded in the manifest. Held-out labels are written before any v0.3.0 tuning on that split and are not used for development.
- **Label units:** relationship facts, not finding counts:
  1. Workflow job can mint OIDC (yes/no/unknown).
  2. Job → role trust accepted as written (definite/conditional/no).
  3. Credential lifetime class (job/session/persistent).
  4. Mutable third-party action reachability to a role.
  5. Expected rule hits.
- **Rubric:** `benchmarks/labels/RUBRIC.md`. Labels are maintainer-labelled by a single labeller and stated as such. If a second labeller becomes available later, add Cohen's kappa and adjudication.
- **Metrics:**
  - Per unit: precision, recall and F1, with Wilson 95% confidence intervals.
  - Confusion matrices.
  - `conditional` and `unknown` are reported as separate columns, never folded into TP or TN.
  - Coverage: parse rate, unsupported inputs, completeness-status distribution.
  - Runtime: 5 runs after 1 warm-up, median and IQR, with OS, CPU and Python stated.

### Tier T3: comparator study (overlapping tasks only)

| Task | Comparators (pinned releases, checksum-verified, isolated venv/binary) |
|---|---|
| Mutable / unpinned third-party action detection | zizmor (`unpinned-uses`), poutine |
| Excessive `GITHUB_TOKEN` / `id-token` permissions | zizmor |
| `secrets: inherit` usage | zizmor |
| Overly broad GitHub OIDC trust in Terraform | Checkov, Trivy (check IDs verified at the pinned version) |

- Same corpus snapshot and the same machine. Record commands, versions, exit codes, runtime and raw outputs.
- Adjudicate disagreements against the T2 labels.
- Credential survival and rotation order are reported in a capability matrix, not scored. No comparator claims those features, and a missing feature is not counted as a false negative.

### T4 (prepared, not scored in v0.3.0)

- An IAMVulnerable-derived fixture list for the deferred role-chaining work.

### Reproducibility gate

A result is published only with:
- The manifest digest.
- Tool and data versions (`nhi-blast version --data`).
- Config.
- OS/Python.
- Exact command lines.
- Raw outputs in `benchmarks/results/<date>/`.
- Aggregation script hash.

A repeat run must give identical semantic results. `docs/benchmark.md` is rewritten from these artifacts, and the stale 10-repo numbers are removed.
