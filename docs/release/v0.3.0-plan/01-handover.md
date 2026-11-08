# NHI-Blast v0.3.0 Beta — Context and handover report

> **Revised 2026-11-02.** Where this part conflicts with [12-revision-2.md](12-revision-2.md) (final design review: corrections, deviations, verified sources) or [11-ui-direction.md](11-ui-direction.md), those documents win. See the implementation log for what was built.

## Context

The maintainer wants one consolidated `v0.3.0 Beta` that makes NHI-Blast more trustworthy (evidence completeness), comparable (report diff/baselines), decision-useful (offline containment what-if), installable (PyPI + provenance) and CI-integrated (thin GitHub Action), with a defensible benchmark. This plan is based on an audit of the actual repository (2026-10-31) and primary-source research.

On approval, step 0 splits this file into separate documents under `docs/release/v0.3.0-plan/` (01-handover.md … 10-acceptance.md). That keeps each file small and reviewable.

Wording rule: results are described exactly as produced. Automated tests are "tested". Labels are "maintainer-labelled (single labeller)". Scripted browser walkthroughs are "scripted task walkthroughs". No claim of independent annotation, human usability study or independent audit is made unless one actually happens.

---

## 1. Repository handover report

**Identity and state (verified with read-only git):**
- Remote `origin` = `https://github.com/DKtech-dev/nhi-blast.git`.
- HEAD `7dd00c0` on `docs/readme-imagery-modern` (PR #6, open, 12/12 CI checks passed).
- `main` = `1535113`. Tag `v0.2.0` = `41d08a8` (public pre-release; Windows exe only).
- Package version `0.2.0` (`pyproject.toml:7`); schema `nhi-blast-report/1.0` (`src/nhi_blast/__init__.py:6`).
- Untracked: `docs/engineering-checkpoint.md` (local-only, must stay uncommitted).
- Ignored scratch: `HANDOVER.md` (marked superseded), `_spec_extract.txt`, `_blueprint_extract.txt`, `_extract*.py`, `_t.py`, `build/`, `dist/`, `.buildcheck/`, `nhi-blast-out/`. Classified as generated/historical; leave untouched.

**Prior-agent work:** confirmed by the maintainer that no separate v0.3.0 work exists. The pre-existing implementation is the v0.1.0–v0.2.0 history already in Git. No diff, baseline, completeness, what-if, Action or PyPI workflow code exists on any branch.

**Baseline:** CI on `7dd00c0` (code identical to v0.2.0) passed all 12 checks: ruff, mypy strict, pytest, coverage gate, slow suite on ubuntu+windows × py3.12/3.13/3.14, package job, CodeQL, audit. A local baseline was not run in plan mode to avoid writing caches; step 0 runs it and records the output.

**Codebase size (approx. LOC):**

| Package | LOC |
|---|---|
| `report/` | 5,416 |
| `graph/` | 1,948 |
| `analysis/` | 1,876 |
| `resolvers/` | 1,819 |
| `core/` | 1,622 |
| `parsers/gha` | 1,262 |
| `aws/` | 1,176 |
| `parsers/terraform` | 901 |
| `pipeline.py` | 825 |
| `oidc/` | 589 |

There are 48 test files, 504 test functions and ~805 parametrised passes.

**Stale or inconsistent documentation to fix in Stage A4:**
1. `docs/known-limitations.md:154` says Linux is an external gate, which contradicts Ubuntu CI.
2. `docs/benchmark.md` shows the old 10-repo run. The newer 15-dataset pinned corpus (`scripts/corpus_manifest.json`) is unpublished.
3. The `docs/production-readiness.md` gate matrix still shows 0.1.1 numbers (418 passed, 86.67%).
4. `release.md:39` and `CONTRIBUTING.md:32` cite `coverage report`, but CI uses `scripts/check_coverage.py`.
5. `docs/security-audit.md` covers v0.1.1 (`c702d9d`) only, and has no record of the PR #3 remediation. The labelled harness reuses the ID "AUD-01".
6. The CHANGELOG 0.2.0 entry has no date and omits the PR #3 hardening.
7. The issue template lists macOS 15, but macOS is untested.
8. Assumption `A-NO-SCP` is attached when a permissions boundary is missing (`aws/policy_eval.py:228`). That conflates boundaries with organisation policies.
