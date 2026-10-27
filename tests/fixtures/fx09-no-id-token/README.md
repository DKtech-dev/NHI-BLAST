# fx09-no-id-token

Two jobs with different effective permissions prove OIDC authority is job-scoped:
`read-all` and an empty permissions map grant no id-token write access.

Verified 2026-10-26: 2 jobs, 3 Terraform resources, 11 nodes, 8 edges, 3 findings;
`repo-write` gives R=2, E=1, Z=1, potential=0 and no diagnostics.
