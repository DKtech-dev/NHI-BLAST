"""Configuration file (nhi-blast.toml) handling (spec 14.3).

The file supplies repository identity, AWS identity, role and credential bindings,
an optional custom OIDC subject template, ignores and limit overrides. Unknown keys
are rejected so a typo cannot silently change behaviour.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from nhi_blast.core.limits import Limits

CONFIG_FILENAME = "nhi-blast.toml"
_TOP_LEVEL_KEYS = frozenset(
    {
        "repo_slug",
        "default_branch",
        "aws_account",
        "aws_region",
        "bindings",
        "oidc",
        "ignore",
        "limits",
    }
)
_SUB_TEMPLATE_KEYS = frozenset({"repo", "context"})


class ConfigError(ValueError):
    """Invalid configuration file; the CLI turns this into a usage error."""


@dataclass(frozen=True, slots=True)
class Config:
    path: str | None = None
    repo_slug: str | None = None
    default_branch: str = "main"
    aws_account: str | None = None
    aws_region: str | None = None
    role_bindings: Mapping[str, str] = field(default_factory=dict)
    credential_bindings: Mapping[str, str] = field(default_factory=dict)
    sub_template: tuple[str, ...] | None = None
    ignore_rules: tuple[str, ...] = ()
    ignore_paths: tuple[str, ...] = ()
    limits_overrides: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> Config:
        return cls()

    @classmethod
    def from_file(cls, path: Path) -> Config:
        try:
            raw_bytes = path.read_bytes()
        except OSError as exc:
            msg = f"cannot read config file {path}: {exc}"
            raise ConfigError(msg) from exc
        try:
            data = tomllib.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            msg = f"invalid config file {path}: {exc}"
            raise ConfigError(msg) from exc
        return cls.from_mapping(data, path=str(path))

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, path: str | None = None) -> Config:
        unknown = set(data) - _TOP_LEVEL_KEYS
        if unknown:
            msg = f"unknown config key(s): {', '.join(sorted(unknown))}"
            raise ConfigError(msg)

        bindings = data.get("bindings", {}) or {}
        if not isinstance(bindings, dict):
            msg = "config: [bindings] must be a table"
            raise ConfigError(msg)
        unknown_bindings = set(bindings) - {"roles", "credentials"}
        if unknown_bindings:
            msg = f"unknown config binding(s): {', '.join(sorted(unknown_bindings))}"
            raise ConfigError(msg)

        oidc = data.get("oidc", {}) or {}
        if not isinstance(oidc, dict):
            msg = "config: [oidc] must be a table"
            raise ConfigError(msg)
        unknown_oidc = set(oidc) - {"sub_template"}
        if unknown_oidc:
            msg = f"unknown config key(s) under [oidc]: {', '.join(sorted(unknown_oidc))}"
            raise ConfigError(msg)
        sub_template = cls._parse_sub_template(oidc.get("sub_template"))

        ignore = data.get("ignore", {}) or {}
        if not isinstance(ignore, dict):
            msg = "config: [ignore] must be a table"
            raise ConfigError(msg)
        unknown_ignore = set(ignore) - {"rules", "paths"}
        if unknown_ignore:
            msg = f"unknown config key(s) under [ignore]: {', '.join(sorted(unknown_ignore))}"
            raise ConfigError(msg)

        limits_raw = data.get("limits", {}) or {}
        if not isinstance(limits_raw, dict):
            msg = "config: [limits] must be a table"
            raise ConfigError(msg)
        try:
            Limits.from_mapping(limits_raw)
        except (TypeError, ValueError) as exc:
            msg = f"config: {exc}"
            raise ConfigError(msg) from exc

        return cls(
            path=path,
            repo_slug=cls._opt_str(data, "repo_slug"),
            default_branch=cls._opt_str(data, "default_branch") or "main",
            aws_account=cls._opt_str(data, "aws_account"),
            aws_region=cls._opt_str(data, "aws_region"),
            role_bindings=cls._parse_str_map(bindings.get("roles"), "[bindings.roles]"),
            credential_bindings=cls._parse_str_map(
                bindings.get("credentials"), "[bindings.credentials]"
            ),
            sub_template=sub_template,
            ignore_rules=cls._parse_str_list(ignore.get("rules"), "[ignore].rules"),
            ignore_paths=cls._parse_str_list(ignore.get("paths"), "[ignore].paths"),
            limits_overrides=dict(limits_raw),
        )

    def limits(self) -> Limits:
        base = Limits()
        return replace(base, **dict(self.limits_overrides))

    def with_identity(
        self,
        *,
        repo_slug: str | None = None,
        default_branch: str | None = None,
        aws_account: str | None = None,
        aws_region: str | None = None,
    ) -> Config:
        return replace(
            self,
            repo_slug=repo_slug or self.repo_slug,
            default_branch=default_branch or self.default_branch,
            aws_account=aws_account or self.aws_account,
            aws_region=aws_region or self.aws_region,
        )

    def role_binding(self, key: str) -> str | None:
        return self.role_bindings.get(key)

    def credential_binding(self, key: str) -> str | None:
        return self.credential_bindings.get(key)

    @staticmethod
    def _opt_str(data: Mapping[str, Any], key: str) -> str | None:
        value = data.get(key)
        if value is None:
            return None
        if not isinstance(value, str):
            msg = f"config: {key} must be a string"
            raise ConfigError(msg)
        return value

    @staticmethod
    def _parse_str_map(value: Any, section: str) -> dict[str, str]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            msg = f"config: {section} must be a table of strings"
            raise ConfigError(msg)
        parsed: dict[str, str] = {}
        for key, item in value.items():
            if not isinstance(item, str):
                msg = f"config: {section}.{key} must be a string"
                raise ConfigError(msg)
            parsed[str(key)] = item
        return parsed

    @staticmethod
    def _parse_str_list(value: Any, section: str) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            msg = f"config: {section} must be a list of strings"
            raise ConfigError(msg)
        return tuple(value)

    @classmethod
    def _parse_sub_template(cls, value: Any) -> tuple[str, ...] | None:
        if value is None:
            return None
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            msg = "config: [oidc].sub_template must be a list of strings"
            raise ConfigError(msg)
        template = tuple(value)
        unknown = set(template) - _SUB_TEMPLATE_KEYS
        if unknown:
            msg = f"config: [oidc].sub_template has unknown key(s): {', '.join(sorted(unknown))}"
            raise ConfigError(msg)
        if not template:
            msg = "config: [oidc].sub_template must not be empty"
            raise ConfigError(msg)
        return template
