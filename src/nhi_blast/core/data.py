"""Typed accessors for the platform data files (spec 5.7).

Facts that change with the platforms live in YAML under nhi_blast/data, never in
code. Each file carries source_url and verified_on so reports can show provenance.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from typing import Any

import yaml

from nhi_blast.core.models import CredentialKind, DataFileInfo, Severity, SinkType

DATA_PACKAGE = "nhi_blast.data"


class DataFileError(RuntimeError):
    """A packaged data file is missing or shaped unexpectedly."""


@dataclass(frozen=True, slots=True)
class _Document:
    name: str
    payload: Mapping[str, Any]

    @property
    def source_url(self) -> str:
        return str(self.payload.get("source_url", ""))

    @property
    def verified_on(self) -> str:
        return str(self.payload.get("verified_on", ""))


def _read_document(name: str) -> _Document:
    path = resources.files(DATA_PACKAGE).joinpath(name)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        msg = f"packaged data file missing: {name}"
        raise DataFileError(msg) from exc
    payload = yaml.safe_load(text)
    if not isinstance(payload, dict):
        msg = f"packaged data file is not a mapping: {name}"
        raise DataFileError(msg)
    return _Document(name=name, payload=payload)


# ---------------------------------------------------------------- assumptions


@dataclass(frozen=True, slots=True)
class Assumption:
    id: str
    kind: str
    statement: str
    verify: bool
    impact: str


class AssumptionRegistry:
    def __init__(self, document: _Document) -> None:
        entries = document.payload.get("entries", [])
        if not isinstance(entries, list):
            msg = "assumptions.yaml: entries must be a list"
            raise DataFileError(msg)
        parsed: dict[str, Assumption] = {}
        for raw in entries:
            if not isinstance(raw, dict):
                continue
            assumption = Assumption(
                id=str(raw["id"]),
                kind=str(raw.get("kind", "assumption")),
                statement=str(raw.get("statement", "")).strip(),
                verify=bool(raw.get("verify", False)),
                impact=str(raw.get("impact", "")).strip(),
            )
            parsed[assumption.id] = assumption
        self._entries = parsed
        self._meta = document

    @property
    def info(self) -> DataFileInfo:
        return DataFileInfo(
            name="assumptions.yaml",
            verified_on=self._meta.verified_on,
            source_url=self._meta.source_url,
            entry_count=len(self._entries),
        )

    def get(self, assumption_id: str) -> Assumption:
        try:
            return self._entries[assumption_id]
        except KeyError:
            msg = f"unknown assumption id: {assumption_id}"
            raise DataFileError(msg) from None

    def statement(self, assumption_id: str) -> str:
        return self.get(assumption_id).statement

    def is_verify(self, assumption_id: str) -> bool:
        return self.get(assumption_id).verify

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._entries))

    def all(self) -> tuple[Assumption, ...]:
        return tuple(self._entries[key] for key in sorted(self._entries))


@functools.cache
def assumptions() -> AssumptionRegistry:
    return AssumptionRegistry(_read_document("assumptions.yaml"))


# --------------------------------------------------------------- rules catalog


@dataclass(frozen=True, slots=True)
class RuleDefinition:
    id: str
    title: str
    base_severity: Severity
    short_description: str
    full_description: str
    help: str
    tags: tuple[str, ...]
    precision: str
    doc: str
    severity_note: str


class RuleCatalog:
    def __init__(self, document: _Document) -> None:
        raw_rules = document.payload.get("rules", [])
        if not isinstance(raw_rules, list):
            msg = "rules.yaml: rules must be a list"
            raise DataFileError(msg)
        parsed: dict[str, RuleDefinition] = {}
        for raw in raw_rules:
            if not isinstance(raw, dict):
                continue
            rule = RuleDefinition(
                id=str(raw["id"]),
                title=str(raw.get("title", "")),
                base_severity=Severity(str(raw["base_severity"]).upper()),
                short_description=str(raw.get("short_description", "")).strip(),
                full_description=str(raw.get("full_description", "")).strip(),
                help=str(raw.get("help", "")).strip(),
                tags=tuple(str(tag) for tag in raw.get("tags", ())),
                precision=str(raw.get("precision", "medium")),
                doc=str(raw.get("doc", "")),
                severity_note=str(raw.get("severity_note", "")).strip(),
            )
            parsed[rule.id] = rule
        self._rules = parsed
        self._meta = document

    @property
    def info(self) -> DataFileInfo:
        return DataFileInfo(
            name="rules.yaml",
            verified_on=self._meta.verified_on,
            source_url=self._meta.source_url,
            entry_count=len(self._rules),
        )

    def get(self, rule_id: str) -> RuleDefinition:
        try:
            return self._rules[rule_id]
        except KeyError:
            msg = f"unknown rule id: {rule_id}"
            raise DataFileError(msg) from None

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._rules))

    def all(self) -> tuple[RuleDefinition, ...]:
        return tuple(self._rules[key] for key in sorted(self._rules))


@functools.cache
def rules() -> RuleCatalog:
    return RuleCatalog(_read_document("rules.yaml"))


# ---------------------------------------------------------- condition keys


@dataclass(frozen=True, slots=True)
class ConditionKeyRegistry:
    info: DataFileInfo
    provider_host: str
    supported: frozenset[str]
    not_documented: frozenset[str]
    not_statically_fixable: frozenset[str]
    required_control_any_of: tuple[str, ...]

    def is_supported(self, key: str) -> bool:
        return key in self.supported

    def is_documented_dead(self, key: str) -> bool:
        return key in self.not_documented


@functools.cache
def condition_keys() -> ConditionKeyRegistry:
    document = _read_document("aws_github_condition_keys.yaml")
    payload = document.payload
    return ConditionKeyRegistry(
        info=DataFileInfo(
            name="aws_github_condition_keys.yaml",
            verified_on=document.verified_on,
            source_url=document.source_url,
            entry_count=len(payload.get("supported", ())),
        ),
        provider_host=str(payload.get("provider_host", "token.actions.githubusercontent.com")),
        supported=frozenset(payload.get("supported", ())),
        not_documented=frozenset(payload.get("not_documented", ())),
        not_statically_fixable=frozenset(payload.get("not_statically_fixable", ())),
        required_control_any_of=tuple(payload.get("required_control_any_of", ())),
    )


# --------------------------------------------------------------- sink catalog


@dataclass(frozen=True, slots=True)
class SinkTypeSpec:
    sink_type: SinkType
    value_read_actions: tuple[str, ...]
    modify_actions: tuple[str, ...]
    arn_pattern: str
    credential_bearing_types: tuple[str, ...]
    default_kms_alias: str | None


class SinksCatalog:
    def __init__(self, document: _Document) -> None:
        self._specs: dict[SinkType, SinkTypeSpec] = {}
        for sink_type in SinkType:
            raw = document.payload.get(sink_type.value)
            if not isinstance(raw, dict):
                msg = f"sinks_catalog.yaml: missing section {sink_type.value}"
                raise DataFileError(msg)
            self._specs[sink_type] = SinkTypeSpec(
                sink_type=sink_type,
                value_read_actions=tuple(str(a) for a in raw.get("value_read_actions", ())),
                modify_actions=tuple(str(a) for a in raw.get("modify_actions", ())),
                arn_pattern=str(raw.get("arn_pattern", "")),
                credential_bearing_types=tuple(
                    str(t) for t in raw.get("credential_bearing_types", ())
                ),
                default_kms_alias=(
                    None if raw.get("default_kms_alias") is None else str(raw["default_kms_alias"])
                ),
            )
        self._meta = document

    @property
    def info(self) -> DataFileInfo:
        return DataFileInfo(
            name="sinks_catalog.yaml",
            verified_on=self._meta.verified_on,
            source_url=self._meta.source_url,
            entry_count=len(self._specs),
        )

    def spec(self, sink_type: SinkType) -> SinkTypeSpec:
        return self._specs[sink_type]

    def arn(
        self, sink_type: SinkType, *, name: str, region: str | None, account: str | None
    ) -> str:
        """Build the ARN glob used when comparing policy resources (spec 9.6)."""
        spec = self.spec(sink_type)
        return spec.arn_pattern.format(
            region=region or "*",
            account=account or "*",
            name=name,
            name_without_leading_slash=name.lstrip("/"),
        )


@functools.cache
def sinks() -> SinksCatalog:
    return SinksCatalog(_read_document("sinks_catalog.yaml"))


# ------------------------------------------------------- credential heuristics


@dataclass(frozen=True, slots=True)
class LiteralPattern:
    id: str
    kind: CredentialKind
    pattern: str
    boundary: str


@dataclass(frozen=True, slots=True)
class SecretNameRule:
    id: str
    kind: CredentialKind
    criticality: int
    rotation_hint: str
    regex: re.Pattern[str]


class CredentialHeuristics:
    def __init__(self, document: _Document) -> None:
        payload = document.payload
        self._literal_patterns: tuple[LiteralPattern, ...] = tuple(
            LiteralPattern(
                id=str(raw["id"]),
                kind=CredentialKind(str(raw["kind"])),
                pattern=str(raw["pattern"]),
                boundary=str(raw.get("boundary", "none")),
            )
            for raw in payload.get("literal_credentials", ())
        )
        rules: list[SecretNameRule] = []
        for raw in payload.get("secret_name_rules", ()):
            rules.append(
                SecretNameRule(
                    id=str(raw["id"]),
                    kind=CredentialKind(str(raw["kind"])),
                    criticality=int(raw["criticality"]),
                    rotation_hint=str(raw.get("rotation_hint", "")),
                    regex=re.compile(str(raw["pattern"]), re.IGNORECASE),
                )
            )
        self._secret_name_rules = tuple(rules)
        self._default_kind_by_sink = {
            SinkType(str(key)): CredentialKind(str(value))
            for key, value in payload.get("default_kind_by_sink", {}).items()
        }
        self._default_criticality = {
            CredentialKind(str(key)): int(value)
            for key, value in payload.get("default_criticality", {}).items()
        }
        self._meta = document

    @property
    def info(self) -> DataFileInfo:
        return DataFileInfo(
            name="credential_heuristics.yaml",
            verified_on=self._meta.verified_on,
            source_url=self._meta.source_url,
            entry_count=len(self._literal_patterns) + len(self._secret_name_rules),
        )

    def literal_patterns(self) -> tuple[LiteralPattern, ...]:
        return self._literal_patterns

    def criticality(self, kind: CredentialKind) -> int:
        return self._default_criticality.get(kind, 0)

    def classify_label(self, label: str) -> tuple[CredentialKind, int]:
        """Classify a GitHub secret or workflow label (H-SECRET-NAME)."""
        for rule in self._secret_name_rules:
            if rule.regex.search(label):
                return rule.kind, rule.criticality
        return CredentialKind.GENERIC_SECRET, self.criticality(CredentialKind.GENERIC_SECRET)

    def classify_sink(
        self,
        name: str,
        sink_type: SinkType,
        *,
        parameter_type: str | None = None,
        credential_bearing_types: tuple[str, ...] = (),
    ) -> tuple[CredentialKind | None, int]:
        """Infer whether a store holds a credential and which kind (H-SECRET-NAME)."""
        if sink_type is SinkType.SSM_PARAMETER and (
            parameter_type is None or parameter_type not in credential_bearing_types
        ):
            return None, 0
        for rule in self._secret_name_rules:
            if rule.regex.search(name):
                return rule.kind, rule.criticality
        default_kind = self._default_kind_by_sink.get(sink_type)
        if default_kind is None:
            return None, 0
        return default_kind, self.criticality(default_kind)


@functools.cache
def credential_heuristics() -> CredentialHeuristics:
    return CredentialHeuristics(_read_document("credential_heuristics.yaml"))


# ------------------------------------------------------------ rotation hints


class RotationHints:
    def __init__(self, document: _Document) -> None:
        payload = document.payload
        self._hints = {
            CredentialKind(str(key)): str(value).strip()
            for key, value in (payload.get("hints") or {}).items()
        }
        self._notes = {
            str(key): str(value).strip() for key, value in (payload.get("notes") or {}).items()
        }
        verify_actions = payload.get("verify_actions") or {}
        self._verify_default = str(verify_actions.get("default", "")).strip()
        self._meta = document

    @property
    def info(self) -> DataFileInfo:
        return DataFileInfo(
            name="rotation_hints.yaml",
            verified_on=self._meta.verified_on,
            source_url=self._meta.source_url,
            entry_count=len(self._hints),
        )

    def hint(self, kind: CredentialKind) -> str:
        return self._hints.get(kind, "")

    def note(self, name: str) -> str:
        return self._notes.get(name, "")

    def verify_default(self) -> str:
        return self._verify_default


@functools.cache
def rotation_hints() -> RotationHints:
    return RotationHints(_read_document("rotation_hints.yaml"))


# --------------------------------------------------------- trigger profiles


@dataclass(frozen=True, slots=True)
class TriggerProfile:
    event: str
    attacker: str
    candidate: str
    fork_without_credentials: bool
    pr_code_untrusted: bool
    note: str


class TriggerProfiles:
    def __init__(self, document: _Document) -> None:
        raw = document.payload.get("profiles", {})
        if not isinstance(raw, dict):
            msg = "trigger_profiles.yaml: profiles must be a mapping"
            raise DataFileError(msg)
        self._profiles: dict[str, TriggerProfile] = {}
        for event, entry in raw.items():
            if not isinstance(entry, dict):
                continue
            self._profiles[str(event)] = TriggerProfile(
                event=str(event),
                attacker=str(entry.get("attacker", "unknown")),
                candidate=str(entry.get("candidate", "ref")),
                fork_without_credentials=bool(entry.get("fork_without_credentials", False)),
                pr_code_untrusted=bool(entry.get("pr_code_untrusted", False)),
                note=str(entry.get("note", "")),
            )
        self._meta = document

    @property
    def info(self) -> DataFileInfo:
        return DataFileInfo(
            name="trigger_profiles.yaml",
            verified_on=self._meta.verified_on,
            source_url=self._meta.source_url,
            entry_count=len(self._profiles),
        )

    def known(self, event: str) -> bool:
        return event in self._profiles

    def profile(self, event: str) -> TriggerProfile:
        """Unknown events fail closed: any-ref candidates with unknown attacker."""
        if event in self._profiles:
            return self._profiles[event]
        return TriggerProfile(
            event=event,
            attacker="unknown",
            candidate="all_refs",
            fork_without_credentials=False,
            pr_code_untrusted=False,
            note="event not present in trigger_profiles.yaml; treated as arbitrary ref",
        )


@functools.cache
def trigger_profiles() -> TriggerProfiles:
    return TriggerProfiles(_read_document("trigger_profiles.yaml"))


@dataclass(frozen=True, slots=True)
class PermissionScopes:
    info: DataFileInfo
    scopes: tuple[str, ...]
    read_all: str
    write_all: str


@functools.cache
def permission_scopes() -> PermissionScopes:
    document = _read_document("permission_scopes.yaml")
    return PermissionScopes(
        info=DataFileInfo(
            name="permission_scopes.yaml",
            verified_on=document.verified_on,
            source_url=document.source_url,
            entry_count=len(document.payload.get("scopes", ())),
        ),
        scopes=tuple(str(scope) for scope in document.payload.get("scopes", ())),
        read_all=str(document.payload.get("read_all", "read")),
        write_all=str(document.payload.get("write_all", "write")),
    )


def all_data_file_infos() -> tuple[DataFileInfo, ...]:
    infos = [
        assumptions().info,
        condition_keys().info,
        sinks().info,
        credential_heuristics().info,
        rotation_hints().info,
        trigger_profiles().info,
        permission_scopes().info,
        rules().info,
    ]
    return tuple(sorted(infos, key=lambda info: info.name))
