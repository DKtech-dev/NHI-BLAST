"""NHI-Blast: offline, evidence-labelled NHI authority and revocation-survival analysis."""

from __future__ import annotations

__version__ = "0.3.0"
SCHEMA_VERSION = "nhi-blast-report/1.1"
READABLE_SCHEMAS = frozenset({"nhi-blast-report/1.0", SCHEMA_VERSION})
RANK_SCHEMA_VERSION = "nhi-blast-report/1.0/rank"
# Bump whenever evaluation semantics change (conditions, reachability, partitioning,
# rotation, findings). tests/golden/engine-fingerprint.json must gain a matching entry.
ENGINE_SEMANTICS = "5"
