"""Normalised GitHub Actions facts (spec 7.2).

The workflow parser fills these models; nothing here performs I/O or cross-file
resolution. Line numbers are 1-based and come from YAML node marks.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from nhi_blast.core.models import CredentialKind, PermLevel, PinKind


class Trigger(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event: str
    branches: tuple[str, ...] = ()
    branches_ignore: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    tags_ignore: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    paths_ignore: tuple[str, ...] = ()
    types: tuple[str, ...] = ()
    line: int = 0

    def sort_key(self) -> tuple[str, int]:
        return (self.event, self.line)


class Perms(BaseModel):
    """A permissions block after expansion (spec 7.4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    levels: dict[str, PermLevel] = Field(default_factory=dict)
    all_read: bool = False
    all_write: bool = False
    empty: bool = False
    has_expression: bool = False
    raw: dict[str, str] = Field(default_factory=dict)
    line: int = 0


class ExprRefs(BaseModel):
    """References extracted from expression syntax without evaluating it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    secrets: tuple[str, ...] = ()
    secrets_all: bool = False
    vars: tuple[str, ...] = ()
    env: tuple[str, ...] = ()
    head_ref_use: bool = False
    custom_oidc_request: bool = False

    def merge(self, other: ExprRefs) -> ExprRefs:
        return ExprRefs(
            secrets=tuple(sorted(set(self.secrets) | set(other.secrets))),
            secrets_all=self.secrets_all or other.secrets_all,
            vars=tuple(sorted(set(self.vars) | set(other.vars))),
            env=tuple(sorted(set(self.env) | set(other.env))),
            head_ref_use=self.head_ref_use or other.head_ref_use,
            custom_oidc_request=self.custom_oidc_request or other.custom_oidc_request,
        )


class UsesRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    raw: str
    kind: str  # REMOTE, LOCAL, DOCKER
    owner: str | None = None
    repo: str | None = None
    subpath: str | None = None
    ref: str | None = None
    pin_kind: PinKind = PinKind.LOCAL
    mutable: bool = False
    first_party: bool = False
    line: int = 0


class AwsAuthUse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    role_ref_kind: str = "NONE"  # ARN, EXPR, NONE
    role_arn: str | None = None
    role_ref_name: str | None = None
    audience: str = "sts.amazonaws.com"
    static_keys: bool = False
    static_secret_refs: tuple[str, ...] = ()
    line: int = 0


class LiteralHit(BaseModel):
    """A possible literal credential. The value itself is never retained."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: CredentialKind
    line: int
    length: int
    pattern_id: str = ""


class StepFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int
    line: int
    name: str | None = None
    uses: UsesRef | None = None
    refs: ExprRefs = Field(default_factory=ExprRefs)
    literals: tuple[LiteralHit, ...] = ()
    aws_auth: AwsAuthUse | None = None
    has_run: bool = False


class JobFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    line: int
    name: str | None = None
    runs_on: tuple[str, ...] = ()
    self_hosted: bool | None = None
    permissions: Perms | None = None
    environment: str | None = None
    environment_unresolved: bool = False
    uses_workflow: UsesRef | None = None
    secrets_mode: str = "NONE"  # NONE, EXPLICIT, INHERIT
    steps: tuple[StepFact, ...] = ()
    refs: ExprRefs = Field(default_factory=ExprRefs)
    untrusted_checkout: bool = False
    untrusted_checkout_line: int | None = None
    literals: tuple[LiteralHit, ...] = ()


class WorkflowFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    name: str | None = None
    triggers: tuple[Trigger, ...] = ()
    permissions: Perms | None = None
    jobs: dict[str, JobFact] = Field(default_factory=dict)

    def trigger_events(self) -> tuple[str, ...]:
        return tuple(sorted({trigger.event for trigger in self.triggers}))


class CompositeActionFact(BaseModel):
    """A local composite action read from ./path/action.yml (spec 7.7)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    name: str | None = None
    using: str | None = None
    steps: tuple[StepFact, ...] = ()
    refs: ExprRefs = Field(default_factory=ExprRefs)
