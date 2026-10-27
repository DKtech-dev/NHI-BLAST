"""Documentation integrity checks: local links and rule coverage."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

DOCS = (
    ROOT / "README.md",
    ROOT / "SECURITY.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "CHANGELOG.md",
    ROOT / "docs" / "architecture.md",
    ROOT / "docs" / "assumptions.md",
    ROOT / "docs" / "benchmark.md",
    ROOT / "docs" / "data-provenance.md",
    ROOT / "docs" / "implementation-status.md",
    ROOT / "docs" / "known-limitations.md",
    ROOT / "docs" / "production-readiness.md",
    ROOT / "docs" / "release.md",
    ROOT / "docs" / "requirements-traceability.md",
    ROOT / "docs" / "testing.md",
    ROOT / "docs" / "research" / "sources.md",
    *sorted((ROOT / "docs" / "rules").glob("*.md")),
)


def _local_targets(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    targets = []
    for raw in LINK.findall(text):
        target = raw.strip().split(" ", 1)[0]
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = target.split("#", 1)[0].split("?", 1)[0]
        if target:
            targets.append(target)
    return targets


def test_local_documentation_links_resolve() -> None:
    missing = []
    for document in DOCS:
        assert document.is_file(), f"missing documentation file: {document}"
        for target in _local_targets(document):
            resolved = (document.parent / target).resolve()
            if not resolved.exists():
                missing.append(f"{document.relative_to(ROOT)} -> {target}")
    assert not missing, "broken local links:\n" + "\n".join(sorted(missing))


def test_every_rule_has_documentation() -> None:
    catalog = yaml.safe_load(
        (ROOT / "src" / "nhi_blast" / "data" / "rules.yaml").read_text(encoding="utf-8")
    )
    index = (ROOT / "docs" / "rules" / "README.md").read_text(encoding="utf-8")
    for rule in catalog["rules"]:
        rule_id = rule["id"]
        page = ROOT / "docs" / "rules" / f"{rule_id}.md"
        assert page.is_file(), f"missing rule page for {rule_id}"
        assert rule_id in page.read_text(encoding="utf-8")
        assert rule_id in index, f"{rule_id} is absent from docs/rules/README.md"


def test_readme_documents_every_cli_command() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for command in ("scan", "rank", "explain", "export", "schema", "version"):
        assert f"nhi-blast {command}" in readme or f"`{command}`" in readme
