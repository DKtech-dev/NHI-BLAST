# NHB-OIDC-002 — Organisation-wide or global wildcard in subject

**Base severity:** HIGH · **Dynamic:** CRITICAL when the breadth class is `ANY_ORG` or
`SAME_ORG`, raised further when surviving credentials are non-empty · **Precision:** high

## What it detects

The trust policy's `sub` condition accepts repositories outside the analysed
repository: for example `repo:acme/*` (same organisation) or `repo:*` (any owner).
The solver reports the breadth class and the workflow lines that satisfy the
pattern.

## Why it matters

A workflow author in another repository of the same organisation, or in any
organisation for a global wildcard, may satisfy the policy as written if the
audience check also passes. The path is potentially reachable without access to the
analysed repository's workflow files.

## Evidence

`DECLARED` policy text plus `DERIVED` subject candidates. The finding does not prove
that a workflow in another repository exists or is attacker-controlled.

## Limits

Organisation membership and repository write access are not present in repository
files. Repositories that mint immutable subjects are evaluated separately
(`A-REPO-AGE`).

## Remediation

Replace the wildcard with the exact repository and ref, or constrain
`job_workflow_ref` to a reviewed reusable workflow. Prefer environment claims with
verified protection rules over owner-wide patterns.

## Related

[NHB-OIDC-001](NHB-OIDC-001.md) · [NHB-OIDC-003](NHB-OIDC-003.md) ·
[NHB-OIDC-005](NHB-OIDC-005.md)
