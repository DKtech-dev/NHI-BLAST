# NHB-GHA-003 — Self-hosted runner

**Base severity:** INFO · **Precision:** high · **Tags:** github-actions, runner

## What it detects

A job targets a self-hosted runner (`runs-on` names a self-hosted label).

## Why it matters

Runner state, local files and non-ephemeral credentials can persist between jobs.
Reachability assumptions that hold for fresh GitHub-hosted runners are not
sufficient: a previous job may have left credentials or code on the host.

## Evidence

`DECLARED` `runs-on`. This is informational and does not by itself indicate a
credential exposure.

## Limits

The scanner cannot see the runner's filesystem, registration, labels or reuse
policy. It does not assert that state persisted or that an attacker can reach the
runner.

## Remediation

Use ephemeral self-hosted runners, avoid persisting credentials on the host, and
isolate jobs that handle production credentials.

## Related

[NHB-GHA-002](NHB-GHA-002.md) · [NHB-GHA-004](NHB-GHA-004.md)
