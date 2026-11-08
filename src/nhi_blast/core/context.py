"""Build and verify the reproducibility record stored in ``Report.context``."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from nhi_blast import ENGINE_SEMANTICS, __version__
from nhi_blast.core.canonical import digest_of
from nhi_blast.core.config import Config
from nhi_blast.core.data import data_digests
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import (
    AnalyzerIdentity,
    GraphData,
    OidcSettings,
    Report,
    ReportContext,
    ScenarioContext,
)


def analyzer_identity() -> AnalyzerIdentity:
    digests = data_digests()
    return AnalyzerIdentity(
        tool_version=__version__,
        engine_semantics=ENGINE_SEMANTICS,
        rules_digest=digests.get("rules.yaml", ""),
        data_digests=digests,
    )


def graph_digest(graph: GraphData) -> str:
    return digest_of(graph.model_dump(mode="json", by_alias=True, exclude_none=True))


def _context_digest(context: ReportContext) -> str:
    payload = context.model_dump(
        mode="json", by_alias=True, exclude_none=True, exclude={"context_digest"}
    )
    return digest_of(payload)


def build_context(
    *,
    config: Config,
    limits: Limits,
    max_depth: int,
    strict: bool,
    selectors: Sequence[str],
    scenarios: Sequence[ScenarioContext],
    graph: GraphData,
    oidc: OidcSettings | None = None,
    sanitize: Callable[[ReportContext], ReportContext] | None = None,
) -> ReportContext:
    """``graph`` must be the graph as serialised (after output redaction).

    ``sanitize`` is the output redaction applied to the context, so the stored digest
    matches the bytes that are written and later reloaded.
    """
    effective_limits = limits.as_dict()
    effective_limits["max_closure_depth"] = max_depth
    draft = ReportContext(
        analyzer=analyzer_identity(),
        default_branch=config.default_branch,
        aws_account=config.aws_account,
        aws_region=config.aws_region,
        role_bindings=dict(sorted(config.role_bindings.items())),
        credential_bindings=dict(sorted(config.credential_bindings.items())),
        sub_template=config.sub_template,
        ignore_rules=tuple(sorted(config.ignore_rules)),
        ignore_paths=tuple(sorted(config.ignore_paths)),
        oidc=oidc or OidcSettings(),
        limits=dict(sorted(effective_limits.items())),
        max_depth=max_depth,
        strict=strict,
        selectors=tuple(sorted(set(selectors))),
        scenarios=tuple(sorted(scenarios, key=lambda item: item.selector)),
        config_digest=config.digest(),
        graph_digest=graph_digest(graph),
        context_digest="",
    )
    cleaned = sanitize(draft) if sanitize is not None else draft
    return cleaned.model_copy(update={"context_digest": _context_digest(cleaned)})


def integrity_failures(report: Report) -> tuple[str, ...]:
    """Reasons a loaded report's recorded digests no longer match its content."""
    context = report.context
    if context is None:
        return ("context-missing",)
    failures: list[str] = []
    if graph_digest(report.graph) != context.graph_digest:
        failures.append("graph-digest-mismatch")
    if _context_digest(context) != context.context_digest:
        failures.append("context-digest-mismatch")
    return tuple(failures)


__all__ = ["analyzer_identity", "build_context", "graph_digest", "integrity_failures"]
