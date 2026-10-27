# NHB-SURV-001 — Credentials survive revocation of the entrypoint

**Base severity:** HIGH · **Dynamic:** reported at the highest criticality of the
surviving credentials · **Precision:** medium · **Tags:** incident-response, rotation

## What it detects

The selected scenario obtains at least one persistent credential. Stopping the
workflow, removing the action or revoking the job token does not invalidate those
values.

## Why it matters

Revoking the entrypoint is not sufficient if credentials survive. The response must
rotate the survivors in an order that prevents a surviving credential from reading a
freshly rotated one. The rotation plan provides that order.

## Evidence

`DERIVED` graph paths plus `ASSUMED` credential classification. Severity reflects
the highest criticality among surviving credentials; criticality is an ordering
input, not a verdict.

## Limits

Survival is conditional on the path having been exercised. The analysis does not
prove that any credential was actually read, exfiltrated or used. It models the
configuration as written, not runtime logs.

## Remediation

Follow the rotation plan: contain the entrypoint, rotate survivors in generation
order, then verify with CloudTrail and provider audit logs. Investigate any use
before rotation completed.

## Related

[NHB-ROT-001](NHB-ROT-001.md) · [NHB-ROT-002](NHB-ROT-002.md) ·
[NHB-CRED-001](NHB-CRED-001.md)
