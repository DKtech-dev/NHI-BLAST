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

## Tests and fixtures

- Unit tests prove one rule or invariant.
- Property-based tests cover globs, conditions and identifier stability.
- Integration tests drive the real CLI and assert exit codes and artifacts.
- Golden files must be reviewed against the specification before being committed.
  Never generate a golden and trust it blindly.
- Fixtures are hostile inputs. Do not add executable code paths to them, and do not
  let fixture content affect lint or type checking.
- Performance gates use the deterministic generator in `scripts/gen_fixtures.py`; see
  `docs/benchmark.md` for the current environment and budgets.

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
- `docs/requirements-traceability.md` maps specification requirements to code and
  tests. Update it when a requirement's status changes.
- `docs/implementation-status.md` records the actual result of each gate. Never mark a
  gate passed without a command and its output.

## Commits and releases

Do not commit generated outputs (`dist/`, `nhi-blast-out/`, caches) or real
credential material. Do not rewrite history or create artificial commits. Publishing,
tagging, deploying or pushing requires explicit authorization from the maintainer;
see `docs/release.md` for the release procedure.

## Licence

By contributing you agree that your contribution is licensed under the MIT License in
`LICENSE`.
