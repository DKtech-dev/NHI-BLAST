"""Cross-format output safety and secret-leak checks (M5, spec 2.5 and 13)."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

from nhi_blast import __version__
from nhi_blast.analysis.findings import build_findings
from nhi_blast.core.models import Inputs, Report, Severity, ToolInfo
from nhi_blast.report.console import render_console
from nhi_blast.report.html import html_report
from nhi_blast.report.json_report import report_json
from nhi_blast.report.sarif import sarif_report
from tests.report_support import HOSTILE, make_report
from tests.test_graph_builder import build_inline


class _TagCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.controls: list[tuple[str, dict[str, str | None], bool]] = []
        self.label_for: set[str] = set()
        self._label_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        self.tags.append((tag, attributes))
        if tag == "label":
            self._label_depth += 1
            target = attributes.get("for")
            if target:
                self.label_for.add(target)
        if tag in {"input", "select", "textarea"}:
            self.controls.append((tag, attributes, self._label_depth > 0))

    def handle_endtag(self, tag: str) -> None:
        if tag == "label":
            self._label_depth = max(0, self._label_depth - 1)


def _literal_report() -> tuple[Report, str]:
    token = "ghp_" + "S" * 36
    build = build_inline(
        f"""
name: Literal credential
on: push
permissions:
  id-token: write
jobs:
  deploy:
    runs-on: ubuntu-latest
    env:
      LEAKED_TOKEN: {token}
    steps:
      - run: echo deploy
"""
    )
    findings = build_findings(build.graph).findings
    report = Report(
        tool=ToolInfo(version=__version__),
        inputs=Inputs(
            digest="d" * 64,
            repo_slug="acme/shop",
            repo_slug_source="test",
        ),
        findings=findings,
        graph=build.graph,
    )
    return report, token


CLAIM_ASSERTION = re.compile(
    r"\b(?:proves|guarantees?|guaranteed|exploitable|takeover|take over|taken over)\b",
    re.IGNORECASE,
)


def test_report_has_one_title_unique_ids_and_labelled_controls() -> None:
    document = html_report(make_report())
    collector = _TagCollector()
    collector.feed(document)

    h1s = [tag for tag, _ in collector.tags if tag == "h1"]
    ids = [attrs["id"] for _, attrs in collector.tags if attrs.get("id")]
    assert h1s == ["h1"]
    assert "Incident exposure report" in document
    assert len(ids) == len(set(ids))
    assert collector.controls
    for tag, attrs, wrapped in collector.controls:
        label = attrs.get("aria-label")
        control_id = attrs.get("id")
        assert label or wrapped or (control_id is not None and control_id in collector.label_for), (
            f"{tag} control without an accessible name: {attrs}"
        )


def test_html_font_faces_are_embedded_and_never_fetched() -> None:
    document = html_report(make_report())
    style = document.split("<style>", 1)[1].split("</style>", 1)[0]
    faces = re.findall(r"@font-face \{.*?\}", style, re.DOTALL)

    assert len(faces) == 3
    for face in faces:
        sources = re.findall(r"url\(([^)]+)\)", face)
        assert sources
        assert all(item.startswith('"data:font/woff2;base64,') for item in sources)
    assert "fonts.googleapis.com" not in document
    assert "fonts.gstatic.com" not in document


def test_report_templates_do_not_assert_claims() -> None:
    root = Path(__file__).resolve().parents[1]
    templates = sorted((root / "src" / "nhi_blast" / "report").glob("*.py"))
    assert len(templates) > 2
    offenders = []
    for template in templates:
        text = template.read_text(encoding="utf-8")
        for match in CLAIM_ASSERTION.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{template.relative_to(root)}:{line}:{match.group(0)}")
    assert not offenders, "claim wording in report templates:\n" + "\n".join(offenders)
    assert "not proof of exploitation" in html_report(make_report())


def test_literal_credential_value_is_absent_from_every_renderer() -> None:
    report, token = _literal_report()
    outputs = (
        report_json(report),
        render_console(report, color=False),
        json.dumps(sarif_report(report), sort_keys=True),
        html_report(report),
    )

    assert any(finding.rule == "NHB-GHA-005" for finding in report.findings)
    for output in outputs:
        assert token not in output
        assert "SSSSSSSSSSSSSSSS" not in output


def test_hostile_strings_remain_data_in_json_and_sarif() -> None:
    report = make_report(hostile=True)

    json_data = json.loads(report_json(report))
    labels = [node["label"] for node in json_data["graph"]["nodes"]]
    sarif = sarif_report(report)
    message = sarif["runs"][0]["results"][0]["message"]["text"]

    assert HOSTILE in labels
    assert "\x00" not in message
    assert "\x1b" not in message
    assert "alert(1)" in message


def test_hostile_strings_do_not_create_html_elements_or_event_handlers() -> None:
    document = html_report(make_report(hostile=True))
    collector = _TagCollector()
    collector.feed(document)

    tags = [tag for tag, _ in collector.tags]
    assert not {"img", "iframe", "object", "embed"} & set(tags)
    assert tags.count("script") == 3
    assert not any(name.lower().startswith("on") for _, attrs in collector.tags for name in attrs)
    assert "<img" not in document.lower()


def test_sarif_omits_absolute_and_traversing_artifact_paths() -> None:
    report = make_report()
    base = report.findings[0]
    for path in ("C:\\secret\\release.yml", "/etc/passwd", "../outside/release.yml"):
        evidence = base.evidence[0].model_copy(update={"file": path})
        changed = base.model_copy(update={"evidence": (evidence,)})
        serialized = json.dumps(
            sarif_report(report.model_copy(update={"findings": (changed,)})),
            sort_keys=True,
        )
        assert path not in serialized


def test_all_renderers_are_byte_stable_for_equal_input() -> None:
    report = make_report(hostile=True)

    assert report_json(report) == report_json(report)
    assert render_console(report, color=False) == render_console(report, color=False)
    assert sarif_report(report) == sarif_report(report)
    assert html_report(report) == html_report(report)


def test_report_shell_contains_no_control_characters() -> None:
    document = html_report(make_report(hostile=True))
    script_start = document.find('<script type="application/json"')
    assert script_start > 0
    shell = document[:script_start] + document[document.rfind("</script>") :]

    assert "\x00" not in shell
    assert "\x1b" not in shell


def test_sarif_severity_mapping_covers_every_level() -> None:
    report = make_report()
    base = report.findings[0]
    findings = tuple(
        base.model_copy(
            update={
                "id": f"NHB-SURV-001-{index:08x}",
                "severity": severity,
            }
        )
        for index, severity in enumerate(Severity)
    )

    results = sarif_report(report.model_copy(update={"findings": findings}))["runs"][0]["results"]
    levels = {result["properties"].get("security-severity") for result in results}

    assert levels == {None, "9.5", "8.0", "5.5", "3.0"}
