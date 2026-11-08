"""Run a diff end to end: load, compare, apply the baseline, render and write."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from nhi_blast.core.artifact_io import (
    ArtifactCleanupError,
    ArtifactOutputError,
    InputIdentity,
    write_artifacts,
)
from nhi_blast.core.models import Report, Severity
from nhi_blast.diff.baseline import Baseline, BaselineError, apply_gate, load_baseline_with_identity
from nhi_blast.diff.compare import diff_reports
from nhi_blast.diff.render import RENDERERS, render_console, to_json_text
from nhi_blast.report._text import safe_text
from nhi_blast.report.loader import ReportLoadError, load_report_with_identity


class DiffInputError(ValueError):
    """Invalid invocation or unreadable input (CLI exit code 2)."""


class DiffOutputError(OSError):
    """An output artifact could not be written (CLI exit code 4)."""


@dataclass(frozen=True, slots=True)
class DiffOptions:
    base: Path
    head: Path
    baseline: Path | None = None
    fail_on: Severity | None = None
    formats: tuple[str, ...] = ("console",)
    out_dir: Path = Path("nhi-blast-diff-out")
    as_of: date | None = None


@dataclass(frozen=True, slots=True)
class DiffOutcome:
    payload: dict[str, object]
    exit_code: int
    console_text: str
    written: tuple[Path, ...] = field(default_factory=tuple)


def load_input(path: Path, label: str) -> Report:
    report, _identity = _load_input_with_identity(path, label)
    return report


def _load_input_with_identity(path: Path, label: str) -> tuple[Report, InputIdentity]:
    try:
        return load_report_with_identity(path)
    except ReportLoadError as exc:
        msg = f"{label}: {safe_text(exc, 400)}"
        raise DiffInputError(msg) from None
    except (RecursionError, ValueError, MemoryError):
        msg = f"{label}: report cannot be read"
        raise DiffInputError(msg) from None


def normalise_formats(values: tuple[str, ...]) -> tuple[str, ...]:
    chosen: list[str] = []
    for raw in values or ("console",):
        name = raw.strip().lower()
        if name not in RENDERERS:
            known = ", ".join(sorted(RENDERERS))
            msg = f"unsupported --format {safe_text(raw, 40)!r}; choose {known}"
            raise DiffInputError(msg)
        if name not in chosen:
            chosen.append(name)
    return tuple(chosen)


def run_diff(options: DiffOptions) -> DiffOutcome:
    formats = normalise_formats(options.formats)
    base, base_identity = _load_input_with_identity(options.base, "BASE")
    head, head_identity = _load_input_with_identity(options.head, "HEAD")
    inputs = [base_identity, head_identity]
    baseline: Baseline | None = None
    if options.baseline is not None:
        try:
            baseline, baseline_identity = load_baseline_with_identity(options.baseline)
            inputs.append(baseline_identity)
        except BaselineError as exc:
            msg = f"baseline: {safe_text(exc, 400)}"
            raise DiffInputError(msg) from None
    payload = apply_gate(
        diff_reports(base, head), baseline, fail_on=options.fail_on, as_of=options.as_of
    )
    artifacts: list[tuple[Path, bytes]] = []
    try:
        for name in formats:
            if name == "console":
                continue
            renderer = RENDERERS[name]
            target = options.out_dir / f"diff.{renderer.extension}"
            artifacts.append((target, renderer.render(payload).encode("utf-8")))
        console = render_console(payload) if "console" in formats else ""
        written = write_artifacts(artifacts, inputs=inputs)
    except ArtifactCleanupError as exc:
        raise DiffOutputError(str(exc)) from None
    except (OSError, ValueError) as exc:
        detail = str(exc) if isinstance(exc, ArtifactOutputError) else "render or write failed"
        msg = f"cannot write diff output: {detail}"
        raise DiffOutputError(msg) from None
    return DiffOutcome(
        payload=payload,
        exit_code=int(payload["gate"]["exit_code"]),
        console_text=console,
        written=tuple(written),
    )


__all__ = [
    "DiffInputError",
    "DiffOptions",
    "DiffOutcome",
    "DiffOutputError",
    "load_input",
    "normalise_formats",
    "run_diff",
    "to_json_text",
]
