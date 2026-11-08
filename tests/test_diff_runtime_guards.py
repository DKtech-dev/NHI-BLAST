"""Comparison context validation must remain conservative under optimized Python."""

from __future__ import annotations

import pytest

from nhi_blast.diff.compare import _analyzer_drift
from tests.test_diff_support import base_report


@pytest.mark.parametrize(
    ("base_missing", "head_missing"), [(True, False), (False, True), (True, True)]
)
def test_analyzer_drift_handles_missing_context_without_runtime_assertions(
    base_missing: bool, head_missing: bool
) -> None:
    base = base_report()
    head = base_report()
    if base_missing:
        base = base.model_copy(update={"context": None})
    if head_missing:
        head = head.model_copy(update={"context": None})
    drift = _analyzer_drift(base, head)
    assert drift == [
        {
            "code": "schema_changed",
            "field": "context",
            "base": "no-context" if base_missing else base.schema_id,
            "head": "no-context" if head_missing else head.schema_id,
        }
    ]
