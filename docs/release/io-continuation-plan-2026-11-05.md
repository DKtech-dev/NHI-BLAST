# P0-A IO Continuation Implementation Plan

> **For agentic workers:** Continue the already approved transformation task-by-task with disjoint native-team scopes and fresh review. Do not create commits.

**Goal:** Finish the checkpoint's input-preserving scan/rank/export/baseline output integration and make cleanup failures truthful.

**Architecture:** Capture transient identities from actual opened inputs before parsing, including configuration and Git-origin reads and inputs rejected by limits/encoding. Carry these outside serialized models into the existing rollback-capable artifact writer. Render all selected formats before staging; keep current artifact names and report bytes unchanged. Distinguish post-promotion cleanup failure from failed promotion. Completion manifests and source receipts remain the broader blueprint's later versioned package contract; this increment does not invent one or claim all P0-A acceptance complete.

**Tech Stack:** Existing Python 3.12+, Pydantic, pytest, Ruff and strict mypy. No dependencies added.

**Spec:** [normative specification](<../SPEC.md>), [approved checkpoint](<assurance-session-2026-11-03.md>); archived approved blueprint recovered locally under nhi-blast-out/session-recovery-45a26d8a.

## Global Constraints

- Preserve all existing modifications; no reset/clean, staging, commit, push, publication or host-policy changes.
- No secret values in diagnostics or new artifacts.
- Parsers do no cross-file IO; scanned content is never executed.
- Identical inputs produce deterministic artifacts; transient filesystem identities never enter reports or hashes.
- No hostile-directory race-free or filesystem-wide cross-file atomicity claim.
- Never weaken a valid test or gate.

## Review Focus

1. Configuration consumed before its own lowered cap must remain protected.
2. Malformed/oversized/invalid-encoding input files remain protected even without returned facts.
3. Original, resolved and hardlinked identities and post-read path replacement remain protected.
4. A later renderer/staging/promotion failure cannot replace earlier/prior outputs.
5. Cleanup failures must preserve committed-versus-rolled-back state and recovery material.

## Task 1: opened input tracking and cleanup state

**Files:** core/artifact_io.py, core/config.py, discovery/walker.py, discovery/repo.py; dedicated tests/test_input_identity_tracking.py and tests/test_artifact_cleanup.py.

**Interfaces:** InputLoader retains conservative pre-open guards alongside actual-open fstat identities; positive/failed JSON sniffs carry Discovery.protected_inputs (successful ordinary negative sniffs do not). identify_open_input(path: Path, handle: BinaryIO) -> InputIdentity; Config.from_file_with_identity(path: Path) -> tuple[Config, InputIdentity]; resolve_identity_with_inputs(existing keyword arguments) -> tuple[RepoIdentity, tuple[InputIdentity, ...]]; InputLoader.protected_inputs() -> tuple[InputIdentity, ...]. Preserve existing public wrappers. ArtifactCleanupError extends ArtifactOutputError and carries committed_paths and retained staging paths; no new return type for write_artifacts. The 2026-11-07 continuation replaces the Windows tempfile denied-parent retry path with at most 32 genuine name-collision attempts and immediate propagation of permission/other filesystem failures. Existing executable timeouts and rollback expectations remain unchanged.

- [x] Write failing tests for actual-open fstat identity, short/oversized/invalid-encoding reads, configuration early identity, Git-origin identity, post-commit cleanup and cleanup during failed promotion.
- [x] Run new tests and observe the intended red behaviors.
- [x] Implement the interfaces and preserve existing bounded reads, BOM/error behavior, rollback backups and generic secret-safe errors.
- [x] Run focused input/cleanup/security tests, lint and strict source typing.

## Task 2: baseline CLI diff identity

**Files:** diff/baseline.py, cli/diff_cmd.py; tests/test_baseline_io_safety.py.

**Interfaces:** load_diff_with_identity(path: Path) -> tuple[dict[str, Any], InputIdentity]; existing load_diff delegates. Accept/prune pass the loaded diff identity to write_baseline(inputs=...). Existing baseline updates remain allowed, but aliasing the separate diff input is never allowed. BaselineOutputError remains a BaselineError subtype for direct callers, but CLI output failures are exit 4 and invalid input/usage exit 2, matching the documented contract. The earlier plan incorrectly retained the historical exit-2 output behavior; real CLI regressions justified its correction.

- [x] Write real CLI regressions for exact/hardlink/symlink diff aliases and allowed ordinary accept/prune updates, with unchanged input bytes.
- [x] Observe red tests before implementation; implement identity plumbing.
- [x] Run baseline and diff tests plus focused lint/type checks.

## Task 3: pipeline protected staged writers

**Files:** pipeline.py, report/sarif.py; tests/test_pipeline_io_safety.py.

**Interfaces:** ParsedRepository.protected_inputs: tuple[InputIdentity, ...] is transient and excluded from repr/comparison; load_repository combines early config/Git-origin identities and loader identities. _write_scan_artifacts consumes these and uses report_json/html_report/sarif_json pure renderers plus write_artifacts. sarif_json(report: Report) -> str preserves existing bytes. Rank/export use existing pure renderers and the same protected writer; console render occurs before commit.

- [x] Write alias matrices for scan/rank/export against Terraform/IAM/config/Git and invalid/oversized inputs, plus second-render/staging/promotion failures and control successes.
- [x] Run tests before production edits and inspect the expected failures.
- [x] Implement plumbing without report/schema/analysis semantic changes or extra output files.
- [x] Run focused/full tests, security tests, lint, formatting, strict typing and schema consistency.

## Stage verification and handoff

- [x] Lead personally reviewed the final diff and fixed real findings with regressions; independent workers were stopped at the user's request. No independent final audit is claimed.
- [ ] Collect fresh coverage, browser, clean package/installed-wheel and Windows parity evidence where available.
- [x] Record unavailable cross-OS/environment gates concretely without weakening them.
- [ ] Update per-session readiness and precise remaining blueprint steps; no overall-release or authorization-correctness claim.

Baseline: 1796 passed, 17 skipped, 77.42 seconds on this current tree with NHB_SKIP_UI_TESTS=1; browser and executable gates are separate.
