"""Apply an interventions plan to a copy of the saved graph and re-run the analysis.

Containment steps change which paths exist for future runs. Credentials that a run may
already have obtained are not affected by them: sessions stay issued until their TTL and
persistent credentials stay in Z until rotated. The result therefore separates the
carried state (`after`) from what new runs could still reach (`future_reach`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from nhi_blast.analysis.scenario import ScenarioAnalysis, analyze_scenario
from nhi_blast.core.canonical import digest_of
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import (
    AUTHORITY_EDGE_KINDS,
    PERSISTENT_LIFETIMES,
    Edge,
    EdgeKind,
    GraphData,
    Lifetime,
    Node,
    NodeKind,
    Partition,
    Report,
    ScenarioContext,
    ScenarioReport,
)
from nhi_blast.report.redaction import redact_payload
from nhi_blast.whatif import HEADER, WHATIF_SCHEMA
from nhi_blast.whatif.guard import (
    CONTEXT_MISSING,
    GuardFailure,
    config_from_context,
    guard_failures,
    limits_from_context,
    pristine_graph,
)
from nhi_blast.whatif.plan import (
    DisableEntrypoint,
    Plan,
    PlanEntry,
    Rejection,
    RemoveTrust,
    RevokeRoleSessions,
    RotateCredential,
)
from nhi_blast.whatif.sessions import (
    REVOKE_CAVEATS,
    assess_session,
    format_timestamp,
    resolve_cutoff,
)

ANALYSIS_TIME = "D-WHATIF-ANALYSIS-TIME"
_CONTAINMENT_TYPES = frozenset({"disable_entrypoint", "remove_trust", "revoke_role_sessions"})
_TRUST_EDGES = frozenset({EdgeKind.CAN_ASSUME, EdgeKind.AUTHENTICATES_AS})
_ENTRYPOINT_KINDS = frozenset({NodeKind.JOB, NodeKind.WORKFLOW})
_ALL_KINDS = frozenset(NodeKind)
_RESIDUAL_UNKNOWN = (
    "derived credentials (chained role sessions, access keys created by the session, "
    "secrets already read) are not affected by the deny; role chaining is not modelled"
)
_BASE_CAVEATS: tuple[tuple[str, str], ...] = (
    (
        "C-OFFLINE-MODEL",
        "Offline model of the saved report. Nothing was executed and no AWS account, "
        "repository or secret store was read or changed.",
    ),
    (
        "C-ISSUED-STATE",
        "Containment steps change paths for future runs only. Sessions already issued "
        "stay issued until their TTL; persistent credentials stay in Z until rotated.",
    ),
    (
        "C-UNKNOWN-EDGES",
        "UNKNOWN-class edges never contribute to R, E or Z; they are reported only as potential.",
    ),
)


class WhatIfAbort(Exception):  # noqa: N818 - boundary signal carrying a diagnostic code
    """The what-if cannot run; the CLI prints one code and exits 2 without writing."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class _State:
    removed_edges: frozenset[str] = frozenset()
    disabled_jobs: frozenset[str] = frozenset()
    blocked_roles: frozenset[str] = frozenset()

    def key(self) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        return (
            tuple(sorted(self.removed_edges)),
            tuple(sorted(self.disabled_jobs)),
            tuple(sorted(self.blocked_roles)),
        )


@dataclass(slots=True)
class _Outcome:
    status: str
    effects: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    rejection: Rejection | None = None
    state: _State = field(default_factory=_State)
    role: str | None = None
    credential: str | None = None


class _Index:
    """Lookups over the saved graph (which includes scenario-added nodes and edges)."""

    def __init__(self, report: Report) -> None:
        self.nodes: dict[str, Node] = {node.id: node for node in report.graph.nodes}
        self.edges: dict[str, Edge] = {edge.id: edge for edge in report.graph.edges}
        self.base = pristine_graph(report.graph)
        self.base_edge_ids = {edge.id for edge in self.base.edges}

    def resolve(self, ref: str, kinds: frozenset[NodeKind]) -> Node | Rejection:
        node = self.nodes.get(ref)
        if node is not None and node.kind in kinds:
            return node
        found = sorted(
            candidate.id
            for candidate in self.nodes.values()
            if candidate.kind in kinds
            and ref in {candidate.label, candidate.attrs.get("arn"), candidate.attrs.get("address")}
        )
        if len(found) == 1:
            return self.nodes[found[0]]
        if not found:
            return Rejection("unresolved_reference", ref)
        return Rejection("ambiguous_reference", ref)


def _working_graph(index: _Index, state: _State) -> GraphData:
    nodes = tuple(
        node.model_copy(update={"attrs": {**node.attrs, "repo_write_accepted": False}})
        if node.id in state.blocked_roles
        else node
        for node in index.base.nodes
    )
    edges = tuple(edge for edge in index.base.edges if edge.id not in state.removed_edges)
    return GraphData(nodes=nodes, edges=edges)


def _apply_disable(
    index: _Index, state: _State, step: DisableEntrypoint, starts: set[str]
) -> _Outcome:
    found = index.resolve(step.node, _ENTRYPOINT_KINDS)
    if isinstance(found, Rejection):
        return _Outcome("rejected", rejection=found, state=state)
    if found.kind is NodeKind.WORKFLOW:
        jobs = {
            edge.dst
            for edge in index.edges.values()
            if edge.kind is EdgeKind.CONTAINS
            and edge.src == found.id
            and index.nodes[edge.dst].kind is NodeKind.JOB
        }
    else:
        jobs = {found.id}
    removed = sorted(
        edge.id
        for edge in index.base.edges
        if edge.src in jobs
        and edge.kind in AUTHORITY_EDGE_KINDS
        and edge.id not in state.removed_edges
    )
    new_jobs = jobs - state.disabled_jobs
    changed = bool(removed) or bool(new_jobs & starts)
    updated = replace(
        state,
        removed_edges=state.removed_edges | set(removed),
        disabled_jobs=state.disabled_jobs | jobs,
    )
    return _Outcome(
        "applied" if changed else "no_effect",
        effects={"disabled_jobs": sorted(jobs), "removed_edges": removed},
        state=updated,
    )


def _apply_remove_trust(index: _Index, state: _State, step: RemoveTrust) -> _Outcome:
    role = index.resolve(step.role, frozenset({NodeKind.AWS_ROLE}))
    if isinstance(role, Rejection):
        return _Outcome("rejected", rejection=role, state=state)
    trust = [
        edge
        for edge in sorted(index.edges.values(), key=Edge.sort_key)
        if edge.kind in _TRUST_EDGES and edge.dst == role.id
    ]
    if step.edge is not None:
        matched = [edge for edge in trust if edge.id == step.edge]
    else:
        principal = index.resolve(str(step.principal), _ALL_KINDS)
        if isinstance(principal, Rejection):
            return _Outcome("rejected", rejection=principal, state=state)
        matched = [edge for edge in trust if edge.src == principal.id]
    if not matched:
        return _Outcome(
            "rejected", rejection=Rejection("no_matching_trust_edge", step.role), state=state
        )
    removed: set[str] = set()
    clears = False
    for edge in matched:
        if edge.attrs.get("repo_write") is True:
            clears = True
        elif edge.id in index.base_edge_ids:
            removed.add(edge.id)
            if (
                edge.kind is EdgeKind.CAN_ASSUME
                and index.nodes[edge.src].kind is NodeKind.OIDC_IDENTITY
            ):
                clears = True
    new_removed = removed - state.removed_edges
    new_block = clears and role.id not in state.blocked_roles
    updated = replace(
        state,
        removed_edges=state.removed_edges | removed,
        blocked_roles=state.blocked_roles | ({role.id} if clears else set()),
    )
    notes = (
        ["repo-write acceptance of this role is cleared for every principal (role-level model)"]
        if clears
        else []
    )
    return _Outcome(
        "applied" if new_removed or new_block else "no_effect",
        effects={
            "removed_edges": sorted(new_removed),
            "matched_edges": sorted(edge.id for edge in matched),
            "repo_write_acceptance_cleared": clears,
        },
        notes=notes,
        state=updated,
        role=role.id,
    )


def _apply_revoke(
    index: _Index, state: _State, step: RevokeRoleSessions, report: Report
) -> _Outcome:
    role = index.resolve(step.role, frozenset({NodeKind.AWS_ROLE}))
    if isinstance(role, Rejection):
        return _Outcome("rejected", rejection=role, state=state)
    cutoff, source = resolve_cutoff(step.revoked_at, step.cutoff)
    in_scope = sorted(
        {
            item.credential
            for scenario in report.scenarios
            for item in scenario.partition.E
            if index.nodes[item.credential].attrs.get("role") == role.id
        }
    )
    return _Outcome(
        "applied" if in_scope else "no_effect",
        effects={
            "role": role.id,
            "cutoff": None if cutoff is None else format_timestamp(cutoff),
            "cutoff_source": source,
            "sessions_in_scope": in_scope,
        },
        state=state,
        role=role.id,
    )


def _apply_rotate(index: _Index, state: _State, step: RotateCredential, report: Report) -> _Outcome:
    node = index.resolve(step.credential, frozenset({NodeKind.CREDENTIAL}))
    if isinstance(node, Rejection):
        return _Outcome("rejected", rejection=node, state=state)
    lifetime = str(node.attrs.get("lifetime", Lifetime.NA.value))
    if Lifetime(lifetime) not in PERSISTENT_LIFETIMES:
        return _Outcome(
            "rejected", rejection=Rejection("not_persistent_credential", node.id), state=state
        )
    surviving = any(
        item.credential == node.id for scenario in report.scenarios for item in scenario.partition.Z
    )
    return _Outcome(
        "applied" if surviving else "no_effect",
        effects={"credential": node.id},
        notes=[] if surviving else ["credential is not in the surviving set of any scenario"],
        state=state,
        credential=node.id,
    )


class _Run:
    def __init__(self, report: Report, plan: Plan) -> None:
        context = report.context
        if context is None:
            msg = "guard must run before the engine"
            raise AssertionError(msg)
        self.report = report
        self.plan = plan
        self.context = context
        self.limits: Limits = limits_from_context(context)
        self.config = config_from_context(context)
        self.index = _Index(report)
        saved = {item.selector: item for item in report.scenarios}
        self.scenarios: list[tuple[ScenarioContext, ScenarioReport]] = [
            (item, saved[item.selector]) for item in context.scenarios
        ]
        self.starts = {node for item, _ in self.scenarios for node in item.start_nodes}
        self._cache: dict[Any, dict[str, ScenarioAnalysis]] = {}

    def analyses(self, state: _State) -> dict[str, ScenarioAnalysis]:
        key = state.key()
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        graph = _working_graph(self.index, state)
        result: dict[str, ScenarioAnalysis] = {}
        for item, _ in self.scenarios:
            starts = tuple(node for node in item.start_nodes if node not in state.disabled_jobs)
            analysis = analyze_scenario(
                graph,
                starts,
                selector=item.selector,
                selector_kind=item.selector_kind,
                max_depth=self.context.max_depth,
                limits=self.limits,
                config=self.config,
                strict=self.context.strict,
            )
            if analysis.time_budget_exhausted:
                msg = f"re-analysis of {item.selector} exhausted the time budget"
                raise WhatIfAbort(ANALYSIS_TIME, msg)
            result[item.selector] = analysis
        self._cache[key] = result
        return result


def _credential_ids(partition: Partition) -> set[str]:
    return {item.credential for item in partition.E} | {item.credential for item in partition.Z}


def _path_record(analysis: ScenarioAnalysis, credential: str) -> dict[str, Any]:
    path = analysis.reach.get(credential)
    return {
        "credential": credential,
        "path_edges": [] if path is None else list(path.ids),
        "weakest": None if path is None else path.weakest.value,
    }


def _step_args(entry: PlanEntry) -> dict[str, Any]:
    item = entry.intervention
    if isinstance(item, DisableEntrypoint):
        return {"node": item.node}
    if isinstance(item, RemoveTrust):
        return {"role": item.role, "principal": item.principal, "edge": item.edge}
    if isinstance(item, RotateCredential):
        return {"credential": item.credential}
    if isinstance(item, RevokeRoleSessions):
        return {
            "role": item.role,
            "revoked_at": None if item.revoked_at is None else format_timestamp(item.revoked_at),
            "cutoff": None if item.cutoff is None else format_timestamp(item.cutoff),
            "assessed_at": (
                None if item.assessed_at is None else format_timestamp(item.assessed_at)
            ),
            "issued_no_later_than": {
                key: format_timestamp(value) for key, value in item.issued_no_later_than
            },
            "issued_no_later_than_all": (
                None if item.issued_default is None else format_timestamp(item.issued_default)
            ),
        }
    return {}


def _counts(analyses: Mapping[str, ScenarioAnalysis]) -> list[dict[str, Any]]:
    return [
        {
            "selector": selector,
            "R": len(analysis.partition.R),
            "E": len(analysis.partition.E),
            "Z": len(analysis.partition.Z),
            "potential": len(analysis.potential_edges),
        }
        for selector, analysis in sorted(analyses.items())
    ]


def _apply_step(run: _Run, state: _State, entry: PlanEntry) -> _Outcome:
    item = entry.intervention
    if isinstance(item, DisableEntrypoint):
        return _apply_disable(run.index, state, item, run.starts)
    if isinstance(item, RemoveTrust):
        return _apply_remove_trust(run.index, state, item)
    if isinstance(item, RevokeRoleSessions):
        return _apply_revoke(run.index, state, item, run.report)
    if isinstance(item, RotateCredential):
        return _apply_rotate(run.index, state, item, run.report)
    return _Outcome("rejected", rejection=entry.rejection, state=state)


@dataclass(slots=True)
class _Executed:
    entry: PlanEntry
    outcome: _Outcome
    state_after: _State


def _execute(run: _Run) -> list[_Executed]:
    state = _State()
    executed: list[_Executed] = []
    for entry in run.plan.entries:
        if entry.intervention is None:
            outcome = _Outcome("rejected", rejection=entry.rejection, state=state)
        else:
            outcome = _apply_step(run, state, entry)
        state = outcome.state
        executed.append(_Executed(entry, outcome, state))
    return executed


def _step_records(run: _Run, executed: list[_Executed]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in executed:
        outcome = item.outcome
        record: dict[str, Any] = {
            "index": item.entry.index,
            "type": item.entry.type,
            "status": outcome.status,
            "args": _step_args(item.entry),
            "effects": outcome.effects,
            "notes": sorted(outcome.notes),
        }
        if outcome.rejection is not None:
            record["reason"] = outcome.rejection.reason
            if outcome.rejection.detail is not None:
                record["detail"] = outcome.rejection.detail
        else:
            record["future_reach_counts"] = _counts(run.analyses(item.state_after))
        records.append(record)
    return records


def _rejected(executed: list[_Executed]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in executed:
        rejection = item.outcome.rejection
        if rejection is None:
            continue
        row: dict[str, Any] = {
            "index": item.entry.index,
            "type": item.entry.type,
            "reason": rejection.reason,
        }
        if rejection.detail is not None:
            row["detail"] = rejection.detail
        rows.append(row)
    return rows


def _revoked_access(
    run: _Run,
    executed: list[_Executed],
    scenario: ScenarioReport,
) -> list[dict[str, Any]]:
    trust_roles = {
        item.outcome.role
        for item in executed
        if item.entry.type == "remove_trust" and item.outcome.status == "applied"
    }
    rows: list[dict[str, Any]] = []
    for item in executed:
        step = item.entry.intervention
        if not isinstance(step, RevokeRoleSessions) or item.outcome.role is None:
            continue
        role_id = item.outcome.role
        cutoff, source = resolve_cutoff(step.revoked_at, step.cutoff)
        issued_map = dict(step.issued_no_later_than)
        for ecred in sorted(scenario.partition.E, key=lambda value: value.credential):
            if run.index.nodes[ecred.credential].attrs.get("role") != role_id:
                continue
            issued = issued_map.get(ecred.credential, step.issued_default)
            result = assess_session(
                issued_no_later_than=issued,
                ttl_seconds=ecred.ttl_seconds,
                revoked_at=step.revoked_at,
                cutoff=cutoff,
                assessed_at=step.assessed_at,
            )
            rows.append(
                {
                    "step": item.entry.index,
                    "credential": ecred.credential,
                    "role": role_id,
                    "ttl_seconds": ecred.ttl_seconds,
                    "issued_no_later_than": None if issued is None else format_timestamp(issued),
                    "revoked_at": (
                        None if step.revoked_at is None else format_timestamp(step.revoked_at)
                    ),
                    "cutoff": None if cutoff is None else format_timestamp(cutoff),
                    "cutoff_source": source,
                    "cutoff_assumed": source == "assumed_revoked_at_plus_30s",
                    "assessed_at": (
                        None if step.assessed_at is None else format_timestamp(step.assessed_at)
                    ),
                    "validity": result.validity,
                    "access": result.access,
                    "display_state": result.display_state,
                    "conditional_on_propagation": result.conditional_on_propagation,
                    "issue_time_basis": "upper_bound",
                    "re_issue_possible": role_id not in trust_roles,
                    "residual_unknown": [
                        {"kind": "derived_credentials", "detail": _RESIDUAL_UNKNOWN}
                    ],
                }
            )
    return rows


def _issued_before_containment(
    run: _Run,
    executed: list[_Executed],
    scenario: ScenarioReport,
    future: ScenarioAnalysis,
) -> list[dict[str, Any]]:
    if not any(
        item.entry.type in _CONTAINMENT_TYPES and item.outcome.status != "rejected"
        for item in executed
    ):
        return []
    revoked_roles = {
        item.outcome.role
        for item in executed
        if item.entry.type == "revoke_role_sessions" and item.outcome.role is not None
    }
    trust_roles = {
        item.outcome.role
        for item in executed
        if item.entry.type == "remove_trust" and item.outcome.role is not None
    }
    obtainable = {item.credential for item in future.partition.E}
    rows: list[dict[str, Any]] = []
    for ecred in sorted(scenario.partition.E, key=lambda value: value.credential):
        role = run.index.nodes[ecred.credential].attrs.get("role")
        row: dict[str, Any] = {
            "credential": ecred.credential,
            "label": "issued_before_containment",
            "max_remaining_seconds": ecred.ttl_seconds,
            "role": role,
            "still_obtainable_by_new_runs": ecred.credential in obtainable,
        }
        if role in trust_roles and role not in revoked_roles:
            row["note"] = (
                "trust was removed without a revocation step: the existing session "
                "remains active until its expiry"
            )
        rows.append(row)
    return rows


def _rotation_order(
    scenario: ScenarioReport, planned: set[str], risky: set[str]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for step in scenario.rotation_plan.rotation:
        rows.append(
            {
                "order": len(rows) + 1,
                "generation": step.generation,
                "batch": step.batch,
                "depends_on": list(step.depends_on),
                "credentials": [
                    {
                        "id": ref.id,
                        "label": ref.label,
                        "planned": ref.id in planned,
                        "re_exposure_risk": ref.id in risky,
                    }
                    for ref in step.credentials
                ],
            }
        )
    return rows


def _scenario_record(
    run: _Run,
    executed: list[_Executed],
    final: _State,
    item: ScenarioContext,
    saved: ScenarioReport,
) -> dict[str, Any]:
    future = run.analyses(final)[item.selector]
    future_z = {entry.credential for entry in future.partition.Z}
    rotated = [
        step.outcome.credential
        for step in executed
        if step.entry.type == "rotate_credential" and step.outcome.credential is not None
    ]
    before_z = {entry.credential for entry in saved.partition.Z}
    planned = {credential for credential in rotated if credential in before_z}
    risk = sorted(credential for credential in planned if credential in future_z)
    clean = sorted(planned - set(risk))
    after_z = [entry for entry in saved.partition.Z if entry.credential not in clean]
    residual: list[dict[str, Any]] = []
    for entry in future.partition.E:
        residual.append({**_path_record(future, entry.credential), "class": "E"})
    for z_entry in future.partition.Z:
        residual.append(
            {**_path_record(future, z_entry.credential), "class": "Z", "depth": z_entry.depth}
        )
    return {
        "selector": item.selector,
        "selector_kind": item.selector_kind,
        "start_nodes": list(saved.start_nodes),
        "before": saved.partition.model_dump(mode="json"),
        "after": {
            "R": list(saved.partition.R),
            "E": [entry.model_dump(mode="json") for entry in saved.partition.E],
            "Z": [entry.model_dump(mode="json") for entry in after_z],
            "rotated": clean,
            "issued_before_containment": _issued_before_containment(run, executed, saved, future),
            "revoked_access": _revoked_access(run, executed, saved),
            "re_exposure_risk": [
                {**_path_record(future, credential), "reason": "surviving_path"}
                for credential in risk
            ],
        },
        "future_reach": {
            "R": list(future.partition.R),
            "E": [entry.model_dump(mode="json") for entry in future.partition.E],
            "Z": [entry.model_dump(mode="json") for entry in future.partition.Z],
            "truncated": future.truncated,
        },
        "residual_paths": sorted(residual, key=lambda row: (row["class"], row["credential"])),
        "rotation_order": _rotation_order(saved, planned, set(risk)),
        "potential": {
            "before": {"edges": list(saved.potential), "nodes": list(saved.potential_nodes)},
            "after": {
                "edges": list(future.potential_edges),
                "nodes": list(future.potential_nodes),
                "unresolved_inputs": list(future.unresolved_inputs),
            },
        },
    }


def _warn(code: str, detail: str) -> dict[str, str]:
    return {"code": code, "detail": detail}


def _warnings(run: _Run, executed: list[_Executed], final: _State) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    if not run.scenarios:
        warnings.append(_warn("W-WHATIF-NO-SCENARIOS", "the report records no scenarios"))
    final_analyses = run.analyses(final)
    for item, saved in run.scenarios:
        if saved.truncated:
            warnings.append(_warn("W-WHATIF-DEPTH-TRUNCATED", item.selector))
        if final_analyses[item.selector].truncated and not saved.truncated:
            warnings.append(_warn("W-WHATIF-AFTER-DEPTH-TRUNCATED", item.selector))
    trust_roles = {
        step.outcome.role
        for step in executed
        if step.entry.type == "remove_trust" and step.outcome.status == "applied"
    }
    revoke_roles = {
        step.outcome.role
        for step in executed
        if step.entry.type == "revoke_role_sessions" and step.outcome.role is not None
    }
    for role in sorted(str(value) for value in revoke_roles - trust_roles):
        warnings.append(_warn("W-WHATIF-REVOKE-WITHOUT-REMOVE-TRUST", f"re_issue_possible: {role}"))
    session_roles = {
        run.index.nodes[entry.credential].attrs.get("role")
        for _, saved in run.scenarios
        for entry in saved.partition.E
    }
    for role in sorted(str(value) for value in (trust_roles - revoke_roles) & session_roles):
        warnings.append(
            _warn("W-WHATIF-REMOVE-TRUST-WITHOUT-REVOKE", f"sessions remain until expiry: {role}")
        )
    for step in executed:
        if step.outcome.status == "no_effect":
            warnings.append(_warn("W-WHATIF-STEP-NO-EFFECT", f"step {step.entry.index}"))
        if step.outcome.effects.get("repo_write_acceptance_cleared") is True:
            warnings.append(_warn("W-WHATIF-REPO-WRITE-ACCEPTANCE-CLEARED", str(step.outcome.role)))
    warnings.extend(_rotation_warnings(run, executed))
    warnings.extend(_unused_issue_time_warnings(run, executed))
    return warnings


def _rotation_warnings(run: _Run, executed: list[_Executed]) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    final = executed[-1].state_after if executed else _State()
    final_analyses = run.analyses(final)
    sequence = [
        (step.entry.index, step.outcome.credential, step.state_after)
        for step in executed
        if step.entry.type == "rotate_credential" and step.outcome.credential is not None
    ]
    for index, credential, at_step in sequence:
        for item, saved in run.scenarios:
            if credential not in {entry.credential for entry in saved.partition.Z}:
                continue
            then = credential in {
                entry.credential for entry in run.analyses(at_step)[item.selector].partition.Z
            }
            now = credential in {
                entry.credential for entry in final_analyses[item.selector].partition.Z
            }
            if then and not now:
                warnings.append(
                    _warn("W-WHATIF-ROTATE-BEFORE-CLOSING-PATH", f"step {index}: {credential}")
                )
                break
    for item, saved in run.scenarios:
        generation = {
            ref.id: step.generation
            for step in saved.rotation_plan.rotation
            for ref in step.credentials
            if step.generation is not None
        }
        seen: list[tuple[str, int]] = []
        for _, credential, _state in sequence:
            if credential in generation:
                for earlier, earlier_generation in seen:
                    if earlier_generation > generation[credential]:
                        warnings.append(
                            _warn(
                                "W-WHATIF-ROTATION-ORDER",
                                f"{item.selector}: {earlier} is rotated before {credential}",
                            )
                        )
                seen.append((credential, generation[credential]))
    return warnings


def _unused_issue_time_warnings(run: _Run, executed: list[_Executed]) -> list[dict[str, str]]:
    in_scope = {entry.credential for _, saved in run.scenarios for entry in saved.partition.E}
    warnings: list[dict[str, str]] = []
    for step in executed:
        item = step.entry.intervention
        if not isinstance(item, RevokeRoleSessions):
            continue
        if step.outcome.status == "no_effect":
            warnings.append(_warn("W-WHATIF-REVOKE-NO-SESSIONS", f"step {step.entry.index}"))
        warnings.extend(
            _warn("W-WHATIF-UNUSED-ISSUE-TIME", f"step {step.entry.index}: {key}")
            for key, _ in item.issued_no_later_than
            if key not in in_scope
        )
    return warnings


def _caveats(executed: list[_Executed]) -> list[dict[str, str]]:
    caveats = list(_BASE_CAVEATS)
    if any(
        step.entry.type == "revoke_role_sessions" and step.outcome.role is not None
        for step in executed
    ):
        caveats.extend(REVOKE_CAVEATS)
    return [{"id": key, "text": text} for key, text in sorted(caveats)]


def run_whatif(report: Report, plan: Plan, *, check: bool = True) -> dict[str, Any]:
    """The nhi-blast-whatif/1.0 document as plain data (sorted at serialisation)."""
    if check:
        failures: tuple[GuardFailure, ...] = guard_failures(report)
        if failures:
            first = failures[0]
            raise WhatIfAbort(first.code, first.message)
    context = report.context
    if context is None:
        msg = "report has no replay context"
        raise WhatIfAbort(CONTEXT_MISSING, msg)
    run = _Run(report, plan)
    executed = _execute(run)
    final = executed[-1].state_after if executed else _State()
    payload: dict[str, Any] = {
        "schema": WHATIF_SCHEMA,
        "header": HEADER,
        "source_report_digest": digest_of(
            {"context_digest": context.context_digest, "graph_digest": context.graph_digest}
        ),
        "plan_digest": plan.digest,
        "steps": _step_records(run, executed),
        "per_scenario": [
            _scenario_record(run, executed, final, item, saved) for item, saved in run.scenarios
        ],
        "rejected": _rejected(executed),
        "warnings": [
            {"code": code, "detail": detail}
            for code, detail in sorted(
                {(item["code"], item["detail"]) for item in _warnings(run, executed, final)}
            )
        ],
        "caveats": _caveats(executed),
    }
    return redact_payload(payload)


__all__ = ["ANALYSIS_TIME", "WhatIfAbort", "run_whatif"]
