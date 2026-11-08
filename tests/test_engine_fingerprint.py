"""Engine fingerprint: analysis output may only change together with ENGINE_SEMANTICS.

Two reports are comparable (diff) and replayable (what-if) only when the engine that made
them is the same. The registry maps each engine version to a digest of every fixture's
analysis output. If results change, bump ENGINE_SEMANTICS in nhi_blast/__init__.py and add
a NEW registry entry; entries for earlier versions are history and must not be edited.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nhi_blast import ENGINE_SEMANTICS
from nhi_blast.core.canonical import digest_of
from nhi_blast.pipeline import ScanOptions, run_scan

FIXTURES = Path(__file__).parent / "fixtures"
REGISTRY = Path(__file__).parent / "golden" / "engine-fingerprint.json"
SELECTORS = ("all-mutable-actions", "repo-write")
# A fixed list: adding a fixture for another feature must not change the fingerprint.
FIXTURE_NAMES = (
    "fx01-minimal",
    "fx02-exact-trust",
    "fx03-wildcard-trust",
    "fx04-environment",
    "fx05-pull-request",
    "fx06-composite",
    "fx07-incident",
    "fx08-tf-plan-unknowns",
    "fx09-no-id-token",
    "fx10-hcl-fallback",
    "fx11-rotation-cycle",
    "fx12-untrusted-checkout",
    "fx13-secrets-inherit",
    "fx14-hostile",
)


def _fixture_roots() -> list[Path]:
    return [FIXTURES / name for name in FIXTURE_NAMES]


def compute_fingerprint() -> tuple[str, dict[str, str]]:
    per_fixture: dict[str, str] = {}
    for root in _fixture_roots():
        report = run_scan(ScanOptions(root=root, repo_slug="acme/app", selectors=SELECTORS)).report
        payload = {
            "findings": [f.model_dump(mode="json") for f in report.findings],
            "scenarios": [s.model_dump(mode="json") for s in report.scenarios],
            "graph": report.graph.model_dump(mode="json"),
            "assumptions": sorted(item.id for item in report.assumptions),
        }
        per_fixture[root.name] = digest_of(payload)
    return digest_of(per_fixture), per_fixture


def _registry() -> dict[str, str]:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return {str(key): str(value) for key, value in data.items()}


def test_current_engine_version_is_registered() -> None:
    assert ENGINE_SEMANTICS in _registry(), (
        f"add an entry for ENGINE_SEMANTICS={ENGINE_SEMANTICS!r} to {REGISTRY.name}"
    )


@pytest.mark.golden
def test_analysis_output_matches_the_registered_engine_fingerprint() -> None:
    fingerprint, per_fixture = compute_fingerprint()
    expected = _registry()[ENGINE_SEMANTICS]
    changed = "" if fingerprint == expected else f"\nper fixture: {json.dumps(per_fixture)}"
    assert fingerprint == expected, (
        "analysis output changed without an ENGINE_SEMANTICS bump. If the change is "
        "intended, bump ENGINE_SEMANTICS and register the new fingerprint "
        f"{fingerprint}.{changed}"
    )


def test_fingerprint_is_stable_across_runs() -> None:
    assert compute_fingerprint()[0] == compute_fingerprint()[0]
