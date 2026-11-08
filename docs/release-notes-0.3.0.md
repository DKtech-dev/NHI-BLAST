# NHI-Blast 0.3.0: release notes

**Status: published as the GitHub pre-release `v0.3.0`** — wheel, sdist, SHA-256 sums, a CycloneDX
SBOM and a standalone Windows executable. There is no package-index (PyPI/TestPyPI) publication.
See "State of this release" below.

## What changed for users

1. **Reports record how they were made** (schema `nhi-blast-report/1.1`): analyzer identity, the
   effective configuration and limits, every scenario's start nodes, and digests of the graph
   and of the context. A 1.0 report still loads everywhere; it just has no context.
2. **Completeness is explicit.** Each report lists which families of input were analysed,
   partly analysed, not provided, not supported or not applicable. Not provided and not
   supported mean the report says nothing about that family. There is no score and no
   "complete" badge.
3. **`nhi-blast diff`** compares two saved reports. A finding that disappears is reported as
   resolved only when both reports come from the same analyzer, the same inputs and settings
   apart from file content, a scenario that is still complete, and no degraded input family.
   Otherwise it is "not observed", with the reason. A reviewed baseline suppresses only the exit
   code for new findings. See `docs/diff.md`.
4. **`nhi-blast whatif`** models containment on a saved report without executing anything:
   disable an entrypoint, remove trust, revoke role sessions, rotate a credential. Revocation is
   modelled as an access state ("access denied - credential still valid"), never as deletion or
   expiry, with the cutoff, propagation and scope caveats AWS documents. It aborts when the saved
   report cannot be replayed exactly. See `docs/whatif.md`.
5. **AWS condition evaluation is stricter about what it does not know.** See the changelog for the
   correction and its effect on results.
6. **Session lifetimes carry provenance.** A declared `role-duration-seconds`, an action default
   that is verified for the pinned ref, an assumed default, or a bound from the role maximum.
   A duration above the role maximum, or above one hour under role chaining, fails as declared and
   leaves the session in the potential set.
7. **OIDC subjects can be declared** with `[github] subject_format`, `owner_id` and `repo_id`, and
   for GitHub Enterprise Server (classic subjects only).
8. **The HTML report has light and dark themes** with a System / Light / Dark switcher, an
   Analysis completeness panel, and a notice instead of a bare success when no findings were
   produced from partly analysed inputs.

## Migration

- Read 1.0 reports with 1.1 tools without change. Re-scan with 0.3.0 before using `diff` against
  a 0.2.0 report: a 1.0 report has no analyzer identity, so its findings can never be "resolved".
- Reports produced by 0.2.0 from a repository with a configuration file that binds credentials
  contain the absolute path of that file in evidence and edge ids. Re-scan to get portable ids.
- Baseline files are new in this version.

## Limits you should know

- Session policies are recorded but not evaluated; access may be broader than a session allows.
- Role chaining, SCPs, RCPs, resource policies, KMS key policies, branch protection and environment
  protection settings are not analysed. The report says so per family.
- `diff` and `whatif` have no HTML pages yet.
- Only Windows was exercised locally. Linux and macOS are untested for this version.
- No independent security audit has been performed.

## State of this release

| State | Status |
|---|---|
| Implementation | Partly complete. Not built: diff and what-if HTML, GitHub Action, GitHub context import, session policy evaluation, labelled harness growth to 40 cases, public-corpus benchmark, internal security review |
| Tests and evidence | Complete for what is built (see `docs/production-readiness.md`); the release workflow builds and smoke-tests the wheel on Linux |
| Release candidate | Committed and tagged `v0.3.0`; wheel, sdist, checksums and SBOM built and checked |
| Owner actions pending | Package-index publication is optional and separate: register PyPI/TestPyPI pending publishers and create protected environments only if that channel is later wanted |
| Public release | Published as the GitHub pre-release `v0.3.0` (wheel, sdist, SHA-256 sums, SBOM, Windows executable). No package-index upload |
