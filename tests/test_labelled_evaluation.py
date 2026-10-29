"""AUD-01: the recovered labelled synthetic evaluation is reproducible."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

PROJECT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT / "scripts" / "evaluate_labelled.py"
FIXTURES = PROJECT / "tests" / "fixtures" / "labelled"


@pytest.fixture(scope="module")
def harness() -> ModuleType:
    assert SCRIPT.is_file(), "the labelled evaluation script is not implemented"
    spec = importlib.util.spec_from_file_location("evaluate_labelled", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def summary(harness: ModuleType) -> dict[str, Any]:
    result: dict[str, Any] = harness.evaluate(FIXTURES)
    return result


def test_recovered_cases_match_expected_labels(summary: dict[str, Any]) -> None:
    assert summary["metrics"] == {
        "sample": 14,
        "TP": 8,
        "FP": 0,
        "FN": 0,
        "TN": 6,
        "precision": 1.0,
        "recall": 1.0,
    }
    assert summary["passed"] is True


def test_evaluation_is_deterministic(harness: ModuleType, summary: dict[str, Any]) -> None:
    repeated: dict[str, Any] = harness.evaluate(FIXTURES)
    assert json.dumps(repeated, sort_keys=True) == json.dumps(summary, sort_keys=True)


def test_synthetic_canary_never_reaches_serialized_outputs(summary: dict[str, Any]) -> None:
    literal = next(case for case in summary["cases"] if case["id"] == "synthetic-literal")
    assert literal["canary_absent"] is True


def test_manifest_and_case_directories_agree() -> None:
    manifest = json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))
    cases = manifest["cases"]
    names = [case["id"] for case in cases]
    assert len(names) == len(set(names)) == 14
    directories = sorted(path.name for path in FIXTURES.iterdir() if path.is_dir())
    assert directories == sorted(names)
    for case in cases:
        assert case["rule"].startswith("NHB-")
        assert isinstance(case["expected"], bool)
        assert case["rationale"].strip()
        assert (FIXTURES / case["id"] / ".github" / "workflows" / "build.yml").is_file()


def test_fixtures_do_not_embed_a_token_shaped_secret() -> None:
    token = re.compile(r"ghp_[A-Za-z0-9]{36}")
    for path in FIXTURES.rglob("*"):
        if path.is_file():
            assert token.search(path.read_text(encoding="utf-8")) is None, path
