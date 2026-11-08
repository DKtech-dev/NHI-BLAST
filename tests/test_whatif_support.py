"""Shared builders for the what-if tests (no tests in this module)."""

from __future__ import annotations

import functools
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from nhi_blast.core.canonical import digest_of
from nhi_blast.core.models import Report
from nhi_blast.pipeline import ScanOptions, run_scan
from nhi_blast.report.json_report import write_json
from nhi_blast.whatif.engine import run_whatif
from nhi_blast.whatif.plan import parse_plan
from nhi_blast.whatif.playbook import render_playbook
from nhi_blast.whatif.render import whatif_json

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = Path(__file__).parent / "golden"
FX16 = FIXTURES / "fx16-containment"
SELECTORS = ("action:acme/build-helper@v1", "repo-write", "role:aws_iam_role.ci_deploy")
ACTION = SELECTORS[0]
REPO_WRITE = SELECTORS[1]
ROLE_SELECTOR = SELECTORS[2]
ROLE = "aws:role:arn:aws:iam::111122223333:role/ci-deploy"
OPS_ROLE = "aws:role:arn:aws:iam::111122223333:role/ops-admin"
JOB = "job:.github/workflows/deploy.yml#deploy"
OIDC = "oidc:job:.github/workflows/deploy.yml#deploy:sts.amazonaws.com"
SESSION = f"cred:{OIDC}:sts-session:{ROLE}"
DEPLOY_KEY = "cred:aws:secret:ci/deploy-key:stored"
REGISTRY_TOKEN = "cred:aws:ssm:/ci/registry-token:stored"
DB_PASSWORD = "cred:aws:secret:ops/db-password:stored"
REVOKED_AT = "2026-03-01T10:00:00Z"
ASSESSED_AT = "2026-03-01T10:05:00Z"
ISSUED = "2026-03-01T09:30:00Z"
FORBIDDEN = re.compile(r"deleted|invalidated|revoked credential|contained", re.IGNORECASE)


@functools.cache
def fx16_report() -> Report:
    return run_scan(ScanOptions(root=FX16, selectors=SELECTORS)).report


def scan(root: Path, selectors: tuple[str, ...] = SELECTORS, **kwargs: Any) -> Report:
    return run_scan(ScanOptions(root=root, selectors=selectors, **kwargs)).report


def save(report: Report, path: Path) -> Path:
    write_json(report, path)
    return path


def plan_of(*interventions: dict[str, Any]) -> Any:
    return parse_plan(
        {"schema": "nhi-blast-interventions/1.0", "interventions": list(interventions)}
    )


def run(report: Report, *interventions: dict[str, Any]) -> dict[str, Any]:
    return run_whatif(report, plan_of(*interventions))


def scenario(payload: dict[str, Any], selector: str) -> dict[str, Any]:
    found = next(item for item in payload["per_scenario"] if item["selector"] == selector)
    assert isinstance(found, dict)
    return found


def revoke(**extra: Any) -> dict[str, Any]:
    return {"type": "revoke_role_sessions", "role": ROLE, **extra}


def remove_oidc_trust() -> dict[str, Any]:
    return {"type": "remove_trust", "role": ROLE, "principal": OIDC}


def disable_job() -> dict[str, Any]:
    return {"type": "disable_entrypoint", "node": JOB}


def rotate(credential: str) -> dict[str, Any]:
    return {"type": "rotate_credential", "credential": credential}


def outputs(report: Report, *interventions: dict[str, Any]) -> tuple[str, str]:
    payload = run(report, *interventions)
    return whatif_json(payload), render_playbook(report, payload)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plan_digest(*interventions: dict[str, Any]) -> str:
    return digest_of(
        {"schema": "nhi-blast-interventions/1.0", "interventions": list(interventions)}
    )


def write_plan(path: Path, *interventions: dict[str, Any]) -> Path:
    document = {"schema": "nhi-blast-interventions/1.0", "interventions": list(interventions)}
    path.write_text(json.dumps(document), encoding="utf-8")
    return path
