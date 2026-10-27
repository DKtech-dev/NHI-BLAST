# AGENTS.md — operating rules for agents working on NHI-Blast

This file is the engineering contract for any agent or human contributor. Read
`docs/SPEC.md` first; it is the normative requirements source. Where this file and
the specification disagree, the specification wins.

## 1. What the product is

NHI-Blast is a local-first, offline Python 3.12+ CLI that reads repository files
(GitHub Actions workflows, local composite actions, Terraform plan/state JSON, HCL
fallback, IAM policy JSON) and answers three incident-response questions:

1. From a hypothetical compromised entrypoint, which AWS roles, credential stores and
   credentials are potentially reachable?
2. If the entrypoint is revoked, which credentials end with the job (R), which expire
   on their own (E), and which survive (Z)?
3. In what order should surviving credentials be rotated so a surviving credential
   cannot re-read a freshly rotated one?

Outputs: console, deterministic JSON, SARIF 2.1.0, single-file offline HTML.

## 2. Hard rules (never violate)

1. **Evidence honesty.** Every node and edge carries at least one `Evidence` whose
   class is one of `DECLARED > DERIVED > ASSUMED > UNKNOWN`. Edge confidence is the
   weakest class among its evidence. UNKNOWN-class edges never contribute to R, E or Z;
   they feed the separate `potential` set.
2. **Claim hygiene.** Never state that something "proves", "guarantees", "is exploitable"
   or "is taken over". Use "potentially reachable", "accepted by the trust policy as
   written", "survives revocation if the path was exercised". Severity is a label for
   ordering, not a verdict.
3. **No secret values.** Never store, print, log, embed or test-snapshot a credential
   value. Literal credentials found in files are reported as kind plus length only.
   A credential identified is not a credential proven obtained.
4. **No execution of scanned content.** Never run terraform/tofu/git/shell, never fetch
   providers or modules, never evaluate `${{ ... }}` expressions. Runtime must make no
   network calls.
5. **Safe parsing.** yaml.compose + SafeLoader, marks for line numbers, duplicate-key
   detection, YAML 1.1 `on`/`True` normalisation, only the first document, configured
   limits on size/node count/depth/aliases. Parsers never raise on hostile input; they
   return partial facts plus diagnostics.
6. **Path safety.** Resolve every path and require it to stay inside the scan root;
   never follow symlinks that escape it; never read outside it.
7. **Determinism.** Equal inputs produce byte-identical artifacts. No wall-clock time
   in artifacts unless `--timestamp` is given. Sorted keys/arrays; identifiers per
   spec 5.5; no set-iteration order leaks into output.
8. **Report security.** The HTML report embeds data in
   `<script type="application/json">` with `<`, `>`, `&` escaped as Unicode escapes,
   builds DOM with `textContent`/`setAttribute` only, ships a restrictive CSP with inline
   script hashes, and makes no network requests. Hostile strings must render inert.
9. **No fabrication.** Do not invent sources, benchmarks, compatibility claims, test
   results, certifications, audits or release artifacts. Anything the specification
   marks VERIFY stays ASSUMED and is listed in report assumptions.
10. **Never weaken a valid test or gate** to get a green build. Fix the cause; add a
    regression test. Never delete requirements to make progress look better.

## 3. Code standard

- Python 3.12+, full type annotations, `ruff` clean, `mypy --strict` clean.
- Clear module boundaries: discovery → pure parsers (path+text only) → typed facts →
  resolvers → graph builder → analysis → reporters. Parsers do no cross-file I/O.
- No duplicated business rules: platform facts live in `src/nhi_blast/data/*.yaml`
  with `source_url` and `verified_on`; evaluation logic lives in one module.
- Comments only where they explain contracts, non-obvious platform semantics, security
  boundaries, invariants or deliberate workarounds. No narration, banners, TODOs that
  will not be done, or claims that work is complete.
- Deterministic, side-effect-free functions where possible; diagnostics at boundaries;
  no catch-all exception suppression.
- Tests prove behaviour: focused unit tests, integration tests through the real CLI,
  property-based tests for the glob/condition/identifier logic, adversarial security
  tests for every output boundary, golden files reviewed against the spec (never
  generated and trusted blindly).

## 4. Workflow

1. Work milestone by milestone (see `docs/implementation-status.md`); do not start the
   next milestone until the current milestone's acceptance tests pass.
2. Write the failing test first where practical; implement the smallest coherent change;
   run the full relevant test suite, ruff, mypy, and the security tests.
3. Diagnose root causes; do not delete tests or silently relabel failures.
4. Update `docs/requirements-traceability.md` and `docs/implementation-status.md` with
   the actual result of each check.
5. If a gate genuinely cannot pass in this environment, record the blocker, its impact
   and the exact next action in `docs/implementation-status.md`. Never report a release
   candidate falsely.

## 5. Security boundaries of the tool itself

Treat the scanned repository as hostile. The test suite must include: hostile YAML
(duplicate keys, billion laughs, deep nesting), oversized inputs, path traversal and
symlink escape, malformed JSON/Terraform, HTML injection through every string field,
and secret-leakage checks across console/JSON/SARIF/HTML output.

## 6. Prohibited

- Expanding scope beyond specification section 2.3 (no GCP/Azure/Kubernetes/MCP/GitLab,
  no live API collection, no database-backed web app, no SaaS).
- Publishing, deploying, uploading, or destructive actions without explicit authorization.
- Artificial commits, rewritten history, or claiming an independent security audit.
