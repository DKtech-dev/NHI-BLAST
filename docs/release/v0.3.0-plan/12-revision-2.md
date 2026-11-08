# 12. Revision 2: final technical design review (applied)

Date: 2026-11-02. Supersedes where it conflicts: 02-feature-matrix (conditions, TTL, OIDC, PyPI rows), 03-research (A2-A10 are replaced by S1-S19 below), 04-architecture sections 4.1-4.5, 05-sequence, 06-benchmark (C11), 08-gui (C8, C13), 09-risks (risks 16-30), 10-acceptance (states S1-S5). The detailed text of each correction was reviewed and approved in the planning session; this file records what was decided, what was built, and every deviation from the approved text.

## Corrections and their status

| # | Correction | Status in the working tree |
|---|---|---|
| C1 | Session revocation modelled as an explicit-deny access state, never as deletion or expiry | Built by the what-if package (see the implementation log) |
| C2 | Session duration and session-policy provenance | Built: `aws/sessions.py`, parser inputs, data file `configure_aws_credentials.yaml`. Session policies are recorded but **not intersected** (deviation 1) |
| C3 | AWS condition semantics with Present / Absent / Unknown | Built: `aws/conditions.py`, 276-vector oracle, Hypothesis soundness property |
| C4 | Diff false-resolution safety | Built by the diff package (see the implementation log) |
| C5 | What-if replay and reproducibility | `ReportContext`, analyzer identity, engine fingerprint built; replay guard in the what-if package |
| C6 | Deterministic completeness digests | Built: `core/canonical.py`, `core/completeness.py`, cross-root and pinned-constant tests |
| C7 | GitHub OIDC immutable subjects and environments | OIDC built (`[github]` config). Environment facts 2 and 3 need the context-file import, which was not built (stretch D4') |
| C8 | Standalone HTML GUI | Built: `safeStorage`, three-engine `file://` tests |
| C9 | PyPI availability | Wording corrected. Name availability stays unverified |
| C10 | GitHub Action security | Not built (stretch F1') |
| C11 | Benchmark validity | Not built (stretch R1); `docs/benchmark.md` still reports only the synthetic harness |
| C12 | Release states | Defined below |
| C13 | UI direction, light/dark theme and switcher | Built; see 11-ui-direction.md |

## Deviations from the approved text (all deliberate)

1. **Session policies are recorded, not evaluated.** A literal inline policy is not intersected into the edges yet. Sessions that pass one carry `session_policy_evaluated = false`, assumption `A-SESSION-POLICY`, and the family `iam_session_policies` is `partially_analysed`. Reachable access may therefore be broader than the session allows (a safe over-approximation).
2. **`A-CAC-DEFAULT` verified refs** are only `v6` and `v6.3.0` (the README on the default branch). A commit SHA, an older major or a branch is ASSUMED, so most real workflows report the default as assumed.
3. **Immutable format declared without IDs**: the `@*` candidate keeps its previous evidence class instead of becoming UNKNOWN-class, so that trust results do not silently vanish. The completeness item for the subject format records whether the format was declared.
4. **Role maximum from Terraform**: a declared value outside 3600-43200 is treated as the AWS default (3600). A value that is unknown after apply is bounded by the STS limit (43200 s), source `unknown`.
5. **Canonical JSON floats**: finite floats are allowed (shortest round-trip form); NaN and infinity are rejected. The approved text said "integers only", but a configured time budget is a float.
6. **`aws_role_chaining` and `aws_org_policies`** are `not_supported` only when the scan contains AWS roles; otherwise `not_applicable`. The approved text said "always".
7. **Extra family `analysis_budget`** (graph and time limits) was added to the completeness families.
8. **The completeness digest excludes the explanation text** so that rewording cannot change a digest.
9. **Condition semantics**: `ArnEquals` accepts wildcards (AWS documents `ArnEquals` and `ArnLike` as behaving identically); a date-time without a UTC offset is malformed; Bool and Null accept only true/false.
10. **`Config.path` is a scan-root-relative POSIX path.** Found during what-if work: the absolute host path leaked into evidence and edge ids, breaking determinism. Fixed at the source.

## Sources verified (accessed 2026-11-02)

S1 AWS revoke role sessions (`AWSRevokeOlderSessions`, about 30 s into the future, all users, no service-linked roles) - https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html
S2 AssumeRoleWithWebIdentity - https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRoleWithWebIdentity.html
S3 AssumeRole (DurationSeconds 900-43200; chaining capped at 1 h) - https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html
S4 Role chaining definition - https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_terms-and-concepts.html
S5 Role maximum session duration (1-12 h, 1 h default) - https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_update-role-settings.html
S6 Session policies and resource policies - https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html
S7 Condition operators - https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_condition_operators.html
S8 Single- vs multi-valued keys - https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-single-vs-multi-valued-context-keys.html
S9 configure-aws-credentials `action.yml` and README (default branch) - https://github.com/aws-actions/configure-aws-credentials
S10 GitHub OIDC reference (immutable subjects) - https://docs.github.com/en/actions/reference/security/oidc
S11 Deployments and environments - https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments
S12 Secure use - https://docs.github.com/en/actions/reference/security/secure-use
S13 Events that trigger workflows (fork pull requests) - https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
S14 Uploading SARIF - https://docs.github.com/en/code-security/how-tos/scan-code-for-vulnerabilities/integrate-with-existing-tools/uploading-a-sarif-file-to-github
S15 PyPI pending publishers do not reserve a name - https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/
S16 MDN sessionStorage (SecurityError on `file:`) - https://developer.mozilla.org/en-US/docs/Web/API/Window/sessionStorage
S17 npm motion@14.7.1 (MIT) - https://registry.npmjs.org/motion/14.7.1
S18 Workflow artifact retention - https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts
S19 Inspo and inspo-mcp@0.2.0 (MIT) - https://github.com/Nutlope/inspo

Motion provenance: the vendored `motion-14.7.1.min.js` SHA-256 equals the manifest value and the `dist/motion.js` of the npm 14.7.1 package extracted locally; the registry lists the MIT licence and tarball integrity. The tarball was not re-downloaded and re-hashed against the registry integrity in this pass (step G0 follow-up).

## Not verified

- The github.blog changelog of 2026-04-23 (host unreachable from the sandbox; S10 covers the same facts).
- configure-aws-credentials defaults at the tags that fixtures pin (only the default branch was read).
- Who can download Actions artifacts on public repositories; the PyPI name-retention page; real AWS propagation time; Zelkova, USENIX dataset licences, Checkov/Trivy check IDs.
- Linux and macOS behaviour: only Windows was run locally. Digest constants are asserted on every OS in CI, which has not run for this branch.

## Release states (C12)

| State | Definition | Who |
|---|---|---|
| Implementation complete | Core steps done on the local branch with no placeholder code | agent |
| Tests and evidence complete | Local gates pass on Windows (Python 3.12 to 3.14) and are recorded with command, exit code and commit; cross-OS rows read "pending CI" | agent |
| Release candidate ready | Artifacts built from a clean tree at a recorded commit, with checksums, SBOM, smoke test and browser matrix. Not blocked by owner actions | agent |
| Owner actions pending | Authorise a branch push (starts CI for Linux and macOS), register pending publishers, create environments, approve and tag | owner |
| Public release published | TestPyPI, PyPI, draft GitHub release, attestations verified | owner |

Nothing is pushed, tagged, uploaded or published without explicit owner authorisation.


## Additional deviations recorded after the first build pass

11. **Diff safety.** `lk` carries the scenario only for `NHB-SURV-001`, `NHB-ROT-001` and `NHB-ROT-002`
    (`SCENARIO_RULES`); for every other rule the scenario is attribution only. An unreadable or
    malformed report exits 2 (not 3); exit 3 is reserved for reports that load but are incomparable.
    Completeness drift ignores per-source hashes (any edit changes them). `--fail-on` defaults to
    `never`. An extra conservative rule marks a re-routed path `ambiguous_match`.
12. **What-if.** Replay runs on the saved graph minus synthetic scenario nodes and edges. `after`
    is the carried state; `future_reach` is what new runs could still reach. `issued_no_later_than`
    is an upper bound, so `not_denied` means the deny is not established. HTML output is not built.
13. **Engine fingerprint.** The registry covers a fixed list of fixtures so that adding a fixture
    for another feature cannot change it. The first registration embedded a host path (see
    `Config.path` above) and was replaced before any release.
14. **Not built** from the approved plan: diff and what-if HTML (G1), graph list fallback (G2),
    labelled harness growth (A4), GitHub context import (D4'), the Action (F1'), the public-corpus
    benchmark (R1), the internal review (R2), session policy evaluation.
