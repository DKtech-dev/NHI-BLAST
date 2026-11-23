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
from nhi_blast.report.redaction import redact_model
from nhi_blast.report.whatif_html import render_whatif_html
from nhi_blast.whatif.engine import WhatIfAbort, run_whatif
from nhi_blast.whatif.plan import (
    PLAN_INVALID,
    PlanError,
    load_plan_with_identity,
    synthesize_auto_plan,
)
from nhi_blast.whatif.playbook import render_playbook
from nhi_blast.whatif.render import console_summary, whatif_json
from nhi_blast.whatif.sessions import TimestampError

USAGE = "D-WHATIF-USAGE"
OUTPUT = "D-WHATIF-OUTPUT"
FORMATS = ("json", "md", "html")


@dataclass(frozen=True, slots=True)
class WhatIfOutcome:
    console_text: str
    written: tuple[Path, ...]


def normalise_formats(formats: Sequence[str]) -> tuple[str, ...]:
    chosen: list[str] = []
    for raw in formats or ("json", "md"):
        value = raw.strip().lower()
        if value not in FORMATS:
            msg = f"unsupported whatif format {raw!r}; use json, md or html"
            raise WhatIfAbort(USAGE, msg)
        if value not in chosen:
            chosen.append(value)
    return tuple(chosen)


def execute(
    report_path: Path,
    plan_path: Path | None,
    formats: Sequence[str],
    out_dir: Path,
    *,
    auto_plan: bool = False,
) -> WhatIfOutcome:
    chosen = normalise_formats(formats)
    if auto_plan and plan_path is not None:
        raise WhatIfAbort(USAGE, "pass either --plan or --auto-plan, not both")
    if not auto_plan and plan_path is None:
        raise WhatIfAbort(USAGE, "provide --plan FILE or --auto-plan")
    try:
        report, report_identity = load_report_with_identity(report_path)
    except ReportLoadError as exc:
        raise WhatIfAbort(USAGE, str(exc)) from None
    report = redact_model(report)
    identities = [report_identity]
    if auto_plan:
        plan = synthesize_auto_plan(report)
    else:
        if plan_path is None:
            msg = "plan_path is required when auto_plan is False"
            raise ValueError(msg)
        try:
            plan, plan_identity = load_plan_with_identity(plan_path)
        except PlanError as exc:
            raise WhatIfAbort(PLAN_INVALID, str(exc)) from None
        identities.append(plan_identity)
    try:
        payload = run_whatif(report, plan)
        texts = {
            "json": ("whatif.json", whatif_json(payload)),
            "md": ("playbook.md", render_playbook(report, payload)),
            "html": ("whatif.html", render_whatif_html(report, payload)),
        }
        console = console_summary(payload)
        artifacts = [(out_dir / texts[name][0], texts[name][1].encode("utf-8")) for name in chosen]
        written = write_artifacts(artifacts, inputs=tuple(identities))
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
