# Install

NHI-Blast 0.3.0 is distributed as the GitHub pre-release
[`v0.3.0`](https://github.com/DKtech-dev/nhi-blast/releases/tag/v0.3.0): a wheel, an sdist,
SHA-256 sums, a CycloneDX SBOM and a standalone Windows executable. There is **no PyPI or
TestPyPI publication** for this version; commands that name a package index will not find it.
Whether the distribution name `nhi-blast` is available on PyPI is **unverified**: a `404` from
`https://pypi.org/pypi/nhi-blast/json` on 2026-10-31 only showed that no public project was
visible then, and a pending publisher does not reserve a name. The name is secured only by a
successful first publish.

## From the GitHub release assets

Download `nhi_blast-0.3.0-py3-none-any.whl` (and `requirements.lock` from the repository at tag
`v0.3.0`) from the release page, then:

```sh
python -m pip install -c requirements.lock "nhi_blast-0.3.0-py3-none-any.whl[hcl]"
nhi-blast version
```

The `[hcl]` extra adds the optional Terraform HCL fallback; without it, HCL input is skipped
with a diagnostic and JSON input still works. Verify what you download as described in
[verify-release.md](verify-release.md).

On Windows, the standalone `nhi-blast-windows-x64.exe` needs no Python installation; it is
unsigned and embeds its licence notices.

## From a local build

```sh
python -m pip install -c requirements-dev.lock hatchling
python -m hatchling build -t wheel -t sdist -d dist
python scripts/check_artifacts.py dist
python -m pip install -c requirements.lock "dist/nhi_blast-0.3.0-py3-none-any.whl[hcl]"
nhi-blast version
```

## If a package index is published later

Index publication is a separate owner decision. Only after it happens would commands like
`pipx install "nhi-blast==0.3.0"` or `python -m pip install "nhi-blast==0.3.0"` work. A beta
version is installed from an index only when you ask for it by exact version (PEP 440
pre-release).

The tool runs offline and makes no network calls at run time.