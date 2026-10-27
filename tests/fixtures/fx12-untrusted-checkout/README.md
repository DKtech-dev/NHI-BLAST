# fx12-untrusted-checkout

Workflow-run and issue-comment jobs check out attacker-controlled revisions under
privileged triggers.

Verified 2026-10-26: 2 workflows, 2 jobs, 15 nodes, 13 edges, 5 findings; `repo-write`
gives R=3, E=1, Z=1, potential=0 and `D-GHA-UNTRUSTED-CHECKOUT`.
