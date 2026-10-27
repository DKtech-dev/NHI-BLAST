# Benchmark notes

The specification sets two performance budgets (section 12.8):

- graph build plus one scenario for 200 workflows and 2,000 Terraform resources
  under **5 seconds**;
- `rank` over at least 300 mutable actions under **60 seconds**.

`tests/test_performance.py` asserts both budgets with the `slow` marker. The test is
excluded from coverage runs because tracing changes the measured time.

## Measured result

Recorded on 2026-10-26:

| Measurement | Result | Budget |
| --- | --- | --- |
| Repository load | 0.623 s | — |
| Graph build plus one `repo-write` scenario | **1.568 s** | 5 s |
| `rank` | **6.285 s** | 60 s |
| Graph size | 4,202 nodes, 4,199 edges | — |
| Scenario partition | R=400, E=200, Z=1,000 | — |
| Rank rows | 400 | ≥300 |

Machine: Windows 11 (10.0.26200), 12th Gen Intel Core i5-12450H, 15.7 GiB RAM,
Python 3.12.14 (64-bit), local SSD, project virtual environment.

## Real-world corpus

A separate harness scanned ten public repositories (1,959 files: 163 workflow files,
101 Terraform files) twice each with `--simulate-compromise all-mutable-actions`, then
ran `rank` and `export`.

| Measurement | Result |
| --- | --- |
| Repositories / workflow files / Terraform files | 10 / 163 / 101 |
| Scan failures | 0 |
| Scenarios and rank rows | 21 / 21 (equal for every repository) |
| Findings / nodes / edges / diagnostics | 37 / 1,149 / 2,181 / 451 |
| Repeated JSON, SARIF and HTML | byte-identical for every repository |
| Maximum scan time | 1.92 s |
| Maximum rank time | 1.82 s |
| Maximum export time | 1.87 s |

These are sample observations, not a benchmark of all repositories. A separate
16-case adversarial soak (hostile YAML, path traversal, malformed Terraform, deep and
wide plans, HCL, 80 findings and invalid CLI input) completed with no failures and no
undocumented exit code.

## How to reproduce

```sh
./.venv/Scripts/python.exe scripts/gen_fixtures.py "$TEMP/nhi-blast-fx15" \
  --workflows 200 --resources 2000 --actions-per-workflow 2
./.venv/Scripts/python.exe -m pytest -q -m slow -s
```

Generation is deterministic, offline and excluded from the timed section. The test
generates its own fixture through `scripts/gen_fixtures.py` and fails with the
measured duration in the assertion message.

## Why the graph stays bounded

The scale fixture uses a concrete AWS account, region and ARNs. Secrets Manager and
SSM candidate ARNs are therefore concrete rather than `arn:aws:ssm:*:*:...`.
Wildcard candidate ARNs are still compared with exact glob intersection; the
`CandidateFilter` only skips pairs that provably cannot match. This is a soundness
requirement, not an optimisation that may drop authority.

## Caveats

These are single-machine observations, not a portability claim. CI runs the same
budgets on hosted runners. A busy shared runner, antivirus scanning or a slow
filesystem can change the result. Increase the fixture only as a deliberate
product decision; do not relax the budget to make a run green.
