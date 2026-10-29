"""Cloud fact resolution from Terraform and IAM JSON inputs (spec 8.3-8.6).

The resolver assembles roles, credential stores, OIDC providers and external targets
from parsed resources. It never reads a secret value: sensitive leaves were removed
by the parsers, and policy strings are resolved only from literal JSON, a referenced
``data.aws_iam_policy_document`` body, or an IAM JSON input. Anything else is marked
unresolved rather than guessed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from nhi_blast.core.config import Config
from nhi_blast.core.data import credential_heuristics, sinks
from nhi_blast.core.diagnostics import (
    Diagnostic,
    DiagnosticBag,
    DiagnosticLevel,
    info,
    warning,
)
from nhi_blast.core.evidence import (
    Evidence,
    EvidenceClass,
    dedupe_evidence,
    evidence_sort_key,
)
from nhi_blast.core.ids import role_node_id, sink_node_id
from nhi_blast.core.models import (
    CredentialKind,
    ExternalTargetFact,
    PolicyContext,
    ProviderFact,
    RoleFact,
    SinkFact,
    SinkType,
    Statement,
    TfSource,
)
from nhi_blast.parsers.iam.policy_doc import parse_policy_text, statements_from_policy_object
from nhi_blast.parsers.terraform.facts import (
    IamDocumentFact,
    TfModelFact,
    TfPolicyDocumentFact,
    TfResource,
)

_ARN_SECRET = re.compile(r"^arn:[^:]+:secretsmanager:[^:]*:[^:]*:secret:(?P<name>.+)$")
_ARN_SSM = re.compile(r"^arn:[^:]+:ssm:[^:]*:[^:]*:parameter/(?P<name>.+)$")
_RANDOM_SUFFIX = re.compile(r"-(?:\?{6}|\*{6})$")
_SOURCE_RANK = {
    TfSource.PLAN: 0,
    TfSource.STATE: 0,
    TfSource.IAM_JSON: 0,
    TfSource.HCL: 1,
}


@dataclass(frozen=True, slots=True)
class CloudFacts:
    roles: tuple[RoleFact, ...]
    sinks: tuple[SinkFact, ...]
    providers: tuple[ProviderFact, ...]
    externals: tuple[ExternalTargetFact, ...]
    policy_context: PolicyContext
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True, slots=True)
class _Snapshot:
    resources: Mapping[str, TfResource]
    documents: Mapping[str, TfPolicyDocumentFact]


@dataclass(frozen=True, slots=True)
class _ResolvedPolicy:
    statements: tuple[Statement, ...]
    resolved: bool


@dataclass(frozen=True, slots=True)
class _PolicyBody:
    arn: str | None
    aliases: tuple[str, ...]
    statements: tuple[Statement, ...]
    resolved: bool


@dataclass(slots=True)
class _RoleDraft:
    address: str
    resource: TfResource | None
    file: str
    line: int | None
    name: str
    arn: str | None
    max_session_duration: int = 3600
    trust: list[Statement] = field(default_factory=list)
    trust_unresolved: bool = False
    inline: list[Statement] = field(default_factory=list)
    managed_arns: list[str] = field(default_factory=list)
    boundary_raw: str | None = None
    boundary: list[Statement] = field(default_factory=list)
    boundary_supplied: bool = False
    unresolved_refs: set[str] = field(default_factory=set)
    evidence: list[Evidence] = field(default_factory=list)


@dataclass(slots=True)
class _SinkDraft:
    id: str
    name: str
    sink_type: SinkType
    arn: str | None
    kms_key_id: str | None
    rotation_interval_days: int | None
    credential_kind: CredentialKind | None
    criticality: int
    evidence: list[Evidence] = field(default_factory=list)
    resource_policy: list[Statement] = field(default_factory=list)
    aliases: set[str] = field(default_factory=set)


def _source_class(source: TfSource) -> EvidenceClass:
    return EvidenceClass.DERIVED if source is TfSource.HCL else EvidenceClass.DECLARED


def _evidence_for(resource: TfResource, rule: str, detail: str = "") -> Evidence:
    return Evidence(
        cls=_source_class(resource.source),
        rule=rule,
        file=resource.file,
        line=resource.line,
        detail=detail,
    )


def _collect(models: Sequence[TfModelFact]) -> _Snapshot:
    resources: dict[str, TfResource] = {}
    documents: dict[str, TfPolicyDocumentFact] = {}
    ordered = sorted(models, key=lambda model: (_SOURCE_RANK[model.source], model.file))
    for model in ordered:
        for address in sorted(model.resources):
            resources.setdefault(address, model.resources[address])
        for address in sorted(model.policy_documents):
            documents.setdefault(address, model.policy_documents[address])
    return _Snapshot(resources=resources, documents=documents)


def _text(values: Mapping[str, Any], key: str) -> str | None:
    value = values.get(key)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _text_tuple(values: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = values.get(key)
    if isinstance(value, str):
        stripped = value.strip()
        return (stripped,) if stripped else ()
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    return ()


def _integer(values: Mapping[str, Any], key: str) -> int | None:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _normalise_reference(value: str) -> str:
    text = value.strip()
    if text.startswith("${") and text.endswith("}"):
        return text[2:-1].strip()
    return text


def _resolve_policy_text(value: str, documents: Mapping[str, TfPolicyDocumentFact]) -> str | None:
    text = _normalise_reference(value)
    if text.startswith("{"):
        return text
    address = text[: -len(".json")] if text.endswith(".json") else text
    document = documents.get(address) or documents.get(text)
    if document is None or document.json_text is None:
        return None
    return document.json_text


def _resolve_policy(
    value: Any,
    *,
    resource: TfResource,
    documents: Mapping[str, TfPolicyDocumentFact],
    rule: str,
    detail: str,
    diagnostics: list[Diagnostic],
) -> _ResolvedPolicy:
    if isinstance(value, Mapping):
        return _ResolvedPolicy(
            statements=statements_from_policy_object(
                value,
                file=resource.file,
                line=resource.line,
                rule=rule,
                detail=detail,
            ),
            resolved=True,
        )
    if not isinstance(value, str):
        diagnostics.append(
            warning(
                "D-TF-POLICY-SHAPE",
                f"{resource.address}: policy value is not a string",
                file=resource.file,
                line=resource.line,
            )
        )
        return _ResolvedPolicy((), False)
    text = _resolve_policy_text(value, documents)
    if text is None:
        diagnostics.append(
            warning(
                "D-TF-POLICY-UNRESOLVED",
                f"{resource.address}: policy body could not be resolved from the inputs",
                file=resource.file,
                line=resource.line,
            )
        )
        return _ResolvedPolicy((), False)
    statements, parse_diagnostics = parse_policy_text(
        text, file=resource.file, rule=rule, detail=detail, line=resource.line
    )
    diagnostics.extend(parse_diagnostics)
    resolved = not any(item.level is DiagnosticLevel.ERROR for item in parse_diagnostics)
    return _ResolvedPolicy(statements, resolved)


def _statement_signature(statement: Statement) -> str:
    return json.dumps(
        {
            "effect": statement.effect.value,
            "actions": statement.actions,
            "not_actions": statement.not_actions,
            "resources": statement.resources,
            "not_resources": statement.not_resources,
            "principals": statement.principals,
            "conditions": statement.conditions,
            "sid": statement.sid,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _unique_statements(statements: Iterable[Statement]) -> tuple[Statement, ...]:
    unique: dict[str, Statement] = {}
    for statement in statements:
        unique.setdefault(_statement_signature(statement), statement)
    return tuple(unique.values())


def _sorted_evidence(evidence: Iterable[Evidence]) -> tuple[Evidence, ...]:
    return tuple(sorted(dedupe_evidence(evidence), key=evidence_sort_key))


def _policy_bodies(
    snapshot: _Snapshot, diagnostics: list[Diagnostic]
) -> tuple[dict[str, _PolicyBody], dict[str, tuple[Statement, ...]]]:
    by_alias: dict[str, _PolicyBody] = {}
    by_arn: dict[str, tuple[Statement, ...]] = {}
    for address in sorted(snapshot.resources):
        resource = snapshot.resources[address]
        if resource.type != "aws_iam_policy":
            continue
        arn = _text(resource.values, "arn")
        name = _text(resource.values, "name") or resource.name
        aliases = tuple(
            sorted(
                {
                    address,
                    f"{address}.arn",
                    f"{address}.id",
                    f"{address}.name",
                    name,
                    *([arn] if arn else []),
                }
            )
        )
        raw = resource.values.get("policy")
        if "policy" in resource.unknown_fields or raw is None:
            diagnostics.append(
                warning(
                    "D-TF-POLICY-UNRESOLVED",
                    f"{address}: managed policy body is unknown",
                    file=resource.file,
                    line=resource.line,
                )
            )
            body = _PolicyBody(arn=arn, aliases=aliases, statements=(), resolved=False)
        else:
            resolved = _resolve_policy(
                raw,
                resource=resource,
                documents=snapshot.documents,
                rule="IAM.managed",
                detail=f"managed policy {name}",
                diagnostics=diagnostics,
            )
            body = _PolicyBody(
                arn=arn,
                aliases=aliases,
                statements=resolved.statements,
                resolved=resolved.resolved,
            )
        for alias in aliases:
            by_alias.setdefault(alias, body)
        if arn is not None and body.resolved:
            by_arn[arn] = _unique_statements((*by_arn.get(arn, ()), *body.statements))
    return by_alias, by_arn


def _resolve_policy_arn(raw: str, by_alias: Mapping[str, _PolicyBody]) -> str | None:
    text = _normalise_reference(raw)
    if text.startswith("arn:"):
        return text
    body = by_alias.get(text)
    return body.arn if body is not None else None


def _role_aliases(draft: _RoleDraft) -> tuple[str, ...]:
    aliases = {
        draft.address,
        f"{draft.address}.id",
        f"{draft.address}.name",
        f"{draft.address}.arn",
        draft.name,
        draft.arn or "",
    }
    return tuple(sorted(alias for alias in aliases if alias))


def _create_role_draft(
    resource: TfResource,
    snapshot: _Snapshot,
    by_alias: Mapping[str, _PolicyBody],
    diagnostics: list[Diagnostic],
) -> _RoleDraft:
    values = resource.values
    arn = _text(values, "arn")
    name = _text(values, "name") or _role_name_from_arn(arn) or resource.name
    max_session = _integer(values, "max_session_duration")
    draft = _RoleDraft(
        address=resource.address,
        resource=resource,
        file=resource.file,
        line=resource.line,
        name=name,
        arn=arn,
        max_session_duration=max_session if max_session and max_session > 0 else 3600,
        boundary_raw=_text(values, "permissions_boundary"),
    )
    draft.evidence.append(_evidence_for(resource, "TF.role", f"role {name}"))
    _fill_role_policy(draft, resource, snapshot, diagnostics)
    for raw in _text_tuple(values, "managed_policy_arns"):
        resolved = _resolve_policy_arn(raw, by_alias)
        if resolved is None:
            draft.unresolved_refs.add(raw)
            diagnostics.append(
                warning(
                    "D-TF-POLICY-UNRESOLVED",
                    f"{resource.address}: managed policy reference {raw} could not be resolved",
                    file=resource.file,
                    line=resource.line,
                )
            )
        else:
            draft.managed_arns.append(resolved)
    if "permissions_boundary" in resource.unknown_fields:
        draft.unresolved_refs.add("permissions_boundary")
        diagnostics.append(
            warning(
                "D-TF-BOUNDARY-UNRESOLVED",
                f"{resource.address}: permissions boundary is unknown",
                file=resource.file,
                line=resource.line,
            )
        )
    return draft


def _role_name_from_arn(arn: str | None) -> str | None:
    if arn is None:
        return None
    marker = ":role/"
    if marker not in arn:
        return None
    tail = arn.split(marker, 1)[1]
    return tail.rsplit("/", 1)[-1] or None


def _fill_role_policy(
    draft: _RoleDraft,
    resource: TfResource,
    snapshot: _Snapshot,
    diagnostics: list[Diagnostic],
) -> None:
    if "assume_role_policy" in resource.unknown_fields:
        draft.trust_unresolved = True
        diagnostics.append(
            warning(
                "D-TF-UNKNOWN",
                f"{resource.address}.assume_role_policy is unknown; trust is not analysed",
                file=resource.file,
                line=resource.line,
            )
        )
    else:
        raw = resource.values.get("assume_role_policy")
        if raw is None:
            draft.trust_unresolved = True
        else:
            resolved = _resolve_policy(
                raw,
                resource=resource,
                documents=snapshot.documents,
                rule="IAM.trust",
                detail=f"trust policy for {draft.name}",
                diagnostics=diagnostics,
            )
            draft.trust.extend(resolved.statements)
            draft.trust_unresolved = not resolved.resolved

    raw_inline = resource.values.get("inline_policy")
    if raw_inline is not None and not isinstance(raw_inline, (str, bytes, bytearray)):
        if not isinstance(raw_inline, Sequence):
            diagnostics.append(
                warning(
                    "D-TF-POLICY-SHAPE",
                    f"{resource.address}: inline_policy is not a list",
                    file=resource.file,
                    line=resource.line,
                )
            )
            return
        for position, entry in enumerate(raw_inline):
            if not isinstance(entry, Mapping):
                diagnostics.append(
                    warning(
                        "D-TF-POLICY-SHAPE",
                        f"{resource.address}: inline_policy[{position}] is not a mapping",
                        file=resource.file,
                        line=resource.line,
                    )
                )
                continue
            policy_name = entry.get("name")
            label = str(policy_name) if isinstance(policy_name, str) else f"#{position}"
            resolved = _resolve_policy(
                entry.get("policy"),
                resource=resource,
                documents=snapshot.documents,
                rule="IAM.inline",
                detail=f"inline policy {label} on {draft.name}",
                diagnostics=diagnostics,
            )
            draft.inline.extend(resolved.statements)
            draft.evidence.append(_evidence_for(resource, "IAM.inline", f"inline policy {label}"))
            if not resolved.resolved:
                draft.unresolved_refs.add(f"{resource.address}.inline_policy[{position}]")
    if "inline_policy" in resource.unknown_fields:
        draft.unresolved_refs.add("inline_policy")
        diagnostics.append(
            warning(
                "D-TF-UNKNOWN",
                f"{resource.address}.inline_policy is unknown; permissions are not analysed",
                file=resource.file,
                line=resource.line,
            )
        )


def _role_alias_map(drafts: Mapping[str, _RoleDraft]) -> dict[str, _RoleDraft]:
    aliases: dict[str, _RoleDraft] = {}
    for draft in drafts.values():
        for alias in _role_aliases(draft):
            aliases.setdefault(alias, draft)
    return aliases


def _find_role(raw: str, aliases: Mapping[str, _RoleDraft]) -> _RoleDraft | None:
    return aliases.get(_normalise_reference(raw))


def _apply_role_attachments(
    resources: Mapping[str, TfResource],
    draft_aliases: dict[str, _RoleDraft],
    snapshot: _Snapshot,
    by_alias: Mapping[str, _PolicyBody],
    diagnostics: list[Diagnostic],
) -> None:
    for address in sorted(resources):
        resource = resources[address]
        if resource.type == "aws_iam_role_policy":
            _apply_inline_attachment(resource, draft_aliases, snapshot, diagnostics)
        elif resource.type in {"aws_iam_role_policy_attachment", "aws_iam_policy_attachment"}:
            _apply_policy_attachment(resource, draft_aliases, by_alias, diagnostics)


def _apply_inline_attachment(
    resource: TfResource,
    draft_aliases: dict[str, _RoleDraft],
    snapshot: _Snapshot,
    diagnostics: list[Diagnostic],
) -> None:
    raw_role = resource.values.get("role")
    if not isinstance(raw_role, str):
        diagnostics.append(
            warning(
                "D-TF-ROLE-UNBOUND",
                f"{resource.address}: role reference is missing or not a string",
                file=resource.file,
                line=resource.line,
            )
        )
        return
    draft = _find_role(raw_role, draft_aliases)
    if draft is None:
        diagnostics.append(
            warning(
                "D-TF-ROLE-UNBOUND",
                f"{resource.address}: role {raw_role} is not present in the inputs",
                file=resource.file,
                line=resource.line,
            )
        )
        return
    policy_name = _text(resource.values, "name") or resource.name
    if "policy" in resource.unknown_fields or resource.values.get("policy") is None:
        draft.unresolved_refs.add(f"{resource.address}.policy")
        diagnostics.append(
            warning(
                "D-TF-POLICY-UNRESOLVED",
                f"{resource.address}: attached inline policy is unknown",
                file=resource.file,
                line=resource.line,
            )
        )
    else:
        resolved = _resolve_policy(
            resource.values.get("policy"),
            resource=resource,
            documents=snapshot.documents,
            rule="IAM.inline",
            detail=f"inline policy {policy_name} on {draft.name}",
            diagnostics=diagnostics,
        )
        draft.inline.extend(resolved.statements)
        if not resolved.resolved:
            draft.unresolved_refs.add(f"{resource.address}.policy")
    draft.evidence.append(_evidence_for(resource, "IAM.inline", f"inline policy {policy_name}"))


def _apply_policy_attachment(
    resource: TfResource,
    draft_aliases: dict[str, _RoleDraft],
    by_alias: Mapping[str, _PolicyBody],
    diagnostics: list[Diagnostic],
) -> None:
    role_refs = _text_tuple(resource.values, "roles") or _text_tuple(resource.values, "role")
    if not role_refs:
        diagnostics.append(
            warning(
                "D-TF-ROLE-UNBOUND",
                f"{resource.address}: attachment names no role",
                file=resource.file,
                line=resource.line,
            )
        )
        return
    raw_policy = resource.values.get("policy_arn")
    policy_arn = _resolve_policy_arn(raw_policy, by_alias) if isinstance(raw_policy, str) else None
    if policy_arn is None:
        diagnostics.append(
            warning(
                "D-TF-POLICY-UNRESOLVED",
                f"{resource.address}: policy_arn could not be resolved",
                file=resource.file,
                line=resource.line,
            )
        )
    for role_ref in role_refs:
        draft = _find_role(role_ref, draft_aliases)
        if draft is None:
            diagnostics.append(
                warning(
                    "D-TF-ROLE-UNBOUND",
                    f"{resource.address}: role {role_ref} is not present in the inputs",
                    file=resource.file,
                    line=resource.line,
                )
            )
            continue
        draft.evidence.append(
            _evidence_for(resource, "IAM.attached", f"policy attachment for {draft.name}")
        )
        if policy_arn is None:
            draft.unresolved_refs.add(str(raw_policy or resource.address))
        else:
            draft.managed_arns.append(policy_arn)


def _report_missing_policy_bodies(
    drafts: Iterable[_RoleDraft],
    by_arn: Mapping[str, tuple[Statement, ...]],
    diagnostics: list[Diagnostic],
) -> None:
    for draft in drafts:
        for arn in sorted({*draft.managed_arns}):
            if arn in by_arn:
                continue
            draft.unresolved_refs.add(arn)
            diagnostics.append(
                info(
                    "D-TF-POLICY-UNRESOLVED",
                    f"attached managed policy {arn} body was not supplied",
                    file=draft.file,
                    line=draft.line,
                )
            )


def _resolve_boundaries(
    drafts: Iterable[_RoleDraft],
    by_alias: Mapping[str, _PolicyBody],
    by_arn: Mapping[str, tuple[Statement, ...]],
    diagnostics: list[Diagnostic],
) -> None:
    for draft in drafts:
        if draft.boundary_raw is None:
            continue
        arn = _resolve_policy_arn(draft.boundary_raw, by_alias)
        statements = by_arn.get(arn, ()) if arn is not None else ()
        if arn is None or arn not in by_arn:
            draft.unresolved_refs.add(draft.boundary_raw)
            diagnostics.append(
                warning(
                    "D-TF-BOUNDARY-UNRESOLVED",
                    f"{draft.address}: permissions boundary body was not supplied",
                    file=draft.file,
                    line=draft.line,
                )
            )
            continue
        draft.boundary.extend(statements)
        draft.boundary_supplied = True


def _apply_iam_documents(
    drafts: dict[str, _RoleDraft],
    aliases: dict[str, _RoleDraft],
    documents: Sequence[IamDocumentFact],
    diagnostics: list[Diagnostic],
) -> None:
    for document in sorted(documents, key=lambda item: (item.file, item.label)):
        identity = document.role_arn or document.role_name
        if identity is None:
            if document.statements or document.assume_role_statements:
                diagnostics.append(
                    warning(
                        "D-IAM-UNBOUND",
                        f"{document.label}: policy document is not bound to a role",
                        file=document.file,
                    )
                )
            continue
        draft = aliases.get(identity) or (
            aliases.get(document.role_name) if document.role_name else None
        )
        if draft is None:
            draft = _role_draft_from_iam(document, identity)
            drafts.setdefault(_draft_key(draft), draft)
            aliases.update(dict.fromkeys(_role_aliases(draft), draft))
            diagnostics.append(
                info(
                    "D-IAM-ROLE-ONLY",
                    f"{document.label}: role is defined only in IAM JSON; policies are unknown",
                    file=document.file,
                )
            )
        else:
            draft.evidence.append(
                Evidence(
                    cls=EvidenceClass.DECLARED,
                    rule="IAM.trust",
                    file=document.file,
                    detail=f"IAM JSON trust policy for {draft.name}",
                )
            )
        if document.assume_role_statements:
            draft.trust.extend(document.assume_role_statements)
            draft.trust_unresolved = False
        if document.statements:
            draft.inline.extend(document.statements)


def _draft_key(draft: _RoleDraft) -> str:
    return role_node_id(draft.arn or draft.address)


def _role_draft_from_iam(document: IamDocumentFact, identity: str) -> _RoleDraft:
    arn = document.role_arn
    name = document.role_name or _role_name_from_arn(arn) or identity
    draft = _RoleDraft(
        address=identity,
        resource=None,
        file=document.file,
        line=None,
        name=name,
        arn=arn,
        trust=list(document.assume_role_statements),
        trust_unresolved=not document.assume_role_statements,
        inline=list(document.statements),
    )
    draft.evidence.append(
        Evidence(
            cls=EvidenceClass.DECLARED,
            rule="IAM.role",
            file=document.file,
            detail=f"role {name} from IAM JSON",
        )
    )
    return draft


def _finalise_roles(drafts: Iterable[_RoleDraft]) -> tuple[RoleFact, ...]:
    grouped: dict[str, list[_RoleDraft]] = {}
    for draft in sorted(
        drafts, key=lambda item: (item.resource is None, item.address, item.arn or "")
    ):
        grouped.setdefault(_draft_key(draft), []).append(draft)
    roles: list[RoleFact] = []
    for key in sorted(grouped):
        group = grouped[key]
        primary = group[0]
        trust: list[Statement] = []
        inline: list[Statement] = []
        boundary: list[Statement] = []
        managed: set[str] = set()
        unresolved: set[str] = set()
        evidence: list[Evidence] = []
        boundary_supplied = False
        trust_unresolved = False
        for draft in group:
            trust.extend(draft.trust)
            inline.extend(draft.inline)
            boundary.extend(draft.boundary)
            managed.update(draft.managed_arns)
            unresolved.update(draft.unresolved_refs)
            evidence.extend(draft.evidence)
            boundary_supplied = boundary_supplied or draft.boundary_supplied
            trust_unresolved = trust_unresolved or draft.trust_unresolved
        roles.append(
            RoleFact(
                id=key,
                address=primary.address,
                name=primary.name,
                arn=primary.arn,
                max_session_duration=primary.max_session_duration,
                trust_statements=_unique_statements(trust),
                inline_statements=_unique_statements(inline),
                managed_policy_arns=tuple(sorted(managed)),
                boundary_statements=_unique_statements(boundary),
                boundary_supplied=boundary_supplied,
                trust_unresolved=trust_unresolved,
                unresolved_policy_refs=tuple(sorted(unresolved)),
                evidence=_sorted_evidence(evidence),
            )
        )
    return tuple(roles)


def _sink_name_from_arn(sink_type: SinkType, arn: str | None) -> str | None:
    if arn is None:
        return None
    if sink_type is SinkType.SECRETSMANAGER_SECRET:
        match = _ARN_SECRET.match(arn)
        if match is not None:
            return _RANDOM_SUFFIX.sub("", match.group("name"))
    else:
        match = _ARN_SSM.match(arn)
        if match is not None:
            return match.group("name")
    return None


def _secret_sink_draft(
    resource: TfResource,
    snapshot: _Snapshot,
    diagnostics: list[Diagnostic],
) -> _SinkDraft | None:
    arn = _text(resource.values, "arn")
    name = _text(resource.values, "name") or _sink_name_from_arn(
        SinkType.SECRETSMANAGER_SECRET, arn
    )
    if name is None:
        diagnostics.append(
            warning(
                "D-TF-UNKNOWN",
                f"{resource.address}: secret name is unknown",
                file=resource.file,
                line=resource.line,
            )
        )
        return None
    kind, criticality = credential_heuristics().classify_sink(name, SinkType.SECRETSMANAGER_SECRET)
    draft = _SinkDraft(
        id=sink_node_id(SinkType.SECRETSMANAGER_SECRET.value, name),
        name=name,
        sink_type=SinkType.SECRETSMANAGER_SECRET,
        arn=arn,
        kms_key_id=_text(resource.values, "kms_key_id"),
        rotation_interval_days=None,
        credential_kind=kind,
        criticality=criticality,
        evidence=[_evidence_for(resource, "TF.sink", f"Secrets Manager secret {name}")],
        aliases={resource.address, f"{resource.address}.id", f"{resource.address}.arn", name},
    )
    if arn is not None:
        draft.aliases.add(arn)
    raw_policy = resource.values.get("policy")
    if raw_policy is not None:
        resolved = _resolve_policy(
            raw_policy,
            resource=resource,
            documents=snapshot.documents,
            rule="IAM.resource",
            detail=f"resource policy for {name}",
            diagnostics=diagnostics,
        )
        draft.resource_policy.extend(resolved.statements)
    return draft


def _parameter_sink_draft(resource: TfResource, diagnostics: list[Diagnostic]) -> _SinkDraft | None:
    arn = _text(resource.values, "arn")
    name = _text(resource.values, "name") or _sink_name_from_arn(SinkType.SSM_PARAMETER, arn)
    if name is None:
        diagnostics.append(
            warning(
                "D-TF-UNKNOWN",
                f"{resource.address}: parameter name is unknown",
                file=resource.file,
                line=resource.line,
            )
        )
        return None
    parameter_type = _text(resource.values, "type")
    kind, criticality = credential_heuristics().classify_sink(
        name,
        SinkType.SSM_PARAMETER,
        parameter_type=parameter_type,
        credential_bearing_types=sinks().spec(SinkType.SSM_PARAMETER).credential_bearing_types,
    )
    draft = _SinkDraft(
        id=sink_node_id(SinkType.SSM_PARAMETER.value, name),
        name=name,
        sink_type=SinkType.SSM_PARAMETER,
        arn=arn,
        kms_key_id=_text(resource.values, "key_id"),
        rotation_interval_days=None,
        credential_kind=kind,
        criticality=criticality,
        evidence=[_evidence_for(resource, "TF.sink", f"SSM parameter {name}")],
        aliases={resource.address, f"{resource.address}.id", f"{resource.address}.arn", name},
    )
    if arn is not None:
        draft.aliases.add(arn)
    return draft


def _sink_index(
    drafts: Mapping[str, _SinkDraft],
) -> dict[str, _SinkDraft]:
    aliases: dict[str, _SinkDraft] = {}
    for key in sorted(drafts):
        draft = drafts[key]
        for alias in sorted(draft.aliases):
            aliases.setdefault(alias, draft)
    return aliases


def _lookup_sink(raw: str, aliases: Mapping[str, _SinkDraft]) -> _SinkDraft | None:
    return aliases.get(_normalise_reference(raw))


def _rotation_days(values: Mapping[str, Any]) -> int | None:
    enabled = values.get("rotation_enabled")
    if enabled is False:
        return None
    raw_rules = values.get("rotation_rules")
    rules: tuple[Any, ...]
    if isinstance(raw_rules, Mapping):
        rules = (raw_rules,)
    elif isinstance(raw_rules, Sequence) and not isinstance(raw_rules, (str, bytes, bytearray)):
        rules = tuple(raw_rules)
    else:
        rules = ()
    for rule in rules:
        if not isinstance(rule, Mapping):
            continue
        days = _integer(rule, "automatically_after_days")
        if days is not None and days > 0:
            return days
    return None


def _apply_rotation(
    resources: Mapping[str, TfResource],
    sinks_by_alias: Mapping[str, _SinkDraft],
    diagnostics: list[Diagnostic],
) -> None:
    for address in sorted(resources):
        resource = resources[address]
        if resource.type != "aws_secretsmanager_secret_rotation":
            continue
        raw = resource.values.get("secret_id")
        if not isinstance(raw, str):
            diagnostics.append(
                warning(
                    "D-TF-ROTATION-UNBOUND",
                    f"{resource.address}: rotation secret_id is unknown",
                    file=resource.file,
                    line=resource.line,
                )
            )
            continue
        draft = _lookup_sink(raw, sinks_by_alias)
        if draft is None:
            diagnostics.append(
                warning(
                    "D-TF-ROTATION-UNBOUND",
                    f"{resource.address}: rotation target {raw} is not a supplied secret",
                    file=resource.file,
                    line=resource.line,
                )
            )
            continue
        days = _rotation_days(resource.values)
        if days is None:
            draft.evidence.append(
                _evidence_for(resource, "H-ROT-WINDOW", "rotation is disabled or unscheduled")
            )
            continue
        if draft.rotation_interval_days is not None and draft.rotation_interval_days != days:
            diagnostics.append(
                warning(
                    "D-TF-ROTATION-CONFLICT",
                    f"{resource.address}: rotation interval conflicts with another resource",
                    file=resource.file,
                    line=resource.line,
                )
            )
            draft.rotation_interval_days = min(draft.rotation_interval_days, days)
        else:
            draft.rotation_interval_days = days
        draft.evidence.append(
            _evidence_for(resource, "H-ROT-WINDOW", f"rotation every {days} days")
        )


def _apply_secret_policies(
    resources: Mapping[str, TfResource],
    sinks_by_alias: Mapping[str, _SinkDraft],
    snapshot: _Snapshot,
    diagnostics: list[Diagnostic],
) -> None:
    for address in sorted(resources):
        resource = resources[address]
        if resource.type != "aws_secretsmanager_secret_policy":
            continue
        raw = resource.values.get("secret_arn")
        draft = _lookup_sink(raw, sinks_by_alias) if isinstance(raw, str) else None
        if draft is None:
            diagnostics.append(
                warning(
                    "D-TF-SINK-UNBOUND",
                    f"{resource.address}: secret policy target is not a supplied secret",
                    file=resource.file,
                    line=resource.line,
                )
            )
            continue
        resolved = _resolve_policy(
            resource.values.get("policy"),
            resource=resource,
            documents=snapshot.documents,
            rule="IAM.resource",
            detail=f"resource policy for {draft.name}",
            diagnostics=diagnostics,
        )
        draft.resource_policy.extend(resolved.statements)
        draft.evidence.append(_evidence_for(resource, "IAM.resource", "secret resource policy"))


def _apply_secret_versions(
    resources: Mapping[str, TfResource],
    sinks_by_alias: Mapping[str, _SinkDraft],
) -> None:
    for address in sorted(resources):
        resource = resources[address]
        if resource.type != "aws_secretsmanager_secret_version":
            continue
        raw = resource.values.get("secret_id")
        draft = _lookup_sink(raw, sinks_by_alias) if isinstance(raw, str) else None
        if draft is None:
            continue
        draft.evidence.append(
            _evidence_for(
                resource, "TF.secret_version", "value is managed by Terraform (value not read)"
            )
        )


def _merge_sinks(drafts: Mapping[str, _SinkDraft]) -> tuple[SinkFact, ...]:
    facts: list[SinkFact] = []
    for key in sorted(drafts):
        draft = drafts[key]
        facts.append(
            SinkFact(
                id=draft.id,
                name=draft.name,
                sink_type=draft.sink_type,
                arn=draft.arn,
                kms_key_id=draft.kms_key_id,
                rotation_interval_days=draft.rotation_interval_days,
                resource_policy_statements=_unique_statements(draft.resource_policy),
                credential_kind=draft.credential_kind,
                criticality=draft.criticality,
                evidence=_sorted_evidence(draft.evidence),
            )
        )
    return tuple(facts)


def _collect_sinks(snapshot: _Snapshot, diagnostics: list[Diagnostic]) -> tuple[_SinkDraft, ...]:
    drafts: dict[str, _SinkDraft] = {}
    for address in sorted(snapshot.resources):
        resource = snapshot.resources[address]
        draft: _SinkDraft | None = None
        if resource.type == "aws_secretsmanager_secret":
            draft = _secret_sink_draft(resource, snapshot, diagnostics)
        elif resource.type == "aws_ssm_parameter":
            draft = _parameter_sink_draft(resource, diagnostics)
        if draft is None:
            continue
        existing = drafts.get(draft.id)
        if existing is not None:
            existing.evidence.extend(draft.evidence)
            existing.aliases.update(draft.aliases)
            existing.resource_policy.extend(draft.resource_policy)
            if existing.arn is None:
                existing.arn = draft.arn
            if existing.kms_key_id is None:
                existing.kms_key_id = draft.kms_key_id
            if existing.credential_kind is None:
                existing.credential_kind = draft.credential_kind
                existing.criticality = draft.criticality
            continue
        drafts[draft.id] = draft
    by_alias = _sink_index(drafts)
    _apply_rotation(snapshot.resources, by_alias, diagnostics)
    _apply_secret_policies(snapshot.resources, by_alias, snapshot, diagnostics)
    _apply_secret_versions(snapshot.resources, by_alias)
    return tuple(drafts[key] for key in sorted(drafts))


def _providers(snapshot: _Snapshot, diagnostics: list[Diagnostic]) -> tuple[ProviderFact, ...]:
    unique: dict[tuple[str, str, tuple[str, ...]], list[Evidence]] = {}
    for address in sorted(snapshot.resources):
        resource = snapshot.resources[address]
        if resource.type != "aws_iam_openid_connect_provider":
            continue
        url = _text(resource.values, "url")
        if url is None:
            diagnostics.append(
                warning(
                    "D-TF-UNKNOWN",
                    f"{address}: provider url is unknown",
                    file=resource.file,
                    line=resource.line,
                )
            )
            continue
        try:
            host = urlsplit(url).hostname or url
        except ValueError:
            diagnostics.append(
                warning(
                    "D-TF-UNKNOWN",
                    f"{address}: provider url is malformed",
                    file=resource.file,
                    line=resource.line,
                )
            )
            continue
        client_ids = _text_tuple(resource.values, "client_id_list")
        key = (host.lower(), url, client_ids)
        unique.setdefault(key, []).append(
            _evidence_for(resource, "TF.oidc_provider", f"OIDC provider {host}")
        )
    return tuple(
        ProviderFact(
            host=host,
            url=url,
            client_ids=client_ids,
            evidence=_sorted_evidence(evidence),
        )
        for (host, url, client_ids), evidence in sorted(unique.items())
    )


def _db_targets(
    snapshot: _Snapshot, config: Config, diagnostics: list[Diagnostic]
) -> tuple[ExternalTargetFact, ...]:
    targets: dict[str, ExternalTargetFact] = {}
    for address in sorted(snapshot.resources):
        resource = snapshot.resources[address]
        if resource.type != "aws_db_instance":
            continue
        identifier = _text(resource.values, "identifier") or resource.name
        label = f"database:{identifier}"
        evidence = [_evidence_for(resource, "TF.db_instance", f"database {identifier}")]
        credential_refs = tuple(sorted(_master_user_secret_refs(resource.values)))
        bound = bool(resource.values.get("master_user_secret")) or (
            resource.values.get("manage_master_user_password") is True
        )
        if not bound:
            bound = _db_bound_by_config(config, address, identifier)
            if bound:
                evidence.append(
                    Evidence(
                        cls=EvidenceClass.DECLARED,
                        rule="CONFIG.credential-binding",
                        file=config.path,
                        detail=f"a stored credential is bound to {address}",
                    )
                )
        if not bound:
            diagnostics.append(
                warning(
                    "D-TF-DB-UNBOUND",
                    f"{address}: no master credential is bound to database {identifier}",
                    file=resource.file,
                    line=resource.line,
                )
            )
        targets[label] = ExternalTargetFact(
            label=label,
            kind="database",
            address=resource.address,
            credential_refs=credential_refs,
            evidence=_sorted_evidence(evidence),
        )
    return tuple(targets[label] for label in sorted(targets))


def _master_user_secret_refs(values: Mapping[str, Any]) -> set[str]:
    raw = values.get("master_user_secret")
    entries: tuple[Any, ...]
    if isinstance(raw, Mapping):
        entries = (raw,)
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        entries = tuple(raw)
    else:
        entries = ()
    refs: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        for key in ("secret_arn", "arn"):
            value = entry.get(key)
            if isinstance(value, str) and value.strip():
                refs.add(value.strip())
    return refs


def _db_bound_by_config(config: Config, address: str, identifier: str) -> bool:
    candidates = {address, f"{address}.id", f"{address}.arn", identifier}
    return any(value.strip() in candidates for value in config.credential_bindings.values())


def _arn_identity(arn: str) -> tuple[str | None, str | None]:
    parts = arn.split(":")
    if len(parts) < 6 or parts[0] != "arn":
        return None, None
    return (parts[3] or None, parts[4] or None)


def _policy_context(
    config: Config,
    by_arn: Mapping[str, tuple[Statement, ...]],
    roles: Iterable[RoleFact],
    sinks_facts: Iterable[SinkFact],
) -> PolicyContext:
    accounts: set[str] = set()
    regions: set[str] = set()
    for arn in (
        *[role.arn for role in roles if role.arn],
        *[sink.arn for sink in sinks_facts if sink.arn],
        *sorted(by_arn),
    ):
        region, account = _arn_identity(arn)
        if region:
            regions.add(region)
        if account:
            accounts.add(account)
    return PolicyContext(
        account=config.aws_account or (sorted(accounts)[0] if accounts else None),
        region=config.aws_region or (sorted(regions)[0] if regions else None),
        managed_policies={arn: by_arn[arn] for arn in sorted(by_arn)},
    )


def resolve_cloud_facts(
    models: Sequence[TfModelFact],
    iam_documents: Sequence[IamDocumentFact],
    *,
    config: Config,
) -> CloudFacts:
    """Assemble role, sink, provider and external facts from parsed inputs."""
    diagnostics: list[Diagnostic] = []
    snapshot = _collect(models)
    by_alias, by_arn = _policy_bodies(snapshot, diagnostics)
    drafts: dict[str, _RoleDraft] = {}
    for address in sorted(snapshot.resources):
        resource = snapshot.resources[address]
        if resource.type != "aws_iam_role":
            continue
        draft = _create_role_draft(resource, snapshot, by_alias, diagnostics)
        drafts[_draft_key(draft)] = draft
    role_aliases = _role_alias_map(drafts)
    _apply_role_attachments(snapshot.resources, role_aliases, snapshot, by_alias, diagnostics)
    _report_missing_policy_bodies(drafts.values(), by_arn, diagnostics)
    _resolve_boundaries(drafts.values(), by_alias, by_arn, diagnostics)
    _apply_iam_documents(drafts, role_aliases, iam_documents, diagnostics)
    roles = _finalise_roles(drafts.values())
    sink_drafts = _collect_sinks(snapshot, diagnostics)
    sinks_facts = _merge_sinks({draft.id: draft for draft in sink_drafts})
    providers = _providers(snapshot, diagnostics)
    externals = _db_targets(snapshot, config, diagnostics)
    context = _policy_context(config, by_arn, roles, sinks_facts)
    return CloudFacts(
        roles=roles,
        sinks=sinks_facts,
        providers=providers,
        externals=externals,
        policy_context=context,
        diagnostics=DiagnosticBag(diagnostics).sorted(),
    )
