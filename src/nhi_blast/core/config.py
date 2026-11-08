"""Configuration file (nhi-blast.toml) handling (spec 14.3).

The file supplies repository identity, AWS identity, role and credential bindings,
an optional custom OIDC subject template, ignores and limit overrides. Unknown keys
are rejected so a typo cannot silently change behaviour.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from nhi_blast.core.artifact_io import (
    ArtifactReadError,
    InputIdentity,
    identify_open_input,
    read_bounded_stream,
)
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import OidcSettings

CONFIG_FILENAME = "nhi-blast.toml"
_TOP_LEVEL_KEYS = frozenset(
    {
        "repo_slug",
        "default_branch",
        "aws_account",
        "aws_region",
        "bindings",
        "oidc",
        "github",
        "ignore",
        "limits",
    }
)
_SUB_TEMPLATE_KEYS = frozenset({"repo", "context"})
_GITHUB_KEYS = frozenset({"host", "subject_format", "owner_id", "repo_id"})
_GITHUB_HOSTS = frozenset({"github.com", "ghes"})
_SUBJECT_FORMATS = frozenset({"classic", "immutable", "unknown"})


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
    github_host: str = "github.com"
    github_subject_format: str = "unknown"
    github_owner_id: int | None = None
    github_repo_id: int | None = None

    @classmethod
    def empty(cls) -> Config:
        return cls()

    def digest(self) -> str:
        """SHA-256 over every setting that can change a result; the file path is excluded."""
        payload = {
            "repo_slug": self.repo_slug,
            "default_branch": self.default_branch,
            "aws_account": self.aws_account,
            "aws_region": self.aws_region,
            "role_bindings": dict(self.role_bindings),
            "credential_bindings": dict(self.credential_bindings),
            "sub_template": None if self.sub_template is None else list(self.sub_template),
            "ignore_rules": sorted(self.ignore_rules),
            "ignore_paths": sorted(self.ignore_paths),
            "limits": dict(self.limits_overrides),
            "github": [
                self.github_host,
                self.github_subject_format,
                self.github_owner_id,
                self.github_repo_id,
            ],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def from_file(cls, path: Path) -> Config:
        config, _identity = cls.from_file_with_identity(path)
        return config

    @classmethod
    def from_file_with_identity(cls, path: Path) -> tuple[Config, InputIdentity]:
        # A config cannot raise the cap used to read its own limit overrides.
        limit = Limits().max_yaml_policy_file_bytes
        try:
            with path.open("rb") as handle:
                identity = identify_open_input(path, handle)
                try:
                    raw_bytes = read_bounded_stream(
                        handle, limit, chunk_bytes=limit + 1, stop_at_file_end=True
                    )
                except ArtifactReadError:
                    msg = f"config file exceeds the {limit}-byte limit"
                    raise ConfigError(msg) from None
        except (OSError, ArtifactReadError):
            msg = "cannot read config file"
            raise ConfigError(msg) from None
        try:
            data = tomllib.loads(raw_bytes.decode("utf-8"))
        except (ValueError, RecursionError):
            # TOML errors can disclose keys and values, and CPython rejects very long
            # integer literals with a bare ValueError; expose only the boundary failure.
            msg = (
                "invalid config file: malformed TOML, invalid UTF-8, "
                "excessive nesting or an oversized number literal"
            )
            raise ConfigError(msg) from None
        return cls.from_mapping(data, path=str(path)), identity

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

        github = cls._parse_github(data.get("github"))

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
            github_host=github.host,
            github_subject_format=github.subject_format,
            github_owner_id=github.owner_id,
            github_repo_id=github.repo_id,
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

    def oidc_settings(self) -> OidcSettings:
        return OidcSettings(
            host=self.github_host,
            subject_format=self.github_subject_format,
            owner_id=self.github_owner_id,
            repo_id=self.github_repo_id,
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
    def _parse_github(cls, value: Any) -> OidcSettings:
        if value is None:
            return OidcSettings()
        if not isinstance(value, dict):
            msg = "config: [github] must be a table"
            raise ConfigError(msg)
        unknown = set(value) - _GITHUB_KEYS
        if unknown:
            msg = f"unknown config key(s) under [github]: {', '.join(sorted(unknown))}"
            raise ConfigError(msg)
        host = value.get("host", "github.com")
        fmt = value.get("subject_format", "unknown")
        if host not in _GITHUB_HOSTS:
            msg = "config: [github].host must be 'github.com' or 'ghes'"
            raise ConfigError(msg)
        if fmt not in _SUBJECT_FORMATS:
            msg = "config: [github].subject_format must be 'classic', 'immutable' or 'unknown'"
            raise ConfigError(msg)
        ids: dict[str, int | None] = {}
        for key in ("owner_id", "repo_id"):
            raw = value.get(key)
            if raw is not None and (isinstance(raw, bool) or not isinstance(raw, int) or raw < 1):
                msg = f"config: [github].{key} must be a positive integer"
                raise ConfigError(msg)
            ids[key] = raw
        if (ids["owner_id"] is None) != (ids["repo_id"] is None):
            msg = "config: [github].owner_id and repo_id must be given together"
            raise ConfigError(msg)
        has_ids = ids["owner_id"] is not None
        if host == "ghes" and (fmt == "immutable" or has_ids):
            msg = "config: immutable subject claims are not available on GitHub Enterprise Server"
            raise ConfigError(msg)
        if fmt == "classic" and has_ids:
            msg = "config: [github] IDs contradict subject_format = 'classic'"
            raise ConfigError(msg)
        return OidcSettings(
            host=host,
            subject_format=fmt,
            owner_id=ids["owner_id"],
            repo_id=ids["repo_id"],
        )

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
