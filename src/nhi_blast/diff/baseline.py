"""Reviewed baseline (nhi-blast-baseline/1.0) and the exit-code gate.

A baseline entry suppresses a *new* finding for the exit-code decision only. It never hides
drift, diagnostics, completeness or the finding itself. Nothing here reads the wall clock:
expiry is evaluated against a date the user supplies. The file is only ever written by an
explicit command.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from nhi_blast.core.artifact_io import (
    ArtifactCleanupError,
    ArtifactOutputError,
    ArtifactReadError,
    InputIdentity,
    read_bounded_utf8,
    write_artifacts,
)
from nhi_blast.core.models import Severity, severity_at_least
from nhi_blast.diff.compare import DIFF_SCHEMA
from nhi_blast.report._text import safe_text

BASELINE_SCHEMA = "nhi-blast-baseline/1.0"
CODE_BASELINE_EXPIRED = "D-DIFF-BASELINE-EXPIRED"
CODE_BASELINE_MISMATCH = "D-DIFF-BASELINE-MISMATCH"
_MAX_FILE_BYTES = 8 * 1024 * 1024
_MAX_DIFF_BYTES = 256 * 1024 * 1024
_MAX_ENTRIES = 100_000
_HEX64 = re.compile(r"[0-9a-f]{64}")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

Text = Annotated[str, StringConstraints(min_length=1, max_length=500)]


class BaselineError(ValueError):
    """The baseline or diff file cannot be read, is invalid, or the command cannot apply."""


class BaselineOutputError(BaselineError):
    """Baseline output failed or committed output needs staging cleanup."""


class BaselineEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lk: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    rule: Text
    scenario: Annotated[str, StringConstraints(max_length=500)] | None = None
    reason: Text
    reviewer: Text
    expires: Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")] | None = None


class Baseline(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    schema_id: str = Field(default=BASELINE_SCHEMA, alias="schema", serialization_alias="schema")
    created_from_report_digest: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    entries: tuple[BaselineEntry, ...] = Field(default=(), max_length=_MAX_ENTRIES)


def parse_date(text: str, label: str) -> date:
    if _DATE.fullmatch(text) is None:
        msg = f"{label} must be a YYYY-MM-DD date"
        raise BaselineError(msg)
    try:
        return date.fromisoformat(text)
    except ValueError:
        msg = f"{label} is not a valid calendar date"
        raise BaselineError(msg) from None


def _read_text_with_identity(path: Path, limit: int, label: str) -> tuple[str, InputIdentity]:
    try:
        return read_bounded_utf8(path, limit)
    except ArtifactReadError as exc:
        msg = f"cannot read {label}: {exc}"
        raise BaselineError(msg) from None


def _read_text(path: Path, limit: int, label: str) -> str:
    text, _identity = _read_text_with_identity(path, limit, label)
    return text


def load_baseline(path: Path) -> Baseline:
    baseline, _identity = load_baseline_with_identity(path)
    return baseline


def load_baseline_with_identity(path: Path) -> tuple[Baseline, InputIdentity]:
    text, identity = _read_text_with_identity(path, _MAX_FILE_BYTES, "baseline file")
    try:
        baseline = Baseline.model_validate_json(text)
    except ValidationError as exc:
        location = ".".join(str(part) for part in exc.errors()[0]["loc"]) if exc.errors() else ""
        msg = f"baseline file is not valid nhi-blast-baseline/1.0 JSON at {location or 'document'}"
        raise BaselineError(msg) from None
    except RecursionError:
        msg = "baseline file is nested too deeply"
        raise BaselineError(msg) from None
    if baseline.schema_id != BASELINE_SCHEMA:
        msg = f"unsupported baseline schema: {safe_text(baseline.schema_id, 80)}"
        raise BaselineError(msg)
    seen: set[str] = set()
    for entry in baseline.entries:
        if entry.lk in seen:
            msg = f"baseline file lists {entry.lk[:12]} more than once"
            raise BaselineError(msg)
        seen.add(entry.lk)
        if entry.expires is not None:
            parse_date(entry.expires, "baseline expires")
    return baseline, identity


def baseline_text(baseline: Baseline) -> str:
    """Deterministic file text: entries sorted by key, sorted keys, no timestamps."""
    entries = sorted(baseline.entries, key=lambda item: item.lk)
    payload: dict[str, Any] = {
        "schema": BASELINE_SCHEMA,
        "created_from_report_digest": baseline.created_from_report_digest,
        "entries": [item.model_dump(mode="json", exclude_none=True) for item in entries],
    }
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_baseline(path: Path, baseline: Baseline, *, inputs: Sequence[InputIdentity] = ()) -> None:
    try:
        write_artifacts([(path, baseline_text(baseline).encode("utf-8"))], inputs=inputs)
    except ArtifactCleanupError as exc:
        raise BaselineOutputError(str(exc)) from None
    except ArtifactOutputError as exc:
        msg = f"cannot write baseline file: {exc}"
        raise BaselineOutputError(msg) from None


# ------------------------------------------------------------------------ diff files


def load_diff(path: Path) -> dict[str, Any]:
    diff, _identity = load_diff_with_identity(path)
    return diff


def load_diff_with_identity(path: Path) -> tuple[dict[str, Any], InputIdentity]:
    text, identity = _read_text_with_identity(path.expanduser(), _MAX_DIFF_BYTES, "diff file")
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, RecursionError):
        msg = "diff file is not valid JSON"
        raise BaselineError(msg) from None
    if not isinstance(data, dict) or data.get("schema") != DIFF_SCHEMA:
        msg = f"diff file is not an {DIFF_SCHEMA} document"
        raise BaselineError(msg)
    findings = data.get("findings")
    head = data.get("head")
    if (
        not isinstance(findings, list)
        or not all(isinstance(item, dict) for item in findings)
        or not isinstance(head, dict)
        or not isinstance(head.get("report_digest"), str)
    ):
        msg = "diff file is missing findings or the head report digest"
        raise BaselineError(msg)
    return data, identity


def _finding_with(diff: Mapping[str, Any], lk: str, klass: str) -> dict[str, Any] | None:
    for item in diff["findings"]:
        if item.get("lk") == lk and item.get("class") == klass:
            found: dict[str, Any] = item
            return found
    return None


def accept_entry(
    existing: Baseline | None,
    diff: Mapping[str, Any],
    *,
    lk: str,
    reason: str,
    reviewer: str,
    expires: str | None,
) -> Baseline:
    """Add an entry for a finding that is NEW in the given diff. Never edits an existing entry."""
    if _HEX64.fullmatch(lk) is None:
        msg = "LK must be a 64-character lowercase hex logical key"
        raise BaselineError(msg)
    finding = _finding_with(diff, lk, "new")
    if finding is None:
        msg = "LK is not a new finding in the given diff; only new findings can be accepted"
        raise BaselineError(msg)
    clean_reason = safe_text(reason, 500)
    clean_reviewer = safe_text(reviewer, 200)
    if not clean_reason or not clean_reviewer:
        msg = "reason and reviewer must not be empty"
        raise BaselineError(msg)
    if expires is not None:
        parse_date(expires, "--expires")
    current = existing or Baseline(created_from_report_digest=diff["head"]["report_digest"])
    if any(entry.lk == lk for entry in current.entries):
        msg = "LK is already in the baseline; remove or edit the entry deliberately"
        raise BaselineError(msg)
    entry = BaselineEntry(
        lk=lk,
        rule=safe_text(finding.get("rule", ""), 500) or "unknown",
        scenario=finding.get("scenario") if isinstance(finding.get("scenario"), str) else None,
        reason=clean_reason,
        reviewer=clean_reviewer,
        expires=expires,
    )
    return current.model_copy(update={"entries": (*current.entries, entry)})


def prune_entries(
    baseline: Baseline, diff: Mapping[str, Any]
) -> tuple[Baseline, tuple[BaselineEntry, ...]]:
    """Drop only the entries whose finding is "resolved" in the diff."""
    resolved = {
        item.get("lk")
        for item in diff["findings"]
        if item.get("class") == "resolved" and isinstance(item.get("lk"), str)
    }
    removed = tuple(entry for entry in baseline.entries if entry.lk in resolved)
    kept = tuple(entry for entry in baseline.entries if entry.lk not in resolved)
    return baseline.model_copy(update={"entries": kept}), removed


# ---------------------------------------------------------------------------- gate


def apply_gate(
    payload: Mapping[str, Any],
    baseline: Baseline | None,
    *,
    fail_on: Severity | None,
    as_of: date | None,
) -> dict[str, Any]:
    """Add the baseline and exit-code sections; the findings themselves are never removed."""
    result: dict[str, Any] = copy.deepcopy(dict(payload))
    entries = {} if baseline is None else {entry.lk: entry for entry in baseline.entries}
    diagnostics: list[dict[str, Any]] = []
    expired: set[str] = set()
    for lk in sorted(entries):
        expires = entries[lk].expires
        if (
            as_of is not None
            and expires is not None
            and parse_date(expires, "baseline expires") <= as_of
        ):
            expired.add(lk)
            diagnostics.append({"code": CODE_BASELINE_EXPIRED, "lk": lk, "expires": expires})
    suppressed: list[str] = []
    blocking: list[str] = []
    for record in result["findings"]:
        record["suppressed_by_baseline"] = False
        if record["class"] != "new":
            continue
        accepted = entries.get(record["lk"])
        active = accepted is not None and record["lk"] not in expired
        if accepted is not None and accepted.rule != record["rule"]:
            active = False
            diagnostics.append({"code": CODE_BASELINE_MISMATCH, "lk": record["lk"]})
        if active:
            record["suppressed_by_baseline"] = True
            suppressed.append(record["lk"])
            continue
        if fail_on is not None and severity_at_least(Severity(record["severity"]), fail_on):
            blocking.append(record["lk"])
    result["diagnostics"]["baseline"] = diagnostics
    incomparable = result["comparability"]["status"] == "incomparable"
    exit_code = 3 if incomparable else (1 if blocking else 0)
    result["gate"] = {
        "fail_on": None if fail_on is None else fail_on.value,
        "as_of": None if as_of is None else as_of.isoformat(),
        "baseline_entries": len(entries),
        "suppressed": sorted(set(suppressed)),
        "blocking": sorted(set(blocking)),
        "expired": sorted(expired),
        "exit_code": exit_code,
    }
    return result
