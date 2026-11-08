# 3. Research and competitor findings (accessed 2026-10-31)

> **Revised 2026-11-02.** Where this part conflicts with [12-revision-2.md](12-revision-2.md) (final design review: corrections, deviations, verified sources) or [11-ui-direction.md](11-ui-direction.md), those documents win. See the implementation log for what was built.

### 3.1 Official semantics (oracles)

| ID | Source | Claim used |
|---|---|---|
| A1 | AWS, Policy evaluation logic — https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html | Explicit deny in identity policy, SCP or RCP overrides allow. Boundaries intersect; identity and resource policies union. |
| A2 | AWS, Revoke role temporary credentials — https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html | `AWSRevokeOlderSessions` denies sessions with `aws:TokenIssueTime` older than now (+~30 s). Stopping a workflow does not revoke issued sessions. |
| A3 | AWS STS AssumeRole API — https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html | Session duration 1–12 h, default 3600 s. Role chaining is capped at 1 h. Session policies intersect. |
| A4 | AWS condition operators — https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_condition_operators.html | Missing key → false (negated → true), except `IfExists` (true) and `Null`. |
| A4b | AWS multivalued keys — https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-single-vs-multi-valued-context-keys.html | `ForAllValues` is true when the key is absent. `ForAnyValue` is false when the key is absent. |
| A5 | AWS Access Analyzer custom checks — https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-custom-policy-checks.html | Checks are charged per call and need AWS credentials. Not usable as a free oracle, so it is not run. |
| A6 | GitHub OIDC reference — https://docs.github.com/en/actions/reference/security/oidc ; changelog 2026-04-23 — https://github.blog/changelog/2026-04-23-immutable-subject-claims-for-github-actions-oidc-tokens/ | Repositories created after 2026-07-15 use immutable `repo:owner@OWNERID/repo@REPOID:...`. Older ones opt in. |
| A7 | GitHub Secure use — https://docs.github.com/en/actions/reference/security/secure-use | Pin actions to a full SHA. Warns about `pull_request_target`. Least-privilege `GITHUB_TOKEN`. |
| A8 | GitHub reusable workflows — https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows ; environments — https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments | `secrets: inherit` works within the same org/enterprise. Environment secrets are withheld until reviewers approve. |
| A9 | Terraform JSON format — https://developer.hashicorp.com/terraform/internals/json-format | `after_unknown` mirrors `after`, with unknown leaves set to `true`. `sensitive_values` and `module_calls` are documented. |
| A10 | aws-actions/configure-aws-credentials `action.yml` (to verify at the pinned tag in Stage D) | Inputs `role-duration-seconds`, `inline-session-policy`, `managed-session-policies`, `role-chaining`. |

### 3.2 Competitors and adjacent tools (versions as observed)

| Tool | Licence / version | Overlap with NHI-Blast | Relationship |
|---|---|---|---|
| zizmor (https://github.com/zizmorcore/zizmor) | MIT, v1.31.1 (2026-10-15) | Unpinned uses, excessive permissions, `secrets: inherit` | Complementary, with partial overlap on workflow hygiene. No cloud or credential survival. |
| actionlint (https://github.com/rhysd/actionlint) | MIT, v1.7.12 | Workflow correctness | Complementary |
| poutine (https://github.com/boostsecurityio/poutine) | Apache-2.0, v1.1.6 | CI misconfiguration / injection | Complementary |
| Gato-X (https://github.com/AdnaneKhan/gato-x) | Apache-2.0, v1.4.0 | Live GitHub enumeration and attack | Different (online, offensive) |
| OpenSSF Scorecard (https://github.com/ossf/scorecard) | Apache-2.0, v5.6.0 | Pinning and token-permission heuristics | Complementary |
| harden-runner (https://github.com/step-security/harden-runner) | Apache-2.0, v2.22.3 | Runtime egress | Complementary (runtime) |
| PMapper (https://github.com/nccgroup/PMapper) | AGPL-3.0, last commit 2022-02 | IAM privilege-escalation graph (live) | Adjacent; unmaintained |
| Cartography (https://github.com/cartography-cncf/cartography) | Apache-2.0, 0.144.0 | Live asset graph | Different (live, Neo4j) |
| Cloudsplaining / Parliament | BSD, 0.9.1 / 1.6.4 | IAM policy lint and least privilege | Complementary |
| Checkov / Trivy / Prowler | Apache-2.0; 3.4.0 / v0.76.1 / 5.47.0 | IaC checks, including GitHub OIDC trust-breadth checks (check IDs to verify at the pinned version) | Partial overlap on trust breadth |
| Semgrep | LGPL-2.1, 1.183.0 | Pattern rules | Adjacent |

**Finding:** no surveyed open-source tool documents offline workflow→OIDC→role→credential reachability combined with survival classification (R/E/Z) and rotation ordering. This is a statement about the tools surveyed, not a "first" or "unique" claim.

### 3.3 Standards and taxonomies

- OWASP Top 10 CI/CD Security Risks — https://owasp.org/www-project-top-10-ci-cd-security-risks/ — CICD-SEC-2, -4, -6.
- OWASP NHI Top 10 2025 — https://owasp.org/www-project-non-human-identities-top-10/2025/top-10-2025/ — NHI5 overprivileged, NHI7 long-lived secrets.
- MITRE ATT&CK T1552, T1078.004, T1528 — https://attack.mitre.org/techniques/T1552/ (and others).
- SLSA build levels — https://slsa.dev/spec/v1.1/levels (page marked retired; cite the current version at implementation time).
- NIST SP 800-204D (Feb 2024) — https://csrc.nist.gov/pubs/sp/800/204/d/final.

**Use:** rule documentation maps each rule to these IDs. Taxonomy mapping, not certification.

### 3.4 Benchmarks and datasets

| Dataset | Licence | Ground truth | Fit |
|---|---|---|---|
| BishopFox IAMVulnerable (https://github.com/BishopFox/iam-vulnerable) | MIT | 31 labelled IAM privesc paths (Terraform) | Partial: role-chaining/privesc oracle for v0.4 |
| Quacky (https://github.com/vlab-cs-ucsb/quacky) | BSD-style | Policy permissiveness sets | Partial: policy semantics only |
| CloudGoat / cicd-goat / TerraGoat | BSD-3 / Apache-2.0 | Flags or none | Weak: scenario walkthroughs, not labels |
| USENIX Sec'22 GitHub CI workflows; ARGUS (Sec'23) | Licence not verified | Paper findings | Context only |
| GHALogs (Zenodo 10154920) | CC-BY-SA-4.0 | Run logs, no security labels | Not a fit |

**Conclusion:** no official benchmark exists for CI-to-cloud identity reachability or credential survival. NHI-Blast will publish its own clearly named *NHI-Blast Open Evaluation Corpus* (see section 6).

### 3.5 Distribution and provenance

- PyPI Trusted Publishers — https://docs.pypi.org/trusted-publishers/ — OIDC, no long-lived token.
- PEP 740 / PyPI attestations — https://peps.python.org/pep-0740/ , https://docs.pypi.org/attestations/.
- pypa/gh-action-pypi-publish v1.14.x — https://github.com/pypa/gh-action-pypi-publish — `attestations: true` by default with Trusted Publishing.
- GitHub artifact attestations — https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations — `actions/attest` v4, `gh attestation verify`, needs `id-token: write`.
- CycloneDX Python (`cyclonedx-py`) 7.6.0 — https://github.com/CycloneDX/cyclonedx-python.
- On 2026-10-31 `https://pypi.org/pypi/nhi-blast/json` returned 404. That shows only that no public project was visible then. Whether the name is available is **unverified**: a pending publisher does not reserve a name (https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/), and the name is secured only by a successful first publish.

**Not verified this session:** Zelkova paper text, the AWS session/cross-account subpage text, the USENIX dataset licences, Checkov/Prowler exact check IDs. Each is to be verified before being cited in docs.
