Offline model. Not executed. Verify in your account.

# Containment playbook (what-if)

- Source report digest: `<source-report-digest>`
- Plan digest: `b5c82bdf2d9fc2fc35f86b9c2725622c19a03e81893682c4fa2ba7f83a6e3b42`
- Every item is a human task. Owners, times and account details are placeholders.

## 1. Revoke role sessions

### Step 1.1: revoke sessions of role `aws:role:arn:aws:iam::111122223333:role/ci-deploy` (plan step 0)

- Owner: `<owner: assign a person or team>`
- Evidence (role): tfstate.json:23 [DECLARED IAM.inline]; tfstate.json:23 [DECLARED TF.role]
- Modelled cutoff: `2026-03-01T10:00:30Z` (source: assumed_revoked_at_plus_30s)
- The cutoff is revoked_at plus an ASSUMED 30 s propagation window (https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html); it is not a guarantee.
- Scenario `action:acme/build-helper@v1`, session `cred:oidc:job:.github/workflows/deploy.yml#deploy:sts.amazonaws.com:sts-session:aws:role:arn:aws:iam::111122223333:role/ci-deploy`: unknown (validity unknown, access unknown, re-issue possible)
- Scenario `repo-write`, session `cred:oidc:job:.github/workflows/deploy.yml#deploy:sts.amazonaws.com:sts-session:aws:role:arn:aws:iam::111122223333:role/ci-deploy`: unknown (validity unknown, access unknown, re-issue possible)
- Scenario `role:aws_iam_role.ci_deploy`, session `cred:oidc:job:.github/workflows/deploy.yml#deploy:sts.amazonaws.com:sts-session:aws:role:arn:aws:iam::111122223333:role/ci-deploy`: unknown (validity unknown, access unknown, re-issue possible)
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

No remove_trust or disable_entrypoint step is in the plan.

## 3. Rotate surviving credentials in dependency order

### Scenario `action:acme/build-helper@v1`

1. Generation 0, single
   - `cred:aws:secret:ci/deploy-key:stored` (not in plan); evidence tfstate.json:63
   - Owner: `<owner: assign a person or team>`
   - Human verification task: confirm in the store that the new value is in use and that the old value no longer authenticates; do not copy values into this document.
   - Rollback / validation: record the previous version identifier before changing it and confirm in your account whether the store keeps it.
2. Generation 0, single
   - `cred:aws:ssm:/ci/registry-token:stored` (in plan, re-exposure risk: a surviving path still reaches it); evidence tfstate.json:91
   - Owner: `<owner: assign a person or team>`
   - Human verification task: confirm in the store that the new value is in use and that the old value no longer authenticates; do not copy values into this document.
   - Rollback / validation: record the previous version identifier before changing it and confirm in your account whether the store keeps it.
3. Generation 1, single
   - `cred:aws:secret:ops/db-password:stored` (not in plan); evidence tfstate.json:77
   - Owner: `<owner: assign a person or team>`
   - Human verification task: confirm in the store that the new value is in use and that the old value no longer authenticates; do not copy values into this document.
   - Rollback / validation: record the previous version identifier before changing it and confirm in your account whether the store keeps it.

### Scenario `repo-write`

1. Generation 0, single
   - `cred:aws:secret:ci/deploy-key:stored` (not in plan); evidence tfstate.json:63
   - Owner: `<owner: assign a person or team>`
   - Human verification task: confirm in the store that the new value is in use and that the old value no longer authenticates; do not copy values into this document.
   - Rollback / validation: record the previous version identifier before changing it and confirm in your account whether the store keeps it.
2. Generation 0, single
   - `cred:aws:ssm:/ci/registry-token:stored` (in plan, re-exposure risk: a surviving path still reaches it); evidence tfstate.json:91
   - Owner: `<owner: assign a person or team>`
   - Human verification task: confirm in the store that the new value is in use and that the old value no longer authenticates; do not copy values into this document.
   - Rollback / validation: record the previous version identifier before changing it and confirm in your account whether the store keeps it.
3. Generation 1, single
   - `cred:aws:secret:ops/db-password:stored` (not in plan); evidence tfstate.json:77
   - Owner: `<owner: assign a person or team>`
   - Human verification task: confirm in the store that the new value is in use and that the old value no longer authenticates; do not copy values into this document.
   - Rollback / validation: record the previous version identifier before changing it and confirm in your account whether the store keeps it.

### Scenario `role:aws_iam_role.ci_deploy`

1. Generation 0, single
   - `cred:aws:secret:ci/deploy-key:stored` (not in plan); evidence tfstate.json:63
   - Owner: `<owner: assign a person or team>`
   - Human verification task: confirm in the store that the new value is in use and that the old value no longer authenticates; do not copy values into this document.
   - Rollback / validation: record the previous version identifier before changing it and confirm in your account whether the store keeps it.
2. Generation 0, single
   - `cred:aws:ssm:/ci/registry-token:stored` (in plan, re-exposure risk: a surviving path still reaches it); evidence tfstate.json:91
   - Owner: `<owner: assign a person or team>`
   - Human verification task: confirm in the store that the new value is in use and that the old value no longer authenticates; do not copy values into this document.
   - Rollback / validation: record the previous version identifier before changing it and confirm in your account whether the store keeps it.
3. Generation 1, single
   - `cred:aws:secret:ops/db-password:stored` (not in plan); evidence tfstate.json:77
   - Owner: `<owner: assign a person or team>`
   - Human verification task: confirm in the store that the new value is in use and that the old value no longer authenticates; do not copy values into this document.
   - Rollback / validation: record the previous version identifier before changing it and confirm in your account whether the store keeps it.

## 4. Verify

- Owner: `<owner: assign a person or team>`
- Human verification task: review CloudTrail inside the exposure window for the roles, sessions and stores named in this playbook; none of that was executed here.
- Rollback / validation: compare the account state with the modelled result below and re-run nhi-blast on the updated repository to confirm the new report.

### Scenario `action:acme/build-helper@v1`

- New runs could still reach: R=2, E=1, Z=3
- Session `cred:oidc:job:.github/workflows/deploy.yml#deploy:sts.amazonaws.com:sts-session:aws:role:arn:aws:iam::111122223333:role/ci-deploy` may have been issued before containment (modelled); at most 3600 s remain.
- Re-exposure risk: `cred:aws:ssm:/ci/registry-token:stored`
- Residual E path to `cred:oidc:job:.github/workflows/deploy.yml#deploy:sts.amazonaws.com:sts-session:aws:role:arn:aws:iam::111122223333:role/ci-deploy` (2 edge(s))
- Residual Z path to `cred:aws:secret:ci/deploy-key:stored` (4 edge(s))
- Residual Z path to `cred:aws:secret:ops/db-password:stored` (7 edge(s))
- Residual Z path to `cred:aws:ssm:/ci/registry-token:stored` (4 edge(s))

### Scenario `repo-write`

- New runs could still reach: R=2, E=1, Z=3
- Session `cred:oidc:job:.github/workflows/deploy.yml#deploy:sts.amazonaws.com:sts-session:aws:role:arn:aws:iam::111122223333:role/ci-deploy` may have been issued before containment (modelled); at most 3600 s remain.
- Re-exposure risk: `cred:aws:ssm:/ci/registry-token:stored`
- Residual E path to `cred:oidc:job:.github/workflows/deploy.yml#deploy:sts.amazonaws.com:sts-session:aws:role:arn:aws:iam::111122223333:role/ci-deploy` (2 edge(s))
- Residual Z path to `cred:aws:secret:ci/deploy-key:stored` (3 edge(s))
- Residual Z path to `cred:aws:secret:ops/db-password:stored` (6 edge(s))
- Residual Z path to `cred:aws:ssm:/ci/registry-token:stored` (3 edge(s))

### Scenario `role:aws_iam_role.ci_deploy`

- New runs could still reach: R=0, E=1, Z=3
- Session `cred:oidc:job:.github/workflows/deploy.yml#deploy:sts.amazonaws.com:sts-session:aws:role:arn:aws:iam::111122223333:role/ci-deploy` may have been issued before containment (modelled); at most 3600 s remain.
- Re-exposure risk: `cred:aws:ssm:/ci/registry-token:stored`
- Residual E path to `cred:oidc:job:.github/workflows/deploy.yml#deploy:sts.amazonaws.com:sts-session:aws:role:arn:aws:iam::111122223333:role/ci-deploy` (0 edge(s))
- Residual Z path to `cred:aws:secret:ci/deploy-key:stored` (2 edge(s))
- Residual Z path to `cred:aws:secret:ops/db-password:stored` (5 edge(s))
- Residual Z path to `cred:aws:ssm:/ci/registry-token:stored` (2 edge(s))

## Warnings

- W-WHATIF-REVOKE-WITHOUT-REMOVE-TRUST: re_issue_possible: aws:role:arn:aws:iam::111122223333:role/ci-deploy
