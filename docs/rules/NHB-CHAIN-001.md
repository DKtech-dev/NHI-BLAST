# NHB-CHAIN-001: Intra-input STS role chaining extends blast radius

A reachable AWS role can call `sts:AssumeRole` on another IAM role present in the scanned inputs whose trust policy accepts it without an explicit deny.

## Why this matters

Chaining extends the effective blast radius across role boundaries. AWS caps chained STS sessions at 3,600 seconds.

## Remediation

Remove unused `sts:AssumeRole` permissions or restrict target role trust policies.
