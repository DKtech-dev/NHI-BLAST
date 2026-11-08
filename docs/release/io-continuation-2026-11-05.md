# IO continuation — 2026-11-05

This record resumes the [archived checkpoint](<assurance-session-2026-11-03.md>), not a new audit or a release sign-off. The [scoped plan](<io-continuation-plan-2026-11-05.md>) follows the already approved transformation. Broader authorization/session/custody/diff/release defects remain open.

## Recovery and ownership

- Recovered the original main transcript and explicitly approved blueprint from the supplied session archive. The last successful session stopped on 2026-11-03; subsequent continuation attempts failed before implementation. Existing project changes and saved research were preserved.
- Branch remains `feature/v0.3.0-beta-consolidated`, HEAD `df20cba`; no staging, commit, push, publication or host-policy change. Tool/schema remain `0.3.0b1` / `1.1`; no authorization semantics or report design was changed in this increment.
- Initial implementation was split into disjoint scopes. At the user's request at approximately 18:42 IST, all parallel workers were stopped. Lead personally completed remaining changes, review and verification; no further delegation occurred. The earlier read-only findings are retained, but no independent final review or security audit is claimed.
- No new paid research, dataset acquisition, credentials, cloud resources or runtime dependencies. Eighteen existing runtime pins were obtained from the local pip cache into a verification wheelhouse, then installed offline into a new consumer environment.

## Implemented boundaries

1. [Artifact IO](<../../src/nhi_blast/core/artifact_io.py>) captures actual-open regular-file identities, performs bounded reads including short-read handling, and reports committed outputs versus incomplete rollback/cleanup with retained recovery paths. Error text excludes private payloads and host-path details.
2. [Configuration](<../../src/nhi_blast/core/config.py>) and [Git-origin loading](<../../src/nhi_blast/discovery/repo.py>) preserve transient identities from early reads without adding fields to serialized analysis models. Their existing public APIs and decoding/limit behavior remain.
3. [Discovery and loading](<../../src/nhi_blast/discovery/walker.py>) retain conservative selected-name/pre-open guards plus actual-open fstat identities. Positive and failed JSON sniffs retain their guards before loader reads; ordinary successfully negative JSON sniffs do not prevent legitimate prior-output replacement. Sniffing respects the applicable prefix cap.
4. [Pipeline](<../../src/nhi_blast/pipeline.py>) carries these identities outside report metadata/hashes, including explicit option spellings and old inodes retained across controlled replacement. Scan renders every selected format before shared staged promotion; rank console rendering also precedes promotion; export uses the same protected writer. [Pure SARIF serialization](<../../src/nhi_blast/report/sarif.py>) preserves existing artifact bytes.
5. [Baseline loader/writer](<../../src/nhi_blast/diff/baseline.py>) and [commands](<../../src/nhi_blast/cli/diff_cmd.py>) protect the actual loaded diff source while permitting the deliberate baseline update. Output errors now exit 4 and input/usage errors exit 2, matching the [documented contract](<../diff.md>). A BaselineOutputError subtype preserves direct BaselineError compatibility.
6. [Diff runner](<../../src/nhi_blast/diff/run.py>) and [what-if runner](<../../src/nhi_blast/whatif/run.py>) retain explicit committed/rollback cleanup status instead of claiming no files were written.

No filesystem-wide multi-file atomicity, crash durability/fsync or hostile-directory race-free guarantee is made. Completion manifests, source receipts and the new analysis schema remain the later blueprint contract, not silently invented in this increment.

## Executed checks

| Check | Actual result | Limits |
|---|---|---|
| Fresh preserved-tree baseline | 1796 passed, 17 skipped, 77.42 seconds | Browser wrapper explicitly skipped; executable unset |
| Focused final input/output regressions | 239 passed, 39 skipped, 11.33 seconds | All 39 skips require unavailable file-symlink privilege |
| Ruff lint | Clean over src/tests/scripts | No gate relaxed |
| Ruff format | 195 files already formatted | Final frozen-source check |
| Strict mypy | No issues in 108 source/script files | Canonical source/scripts gate |
| Schema generator check | Exit 0 | No schema version/analysis changes |
| Frozen non-slow coverage gate | 1973 passed, 51 skipped, 2 slow deselected; 90.77% overall; every enforced module >=80%; exit 0 | 200.77 seconds; browser ran separately; executable unset here |
| Wheel/sdist checks | 133 wheel entries, 440 sdist entries; required assets/licences and forbidden-content checks passed | Local uncommitted verification artifacts, not public release assets |
| Repeated wheel/sdist builds | Both SHA-256 values identical across two sequential Hatch builds | Fixed SOURCE_DATE_EPOCH; same local toolchain/source; later session-doc updates are not part of that build snapshot |
| Clean installed wheel | Offline install and pip check passed; package metadata/source both 0.3.0b1 | Windows CPython 3.12.14 |
| Installed/source/wheel parity | 126 package files byte-identical | Does not establish all platforms |
| Installed entrypoint collision checks | Six scan/rank/export checks returned output-error 4 and preserved source hashes | Three commands each on installed wheel CLI and standalone executable |
| Rebuilt Windows executable | Build/checksum/embedded-resource/artifact checks passed | Isolated existing pinned PyInstaller 6.22.3 toolchain; optional hidden tzdata import warning recorded |
| Full standalone executable parity suite | Interrupted after a stale eight-versus-ten data-inventory failure and a CPU-consuming denied-output-directory staging loop | Gate did not pass; 2026-11-07 continuation repairs the actual staging issue and expands the reviewed inventory check |
| Complete Chromium/Firefox/WebKit browser suite | 401 passed, 1 Firefox scroll-progress case failed; 22.9 minutes; exit 1 | The unchanged failed case passed once in isolation (10.2 seconds); root cause remains unresolved, so the complete gate is not labelled passed |
| Full Python/slow/security gate with executable | Pending after browser/timing contention ends | Timing budgets remain unchanged |

## Failed and interim checks

- The first test file had a syntax error and a what-if test initially used an invalid CLI option. Both fixtures were corrected before the intended red behaviors were accepted.
- Genuine reds observed for input aliases, later render/staging/promotion failures, unreadable selected inputs, guard-identification failure classification and cleanup status. Existing valid assertions were not deleted.
- First coverage execution reported 1940 passing tests but failed the per-module gate with diff runner at 70.53%. Its execution overlapped a source import reformat, so it was not accepted as frozen-source evidence. The fresh frozen run passed with diff runner at 93.68%; the original failure remains recorded.
- `python -m build` failed because the installed frontend was absent and the local build directory resolved as a namespace package. Hatch backend help was inspected; comma-separated target syntax was then rejected by this installed CLI. Separate repeated `-t wheel -t sdist` flags built successfully, without installing/replacing build tools or weakening checks.
- Builds produced before the unreadable-source/discovery corrections are retained as interim evidence and are not the tested final source artifact.

## Unavailable environment gates and next steps

1. Local Linux execution unavailable: WSL launcher exists but `wsl --list --quiet` reports WSL is not installed; Docker/Podman not found. Local macOS is unavailable on this Windows host. No OS installation/elevation/security weakening was performed. Current-version native Linux/macOS checks still require a suitable environment or explicitly authorized CI; historical runs are not substitutes.
2. File symlinks require a privilege not held by this process; hardlinks and existing Windows junction/reparse-point tests remain exercised. Do not relabel those symlink cases as passed.
3. Continue from the native denied-output-directory staging failure. The 2026-11-07 work uses bounded mkdir allocation, reviewed inventory expectations, rebuilt artifacts and fresh executable/full-Python/coverage/browser checks. Preserve this historical failed browser/Windows evidence; later passes do not erase it.
4. Next approved engineering phase remains P0-B: boundary ceilings across conditional grants, supported trust Deny and a shared request witness, with sourced normative amendments and independent supported-fragment oracles. Then population/custody/time, dependency-safe comparison, coherent replay, source receipts/completion manifests and release safety. No overall authorization, containment, production-readiness or release-candidate verdict follows from this IO increment.
