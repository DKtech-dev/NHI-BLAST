# Release procedure

This document describes how a release is prepared and checked. The latest stable
published release is `0.1.1`, distributed as GitHub Release assets (wheel, sdist and
SHA-256 sums) under the MIT License; `0.1.0` remains available. There is no
package-index upload or deployment. Version `0.2.0` is a public beta under the MIT
License, prepared as a GitHub pre-release that adds the standalone Windows executable.
The gate record for `0.1.1` and its run URLs are in `docs/production-readiness.md`; the
0.2.0 beta has its own results recorded there and in the release notes. No independent
human audit has been performed.

## Preconditions

1. The working tree is clean and reviewed. Do not build a release from a dirty tree.
2. `CHANGELOG.md` describes the release and the version in `pyproject.toml` matches.
3. The licence state is confirmed before the build: `0.1.0`, `0.1.1` and `0.2.0` are
   MIT releases. Do not relicense published artifacts or publish a source version under
   the wrong terms. `THIRD_PARTY_NOTICES.md` must match the frozen executable contents.
4. `requirements.lock` and `requirements-dev.lock` are regenerated and audited.
5. The primary-source dates in the data files are current enough for the release; see
   `docs/data-provenance.md`.
6. Every gate in `docs/production-readiness.md` has a recorded command and result.
7. Explicit authorization to tag or publish has been given. The maintainer authorized
   GitHub Releases with wheel, sdist and SHA-256 sums for `v0.1.0` and, separately, for
   the `v0.1.1` report patch, and authorized the `v0.2.0` public-beta pre-release with
   the Windows executable and checksum. That authorization does not extend to package
   indexes, deployments or later versions.

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

All commands must succeed. A skipped test must be explained in the release record; a
skipped test is not a pass.

## 2. Build the distributions

```
rm -rf dist
python -m hatchling build -t wheel -d dist
python -m hatchling build -t sdist -d dist
python scripts/check_artifacts.py dist
```

The artifact checker requires exactly one wheel and one sdist. It verifies that the
wheel contains all eight platform data files, the three embedded fonts and both font
licence files, the Motion runtime and its MIT licence, and `MANIFEST.json`; that wheel
metadata reports `License-Expression: MIT` and declares `LICENSE`, `NOTICE` and
`THIRD_PARTY_NOTICES.md`; that those files are present in both artifacts; that the
notices name every package frozen into the Windows executable; that runtime metadata
excludes test tooling; and that neither artifact contains caches, the private research
cache, scratch files or the local output directory.

## 3. Verify installation in a clean environment

Create a fresh virtual environment per platform and install from the built wheel.
Install the runtime lock alongside it so dependency versions are exact:

```
python -m venv /tmp/nhi-blast-consumer
/tmp/nhi-blast-consumer/bin/python -m pip install --upgrade pip
/tmp/nhi-blast-consumer/bin/python -m pip install \
  -c requirements.lock dist/nhi_blast-<version>-py3-none-any.whl
```

Substitute the version from `pyproject.toml`. On Windows use `\Scripts\python.exe` and
quote extras as `"dist/nhi_blast-<version>-py3-none-any.whl[hcl]"` when testing the HCL
extra.

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

## 5. Build and verify the Windows executable pre-release

The Windows executable is built by the manual `build-windows` workflow on the default
branch. It does not sign, tag or publish anything; it uploads a build artifact.

1. Dispatch `build-windows.yml` on `main` and wait for the job to succeed.
2. Download the `nhi-blast-windows-x64` artifact. It contains the executable, its
   `.sha256` record, `LICENSE`, `NOTICE` and `THIRD_PARTY_NOTICES.md`.
3. Verify the checksum independently of the build output with `Get-FileHash` or
   `sha256sum`, comparing against the downloaded `.sha256` record.
4. Copy the executable to a clean Windows environment outside the repository, with no
   Python, pip or project virtual environment on `PATH`, and run `--help`, `version` and
   a scan of a synthetic fixture. Confirm the exit codes and outputs match the source
   build.
5. Run `scripts/check_artifacts.py` with `--windows-exe` against the downloaded file to
   confirm the archive resources, embedded notices and secret scan.
6. Create the GitHub pre-release `v0.2.0` only if every step above succeeded. Attach the
   executable, its `.sha256`, `LICENSE`, `NOTICE` and `THIRD_PARTY_NOTICES.md`. Mark it
   as a pre-release and state that it is unsigned, that no code-signing certificate is
   used and that no independent audit has been performed.

If the workflow, checksum, clean-environment run or artifact check fails, do not create
the release. Fix the cause and rebuild.

## 6. Publish (requires explicit authorization)

Only after the maintainer authorizes publication:

1. Commit the release state and create a signed or annotated tag for the version.
2. Upload the wheel, sdist and digests to the chosen distribution channel.
3. Attach the changelog and the release evidence to the release record.
4. Publish no credentials, scans of customer repositories or private research cache.
5. Verify the published artifacts install in a new environment and match the recorded
   digests.

If any gate fails after artifacts were built, discard the artifacts, fix the cause and
rebuild. Do not ship a build that bypassed a failing test.

## 7. After release

- Update `docs/production-readiness.md` and the release notes with the published
  version, date, tag commit and release URL. Keep digests in the release's
  `SHA256SUMS` asset, not inside documents packaged in the sdist.
- Open follow-up items for known limitations that were accepted for this release.
- Keep the previous release artifacts available for incident response.
- Record any data-file staleness warnings so the next release refreshes primary
  sources.
