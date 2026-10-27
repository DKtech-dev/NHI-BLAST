# Findings catalogue

NHI-Blast emits the following rules. Severity is an ordering label for triage, not a
verdict: a finding states what the supplied files accept or permit, not that anything
was exploited. Every finding carries evidence, the affected node or edge identifiers,
and the assumptions that shaped it.

The machine-readable catalogue is `src/nhi_blast/data/rules.yaml`. Each rule below has
a page describing what it detects, why it matters, the evidence and limits, and the
remediation.

## OIDC trust policy

| Rule | Base severity | What it reports |
| --- | --- | --- |
| [NHB-OIDC-001](NHB-OIDC-001.md) | CRITICAL | A trust policy has neither a `sub` nor a `job_workflow_ref` control, so the condition reduces to the provider and audience alone. |
| [NHB-OIDC-002](NHB-OIDC-002.md) | HIGH | A `sub` condition accepts an organisation-wide, enterprise-wide or global wildcard. |
| [NHB-OIDC-003](NHB-OIDC-003.md) | HIGH | A `sub` condition is repo-wide and does not constrain branch, tag or environment context. |
| [NHB-OIDC-004](NHB-OIDC-004.md) | MEDIUM | `aud` is absent, a wildcard, or otherwise unconstrained. |
| [NHB-OIDC-005](NHB-OIDC-005.md) | LOW | The subject format is inconsistent with the repository's expected GitHub subject format (classic or immutable). |
| [NHB-OIDC-006](NHB-OIDC-006.md) | LOW | A condition key is not an AWS-documented GitHub provider claim, so it cannot match as written. |
| [NHB-OIDC-007](NHB-OIDC-007.md) | INFO | The trust policy relies on an environment claim whose protection rules are unknown. |

## GitHub Actions configuration

| Rule | Base severity | What it reports |
| --- | --- | --- |
| [NHB-GHA-001](NHB-GHA-001.md) | MEDIUM | A third-party action uses a mutable tag or branch in a job that holds secrets or OIDC. |
| [NHB-GHA-002](NHB-GHA-002.md) | HIGH | A privileged trigger checks out pull-request head content before running it. |
| [NHB-GHA-003](NHB-GHA-003.md) | INFO | A job targets a self-hosted runner, where state may persist between jobs. |
| [NHB-GHA-004](NHB-GHA-004.md) | MEDIUM | `secrets: inherit`, the bare `secrets` context, `toJSON(secrets)` or a dynamic index exposes an unknown set of secrets. |
| [NHB-GHA-005](NHB-GHA-005.md) | HIGH | A workflow scalar matches a literal credential heuristic. Only kind and length are reported. |

## Credentials and incident response

| Rule | Base severity | What it reports |
| --- | --- | --- |
| [NHB-CRED-001](NHB-CRED-001.md) | MEDIUM | Static AWS access keys are used where OIDC federation is available. |
| [NHB-SURV-001](NHB-SURV-001.md) | HIGH | At least one persistent credential survives revocation of the entrypoint. |
| [NHB-ROT-001](NHB-ROT-001.md) | LOW | A reachable credential sink has no configured rotation. |
| [NHB-ROT-002](NHB-ROT-002.md) | MEDIUM | A reachable role can modify a credential sink and can therefore defeat a later rotation. |

## Reading a finding

Findings reference graph elements by identifier. Use `nhi-blast explain` on a saved
JSON report to print the evidence chain:

```
nhi-blast explain NHB-OIDC-002-ebd9705d --report nhi-blast-out/report.json
```

Dynamic severity adjustments are described in each rule page and in the rule's
`severity_note` in `rules.yaml`. A higher severity never means "proven exploitable";
it means the reported configuration deserves earlier review.

## Suppression

Rules can be ignored with `[ignore].rules` in `nhi-blast.toml`. A suppression removes
the finding from the report; it does not change the graph or the survival partition.
Record why a suppression exists in the configuration comment. Ignoring a rule does not
make the underlying authority path disappear.
