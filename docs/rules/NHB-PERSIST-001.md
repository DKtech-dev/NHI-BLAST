# NHB-PERSIST-001: Reachable IAM role holds out-of-band persistence permissions

A reachable AWS role is permitted to call one or more IAM persistence actions (`iam:CreateAccessKey`, `iam:UpdateAssumeRolePolicy`, `iam:PutRolePolicy`, `iam:AttachRolePolicy`, `iam:CreateLoginProfile`, `iam:AddUserToGroup`).

## Why this matters

`AWSRevokeOlderSessions` and secret rotation do not revoke newly created IAM access keys or modified trust policies. Incident response must include a Cloud Persistence Audit.

## Remediation

Remove IAM mutation permissions from CI/CD roles or cap them with a permissions boundary.
