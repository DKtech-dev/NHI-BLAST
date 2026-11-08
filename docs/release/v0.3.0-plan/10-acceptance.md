# 10. Final v0.3.0 release acceptance checklist

> **Revised 2026-11-02.** Where this part conflicts with [12-revision-2.md](12-revision-2.md) (final design review: corrections, deviations, verified sources) or [11-ui-direction.md](11-ui-direction.md), those documents win. See the implementation log for what was built.

Each item is marked DONE / PARTIAL / BLOCKED / NOT RUN / N/A, with evidence, in `docs/production-readiness.md`.

**Stage gates:**
- [ ] A: five completeness states represented and schema-validated; JSON, console and HTML agree; UNKNOWN stays outside R/E/Z; hostile strings inert; deterministic.
- [ ] A: ≥40 labelled synthetic cases with rationale; all 16 rules have positive and negative cases; evaluate_labelled gate in CI.
- [ ] A: documentation reconciled (handover list items 1–8 fixed).
- [ ] B: self-diff empty; ordering/line noise ignored; new persistent-credential path detected; resolved only when comparable; malformed, duplicate, missing-node, 1.0 and truncated inputs tested; diff JSON byte-deterministic; baseline cannot hide drift or diagnostics.
- [ ] C: source report unchanged; unsupported interventions fail closed; E persists after `disable_entrypoint`; Z persists until rotation; residual paths shown; fx16 golden passes; no network, subprocess or out-of-tree writes.
- [ ] D: oracle vectors pass; each new semantic has positive, negative, partial and malformed fixtures; imported context is versioned with provenance; deferrals documented.
- [ ] E: wheel and sdist build and pass `check_artifacts.py`; clean installs on ubuntu, windows and macOS (CI); SBOM, checksums and attestation generated in a release dry run; trusted-publishing workflow has no secrets.
- [ ] F: Action installs the exact pinned version, produces valid SARIF, preserves exit codes, behaves safely in the fork case, and every reference is pinned to a full SHA.
- [ ] GUI: completeness panel, graph list fallback, light/dark themes, diff and what-if HTML; Playwright and axe pass on the stated browser/OS matrix; scripted walkthroughs recorded.

**Global gates:**
- [ ] ruff, format, mypy strict, full pytest, security, golden, slow, coverage gate (thresholds not lowered), schema check, audit workflow: all green in CI on the release commit.
- [ ] No-network and no-subprocess runtime tests pass; the redaction canary is absent from every output format.
- [ ] Benchmark artifacts reproducible from the manifest; `docs/benchmark.md` regenerated; limitations stated.
- [ ] Internal review recorded with exact commit and scope (`docs/security-audit.md`). The external audit package is updated. "No independent audit" is stated.
- [ ] Version `0.3.0b1`; CHANGELOG, `docs/release-notes-0.3.0.md`, README quickstart (`pipx`/`uvx`) and migration notes complete.
- [ ] v0.2.0 tag and assets untouched.

**Owner-only steps (not done by the agent):**
- [ ] PyPI and TestPyPI pending trusted publisher registered.
- [ ] `testpypi` and `pypi` environments created with reviewers.
- [ ] Approve the publish.
- [ ] Push tag `v0.3.0-beta.1`.
- [ ] Publish the GitHub release.
- [ ] Optional: Marketplace repo; recruit independent reviewers and usability participants.

**Go/no-go:** "Go" only if every stage gate and global gate is DONE. Otherwise, list the blockers and keep the candidate unpublished.
