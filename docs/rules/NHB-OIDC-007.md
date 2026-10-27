# NHB-OIDC-007 — Environment-only trust with unknown protection

**Base severity:** INFO · **Precision:** low · **Tags:** oidc, settings

## What it detects

The trust policy's `sub` condition names a GitHub environment. Environment
protection rules are not stored in repository files, so the scanner cannot verify
required reviewers, deployment branch rules or wait timers.

## Why it matters

Anyone who can edit workflows can add an `environment:` claim. The environment is a
real control only if its protection rules actually constrain who can deploy and
from which branches.

## Evidence

`DECLARED` policy text and `A-ENV-UNPROTECTED` (`VERIFY`). This is informational: it
does not assert that the environment is unprotected.

## Limits

GitHub organisation and environment settings are out of scope. The finding
disappears only when the policy also pins `sub` to a ref that the environment
cannot be reached from.

## Remediation

Confirm required reviewers and deployment branch rules in GitHub settings, or pin
`sub` to a specific ref as well. Record the settings check in the incident notes.

## Related

[NHB-OIDC-003](NHB-OIDC-003.md) · [NHB-OIDC-004](NHB-OIDC-004.md)
