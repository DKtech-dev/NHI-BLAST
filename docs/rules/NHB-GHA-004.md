# NHB-GHA-004 — `secrets: inherit` or whole secrets context

**Base severity:** MEDIUM · **Precision:** high · **Tags:** github-actions, secrets

## What it detects

A job uses `secrets: inherit` on a reusable workflow call, the bare `secrets`
context, `toJSON(secrets)`, or a dynamic index into `secrets`.

## Why it matters

The set of materialised secrets cannot be determined from the workflow file. The
job may hold every secret the repository can see instead of the named few it needs.
The graph records a wildcard, UNKNOWN-class credential edge rather than inventing a
precise list.

## Evidence

`DECLARED` workflow expression plus `A-RUNNER-SECRETS` (`VERIFY`). The wildcard edge
never contributes to R, E or Z; it feeds the `potential` set only.

## Limits

The finding does not enumerate the secrets, prove which were materialised, or prove
that any value was read.

## Remediation

Pass only the secrets the reusable workflow needs, using explicit names with
`inherit: false`. Avoid `toJSON(secrets)` and dynamic secret indexing.

## Related

[NHB-GHA-001](NHB-GHA-001.md) · [NHB-GHA-005](NHB-GHA-005.md)
