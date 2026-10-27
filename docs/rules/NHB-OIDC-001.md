# NHB-OIDC-001 — Trust policy has no subject or workflow control

**Base severity:** CRITICAL · **Precision:** high · **Tags:** oidc, aws, trust-policy

## What it detects

An AWS role trust statement permits `sts:AssumeRoleWithWebIdentity` for the GitHub
OIDC provider but has no `sub` or `job_workflow_ref` condition. The statement may
constrain `aud`; that does not identify the repository, ref or workflow that may
assume the role.

## Why it matters

Any GitHub Actions workflow that can obtain a token for the accepted audience and
provider may satisfy the policy as written, regardless of repository or owner.
Whether such a workflow exists and is reachable by an attacker is a separate
question that repository files cannot answer.

## Evidence

The finding is supported by the trust statement itself (`DECLARED`). Reachability
from a compromise entrypoint is only reported when the graph contains a matching
path; the finding alone does not claim one.

## Limits

The analysis evaluates the policy as written. It does not prove that a live caller
exists, that a token was issued, or that credentials were read.

## Remediation

Add an exact `sub` condition for the repository, ref and environment, or pin
`job_workflow_ref` to a reviewed reusable workflow. Keep `aud` constrained to the
audience the workflow actually requests (`sts.amazonaws.com` by default).

## Related

[NBHOIDC-002](NHB-OIDC-002.md) · [NHB-OIDC-003](NHB-OIDC-003.md) ·
[NHB-OIDC-004](NHB-OIDC-004.md)
