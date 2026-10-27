# NHB-ROT-002 — Role can modify a reachable sink

**Base severity:** MEDIUM · **Precision:** high · **Tags:** rotation, aws, iam

## What it detects

A role reachable from the entrypoint is allowed to write or rotate a credential
sink in the scenario, for example with `secretsmanager:PutSecretValue` or
`ssm:PutParameter`.

## Why it matters

An actor holding that role can re-write a freshly rotated value. Rotating the sink
before removing the role's write access can therefore be undone. The affected
credentials form a cycle in the rotation plan and must be rotated with the role's
authority contained first.

## Evidence

`DERIVED` policy evaluation (`CAN_MODIFY`) plus reachability. The finding does not
prove that the role was used to modify anything.

## Limits

Resource policies, SCPs and KMS key policies that were not supplied are not
modelled (`A-NO-SCP`, `A-KMS-UNMODELLED`). A write permission in the role policy
may still be blocked by an unmodelled control.

## Remediation

Remove write access from the federated role. Use separate roles for read and
rotation, and rotate the modifying role's credentials before dependent sinks.

## Related

[NHB-ROT-001](NHB-ROT-001.md) · [NHB-SURV-001](NHB-SURV-001.md)
