# Release procedure

This document describes how a release is prepared and checked. It is a procedure, not
evidence that a release happened. No version of NHI-Blast has been published, tagged
or deployed. The current gate results are in `docs/production-readiness.md`.

## Preconditions

1. The working tree is clean and reviewed. Do not build a release from a dirty tree.
2. `CHANGELOG.md` describes the release and the version in `pyproject.toml` matches.
3. `requirements.lock` and `requirements-dev.lock` are regenerated and audited.
4. The primary-source dates in the data files are current enough for the release; see
   `docs/data-provenance.md`.
5. Every gate in `docs/production-readiness.md` has a recorded command and result.
6. Explicit authorization to tag or publish has been given. Preparing artifacts
   locally does not imply authorization to distribute them.

## 1. Run the full gate set

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

All commands must succeed. A skipped test must be explained in
`docs/implementation-status.md`; a skipped test is not a pass.

## 2. Build the distributions

```
rm -rf dist
python -m hatchling build -t wheel -d dist
python -m hatchling build -t sdist -d dist
python scripts/check_artifacts.py dist
```

The artifact checker requires exactly one wheel and one sdist. It verifies that the
wheel contains all eight platform data files and the three vendored report assets
plus `MANIFEST.json`, that runtime metadata excludes test tooling, and that neither
artifact contains caches, the private research cache, scratch files or the local
output directory.

## 3. Verify installation in a clean environment

Create a fresh virtual environment per platform and install from the built wheel.
Install the runtime lock alongside it so dependency versions are exact:

```
python -m venv /tmp/nhi-blast-consumer
/tmp/nhi-blast-consumer/bin/python -m pip install --upgrade pip
/tmp/nhi-blast-consumer/bin/python -m pip install \
  -c requirements.lock dist/nhi_blast-0.1.0-py3-none-any.whl
```

On Windows use `\Scripts\python.exe` and quote extras as
`"dist/nhi_blast-0.1.0-py3-none-any.whl[hcl]"` when testing the HCL extra.

Check the installed surface:

```
nhi-blast version
nhi-blast version --data
nhi-blast schema
nhi-blast scan tests/fixtures/fx07-incident --simulate-compromise action:tj-actions/changed-files@v45 --fail-on high
nhi-blast rank tests/fixtures/fx07-incident
nhi-blast export tests/fixtures/fx07-incident --format json
nhi-blast explain <finding-id> --report nhi-blast-out/report.json
```

Run the same checks in a second environment without the `hcl` extra and confirm that
HCL input is skipped with a diagnostic while JSON input still works. Confirm that the
`schema` command works without network access.

## 4. Record artifact digests

Record the SHA-256 of each artifact in a checksum file beside the artifacts. On POSIX:

```
sha256sum dist/*.whl dist/*.tar.gz > dist/SHA256SUMS
```

On Windows PowerShell:

```
Get-FileHash dist\*.whl, dist\*.tar.gz -Algorithm SHA256 |
  ForEach-Object { "$($_.Hash.ToLower())  $($_.Path | Split-Path -Leaf)" } |
  Set-Content dist\SHA256SUMS
```

Keep the digest record next to the artifacts rather than inside a document that the
sdist packages. A digest written into a packaged document changes the sdist on the
next build, so it can never match the digest of the artifact that contains it. The
frozen artifact set and its `dist/SHA256SUMS` file are authoritative; verify with
`sha256sum -c dist/SHA256SUMS` before publication.

Do not describe the build as bit-for-bit reproducible unless at least two clean builds
on the same toolchain are compared and the digests match. The current record compares
three builds. The lock files currently pin versions, not package hashes.

Also install the sdist into a fresh environment and repeat `version` and one scan; the
wheel built from the sdist must behave identically.

## 5. Publish (requires explicit authorization)

Only after the maintainer authorizes publication:

1. Commit the release state and create a signed or annotated tag for the version.
2. Upload the wheel, sdist and digests to the chosen distribution channel.
3. Attach the changelog and the release evidence to the release record.
4. Publish no credentials, scans of customer repositories or private research cache.
5. Verify the published artifacts install in a new environment and match the recorded
   digests.

If any gate fails after artifacts were built, discard the artifacts, fix the cause and
rebuild. Do not ship a build that bypassed a failing test.

## 6. After release

- Update `docs/implementation-status.md` and `docs/production-readiness.md` with the
  published version, date and artifact digests.
- Open follow-up items for known limitations that were accepted for this release.
- Keep the previous release artifacts available for incident response.
- Record any data-file staleness warnings so the next release refreshes primary
  sources.
