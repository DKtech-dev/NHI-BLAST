"""Typer command implementations (spec 14.1-14.2)."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

import typer

from nhi_blast import SCHEMA_VERSION, __version__
from nhi_blast.core.data import all_data_file_infos
from nhi_blast.pipeline import (
    ExportOptions,
    OutputError,
    RankOptions,
    ScanOptions,
    UsageError,
    parse_fail_on,
    run_export,
    run_rank,
    run_scan,
)
from nhi_blast.report._text import safe_text
from nhi_blast.report.explain import ExplainError, load_report, render_explanation
from nhi_blast.report.model_json import report_schema

PathArgument = Annotated[Path, typer.Argument(metavar="PATH", help="Repository root to read.")]
RepoSlugOption = Annotated[
    str | None, typer.Option("--repo-slug", help="Override the owner/repo identity.")
]
DefaultBranchOption = Annotated[
    str | None, typer.Option("--default-branch", help="Override the default branch.")
]
AwsAccountOption = Annotated[
    str | None, typer.Option("--aws-account", help="Override the AWS account id.")
]
AwsRegionOption = Annotated[
    str | None, typer.Option("--aws-region", help="Override the AWS region.")
]
ConfigOption = Annotated[
    Path | None, typer.Option("--config", help="Configuration file inside the scan root.")
]
TfJsonOption = Annotated[
    list[Path] | None,
    typer.Option("--tf-json", help="Terraform plan or state JSON; repeatable."),
]
TfHclOption = Annotated[
    bool | None,
    typer.Option(
        "--tf-hcl/--no-tf-hcl",
        help="Enable the HCL fallback; default only when no Terraform JSON exists.",
    ),
]
IamJsonOption = Annotated[
    list[Path] | None,
    typer.Option("--iam-json", help="IAM policy or get-role JSON; repeatable."),
]
StrictOption = Annotated[
    bool, typer.Option("--strict", help="Exit 3 when error diagnostics make results partial.")
]
NoColorOption = Annotated[bool, typer.Option("--no-color", help="Disable terminal colour.")]
OutOption = Annotated[Path, typer.Option("--out", help="Output directory for requested artifacts.")]
MaxDepthOption = Annotated[
    int | None,
    typer.Option("--max-depth", min=0, help="Persistent-credential closure depth."),
]


def _error(message: str) -> None:
    typer.echo(f"error: {safe_text(message, 600)}", err=True)


def _execute(action: Callable[[], int]) -> None:
    try:
        code = action()
    except UsageError as exc:
        _error(str(exc))
        raise typer.Exit(2) from None
    except OutputError as exc:
        _error(str(exc))
        raise typer.Exit(4) from None
    except Exception as exc:
        _error(f"internal error: {type(exc).__name__}")
        raise typer.Exit(4) from None
    raise typer.Exit(code)


def _use_color(no_color: bool) -> bool:
    return not no_color and sys.stdout.isatty()


def _written(paths: tuple[Path, ...]) -> str:
    return " ".join(safe_text(path.as_posix(), 500) for path in paths)


def scan(
    path: PathArgument,
    tf_json: TfJsonOption = None,
    tf_hcl: TfHclOption = None,
    iam_json: IamJsonOption = None,
    simulate: Annotated[
        list[str] | None,
        typer.Option("--simulate-compromise", help="Compromise selector; repeatable."),
    ] = None,
    formats: Annotated[
        list[str] | None,
        typer.Option("--format", help="console, json, sarif or html; repeatable."),
    ] = None,
    out_dir: OutOption = Path("nhi-blast-out"),
    fail_on: Annotated[
        str,
        typer.Option("--fail-on", help="critical, high, medium, low or never."),
    ] = "never",
    max_depth: MaxDepthOption = None,
    repo_slug: RepoSlugOption = None,
    default_branch: DefaultBranchOption = None,
    aws_account: AwsAccountOption = None,
    aws_region: AwsRegionOption = None,
    config_path: ConfigOption = None,
    strict: StrictOption = False,
    timestamp: Annotated[
        bool, typer.Option("--timestamp", help="Add wall-clock time to artifacts.")
    ] = False,
    no_color: NoColorOption = False,
) -> None:
    """Parse a repository, audit trust, run scenarios and write reports."""

    def action() -> int:
        options = ScanOptions(
            root=path,
            tf_json=tuple(tf_json or ()),
            tf_hcl=tf_hcl,
            iam_json=tuple(iam_json or ()),
            repo_slug=repo_slug,
            default_branch=default_branch,
            aws_account=aws_account,
            aws_region=aws_region,
            config_path=config_path,
            strict=strict,
            selectors=tuple(simulate or ()),
            formats=tuple(formats or ("console",)),
            out_dir=out_dir,
            fail_on=parse_fail_on(fail_on),
            max_depth=max_depth,
            timestamp=timestamp,
        )
        outcome = run_scan(options, color=_use_color(no_color))
        typer.echo(outcome.console_text, nl=False)
        if outcome.written:
            typer.echo(f"Written: {_written(outcome.written)}")
        return outcome.exit_code

    _execute(action)


def rank(
    path: PathArgument,
    tf_json: TfJsonOption = None,
    tf_hcl: TfHclOption = None,
    iam_json: IamJsonOption = None,
    repo_slug: RepoSlugOption = None,
    default_branch: DefaultBranchOption = None,
    aws_account: AwsAccountOption = None,
    aws_region: AwsRegionOption = None,
    config_path: ConfigOption = None,
    strict: StrictOption = False,
    max_depth: MaxDepthOption = None,
    output_format: Annotated[str, typer.Option("--format", help="console or json.")] = "console",
    out_dir: OutOption = Path("nhi-blast-out"),
) -> None:
    """Rank mutable third-party actions by potential blast radius."""

    def action() -> int:
        options = RankOptions(
            root=path,
            tf_json=tuple(tf_json or ()),
            tf_hcl=tf_hcl,
            iam_json=tuple(iam_json or ()),
            repo_slug=repo_slug,
            default_branch=default_branch,
            aws_account=aws_account,
            aws_region=aws_region,
            config_path=config_path,
            strict=strict,
            fmt=output_format,
            out_dir=out_dir,
            max_depth=max_depth,
        )
        outcome = run_rank(options)
        typer.echo(outcome.console_text, nl=False)
        if outcome.written:
            typer.echo(f"Written: {_written(outcome.written)}")
        return outcome.exit_code

    _execute(action)


def explain(
    identifier: Annotated[str, typer.Argument(metavar="ID", help="Finding, node or edge id.")],
    report_path: Annotated[Path, typer.Option("--report", help="Saved JSON report to explain.")],
) -> None:
    """Show the evidence chain for a finding, node or edge in a saved report."""

    def action() -> int:
        try:
            report = load_report(report_path)
            text = render_explanation(report, identifier)
        except ExplainError as exc:
            raise UsageError(str(exc)) from None
        typer.echo(text, nl=False)
        return 0

    _execute(action)


def export(
    path: PathArgument,
    output_format: Annotated[str, typer.Option("--format", help="json or dot.")],
    tf_json: TfJsonOption = None,
    tf_hcl: TfHclOption = None,
    iam_json: IamJsonOption = None,
    repo_slug: RepoSlugOption = None,
    default_branch: DefaultBranchOption = None,
    aws_account: AwsAccountOption = None,
    aws_region: AwsRegionOption = None,
    config_path: ConfigOption = None,
    strict: StrictOption = False,
    out_dir: OutOption = Path("nhi-blast-out"),
    timestamp: Annotated[
        bool, typer.Option("--timestamp", help="Add wall-clock time to the export.")
    ] = False,
) -> None:
    """Export the authority graph as JSON or Graphviz DOT."""

    def action() -> int:
        options = ExportOptions(
            root=path,
            tf_json=tuple(tf_json or ()),
            tf_hcl=tf_hcl,
            iam_json=tuple(iam_json or ()),
            repo_slug=repo_slug,
            default_branch=default_branch,
            aws_account=aws_account,
            aws_region=aws_region,
            config_path=config_path,
            strict=strict,
            fmt=output_format,
            out_dir=out_dir,
            timestamp=timestamp,
        )
        outcome = run_export(options)
        typer.echo(outcome.text, nl=False)
        return outcome.exit_code

    _execute(action)


def schema() -> None:
    """Print the report JSON Schema."""
    typer.echo(json.dumps(report_schema(), indent=2, sort_keys=True, ensure_ascii=False))


def _age_text(verified_on: str, today: date) -> str:
    try:
        verified = date.fromisoformat(verified_on)
    except ValueError:
        return "age unknown"
    delta = (today - verified).days
    if delta < 0:
        return "date is in the future"
    if delta == 0:
        return "today"
    if delta == 1:
        return "1 day ago"
    return f"{delta} days ago"


def version(
    data: Annotated[bool, typer.Option("--data", help="Show data-file versions and ages.")] = False,
) -> None:
    """Print the tool version, schema version and optionally data-file ages."""
    typer.echo(f"nhi-blast {__version__}")
    typer.echo(f"report schema {SCHEMA_VERSION}")
    if not data:
        return
    infos = all_data_file_infos()
    today = datetime.now(UTC).date()
    typer.echo(f"Data files: {len(infos)}")
    for info in infos:
        typer.echo(
            f"  {safe_text(info.name, 120)}  verified {safe_text(info.verified_on, 40)} "
            f"({_age_text(info.verified_on, today)})  "
            f"{info.entry_count} entries  {safe_text(info.source_url, 300)}"
        )


__all__ = [
    "explain",
    "export",
    "rank",
    "scan",
    "schema",
    "version",
]
