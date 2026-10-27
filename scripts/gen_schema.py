"""Generate or verify the committed NHI-Blast report schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from nhi_blast.report.model_json import report_schema

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "docs" / "schema" / "report.schema.json"


def render() -> str:
    return json.dumps(report_schema(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_PATH)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when the committed schema differs from the generated schema",
    )
    args = parser.parse_args(argv)
    expected = render()
    if args.check:
        try:
            actual = args.path.read_text(encoding="utf-8")
        except OSError as exc:
            sys.stderr.write(f"cannot read {args.path}: {exc}\n")
            return 1
        if actual != expected:
            sys.stderr.write(f"{args.path} is stale; run scripts/gen_schema.py\n")
            return 1
        return 0
    args.path.parent.mkdir(parents=True, exist_ok=True)
    args.path.write_text(expected, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
