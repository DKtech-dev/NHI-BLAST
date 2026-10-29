"""End-to-end scan pipeline connecting discovery, analysis and reporters (M6)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from nhi_blast import SCHEMA_VERSION, __version__
from nhi_blast.analysis.findings import build_findings, filter_findings
from nhi_blast.analysis.rank import rank_mutable_actions
from nhi_blast.analysis.scenario import ScenarioAnalysis, analyze_scenario
from nhi_blast.analysis.selectors import (
    SelectorError,
    SelectorKind,
    mutable_action_scenarios,
    parse_selector,
    resolve_starts,
)
from nhi_blast.core.config import CONFIG_FILENAME, Config, ConfigError
from nhi_blast.core.data import DataFileError, all_data_file_infos, assumptions
from nhi_blast.core.diagnostics import Diagnostic, DiagnosticBag, DiagnosticLevel, warning
from nhi_blast.core.ids import digest_pairs
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import (
    NODE_KIND_ORDER,
    AssumptionUse,
    DataFileInfo,
    Edge,
    Finding,
    GraphData,
    InputFile,
    Inputs,
    RankReport,
    Report,
    ScenarioReport,
    Severity,
    ToolInfo,
    severity_at_least,
)
from nhi_blast.discovery.paths import OutsideRootError, PathGuard
from nhi_blast.discovery.repo import RepoIdentity, resolve_identity
from nhi_blast.discovery.walker import (
    FileKind,
    InputLoader,
    LoadedText,
    discover,
)
from nhi_blast.graph.builder import GraphBuild, GraphInputs, build_graph
from nhi_blast.parsers.gha.facts import CompositeActionFact, WorkflowFact
from nhi_blast.parsers.gha.workflow import parse_composite_action, parse_workflow
from nhi_blast.parsers.iam.policy_doc import parse_iam_document
from nhi_blast.parsers.terraform.facts import IamDocumentFact, TfModelFact
from nhi_blast.parsers.terraform.tfhcl import parse_tf_hcl
from nhi_blast.parsers.terraform.tfjson import parse_tf_json
from nhi_blast.report._text import safe_text
from nhi_blast.report.console import render_console
from nhi_blast.report.graph_export import graph_export_dot, graph_export_json
from nhi_blast.report.html import write_html
from nhi_blast.report.json_report import write_json
from nhi_blast.report.rank import render_rank_console, write_rank_json
from nhi_blast.report.sarif import write_sarif
from nhi_blast.resolvers.composite import ExpandedJob, expand_jobs
from nhi_blast.resolvers.roles import CloudFacts, resolve_cloud_facts

STALE_AFTER_DAYS = 180
_MAX_AGE_SUFFIX = "more than 180 days"


class PipelineError(Exception):
    """Base class for operational failures surfaced by the CLI."""


class UsageError(PipelineError):
    """Invalid invocation, configuration or selector (CLI exit code 2)."""


class OutputError(PipelineError):
    """An output artifact could not be written (CLI exit code 4)."""


class OutputFormat(StrEnum):
    CONSOLE = "console"
    JSON = "json"
    SARIF = "sarif"
    HTML = "html"


class RankFormat(StrEnum):
    CONSOLE = "console"
    JSON = "json"


class ExportFormat(StrEnum):
    JSON = "json"
    DOT = "dot"


@dataclass(frozen=True, slots=True)
class SourceOptions:
    root: Path
    tf_json: tuple[Path, ...] = ()
    tf_hcl: bool | None = None
    iam_json: tuple[Path, ...] = ()
    repo_slug: str | None = None
    default_branch: str | None = None
    aws_account: str | None = None
    aws_region: str | None = None
    config_path: Path | None = None
    strict: bool = False


@dataclass(frozen=True, slots=True)
class ScanOptions(SourceOptions):
    selectors: tuple[str, ...] = ()
    formats: tuple[str, ...] = (OutputFormat.CONSOLE.value,)
    out_dir: Path = Path("nhi-blast-out")
    fail_on: Severity | None = None
    max_depth: int | None = None
    timestamp: bool = False


@dataclass(frozen=True, slots=True)
class RankOptions(SourceOptions):
    fmt: str = RankFormat.CONSOLE.value
    out_dir: Path = Path("nhi-blast-out")
    max_depth: int | None = None


@dataclass(frozen=True, slots=True)
class ExportOptions(SourceOptions):
    fmt: str = ExportFormat.JSON.value
    out_dir: Path = Path("nhi-blast-out")
    timestamp: bool = False


@dataclass(frozen=True, slots=True)
class ParsedRepository:
    root: Path
    identity: RepoIdentity
    config: Config
    limits: Limits
    inputs: Inputs
    workflows: tuple[WorkflowFact, ...]
    composites: tuple[CompositeActionFact, ...]
    tf_models: tuple[TfModelFact, ...]
    iam_documents: tuple[IamDocumentFact, ...]
    expanded_jobs: tuple[ExpandedJob, ...]
    cloud: CloudFacts
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True, slots=True)
class ScanOutcome:
    report: Report
    exit_code: int
    console_text: str
    written: tuple[Path, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RankOutcome:
    report: RankReport
    exit_code: int
    console_text: str
    written: tuple[Path, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ExportOutcome:
    exit_code: int
    text: str
    written: tuple[Path, ...] = field(default_factory=tuple)
    node_count: int = 0
    edge_count: int = 0


# --------------------------------------------------------------------- validation


def parse_fail_on(text: str) -> Severity | None:
    normalized = text.strip().lower()
    if normalized == "never":
        return None
    if normalized not in {"critical", "high", "medium", "low"}:
        msg = "unsupported --fail-on level; choose critical, high, medium, low or never"
        raise UsageError(msg)
    return Severity(normalized.upper())


def _normalise_formats(values: Sequence[str]) -> tuple[OutputFormat, ...]:
    requested: set[OutputFormat] = set()
    for raw in values:
        try:
            requested.add(OutputFormat(raw.strip().lower()))
        except ValueError:
            msg = f"unsupported --format {raw!r}; choose console, json, sarif or html"
            raise UsageError(msg) from None
    if not requested:
        requested.add(OutputFormat.CONSOLE)
    return tuple(fmt for fmt in OutputFormat if fmt in requested)


def _rank_format(raw: str) -> RankFormat:
    try:
        return RankFormat(raw.strip().lower())
    except ValueError:
        msg = f"unsupported rank --format {raw!r}; choose console or json"
        raise UsageError(msg) from None


def _export_format(raw: str) -> ExportFormat:
    normalized = raw.strip().lower()
    if normalized == "opengraph":
        msg = "opengraph export is Phase 2 and is not available in this build"
        raise UsageError(msg)
    try:
        return ExportFormat(normalized)
    except ValueError:
        msg = f"unsupported export --format {raw!r}; choose json or dot"
        raise UsageError(msg) from None


def _effective_depth(value: int | None, limits: Limits) -> int:
    depth = limits.max_closure_depth if value is None else value
    if isinstance(depth, bool) or depth < 0:
        msg = "--max-depth must be a non-negative integer"
        raise UsageError(msg)
    return int(depth)


def _resolve_root(path: Path) -> Path:
    candidate = path.expanduser()
    try:
        root = candidate.resolve(strict=True)
    except OSError as exc:
        msg = f"scan path is not accessible: {path} ({exc.strerror or exc})"
        raise UsageError(msg) from None
    if not root.is_dir():
        msg = f"scan path is not a directory: {path}"
        raise UsageError(msg)
    return root


def _require_inside_file(path: Path, guard: PathGuard, flag: str) -> Path:
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    try:
        resolved = guard.require_inside(candidate)
    except (OSError, OutsideRootError):
        msg = f"{flag} path must be inside the scan root: {path}"
        raise UsageError(msg) from None
    if not resolved.is_file():
        msg = f"{flag} file does not exist or is not a file: {path}"
        raise UsageError(msg)
    return resolved


def _load_config(root: Path, guard: PathGuard, explicit: Path | None) -> tuple[Config, Path | None]:
    if explicit is not None:
        resolved = _require_inside_file(explicit, guard, "--config")
        try:
            return Config.from_file(resolved), resolved
        except ConfigError as exc:
            raise UsageError(str(exc)) from None
    default = root / CONFIG_FILENAME
    if not default.exists():
        return Config.empty(), None
    try:
        resolved_default = guard.require_inside(default)
    except (OSError, OutsideRootError):
        msg = f"the default configuration file resolves outside the scan root: {CONFIG_FILENAME}"
        raise UsageError(msg) from None
    if not resolved_default.is_file():
        msg = f"configuration path is not a file: {CONFIG_FILENAME}"
        raise UsageError(msg)
    try:
        return Config.from_file(resolved_default), resolved_default
    except ConfigError as exc:
        raise UsageError(str(exc)) from None


# ------------------------------------------------------------------- repository


def _parse_files(
    loaded: Sequence[LoadedText], limits: Limits, diagnostics: DiagnosticBag
) -> tuple[
    tuple[WorkflowFact, ...],
    tuple[CompositeActionFact, ...],
    tuple[TfModelFact, ...],
    tuple[IamDocumentFact, ...],
]:
    workflows: list[WorkflowFact] = []
    composites: list[CompositeActionFact] = []
    models: list[TfModelFact] = []
    documents: list[IamDocumentFact] = []
    for item in loaded:
        if item.kind is FileKind.WORKFLOW:
            parsed = parse_workflow(item.rel, item.text, limits=limits)
            diagnostics.extend(parsed.diagnostics)
            if parsed.facts is not None:
                workflows.append(parsed.facts)
        elif item.kind is FileKind.COMPOSITE_ACTION:
            parsed_action = parse_composite_action(item.rel, item.text, limits=limits)
            diagnostics.extend(parsed_action.diagnostics)
            if parsed_action.facts is not None:
                composites.append(parsed_action.facts)
        elif item.kind is FileKind.TF_JSON:
            parsed_json = parse_tf_json(item.rel, item.text, limits=limits)
            diagnostics.extend(parsed_json.diagnostics)
            if parsed_json.facts is not None:
                models.append(parsed_json.facts)
        elif item.kind is FileKind.TF_HCL:
            parsed_hcl = parse_tf_hcl(item.rel, item.text, limits=limits)
            diagnostics.extend(parsed_hcl.diagnostics)
            if parsed_hcl.facts is not None:
                models.append(parsed_hcl.facts)
        elif item.kind is FileKind.IAM_JSON:
            document, iam_diagnostics = parse_iam_document(
                item.text, label=item.rel, kind=FileKind.IAM_JSON.value
            )
            diagnostics.extend(iam_diagnostics)
            if document is not None:
                documents.append(document)
    return (
        tuple(sorted(workflows, key=lambda item: item.path)),
        tuple(sorted(composites, key=lambda item: item.path)),
        tuple(sorted(models, key=lambda item: (item.source.value, item.file))),
        tuple(sorted(documents, key=lambda item: item.label)),
    )


def load_repository(options: SourceOptions) -> ParsedRepository:
    """Discover, read and parse one repository without running scenarios."""
    root = _resolve_root(options.root)
    try:
        guard = PathGuard.create(root)
    except OutsideRootError as exc:
        raise UsageError(str(exc)) from None
    base_config, config_path = _load_config(root, guard, options.config_path)
    config = base_config.with_identity(
        repo_slug=options.repo_slug,
        default_branch=options.default_branch,
        aws_account=options.aws_account,
        aws_region=options.aws_region,
    )
    limits = config.limits()
    identity = resolve_identity(
        root=root,
        cli_repo_slug=options.repo_slug,
        cli_default_branch=options.default_branch,
        config_repo_slug=base_config.repo_slug,
        config_default_branch=base_config.default_branch,
    )
    extra_tf = tuple(
        dict.fromkeys(_require_inside_file(item, guard, "--tf-json") for item in options.tf_json)
    )
    extra_iam = tuple(
        dict.fromkeys(_require_inside_file(item, guard, "--iam-json") for item in options.iam_json)
    )
    try:
        discovery = discover(
            root,
            limits=limits,
            extra_tf_json=extra_tf,
            extra_iam_json=extra_iam,
            config_path=config_path,
            hcl_enabled=True,
        )
    except ValueError as exc:
        raise UsageError(str(exc)) from None
    has_tf_json = any(item.kind is FileKind.TF_JSON for item in discovery.files)
    hcl_enabled = options.tf_hcl if options.tf_hcl is not None else not has_tf_json
    selected = tuple(
        item for item in discovery.files if hcl_enabled or item.kind is not FileKind.TF_HCL
    )
    loader = InputLoader(guard=guard, limits=limits)
    for item in selected:
        loader.load(item.path, item.kind)
    if identity.source == ".git/config":
        git_config = root / ".git" / "config"
        if git_config.is_file():
            loader.load(git_config, FileKind.GIT_CONFIG)
    diagnostics = DiagnosticBag(discovery.diagnostics)
    diagnostics.extend(loader.diagnostics)
    loaded = loader.loaded_inputs()
    workflows, composites, models, documents = _parse_files(loaded, limits, diagnostics)
    composite_map = {item.path: item for item in composites}
    expanded = expand_jobs(workflows, composite_map, limits=limits)
    for job in expanded:
        diagnostics.extend(job.diagnostics)
    cloud = resolve_cloud_facts(models, documents, config=config)
    diagnostics.extend(cloud.diagnostics)
    input_files = tuple(
        InputFile(path=item.rel, sha256=item.sha256, kind=item.kind.value) for item in loaded
    )
    inputs = Inputs(
        digest=digest_pairs((item.path, item.sha256) for item in input_files),
        repo_slug=identity.slug or "*/*",
        repo_slug_source=identity.source,
        files=input_files,
    )
    return ParsedRepository(
        root=root,
        identity=identity,
        config=config,
        limits=limits,
        inputs=inputs,
        workflows=workflows,
        composites=composites,
        tf_models=models,
        iam_documents=documents,
        expanded_jobs=expanded,
        cloud=cloud,
        diagnostics=diagnostics.sorted(),
    )


def build_repository_graph(parsed: ParsedRepository) -> GraphBuild:
    return build_graph(
        GraphInputs(
            repository=parsed.identity,
            workflows=parsed.workflows,
            expanded_jobs=parsed.expanded_jobs,
            cloud=parsed.cloud,
            config=parsed.config,
            limits=parsed.limits,
        )
    )


# ---------------------------------------------------------------------- analysis


def _scenario_targets(
    parsed: ParsedRepository, graph: GraphData, options: ScanOptions
) -> tuple[tuple[str, SelectorKind, tuple[str, ...]], ...]:
    targets: dict[str, tuple[SelectorKind, tuple[str, ...]]] = {}
    for raw in sorted(set(options.selectors)):
        try:
            selector = parse_selector(raw)
            if selector.kind is SelectorKind.ALL_MUTABLE_ACTIONS:
                for label, starts in mutable_action_scenarios(graph):
                    targets.setdefault(label, (SelectorKind.ACTION, starts))
                continue
            starts = resolve_starts(selector, graph, jobs=parsed.expanded_jobs)
        except SelectorError as exc:
            msg = f"invalid --simulate-compromise {raw!r}: {exc}"
            raise UsageError(msg) from None
        targets[selector.raw] = (selector.kind, starts)
    return tuple((label, kind, starts) for label, (kind, starts) in sorted(targets.items()))


def _scenario_analyses(
    parsed: ParsedRepository, graph: GraphData, depth: int, options: ScanOptions
) -> tuple[ScenarioAnalysis, ...]:
    analyses: list[ScenarioAnalysis] = []
    for label, kind, starts in _scenario_targets(parsed, graph, options):
        analyses.append(
            analyze_scenario(
                graph,
                starts,
                selector=label,
                selector_kind=kind.value,
                max_depth=depth,
                limits=parsed.limits,
                config=parsed.config,
                strict=options.strict,
            )
        )
    return tuple(analyses)


def _scenario_reports(
    analyses: Sequence[ScenarioAnalysis], final_ids: set[str]
) -> tuple[ScenarioReport, ...]:
    reports: list[ScenarioReport] = []
    for analysis in analyses:
        report = analysis.to_report()
        reports.append(
            report.model_copy(
                update={"findings": tuple(item for item in report.findings if item in final_ids)}
            )
        )
    return tuple(reports)


def _merged_findings(
    graph: GraphData,
    analyses: Sequence[ScenarioAnalysis],
    config: Config,
    strict: bool,
) -> tuple[tuple[Finding, ...], tuple[Diagnostic, ...]]:
    preliminary = tuple(analysis.to_report() for analysis in analyses)
    base = build_findings(graph, scenarios=preliminary)
    scenario_rules = {"NHB-SURV-001", "NHB-ROT-001", "NHB-ROT-002"}
    merged: dict[str, Finding] = {
        finding.id: finding for finding in base.findings if finding.rule not in scenario_rules
    }
    for analysis in analyses:
        for finding in analysis.findings:
            if finding.rule in scenario_rules:
                merged[finding.id] = finding
    filtered = filter_findings(merged.values(), config=config, strict=strict)
    return filtered.findings, filtered.diagnostics


# ------------------------------------------------------------------- assumptions


def _iter_assumption_ids(values: object) -> Iterable[str]:
    if isinstance(values, str):
        return (values,)
    if not isinstance(values, Sequence):
        return ()
    return (item for item in values if isinstance(item, str))


def _collect_assumptions(
    graph: GraphData,
    used: Sequence[str],
    findings: Sequence[Finding],
    analyses: Sequence[ScenarioAnalysis],
) -> tuple[tuple[AssumptionUse, ...], tuple[Diagnostic, ...]]:
    usage: dict[str, set[str]] = {
        assumption_id: set() for assumption_id in used if assumption_id.startswith(("A-", "H-"))
    }

    def add(assumption_id: str, owner: str) -> None:
        if assumption_id.startswith(("A-", "H-")):
            usage.setdefault(assumption_id, set()).add(owner)

    for node in graph.nodes:
        for evidence in node.evidence:
            add(evidence.rule, node.id)
    for edge in graph.edges:
        for evidence in edge.evidence:
            add(evidence.rule, edge.id)
        for key in ("assumption", "assumptions"):
            for assumption_id in _iter_assumption_ids(edge.attrs.get(key, ())):
                add(assumption_id, edge.id)
    for finding in findings:
        for evidence in finding.evidence:
            add(evidence.rule, finding.id)
        for assumption_id in finding.assumptions:
            add(assumption_id, finding.id)
    for analysis in analyses:
        if analysis.selector_kind == "repo-write":
            add("A-REPO-WRITE", f"scenario:{analysis.selector}")
    registry = assumptions()
    diagnostics: list[Diagnostic] = []
    entries: list[AssumptionUse] = []
    for assumption_id in sorted(usage):
        try:
            entry = registry.get(assumption_id)
        except DataFileError:
            diagnostics.append(
                warning(
                    "D-DATA-ASSUMPTION",
                    f"evidence references an unregistered assumption id: {assumption_id}",
                )
            )
            continue
        entries.append(
            AssumptionUse(
                id=assumption_id,
                statement=entry.statement,
                verify=entry.verify,
                used_by=tuple(sorted(usage[assumption_id])),
            )
        )
    return tuple(entries), tuple(diagnostics)


# ------------------------------------------------------------------- reporting


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _scope_lines(parsed: ParsedRepository, depth: int) -> tuple[str, ...]:
    resources = {address for model in parsed.tf_models for address in model.resources}
    budget = parsed.limits.scenario_time_budget_seconds
    budget_text = f"{budget:g}"
    return (
        "Scope: "
        f"{_plural(len(parsed.workflows), 'workflow', 'workflows')}, "
        f"{_plural(len(parsed.expanded_jobs), 'job', 'jobs')}, "
        f"{_plural(len(resources), 'Terraform resource', 'Terraform resources')}.",
        "Not analysed: SCPs, environment protection, branch rules, live AWS state, "
        "job outputs and artifacts.",
        f"Limits: closure depth {depth}, graph node budget {parsed.limits.max_graph_nodes}, "
        f"scenario time budget {budget_text} s.",
    )


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stale_data_diagnostics(
    data_files: Sequence[DataFileInfo], generated_at: str | None
) -> tuple[Diagnostic, ...]:
    if generated_at is None:
        return ()
    try:
        report_date = datetime.fromisoformat(generated_at.replace("Z", "+00:00")).date()
    except ValueError:
        return ()
    diagnostics: list[Diagnostic] = []
    for info in data_files:
        try:
            verified = datetime.fromisoformat(info.verified_on).date()
        except ValueError:
            continue
        if (report_date - verified).days > STALE_AFTER_DAYS:
            diagnostics.append(
                warning(
                    "D-DATA-STALE",
                    f"data file {info.name} was verified {info.verified_on}, "
                    f"{_MAX_AGE_SUFFIX} before this report",
                    file=info.name,
                )
            )
    return tuple(diagnostics)


def _has_error(diagnostics: Sequence[Diagnostic]) -> bool:
    return any(item.level is DiagnosticLevel.ERROR for item in diagnostics)


def _scan_exit_code(report: Report, *, strict: bool, fail_on: Severity | None) -> int:
    if strict and _has_error(report.diagnostics):
        return 3
    if fail_on is not None and any(
        severity_at_least(finding.severity, fail_on) for finding in report.findings
    ):
        return 1
    return 0


def _write_scan_artifacts(
    report: Report, formats: Sequence[OutputFormat], out_dir: Path
) -> tuple[Path, ...]:
    writers = {
        OutputFormat.JSON: ("report.json", write_json),
        OutputFormat.SARIF: ("report.sarif", write_sarif),
        OutputFormat.HTML: ("report.html", write_html),
    }
    written: list[Path] = []
    for fmt in formats:
        entry = writers.get(fmt)
        if entry is None:
            continue
        filename, writer = entry
        target = out_dir.expanduser() / filename
        try:
            writer(report, target)
        except OSError as exc:
            msg = f"cannot write {filename}: {exc.strerror or exc}"
            raise OutputError(msg) from None
        written.append(target)
    return tuple(written)


def run_scan(options: ScanOptions, *, color: bool = False) -> ScanOutcome:
    formats = _normalise_formats(options.formats)
    parsed = load_repository(options)
    depth = _effective_depth(options.max_depth, parsed.limits)
    build = build_repository_graph(parsed)
    graph = build.graph
    analyses = _scenario_analyses(parsed, graph, depth, options)
    findings, filter_diagnostics = _merged_findings(graph, analyses, parsed.config, options.strict)
    final_ids = {finding.id for finding in findings}
    scenario_reports = _scenario_reports(analyses, final_ids)
    nodes = {node.id: node for node in graph.nodes}
    edges = {edge.id: edge for edge in graph.edges}
    for analysis in analyses:
        nodes.update((node.id, node) for node in analysis.synthetic_nodes)
        edges.update((edge.id, edge) for edge in analysis.synthetic_edges)
    graph = GraphData(
        nodes=tuple(sorted(nodes.values(), key=lambda node: (NODE_KIND_ORDER[node.kind], node.id))),
        edges=tuple(sorted(edges.values(), key=Edge.sort_key)),
    )
    assumptions_used, assumption_diagnostics = _collect_assumptions(
        graph, build.assumptions_used, findings, analyses
    )
    data_files = all_data_file_infos()
    generated_at = _utc_now() if options.timestamp else None
    diagnostics = DiagnosticBag(parsed.diagnostics)
    diagnostics.extend(build.diagnostics)
    for analysis in analyses:
        diagnostics.extend(analysis.diagnostics)
    diagnostics.extend(filter_diagnostics)
    diagnostics.extend(assumption_diagnostics)
    diagnostics.extend(_stale_data_diagnostics(data_files, generated_at))
    report = Report(
        schema_id=SCHEMA_VERSION,
        tool=ToolInfo(version=__version__),
        inputs=parsed.inputs,
        scope_and_limits=_scope_lines(parsed, depth),
        assumptions=assumptions_used,
        data_files=data_files,
        diagnostics=diagnostics.sorted(),
        findings=findings,
        graph=graph,
        scenarios=scenario_reports,
        generated_at=generated_at,
    )
    exit_code = _scan_exit_code(report, strict=options.strict, fail_on=options.fail_on)
    return ScanOutcome(
        report=report,
        exit_code=exit_code,
        console_text=render_console(report, color=color),
        written=_write_scan_artifacts(report, formats, options.out_dir),
    )


def run_rank(options: RankOptions) -> RankOutcome:
    fmt = _rank_format(options.fmt)
    parsed = load_repository(options)
    depth = _effective_depth(options.max_depth, parsed.limits)
    build = build_repository_graph(parsed)
    diagnostics = (*parsed.diagnostics, *build.diagnostics)
    report = rank_mutable_actions(
        build.graph,
        inputs=parsed.inputs,
        max_depth=depth,
        diagnostics=diagnostics,
    )
    exit_code = 3 if options.strict and _has_error(report.diagnostics) else 0
    written: tuple[Path, ...] = ()
    if fmt is RankFormat.JSON:
        target = options.out_dir.expanduser() / "rank.json"
        try:
            write_rank_json(report, target)
        except OSError as exc:
            msg = f"cannot write rank.json: {exc.strerror or exc}"
            raise OutputError(msg) from None
        written = (target,)
    return RankOutcome(
        report=report,
        exit_code=exit_code,
        console_text=render_rank_console(report),
        written=written,
    )


def run_export(options: ExportOptions) -> ExportOutcome:
    fmt = _export_format(options.fmt)
    parsed = load_repository(options)
    build = build_repository_graph(parsed)
    diagnostics = DiagnosticBag(parsed.diagnostics)
    diagnostics.extend(build.diagnostics)
    generated_at = _utc_now() if options.timestamp else None
    tool = ToolInfo(version=__version__)
    data_files = all_data_file_infos()
    if fmt is ExportFormat.DOT:
        text = graph_export_dot(
            tool=tool,
            inputs=parsed.inputs,
            graph=build.graph,
            generated_at=generated_at,
        )
        filename = "graph.dot"
    else:
        text = graph_export_json(
            tool=tool,
            inputs=parsed.inputs,
            data_files=data_files,
            diagnostics=diagnostics.sorted(),
            graph=build.graph,
            generated_at=generated_at,
        )
        filename = "graph.json"
    target = options.out_dir.expanduser() / filename
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    except OSError as exc:
        msg = f"cannot write {filename}: {exc.strerror or exc}"
        raise OutputError(msg) from None
    node_count = len(build.graph.nodes)
    edge_count = len(build.graph.edges)
    exit_code = 3 if options.strict and _has_error(diagnostics.sorted()) else 0
    return ExportOutcome(
        exit_code=exit_code,
        text=(
            f"Exported {node_count} nodes and {edge_count} edges to "
            f"{safe_text(target.as_posix(), 500)}\n"
        ),
        written=(target,),
        node_count=node_count,
        edge_count=edge_count,
    )


__all__ = [
    "STALE_AFTER_DAYS",
    "ExportFormat",
    "ExportOptions",
    "ExportOutcome",
    "OutputError",
    "OutputFormat",
    "ParsedRepository",
    "PipelineError",
    "RankFormat",
    "RankOptions",
    "RankOutcome",
    "ScanOptions",
    "ScanOutcome",
    "SourceOptions",
    "UsageError",
    "build_repository_graph",
    "load_repository",
    "parse_fail_on",
    "run_export",
    "run_rank",
    "run_scan",
]
