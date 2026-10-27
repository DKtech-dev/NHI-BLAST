# fx10-hcl-fallback

Best-effort HCL ingestion resolves literal policies while unsupported evaluation stays
explicitly unresolved. No Terraform command or expression evaluator is run.

Verified 2026-10-26: 5 Terraform resources, 14 nodes, 11 edges, 2 findings;
`repo-write` gives R=2, E=1, Z=1, potential=1, with `D-TF-HCL-LIMIT` and
`D-TF-UNKNOWN`.
