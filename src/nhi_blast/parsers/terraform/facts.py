"""Normalised Terraform facts (spec 8.2, 8.5).

Both the plan/state JSON adapter and the HCL fallback produce these models. Values
are strings, numbers, booleans or null only; sensitive leaves are never read.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from nhi_blast.core.models import Statement, TfSource


class TfResource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str
    mode: str  # managed or data
    type: str
    name: str
    index: int | str | None = None
    values: dict[str, Any] = Field(default_factory=dict)
    unknown_fields: tuple[str, ...] = ()
    sensitive_fields: tuple[str, ...] = ()
    references: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    source: TfSource = TfSource.PLAN
    file: str = ""
    line: int | None = None


class TfPolicyDocumentFact(BaseModel):
    """A resolved data.aws_iam_policy_document JSON body."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str
    json_text: str | None = None
    unknown: bool = False
    file: str = ""
    line: int | None = None


class TfModelFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: TfSource
    file: str
    format_version: str | None = None
    terraform_version: str | None = None
    resources: dict[str, TfResource] = Field(default_factory=dict)
    policy_documents: dict[str, TfPolicyDocumentFact] = Field(default_factory=dict)
    variables: dict[str, Any] = Field(default_factory=dict)

    def sorted_resources(self) -> tuple[TfResource, ...]:
        return tuple(self.resources[address] for address in sorted(self.resources))


class IamDocumentFact(BaseModel):
    """A policy document or aws iam get-role output supplied with --iam-json."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str
    file: str
    statements: tuple[Statement, ...] = ()
    role_arn: str | None = None
    role_name: str | None = None
    assume_role_statements: tuple[Statement, ...] = ()
    path_prefix: str | None = None
