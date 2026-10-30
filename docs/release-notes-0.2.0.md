# NHI-Blast v0.2.0 — public beta

This is a **pre-release** of NHI-Blast 0.2.0, a public beta of the offline blast-radius
analyser for non-human identity in CI. It is provided for testing and evaluation. It is
not a production security control, and its analysis is not a substitute for an
independent cloud security assessment. No independent audit has been performed.

## Highlights

- **Standalone Windows x64 executable.** `nhi-blast-windows-x64.exe` is a one-file
  console application that bundles Python 3.12, the optional Terraform HCL parser, the
  console extras and every report asset. It needs no Python, pip, administrator rights or
  source checkout, makes no network requests and requires no cloud credentials.
- **Redesigned offline HTML report.** The report uses the Vermilion Noir visual system,
  a deterministic layered SVG authority graph, an R/E/Z survival rail, a rotation plan,
  accessible graph navigation and a print/PDF layout. The report remains a single
  self-contained file with a restrictive content security policy and no external
  requests.
- **MIT License.** The 0.2.0 source tree and this release are licensed under the MIT
  License. Versions 0.1.0 and 0.1.1 remain under the MIT License they were published
  with. `THIRD_PARTY_NOTICES.md` records the Python runtime and every bundled package
  with the full upstream licence texts.

## Install

### Windows standalone executable

1. Download `nhi-blast-windows-x64.exe` and
   `nhi-blast-windows-x64.exe.sha256` from this release.
2. Verify the download in PowerShell before running it:

   ```powershell
   $record = (Get-Content .\nhi-blast-windows-x64.exe.sha256 -Raw).Trim()
   $actual = (Get-FileHash .\nhi-blast-windows-x64.exe -Algorithm SHA256).Hash.ToLower()
   if ($record -ne "$actual  nhi-blast-windows-x64.exe") { throw "checksum mismatch" }
   ```

3. Run `nhi-blast-windows-x64.exe --help`, then
   `nhi-blast-windows-x64.exe scan . --format html --out nhi-blast-out`.

The executable is unsigned. Windows may show a reputation-based SmartScreen warning; no
code-signing certificate is used and no SmartScreen reputation is claimed.

### Python source

Requires Python 3.12, 3.13 or 3.14.

```
python -m venv .venv
.venv/bin/python -m pip install ".[hcl]"
```

On Windows use `.venv\Scripts\python.exe`. `[hcl]` adds the optional Terraform HCL
fallback. Installation from an index is required once; scans run offline.

## Supported platforms

- Windows 11 x64 with the standalone executable.
- Python 3.12, 3.13 and 3.14 on Windows and Linux, from source.
- GitHub Actions `ubuntu-latest` and `windows-latest` runners in CI.

Other platforms and architectures are untested. The executable is built for Windows x64
only. No package-index publication is made; this is a GitHub pre-release.

## Limitations and security warnings

- The tool reads GitHub Actions workflows, Terraform plan/state JSON with an HCL
  fallback, and IAM policy JSON. It does not execute scanned content, fetch anything or
  evaluate expressions.
- Not modelled: SCPs, permission boundaries, KMS key policies, environment protection,
  branch rules and live AWS state. See `docs/known-limitations.md` in the source tree.
- Findings describe potential authority and conditional revocation survival. They do not
  prove compromise, credential access or role takeover.
- Credential values are never stored, printed, logged or embedded. If you believe an
  output contains a credential value, treat it as sensitive and report it privately as
  described in `SECURITY.md`.
- The beta has no SLA and no fix commitment. Back up your work and validate results
  before acting.

## Beta testing

Use synthetic fixtures such as `tests/fixtures/fx07-incident`, or repositories you own or
are explicitly authorised to assess. Do not send credentials, secrets, private repository
contents or live cloud data. Report reproducible problems through the beta bug report
issue form with the operating system, version, command, expected result, actual result
and sanitised logs. The full process is in `docs/beta-testing.md`.

## Licence

MIT License. See `LICENSE`, `NOTICE` and `THIRD_PARTY_NOTICES.md`, which are attached to
this release and embedded in the executable.
