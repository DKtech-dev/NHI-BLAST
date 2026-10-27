"""Coverage gate for the non-slow suite (M7).

Performance tests are excluded because coverage tracing changes their measured
runtime; they are a separate gate (`pytest -m slow`). The policy here is deliberately
modest and architectural: 80% overall line coverage, and every module that makes
authority decisions or writes an artifact also at least 80%. Parser safety is proven
by the adversarial suite rather than by a line percentage.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

OVERALL_MINIMUM = 80.0
ENFORCED_PACKAGES = ("aws", "analysis", "report")
PACKAGE_MINIMUM = 80.0
REPO_ROOT = Path(__file__).resolve().parents[1]


def _normalise(path: str) -> str:
    return path.replace("\\", "/")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nhi-blast-coverage-") as tmp:
        report = Path(tmp) / "coverage.json"
        completed = subprocess.run(  # noqa: S603 - fixed interpreter and repository-relative args
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-m",
                "not slow",
                "--cov=src/nhi_blast",
                "--cov-branch",
                f"--cov-report=json:{report}",
            ],
            cwd=REPO_ROOT,
            check=False,
        )
        if completed.returncode != 0:
            return completed.returncode
        if not report.is_file():
            sys.stderr.write("coverage report was not produced\n")
            return 1
        payload = json.loads(report.read_text(encoding="utf-8"))

    failures: list[str] = []
    total = float(payload["totals"]["percent_covered"])
    sys.stdout.write(f"overall line coverage: {total:.2f}% (minimum {OVERALL_MINIMUM:.0f}%)\n")
    if total < OVERALL_MINIMUM:
        failures.append(f"overall coverage {total:.2f}% is below {OVERALL_MINIMUM:.0f}%")

    for raw_path, data in sorted(payload["files"].items()):
        path = _normalise(raw_path)
        if not path.startswith("src/nhi_blast/"):
            continue
        parts = path.split("/")
        if len(parts) < 4 or parts[2] not in ENFORCED_PACKAGES:
            continue
        percent = float(data["summary"]["percent_covered"])
        if percent < PACKAGE_MINIMUM:
            failures.append(f"{path}: {percent:.2f}% is below {PACKAGE_MINIMUM:.0f}%")
        sys.stdout.write(f"  {path}: {percent:.2f}%\n")

    if failures:
        for failure in failures:
            sys.stderr.write(f"coverage gate failed: {failure}\n")
        return 1
    sys.stdout.write("coverage gate passed\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
