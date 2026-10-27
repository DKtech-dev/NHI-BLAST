# Architecture

NHI-Blast is a single-process, offline pipeline. It reads repository files, converts
them into typed facts, builds one authority graph, runs incident scenarios and
renders deterministic artifacts. No stage executes scanned content or makes a
network call.

## 1. Layers

| Layer | Modules | Responsibility |
| --- | --- | --- |
| Core | `core/models.py`, `core/evidence.py`, `core/diagnostics.py`, `core/ids.py`, `core/limits.py`, `core/config.py`, `core/data.py` | Typed models, evidence ordering, diagnostics, stable identifiers, limits, strict configuration, platform-data loading |
| Discovery | `discovery/walker.py`, `discovery/paths.py`, `discovery/repo.py` | Walk inside a resolved root, classify inputs, reject link escapes, read repository identity without invoking git |
| Parsers | `parsers/yaml_marked.py`, `parsers/gha/*`, `parsers/terraform/*`, `parsers/iam/*` | Pure path-plus-text parsers returning facts and diagnostics. No cross-file I/O, no expression evaluation |
| Resolvers | `resolvers/workflows.py`, `resolvers/composite.py`, `resolvers/permissions.py`, `resolvers/roles.py` | Composite expansion, effective permissions, Terraform/IAM normalization into cloud facts |
| Cloud logic | `aws/glob.py`, `aws/conditions.py`, `aws/trust.py`, `aws/policy_eval.py`, `aws/sinks.py`; `oidc/*` | IAM glob intersection, condition evaluation, trust matching, allow/deny decision procedure, OIDC subject candidates and breadth |
| Graph | `graph/store.py`, `graph/builder.py` | Merge nodes/edges, enforce invariants, apply rules R1–R14 |
| Analysis | `analysis/selectors.py`, `reach.py`, `partition.py`, `rotation.py`, `rank.py`, `findings.py`, `scenario.py` | Start sets, best-evidence reach, R/E/Z partition, closure, rotation order, mutable-action ranking, findings |
| Reports | `report/*` | Console, canonical JSON, SARIF 2.1.0, offline HTML, JSON/DOT export, explanations |
| Orchestration | `pipeline.py`, `cli/app.py`, `cli/commands.py` | Wire stages, merge diagnostics, enforce exit codes, write artifacts |

Import direction is one-way: core → parsers → resolvers → cloud → graph → analysis →
reports. Reports never parse inputs; parsers never import analysis.

## 2. Data flow

```text
root ─ discovery ─┬─ GHA parser ── composite/permission resolvers ─┐
                  ├─ TF JSON/HCL ─ role/sink resolvers ────────────┤
                  └─ IAM JSON ──────────────────────────────────────┤
                                                                   ▼
                                   OIDC subjects + trust solver → graph builder
                                                                   │
                                              scenario selector ───┤
                                                                   ▼
                                    reach → R/E/Z → closure → rotation → findings
                                                                   │
                                               console / JSON / SARIF / HTML / DOT
```

`pipeline.py` merges discovery, parser, resolver, graph and analysis diagnostics
into one report. A diagnostic never suppresses a result silently: partial results
carry the diagnostic, and `--strict` turns error diagnostics into exit code 3.

## 3. Evidence model

Every node and edge has at least one `Evidence` item with a class:

```text
DECLARED > DERIVED > ASSUMED > UNKNOWN
```

The confidence of an edge is the weakest class among its evidence. Trust decisions,
credential classification and read/write decisions all lower confidence when they
depend on an assumption. UNKNOWN authority edges never enter R, E or Z; they feed a
separate `potential` set. This is the main defence against a plausible-looking graph
overstating authority.

## 4. Graph rules

| Rule | Adds |
| --- | --- |
| R1 | REPOSITORY, WORKFLOW and JOB structure |
| R2 | Action use sites and RUNS_IN |
| R3 | GITHUB_TOKEN and OIDC request tokens |
| R4 | Referenced secrets |
| R5 | Literal credentials (kind + length only) |
| R6 | OIDC identity per audience for jobs with writable `id-token` |
| R7 | Cloud provider, roles and sinks |
| R8 | Trust matches, STS sessions and CAN_ASSUME |
| R9 | Read permissions (`CAN_READ_VALUE`) |
| R10 | Stored credentials and STORES |
| R11 | Static AWS keys |
| R12 | Database secrets and configured credential bindings |
| R13 | Modify permissions (`CAN_MODIFY`) |
| R14 | Intended role binding |

The store validates endpoints, merges duplicate nodes and edges, recomputes
confidence from evidence, derives content-based IDs and rejects dangling edges.
Node-budget truncation removes orphaned edges rather than leaving an invalid graph.

## 5. Analysis

Selectors start at an entrypoint: `action:`, `job:`, `role:`, `credential:`,
`repo:`, `repo-write` or `fork-pr`. Reach prefers the strongest weakest-edge class,
then fewer hops, then the lexicographically smallest edge-ID path. The partition
assigns each credential to:

- **R** — revoked with the entrypoint;
- **E** — expires on its own (temporary STS session);
- **Z** — survives (persistent credential).

Closure follows `AUTHENTICATES_AS`, `CAN_READ_VALUE`/`CAN_MODIFY` and `STORES`
within the configured depth. The rotation planner orders survivors so a surviving
credential cannot re-read a freshly rotated one; cycles become SCC batches.
Findings are derived from the graph and scenario, never invented by a reporter.

## 6. Reports

All renderers consume the same validated `Report` model:

- **Console** is a deterministic text rendering; colour is TTY-only and can be
  disabled.
- **JSON** uses canonical ordering and a committed Draft 2020-12 schema.
- **SARIF 2.1.0** carries one run, all catalog rules, stable fingerprints and
  code-flow locations, capped at 5,000 results with a warning.
- **HTML** is one file with data in `<script type="application/json">`, escaped
  `<`, `>`, `&`, U+2028 and U+2029, a restrictive CSP with inline-script hashes, and
  DOM construction through `textContent`/`setAttribute` only. Vendored scripts and the
  embedded Geist fonts are hash-verified against `assets/MANIFEST.json`; a boot gate
  hides the shell until the first hydrated render, with a no-script override.
- **DOT** uses numeric vertex IDs so hostile labels cannot inject syntax.

## 7. Determinism and safety

- No wall-clock value enters an artifact unless `--timestamp` is given.
- Keys and arrays are sorted; identifiers are content-derived SHA-256 prefixes.
- Scan results are byte-identical across output directories and selector order.
- Parsers are pure and never raise on hostile input; they return facts plus
  diagnostics.
- Discovery resolves every path and refuses anything outside the scan root,
  including escaping symlinks and Windows directory junctions.
- The runtime has no network code and the test suite replaces socket entry points
  with failures.

## 8. Extending the tool

1. Put platform facts in `src/nhi_blast/data/*.yaml` with source and verification
   date.
2. Keep parsers path-plus-text pure and total on hostile shapes.
3. Add evidence at the point a fact is created, not in a reporter.
4. Add a behavioural test at the narrowest layer, then a fixture/integration test.
5. Update `docs/requirements-traceability.md` and the rule/assumption docs.
6. Do not widen scope beyond specification 2.3.
