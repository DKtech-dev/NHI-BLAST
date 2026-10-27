# Security policy

NHI-Blast analyses hostile repository content. Its own security properties matter as
much as its findings, so defects that break them are treated as security bugs.

## Supported versions

NHI-Blast is a pre-release project. No version has been published to a package index.
Security fixes are made on the current `0.1.x` line only; there are no long-term
support branches and no backports. A version is supported only when its source can be
verified against this repository.

## Reporting a vulnerability

Report suspected vulnerabilities privately. Use the private security-advisory
mechanism of the hosting forge where this repository is published. If no such
mechanism is available, contact the maintainer through the same private channel by
which you obtained the source. Do not open a public issue, and do not include real
credential values, production tokens or customer data in a report.

A useful report contains: the affected version or commit, the command or API used,
the input that triggers the problem, the observed behaviour, and why it violates a
property below. Attach a minimised reproducer where possible.

This is a volunteer pre-release project. There is no bug bounty, no formal SLA and no
claim of an independent security audit. Reports are acknowledged and triaged when a
maintainer is available; a fix or advisory is published at the maintainer's
discretion.

## Security properties in scope

The following are hard requirements from `AGENTS.md` and `docs/SPEC.md`. A bypass is
a security defect:

1. **No execution of scanned content.** The tool must never run Terraform, OpenTofu,
   Git, shell commands or actions, never fetch providers or modules, and never
   evaluate `${{ ... }}` expressions.
2. **No network access at analysis time.** Scanning, reporting and the generated HTML
   report must work completely offline and must make no outbound requests.
3. **Path containment.** Every read must stay inside the scan root. Symlinks,
   junctions and crafted relative paths must not escape it or expose files outside it.
4. **No secret values in output.** Console, JSON, SARIF, HTML, diagnostics, logs and
   test snapshots must never contain a credential value. Literal-credential findings
   may report only the credential kind and its length.
5. **Inert hostile strings.** Untrusted strings from scanned files must not execute
   script, inject markup, or escape the embedded JSON data block in the HTML report.
   The report must keep its restrictive content security policy and must not require
   network access.
6. **Bounded processing of hostile input.** YAML aliases, deep nesting, oversized
   files, malformed JSON/HCL and pathological graphs must produce diagnostics or a
   clean failure, not unbounded memory, recursion or CPU use.
7. **Honest evidence.** UNKNOWN-class edges must never contribute to the R, E or Z
   survival sets. A defect that silently promotes unknown authority to declared
   authority is a correctness and security defect.

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
credential kind, redact the value, and send the redacted reproduction privately. The
project cannot rotate credentials for you; rotate anything that may have been exposed
before sharing diagnostic material.

## Verifying the guarantees

The repository's test suite contains security-marked tests for path escape,
symlinked inputs, hostile YAML, oversized inputs, malformed documents, HTML
injection, CSP integrity and secret leakage across every output format. Run:

```
python -m pytest -m security
python -m pytest tests/test_security.py tests/test_html_security.py
```

The HTML report embeds data as an escaped JSON block and builds the DOM without
HTML-string concatenation. It inlines its JavaScript libraries, recorded by hash in
`src/nhi_blast/report/assets/MANIFEST.json`; it does not load code from a CDN.
