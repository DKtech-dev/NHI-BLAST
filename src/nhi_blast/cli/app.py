"""Typer application entry point (spec 14.1)."""

from __future__ import annotations

import typer

from nhi_blast.cli.commands import explain, export, rank, scan, schema, version

app = typer.Typer(
    name="nhi-blast",
    help="Offline, evidence-labelled GitHub Actions to AWS OIDC authority analysis.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
)

app.command("scan", help="Parse a repository, audit trust, run scenarios and write reports.")(scan)
app.command("rank", help="Rank mutable third-party actions by potential blast radius.")(rank)
app.command("explain", help="Show the evidence chain for a finding, node or edge.")(explain)
app.command("export", help="Export the authority graph as JSON or Graphviz DOT.")(export)
app.command("schema", help="Print the report JSON Schema.")(schema)
app.command("version", help="Print tool, schema and data-file versions.")(version)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
