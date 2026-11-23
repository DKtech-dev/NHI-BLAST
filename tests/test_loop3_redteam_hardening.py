"""Loop 3 Red-Team adversarial security & hardening regression tests (Audits #7 & #8)."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from nhi_blast.aws.glob import MAX_GLOB_LENGTH, GlobRelation, glob_relation
from nhi_blast.aws.solver import (
    MAX_ALPHABET_SIZE,
    MAX_WITNESS_STEPS,
    CidrPredicate,
    IntervalPredicate,
    SolverStatus,
    StringPredicate,
    solve_cidr_predicates,
    solve_interval_predicates,
    solve_string_predicates,
)
from nhi_blast.cli.app import app
from nhi_blast.core.limits import MIB, Limits
from nhi_blast.discovery.paths import PathGuard
from nhi_blast.discovery.walker import FileKind, InputLoader, _walk, discover
from nhi_blast.parsers._json import MAX_JSON_DEPTH, JsonDepthError, _exceeds_depth, decode_json
from nhi_blast.parsers.terraform.tfhcl import (
    MAX_RESOLVE_DEPTH,
    MAX_SUBSTITUTED_CHARS,
    _normalise_policy_value,
    _resolve_string,
    _resolve_value,
    _substitute_variables,
    parse_tf_hcl,
)
from nhi_blast.parsers.yaml_marked import load_marked_document, to_plain
from nhi_blast.report._text import safe_text
from nhi_blast.report.loader import ReportLoadError, load_report
from nhi_blast.report.redaction import redact_payload
from nhi_blast.whatif.render import console_summary
from nhi_blast.whatif.run import execute as execute_whatif

FAKE_GH_TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


# ------------------------------------------------------------------ 1. aws/solver.py


def test_interval_solver_large_decimal_gt_and_lt_do_not_hang() -> None:
    gt_res = solve_interval_predicates((IntervalPredicate("gt_huge", "gt", (Decimal("1e30"),)),))
    assert gt_res.status is SolverStatus.SAT
    assert gt_res.witness is not None
    assert gt_res.witness > Decimal("1e30")

    lt_res = solve_interval_predicates((IntervalPredicate("lt_huge", "lt", (Decimal("-1e30"),)),))
    assert lt_res.status is SolverStatus.SAT
    assert lt_res.witness is not None
    assert lt_res.witness < Decimal("-1e30")


def test_interval_solver_step_budget_and_nonfinite_fail_closed() -> None:
    excluded = tuple(Decimal(i) for i in range(MAX_WITNESS_STEPS + 5))
    res = solve_interval_predicates((IntervalPredicate("ne_many", "ne", excluded),))
    assert res.status is SolverStatus.BUDGET

    inf_res = solve_interval_predicates(
        (IntervalPredicate("gt_inf", "gt", (Decimal("Infinity"),)),)
    )
    assert inf_res.status is SolverStatus.BUDGET

    nan_res = solve_interval_predicates((IntervalPredicate("gt_nan", "gt", (Decimal("NaN"),)),))
    assert nan_res.status is SolverStatus.BUDGET


def test_cidr_solver_ipv6_exclusion_dos_fails_closed_to_budget() -> None:
    # Well-spaced /128 exclusions across distinct /16 blocks split ::/0 by >100 prefixes each,
    # rapidly exceeding MAX_CIDR_PREFIXES = 4096.
    exclusions = tuple(f"{i:x}::1/128" for i in range(1, 60))
    res = solve_cidr_predicates((CidrPredicate("deny_many_v6", exclusions, negated=True),))
    assert res.status is SolverStatus.BUDGET


def test_string_solver_pattern_length_and_alphabet_caps_fail_closed() -> None:
    oversized = "a" * (MAX_GLOB_LENGTH + 1)
    res_len = solve_string_predicates((StringPredicate("too_long", (oversized,)),))
    assert res_len.status is SolverStatus.BUDGET

    wide_alpha = "".join(chr(0x0100 + i) for i in range(MAX_ALPHABET_SIZE + 10))
    res_alpha = solve_string_predicates((StringPredicate("wide_alpha", (wide_alpha,)),))
    assert res_alpha.status is SolverStatus.BUDGET


# ------------------------------------------------------------------ 2. aws/glob.py


def test_glob_relation_enforces_max_length_before_literal_fast_path() -> None:
    oversized_literal = "a" * (MAX_GLOB_LENGTH + 1)
    pattern = "*a*a*a*b"
    assert glob_relation(oversized_literal, pattern) is GlobRelation.BUDGET_EXCEEDED
    assert glob_relation(pattern, oversized_literal) is GlobRelation.BUDGET_EXCEEDED


# ------------------------------------------------------------------ 3. parsers/terraform/tfhcl.py


def test_tfhcl_oversized_integer_does_not_crash() -> None:
    giant_int = "9" * 5000
    hcl_text = (
        'resource "aws_iam_role" "r" {\n'
        f'  assume_role_policy = jsonencode({{"Version": {giant_int}}})\n'
        "}\n"
    )
    res = parse_tf_hcl("main.tf", hcl_text, limits=Limits())
    assert res is not None

    # Direct unit checks on _resolve_string and _normalise_policy_value
    val, known = _resolve_string(f'jsonencode({{"n": {giant_int}}})', {})
    assert (val, known) == (None, False)

    norm, norm_known = _normalise_policy_value(f'{{"n": {giant_int}}}')
    assert (norm, norm_known) == (None, False)


def test_tfhcl_variable_substitution_cap_and_resolve_depth_cap() -> None:
    variables = {"big": "x" * 1000}
    template = "${var.big}" * ((MAX_SUBSTITUTED_CHARS // 1000) + 5)
    substituted, ok = _substitute_variables(template, variables)
    assert substituted is None
    assert ok is False

    nested: Any = "leaf"
    for _ in range(MAX_RESOLVE_DEPTH + 5):
        nested = {"k": nested}
    with pytest.raises(RecursionError, match="nesting exceeds"):
        _resolve_value(nested, {})

    deep_json = json.dumps({"resource": {"aws_iam_role": {"r": {"name": nested}}}})
    parsed = parse_tf_hcl("main.tf.json", deep_json, limits=Limits())
    assert parsed.facts is None
    assert any(d.code == "D-TF-HCL-PARSE" for d in parsed.diagnostics)


# ------------------------------------------------------------------ 4. parsers/yaml_marked.py


def test_yaml_rejects_non_scalar_mapping_keys() -> None:
    for payload in ("[a, b]: value\n", "{a: b}: value\n"):
        marked, diagnostics = load_marked_document(payload, rel_path="bad.yml", limits=Limits())
        assert marked is None
        assert any(d.code == "D-YAML-PARSE" for d in diagnostics)


def test_yaml_caps_huge_hex_and_octal_integers_for_safe_json_serialization() -> None:
    huge_hex = "0x" + ("f" * 5000)
    huge_oct = "0" + ("7" * 5000)
    text = f"hex_val: {huge_hex}\noct_val: {huge_oct}\n"
    marked, diagnostics = load_marked_document(text, rel_path="ints.yml", limits=Limits())
    assert marked is not None
    assert not any(d.level.value == "error" for d in diagnostics)
    plain = to_plain(marked)
    assert isinstance(plain["hex_val"], str)
    assert isinstance(plain["oct_val"], str)
    # Must serialize cleanly without ValueError (4300-digit int-to-str limit)
    dumped = json.dumps(plain)
    assert huge_hex in dumped


# ------------------------------------------------------------------ 5. parsers/_json.py


def test_json_rejects_negative_depth_bypass_and_nonfinite_numbers() -> None:
    bypass = "]" * 100 + "[" * (MAX_JSON_DEPTH + 10) + "]" * (MAX_JSON_DEPTH + 10)
    assert _exceeds_depth(bypass, MAX_JSON_DEPTH) is True
    with pytest.raises(JsonDepthError):
        decode_json(bypass)

    for bad in ("NaN", "Infinity", "-Infinity", '{"x": 1e999}', '{"x": -1e999}'):
        with pytest.raises(ValueError, match="not allowed"):
            decode_json(bad)


# ------------------------------------------------------------------ 6. core/limits.py


def test_limits_from_mapping_enforces_hard_upper_ceilings() -> None:
    # Valid values up to 10x defaults remain accepted
    ok = Limits.from_mapping(
        {
            "max_files": 200_000,
            "max_yaml_depth": 640,
            "max_yaml_policy_file_bytes": 50 * MIB,
            "scenario_time_budget_seconds": 600.0,
        }
    )
    assert ok.max_files == 200_000
    assert ok.max_yaml_depth == 640

    # Values above 10x ceiling must be rejected
    for field_name, excessive in (
        ("max_files", 200_001),
        ("max_yaml_depth", 641),
        ("max_yaml_nodes", 2_000_001),
        ("alias_expansion_factor", 101),
        ("max_graph_nodes", 5_000_001),
        ("max_closure_depth", 31),
        ("max_composite_depth", 51),
        ("max_yaml_policy_file_bytes", 50 * MIB + 1),
        ("max_tf_json_bytes", 640 * MIB + 1),
        ("scenario_time_budget_seconds", 600.1),
    ):
        with pytest.raises(ValueError, match="at most"):
            Limits.from_mapping({field_name: excessive})


# ------------------------------------------------------------------ 7. discovery/walker.py


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="os.mkfifo not available on this platform")
def test_walker_rejects_fifo_named_pipes_without_hanging(tmp_path: Path) -> None:
    fifo_json = tmp_path / "trap.json"
    os.mkfifo(fifo_json)

    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    fifo_wf = wf_dir / "trap.yml"
    os.mkfifo(fifo_wf)

    # discover() sniffs .json via _peek_is_tf_json — must not hang on FIFO
    discovery = discover(tmp_path, limits=Limits())
    assert any(d.code == "D-IO-UNREADABLE" and d.file == "trap.json" for d in discovery.diagnostics)

    # InputLoader.load() must reject the workflow FIFO without hanging
    loader = InputLoader(PathGuard.create(tmp_path), Limits())
    assert loader.load(fifo_wf, FileKind.WORKFLOW) is None
    assert any(
        d.code == "D-IO-UNREADABLE" and d.file == ".github/workflows/trap.yml"
        for d in loader.diagnostics
    )


def test_walker_caps_visited_directories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    limits = Limits(max_files=5)
    # Ceiling is max(limits.max_files * 4, 10_000) == 10_000
    yielded = 0

    def fake_walk(root: Path, followlinks: bool = False) -> Any:
        nonlocal yielded
        del followlinks
        for i in range(15_000):
            yielded += 1
            yield (str(root / f"d{i}"), [], [])

    monkeypatch.setattr(os, "walk", fake_walk)
    found, truncated, _escaped = _walk(tmp_path, limits, PathGuard.create(tmp_path))
    assert found == ()
    assert truncated is True
    assert yielded == 10_001


# ------------------------------------------------------------------ 8. report/redaction.py


def test_redact_payload_redacts_secrets_inside_tuples() -> None:
    payload = {
        "flat_tuple": (FAKE_GH_TOKEN, "benign"),
        "nested": (("prefix " + FAKE_GH_TOKEN,), {"k": (FAKE_GH_TOKEN,)}),
    }
    cleaned = redact_payload(payload)
    assert isinstance(cleaned["flat_tuple"], tuple)
    assert isinstance(cleaned["nested"], tuple)
    assert isinstance(cleaned["nested"][0], tuple)
    assert isinstance(cleaned["nested"][1]["k"], tuple)
    assert FAKE_GH_TOKEN not in repr(cleaned)


# ------------------------------------------------------------------ 9. report/_text.py


def test_safe_text_strips_expanded_bidi_zw_and_ansi_dcs_sos_pm_apc() -> None:
    bidi_zw = "a\u200eb\u200fc\u061cd\u200be\u200cf\u200dg\ufeffh\u00adi\u2028j\u2029k"
    assert safe_text(bidi_zw) == "abcdefghijk"

    escape_payload = (
        "ok"
        "\x1bPdcs-payload\x1b\\"
        "\x1bXsos-payload\x1b\\"
        "\x1b^pm-payload\x1b\\"
        "\x1b_apc-payload\x1b\\"
        "end"
    )
    assert safe_text(escape_payload) == "okend"


# ------------------------------------------------------------------ 10. report/loader.py


def test_report_loader_rejects_deeply_nested_json(tmp_path: Path) -> None:
    deep_path = tmp_path / "deep-report.json"
    nested_json = "[" * (MAX_JSON_DEPTH + 10) + "]" * (MAX_JSON_DEPTH + 10)
    deep_path.write_text(nested_json, encoding="utf-8")
    with pytest.raises(ReportLoadError, match="nesting"):
        load_report(deep_path)


# ------------------------------------------------------------------ 11. whatif/run.py & render.py


def test_whatif_execute_redacts_loaded_report_and_sanitizes_console(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    scan_out = tmp_path / "scan-out"
    scan_result = CliRunner().invoke(
        app, ["scan", str(repo), "--format", "json", "--out", str(scan_out)]
    )
    assert scan_result.exit_code == 0, scan_result.output

    report_path = scan_out / "report.json"
    raw = json.loads(report_path.read_text(encoding="utf-8"))
    raw["inputs"]["repo_slug"] = f"org/{FAKE_GH_TOKEN}"
    report_path.write_text(json.dumps(raw), encoding="utf-8")

    out_dir = tmp_path / "whatif-out"
    outcome = execute_whatif(report_path, None, ("json", "md", "html"), out_dir, auto_plan=True)
    assert FAKE_GH_TOKEN not in outcome.console_text
    for artifact_path in outcome.written:
        assert FAKE_GH_TOKEN not in artifact_path.read_text(encoding="utf-8")


def test_whatif_console_summary_sanitizes_all_interpolated_fields() -> None:
    payload = {
        "steps": [{"status": "applied"}],
        "per_scenario": [
            {
                "selector": "sc\x1b[31m1\x1b[0m",
                "before": {"R": [], "E": [], "Z": []},
                "after": {
                    "R": [],
                    "E": [],
                    "Z": [],
                    "issued_before_containment": [],
                    "re_exposure_risk": [],
                    "revoked_access": [
                        {
                            "credential": "cred\u202e1",
                            "display_state": "active\x1bPevil\x1b\\",
                            "validity": "ok\x1b_apc\x1b\\",
                            "access": "yes\u200b",
                        }
                    ],
                },
                "future_reach": {"R": [], "E": [], "Z": []},
            }
        ],
        "rejected": [
            {
                "index": "0\x1b[31m",
                "type": "revoke\u200f",
                "reason": "bad\x1b^pm\x1b\\reason",
            }
        ],
        "warnings": [{"code": "W1\x1bXsos\x1b\\", "detail": "warn\u00addetail"}],
    }
    rendered = console_summary(payload)
    assert "\x1b" not in rendered
    assert "\u202e" not in rendered
    assert "\u200b" not in rendered
    assert "\u200f" not in rendered
    assert "\u00ad" not in rendered
    assert "evil" not in rendered
    assert "apc" not in rendered
    assert "pm" not in rendered
    assert "sos" not in rendered
    assert "badreason" in rendered
    assert "warndetail" in rendered
