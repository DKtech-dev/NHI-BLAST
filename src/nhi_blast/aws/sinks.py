"""Credential-store helpers built on the sinks catalog (spec 9.5, 9.6)."""

from __future__ import annotations

from nhi_blast.core.data import sinks
from nhi_blast.core.models import SinkFact, SinkType


def read_actions(sink_type: SinkType) -> tuple[str, ...]:
    return sinks().spec(sink_type).value_read_actions


def modify_actions(sink_type: SinkType) -> tuple[str, ...]:
    return sinks().spec(sink_type).modify_actions


def default_kms_alias(sink_type: SinkType) -> str | None:
    return sinks().spec(sink_type).default_kms_alias


def candidate_arns(sink: SinkFact, *, region: str | None, account: str | None) -> tuple[str, ...]:
    """ARN globs to compare against policy resource patterns."""
    if sink.arn:
        return (sink.arn,)
    return (sinks().arn(sink.sink_type, name=sink.name, region=region, account=account),)


def uses_default_kms(sink: SinkFact) -> bool:
    alias = default_kms_alias(sink.sink_type)
    if sink.kms_key_id is None:
        return True
    return alias is not None and sink.kms_key_id == alias


def kms_key_arn(sink: SinkFact, *, region: str | None, account: str | None) -> str | None:
    if sink.kms_key_id is None or uses_default_kms(sink):
        return None
    key = sink.kms_key_id
    if key.startswith("arn:"):
        return key
    return f"arn:aws:kms:{region or '*'}:{account or '*'}:key/{key}"
