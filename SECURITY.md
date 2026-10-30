# Security policy

NHI-Blast analyses hostile repository content. Its own security properties matter as
much as its findings, so defects that break them are treated as security bugs.

## Supported versions

NHI-Blast `0.1.1` is the latest published release; `0.1.0` remains available. Both
were distributed as GitHub Release assets under the MIT License. The source tree on
`main` is version `0.2.0` under a proprietary licence and is not yet released.
Security fixes are made on the current source line; there are no long-term support
branches and no backports. A version is supported only when its source can be
verified against this repository and, for a release, against the published SHA-256
sums.

## Reporting a vulnerability

Report suspected vulnerabilities privately through GitHub's private vulnerability
reporting or security-advisory mechanism for this repository. Do not open a public
issue, and do not include real credential values, production tokens or customer data
in a report.

A useful report contains the affected version or commit, the command or API used, the
input that triggers the problem, the observed behaviour, why it violates a property
below, and a minimised reproducer where possible.

This is a small volunteer project. There is no bug bounty, no formal SLA and no claim
of an independent security audit. Reports are acknowledged and triaged when a
maintainer is available; a fix or advisory is published at the maintainer's
discretion.

## Security properties in scope

The following are hard requirements from `AGENTS.md` and `docs/SPEC.md`. A bypass is
a security defect:

1. **No execution of scanned content.** Never run Terraform, OpenTofu, Git, shell
   commands or actions, never fetch providers or modules, and never evaluate
   `${{ ... }}` expressions.
2. **No network access at analysis time.** Scanning, reporting and the generated HTML
   report must work completely offline and make no outbound requests.
3. **Path containment.** Every read must stay inside the scan root. Symlinks,
   junctions and crafted relative paths must not escape it or expose files outside it.
4. **No secret values in output.** Console, JSON, SARIF, HTML, diagnostics, logs and
   test snapshots must never contain a credential value. Literal-credential findings
   may report only the credential kind and its length.
5. **Inert hostile strings.** Untrusted strings must not execute script, inject
   markup, or escape the embedded JSON data block in the HTML report. The report keeps
   its restrictive content security policy and requires no network access.
6. **Bounded processing of hostile input.** YAML aliases, deep nesting, oversized
   files, malformed JSON/HCL and pathological graphs must produce diagnostics or a
   clean failure, not unbounded memory, recursion or CPU use.
7. **Honest evidence.** UNKNOWN-class edges must never contribute to the R, E or Z
   survival sets. Silently promoting unknown authority to declared authority is a
   correctness and security defect.

## Not vulnerabilities

- A finding that describes a weakness in a scanned repository. The tool reports
  authority and evidence; it does not exploit it.
- An assumption-backed result that is conditional by design. The report lists the
  assumption (`A-*` / `H-*`) and the evidence class that produced the result.
- A platform feature that is not modelled. Those are documented limitations, not
  security defects, unless the specification claims the feature is supported.
- A deliberately conservative false positive in a prefilter. Prefilters may admit
  candidates; they must never drop a possible authority path.

## Handling secrets in a report

If you believe a report contains a credential value, treat the report as sensitive:
do not attach it to a public issue. Record the output format, the field path and the
credential kind, redact the value, and send the redacted reproduction privately.
Rotate anything that may have been exposed before sharing diagnostic material; the
project cannot rotate credentials for you.

## Verifying the security properties

The security-marked tests cover path escape, symlinked inputs, hostile YAML,
oversized inputs, malformed documents, HTML injection, CSP integrity and secret
leakage across every output format:

```
python -m pytest -m security
python -m pytest tests/test_security.py tests/test_report_security.py
```

The HTML report embeds data as an escaped JSON block, builds the DOM without
HTML-string concatenation, inlines the vendored Motion runtime and application code
pinned by SHA-256 in the CSP and `src/nhi_blast/report/assets/MANIFEST.json`, and
loads no code from a CDN.
