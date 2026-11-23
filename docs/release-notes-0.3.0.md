# NHI-Blast 0.3.0 Release Notes

## Highlights

- **Formal IAM condition solver (`nhi_blast.aws.solver`)**: Pure-Python minterm-compressed
  NFA-to-DFA solver with bounded state budgets, deterministic shortest witness synthesis,
  deletion-based minimal unsatisfiable subsets (MUS), cross-key OIDC projection, exact
  IPv4/IPv6 CIDR intersection, and exact `Decimal` numeric/date interval solving.
- **Engine soundness fixes**:
  - Enforced permissions boundaries on both definite and conditional allows, with `A-NO-BOUNDARY`
    disclosure when boundary documents are absent.
  - Wired Secrets Manager resource policies into `can_read` and `can_modify` with same-account
    session-ARN handling and explicit-deny precedence.
  - Added explicit `Deny` evaluation (`NotAction`, wildcard principals, conditional downgrades)
    in OIDC trust policies.
  - Replaced silent `False` on oversized globs with tri-state `GlobRelation.BUDGET_EXCEEDED`
    propagating to `ConditionTruth.UNRESOLVED` and `D-COND-BUDGET`.
  - Tracked dual STS session TTLs (`configured_ttl_seconds` and `attacker_max_ttl_seconds`).
  - Added stepwise custody tracking, `--auto-plan`, and copyable `AWSRevokeOlderSessions`
    JSON policy snippets in `nhi-blast whatif`.
  - Fixed console diff crash (`delta['selector']`) and WebKit `requestAnimationFrame` metric
    and scroll-progress bugs.
- **Late-2026 threat model**:
  - `NHB-PERSIST-001` for IAM persistence capabilities (`CreateAccessKey`, `UpdateAssumeRolePolicy`,
    policy mutation) with Cloud Persistence Audit steps in rotation plans and playbooks.
  - `NHB-CHAIN-001` for bounded intra-input `sts:AssumeRole` chaining (3600 s STS cap).
  - `NHB-GHA-002` unsafe PR checkout / cache-write upgrade, `NHB-GHA-006` (AI coding agent
    workflows on PR/issue triggers), and `NHB-GHA-007` (unconstrained package install hooks).
- **Reporting & exports**:
  - Modularized HTML report templates into `nhi_blast.report.templates` loaded via
    `importlib.resources`, preserving single-file offline HTML and strict SHA-256 CSP.
  - Added accessible graph table fallback and interactive offline containment preview.
  - Added zero-Motion companion HTML reports for `nhi-blast diff --format html` and
    `nhi-blast whatif --format html`.
  - Enabled deterministic BloodHound CE OpenGraph JSON export (`nhi-blast export --format opengraph`).
  - Added SHA-pinned reusable composite GitHub Action (`action/action.yml`) and browser/a11y
    CI workflow (`.github/workflows/ui.yml`).

## Breaking / semantic changes

- `ENGINE_SEMANTICS` bumped from `5` to `7`; schema remains backward-compatible with
  `nhi-blast-report/1.0` and `nhi-blast-report/1.1`.
