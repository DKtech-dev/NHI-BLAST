# Contributing to NHI-Blast

Read `docs/SPEC.md` and `AGENTS.md` before changing behaviour. `docs/SPEC.md` is the
normative requirements source; `AGENTS.md` is the engineering and security contract.
Where they disagree, the specification wins.

## Set up

```
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev,hcl]"
```

On Windows use `.venv\Scripts\python.exe`. The optional `hcl` extra installs the
Terraform HCL fallback parser. The optional `rich` extra improves console rendering;
the CLI works without it.

`requirements.lock` and `requirements-dev.lock` contain exact version pins used for
reproducible installs and CI. They are version locks, not hash locks; verify the
resolved versions with `pip-audit` before a release.

## Run the checks

```
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
python -m mypy src
python -m pytest
python -m pytest -m security
python -m pytest -m golden
python -m pytest -m slow
python -m coverage report
python scripts/gen_schema.py --check
```

All warnings are errors in the test configuration. A change is not complete until the
full suite, ruff, formatting and `mypy --strict` pass. Do not weaken, skip or delete a
test to obtain a green run; fix the cause and add a regression test.

## Test programme

The suite is built from focused unit tests, property-based tests for the glob,
condition and identifier logic, integration tests that drive the real CLI and assert
exit codes and artifacts, adversarial security tests for every output boundary, and
reviewed golden files. The markers above select the security, golden and performance
subsets; run them separately as well as within the full suite.

- **Fixtures.** `tests/fixtures/fx01`–`fx15` are deterministic repositories; the
  inventory of verified counts, R/E/Z sizes, findings and diagnostics is
  `tests/fixtures/README.md`. The scale fixture is generated reproducibly by
  `scripts/gen_fixtures.py`. No fixture contains a real credential; placeholder
  canaries are synthetic and exist only for leak tests.
- **Goldens.** `tests/golden/fx07-console.txt` and `fx07-summary.json` are exact
  reviewed output checked against the specification. A failing golden is a behaviour
  change first and a file update second; never regenerate and accept it blindly.
- **Labelled evaluation.** `scripts/evaluate_labelled.py` replays 14 labelled synthetic
  cases and exits non-zero on any mismatch. It is regression coverage for those
  labels, not real-world detection accuracy, and its counts must not be cited as such.
- **Determinism and offline behaviour.** Repeated scans must produce byte-identical
  console, JSON, SARIF and HTML, including for reversed selector order and
  rank/export; a socket guard proves the runtime makes no network call. No wall-clock
  time appears in artifacts unless `--timestamp` is given.
- **Coverage.** `scripts/check_coverage.py` enforces at least 80% overall line coverage
  and at least 80% for every module under `nhi_blast/aws/`, `nhi_blast/analysis/` and
  `nhi_blast/report/`. Coverage runs exclude the `slow` marker so tracing does not
  distort the performance measurement; run performance tests without instrumentation.
- **Performance.** `tests/test_performance.py` asserts the specification budgets against
  the generated 200-workflow, 2,000-resource fixture and reports the measured duration
  on failure. Recorded results and the machine description are in
  [benchmark](docs/benchmark.md); they are one-machine observations, not a portability
  claim.
- **Platforms.** CI runs Ubuntu and Windows on Python 3.12, 3.13 and 3.14. Tests that
  create filesystem symlinks skip with the operating-system error when the host cannot
  create them; on Windows this occurs when symlink creation is unavailable, such as
  without Developer Mode or elevation. The Windows junction-based escape tests do not
  need symlink privileges and run in the Windows matrix; the `mklink`-based case skips
  if junction creation fails.
- **Packaging.** Distribution builds and clean installs are release checks, not part of
  the test suite: build a wheel and sdist, run `scripts/check_artifacts.py`, install the
  wheel into a fresh environment with `-c requirements.lock`, and compare repeated build
  digests. See [release procedure](docs/release.md) and the
  [production readiness record](docs/production-readiness.md).

## Windows standalone executable

The single-file `nhi-blast-windows-x64.exe` is built with PyInstaller from a clean
virtual environment. `requirements-windows-build.lock` pins the build-only toolchain
separately so the runtime dependency locks stay unchanged. The build bundles the
Python runtime, `src/nhi_blast/data/*.yaml`, the report assets, `rich` and the optional
HCL parser; no source checkout or installed Python is required at run time.

In a Git Bash shell on Windows x64:

```
python -m venv .buildcheck/windows-venv
.buildcheck/windows-venv/Scripts/python.exe -m pip install -c requirements-dev.lock hatchling editables
.buildcheck/windows-venv/Scripts/python.exe -m pip install -c requirements-dev.lock --no-build-isolation -e ".[dev,rich,hcl]"
.buildcheck/windows-venv/Scripts/python.exe -m pip install -c requirements-dev.lock -c requirements-windows-build.lock pyinstaller==6.22.3
.buildcheck/windows-venv/Scripts/python.exe scripts/build_windows_exe.py
.buildcheck/windows-venv/Scripts/python.exe scripts/check_artifacts.py dist/windows --windows-exe dist/windows/nhi-blast-windows-x64.exe
```

The build writes `dist/windows/nhi-blast-windows-x64.exe` and its `.sha256` record.
Verify the executable itself with
`NHI_BLAST_WINDOWS_EXE=$PWD/dist/windows/nhi-blast-windows-x64.exe .buildcheck/windows-venv/Scripts/python.exe -m pytest -q tests/test_windows_executable.py`
and rerun it from a directory outside the checkout with a restricted `PATH` to confirm
it does not depend on the repository venv or an installed Python. The parity tests
compare the frozen executable with `NHI_BLAST_REFERENCE_CLI` (default: the installed
`nhi-blast`) for findings, R/E/Z, formats, exit codes and diagnostics; they skip off
Windows or when the executable variable is unset.

`.github/workflows/build-windows.yml` runs the same build and checks on a
`windows-latest` runner by manual `workflow_dispatch`. It uploads the executable and
checksum as a build artifact only; it does not sign, tag, release or publish anything.
The executable is unsigned, so downloading it from a release may trigger a
reputation-based SmartScreen warning.

## Architecture and boundaries

The pipeline is: discovery → pure parsers → typed facts → resolvers → graph builder →
analysis → reporters → CLI. Keep these boundaries:

- Parsers receive a relative path and text only. They do no cross-file I/O and never
  raise on hostile input; they return partial facts plus diagnostics.
- Platform facts live in `src/nhi_blast/data/*.yaml` with `source_url` and
  `verified_on`. Evaluation logic lives in one module, not duplicated per consumer.
- Every node and edge carries evidence. Edge confidence is the weakest evidence class
  among its items. UNKNOWN-class edges never enter R, E or Z.
- Outputs must be deterministic and byte-identical for equal inputs. Sort keys and
  arrays; do not leak set iteration order; do not add wall-clock time unless the
  `--timestamp` option was given.

`docs/architecture.md` describes the layers, graph rules and reporting model in more
detail.

## Security rules for contributions

1. Never store, print, log, embed or snapshot a credential value. Tests that need a
   literal credential must use an obviously fake value and assert that it does not
   appear in any output.
2. Never execute scanned content, evaluate `${{ ... }}` expressions, or make network
   requests at runtime.
3. Resolve every path and keep it inside the scan root. Do not follow links that
   escape it.
4. Treat every string from a scanned file as hostile. The HTML reporter must keep its
   escaped JSON block, its text-only DOM construction and its restrictive CSP with
   inline-script hashes.
5. Do not add scope from the prohibited list in `AGENTS.md` (GCP, Azure, Kubernetes,
   MCP, GitLab, live API collection, SaaS, database-backed web applications).

If you believe a security property is wrong, write an adversarial test first and open
a private report as described in `SECURITY.md` rather than a public issue.

## Platform data updates

When GitHub or AWS documentation changes:

1. Update the affected file under `src/nhi_blast/data/`.
2. Update `source_url` and `verified_on`. Do not backdate verification.
3. Adjust evaluation logic and tests if semantics changed.
4. Update `docs/data-provenance.md` and, where relevant, `docs/assumptions.md`.
5. Record any unresolved disagreement between vendors in the data-file comment and
   treat the uncertain part as ASSUMED.

## Documentation

- `docs/rules/NHB-*.md` documents one finding per file. Keep the language
  evidence-honest: say "potentially reachable", "accepted by the trust policy as
  written" and "survives revocation if the path was exercised". Do not claim proof,
  exploitability, guarantee or takeover.
- Keep `docs/SPEC.md` normative text and committed evidence records accurate; do not
  restate a gate result without the command and its output.
- Run `python -m pytest tests/test_docs.py` after changing links or documentation: it
  checks every local link, rule page and documented CLI command.

## Commits and releases

Do not commit generated outputs (`dist/`, `nhi-blast-out/`, caches) or real
credential material. Do not rewrite history or create artificial commits. Publishing,
tagging, deploying or pushing requires explicit authorization from the maintainer;
see `docs/release.md` for the release procedure.

## Licence

This repository is licensed under the MIT License; see `LICENSE`. By submitting a
contribution you confirm that it is your original work, or that you have the right to
submit it, and you agree that it is licensed under the same MIT terms. Do not submit
code, documentation or assets whose licence is incompatible with MIT. Third-party
components must keep their copyright and licence notices, and new bundled components
must be added to `THIRD_PARTY_NOTICES.md`. Open an issue before a large change; the
maintainer is not obliged to review or merge a contribution.
