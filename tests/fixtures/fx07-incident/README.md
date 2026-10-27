# fx07-incident

The SPEC 14.4 reference incident: a mutable action in release and CI jobs, two accepted
roles, four stored credentials and one referenced workflow secret.

The action scenario is `action:tj-actions/changed-files@v45`. Verified 2026-10-26:
2 workflows, 2 jobs, 9 Terraform resources, 26 nodes, 24 edges, 7 findings; R=3, E=2,
Z=5, potential=0 and no diagnostics. Exact console bytes and a compact semantic summary
are reviewed goldens under `tests/golden/`.

The specification's illustrative output uses numbered stage headings and says one
warning. The implementation uses unnumbered headings and emits zero diagnostics for
this fixture; these documentation differences are recorded rather than hidden.
