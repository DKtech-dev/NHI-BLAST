"""Typer commands for the report diff and the reviewed baseline (registered by cli/app.py)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Annotated

import typer

from nhi_blast.core.models import Severity
from nhi_blast.diff.baseline import (
    BaselineError,
    BaselineOutputError,
    accept_entry,
    load_baseline,
    load_diff_with_identity,
    parse_date,
    prune_entries,
    write_baseline,
)
from nhi_blast.diff.run import DiffInputError, DiffOptions, DiffOutputError, run_diff
from nhi_blast.report._text import safe_text

_FAIL_ON = {"critical", "high", "medium", "low", "never"}


def _error(message: str) -> None:
    typer.echo(f"error: {safe_text(message, 600)}", err=True)


def _guarded(action: Callable[[], int]) -> None:
    try:
        code = action()
    except (DiffOutputError, BaselineOutputError) as exc:
        _error(str(exc))
        raise typer.Exit(4) from None
    except (DiffInputError, BaselineError) as exc:
        _error(str(exc))
        raise typer.Exit(2) from None
    except Exception as exc:
        _error(f"internal error: {type(exc).__name__}")
        raise typer.Exit(4) from None
    raise typer.Exit(code)


def _fail_on(text: str) -> Severity | None:
    normalized = text.strip().lower()
    if normalized not in _FAIL_ON:
        msg = "unsupported --fail-on level; choose critical, high, medium, low or never"
        raise DiffInputError(msg)
    return None if normalized == "never" else Severity(normalized.upper())


def diff(
    base: Annotated[Path, typer.Argument(metavar="BASE", help="Saved JSON report (older).")],
    head: Annotated[Path, typer.Argument(metavar="HEAD", help="Saved JSON report (newer).")],
    baseline: Annotated[
        Path | None, typer.Option("--baseline", help="Reviewed baseline file.")
    ] = None,
    fail_on: Annotated[
        str, typer.Option("--fail-on", help="critical, high, medium, low or never.")
    ] = "never",
    formats: Annotated[
        list[str] | None,
        typer.Option("--format", help="console or json (more when registered); repeatable."),
    ] = None,
    out_dir: Annotated[
        Path, typer.Option("--out", help="Output directory for written formats.")
    ] = Path("nhi-blast-diff-out"),
    as_of: Annotated[
        str | None,
        typer.Option(
            "--as-of", help="YYYY-MM-DD used to expire baseline entries; no clock is read."
        ),
    ] = None,
) -> None:
    """Compare two saved reports. Offline; exit 1 on new findings, 3 when not comparable."""

    def action() -> int:
        options = DiffOptions(
            base=base,
            head=head,
            baseline=baseline,
            fail_on=_fail_on(fail_on),
            formats=tuple(formats or ()),
            out_dir=out_dir,
            as_of=None if as_of is None else _as_of(as_of),
        )
        outcome = run_diff(options)
        typer.echo(outcome.console_text, nl=False)
        if outcome.written:
            typer.echo(
                "Written: " + " ".join(safe_text(p.as_posix(), 500) for p in outcome.written)
            )
        return outcome.exit_code

    _guarded(action)


def _as_of(text: str) -> date:
    try:
        return parse_date(text, "--as-of")
    except BaselineError as exc:
        raise DiffInputError(str(exc)) from None


baseline_app = typer.Typer(
    name="baseline",
    help="Maintain the reviewed baseline of accepted new findings.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
)


@baseline_app.command("accept")
def accept(
    lk: Annotated[str, typer.Argument(metavar="LK", help="Logical key of a NEW finding.")],
    diff_path: Annotated[Path, typer.Option("--diff", help="Diff JSON the finding appears in.")],
    reason: Annotated[str, typer.Option("--reason", help="Why the finding is accepted.")],
    reviewer: Annotated[str, typer.Option("--reviewer", help="Name of the reviewer.")],
    baseline: Annotated[Path, typer.Option("--baseline", help="Baseline file to update.")],
    expires: Annotated[
        str | None, typer.Option("--expires", help="YYYY-MM-DD after which it stops suppressing.")
    ] = None,
) -> None:
    """Add one entry; only a finding that is new in the given diff can be accepted."""

    def action() -> int:
        existing = load_baseline(baseline) if baseline.exists() else None
        loaded_diff, diff_identity = load_diff_with_identity(diff_path)
        updated = accept_entry(
            existing,
            loaded_diff,
            lk=lk.strip().lower(),
            reason=reason,
            reviewer=reviewer,
            expires=expires,
        )
        write_baseline(baseline, updated, inputs=(diff_identity,))
        typer.echo(f"Baseline updated: {len(updated.entries)} entries")
        return 0

    _guarded(action)


@baseline_app.command("prune")
def prune(
    diff_path: Annotated[Path, typer.Option("--diff", help="Diff JSON to prune against.")],
    baseline: Annotated[Path, typer.Option("--baseline", help="Baseline file to update.")],
) -> None:
    """Remove only entries whose finding is resolved (no longer observed) in the diff."""

    def action() -> int:
        existing = load_baseline(baseline)
        loaded_diff, diff_identity = load_diff_with_identity(diff_path)
        updated, removed = prune_entries(existing, loaded_diff)
        if removed:
            write_baseline(baseline, updated, inputs=(diff_identity,))
        typer.echo(f"Baseline pruned: {len(removed)} removed, {len(updated.entries)} kept")
        return 0

    _guarded(action)


__all__ = ["accept", "baseline_app", "diff", "prune"]
