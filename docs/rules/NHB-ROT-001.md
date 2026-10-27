# NHB-ROT-001 — Reachable credential sink without rotation

**Base severity:** LOW · **Precision:** high · **Tags:** rotation, secrets

## What it detects

A credential sink reachable from the scenario has no rotation resource or interval
in the supplied Terraform inputs.

## Why it matters

Without scheduled rotation, the value remains valid until someone rotates it
manually. The response plan must include that manual step; otherwise a surviving
credential can outlive the incident response.

## Evidence

`DERIVED` sink reachability and `H-ROT-WINDOW` heuristics. The finding does not
assert that rotation is impossible, only that none was found in the inputs.

## Limits

Rotation configuration may live outside the scanned files (console settings,
another state file or an external scheduler). A missing rotation resource is not
proof that the credential never rotates.

## Remediation

Enable automatic rotation for the secret, or document the manual rotation step in
the response plan. Confirm the interval against the provider's configuration.

## Related

[NHB-ROT-002](NHB-ROT-002.md) · [NHB-SURV-001](NHB-SURV-001.md)
