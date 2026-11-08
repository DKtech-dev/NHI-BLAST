"""Logical finding keys, pairing and graph keys (nhi-blast-diff/1.0)."""

from __future__ import annotations

import random

from hypothesis import given, settings
from hypothesis import strategies as st

from nhi_blast.analysis.findings import SCENARIO_RULES
from nhi_blast.core.evidence import Evidence, EvidenceClass
from nhi_blast.diff.keys import (
    evidence_digest,
    finding_key,
    pair_findings,
    path_signature,
    strip_file_paths,
    strip_lines,
)
from tests.test_diff_support import base_report, duplicate_of, first_finding


def test_key_is_a_stable_hex_digest() -> None:
    finding = first_finding(base_report(), "NHB-OIDC-002")
    key = finding_key(finding)
    assert len(key) == 64
    assert key == finding_key(finding)
    assert key != finding_key(first_finding(base_report(), "NHB-SURV-001"))


def test_key_ignores_ids_lines_messages_and_severity() -> None:
    finding = first_finding(base_report(), "NHB-OIDC-002")
    shifted = tuple(
        e.model_copy(update={"line": (e.line or 0) + 40, "end_line": None})
        for e in finding.evidence
    )
    other = finding.model_copy(
        update={"id": "other-id", "evidence": shifted, "message": "reworded", "title": "t"}
    )
    assert finding_key(other) == finding_key(finding)


def test_scenario_bound_findings_key_by_scenario() -> None:
    finding = first_finding(base_report(), "NHB-SURV-001")
    assert finding.scenario is not None
    assert finding_key(finding.model_copy(update={"scenario": "fork-pr"})) != finding_key(finding)


def test_scenario_independent_findings_ignore_the_scenario_attribution() -> None:
    for rule in ("NHB-OIDC-002", "NHB-OIDC-005", "NHB-GHA-001"):
        finding = next((item for item in base_report().findings if item.rule == rule), None)
        if finding is None:
            continue
        for scenario in ("fork-pr", "action:x@v1", None):
            assert finding_key(finding.model_copy(update={"scenario": scenario})) == finding_key(
                finding
            )
    assert "NHB-OIDC-002" not in SCENARIO_RULES


def test_key_depends_on_rule_path_and_primary_file() -> None:
    finding = first_finding(base_report(), "NHB-OIDC-002")
    key = finding_key(finding)
    assert finding_key(finding.model_copy(update={"rule": "NHB-OIDC-003"})) != key
    assert finding_key(finding.model_copy(update={"path": (*finding.path, "extra")})) != key
    moved = tuple(e.model_copy(update={"file": "elsewhere.json"}) for e in finding.evidence)
    assert finding_key(finding.model_copy(update={"evidence": moved})) != key


def test_key_is_insensitive_to_path_order() -> None:
    finding = first_finding(base_report(), "NHB-OIDC-002")
    reversed_path = finding.model_copy(update={"path": tuple(reversed(finding.path))})
    assert finding_key(reversed_path) == finding_key(finding)


def test_pairing_never_crosses_rule_or_scenario() -> None:
    finding = first_finding(base_report(), "NHB-SURV-001")
    other_rule = finding.model_copy(update={"rule": "NHB-OIDC-003"})
    other_scenario = finding.model_copy(update={"scenario": "fork-pr"})
    for other in (other_rule, other_scenario):
        pairing = pair_findings([finding], [other])
        assert pairing.pairs == ()
        assert len(pairing.base_unpaired) == 1
        assert len(pairing.head_unpaired) == 1
        assert pairing.ambiguous == frozenset()


def test_equal_sized_duplicate_groups_pair_without_ambiguity() -> None:
    finding = first_finding(base_report(), "NHB-OIDC-002")
    twin = duplicate_of(finding)
    pairing = pair_findings([finding, twin], [finding, twin])
    assert len(pairing.pairs) == 2
    assert pairing.base_unpaired == ()
    assert pairing.ambiguous == frozenset()


def test_surplus_in_a_nonempty_group_is_unpaired_and_flagged() -> None:
    finding = first_finding(base_report(), "NHB-OIDC-002")
    twin = duplicate_of(finding)
    pairing = pair_findings([finding, twin], [finding])
    assert len(pairing.pairs) == 1
    assert len(pairing.base_unpaired) == 1
    assert pairing.ambiguous == frozenset({finding_key(finding)})
    reverse = pair_findings([finding], [finding, twin])
    assert len(reverse.head_unpaired) == 1
    assert reverse.ambiguous == frozenset({finding_key(finding)})


def test_pairing_prefers_equal_evidence_over_position() -> None:
    finding = first_finding(base_report(), "NHB-OIDC-002")
    changed = finding.model_copy(
        update={
            "id": "x",
            "evidence": (
                *finding.evidence,
                Evidence(cls=finding.evidence[0].cls, rule="X.extra", file="f.json", line=1),
            ),
        }
    )
    pairing = pair_findings([finding, changed], [changed, finding])
    for left, right in pairing.pairs:
        assert left.evidence_digest == right.evidence_digest


@settings(max_examples=60, deadline=None)
@given(seed=st.integers(0, 10_000), shift=st.integers(0, 500))
def test_pairing_is_order_independent_and_line_independent(seed: int, shift: int) -> None:
    findings = list(base_report().findings)
    shifted = [
        item.model_copy(
            update={
                "evidence": tuple(
                    e.model_copy(update={"line": None if e.line is None else e.line + shift})
                    for e in item.evidence
                )
            }
        )
        for item in findings
    ]
    shuffled = list(shifted)
    random.Random(seed).shuffle(shuffled)
    pairing = pair_findings(findings, shuffled)
    assert pairing.base_unpaired == ()
    assert pairing.head_unpaired == ()
    assert len(pairing.pairs) == len(findings)
    for left, right in pairing.pairs:
        assert left.lk == right.lk
        assert left.evidence_digest == right.evidence_digest


def test_strip_lines_removes_line_keys_and_file_suffixes() -> None:
    value = {
        "line": 3,
        "use_site": "a/b.yml:10",
        "x": ["tfstate.json:23", {"end_line": 4, "k": "v"}],
    }
    assert strip_lines(value) == {"use_site": "a/b.yml", "x": ["tfstate.json", {"k": "v"}]}
    assert evidence_digest(
        [Evidence(cls=EvidenceClass.DECLARED, rule="r", file="f.yml", line=1, detail="at f.yml:3")]
    ) == evidence_digest(
        [Evidence(cls=EvidenceClass.DECLARED, rule="r", file="f.yml", line=9, detail="at f.yml:30")]
    )


def test_path_signature_strips_known_input_paths() -> None:
    paths = [".github/workflows/release.yml", ".github/workflows/ci.yml"]
    assert (
        strip_file_paths("job:.github/workflows/release.yml#publish", paths) == "job:<file>#publish"
    )
    finding = first_finding(base_report(), "NHB-OIDC-002")
    signature = path_signature(finding, [".github/workflows/release.yml"])
    assert signature[0] == "job:<file>#publish"
    assert signature[-1] == finding.path[-1]
