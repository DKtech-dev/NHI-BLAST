# Verification and audit follow-up — 2026-11-03

This is a local working-tree record, not a production approval, independent security audit, publication, or accuracy guarantee. No scanned repository content was executed. No model was trained: these corpus snapshots have no independently adjudicated accuracy labels, so training on scanner output would create circular evidence.

## Corrections established in this pass

- Motion Off now gates application animations, cancels in-progress inspection animations, and restores visible final styles synchronously. With no explicit user override, a live OS reduced-motion change updates the report without creating a persisted override.
- Persistent credential timeline rows retain their actual survival windows. Periodically rotating credentials are bounded, not labelled “No expiry.” Job-bound credentials are described as ending with the job or token expiry, not immediate invalidation when an action is removed.
- An unverified action ref no longer borrows a one-hour default from a different action version. Its duration upper bound is the known role maximum, or the STS 43,200-second cap; established chaining alone adds a one-hour limit.
- An issuance-time upper bound does not establish a live session or absence of denial. What-if reports “access denied - expiry not established” when denial can be inferred but validity cannot. Expiration requires the assessment time to exceed the latest possible issue time plus a known lifetime upper bound.
- Two runtime assertions in diff identity checking were replaced by explicit missing-context drift handling. The guard remains effective under optimized Python.

The session-bound semantic changes incremented `ENGINE_SEMANTICS` to `3`; a subsequent request-context correction increments it to `4`, preserving prior fingerprints. Namespaced AWS/service request keys are no longer classified as absent or dead using the normalized OIDC-provider-claim allowlist. Missing offline request values stay Unknown, while explicitly supplied Present/Absent states retain their AWS condition behavior. Eleven failing cases were observed before the fix; the twelve-case regression and existing condition/trust tests then passed. See [AWS global condition context keys](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html), verified in this pass. JSON and Markdown golden changes were reviewed by exact field before editing.

## Actual completed checks

| Check | Observed result | Limits |
|---|---|---|
| Ruff / format / strict mypy | Clean before final documentation edits | Local Windows only |
| Focused session / what-if tests | 111 passed | Includes concrete issuance-time witnesses straddling cutoff and expiry |
| Diff tests plus explicit runtime-context guard | 69 passed | Does not establish all possible cross-version compatibility |
| Optimized Python guard script | 3 missing-context cases passed | No pytest assertion optimizations were disabled globally |
| Corpus harness regressions | 55 passed, 1 symlink-privilege skip | The skip is environmental |
| Bandit 1.9.4, project configuration | Initial two B101 findings; rerun returned exit 0 after explicit guards | Automated static check; existing B105 configuration unchanged |
| pip-audit 2.10.1 | No known vulnerabilities for all 18 pinned runtime packages | Known-advisory check, not proof that dependencies are safe |
| npm audit | Zero reported vulnerabilities for browser-test dependency tree | Dev-time tooling, not a runtime network dependency |
| Fresh wheel + sdist artifact checks | Passed; wheel 509,096 bytes, sdist 1,247,178 bytes | Local uncommitted artifacts, not published release assets |
| Fresh isolated wheel install / pip check | Passed; 123 package files byte-matched both wheel and source | Interpreter/platform specific |
| New actual-report browser tests | 29 passed per engine: Chromium, Firefox, WebKit | Full-page automated axe checks are not WCAG conformance certification |
| Fresh screenshot capture | 375 / 768 / 1440, both themes, no page overflow, errors, or external requests observed | Static reduced-motion captures; not a human usability study |

A broad Python run under concurrent browser workload had 1 timing failure, 1,580 passes and 11 skips: the 5-second graph/scenario budget took 5.66 seconds. The budget was not relaxed. The same two performance tests passed in isolation (2.67 seconds for the graph/scenario test call, 6.04 seconds for the rank test call).

The final fast-suite/coverage run passed: **1,580 passed, 12 skipped, 2 slow tests deselected; coverage 90.57%**, with every enforced module at or above 80%. The browser-wrapper skip was explicit (`NHB_SKIP_UI_TESTS=1`) because the actual browser suite ran separately; it was not treated as browser evidence.

The first combined browser run had 400 passes and two Chromium failures: preference restoration after reload and a 45-second full-page axe timeout. Both exact cases passed unchanged in isolation. Twelve raw-storage probes and twelve repetitions of the persistence test also passed. The original preference failure has not been reproduced or attributed to a known root cause. One-worker scheduling is now the documented default for software-WebGL checks; assertions, test counts and deadlines were not relaxed. The final complete serial suite **passed all 402 cases** (134 per engine across Chromium, Firefox and WebKit; 25.0 minutes), including the original two Chromium cases. This does not erase the earlier intermittent preference failure or establish its root cause.

## Public-repository evaluation — reproducibility, not labelled accuracy

Reused the already acquired, pinned corpus rather than download unverified data. All 3,620 regular files passed manifest checks before scanning. The current isolated wheel scanned all 15 datasets twice: 14 external repositories and one historical self-control. Every JSON, SARIF and HTML artifact was byte-identical across repeats, schema-checked and cross-checked; input integrity after the run was PASS.

External-only totals per first repeat: 56 findings, 591 graph nodes, 779 edges, 269 diagnostics; loaded input categories 81 workflows, 84 local-action files, 344 HCL files, 34 Terraform JSON files and 2 explicit IAM documents. “Loaded” does not mean fully parsed or supported. Maximum external scan duration was 5.73 seconds, observed with other checks running; two repeats are not a latency distribution.

Manifest SHA-256: `aa806de287ab35796e37e1538bb48b5cbe980d0e82878a2509d9aa6d3e000ec0`. Initial engine-3 source-tree digest: `6986980df145fe6e3df238b1ff58c2ef426a035591a4b7be0de9940a031795bd`. Final engine-4 source-tree digest: `d68c784c2b0c082a2cba54535db6d68f3f91d8129db7a22990e833740f4b2dd2`. External evidence root: `C:/Users/DK/AppData/Local/Temp/nhb-current-verification-20261103`; full harness output is `corpus-results/summary.json`, with exact commands, exits, revisions, license metadata and artifact hashes. A condensed result is [corpus-summary-2026-11-03.json](<corpus-summary-2026-11-03.json>). Raw third-party source stays outside this repository and is not redistributed.

The self-control is excluded from external totals and preserves historical license metadata. License strings above are retained manifest metadata, not a new legal opinion.

The final engine-4 isolated consumer repeated the same full corpus run and also returned PASS for all 15 datasets with identical JSON/SARIF/HTML repeats and preserved input integrity. Its condensed results replace the current portable summary; the engine-3 raw results remain retained. Final external totals remained 56 findings, 591 nodes, 779 edges and 269 diagnostics. The maximum final external scan was 3.04 seconds; it remains a two-repeat observation, not a representative performance distribution. Exact per-repository durations are in that summary.

### Dataset and scientific limitations

- Independent ground-truth labels for this public corpus: **0**. Therefore precision, recall, F1 and accuracy confidence intervals are **not estimated**. Finding counts are not labels or confirmed exploits.
- The existing 14-case synthetic labelled harness remains separate. It covers selected rule behaviors and cannot support broad real-world accuracy claims.
- Repositories are selected, point-in-time snapshots, not a representative random sample. Many are tool repositories or module examples. Remote callees and live organization/resource policies are outside offline scope.
- Findings inside one repository are correlated. Any future labelled study must report actual labelled positive/negative units, single-labeller limitations and repository-cluster confidence intervals instead of treating every finding as an independent sample.

## Final-build follow-up

The first engine-4 source distribution was rejected because root-unanchored include patterns pulled unrelated `plugins/goal-studio` README/docs files into the archive. Include patterns now anchor to the project root; plugin files were preserved and the artifact checker was not weakened. The corrected build passed: 130 wheel entries, 417 sdist entries; a separate engine-4 consumer installed successfully and its 123 package files match both the wheel and final source.

Final wheel SHA-256: `6e672715d613ae1ac7d4fa578883ca6f8a3554da7db7915c3d052bcadbbbb9ba` (509,285 bytes). Corrected sdist SHA-256: `7e88d7e22f12ccf0092da9aa06f1170ae4c006793fe347f97e5235fa6baef77c` (1,255,010 bytes). Earlier engine-3 artifacts/results remain retained separately rather than silently overwritten.

After the request-context correction, the final fast-suite/coverage run passed: **1,592 tests, 12 skips, two slow tests deselected, 90.57% overall coverage**, with all enforced modules at or above 80%. The browser-wrapper skip is explicit because the separate complete 402-case browser suite was actually executed. Both unchanged timing budgets passed separately. Root-anchored archive expectations passed in the 31-case artifact/Windows-packaging suite; the final source archive is rebuilt after these expectation updates so that its tests match its build configuration. Final artifact hashes are retained in the external evidence directory, not recursively embedded as a claim about the archive containing this record.

The offline HTML preview is [report.html](<../../nhi-blast-out/design-preview-final/report.html>); a brief recorded motion preview is [interaction-demo.webm](<../../nhi-blast-out/design-preview-final/interaction-demo.webm>). Screenshots are [light](<../usability/screens/current/report-light-1440-top.png>) and [dark](<../usability/screens/current/report-dark-1440-top.png>), with mobile/table views alongside them. All screenshots/demo use the built-in synthetic incident fixture, not a customer report or confirmed compromise.

## Still open

Linux/macOS and additional Python-version execution, independent security review, the original full public-label study, managed session-policy evaluation, full environment-protection context, release publication and owner-only actions remain open. The condition-prefilter necessary-pattern contract and rare set-operator combinations still deserve additional primary-source investigation; this pass does not claim formal equivalence to all AWS authorization behavior.

No claim is made that this project is unique, best in the world, production-certified, or a guarantee of employment. Professional value comes from reproducible evidence, clear limits and usable behavior.
