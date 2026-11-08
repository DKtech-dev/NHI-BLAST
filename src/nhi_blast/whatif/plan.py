"""Interventions plan (nhi-blast-interventions/1.0): safe loading and fail-closed parsing.

An entry that is not understood is never dropped: it becomes a rejection that is
reported in the output, so a plan cannot silently do less than it says.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from nhi_blast.core.artifact_io import ArtifactReadError, InputIdentity, read_bounded_utf8
from nhi_blast.core.canonical import CanonicalError, digest_of
from nhi_blast.core.limits import Limits
from nhi_blast.discovery.paths import OutsideRootError, PathGuard
from nhi_blast.parsers._json import _exceeds_depth
from nhi_blast.parsers.yaml_marked import load_marked_document, to_plain
from nhi_blast.report._text import safe_text
from nhi_blast.whatif import PLAN_SCHEMA
from nhi_blast.whatif.sessions import TimestampError, parse_timestamp

MAX_INTERVENTIONS = 500
_MAX_REF_CHARS = 512
_MAX_PLAN_BYTES = 1024 * 1024
_MAX_PLAN_NODES = 20_000
_MAX_PLAN_DEPTH = 16
PLAN_INVALID = "D-WHATIF-PLAN-INVALID"


class PlanError(ValueError):
    """The plan file cannot be read as an interventions document."""


@dataclass(frozen=True, slots=True)
class DisableEntrypoint:
    node: str


@dataclass(frozen=True, slots=True)
class RemoveTrust:
    role: str
    principal: str | None = None
    edge: str | None = None


@dataclass(frozen=True, slots=True)
class RevokeRoleSessions:
    role: str
    revoked_at: datetime | None = None
    cutoff: datetime | None = None
    assessed_at: datetime | None = None
    issued_no_later_than: tuple[tuple[str, datetime], ...] = ()
    issued_default: datetime | None = None


@dataclass(frozen=True, slots=True)
class RotateCredential:
    credential: str


Intervention = DisableEntrypoint | RemoveTrust | RevokeRoleSessions | RotateCredential


@dataclass(frozen=True, slots=True)
class Rejection:
    reason: str
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class PlanEntry:
    index: int
    type: str
    intervention: Intervention | None = None
    rejection: Rejection | None = None


@dataclass(frozen=True, slots=True)
class Plan:
    entries: tuple[PlanEntry, ...]
    digest: str


# Types that the specification names and v0.3.0 refuses, with the reason shown to the user.
REJECTED_TYPES: dict[str, str] = {
    "inject_deny_policy": "arbitrary deny-policy injection is not modelled in v0.3.0",
    "add_deny_policy": "arbitrary deny-policy injection is not modelled in v0.3.0",
    "deny_policy": "arbitrary deny-policy injection is not modelled in v0.3.0",
    "min_cut": "minimum-cut suggestions are not produced in v0.3.0",
    "suggest_min_cut": "minimum-cut suggestions are not produced in v0.3.0",
    "apply": "the tool never mutates live systems",
    "execute": "the tool never mutates live systems",
    "mutate_live": "the tool never mutates live systems",
}

_FIELDS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "disable_entrypoint": (frozenset({"type", "node"}), frozenset({"node"})),
    "remove_trust": (frozenset({"type", "role", "principal", "edge"}), frozenset({"role"})),
    "revoke_role_sessions": (
        frozenset(
            {
                "type",
                "role",
                "revoked_at",
                "cutoff",
                "assessed_at",
                "issued_no_later_than",
            }
        ),
        frozenset({"role"}),
    ),
    "rotate_credential": (frozenset({"type", "credential"}), frozenset({"credential"})),
}


def _text(value: object) -> str | None:
    if isinstance(value, str) and 0 < len(value) <= _MAX_REF_CHARS:
        return value
    return None


def _timestamp(entry: dict[str, Any], key: str) -> tuple[datetime | None, Rejection | None]:
    if key not in entry or entry[key] is None:
        return None, None
    try:
        return parse_timestamp(entry[key]), None
    except TimestampError as exc:
        return None, Rejection("invalid_timestamp", f"{key}: {exc}")


def _parse_revoke(entry: dict[str, Any]) -> Intervention | Rejection:
    role = _text(entry.get("role"))
    if role is None:
        return Rejection("invalid_field", "role must be a non-empty string")
    stamps: dict[str, datetime | None] = {}
    for key in ("revoked_at", "cutoff", "assessed_at"):
        value, problem = _timestamp(entry, key)
        if problem is not None:
            return problem
        stamps[key] = value
    issued: list[tuple[str, datetime]] = []
    issued_default: datetime | None = None
    raw = entry.get("issued_no_later_than")
    if isinstance(raw, dict):
        for credential, stamp in raw.items():
            if _text(credential) is None:
                return Rejection("invalid_field", "issued_no_later_than keys must be ids")
            try:
                issued.append((str(credential), parse_timestamp(stamp)))
            except TimestampError as exc:
                return Rejection("invalid_timestamp", f"issued_no_later_than: {exc}")
    elif raw is not None:
        issued_default, problem = _timestamp(entry, "issued_no_later_than")
        if problem is not None:
            return problem
    return RevokeRoleSessions(
        role=role,
        revoked_at=stamps["revoked_at"],
        cutoff=stamps["cutoff"],
        assessed_at=stamps["assessed_at"],
        issued_no_later_than=tuple(sorted(issued)),
        issued_default=issued_default,
    )


def _parse_known(kind: str, entry: dict[str, Any]) -> Intervention | Rejection:
    allowed, required = _FIELDS[kind]
    extra = sorted(str(key) for key in entry if key not in allowed)
    if extra:
        return Rejection("unsupported_field", ", ".join(extra[:5]))
    for key in sorted(required):
        if key not in entry:
            return Rejection("missing_field", key)
    if kind == "revoke_role_sessions":
        return _parse_revoke(entry)
    values: dict[str, str | None] = {}
    for key in allowed - {"type"}:
        if key not in entry or entry[key] is None:
            values[key] = None
            continue
        text = _text(entry[key])
        if text is None:
            return Rejection("invalid_field", f"{key} must be a non-empty string")
        values[key] = text
    if kind == "disable_entrypoint":
        return DisableEntrypoint(node=str(values["node"]))
    if kind == "rotate_credential":
        return RotateCredential(credential=str(values["credential"]))
    principal, edge = values["principal"], values["edge"]
    if (principal is None) == (edge is None):
        return Rejection("invalid_field", "give exactly one of principal and edge")
    return RemoveTrust(role=str(values["role"]), principal=principal, edge=edge)


def _display_type(value: object) -> str:
    return safe_text(value, 80) if isinstance(value, str) else "<non-string>"


def parse_plan(data: object) -> Plan:
    """Validate the document shape and classify every entry."""
    if not isinstance(data, dict):
        msg = "plan must be a mapping"
        raise PlanError(msg)
    if data.get("schema") != PLAN_SCHEMA:
        msg = f"plan schema must be {PLAN_SCHEMA}"
        raise PlanError(msg)
    unknown = sorted(str(key) for key in data if key not in {"schema", "interventions"})
    if unknown:
        msg = f"unknown plan key(s): {', '.join(unknown[:5])}"
        raise PlanError(msg)
    items = data.get("interventions")
    if not isinstance(items, list):
        msg = "plan interventions must be a list"
        raise PlanError(msg)
    if len(items) > MAX_INTERVENTIONS:
        msg = f"plan has more than {MAX_INTERVENTIONS} interventions"
        raise PlanError(msg)
    try:
        digest = digest_of(data)
    except (CanonicalError, RecursionError, UnicodeEncodeError):
        msg = "plan contains a value that is not canonically serialisable"
        raise PlanError(msg) from None
    entries: list[PlanEntry] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            entries.append(PlanEntry(index, "<invalid>", rejection=Rejection("unsupported")))
            continue
        kind = item.get("type")
        shown = _display_type(kind)
        if not isinstance(kind, str):
            entries.append(PlanEntry(index, shown, rejection=Rejection("unsupported")))
        elif kind in REJECTED_TYPES:
            entries.append(
                PlanEntry(index, shown, rejection=Rejection("rejected", REJECTED_TYPES[kind]))
            )
        elif kind in _FIELDS:
            parsed = _parse_known(kind, item)
            if isinstance(parsed, Rejection):
                entries.append(PlanEntry(index, kind, rejection=parsed))
            else:
                entries.append(PlanEntry(index, kind, intervention=parsed))
        else:
            entries.append(PlanEntry(index, shown, rejection=Rejection("unsupported")))
    return Plan(entries=tuple(entries), digest=digest)


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            msg = "duplicate key in plan"
            raise PlanError(msg)
        result[key] = value
    return result


def _check_node_budget(data: object, max_nodes: int) -> None:
    pending = [data]
    count = 0
    while pending:
        value = pending.pop()
        count += 1
        if count > max_nodes:
            msg = f"plan exceeds the {max_nodes}-node budget"
            raise PlanError(msg)
        if isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
        if count + len(pending) > max_nodes:
            msg = f"plan exceeds the {max_nodes}-node budget"
            raise PlanError(msg)


def parse_plan_text(
    text: str,
    *,
    suffix: str,
    max_depth: int = _MAX_PLAN_DEPTH,
    max_nodes: int = _MAX_PLAN_NODES,
) -> Plan:
    if suffix == ".json":
        if _exceeds_depth(text, max_depth):
            msg = f"plan nesting exceeds {max_depth} levels"
            raise PlanError(msg)
        try:
            data = json.loads(text, object_pairs_hook=_reject_duplicates)
        except RecursionError:
            msg = "plan nesting is too deep"
            raise PlanError(msg) from None
        except ValueError as exc:
            if isinstance(exc, PlanError):
                raise
            msg = "plan is not valid JSON"
            raise PlanError(msg) from None
        _check_node_budget(data, max_nodes)
    else:
        marked, diagnostics = load_marked_document(
            text, rel_path="plan", limits=Limits(max_yaml_nodes=max_nodes, max_yaml_depth=max_depth)
        )
        if marked is None:
            msg = "plan is not safe YAML"
            raise PlanError(msg)
        if any(item.code == "D-YAML-DUPKEY" for item in diagnostics):
            msg = "duplicate key in plan"
            raise PlanError(msg)
        data = to_plain(marked)
    return parse_plan(data)


def load_plan(path: Path) -> Plan:
    plan, _identity = load_plan_with_identity(path)
    return plan


def load_plan_with_identity(path: Path) -> tuple[Plan, InputIdentity]:
    candidate = path.expanduser()
    suffix = candidate.suffix.lower()
    if suffix not in {".json", ".yaml", ".yml"}:
        msg = "plan file must end in .json, .yaml or .yml"
        raise PlanError(msg)
    try:
        guard = PathGuard.create(candidate.parent.resolve())
        guard.require_inside(candidate)
    except (OutsideRootError, OSError):
        msg = "plan path is not readable inside its own directory"
        raise PlanError(msg) from None
    try:
        text, identity = read_bounded_utf8(candidate, _MAX_PLAN_BYTES)
    except ArtifactReadError as exc:
        msg = f"cannot read plan file: {exc}"
        raise PlanError(msg) from None
    return parse_plan_text(text, suffix=suffix), identity


__all__ = [
    "MAX_INTERVENTIONS",
    "PLAN_INVALID",
    "REJECTED_TYPES",
    "DisableEntrypoint",
    "Intervention",
    "Plan",
    "PlanEntry",
    "PlanError",
    "Rejection",
    "RemoveTrust",
    "RevokeRoleSessions",
    "RotateCredential",
    "load_plan",
    "load_plan_with_identity",
    "parse_plan",
    "parse_plan_text",
]
