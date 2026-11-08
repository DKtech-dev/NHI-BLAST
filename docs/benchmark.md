# Benchmark notes

The specification sets two performance budgets (section 12.8):

- graph build plus one scenario for 200 workflows and 2,000 Terraform resources
  under **5 seconds**;
- `rank` over at least 300 mutable actions under **60 seconds**.

`tests/test_performance.py` asserts both budgets with the `slow` marker. The test is
excluded from coverage runs because tracing changes the measured time.

## Historical timing re-run (2026-10-28)

Recorded on 2026-10-28 on the current source tree with the `slow` marker:

| Measurement | Result | Budget |
| --- | --- | --- |
| Graph build plus one `repo-write` scenario | **2.30 s** | 5 s |
| `rank` over 400 mutable actions | **5.36 s** | 60 s |

Machine: Windows 11 (10.0.26200), 12th Gen Intel Core i5-12450H, 15.7 GiB RAM,
Python 3.12.14 (64-bit), local SSD, project virtual environment. These are
single-run timings from `pytest -m slow --durations=0`, not a distribution.

The earlier full run on 2026-10-26 recorded 0.623 s for repository load, 1.568 s for
the graph-and-scenario budget, 6.285 s for `rank`, and a graph of 4,202 nodes and
4,199 edges with R=400, E=200, Z=1,000 and 400 rank rows. The structural counts come
from the deterministic scale fixture; the timings vary with the machine and load.

## Historical public corpus (2026-10-26)

A separate harness recorded on 2026-10-26 scanned ten public repositories (1,959
files: 163 workflow files, 101 Terraform files) twice each with
`--simulate-compromise all-mutable-actions`, then ran `rank` and `export`. It was not
re-run for the presentation pass.

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

## Current public-corpus verification (2026-11-03)

A freshly built and isolated-installed 0.3.0b1 wheel scanned the existing hash-pinned snapshots twice. There were **14 external repositories plus one historical self-control**, 3,620 manifest-verified files, and **no scan failures**. JSON, SARIF and HTML were schema/correspondence-checked and byte-identical between repeats; inputs were unchanged after the run.

External-only first-repeat observations: 56 findings, 591 nodes, 779 edges and 269 diagnostics. Loaded files included 81 workflows, 84 local action files, 344 HCL files, 34 Terraform JSON files and two explicit IAM documents. Loaded files are not necessarily fully parsed or supported. The self-control is excluded from these totals.

These are robustness and determinism observations, **not measured detection accuracy**. Independently adjudicated public-corpus labels: zero, so precision, recall, F1 and accuracy confidence intervals are not reported. The selected tool/module repositories are not a representative random sample; findings within a repository are correlated. Any future labelled study must report actual positive/negative units, single-labeller limitations, and repository-cluster confidence intervals. Synthetic regression tests remain a separate tier.

The maximum observed external scan was 5.73 seconds amid concurrent checks. Two repeats are insufficient to estimate a latency distribution or claim general performance. See the [current verification record](<release/verification-2026-11-03.md>) and the [portable result summary](<release/corpus-summary-2026-11-03.json>) for exact revisions, license metadata, run times and limits. No downloaded source was executed or redistributed.

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
