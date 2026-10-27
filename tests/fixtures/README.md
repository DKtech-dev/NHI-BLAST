# Test fixture inventory

The fx01–fx15 repositories are deterministic, local-only inputs. They contain no
credential values. Terraform sensitive fields use non-credential sentinels solely to
prove those fields are discarded; `tests/test_fixtures.py` checks the sentinels never
reach a report.

Counts below were verified on 2026-10-26 through `load_repository`,
`build_repository_graph`, and a `repo-write` scan. `Potential` is separate from R/E/Z.

| Fixture | Purpose | Workflows / jobs / TF resources | Nodes / edges | Findings | R / E / Z | Potential | Diagnostics |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fx01-minimal | Minimal workflow with no cloud authority | 1 / 1 / 0 | 5 / 4 | 0 | 1 / 0 / 0 | 0 | — |
| fx02-exact-trust | Exact tag trust and one readable sink | 1 / 1 / 3 | 13 / 10 | 2 | 2 / 1 / 1 | 0 | — |
| fx03-wildcard-trust | Wildcard, unconstrained, dead-key and audience trust cases | 1 / 1 / 6 | 18 / 12 | 7 | 2 / 3 / 1 | 0 | — |
| fx04-environment | Literal and expression environments | 1 / 2 / 2 | 16 / 14 | 1 | 4 / 1 / 0 | 1 | D-EXPR-VALUE |
| fx05-pull-request | Pull-request subject and untrusted checkout behavior | 2 / 2 / 2 | 14 / 12 | 2 | 3 / 1 / 0 | 0 | D-GHA-UNTRUSTED-CHECKOUT |
| fx06-composite | Nested, cyclic and over-depth composite actions | 1 / 4 / 0 | 23 / 23 | 1 | 4 / 0 / 1 | 0 | D-GHA-COMPOSITE-CYCLE, D-GHA-COMPOSITE-DEPTH |
| fx07-incident | SPEC 14.4 incident and golden output | 2 / 2 / 9 | 26 / 24 | 7 | 3 / 2 / 5 | 0 | — |
| fx08-tf-plan-unknowns | Unknown plan fields produce separate potential paths | 1 / 1 / 6 | 13 / 11 | 0 | 2 / 0 / 0 | 2 | D-TF-UNKNOWN |
| fx09-no-id-token | Per-job permissions prevent cross-job OIDC reach | 1 / 2 / 3 | 11 / 8 | 3 | 2 / 1 / 1 | 0 | — |
| fx10-hcl-fallback | Literal HCL resolution and explicit unresolved limits | 1 / 1 / 5 | 14 / 11 | 2 | 2 / 1 / 1 | 1 | D-TF-HCL-LIMIT, D-TF-UNKNOWN |
| fx11-rotation-cycle | Stored credentials unlock roles in a rotation cycle | 1 / 1 / 7 | 19 / 17 | 4 | 2 / 1 / 3 | 0 | — |
| fx12-untrusted-checkout | Privileged triggers with attacker-controlled checkout | 2 / 2 / 2 | 15 / 13 | 5 | 3 / 1 / 1 | 0 | D-GHA-UNTRUSTED-CHECKOUT |
| fx13-secrets-inherit | Reusable workflows and whole-secret exposure | 2 / 3 / 3 | 28 / 26 | 5 | 6 / 3 / 2 | 2 | D-GHA-SECRETS-ALL |
| fx14-hostile | Duplicate YAML keys and Unicode paths | 2 / 2 / 3 | 18 / 15 | 3 | 3 / 1 / 3 | 0 | D-YAML-DUPKEY |
| fx15-scale-smoke | Generated scale-shape smoke fixture | 4 / 4 / 40 | 86 / 83 | 33 | 8 / 4 / 20 | 0 | D-TF-ROTATION-UNBOUND |

Regenerate the smoke fixture from the repository root:

```sh
./.venv/Scripts/python.exe scripts/gen_fixtures.py tests/fixtures/fx15-scale-smoke \
  --workflows 4 --resources 40 --actions-per-workflow 2
```

Generate the full SPEC 12.8 performance repository in a temporary directory:

```sh
./.venv/Scripts/python.exe scripts/gen_fixtures.py "$TEMP/nhi-blast-fx15" \
  --workflows 200 --resources 2000 --actions-per-workflow 2
```

The full repository has 200 jobs and 400 mutable action use sites. Generation is
deterministic and performs no network access. Review fixture changes and golden diffs
against `docs/SPEC.md`; never regenerate goldens merely to make a test pass.
