# Beta testing NHI-Blast 0.2.0

NHI-Blast 0.2.0 is a public beta. The purpose of the beta is to find reproducible
defects in the offline analysis, the reports and the Windows executable before a stable
release. It is not a production security control, and its output is not a substitute
for an independent cloud security assessment.

## What you can test

- The Windows x64 executable from the `v0.2.0` GitHub pre-release, once that pre-release
  is published, or an installation from the source tree with
  `python -m pip install ".[hcl]"`.
- The reference fixtures under `tests/fixtures/`, especially `fx07-incident`, and the
  documented commands in the README.
- Your own repositories only when you own them or have explicit written authorisation
  to assess them. Do not scan third-party systems or data you do not control.

Use a disposable copy of any repository you scan. Remove or replace real account IDs,
role ARNs, repository names and bucket names before sharing a reproduction if they are
sensitive in your environment.

## What to report

Report reproducible defects through the repository's
[beta bug report form](https://github.com/DKtech-dev/nhi-blast/issues/new?template=beta-bug-report.yml).
Useful reports include:

- Operating system and version, including whether it is Windows x64, Linux or macOS.
- How you installed NHI-Blast and the output of `nhi-blast version` or
  `nhi-blast-windows-x64.exe version` (tool, schema and data-file versions).
- The exact command, including selectors, formats and options.
- The expected result and the actual result.
- A minimised, synthetic or sanitised input and the relevant diagnostics.
- The exit code, and the output format where the problem appears (console, JSON,
  SARIF, HTML, graph, rotation plan or findings).
- Whether the problem reproduces with a reference fixture and with repeated runs.

If the problem involves a suspected vulnerability in NHI-Blast itself, do not open a
public issue. Follow the private reporting process in `SECURITY.md`.

## Never include

- Credential values, secret strings, private keys, tokens, passwords or connection
  strings.
- Contents of private repositories, customer data, production configuration or live
  cloud state.
- Screenshots or logs that contain any of the above. Redact first; when in doubt,
  describe the shape of the value instead of pasting it.

NHI-Blast is designed not to print credential values. If you believe an output contains
one, treat the file as sensitive, do not attach it publicly, and report it privately as
described in `SECURITY.md`.

## What the beta does not promise

- No SLA, response time or fix commitment. The project is maintained on a best-effort
  basis.
- No independent security audit of NHI-Blast has been performed or is claimed.
- Findings describe potential authority and conditional survival from static input.
  They do not prove compromise, credential access or role takeover. Validate results
  against your own environment before acting.
- The Windows executable is unsigned. Windows may show a reputation-based SmartScreen
  warning; no code-signing certificate is used.
- Supported runtimes are Python 3.12, 3.13 and 3.14 on Windows and Linux, plus the
  Windows x64 standalone executable. Other platforms are untested.

## Reporting security issues in a scanned repository

A finding about your own repository is not a vulnerability in NHI-Blast. If you believe
a finding is wrong, report the false positive or missed authority path with the fixture,
the evidence class shown in the report and the expected behaviour. Do not send the
underlying credentials or live cloud data.
