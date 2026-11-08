# Report diff and reviewed baseline

`nhi-blast diff BASE.json HEAD.json` compares two saved reports offline and writes
`nhi-blast-diff/1.0`. It reads only the two report files (and an optional baseline); it makes no network
call, runs no subprocess and never reads the clock. It is a review aid: it says what the two analyses
observed, never that a problem is fixed or absent.

```
nhi-blast diff BASE.json HEAD.json [--baseline F] [--fail-on critical|high|medium|low|never]
               [--format console|json]... [--out DIR] [--as-of YYYY-MM-DD]
nhi-blast baseline accept LK --diff DIFF.json --reason TEXT --reviewer NAME [--expires YYYY-MM-DD] --baseline F
nhi-blast baseline prune --diff DIFF.json --baseline F
```

`--fail-on` defaults to `never`, as in `scan`. `json` (and any further registered format) is written to
`OUT/diff.<ext>`; `console` is printed. Additional formats register through
`nhi_blast.diff.render.register_renderer`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | No new findings at or above the threshold after baseline suppression |
| 1 | New findings at or above the threshold that are not baselined |
| 2 | Usage or input error (unreadable, oversized, malformed or unsupported report, baseline or diff file) |
| 3 | Incomparable reports |
| 4 | Internal or output error |

A report that cannot be loaded is a usage/input error (2); `INCOMPARABLE` (3) is reserved for reports that
loaded but cannot be compared.

## Logical finding key

`lk = sha256(canonical JSON of [rule, scenario selector, sorted path node ids, primary evidence file])`,
where the scenario component is empty for every rule except the scenario-bound ones
(`SCENARIO_RULES` in `analysis/findings.py`: `NHB-SURV-001`, `NHB-ROT-001`, `NHB-ROT-002`). Only those findings
belong to one scenario's R/E/Z partition. For every other rule (trust audit, workflow rules) the `scenario` field
records which scenario happened to reach the finding first; when a change moves that attribution (for example a
pinned action stops one scenario from reaching a role) the finding is still present, and a scenario in the key
would report it as resolved plus new. Such a move alone is `unchanged`; the `scenario` shown in the output and in a
baseline entry is informational for these rules. Node ids are semantic and only the evidence *file* (not its line) is hashed, so moving a statement
within a file does not change the key. Findings with the same key are paired deterministically: equal
evidence digest (evidence without line numbers) first, then in order of line. Surplus findings in a group whose two
sides differ in size stay unpaired and are flagged `ambiguous_match`. Findings are never paired across
rule or scenario. The graph is compared by node id and by `(kind, src, dst)`; edge ids are not used. Line
numbers (keys named `line`, `*_line`, and `file.ext:LINE` suffixes in strings) are ignored when comparing
evidence, node attributes and edge attributes.

## Comparability

* **incomparable**: schema major version differs, `repo_slug` differs, or the scenario selector sets are
  disjoint. The output has no finding classification.
* **comparable_with_drift**: anything differs in analyzer identity (`analyzer_changed`, `rules_changed`,
  `data_changed`), analysis parameters (`context_changed`: config digest, limits, max depth, strict,
  selectors, OIDC settings, default branch, account, region, bindings, sub template, ignore lists), the schema version or a
  missing context (`schema_changed`), or a completeness status or its diagnostics/assumptions
  (`completeness_changed`). Each drift entry carries the two values; values that could originate in
  scanned files are shown as digests only.
* **comparable**: none of the above.

Completeness drift ignores the per-source content hashes: editing an input file changes them in every
diff and is the expected change, not drift.

## Finding classes and the "resolved" rule

`new`, `changed` (same key, different severity, confidence, evidence, path order or assumptions),
`unchanged` (a pure line shift is unchanged), `resolved` and `not_observed`.

A finding present in BASE and not paired in HEAD is **resolved** only when all of these hold; otherwise it is
**not_observed** with the failing reason codes. The wording is "no longer observed under comparable analysis".

1. Analyzer identity is byte-equal (tool version, engine semantics, rules digest, data digests).
2. Analysis parameters are equal and both reports have a context (so only input files differ).
3. For a scenario-bound rule, HEAD has the same scenario selector.
4. For a scenario-bound rule, that HEAD scenario is not truncated, did not exhaust its time budget and has no
   unresolved inputs BASE lacked. For every other rule the same holds at report level: no scenario that both reports
   have may be truncated, out of budget or have gained unresolved inputs in HEAD.
5. No completeness family the rule depends on (`diff/families.py`, every rule is mapped, and the analysis-budget family
   always applies) has a worse status in HEAD (`not_applicable`=`analysed` < `partially_analysed` < `not_provided`=`not_supported`).
6. Every evidence file of the BASE finding still exists in HEAD's inputs at the same path.
7. No rename candidate: no unpaired HEAD finding of the same rule and scenario has the same path
   signature (file paths stripped), and no evidence file's content hash appears in HEAD at a different path.

| Reason | Meaning |
|---|---|
| `analyzer_changed` | tool version or engine semantics differ |
| `rules_changed` | rules digest differs (a tampered digest with an identical version is caught here) |
| `data_changed` | a data file digest differs |
| `schema_changed` | schema versions differ or a report has no context (schema 1.0) |
| `context_changed` | analysis parameters differ |
| `scenario_missing` | HEAD lacks the finding's scenario |
| `scenario_incomplete` | HEAD scenario truncated, out of time budget, or has new unresolved inputs |
| `dependency_degraded` | a family the rule depends on lost information (or completeness is missing) |
| `evidence_file_missing` | an evidence file is gone from HEAD's inputs |
| `possible_rename` | rename candidate by path signature or content hash |
| `ambiguous_match` | surplus in a same-key group, or an unpaired HEAD finding of the same rule/scenario shares the terminal path node |

A rename or re-routing makes the BASE finding `not_observed` and the HEAD finding `new` with
`possible_rename_of`; such findings still count for `--fail-on` unless baselined.

## Other sections

Per scenario: R/E/Z membership in and out, E `ttl_seconds` changes, Z survival-window, lifetime, criticality and
depth changes, potential and unresolved-input changes, and rotation-dependency changes (keyed by phase and credential).
Also: graph nodes/edges added, removed and changed (field names only), finding path deltas, diagnostic
code deltas (level, code and file only), completeness status changes.

## Baseline

`nhi-blast-baseline/1.0`: `created_from_report_digest` and entries `{lk, rule, scenario, reason, reviewer, expires?}`,
sorted by key, no timestamps, written only by `baseline accept` or `prune`. An entry suppresses a *new*
finding in the exit-code decision only; the finding, drift, completeness and diagnostics stay in every output. An entry
whose `expires` is on or before `--as-of` stops suppressing and produces `D-DIFF-BASELINE-EXPIRED`; without
`--as-of` no expiry is checked. An entry whose rule does not match its key produces `D-DIFF-BASELINE-MISMATCH` and does not
suppress. `accept` only adds a key that is `new` in the given diff and refuses duplicates; `prune` removes only entries
whose finding is `resolved` in the given diff.

## Re-scan rather than translate

There is no compatibility registry. If the tool version changed, re-scan BASE with the HEAD tool version.
