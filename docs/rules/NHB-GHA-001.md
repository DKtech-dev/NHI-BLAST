# NHB-GHA-001 — Mutable third-party action in a privileged job

**Base severity:** MEDIUM · **Dynamic:** HIGH when the resulting scenario has
surviving credentials · **Precision:** high · **Tags:** supply-chain, mutable-reference

## What it detects

A third-party action is referenced by a mutable tag, branch or other non-immutable
reference, and the job holds credentials, secrets or OIDC write permission.

## Why it matters

If the tag or branch is moved, the replacement code runs with everything the job
holds. The tool records this as a potential compromise path from the action to the
job's authority; it does not inspect the action's code.

## Evidence

`DECLARED` workflow reference plus `DERIVED` permission and credential facts. The
action use site is a start node for the `action:` selector.

## Limits

The finding does not prove that the tag was moved or that the action is malicious.
A mutable reference from a trusted first-party owner is still mutable, but the
practical risk depends on the owner's release controls.

## Remediation

Pin the action to a full 40-character commit SHA and review changes before updating
the pin. Prefer actions published with immutable releases.

## Related

[NHB-GHA-002](NHB-GHA-002.md) · [NHB-GHA-004](NHB-GHA-004.md)
