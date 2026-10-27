# NHB-OIDC-004 — Audience not constrained

**Base severity:** MEDIUM · **Precision:** medium · **Tags:** oidc, aws, trust-policy

## What it detects

The trust statement has no `aud` condition. The analysis reports this when the
statement otherwise matches a candidate subject, so the finding stays tied to a
plausible path rather than every role in the repository.

## Why it matters

Without an audience condition, AWS may accept tokens issued for other resource
servers as well as tokens minted for the expected AWS audience. The policy is wider
than the workflow's intended use.

## Evidence

`DECLARED` policy text. The finding is a property of the policy as written; it does
not assert that a token for another audience is accepted in practice.

## Limits

Some AWS configurations rely on the provider's default audience mapping. Confirm
the current AWS behaviour before changing a working policy; GitHub and AWS
documentation have disagreed on related custom-claim details.

## Remediation

Add an `aud` condition with the exact audience the workflow requests, normally
`sts.amazonaws.com`. Keep the workflow's `audience:` input aligned with it.

## Related

[NHB-OIDC-001](NHB-OIDC-001.md) · [NHB-OIDC-006](NHB-OIDC-006.md)
