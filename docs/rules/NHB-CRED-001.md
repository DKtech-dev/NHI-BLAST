# NHB-CRED-001 — Static AWS keys used where OIDC could be used

**Base severity:** MEDIUM · **Precision:** high · **Tags:** credentials, aws, static-keys

## What it detects

A job configures AWS with static access-key inputs instead of OIDC federation. When
the job already has `id-token: write`, the static keys are unnecessary for AWS
authentication.

## Why it matters

Long-lived access keys survive job revocation and are not scoped to a workflow run.
In the survival model they appear as persistent credentials (`Z`), so they must be
rotated after an incident rather than expiring with the runner.

## Evidence

`DECLARED` action inputs and `DERIVED` OIDC permission. The finding does not assert
that the keys are valid or that they were used in a run.

## Limits

Some environments cannot use OIDC (for example providers without federation
support). The finding highlights an unnecessary long-lived credential, not a
definite policy violation.

## Remediation

Remove the static keys and use OIDC federation with a tightly scoped role trust
policy. If static keys are unavoidable, store them in a secret manager, restrict
their permissions and rotate them on a schedule.

## Related

[NHB-SURV-001](NHB-SURV-001.md) · [NHB-GHA-005](NHB-GHA-005.md)
