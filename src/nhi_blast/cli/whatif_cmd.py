"""Typer command for the offline containment what-if (registered by cli/app.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from nhi_blast.report._text import safe_text
from nhi_blast.whatif.engine import WhatIfAbort
from nhi_blast.whatif.run import OUTPUT, execute


def whatif(
    report_path: Annotated[
        Path, typer.Argument(metavar="REPORT", help="Saved JSON report (schema 1.1).")
    ],
    plan: Annotated[
        Path, typer.Option("--plan", help="Interventions plan (.json, .yaml or .yml).")
    ],
    formats: Annotated[
        list[str] | None,
        typer.Option("--format", help="json or md (playbook); repeatable. Default: both."),
    ] = None,
    out_dir: Annotated[
        Path, typer.Option("--out", help="Output directory for the what-if artifacts.")
    ] = Path("nhi-blast-whatif-out"),
) -> None:
    """Model containment interventions on a saved report. Offline; nothing is executed."""
    try:
        outcome = execute(report_path, plan, tuple(formats or ()), out_dir)
    except WhatIfAbort as exc:
        typer.echo(f"error: {exc.code}: {safe_text(exc.message, 600)}", err=True)
        raise typer.Exit(4 if exc.code == OUTPUT else 2) from None
    typer.echo(outcome.console_text, nl=False)
    written = " ".join(safe_text(path.as_posix(), 500) for path in outcome.written)
    typer.echo(f"Written: {written}")


__all__ = ["whatif"]
