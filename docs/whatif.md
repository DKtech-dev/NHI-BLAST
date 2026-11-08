# Containment what-if (`nhi-blast whatif`)

Offline model. Not executed. Verify in your account.

`whatif` takes a **saved report** and an **interventions plan** and answers: if these
steps were taken, which credentials could a future run still reach, which sessions are
still in play, and which persistent credentials still need rotation? It reads two local
files and writes two local files. It makes no network call, starts no subprocess, reads no
AWS account and changes nothing. The source report is never modified.

```text
nhi-blast whatif REPORT.json --plan PLAN.(json|yaml|yml) [--format json|md]... [--out DIR]
```

Defaults: both formats, output directory `nhi-blast-whatif-out` (`whatif.json`,
`playbook.md`). HTML is not available in this version.

Exit codes: `0` success; `2` the replay guard refused the report, the plan or an option
is invalid (one `D-WHATIF-*` code on stderr, nothing written); `4` the output cannot be
written.

## Replay guard

A what-if is only meaningful if the saved result can be reproduced exactly. The guard runs
these checks in order and aborts on the first failure:

| Code | Condition |
| --- | --- |
| `D-WHATIF-CONTEXT-MISSING` | Report is schema 1.0, has no `context`, or the context is inconsistent with the saved scenarios. Re-scan with nhi-blast >= 0.3.0. |
| `D-WHATIF-INTEGRITY` | The recorded graph or context digest no longer matches the report content. |
| `D-WHATIF-ENGINE-MISMATCH` | The running analyzer identity (tool version, engine semantics, rules and data digests) differs from the one that produced the report. Re-scan with this version. |
| `D-WHATIF-NONDETERMINISTIC-SOURCE` | A scenario was cut by the wall-clock time budget; that cut cannot be reproduced. (A replay that itself runs out of time gets the same code.) Depth truncation is allowed and reported as `W-WHATIF-DEPTH-TRUNCATED`. |
| `D-WHATIF-REPLAY-MISMATCH` | Re-running every recorded scenario with the recorded configuration, limits, depth and strictness does not reproduce the saved partition, potential set, unresolved inputs, truncation flag and rotation plan. |

The pipeline merges every scenario's synthetic nodes and edges (repo-write and role
sessions) into the saved graph, but analyses each scenario on the graph as built. The
replay therefore strips those additions first (`pristine_graph`; the markers
`repo_write` and `hypothetical` are set only by `analysis/scenario.py`) and lets
`analyze_scenario` re-apply its own transform. Interventions are applied to the same
stripped copy.

`D-WHATIF-ANALYSIS-TIME` (exit 2) is raised if re-analysis after an intervention exhausts
the recorded time budget.

## Plan file

```yaml
schema: nhi-blast-interventions/1.0
interventions:
  - type: revoke_role_sessions
    role: aws:role:arn:aws:iam::111122223333:role/ci-deploy
    revoked_at: "2026-03-01T10:00:00Z"
```

JSON or YAML (the YAML reader composes the first document only, rejects duplicate keys,
and applies node, depth and alias limits). Size limit 1 MiB, at most 500 interventions,
the file must stay inside its own directory. Timestamps are RFC 3339 with an offset.
References are node ids (or an exact, unique label, ARN or Terraform address).

**Fail closed.** An entry that is not understood is reported, never skipped: an unknown
`type` becomes `{type, reason: "unsupported"}` under `rejected`; unknown fields, missing
fields, bad timestamps and unresolved or ambiguous references reject that step with a reason.
v0.3.0 also rejects arbitrary deny-policy injection, minimum-cut suggestions and anything
that would mutate a live system.

| Type | Fields | Model |
| --- | --- | --- |
| `disable_entrypoint` | `node` (job or workflow) | Removes the authority edges out of the job(s) for **future** runs and takes them out of the scenario start set. |
| `remove_trust` | `role` and one of `principal` or `edge` | Removes a `CAN_ASSUME` / `AUTHENTICATES_AS` edge into the role. Removing the OIDC identity edge, or a repo-write edge, clears the role's repo-write acceptance (a role-level flag, so it applies to every principal). |
| `revoke_role_sessions` | `role`, optional `revoked_at`, `cutoff`, `assessed_at`, `issued_no_later_than` (a timestamp, or a map of session id to timestamp) | The IAM revoke-older-sessions deny (see below). The graph is unchanged. |
| `rotate_credential` | `credential` (persistent) | The credential leaves Z, unless a surviving path still reaches it. |

## Result (`nhi-blast-whatif/1.0`)

Canonical JSON, sorted keys, no timestamps. `source_report_digest` is the digest of the
report's context and graph digests; `plan_digest` is the digest of the parsed plan.

* `steps[]` - every plan entry in order with `status` (`applied`, `no_effect`,
  `rejected`), normalised arguments, effects, and the future-run R/E/Z counts after the
  step (the analysis is re-run on the modified copy after each step).
* `per_scenario[]`
  * `before` - the saved R/E/Z.
  * `after` - the **carried** state: `R` and `E` unchanged; `Z` minus credentials
    that were rotated with no surviving path; `issued_before_containment` (sessions,
    with at most their TTL remaining and whether new runs could still obtain them);
    `revoked_access`; `re_exposure_risk`; `rotated`.
  * `future_reach` - R/E/Z that a new run could still reach on the modified graph.
  * `residual_paths`, `rotation_order` (the saved rotation plan's order with
    planned / at-risk flags), `potential` (UNKNOWN-class edges only).
* `rejected[]`, `warnings[]` (`W-WHATIF-*` codes), `caveats[]`.

Containment steps never remove what a run may already have obtained: sessions stay issued
until their TTL and persistent credentials stay in Z until rotated. UNKNOWN-class edges
never contribute to R, E or Z.

## `revoke_role_sessions`

This models the inline deny that the AWS console applies (`AWSRevokeOlderSessions`:
deny all actions when `aws:TokenIssueTime` is earlier than a cutoff). It never removes or
changes a credential. Each in-scope session (an E entry for that role) gets two independent
axes:

* `validity`: `expired` only when `assessed_at`, `issued_no_later_than` and a TTL upper
  bound are all known and `assessed_at >= latest_issue_time + ttl`; otherwise `unknown`.
  Being before the latest possible expiry cannot establish that credentials are still valid.
* `access`: `denied_by_revocation_policy` (issued before the cutoff; if `assessed_at` is
  absent it is flagged `conditional_on_propagation`), `revocation_propagating`
  (`revoked_at <= assessed_at < cutoff`), `not_denied` only when assessed before `revoked_at`,
  or `unknown`. An issue-time upper bound at or after the cutoff can describe sessions on
  either side of the cutoff, so it cannot establish that the deny does not apply.

The cutoff is the given `cutoff`, else `revoked_at` + 30 s. The 30 s is an **ASSUMED**
propagation window from
<https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html>
("approximately 30 seconds into the future"), never a guarantee. `issued_no_later_than` is an
upper bound, so `issued < cutoff` is certain while `issued >= cutoff` means only that the deny
is not established.

Display state: `access denied - expiry not established`, `expired` or `unknown`.
Access denial does not establish validity. Neither an expiry upper bound nor a propagating
policy establishes an active session. `expired` appears only when expiry is established.

Every output of this intervention carries these caveats: sessions issued inside the
propagation window are covered; sessions issued after the cutoff are not; the deny applies
to every user of the role; service-linked roles cannot be revoked this way; derived
credentials (chained sessions, keys created by the session, secrets already read) are not
affected and appear as `residual_unknown` because role chaining is not modelled. Revocation
without `remove_trust` sets `re_issue_possible`; `remove_trust` without revocation leaves
existing sessions active until expiry.

## Playbook

`playbook.md` is deterministic Markdown that starts with the header line above. Order:
1 revoke sessions, 2 remove trust or disable entrypoint, 3 rotate surviving credentials in
the rotation plan's dependency (SCC) order, 4 verify. Each step has an owner placeholder,
evidence references (file:line and evidence class), a human verification task and
rollback / validation notes. Nothing in it was executed; owners, times and account
details are placeholders for you to fill in.

## Limits

The model works on the saved graph only: SCPs, permission boundaries not recorded in the
report, live session state, role chaining and credentials created after the scan are not
modelled. Rotation re-exposure is judged from the saved paths at the end of the plan; a
rotation placed before the step that closes the path is flagged
`W-WHATIF-ROTATE-BEFORE-CLOSING-PATH`. The model is a planning aid and does not replace
verification in your account.
