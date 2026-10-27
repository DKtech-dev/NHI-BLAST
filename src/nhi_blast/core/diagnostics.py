"""Structured diagnostics.

A diagnostic reports something the analysis could not resolve or had to limit.
Codes follow spec 5.6: D-IO-*, D-YAML-*, D-GHA-*, D-TF-*, D-IAM-*, D-EXPR-*.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class DiagnosticLevel(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


_LEVEL_RANK = {DiagnosticLevel.ERROR: 0, DiagnosticLevel.WARNING: 1, DiagnosticLevel.INFO: 2}


class Diagnostic(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    level: DiagnosticLevel
    code: str
    file: str | None = None
    line: int | None = None
    message: str = ""

    def sort_key(self) -> tuple[int, str, int, str, str]:
        return (
            _LEVEL_RANK[self.level],
            self.file or "",
            self.line if self.line is not None else 0,
            self.code,
            self.message,
        )


def error(
    code: str, message: str, *, file: str | None = None, line: int | None = None
) -> Diagnostic:
    return Diagnostic(level=DiagnosticLevel.ERROR, code=code, file=file, line=line, message=message)


def warning(
    code: str, message: str, *, file: str | None = None, line: int | None = None
) -> Diagnostic:
    return Diagnostic(
        level=DiagnosticLevel.WARNING, code=code, file=file, line=line, message=message
    )


def info(
    code: str, message: str, *, file: str | None = None, line: int | None = None
) -> Diagnostic:
    return Diagnostic(level=DiagnosticLevel.INFO, code=code, file=file, line=line, message=message)


class DiagnosticBag:
    """Collects diagnostics and answers aggregate questions deterministically."""

    def __init__(self, items: Iterable[Diagnostic] = ()) -> None:
        self._items: list[Diagnostic] = list(items)

    def add(self, item: Diagnostic) -> None:
        self._items.append(item)

    def extend(self, items: Iterable[Diagnostic]) -> None:
        self._items.extend(items)

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Diagnostic]:
        return iter(self._items)

    def has_errors(self) -> bool:
        return any(d.level is DiagnosticLevel.ERROR for d in self._items)

    def count(self, level: DiagnosticLevel) -> int:
        return sum(1 for d in self._items if d.level is level)

    def sorted(self) -> tuple[Diagnostic, ...]:
        """Deduplicated and ordered for byte-stable artifacts."""
        unique: dict[str, Diagnostic] = {}
        for item in self._items:
            unique.setdefault(
                f"{item.level.value}|{item.code}|{item.file}|{item.line}|{item.message}", item
            )
        return tuple(sorted(unique.values(), key=lambda d: d.sort_key()))
