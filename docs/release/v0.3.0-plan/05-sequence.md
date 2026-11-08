# 5. Full implementation sequence

> **Revised 2026-11-02.** Where this part conflicts with [12-revision-2.md](12-revision-2.md) (final design review: corrections, deviations, verified sources) or [11-ui-direction.md](11-ui-direction.md), those documents win. See the implementation log for what was built.

Branch `feature/v0.3.0-beta-consolidated` from `main` (after PR #6 is merged, or rebased onto it). Small commits; CI must be green at each stage boundary. Logs: `docs/release/v0.3.0-beta-implementation-log.md` and `docs/release/v0.3.0-beta-progress.md`, updated after every stage. Size estimate: S < 0.5 day, M ≈ 1 day, L ≈ 2+ days.

| Step | Work | Main files | Size |
|---|---|---|---|
| 0 | Split the plan into `docs/release/v0.3.0-plan/*.md`. Run the local baseline gates and record them. Write the handover snapshot (status, commit IDs, untracked inventory; no secrets). | docs only | S |
| A1 | Schema 1.1 scaffolding: `READABLE_SCHEMAS`, `report/loader.py`, `ReportContext`, frozen 1.0 schema, 1.0 golden load test | `__init__.py`, `core/models.py`, `report/explain.py`, `scripts/gen_schema.py`, `docs/schema/` | M |
| A2 | `core/completeness.py`, mapping table, code-coverage test, `A-NO-BOUNDARY` split, `_scope_lines` generated from completeness | `core/completeness.py`, `pipeline.py:586,671-721`, `data/assumptions.yaml`, `docs/assumptions.md` | M |
| A3 | Completeness in console, JSON, SARIF (run properties) and the HTML panel | `report/console.py`, `json_report.py`, `sarif.py`, `ui.py` | M |
| A4 | Labelled harness 14 → ≥40 cases (section 6 T1); evaluate_labelled CI gate; documentation reconciliation (handover list items 1–8) | `tests/fixtures/labelled/`, `scripts/evaluate_labelled.py`, docs | L |
| B1 | `diff/keys.py` + test that `lk` is consistent with the SARIF fingerprint | `diff/` | S |
| B2 | `diff/compare.py`, classification, `diff` command, JSON/console renderers | `diff/`, `cli/app.py`, `cli/commands.py` | L |
| B3 | Baseline file plus `baseline accept/prune`; exit codes | `diff/baseline.py`, CLI | M |
| C1 | `whatif/plan.py` + `engine.py` with replay self-check and four interventions | `whatif/`, reuses `analysis/scenario.py`, `partition.py`, `rotation.py` | L |
| C2 | `whatif/playbook.py`, `whatif` command, golden containment fixture (fx16) with unresolved policy context | `whatif/`, `tests/fixtures/fx16-containment/` | M |
| D1 | Numeric/Date/IP/Binary operators with an oracle table from A4/A4b | `aws/conditions.py`, `tests/test_conditions.py`, new `tests/oracles/aws_conditions.json` | M |
| D2 | `configure-aws-credentials` inputs (TTL, session policies, role-chaining flag) | `resolvers/roles.py`, `graph/builder.py:1098-1175`, `data/` | M |
| D3 | Immutable OIDC binding config | `core/config.py`, `oidc/github_subject.py` | S |
| D4 | GitHub context file import | `core/config.py`, new `parsers/ghcontext.py`, builder, completeness | M |
| D5 | `docs/roadmap.md` deferral register + role-chaining design note | docs | S |
| G1 | `html.py` → `render_document(title, payload, sections)`; diff HTML; what-if HTML (no Motion; CSP and escaping reused) | `report/html.py`, new `report/diff_html.py`, `report/whatif_html.py` | M |
| G2 | Main report: graph list/table fallback, light theme via `prefers-color-scheme`, completeness-aware summary, keyboard fixes | `report/ui.py`, `graph_layout.py` | M |
| G3 | Playwright + axe tests and `ui.yml` workflow; scripted task walkthroughs | `tests/ui/`, `.github/workflows/ui.yml` | M |
| E1 | Bump to `0.3.0b1`; `release.yml`; SBOM; checksums; attestations; install/verify docs; add macOS (py3.12) to the CI matrix | `pyproject.toml`, workflows, docs | M |
| F1 | `action/action.yml`, examples, `action-test.yml` against fixtures (same-repo and simulated fork conditions) | `action/`, workflows, `docs/github-action.md` | M |
| R1 | Benchmark corpus labelling and comparator runs (section 6 T2/T3) | `benchmarks/` | L |
| R2 | Internal security and semantic review of the changed code; update `docs/security-audit.md` and `external-audit-package.md` with the exact commit | docs | M |
| R3 | Final gates, changelog, release notes `docs/release-notes-0.3.0.md`, release checklist, go/no-go | docs | S |

**Ordering rationale:**
- A → B → C carry the highest trust value. D strengthens semantics.
- G follows the new data structures.
- E comes before F because the Action needs a published, pinned package.
- R1 can run in parallel after A4.
- If time or budget runs short, cut in this order (last first): D4, G2 light theme, R1 comparator breadth. Never cut A, B, C, E or the acceptance gates.

**Owner checkpoints** (external actions only): PyPI pending-publisher registration (before E1 publishes), approving the release environment, pushing the tag, publishing the GitHub release.
