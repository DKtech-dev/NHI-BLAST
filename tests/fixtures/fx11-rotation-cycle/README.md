# fx11-rotation-cycle

Configured credential bindings create a credential-to-role cycle, requiring a batched
rotation step rather than an unsafe sequential order.

Verified 2026-10-26: 7 Terraform resources, 19 nodes, 17 edges, 4 findings;
`repo-write` gives R=2, E=1, Z=3, potential=0 and no diagnostics.
