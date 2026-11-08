Offline model. Not executed. Verify in your account.

# Containment playbook (what-if)

- Source report digest: `<source-report-digest>`
- Plan digest: `6f56eadb1da1fbe3448acd4da5fa5cbd5e5b1107574b9492b17730eef2d3806e`
- Every item is a human task. Owners, times and account details are placeholders.

## 1. Revoke role sessions

### Step 1.1: revoke sessions of role `aws:role:arn:aws:iam::111122223333:role/ci-deploy` (plan step 0)

- Owner: `<owner: assign a person or team>`
- Evidence (role): tfstate.json:23 [DECLARED IAM.inline]; tfstate.json:23 [DECLARED TF.role]
- Modelled cutoff: `2026-03-01T10:00:30Z` (source: assumed_revoked_at_plus_30s)
- The cutoff is revoked_at plus an ASSUMED 30 s propagation window (https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html); it is not a guarantee.
- Scenario `action:acme/build-helper@v1`, session `cred:oidc:job:.github/workflows/deploy.yml#deploy:sts.amazonaws.com:sts-session:aws:role:arn:aws:iam::111122223333:role/ci-deploy`: access denied - expiry not established (validity unknown, access denied_by_revocation_policy)
- Scenario `repo-write`, session `cred:oidc:job:.github/workflows/deploy.yml#deploy:sts.amazonaws.com:sts-session:aws:role:arn:aws:iam::111122223333:role/ci-deploy`: access denied - expiry not established (validity unknown, access denied_by_revocation_policy)
- Scenario `role:aws_iam_role.ci_deploy`, session `cred:oidc:job:.github/workflows/deploy.yml#deploy:sts.amazonaws.com:sts-session:aws:role:arn:aws:iam::111122223333:role/ci-deploy`: access denied - expiry not established (validity unknown, access denied_by_revocation_policy)
- Human verification task: In the IAM console confirm that the role carries the AWSRevokeOlderSessions inline policy, that its condition compares aws:TokenIssueTime with the cutoff above, and review CloudTrail for sessions of this role issued after the cutoff.
- Rollback / validation: Removing the inline policy undoes the deny for every user of the role. Try the change on a non-production role first and record the role's current inline policies before editing.

Caveats that apply to every revoke step:
- Sessions issued inside the propagation window (the assumed 30 s before the cutoff) are covered by the deny.
- Sessions issued after the cutoff are not covered; a role that can still be assumed yields new sessions.
- The deny applies to every user of the role, including legitimate sessions issued before the cutoff.
- Service-linked roles cannot be revoked this way.
- Derived credentials (chained role sessions, access keys created by the session, secrets already read) are not affected by the deny; role chaining is not modelled, so they are listed as residual_unknown.
- The 30 s propagation window is ASSUMED from https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html ("approximately 30 seconds into the future") and is not a guarantee.

## 2. Remove trust or disable entrypoint

### Step 2.1: remove trust into `aws:role:arn:aws:iam::111122223333:role/ci-deploy` (plan step 1)

- Owner: `<owner: assign a person or team>`
- Evidence (edge `48129c6636e0a2e4`): .github/workflows/deploy.yml:4 [DERIVED OIDC.subject]; tfstate.json:23 [DECLARED IAM.inline]; tfstate.json:23 [DECLARED IAM.trust]; tfstate.json:23 [DERIVED R8.can-assume]
- Modelled edges removed: 1
- Human verification task: In the role's trust policy confirm that the statement that accepts the principal is gone, and that existing sessions of the role are handled by a revocation step (removing trust does not end sessions already issued).
- Rollback / validation: Restore the previous trust policy document; keep a copy before editing and validate the change with the policy simulator or a test assumption.

### Step 2.2: remove trust into `aws:role:arn:aws:iam::111122223333:role/ops-admin` (plan step 2)

- Owner: `<owner: assign a person or team>`
- Evidence (edge `984179f9d879fc03`): nhi-blast.toml [DECLARED CONFIG.credential-binding]; nhi-blast.toml [ASSUMED R12.credential-binding]
- Modelled edges removed: 1
- Human verification task: In the role's trust policy confirm that the statement that accepts the principal is gone, and that existing sessions of the role are handled by a revocation step (removing trust does not end sessions already issued).
- Rollback / validation: Restore the previous trust policy document; keep a copy before editing and validate the change with the policy simulator or a test assumption.

### Step 2.3: disable entrypoint `job:.github/workflows/deploy.yml#deploy` (plan step 3)

- Owner: `<owner: assign a person or team>`
- Evidence (edge `01f61567a0a698c3`): .github/workflows/deploy.yml:14 [DECLARED R2.action-use]
- Evidence (edge `34c2b215977833e7`): .github/workflows/deploy.yml:12 [DECLARED R3.github-token]
- Evidence (edge `a04693df1c8a7348`): .github/workflows/deploy.yml:15 [DECLARED R2.action-use]
- Evidence (edge `c4d27ac3e0afdd1c`): .github/workflows/deploy.yml:12 [DERIVED R6.oidc-identity]; .github/workflows/deploy.yml:7 [DECLARED GHA.perm.workflow]
- Evidence (edge `d66a0003c6773155`): .github/workflows/deploy.yml:12 [DERIVED R3.oidc-request-token]; .github/workflows/deploy.yml:7 [DECLARED GHA.perm.workflow]
- Evidence (edge `ebdeed2ae34fd1e3`): .github/workflows/deploy.yml:16 [DECLARED R2.action-use]
- Modelled edges removed: 6
- Human verification task: Confirm in the repository settings that the workflow or job can no longer start, and review recent runs for the exposure window.
- Rollback / validation: Re-enable the workflow after the surviving credentials are rotated; validate with a run on a branch that has no deploy permissions.

## 3. Rotate surviving credentials in dependency order

### Scenario `action:acme/build-helper@v1`

1. Generation 0, single
   - `cred:aws:secret:ci/deploy-key:stored` (in plan); evidence tfstate.json:63
   - Owner: `<owner: assign a person or team>`
   - Human verification task: confirm in the store that the new value is in use and that the old value no longer authenticates; do not copy values into this document.
   - Rollback / validation: record the previous version identifier before changing it and confirm in your account whether the store keeps it.
2. Generation 0, single
   - `cred:aws:ssm:/ci/registry-token:stored` (in plan); evidence tfstate.json:91
   - Owner: `<owner: assign a person or team>`
   - Human verification task: confirm in the store that the new value is in use and that the old value no longer authenticates; do not copy values into this document.
   - Rollback / validation: record the previous version identifier before changing it and confirm in your account whether the store keeps it.
3. Generation 1, single
   - `cred:aws:secret:ops/db-password:stored` (in plan); evidence tfstate.json:77
   - Owner: `<owner: assign a person or team>`
   - Human verification task: confirm in the store that the new value is in use and that the old value no longer authenticates; do not copy values into this document.
   - Rollback / validation: record the previous version identifier before changing it and confirm in your account whether the store keeps it.

### Scenario `repo-write`

1. Generation 0, single
   - `cred:aws:secret:ci/deploy-key:stored` (in plan); evidence tfstate.json:63
   - Owner: `<owner: assign a person or team>`
   - Human verification task: confirm in the store that the new value is in use and that the old value no longer authenticates; do not copy values into this document.
   - Rollback / validation: record the previous version identifier before changing it and confirm in your account whether the store keeps it.
2. Generation 0, single
   - `cred:aws:ssm:/ci/registry-token:stored` (in plan); evidence tfstate.json:91
   - Owner: `<owner: assign a person or team>`
   - Human verification task: confirm in the store that the new value is in use and that the old value no longer authenticates; do not copy values into this document.
   - Rollback / validation: record the previous version identifier before changing it and confirm in your account whether the store keeps it.
3. Generation 1, single
   - `cred:aws:secret:ops/db-password:stored` (in plan); evidence tfstate.json:77
   - Owner: `<owner: assign a person or team>`
   - Human verification task: confirm in the store that the new value is in use and that the old value no longer authenticates; do not copy values into this document.
   - Rollback / validation: record the previous version identifier before changing it and confirm in your account whether the store keeps it.

### Scenario `role:aws_iam_role.ci_deploy`

1. Generation 0, single
   - `cred:aws:secret:ci/deploy-key:stored` (in plan, re-exposure risk: a surviving path still reaches it); evidence tfstate.json:63
   - Owner: `<owner: assign a person or team>`
   - Human verification task: confirm in the store that the new value is in use and that the old value no longer authenticates; do not copy values into this document.
   - Rollback / validation: record the previous version identifier before changing it and confirm in your account whether the store keeps it.
2. Generation 0, single
   - `cred:aws:ssm:/ci/registry-token:stored` (in plan, re-exposure risk: a surviving path still reaches it); evidence tfstate.json:91
   - Owner: `<owner: assign a person or team>`
   - Human verification task: confirm in the store that the new value is in use and that the old value no longer authenticates; do not copy values into this document.
   - Rollback / validation: record the previous version identifier before changing it and confirm in your account whether the store keeps it.
3. Generation 1, single
   - `cred:aws:secret:ops/db-password:stored` (in plan); evidence tfstate.json:77
   - Owner: `<owner: assign a person or team>`
   - Human verification task: confirm in the store that the new value is in use and that the old value no longer authenticates; do not copy values into this document.
   - Rollback / validation: record the previous version identifier before changing it and confirm in your account whether the store keeps it.

## 4. Verify

- Owner: `<owner: assign a person or team>`
- Human verification task: review CloudTrail inside the exposure window for the roles, sessions and stores named in this playbook; none of that was executed here.
- Rollback / validation: compare the account state with the modelled result below and re-run nhi-blast on the updated repository to confirm the new report.

### Scenario `action:acme/build-helper@v1`

- New runs could still reach: R=0, E=0, Z=0
- Session `cred:oidc:job:.github/workflows/deploy.yml#deploy:sts.amazonaws.com:sts-session:aws:role:arn:aws:iam::111122223333:role/ci-deploy` may have been issued before containment (modelled); at most 3600 s remain.

### Scenario `repo-write`

- New runs could still reach: R=0, E=0, Z=0
- Session `cred:oidc:job:.github/workflows/deploy.yml#deploy:sts.amazonaws.com:sts-session:aws:role:arn:aws:iam::111122223333:role/ci-deploy` may have been issued before containment (modelled); at most 3600 s remain.

### Scenario `role:aws_iam_role.ci_deploy`

- New runs could still reach: R=0, E=1, Z=2
- Session `cred:oidc:job:.github/workflows/deploy.yml#deploy:sts.amazonaws.com:sts-session:aws:role:arn:aws:iam::111122223333:role/ci-deploy` may have been issued before containment (modelled); at most 3600 s remain.
- Re-exposure risk: `cred:aws:secret:ci/deploy-key:stored`
- Re-exposure risk: `cred:aws:ssm:/ci/registry-token:stored`
- Residual E path to `cred:oidc:job:.github/workflows/deploy.yml#deploy:sts.amazonaws.com:sts-session:aws:role:arn:aws:iam::111122223333:role/ci-deploy` (0 edge(s))
- Residual Z path to `cred:aws:secret:ci/deploy-key:stored` (2 edge(s))
- Residual Z path to `cred:aws:ssm:/ci/registry-token:stored` (2 edge(s))

## Rejected plan entries

- Step 7 `inject_deny_policy`: rejected (arbitrary deny-policy injection is not modelled in v0.3.0)
- Step 8 `teleport`: unsupported

## Warnings

- W-WHATIF-REPO-WRITE-ACCEPTANCE-CLEARED: aws:role:arn:aws:iam::111122223333:role/ci-deploy
