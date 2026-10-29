"""Read-only corpus verification and sequential, installed-CLI benchmarking.

Run this file with a Python environment containing jsonschema. No project package
is imported, no corpus content is executed, and schema references stay offline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from jsonschema import validators
from referencing import Registry

PROJECT = Path(__file__).resolve().parents[1]
SCHEMAS = {
    "json": PROJECT / "docs" / "schema" / "report.schema.json",
    "sarif": PROJECT / "docs" / "schema" / "sarif-2.1.0.schema.json",
}
ARTIFACTS = ("report.json", "report.sarif", "report.html")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_SLUG = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_RESERVED = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.IGNORECASE)
PROCESS_TIMEOUT = 300


class BenchmarkError(ValueError):
    """A fixed diagnostic code, never an untrusted parser/process error string."""


@dataclass(frozen=True)
class Dataset:
    metadata: dict[str, Any]
    root: Path
    expected: dict[str, dict[str, Any]]
    categories: dict[str, int]


def safe_relative(value: Any) -> str:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        msg = "unsafe_path"
        raise BenchmarkError(msg)
    parts = value.split("/")
    if any(
        part in {"", ".", ".."}
        or part.endswith((".", " "))
        or _RESERVED.match(part)
        or any(ord(char) < 32 or char in ':<>"|?*' for char in part)
        for part in parts
    ):
        msg = "unsafe_path"
        raise BenchmarkError(msg)
    return value


def check_path(path: Path) -> None:
    """Reject all symlinks/reparse points, including those in parent components."""
    if not path.is_absolute() or ".." in path.parts:
        msg = "unsafe_path"
        raise BenchmarkError(msg)
    for component in (*reversed(path.parents), path):
        try:
            info = component.lstat()
        except FileNotFoundError:
            msg = "missing_path"
            raise BenchmarkError(msg) from None
        if stat.S_ISLNK(info.st_mode) or (
            getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            msg = "link_path"
            raise BenchmarkError(msg)


def file_bytes(path: Path) -> bytes:
    check_path(path)
    if not stat.S_ISREG(path.lstat().st_mode):
        msg = "nonregular_file"
        raise BenchmarkError(msg)
    return path.read_bytes()


def digest(data: bytes) -> dict[str, Any]:
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def file_digest(path: Path) -> dict[str, Any]:
    return digest(file_bytes(path))


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            msg = "duplicate_json_key"
            raise BenchmarkError(msg)
        result[key] = value
    return result


def reject_constant(_value: str) -> Any:
    msg = "nonfinite_json"
    raise BenchmarkError(msg)


def decode_json(data: bytes | str) -> Any:
    try:
        return json.loads(data, object_pairs_hook=reject_duplicates, parse_constant=reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, BenchmarkError):
            raise
        msg = "invalid_json"
        raise BenchmarkError(msg) from None


def regular_inventory(root: Path) -> dict[str, dict[str, Any]]:
    check_path(root)
    if not root.is_dir():
        msg = "missing_dataset_directory"
        raise BenchmarkError(msg)
    result: dict[str, dict[str, Any]] = {}
    pending = [root]
    while pending:
        directory = pending.pop()
        for child in sorted(directory.iterdir()):
            check_path(child)
            relative = safe_relative(child.relative_to(root).as_posix())
            if not child.resolve().is_relative_to(root):
                msg = "unsafe_path_containment"
                raise BenchmarkError(msg)
            mode = child.lstat().st_mode
            if stat.S_ISDIR(mode):
                pending.append(child)
            elif stat.S_ISREG(mode):
                result[relative] = file_digest(child)
            else:
                msg = "nonregular_dataset_entry"
                raise BenchmarkError(msg)
    return dict(sorted(result.items()))


def input_categories(paths: list[str], iam: list[str]) -> dict[str, int]:
    """Inventory candidates, not claims of successful discovery or parsing."""
    return {
        "all_regular": len(paths),
        "workflows": sum(
            len(path.split("/")) == 3
            and path.startswith(".github/workflows/")
            and path.endswith((".yml", ".yaml"))
            for path in paths
        ),
        "actions": sum(Path(path).name in {"action.yml", "action.yaml"} for path in paths),
        "hcl": sum(path.endswith(".tf") for path in paths),
        "json": sum(path.endswith(".json") for path in paths),
        "iam_json": len(iam),
    }


def expected_files(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    files = metadata.get("files")
    if not isinstance(files, list):
        msg = "invalid_manifest_files"
        raise BenchmarkError(msg)
    result: dict[str, dict[str, Any]] = {}
    folded: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict):
            msg = "invalid_manifest_file"
            raise BenchmarkError(msg)
        path = safe_relative(entry.get("path"))
        size, sha = entry.get("bytes"), entry.get("sha256")
        if (
            type(size) is not int
            or size < 0
            or not isinstance(sha, str)
            or not _SHA256.fullmatch(sha)
        ):
            msg = "invalid_manifest_hash_size"
            raise BenchmarkError(msg)
        if path.casefold() in folded:
            msg = "duplicate_manifest_path"
            raise BenchmarkError(msg)
        folded.add(path.casefold())
        result[path] = {"bytes": size, "sha256": sha}
    return result


def verify_dataset(dataset: Dataset) -> None:
    actual = regular_inventory(dataset.root)
    if dataset.expected.keys() - actual.keys():
        msg = "missing_file"
        raise BenchmarkError(msg)
    if actual.keys() - dataset.expected.keys():
        msg = "extra_file"
        raise BenchmarkError(msg)
    for path, expected in dataset.expected.items():
        if actual[path]["bytes"] != expected["bytes"]:
            msg = "size_mismatch"
            raise BenchmarkError(msg)
        if actual[path]["sha256"] != expected["sha256"]:
            msg = "mutated_file"
            raise BenchmarkError(msg)


def validate_manifest(manifest: Path, datasets: Path) -> list[Dataset]:
    check_path(datasets)
    data = decode_json(file_bytes(manifest))
    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
        msg = "invalid_manifest_version"
        raise BenchmarkError(msg)
    entries = data.get("datasets")
    if not isinstance(entries, list) or not entries:
        msg = "invalid_manifest_datasets"
        raise BenchmarkError(msg)
    result: list[Dataset] = []
    ids: set[str] = set()
    slugs: set[str] = set()
    for metadata in entries:
        if not isinstance(metadata, dict):
            msg = "invalid_manifest_dataset"
            raise BenchmarkError(msg)
        identifier = safe_relative(metadata.get("id"))
        slug = metadata.get("slug")
        if not _ID.fullmatch(identifier) or not isinstance(slug, str) or not _SLUG.fullmatch(slug):
            msg = "invalid_manifest_identity"
            raise BenchmarkError(msg)
        if identifier.casefold() in ids or slug.casefold() in slugs:
            msg = "duplicate_manifest_dataset"
            raise BenchmarkError(msg)
        ids.add(identifier.casefold())
        slugs.add(slug.casefold())
        if type(metadata.get("external")) is not bool or not isinstance(
            metadata.get("selection"), dict
        ):
            msg = "invalid_manifest_metadata"
            raise BenchmarkError(msg)
        for key in ("repository", "revision", "license", "retrieved_on", "archive_sha256"):
            if not isinstance(metadata.get(key), str) or not metadata[key]:
                msg = "invalid_manifest_metadata"
                raise BenchmarkError(msg)
        if not _SHA256.fullmatch(metadata["archive_sha256"]):
            msg = "invalid_manifest_archive_hash"
            raise BenchmarkError(msg)
        expected = expected_files(metadata)
        iam = metadata.get("iam_json")
        if not isinstance(iam, list):
            msg = "invalid_manifest_iam"
            raise BenchmarkError(msg)
        iam = [safe_relative(path) for path in iam]
        if len(set(iam)) != len(iam) or any(path not in expected for path in iam):
            msg = "unlisted_manifest_iam"
            raise BenchmarkError(msg)
        root = datasets / identifier
        if not root.resolve().is_relative_to(datasets):
            msg = "unsafe_path_containment"
            raise BenchmarkError(msg)
        dataset = Dataset(metadata, root, expected, input_categories(list(expected), iam))
        verify_dataset(dataset)
        result.append(dataset)
    actual_ids: set[str] = set()
    for child in datasets.iterdir():
        check_path(child)
        if not child.is_dir():
            msg = "extra_dataset_entry"
            raise BenchmarkError(msg)
        actual_ids.add(child.name.casefold())
    if actual_ids != ids:
        msg = "extra_dataset_directory"
        raise BenchmarkError(msg)
    return sorted(result, key=lambda item: item.metadata["id"])


def load_validator(path: Path) -> Any:
    schema = decode_json(file_bytes(path))
    pending = [schema]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            for key in ("$ref", "$dynamicRef", "$recursiveRef"):
                if key in value and (
                    not isinstance(value[key], str) or not value[key].startswith("#")
                ):
                    msg = "schema_reference_not_local"
                    raise BenchmarkError(msg)
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    cls = validators.validator_for(schema)
    cls.check_schema(schema)
    # An empty Registry fails retrieval rather than using jsonschema's legacy URL loader.
    return cls(schema, registry=Registry())


class EmbeddedData(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.matches = 0
        self.collecting = False
        self.closed = False
        self.fragments: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script" and attributes.get("id") == "report-data":
            self.matches += 1
            self.collecting = attributes.get("type") == "application/json"

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.collecting:
            self.collecting = False
            self.closed = True

    def handle_data(self, data: str) -> None:
        if self.collecting:
            self.fragments.append(data)


def sarif_message(text: str) -> str:
    """Check the SARIF plain-text/4,000-character boundary on already redacted JSON."""
    text = re.sub(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])", "", text)
    text = re.sub(r"[\u202a-\u202e\u2066-\u2069]", "", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)
    text = re.sub(r"\s*\n\s*", " ", text)
    text = re.sub(r"[ \t\f\v]+", " ", text).strip()
    return text if len(text) <= 4000 else text[:3997].rstrip() + "..."


def finding_signature(finding: dict[str, Any]) -> tuple[Any, ...]:
    confidence_order = {"declared": 0, "derived": 1, "assumed": 2, "unknown": 3}
    evidence = sorted(
        finding.get("evidence", []),
        key=lambda item: (
            confidence_order[item["cls"]],
            item.get("file", ""),
            item["rule"],
            item.get("line", 0),
            item.get("end_line", 0),
            item.get("detail", ""),
        ),
    )
    primary: dict[str, Any] = next((item for item in evidence if item.get("file")), {})
    payload = "|".join(
        (finding["rule"], ",".join(sorted(finding.get("path", []))), primary.get("file", ""))
    )
    fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    levels = {
        "CRITICAL": "error",
        "HIGH": "error",
        "MEDIUM": "warning",
        "LOW": "note",
        "INFO": "note",
    }
    return (
        finding["rule"],
        fingerprint,
        levels[finding["severity"]],
        json.dumps(finding["confidence"], sort_keys=True),
        json.dumps(finding.get("assumptions", []), sort_keys=True),
        sarif_message(finding["message"]),
    )


def verify_sarif_correspondence(report: dict[str, Any], sarif: dict[str, Any]) -> None:
    runs = sarif["runs"]
    if len(runs) != 1:
        msg = "inconsistent_sarif_runs"
        raise BenchmarkError(msg)
    run = runs[0]
    driver = run["tool"]["driver"]
    if any(driver.get(key) != report["tool"][key] for key in ("name", "version")):
        msg = "inconsistent_sarif_tool"
        raise BenchmarkError(msg)
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    findings = sorted(
        report.get("findings", []),
        key=lambda item: (
            severity_order[item["severity"]],
            item["rule"],
            item["id"],
        ),
    )
    # The checked-in SARIF writer limits GitHub uploads to 5,000 sorted findings.
    expected = Counter(finding_signature(finding) for finding in findings[:5000])
    actual: Counter[tuple[Any, ...]] = Counter()
    rules = driver.get("rules", [])
    for result in run.get("results", []):
        index = result.get("ruleIndex", -1)
        if (
            type(index) is not int
            or index < 0
            or index >= len(rules)
            or rules[index].get("id") != result.get("ruleId")
        ):
            msg = "inconsistent_sarif_rule_index"
            raise BenchmarkError(msg)
        properties = result.get("properties", {})
        actual[
            (
                result.get("ruleId"),
                result.get("partialFingerprints", {}).get("nhiBlast/v1"),
                result.get("level"),
                json.dumps(properties.get("confidence"), sort_keys=True),
                json.dumps(properties.get("assumptions", []), sort_keys=True),
                result.get("message", {}).get("text"),
            )
        ] += 1
    if actual != expected:
        msg = "inconsistent_sarif_findings"
        raise BenchmarkError(msg)
    dropped = len(findings) - 5000
    if dropped > 0:
        notification = (
            f"{dropped} findings were omitted because GitHub accepts "
            "at most 5000 results per upload."
        )
        messages = [
            entry.get("message", {}).get("text")
            for invocation in run.get("invocations", [])
            for entry in invocation.get("toolExecutionNotifications", [])
        ]
        if notification not in messages:
            msg = "inconsistent_sarif_truncation"
            raise BenchmarkError(msg)


def verify_reference_integrity(report: dict[str, Any]) -> None:
    """Every identifier in the report must resolve to an object in that same report."""
    graph = report["graph"]
    nodes = {node["id"] for node in graph["nodes"]}
    edges = {edge["id"] for edge in graph["edges"]}
    findings = {finding["id"] for finding in report.get("findings", [])}
    if any(edge["src"] not in nodes or edge["dst"] not in nodes for edge in graph["edges"]):
        msg = "graph_reference_invalid"
        raise BenchmarkError(msg)
    for finding in report.get("findings", []):
        if any(item not in nodes for item in finding.get("path", [])):
            msg = "finding_node_reference_invalid"
            raise BenchmarkError(msg)
        if any(item not in edges for item in finding.get("path_edges", [])):
            msg = "finding_edge_reference_invalid"
            raise BenchmarkError(msg)
    scenario_owners: set[str] = set()
    for scenario in report.get("scenarios", []):
        scenario_owners.add("scenario:" + scenario["selector"])
        partition = scenario["partition"]
        credential_ids = [entry["credential"] for entry in partition["E"]]
        credential_ids.extend(entry["credential"] for entry in partition["Z"])
        if any(item not in nodes for item in scenario["start_nodes"]):
            msg = "scenario_start_reference_invalid"
            raise BenchmarkError(msg)
        if any(item not in nodes for item in partition["R"]) or any(
            item not in nodes for item in credential_ids
        ):
            msg = "scenario_credential_reference_invalid"
            raise BenchmarkError(msg)
        if any(item not in edges for item in scenario["potential"]):
            msg = "scenario_potential_edge_reference_invalid"
            raise BenchmarkError(msg)
        if any(item not in nodes for item in scenario["potential_nodes"]):
            msg = "scenario_potential_node_reference_invalid"
            raise BenchmarkError(msg)
        if any(item not in findings for item in scenario["findings"]):
            msg = "scenario_finding_reference_invalid"
            raise BenchmarkError(msg)
        plan = scenario["rotation_plan"]
        for phase in ("containment", "rotation", "verify"):
            for step in plan[phase]:
                if any(item["id"] not in nodes for item in step["credentials"]):
                    msg = "rotation_credential_reference_invalid"
                    raise BenchmarkError(msg)
                if any(item not in nodes for item in step["depends_on"]):
                    msg = "rotation_dependency_reference_invalid"
                    raise BenchmarkError(msg)
    owners = nodes | edges | findings | scenario_owners
    for assumption in report.get("assumptions", []):
        if any(item not in owners for item in assumption["used_by"]):
            msg = "assumption_reference_invalid"
            raise BenchmarkError(msg)


def validate_payloads(payloads: dict[str, bytes], checks: dict[str, Any]) -> dict[str, Any]:
    report = decode_json(payloads["report.json"])
    sarif = decode_json(payloads["report.sarif"])
    for name, value in (("json", report), ("sarif", sarif)):
        if next(checks[name].iter_errors(value), None) is not None:
            msg = "artifact_schema_invalid"
            raise BenchmarkError(msg)
    verify_reference_integrity(report)
    embedded = EmbeddedData()
    embedded.feed(payloads["report.html"].decode("utf-8"))
    embedded.close()
    if embedded.matches != 1 or not embedded.closed:
        msg = "artifact_html_data_invalid"
        raise BenchmarkError(msg)
    if decode_json("".join(embedded.fragments)) != report:
        msg = "inconsistent_html_json"
        raise BenchmarkError(msg)
    verify_sarif_correspondence(report, sarif)
    return {"report": report, "artifacts": {name: digest(data) for name, data in payloads.items()}}


def validate_artifacts(path: Path, checks: dict[str, Any] | None = None) -> dict[str, Any]:
    checks = checks or {name: load_validator(schema) for name, schema in SCHEMAS.items()}
    try:
        return validate_payloads({name: file_bytes(path / name) for name in ARTIFACTS}, checks)
    except (OSError, UnicodeError, RecursionError, KeyError, TypeError, BenchmarkError) as exc:
        code = str(exc) if isinstance(exc, BenchmarkError) else "read_or_structure_invalid"
        raise BenchmarkError("artifact_" + code) from None


def source_tree() -> dict[str, Any]:
    """Actual checkout hashes; not an assertion that the installed CLI matches it."""
    files = {
        "src/" + path: info
        for path, info in regular_inventory(PROJECT / "src").items()
        if "__pycache__" not in Path(path).parts and not path.endswith((".pyc", ".pyo"))
    }
    for relative in (
        "pyproject.toml",
        "requirements.lock",
        "requirements-dev.lock",
        "scripts/benchmark_corpus.py",
        "docs/schema/report.schema.json",
        "docs/schema/sarif-2.1.0.schema.json",
    ):
        files[relative] = file_digest(PROJECT / relative)
    files = dict(sorted(files.items()))
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "root": str(PROJECT),
        "files": files,
        "sha256": digest(canonical)["sha256"],
        "scope": "checkout src (excluding bytecode), harness, schemas, project and lock files",
        "installed_equivalence": "not asserted",
    }


def scan_command(cli: Path, dataset: Dataset, out: Path) -> list[str]:
    command = [
        str(cli),
        "scan",
        str(dataset.root),
        "--repo-slug",
        dataset.metadata["slug"],
        "--simulate-compromise",
        "all-mutable-actions",
    ]
    if dataset.categories["workflows"]:
        command.extend(("--simulate-compromise", "repo-write"))
    command.extend(
        (
            "--format",
            "json",
            "--format",
            "sarif",
            "--format",
            "html",
            "--fail-on",
            "never",
            "--out",
            str(out),
        )
    )
    for relative in sorted(dataset.metadata["iam_json"]):
        command.extend(("--iam-json", str(dataset.root / relative)))
    return command


def counts(values: list[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(value[key] for value in values).items()))


def report_metrics(report: dict[str, Any]) -> dict[str, Any]:
    graph = report.get("graph", {})
    nodes, edges = graph.get("nodes", []), graph.get("edges", [])
    return {
        "reported_tool": report["tool"],
        "input_digest": report["inputs"]["digest"],
        "input_categories": counts(report["inputs"].get("files", []), "kind"),
        "input_count": len(report["inputs"].get("files", [])),
        "graph": {
            "nodes": len(nodes),
            "edges": len(edges),
            "node_kinds": counts(nodes, "kind"),
            "edge_kinds": counts(edges, "kind"),
        },
        "findings": len(report.get("findings", [])),
        "rules": counts(report.get("findings", []), "rule"),
        "diagnostics": counts(report.get("diagnostics", []), "code"),
        "scenarios": [
            {
                "selector": scenario["selector"],
                "partition": scenario.get("partition", {}),
                "partition_counts": {
                    name: len(scenario.get("partition", {}).get(name, []))
                    for name in ("R", "E", "Z")
                },
                "start_nodes": len(scenario.get("start_nodes", [])),
                "potential": len(scenario.get("potential", [])),
                "potential_nodes": len(scenario.get("potential_nodes", [])),
                "unresolved_inputs": len(scenario.get("unresolved_inputs", [])),
                "truncated": scenario.get("truncated", False),
            }
            for scenario in report.get("scenarios", [])
        ],
    }


def run_scan(command: list[str], cwd: Path, checks: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    result: dict[str, Any] = {
        "command": command,
        "cwd": str(cwd),
        "exit": None,
        "validated": False,
        "errors": [],
    }
    stdout = stderr = b""
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    result["environment_overrides"] = {
        "PYTHONPATH": None,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }
    try:
        process = subprocess.run(  # noqa: S603 -- explicit installed executable, never shell
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            check=False,
            shell=False,
            timeout=PROCESS_TIMEOUT,
        )
        stdout, stderr = process.stdout, process.stderr
        result["exit"] = process.returncode
        if process.returncode:
            result["errors"].append("process_nonzero")
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, bytes) else b""
        stderr = exc.stderr if isinstance(exc.stderr, bytes) else b""
        result["errors"].append("process_timeout")
    except OSError:
        result["errors"].append("process_spawn_failure")
    result.update(
        elapsed_seconds=time.perf_counter() - started, stdout=digest(stdout), stderr=digest(stderr)
    )
    path = Path(command[command.index("--out") + 1])
    result["artifacts"] = {}
    for name in ARTIFACTS:
        try:
            result["artifacts"][name] = file_digest(path / name)
        except (OSError, BenchmarkError):
            result["errors"].append("artifact_unreadable_" + name)
    try:
        validated = validate_artifacts(path, checks)
        result.update(report_metrics(validated["report"]))
        result["validated"] = True
    except BenchmarkError as exc:
        result["errors"].append(str(exc))
    result["status"] = "FAIL" if result["errors"] else "PASS"
    return result


def prepare(cli: Path, datasets: Path, manifest: Path, out: Path, repeats: int) -> list[Dataset]:
    if not cli.is_absolute():
        msg = "cli_must_be_absolute"
        raise BenchmarkError(msg)
    if type(repeats) is not int or repeats < 1:
        msg = "repeats_must_be_positive"
        raise BenchmarkError(msg)
    check_path(cli)
    if not stat.S_ISREG(cli.lstat().st_mode) or cli.is_relative_to(datasets):
        msg = "cli_must_be_installed_regular_file"
        raise BenchmarkError(msg)
    check_path(out.parent)
    if os.path.lexists(out):
        msg = "stale_output"
        raise BenchmarkError(msg)
    for protected in (PROJECT, datasets):
        if out.is_relative_to(protected) or protected.is_relative_to(out):
            msg = "output_must_be_external_and_disjoint"
            raise BenchmarkError(msg)
    if cli.is_relative_to(out) or manifest.is_relative_to(out):
        msg = "output_overlaps_input"
        raise BenchmarkError(msg)
    return validate_manifest(manifest, datasets)


def identical_artifact_bytes(runs: list[dict[str, Any]]) -> bool:
    if len(runs) < 2 or not all(run["status"] == "PASS" and run["validated"] for run in runs):
        return False
    baseline: dict[str, bytes] = {}
    try:
        for run in runs:
            command = run["command"]
            path = Path(command[command.index("--out") + 1])
            for name in ARTIFACTS:
                data = file_bytes(path / name)
                if digest(data) != run["artifacts"][name]:
                    return False
                if name in baseline and data != baseline[name]:
                    return False
                baseline.setdefault(name, data)
    except (OSError, BenchmarkError):
        return False
    return True


def verify_final_inputs(manifest: Path, datasets: Path, expected_sha: str) -> None:
    validate_manifest(manifest, datasets)
    if file_digest(manifest)["sha256"] != expected_sha:
        msg = "manifest_mutated_during_run"
        raise BenchmarkError(msg)


def run_benchmark(
    cli: Path, datasets: Path, manifest: Path, out: Path, repeats: int = 2
) -> dict[str, Any]:
    cli = Path(cli)
    datasets, manifest, out = (Path(os.path.abspath(path)) for path in (datasets, manifest, out))
    corpus = prepare(cli, datasets, manifest, out, repeats)
    checks = {name: load_validator(path) for name, path in SCHEMAS.items()}
    summary: dict[str, Any] = {
        "format": "nhi-blast-corpus-benchmark/1",
        "status": "PASS",
        "deterministic": False,
        "repeats": repeats,
        "cli": {"path": str(cli), **file_digest(cli)},
        "manifest": {"path": str(manifest), **file_digest(manifest)},
        "schemas": {
            name: {"path": str(path), **file_digest(path)} for name, path in SCHEMAS.items()
        },
        "source_tree": source_tree(),
        "datasets_root": str(datasets),
        "datasets": [],
        "counts": {
            "external": sum(item.metadata["external"] for item in corpus),
            "self_controls": sum(not item.metadata["external"] for item in corpus),
            "regular_files": sum(len(item.expected) for item in corpus),
        },
    }
    out.mkdir()
    cwd = out / "cwd"
    cwd.mkdir()
    for dataset in corpus:
        row: dict[str, Any] = {
            "metadata": {key: value for key, value in dataset.metadata.items() if key != "files"},
            "root": str(dataset.root),
            "inventory_categories": dataset.categories,
            "runs": [],
        }
        for repeat in range(1, repeats + 1):
            verify_dataset(dataset)
            target = out / dataset.metadata["id"] / f"repeat-{repeat:02d}"
            if os.path.lexists(target):
                msg = "stale_repeat_output"
                raise BenchmarkError(msg)
            run = run_scan(scan_command(cli, dataset, target), cwd, checks)
            row["runs"].append(run)
        valid = all(run["status"] == "PASS" and run["validated"] for run in row["runs"])
        identical = identical_artifact_bytes(row["runs"])
        row["deterministic"] = identical
        row["status"] = "PASS" if valid and (repeats == 1 or identical) else "FAIL"
        row["errors"] = (
            ["nondeterministic_artifacts"] if valid and repeats >= 2 and not identical else []
        )
        summary["datasets"].append(row)
    try:
        verify_final_inputs(manifest, datasets, summary["manifest"]["sha256"])
        summary["input_integrity_after_run"] = "PASS"
    except BenchmarkError as exc:
        summary["input_integrity_after_run"] = str(exc)
        summary["status"] = "FAIL"
    if any(row["status"] == "FAIL" for row in summary["datasets"]):
        summary["status"] = "FAIL"
    summary["deterministic"] = (
        summary["status"] == "PASS"
        and repeats >= 2
        and all(row["deterministic"] for row in summary["datasets"])
    )
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", required=True, type=Path)
    parser.add_argument("--datasets", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()
    try:
        summary = run_benchmark(args.cli, args.datasets, args.manifest, args.out, args.repeats)
    except (BenchmarkError, OSError, RecursionError) as exc:
        code = str(exc) if isinstance(exc, BenchmarkError) else "io_or_recursion_failure"
        print("FAIL: " + code, file=sys.stderr)
        return 1
    print(
        f"{summary['status']}: {len(summary['datasets'])} datasets; "
        f"deterministic={str(summary['deterministic']).lower()}"
    )
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
