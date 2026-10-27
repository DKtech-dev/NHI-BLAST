# fx08-tf-plan-unknowns

Terraform plan unknowns exercise unresolved trust and policy handling. UNKNOWN paths
stay in `potential` and never enter R/E/Z.

Verified 2026-10-26: 6 Terraform resources, 13 nodes, 11 edges, 0 findings;
`repo-write` gives R=2, E=0, Z=0, potential=2 and `D-TF-UNKNOWN`.
