# NHI-Blast 0.1.0

Initial public release, distributed as GitHub Release assets only. NHI-Blast is a
local-first, offline Python 3.12+ command-line tool that reads GitHub Actions
workflows, local composite actions, Terraform JSON/state and IAM policy documents and
answers three incident-response questions from static evidence:

1. From a hypothetical compromised entrypoint, which AWS roles, credential stores and
   credentials are potentially reachable?
2. If the entrypoint is revoked, which credentials end with the job (R), which expire
   on their own (E), and which survive (Z)?
3. In what order should surviving credentials be rotated so a surviving credential
   cannot re-read a freshly rotated one?

Findings describe potential authority and conditional survival. They do not prove that
a compromise occurred, that a credential was obtained, or that a role can be taken
over.

## Install

Download the wheel or sdist and `SHA256SUMS` from this release and verify the checksum.
The sdist contains `requirements.lock`; use it to pin runtime dependencies:

```sh
sha256sum -c SHA256SUMS
python -m venv .venv
.venv/bin/python -m pip install -c requirements.lock nhi_blast-0.1.0-py3-none-any.whl
```

If you install from the wheel alone, take `requirements.lock` from the sdist or the
repository and pass it with `-c`; the wheel does not embed the lock file.

On Windows use `.\.venv\Scripts\python.exe` and `Get-FileHash`. The optional extras are
`rich` for the enhanced console renderer and `hcl` for best-effort Terraform HCL
parsing; JSON plan/state input does not require the HCL extra.

## What is included

- `scan`, `rank`, `explain`, `export`, `schema` and `version` commands with documented
  exit codes 0–4.
- Offline discovery and parsing of workflows, composite actions, Terraform plan/state
  JSON, Terraform JSON configuration and IAM policy documents.
- Evidence classes `DECLARED > DERIVED > ASSUMED > UNKNOWN`, weakest-class edge
  confidence, and a separate potential set for UNKNOWN authority.
- Deterministic JSON (`nhi-blast-report/1.0`), SARIF 2.1.0 and a single-file offline
  HTML report with an exposure matrix, shortest-path trace, scenario-aware summary,
  filters and accessibility support.
- Rotation planning with containment steps, generation ordering, strongly connected
  component batches and verification steps.
- Exact dependency locks, an allowlisted artifact checker, three-build digest
  reproducibility and a security-marked adversarial test suite.

The full feature list and fixes are in `CHANGELOG.md`. Rule documentation is under
`docs/rules/`; assumptions and known limitations are in `docs/assumptions.md` and
`docs/known-limitations.md`.

## Verification performed for this release

- GitHub Actions CI passed on Ubuntu and Windows for Python 3.12, 3.13 and 3.14, plus a
  package job. The run is linked from `docs/production-readiness.md`.
- The advisory workflow audits both lock files with pip-audit, runs Bandit, OSV-Scanner
  and gitleaks, and runs weekly on a schedule.
- The internal audit in `docs/security-audit.md` records zizmor, actionlint, Semgrep,
  Bandit, pip-audit, OSV-Scanner, Grype, pip-licenses, gitleaks and TruffleHog results,
  dependency-age checks, and the fixes made during the audit.
- Runtime and development locks were audited with no known advisories on the audit
  date; licenses are permissive or weak copyleft only.
- The wheel and sdist are byte-identical across three consecutive builds from the same
  toolchain, and their SHA-256 digests are published in `SHA256SUMS`.

## Limits of this release

- **No independent audit.** The project has not been reviewed by an external human
  auditor and no independent audit is claimed. `docs/external-audit-package.md` lists
  what such a review would receive.
- Static analysis only. The tool does not read live cloud or GitHub state, and a
  finding is not proof of exploitability.
- GitHub secret scanning and CodeQL are unavailable on this private repository without
  GitHub Advanced Security; compensating scans are recorded in the internal audit.
- One symlink security test is skipped on the maintainer's Windows environment because
  creating symlinks requires a privilege; the Linux CI job executes it. Windows
  directory junctions are always covered.
- Cross-machine and cross-toolchain byte reproducibility is not claimed.

## License

MIT. See `LICENSE` and `NOTICE`. Vendored report assets retain their upstream
licenses, recorded in `NOTICE` and `src/nhi_blast/report/assets/MANIFEST.json`.
