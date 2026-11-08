"""Command core: load, guard, compute and stage outputs before promotion.

Promotion failure triggers rollback; incomplete recovery or post-commit cleanup is
reported explicitly rather than implying that no outputs were written.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from nhi_blast.core.artifact_io import ArtifactCleanupError, ArtifactOutputError, write_artifacts
from nhi_blast.report.loader import ReportLoadError, load_report_with_identity
from nhi_blast.whatif.engine import WhatIfAbort, run_whatif
from nhi_blast.whatif.plan import PLAN_INVALID, PlanError, load_plan_with_identity
from nhi_blast.whatif.playbook import render_playbook
from nhi_blast.whatif.render import console_summary, whatif_json
from nhi_blast.whatif.sessions import TimestampError

USAGE = "D-WHATIF-USAGE"
OUTPUT = "D-WHATIF-OUTPUT"
FORMATS = ("json", "md")


@dataclass(frozen=True, slots=True)
class WhatIfOutcome:
    console_text: str
    written: tuple[Path, ...]


def normalise_formats(formats: Sequence[str]) -> tuple[str, ...]:
    chosen: list[str] = []
    for raw in formats or ("json", "md"):
        value = raw.strip().lower()
        if value not in FORMATS:
            msg = f"unsupported whatif format {raw!r}; use json or md"
            raise WhatIfAbort(USAGE, msg)
        if value not in chosen:
            chosen.append(value)
    return tuple(chosen)


def execute(
    report_path: Path, plan_path: Path, formats: Sequence[str], out_dir: Path
) -> WhatIfOutcome:
    chosen = normalise_formats(formats)
    try:
        report, report_identity = load_report_with_identity(report_path)
    except ReportLoadError as exc:
        raise WhatIfAbort(USAGE, str(exc)) from None
    try:
        plan, plan_identity = load_plan_with_identity(plan_path)
    except PlanError as exc:
        raise WhatIfAbort(PLAN_INVALID, str(exc)) from None
    try:
        payload = run_whatif(report, plan)
        texts = {
            "json": ("whatif.json", whatif_json(payload)),
            "md": ("playbook.md", render_playbook(report, payload)),
        }
        console = console_summary(payload)
        artifacts = [(out_dir / texts[name][0], texts[name][1].encode("utf-8")) for name in chosen]
        written = write_artifacts(artifacts, inputs=(report_identity, plan_identity))
    except TimestampError as exc:
        msg = f"invalid plan timestamp: {exc}"
        raise WhatIfAbort(PLAN_INVALID, msg) from None
    except ArtifactCleanupError as exc:
        raise WhatIfAbort(OUTPUT, str(exc)) from None
    except (OSError, ValueError) as exc:
        detail = str(exc) if isinstance(exc, ArtifactOutputError) else "render or write failed"
        msg = f"cannot write what-if output: {detail}"
        raise WhatIfAbort(OUTPUT, msg) from None
    return WhatIfOutcome(console, written)


__all__ = ["FORMATS", "OUTPUT", "USAGE", "WhatIfOutcome", "execute", "normalise_formats"]
