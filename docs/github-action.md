# GitHub Action

NHI-Blast ships a composite GitHub Action under `action/action.yml` with SHA-pinned
dependencies. It runs offline against checked-out repository files and writes JSON,
SARIF, and self-contained HTML reports.

## Scan workflow example

Pin the action to the full 40-character commit SHA for the `v0.3.0` release (replace
`<commit-sha>` with the commit hash of the `v0.3.0` tag) and disable credential
persistence on checkout:

```yaml
name: NHI-Blast
on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read
  security-events: write

jobs:
  nhi-blast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
        with:
          persist-credentials: false
      - uses: DKtech-dev/nhi-blast/action@<commit-sha>  # v0.3.0
        with:
          path: "."
          repo: "${{ github.repository }}"
          out-dir: "nhi-blast-out"
          install-spec: "git+https://github.com/DKtech-dev/nhi-blast.git@v0.3.0"
          simulate-compromise: "repo-write"
          upload-sarif: "true"
```

## Key inputs

- `install-spec`: Package specifier, wheel URL/path, or Git URL passed to `pip install`.
  Because `0.3.0` is distributed via GitHub Releases and is **not yet published on PyPI**,
  pass a release wheel URL (for example,
  `https://github.com/DKtech-dev/nhi-blast/releases/download/v0.3.0/nhi_blast-0.3.0-py3-none-any.whl`),
  a local checkout path (`.`), or a tagged Git URL
  (`git+https://github.com/DKtech-dev/nhi-blast.git@v0.3.0`).
- `simulate-compromise`: Optional compromise selector passed to `--simulate-compromise`
  (for example `repo-write`, `fork-pr`, `all-mutable-actions`, or
  `action:OWNER/REPO@REF`) to include R/E/Z survival and rotation-plan analysis in the
  generated reports.

## Fork safety

SARIF upload runs even when findings exceed `fail-on` (unless the job is cancelled) and is
automatically skipped on pull requests originating from forks
(`github.event.pull_request.head.repo.fork == true`), avoiding permission errors on
read-only fork tokens while still generating artifacts and writing the step summary.

## Diff gating

Set `mode: diff`, `base-report: path/to/base.json`, and `fail-on: high` (or
`critical`, `medium`, `low`, `never`) to fail a pull request only when new findings
appear under comparable analysis. In `diff` mode, the initial scan runs with
`--fail-on never` so the diff gate controls the exit code.
