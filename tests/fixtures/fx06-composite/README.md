# fx06-composite

Local composite actions cover nesting, cycles and the depth limit. Expansion remains in
the calling job and terminates with diagnostics on invalid structures.

Verified 2026-10-26: 4 jobs, 23 nodes, 23 edges, 1 finding; `repo-write` gives R=4,
E=0, Z=1, potential=0, with `D-GHA-COMPOSITE-CYCLE` and `D-GHA-COMPOSITE-DEPTH`.
