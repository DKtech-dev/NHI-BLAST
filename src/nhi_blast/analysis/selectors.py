"""Parse compromise selectors and resolve their graph start sets (spec 12.1)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from nhi_blast.core.ids import action_node_id, job_node_id
from nhi_blast.core.models import EdgeKind, GraphData, Node, NodeKind
from nhi_blast.parsers.gha.uses import parse_uses
from nhi_blast.resolvers.composite import ExpandedJob


class SelectorKind(StrEnum):
    ACTION = "action"
    ACTION_ANY = "action-any"
    JOB = "job"
    WORKFLOW = "workflow"
    SECRET = "secret"  # noqa: S105
    ROLE = "role"
    REPO_WRITE = "repo-write"
    FORK_PR = "fork-pr"
    ALL_MUTABLE_ACTIONS = "all-mutable-actions"


class SelectorError(ValueError):
    """A selector is malformed or matches no graph input."""


@dataclass(frozen=True, slots=True)
class Selector:
    raw: str
    kind: SelectorKind
    value: str = ""


def _valid_action(value: str) -> bool:
    if any(character.isspace() for character in value):
        return False
    uses = parse_uses(value, 0)
    return uses.kind == "REMOTE" and bool(uses.owner and uses.repo and uses.ref)


def _valid_action_any(value: str) -> bool:
    parts = value.split("/")
    return (
        len(parts) == 2
        and all(parts)
        and "@" not in value
        and not any(character.isspace() for character in value)
    )


def parse_selector(text: str) -> Selector:
    raw = text.strip()
    if raw in {kind.value for kind in SelectorKind} and ":" not in raw:
        return Selector(raw=raw, kind=SelectorKind(raw))
    prefix, separator, value = raw.partition(":")
    if not separator or prefix not in {kind.value for kind in SelectorKind}:
        msg = f"invalid compromise selector: {text!r}"
        raise SelectorError(msg)
    kind = SelectorKind(prefix)
    if not value:
        msg = f"selector {prefix} requires a value"
        raise SelectorError(msg)
    valid = kind not in {
        SelectorKind.REPO_WRITE,
        SelectorKind.FORK_PR,
        SelectorKind.ALL_MUTABLE_ACTIONS,
    }
    if kind is SelectorKind.ACTION:
        valid = _valid_action(value)
    elif kind is SelectorKind.ACTION_ANY:
        valid = _valid_action_any(value)
    elif kind is SelectorKind.JOB:
        path, hash_separator, job_id = value.rpartition("#")
        valid = bool(hash_separator and path and job_id)
    if not valid:
        msg = f"invalid value for {prefix} selector: {value!r}"
        raise SelectorError(msg)
    return Selector(raw=raw, kind=kind, value=value)


def _node(graph: GraphData, node_id: str) -> Node | None:
    return next((node for node in graph.nodes if node.id == node_id), None)


def mutable_action_nodes(graph: GraphData) -> tuple[Node, ...]:
    """Mutable third-party actions that are used by at least one job (spec 12.1)."""
    used = {edge.dst for edge in graph.edges if edge.kind is EdgeKind.RUNS_IN}
    return tuple(
        sorted(
            (
                node
                for node in graph.nodes
                if node.kind is NodeKind.ACTION_REF
                and node.attrs.get("mutable") is True
                and not bool(node.attrs.get("first_party"))
                and node.id in used
            ),
            key=lambda node: node.id,
        )
    )


def _action_label(node: Node) -> str:
    raw = str(node.attrs.get("raw") or node.id.removeprefix("action:"))
    if raw.startswith("docker://"):
        return raw
    return f"action:{raw}"


def mutable_action_scenarios(graph: GraphData) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """One (label, start jobs) pair per mutable third-party action (spec 12.1).

    An empty result is not an error: a fully pinned repository legitimately has no
    mutable third-party actions, and ``all-mutable-actions`` then expands to no
    scenarios.
    """
    starts: dict[str, set[str]] = {}
    for edge in graph.edges:
        if edge.kind is EdgeKind.RUNS_IN:
            starts.setdefault(edge.dst, set()).add(edge.src)
    return tuple(
        (_action_label(node), tuple(sorted(starts.get(node.id, ()))))
        for node in mutable_action_nodes(graph)
    )


def _jobs_for_actions(graph: GraphData, action_ids: set[str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                edge.src
                for edge in graph.edges
                if edge.kind is EdgeKind.RUNS_IN and edge.dst in action_ids
            }
        )
    )


def _action_starts(selector: Selector, graph: GraphData) -> tuple[str, ...]:
    if selector.kind is SelectorKind.ACTION:
        uses = parse_uses(selector.value, 0)
        action_id = action_node_id(uses.owner or "", uses.repo or "", uses.subpath, uses.ref)
        action_ids = {action_id} if _node(graph, action_id) is not None else set()
    else:
        owner, repo = selector.value.split("/", 1)
        action_ids = {
            node.id
            for node in graph.nodes
            if node.kind is NodeKind.ACTION_REF
            and str(node.attrs.get("owner", "")).lower() == owner.lower()
            and str(node.attrs.get("repo", "")).lower() == repo.lower()
        }
    return _jobs_for_actions(graph, action_ids)


def _secret_starts(selector: Selector, graph: GraphData) -> tuple[str, ...]:
    credentials = {
        node.id
        for node in graph.nodes
        if node.kind is NodeKind.CREDENTIAL
        and node.attrs.get("secret") is True
        and node.label == selector.value
    }
    jobs = {
        edge.src for edge in graph.edges if edge.kind is EdgeKind.HOLDS and edge.dst in credentials
    }
    return tuple(sorted(credentials | jobs))


def _role_starts(selector: Selector, graph: GraphData) -> tuple[str, ...]:
    roles = {
        node.id
        for node in graph.nodes
        if node.kind is NodeKind.AWS_ROLE
        and selector.value in {node.id, node.attrs.get("address"), node.attrs.get("arn")}
    }
    sessions = {
        node.id
        for node in graph.nodes
        if node.kind is NodeKind.CREDENTIAL and node.attrs.get("role") in roles
    }
    return tuple(sorted(roles | sessions))


def _resolve(selector: Selector, graph: GraphData) -> tuple[str, ...]:
    if selector.kind in {SelectorKind.ACTION, SelectorKind.ACTION_ANY}:
        return _action_starts(selector, graph)
    if selector.kind is SelectorKind.JOB:
        path, _, job_id = selector.value.rpartition("#")
        node_id = job_node_id(path, job_id)
        return (node_id,) if _node(graph, node_id) is not None else ()
    if selector.kind is SelectorKind.WORKFLOW:
        return tuple(
            sorted(
                node.id
                for node in graph.nodes
                if node.kind is NodeKind.JOB and node.attrs.get("path") == selector.value
            )
        )
    if selector.kind is SelectorKind.SECRET:
        return _secret_starts(selector, graph)
    if selector.kind is SelectorKind.ROLE:
        return _role_starts(selector, graph)
    if selector.kind is SelectorKind.FORK_PR:
        return tuple(
            sorted(
                node.id
                for node in graph.nodes
                if node.kind is NodeKind.JOB and node.attrs.get("untrusted_checkout") is True
            )
        )
    if selector.kind is SelectorKind.REPO_WRITE:
        return tuple(sorted(node.id for node in graph.nodes if node.kind is NodeKind.JOB))
    msg = "all-mutable-actions is expanded by rank, not resolved as one scenario"
    raise SelectorError(msg)


def resolve_starts(
    selector: Selector, graph: GraphData, *, jobs: Sequence[ExpandedJob]
) -> tuple[str, ...]:
    del jobs
    starts = _resolve(selector, graph)
    if not starts and selector.kind is not SelectorKind.FORK_PR:
        msg = f"selector {selector.raw!r} matched no graph targets"
        raise SelectorError(msg)
    return starts


__all__ = [
    "Selector",
    "SelectorError",
    "SelectorKind",
    "mutable_action_nodes",
    "mutable_action_scenarios",
    "parse_selector",
    "resolve_starts",
]
