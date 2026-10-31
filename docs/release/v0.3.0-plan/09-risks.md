# 9. Risk register

| # | Risk | Likelihood / impact | Mitigation | Owner signal |
|---|---|---|---|---|
| 1 | Diff reports a false "resolved" (false assurance) | M / High | Strict resolved rule; `not_observed` state; Hypothesis line/order permutation tests | Any `resolved` under drift fails a test |
| 2 | What-if diverges from scan semantics | M / High | Replay self-check (`D-WHATIF-REPLAY-MISMATCH`); requires `ReportContext`; same `analyze_scenario` code | Self-check failure aborts |
| 3 | Misread session semantics (claims a revocation that does not happen) | M / High | Revocation only through the explicit `revoke_role_sessions` intervention (A2); `disable_entrypoint` keeps E | Golden fx16 asserts E persists |
| 4 | Condition-operator errors produce confident allow/deny | M / High | T0 oracle table from AWS docs; anything uncertain is UNRESOLVED; property test | Oracle mismatch fails CI |
| 5 | Schema change breaks consumers | L / M | Additive 1.1, frozen 1.0 schema, golden 1.0 load, migration notes | Schema check gate |
| 6 | Completeness becomes noise or a misleading score | M / M | Five states, no percentage, report-level scope by default | UI review checklist |
| 7 | Benchmark bias or overclaiming | M / High | Pre-registered splits, held-out labels, CIs, separate unknown column, single-labeller disclosure | Docs claim review in R2 |
| 8 | Supply chain at first publish (name squatting, token theft) | M / High | Owner registers the pending trusted publisher early; protected environments; no long-lived tokens; SHA pins; attestations | Owner step done before E1 |
| 9 | Action leaks findings or gets privilege on fork PRs | L / High | No `pull_request_target`; SARIF skipped on forks; artifacts opt-in with warning; minimal permissions | `action-test.yml` fork case |
| 10 | HTML growth or performance regression | M / L | Size budget tests; Motion excluded from companion pages; list fallback for large graphs | Budget test |
| 11 | Scope creep in Stage D | H / M | Hard deferral register; `not_supported` completeness items | Roadmap file |
| 12 | Corpus licence or privacy issue | L / M | Manifest-only for non-permissive repos; no secrets in results; redaction checks | Fetch script licence check |
| 13 | macOS/WebKit flakiness | M / L | Non-blocking until stable; claim a platform only when it passes | CI status |
| 14 | Limited agent budget (~USD 100) | H / M | Order A→B→C→E first; targeted test runs; stage logs for resumption | Progress log |
| 15 | Third-party comparator tools run untrusted code | L / M | Pinned official releases with checksums, isolated venvs, corpus treated as data only | R1 record |
