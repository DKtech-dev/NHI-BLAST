"""Supply-chain policy checks for CI, audit automation and dependency locks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.security

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
CI_WORKFLOW = WORKFLOW_DIR / "ci.yml"
AUDIT_WORKFLOW = WORKFLOW_DIR / "audit.yml"
DEPENDABOT = REPO_ROOT / ".github" / "dependabot.yml"
ACTION_PIN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$")
VERSION_PIN = re.compile(r"^[A-Za-z0-9_.-]+==[A-Za-z0-9_.+-]+$")


def _load_workflow(path: Path) -> tuple[str, dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    document = yaml.safe_load(text)
    assert isinstance(document, dict)
    return text, document


def _workflow_paths() -> list[Path]:
    paths = sorted(WORKFLOW_DIR.glob("*.yml"))
    assert paths
    return paths


def test_every_workflow_action_is_pinned_to_a_full_commit() -> None:
    for path in _workflow_paths():
        text, document = _load_workflow(path)
        uses_lines = [
            line.strip() for line in text.splitlines() if "uses:" in line and "uses: ./" not in line
        ]
        assert uses_lines, path
        for line in uses_lines:
            assert re.search(r"#\s*v\d", line), f"{path.name}: missing version comment: {line}"

        jobs = document["jobs"]
        assert isinstance(jobs, dict)
        for job in jobs.values():
            assert isinstance(job, dict)
            steps = job["steps"]
            assert isinstance(steps, list)
            for step in steps:
                assert isinstance(step, dict)
                uses = step.get("uses")
                if uses is None:
                    continue
                assert isinstance(uses, str)
                if uses.startswith("./"):
                    continue
                assert ACTION_PIN.fullmatch(uses), f"{path.name}: unpinned action: {uses}"


def test_checkout_steps_do_not_persist_credentials() -> None:
    for path in _workflow_paths():
        _, document = _load_workflow(path)
        jobs = document["jobs"]
        assert isinstance(jobs, dict)
        for job in jobs.values():
            assert isinstance(job, dict)
            for step in job["steps"]:
                uses = step.get("uses", "")
                if isinstance(uses, str) and uses.startswith("actions/checkout@"):
                    options = step.get("with", {})
                    assert options.get("persist-credentials") is False, path.name


def test_all_workflows_are_read_only_and_never_use_pull_request_target() -> None:
    for path in _workflow_paths():
        _, document = _load_workflow(path)
        assert document["permissions"] == {"contents": "read"}, path.name
        jobs = document["jobs"]
        assert isinstance(jobs, dict)
        for job in jobs.values():
            assert isinstance(job, dict)
            assert "permissions" not in job, path.name

        triggers = document["on"]
        assert isinstance(triggers, dict), path.name
        assert "pull_request_target" not in triggers, path.name


def test_audit_workflow_is_scheduled_and_scans_both_locks() -> None:
    text, document = _load_workflow(AUDIT_WORKFLOW)
    triggers = document["on"]
    assert isinstance(triggers, dict)
    assert triggers["schedule"] == [{"cron": "17 3 * * 1"}]
    assert "workflow_dispatch" in triggers

    for required in (
        "--require-hashes -r requirements-audit.lock",
        "v2.7.0/osv-scanner_linux_amd64",
        "v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz",
        "requirements.lock",
        "requirements-dev.lock",
        ".gitleaks.toml",
        "python -m pip_audit -r requirements.lock",
        "python -m pip_audit -r requirements-dev.lock",
    ):
        assert required in text, required
    assert text.count("sha256sum -c -") == 2
    assert "python -m pip-audit" not in text


def test_no_build_isolation_installs_the_editable_helper() -> None:
    # Editable metadata generation imports the backend's editables helper, which
    # pip does not add when build isolation is disabled.
    text, _ = _load_workflow(CI_WORKFLOW)
    assert "--no-build-isolation -e " in text
    assert "hatchling editables" in text
    pins = dict(line.split("==", 1) for line in _lock_lines("requirements-dev.lock"))
    assert pins["editables"] == "0.6"


def test_dependabot_tracks_python_and_actions_weekly() -> None:
    document = yaml.safe_load(DEPENDABOT.read_text(encoding="utf-8"))
    assert document["version"] == 2
    updates = document["updates"]
    assert isinstance(updates, list)
    ecosystems = {update["package-ecosystem"] for update in updates}
    assert ecosystems == {"pip", "github-actions"}
    for update in updates:
        assert update["directory"] == "/"
        assert update["schedule"]["interval"] == "weekly"
        assert update["open-pull-requests-limit"] <= 5


def test_ci_installs_from_both_locks() -> None:
    text, _ = _load_workflow(CI_WORKFLOW)
    assert "-c requirements-dev.lock" in text
    assert "-c requirements.lock" in text
    assert "--no-build-isolation" in text


def _lock_lines(name: str) -> list[str]:
    lines = []
    for raw in (REPO_ROOT / name).read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return lines


@pytest.mark.parametrize("name", ["requirements.lock", "requirements-dev.lock"])
def test_locks_contain_only_exact_pins(name: str) -> None:
    lines = _lock_lines(name)
    assert lines
    for line in lines:
        assert VERSION_PIN.fullmatch(line), f"{name}: not an exact pin: {line}"
        assert "git+" not in line
        assert "http" not in line
        assert "-e " not in line


def test_audit_lock_pins_every_package_with_a_hash() -> None:
    text = (REPO_ROOT / "requirements-audit.lock").read_text(encoding="utf-8")
    package_lines = [line for line in text.splitlines() if line and not line.startswith((" ", "#"))]
    assert package_lines
    for line in package_lines:
        assert line.rstrip().endswith("\\"), line
        requirement = line.rstrip().removesuffix("\\").strip()
        name_version, _, marker = requirement.partition(";")
        assert VERSION_PIN.fullmatch(name_version.strip()), requirement
        if marker:
            assert marker.strip()
    assert text.count("--hash=sha256:") > len(package_lines)
    assert "bandit==1.9.4" in text
    assert "pip-audit==2.10.1" in text
    assert "git+" not in text
    assert "-e " not in text


def test_runtime_lock_does_not_contain_test_tooling() -> None:
    runtime = {line.split("==")[0].lower() for line in _lock_lines("requirements.lock")}
    assert "pytest" not in runtime
    assert "hypothesis" not in runtime
    assert "pydantic" in runtime
    assert "pyyaml" in runtime


def test_dev_lock_uses_an_advisory_free_pytest() -> None:
    pins = dict(line.split("==", 1) for line in _lock_lines("requirements-dev.lock"))
    version = pins["pytest"]
    major, minor, patch = (int(part) for part in version.split(".")[:3])
    assert (major, minor, patch) >= (9, 0, 3), "pytest 8.4.2 is affected by PYSEC-2026-1845"
