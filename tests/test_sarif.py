"""SARIF 2.1.0 report shape, metadata, limits and determinism (M5, spec 13.3)."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from nhi_blast.core.models import Severity
from nhi_blast.report.sarif import sarif_report, write_sarif
from tests.report_support import make_report

ROOT = Path(__file__).resolve().parents[1]
SARIF_SCHEMA = ROOT / "docs" / "schema" / "sarif-2.1.0.schema.json"


def test_sarif_validates_against_vendored_schema() -> None:
    data = sarif_report(make_report())
    schema = json.loads(SARIF_SCHEMA.read_text(encoding="utf-8"))

    jsonschema.Draft7Validator.check_schema(schema)
    jsonschema.Draft7Validator(schema).validate(data)
    assert data["version"] == "2.1.0"
    assert len(data["runs"]) == 1


def test_sarif_carries_rule_metadata_levels_severity_and_confidence() -> None:
    data = sarif_report(make_report())
    run = data["runs"][0]
    driver = run["tool"]["driver"]

    assert driver["name"] == "nhi-blast"
    assert driver["version"] == "0.1.0"
    assert driver["informationUri"]
    assert any(rule["id"] == "NHB-SURV-001" for rule in driver["rules"])
    assert all(
        rule["fullDescription"]["text"]
        and rule["shortDescription"]["text"]
        and rule["help"]["text"]
        and rule["help"]["markdown"]
        for rule in driver["rules"]
    )

    result = run["results"][0]
    assert result["ruleId"] == "NHB-SURV-001"
    assert result["level"] == "error"
    assert result["properties"]["security-severity"] == "9.5"
    assert result["properties"]["confidence"] == "declared"
    assert result["properties"]["assumptions"] == ["A-STS-TTL"]
    assert len(result["partialFingerprints"]["nhiBlast/v1"]) == 64
    location = result["locations"][0]["physicalLocation"]
    assert location["artifactLocation"] == {
        "uri": ".github/workflows/release.yml",
        "uriBaseId": "%SRCROOT%",
    }
    assert location["region"]["startLine"] == 14


def test_sarif_results_are_severity_ordered_and_info_omits_security_severity() -> None:
    report = make_report()
    base = report.findings[0]
    findings = (
        base.model_copy(
            update={"id": "NHB-ROT-001-aaaaaaaa", "rule": "NHB-ROT-001", "severity": Severity.LOW}
        ),
        base.model_copy(
            update={"id": "NHB-GHA-003-bbbbbbbb", "rule": "NHB-GHA-003", "severity": Severity.INFO}
        ),
        base,
        base.model_copy(
            update={
                "id": "NHB-OIDC-002-cccccccc",
                "rule": "NHB-OIDC-002",
                "severity": Severity.HIGH,
            }
        ),
    )
    data = sarif_report(report.model_copy(update={"findings": findings}))
    results = data["runs"][0]["results"]

    assert [result["ruleId"] for result in results] == [
        "NHB-SURV-001",
        "NHB-OIDC-002",
        "NHB-ROT-001",
        "NHB-GHA-003",
    ]
    info = next(result for result in results if result["ruleId"] == "NHB-GHA-003")
    assert info["level"] == "note"
    assert "security-severity" not in info["properties"]


def test_sarif_code_flow_uses_edge_locations_and_messages() -> None:
    result = sarif_report(make_report())["runs"][0]["results"][0]

    locations = result["codeFlows"][0]["threadFlows"][0]["locations"]
    assert len(locations) == 3
    first = locations[0]["location"]
    assert first["physicalLocation"]["artifactLocation"]["uri"] == (".github/workflows/release.yml")
    assert first["physicalLocation"]["region"]["startLine"] == 14
    assert first["message"]["text"] == "workflow grants id-token: write"


def test_sarif_partial_fingerprint_ignores_line_shifts() -> None:
    report = make_report()
    finding = report.findings[0]
    shifted = finding.model_copy(
        update={"evidence": (finding.evidence[0].model_copy(update={"line": 999}),)}
    )

    first = sarif_report(report)["runs"][0]["results"][0]
    second = sarif_report(report.model_copy(update={"findings": (shifted,)}))["runs"][0]["results"][
        0
    ]

    assert first["partialFingerprints"] == second["partialFingerprints"]


def test_sarif_truncates_at_five_thousand_with_notification() -> None:
    report = make_report()
    base = report.findings[0]
    findings = tuple(
        base.model_copy(
            update={
                "id": f"NHB-SURV-001-{index:08x}",
                "message": f"synthetic finding {index}",
            }
        )
        for index in range(5005)
    )

    data = sarif_report(report.model_copy(update={"findings": findings}))
    run = data["runs"][0]

    assert len(run["results"]) == 5000
    notifications = run["invocations"][0]["toolExecutionNotifications"]
    assert len(notifications) == 1
    assert "5" in notifications[0]["message"]["text"]
    assert notifications[0]["level"] == "warning"


def test_write_sarif_is_sorted_json_with_trailing_newline(tmp_path: Path) -> None:
    path = tmp_path / "report.sarif"
    write_sarif(make_report(), path)
    text = path.read_text(encoding="utf-8")

    assert text.endswith("\n")
    data = json.loads(text)
    assert text == json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
