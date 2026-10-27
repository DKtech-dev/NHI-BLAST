"""Deterministic identifiers (spec 5.5).

Node identifiers are kind-prefix + ':' + canonical key. Edge and finding
identifiers are truncated SHA-256 digests so they are stable across runs and do not
depend on wall-clock time or iteration order.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from nhi_blast.core.evidence import Evidence


def _sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def file_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_pairs(pairs: Iterable[tuple[str, str]]) -> str:
    """sha256 over sorted path/NUL/sha256 pairs; the report inputs digest."""
    joined = "\n".join(f"{path}\0{sha}" for path, sha in sorted(pairs))
    return _sha256_hex(joined)


def evidence_keys(evidence: Iterable[Evidence]) -> tuple[str, ...]:
    return tuple(sorted(ev.key for ev in evidence))


def edge_id(kind: str, src: str, dst: str, evidence: Iterable[Evidence]) -> str:
    """Edge id = sha256(kind|src|dst|sorted evidence keys)[:16] (spec 5.5)."""
    payload = "|".join((kind, src, dst, ";".join(evidence_keys(evidence))))
    return _sha256_hex(payload)[:16]


def finding_id(rule: str, nodes: Iterable[str], evidence: Iterable[Evidence]) -> str:
    """Finding id = NHB-<rule>-<sha256(rule|node ids|primary evidence)[:8]>."""
    payload = "|".join((rule, ",".join(sorted(nodes)), ";".join(evidence_keys(evidence))))
    return f"{rule}-{_sha256_hex(payload)[:8]}"


def repo_node_id(slug: str) -> str:
    return f"repo:{slug}"


def workflow_node_id(rel_path: str) -> str:
    return f"wf:{rel_path}"


def job_node_id(rel_path: str, job_id: str) -> str:
    return f"job:{rel_path}#{job_id}"


def action_node_id(owner: str, repo: str, subpath: str | None, ref: str | None) -> str:
    path = f"{owner}/{repo}" + (f"/{subpath}" if subpath else "")
    return f"action:{path}@{ref or 'unresolved'}"


def local_action_node_id(rel_path: str) -> str:
    path = rel_path[2:] if rel_path.startswith("./") else rel_path
    return f"action:{path}@local"


def credential_node_id(owner_node_id: str, label: str) -> str:
    return f"cred:{owner_node_id}:{label}"


def oidc_node_id(job_node_id_value: str, audience: str) -> str:
    return f"oidc:{job_node_id_value}:{audience}"


def provider_node_id(host: str) -> str:
    return f"aws:oidc:{host}"


def role_node_id(arn_or_address: str) -> str:
    return f"aws:role:{arn_or_address}"


_SINK_PREFIXES = {
    "secretsmanager_secret": "secret",
    "ssm_parameter": "ssm",
}


def sink_node_id(sink_type: str, name: str) -> str:
    prefix = _SINK_PREFIXES.get(sink_type, sink_type)
    return f"aws:{prefix}:{name}"


def external_node_id(label: str) -> str:
    return f"ext:{label}"
