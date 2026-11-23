"""Typer application entry point (spec 14.1)."""

from __future__ import annotations

import sys
from io import TextIOWrapper
from typing import Annotated

import typer

from nhi_blast import __version__
from nhi_blast.cli.commands import explain, export, init_config, rank, scan, schema, version
from nhi_blast.cli.diff_cmd import baseline_app, diff
from nhi_blast.cli.whatif_cmd import whatif

app = typer.Typer(
    name="nhi-blast",
    help="Offline, evidence-labelled GitHub Actions to AWS OIDC authority analysis.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"nhi-blast {__version__}")
        raise typer.Exit(0)


@app.callback()
def _root(
    version_flag: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=_version_callback,
            is_eager=True,
            help="Print version and exit.",
        ),
    ] = False,
) -> None:
    del version_flag


app.command("scan", help="Parse a repository, audit trust, run scenarios and write reports.")(scan)
app.command("rank", help="Rank mutable third-party actions by potential blast radius.")(rank)
app.command("explain", help="Show the evidence chain for a finding, node or edge.")(explain)
app.command(
    "export",
    help="Export the authority graph as JSON, Graphviz DOT, or BloodHound OpenGraph.",
)(export)
app.command("init", help="Scaffold a validated nhi-blast.toml configuration file.")(init_config)
app.command("schema", help="Print the report JSON Schema.")(schema)
app.command("version", help="Print tool, schema and data-file versions.")(version)
app.command("diff", help="Compare two saved reports (new, changed, resolved findings).")(diff)
app.add_typer(baseline_app, name="baseline")
app.command(
    "whatif",
    help="Model containment interventions on a saved report (offline; nothing is executed).",
)(whatif)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")
    app(prog_name="nhi-blast")


if __name__ == "__main__":
    main()
