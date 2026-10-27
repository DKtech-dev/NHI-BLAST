# NHB-OIDC-005 — Subject format drift

**Base severity:** LOW · **Precision:** medium · **Tags:** oidc, compatibility

## What it detects

The trust policy matches only the classic subject form
`repo:OWNER/REPO:...`. Repositories that mint immutable subjects use
`repo:OWNER@OWNER_ID/REPO@REPO_ID:...`, which the pattern does not match.

## Why it matters

A policy that matches only one form can silently fail to federate for repositories
created after the immutable-subject cutover, or after a rename or transfer. The
failure is operational rather than an exposure, but it can push teams toward a
broader wildcard.

## Evidence

`DECLARED` policy text. The scanner does not know the repository's creation date or
rename history, so both subject forms are evaluated (`A-REPO-AGE`).

## Limits

The finding indicates format drift only. It does not prove which form the target
repository currently mints.

## Remediation

Match both forms, or use `job_workflow_ref` with immutable owner and repository
IDs. Test with a workflow run before removing the classic pattern.

## Related

[NHB-OIDC-002](NHB-OIDC-002.md) · [NHB-OIDC-003](NHB-OIDC-003.md)
