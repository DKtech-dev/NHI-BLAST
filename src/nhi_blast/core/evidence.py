"""Evidence classes and provenance.

The ordering DECLARED > DERIVED > ASSUMED > UNKNOWN is normative (spec 3.2): an
edge's confidence is the weakest class among its evidence, and UNKNOWN-class edges
never contribute to R, E or Z. Evidence text must never contain a credential value
(spec 2.5); callers pass metadata only.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class EvidenceClass(StrEnum):
    DECLARED = "declared"
    DERIVED = "derived"
    ASSUMED = "assumed"
    UNKNOWN = "unknown"


_RANK: dict[EvidenceClass, int] = {
    EvidenceClass.DECLARED: 0,
    EvidenceClass.DERIVED: 1,
    EvidenceClass.ASSUMED: 2,
    EvidenceClass.UNKNOWN: 3,
}


def rank(cls: EvidenceClass) -> int:
    """Lower is stronger; 0 is DECLARED."""
    return _RANK[cls]


def weakest(*classes: EvidenceClass) -> EvidenceClass:
    """Return the weakest class; at least one class is required."""
    if not classes:
        msg = "weakest() requires at least one evidence class"
        raise ValueError(msg)
    return max(classes, key=rank)


def weakest_of(classes: Iterable[EvidenceClass]) -> EvidenceClass:
    materialised = tuple(classes)
    if not materialised:
        msg = "weakest_of() requires at least one evidence class"
        raise ValueError(msg)
    return weakest(*materialised)


def is_authority(cls: EvidenceClass) -> bool:
    """True for classes that may carry confirmed authority (spec 4.4)."""
    return cls is not EvidenceClass.UNKNOWN


class Evidence(BaseModel):
    """One provenance record attached to a node or edge.

    rule names the evaluation rule or registry entry that produced the claim, for
    example GHA.permissions, R9 or A-STS-TTL.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    cls: EvidenceClass
    rule: str
    file: str | None = None
    line: int | None = None
    end_line: int | None = None
    detail: str = ""

    @property
    def key(self) -> str:
        """Stable sort key, also used when hashing edge identifiers."""
        return "|".join(
            (
                self.cls.value,
                self.rule,
                self.file or "",
                "" if self.line is None else str(self.line),
                "" if self.end_line is None else str(self.end_line),
                self.detail,
            )
        )

    def location(self) -> str:
        """Human location such as .github/workflows/release.yml:14."""
        if self.file is None:
            return "assumption registry" if self.cls is EvidenceClass.ASSUMED else "unknown"
        if self.line is None:
            return self.file
        return f"{self.file}:{self.line}"


def dedupe_evidence(items: Iterable[Evidence]) -> tuple[Evidence, ...]:
    """Preserve insertion order, drop exact duplicates by fingerprint."""
    seen: dict[str, Evidence] = {}
    for item in items:
        seen.setdefault(item.key, item)
    return tuple(seen.values())


def evidence_sort_key(ev: Evidence) -> tuple[int, str, str, int, int, str]:
    return (
        rank(ev.cls),
        ev.file or "",
        ev.rule,
        ev.line if ev.line is not None else 0,
        ev.end_line if ev.end_line is not None else 0,
        ev.detail,
    )
