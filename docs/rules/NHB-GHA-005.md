# NHB-GHA-005 — Literal credential in workflow

**Base severity:** HIGH · **Precision:** high · **Tags:** secrets, literal

## What it detects

A scalar value in `env`, `with` or `run` matches one of the tool's literal
credential heuristics (for example an AWS access-key shape or a GitHub token
prefix).

## Why it matters

A credential committed to a workflow can be read by anyone who can read the
repository and may persist in history. The report shows only the credential kind
and length; the value is never stored, printed, logged or embedded in any artifact.

## Evidence

`DECLARED` file line and `H-LITERAL` heuristic. The finding states that a literal
was identified, not that it is valid or that it was obtained by an attacker.

## Limits

This is not a secret scanner. It does not search git history, other file types or
encoded values, and its pattern set is deliberately small. Use a dedicated scanner
(gitleaks, TruffleHog) for commit-history coverage.

## Remediation

Rotate the credential, remove it from the workflow and history, and source it from
GitHub secrets or OIDC. Assume the value is compromised once committed.

## Related

[NHB-GHA-004](NHB-GHA-004.md) · [NHB-CRED-001](NHB-CRED-001.md)
