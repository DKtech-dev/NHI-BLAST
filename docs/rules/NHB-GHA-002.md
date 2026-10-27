# NHB-GHA-002 — Untrusted checkout under a privileged trigger

**Base severity:** HIGH · **Dynamic:** CRITICAL when an AWS role is reachable ·
**Precision:** high · **Tags:** github-actions, pwn-request

## What it detects

A workflow triggered by `pull_request_target`, `workflow_run` or `issue_comment`
runs with repository secrets or OIDC, then checks out pull-request head content (or
uses `refs/pull/`) before a `run` or `uses` step.

## Why it matters

That combination executes contributor-controlled content in a context that holds
privileges. It is the classic pwn-request shape: the workflow file is trusted, the
checked-out code is not.

## Evidence

`DECLARED` trigger, checkout reference and credential facts. The execution of
attacker-controlled content is `ASSUMED` (`A-STEP-SHARE`), because repository files
alone cannot prove who controls the checked-out ref.

## Limits

The finding does not prove that the checked-out ref is attacker-controlled or that
the workflow was run with the privileges shown. It does not model branch rules,
environment approvals or CODEOWNERS.

## Remediation

Do not run pull-request code in a privileged trigger. Split the workflow: an
unprivileged workflow builds and uploads artifacts, and a privileged `workflow_run`
consumes only verified artifacts. Avoid checking out the PR head in the privileged
workflow.

## Related

[NHB-GHA-001](NHB-GHA-001.md) · [NHB-GHA-004](NHB-GHA-004.md)
