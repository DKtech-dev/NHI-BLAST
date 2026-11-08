"""Logical finding keys, deterministic pairing and graph keys.

The key is line-insensitive: node ids are semantic and only the primary evidence *file*
(not its line) enters the hash. Findings are never paired across rule or scenario because
both are part of the key.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from nhi_blast.analysis.findings import SCENARIO_RULES
from nhi_blast.core.canonical import digest_of
from nhi_blast.core.evidence import Evidence, dedupe_evidence, evidence_sort_key
from nhi_blast.core.models import Edge, Finding, Node

_LINE_KEYS = frozenset({"line", "end_line", "lines", "start_line"})
_FILE_LINE = re.compile(r"(\.(?:ya?ml|json|tf|tfstate|hcl|toml)):\d+(?:-\d+)?")


def _ordered(evidence: Iterable[Evidence]) -> tuple[Evidence, ...]:
    return tuple(sorted(dedupe_evidence(evidence), key=evidence_sort_key))


def primary_evidence(finding: Finding) -> Evidence | None:
    for item in _ordered(finding.evidence):
        if item.file:
            return item
    return None


def primary_file(finding: Finding) -> str:
    item = primary_evidence(finding)
    return "" if item is None or item.file is None else item.file


def key_scenario(finding: Finding) -> str:
    """Scenario component of the key.

    Only the scenario-bound rules belong to one scenario's partition. For every other rule the
    `scenario` field records which scenario happened to reach the finding first, so a still-present
    finding would otherwise look resolved plus new when that attribution moves.
    """
    return (finding.scenario or "") if finding.rule in SCENARIO_RULES else ""


def finding_key(finding: Finding) -> str:
    """lk = sha256 over rule, scenario (bound rules only), sorted path ids, primary file."""
    return digest_of(
        [finding.rule, key_scenario(finding), sorted(finding.path), primary_file(finding)]
    )


def evidence_digest(evidence: Iterable[Evidence]) -> str:
    """Digest of the evidence set without line numbers, so a pure line shift is invisible."""
    entries = sorted({(e.cls.value, e.rule, e.file or "", strip_lines(e.detail)) for e in evidence})
    return digest_of([list(entry) for entry in entries])


def evidence_files(finding: Finding) -> tuple[str, ...]:
    return tuple(sorted({item.file for item in finding.evidence if item.file}))


def strip_lines(value: Any) -> Any:
    """Copy of a JSON-like value with line numbers removed (keys and `file.ext:LINE` suffixes)."""
    if isinstance(value, dict):
        return {
            k: strip_lines(v)
            for k, v in value.items()
            if k not in _LINE_KEYS and not str(k).endswith("_line")
        }
    if isinstance(value, (list, tuple)):
        return [strip_lines(item) for item in value]
    if isinstance(value, str):
        return _FILE_LINE.sub(r"\1", value)
    return value


def strip_file_paths(text: str, paths: Sequence[str]) -> str:
    """Replace every known input file path in a node id so a renamed file keeps its signature."""
    for path in sorted(set(paths), key=lambda item: (-len(item), item)):
        if path:
            text = text.replace(path, "<file>")
    return text


def path_signature(finding: Finding, paths: Sequence[str]) -> tuple[str, ...]:
    return tuple(strip_file_paths(node, paths) for node in finding.path)


@dataclass(frozen=True, slots=True)
class KeyedFinding:
    finding: Finding
    lk: str
    evidence_digest: str
    line: int

    def order(self) -> tuple[str, int, str]:
        return (self.evidence_digest, self.line, self.finding.id)


def keyed(finding: Finding) -> KeyedFinding:
    primary = primary_evidence(finding)
    line = 0 if primary is None or primary.line is None else primary.line
    return KeyedFinding(
        finding=finding,
        lk=finding_key(finding),
        evidence_digest=evidence_digest(finding.evidence),
        line=line,
    )


@dataclass(frozen=True, slots=True)
class Pairing:
    pairs: tuple[tuple[KeyedFinding, KeyedFinding], ...]
    base_unpaired: tuple[KeyedFinding, ...]
    head_unpaired: tuple[KeyedFinding, ...]
    # lks whose unpaired surplus sits next to a paired or differently sized group.
    ambiguous: frozenset[str]


def _group(items: Iterable[KeyedFinding]) -> dict[str, list[KeyedFinding]]:
    groups: dict[str, list[KeyedFinding]] = {}
    for item in items:
        groups.setdefault(item.lk, []).append(item)
    for members in groups.values():
        members.sort(key=KeyedFinding.order)
    return groups


def pair_findings(base: Iterable[Finding], head: Iterable[Finding]) -> Pairing:
    """Pair findings sharing a logical key: equal evidence digest first, then by line.

    A group whose two sides differ in size and are both non-empty has surplus findings
    that cannot be matched with confidence; they are returned unpaired and flagged.
    """
    base_groups = _group(keyed(item) for item in base)
    head_groups = _group(keyed(item) for item in head)
    pairs: list[tuple[KeyedFinding, KeyedFinding]] = []
    base_unpaired: list[KeyedFinding] = []
    head_unpaired: list[KeyedFinding] = []
    ambiguous: set[str] = set()
    for lk in sorted(set(base_groups) | set(head_groups)):
        left = list(base_groups.get(lk, ()))
        right = list(head_groups.get(lk, ()))
        if left and right and len(left) != len(right):
            ambiguous.add(lk)
        remaining_right = list(right)
        remaining_left: list[KeyedFinding] = []
        for item in left:
            match = next(
                (c for c in remaining_right if c.evidence_digest == item.evidence_digest), None
            )
            if match is None:
                remaining_left.append(item)
            else:
                remaining_right.remove(match)
                pairs.append((item, match))
        count = min(len(remaining_left), len(remaining_right))
        for index in range(count):
            pairs.append((remaining_left[index], remaining_right[index]))
        base_unpaired.extend(remaining_left[count:])
        head_unpaired.extend(remaining_right[count:])
    return Pairing(
        pairs=tuple(pairs),
        base_unpaired=tuple(base_unpaired),
        head_unpaired=tuple(head_unpaired),
        ambiguous=frozenset(ambiguous),
    )


def node_digest(node: Node) -> dict[str, str]:
    return {
        "kind": node.kind.value,
        "label": digest_of(node.label),
        "attrs": digest_of(strip_lines(node.attrs)),
        "evidence": evidence_digest(node.evidence),
    }


def edge_key(edge: Edge) -> tuple[str, str, str]:
    return (edge.kind.value, edge.src, edge.dst)


def edge_digest(edge: Edge) -> dict[str, str]:
    return {
        "lifetime": edge.lifetime.value,
        "confidence": edge.confidence.value,
        "attrs": digest_of(strip_lines(edge.attrs)),
        "evidence": evidence_digest(edge.evidence),
    }
