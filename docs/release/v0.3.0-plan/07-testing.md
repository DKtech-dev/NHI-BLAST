# 7. Complete testing strategy

**Existing gates stay unchanged:**
- `ruff check`, `ruff format --check`, `mypy src` (strict)
- `pytest`, `-m security`, `-m golden`, `-m slow`
- `scripts/check_coverage.py` (80% overall and per file in `aws`, `analysis`, `report`; extend the per-file list to `diff`, `whatif` and `core/completeness.py`)
- `scripts/gen_schema.py --check`
- `audit.yml`

No assertion is loosened.

### Per-feature tests

| Feature | Positive | Negative | Regression / adversarial |
|---|---|---|---|
| Schema 1.1 | 1.1 validates; schema regenerated | Unknown field rejected (`extra=forbid`) | Golden 1.0 report still loads in explain/diff |
| Completeness | Each family reaches each of the five states via fixtures | `not_provided` is not reported as an error; no "complete" text in HTML | Every emitted `D-`/`A-` code is mapped; JSON, console and HTML agree; hostile path strings stay inert |
| Diff | Self-diff → empty; newly reachable persistent credential → new path + Z entry | Removed input, partial parse, changed selector or truncation → `not_observed`, never `resolved` | Hypothesis: shifting line numbers or file order gives an identical diff; duplicate IDs; missing nodes; malformed or 1.0 inputs; byte-identical diff JSON |
| Baseline | Accepted `lk` suppresses only `new` | Cannot suppress diagnostics, drift or completeness; expired entry stops suppressing | `--update` never adds; file is deterministic |
| What-if | Each of the 4 interventions changes the expected sets (fx16 golden) | Unsupported type → fail-closed record; 1.0 report rejected | Replay self-check; source report bytes unchanged; E stays after `disable_entrypoint`; Z stays until `rotate_credential`; `re_exposure_risk` when a surviving path reads the store |
| Conditions | Oracle vectors (T0) | Malformed operands → UNRESOLVED + diagnostic | Hypothesis: a new operator never turns UNRESOLVED into a definite allow |
| configure-aws-credentials | Declared TTL → DECLARED E TTL; session policy narrows | Expression-valued inputs → unknown, not guessed | `role-chaining: true` → `not_supported` item |
| OIDC IDs | Bound IDs give a definite match | Wrong ID gives no match | Absence keeps `A-REPO-AGE` |
| GH context file | Reviewers present clear `A-ENV-UNPROTECTED` | Missing file → `not_provided` | Malformed, oversized or hostile JSON → partial facts plus diagnostics |
| Action | Synthetic workflow on fixtures produces SARIF and the correct exit code | Fork condition skips SARIF upload | `test_ci_pins.py` covers `action/` and the new workflows (full-SHA pins, minimal permissions) |
| Release workflow | Static checks: job-scoped permissions, trusted publishing, no secrets | — | Wheel/sdist smoke in a clean venv; checksum and SBOM present; `gh attestation verify` instructions run in the release dry run |

### Cross-cutting tests (new)

1. **No subprocess at runtime:** a test that monkeypatches `subprocess.Popen`, `os.system`, `os.exec*` and `os.spawn*` to raise, then scans fx14-hostile and runs diff and whatif. This turns the static claim into a tested one.
2. **No network:** extend the existing socket guard (`tests/test_determinism.py:116`) to diff and whatif.
3. **Output redaction:** the canary secret must be absent from diff JSON/HTML, what-if JSON/MD/HTML and the playbook.
4. **HTML security:** for the diff and what-if HTML, check CSP hashes, the escaped JSON island, no external URLs, and no `innerHTML` sinks (reuse `tests/test_html.py` helpers).
5. **Size budget:** main report ≤ 600 KB on fx07; diff and what-if HTML ≤ 250 KB.
6. **Path containment:** the `--github-context`, `--plan` and `--baseline` files resolve via PathGuard or explicit user path rules, with symlink and junction tests.
7. **Performance:** diff and whatif on fx15 scale within documented budgets (to be measured, then fixed as a regression bound).
8. **UI (section 8):** Playwright plus axe.
9. **Platforms:** CI matrix ubuntu, windows and macOS. macOS runs py3.12 only, and is claimed only once it passes.

### Final validation recording

Each check is recorded in `docs/production-readiness.md` as **passed locally / passed in CI / not run (reason) / failed**, with the command, the exit code and the commit.
