"""GitHub Actions workflow parser (spec 7.2-7.11).

Pure: the parser receives a relative path and the file text and returns facts plus
diagnostics. Local composite actions and reusable workflows are expanded by the
resolver, not here.
"""

from __future__ import annotations

from nhi_blast.core.diagnostics import Diagnostic, error, info, warning
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import ParseResult
from nhi_blast.parsers.gha.expressions import (
    contains_head_ref_marker,
    merge_all,
    scan_condition,
    scan_text,
)
from nhi_blast.parsers.gha.facts import (
    AwsAuthUse,
    CompositeActionFact,
    ExprRefs,
    JobFact,
    LiteralHit,
    StepFact,
    UsesRef,
    WorkflowFact,
)
from nhi_blast.parsers.gha.literals import find_literals
from nhi_blast.parsers.gha.permissions import parse_permissions
from nhi_blast.parsers.gha.triggers import parse_triggers
from nhi_blast.parsers.gha.uses import is_action, is_reusable_workflow_ref, parse_uses
from nhi_blast.parsers.yaml_marked import Marked, load_marked_document

AWS_CREDENTIALS_ACTION = ("aws-actions", "configure-aws-credentials")
UNSUPPORTED_OIDC_CONSUMERS = (
    ("azure", "login"),
    ("google-github-actions", "auth"),
    ("hashicorp", "vault-action"),
)
_EXPR_OPEN = "${{"


def _has_expression(text: str | None) -> bool:
    return text is not None and _EXPR_OPEN in text


def _scalar_strings(node: Marked | None) -> tuple[str, ...]:
    if node is None:
        return ()
    if isinstance(node.value, str):
        return (node.value,)
    if isinstance(node.value, tuple):
        return tuple(str(item.value) for item in node.value if item.value is not None)
    return ()


def _scan_values(
    node: Marked | None,
) -> tuple[ExprRefs, tuple[LiteralHit, ...]]:
    """Scan every scalar in a mapping/sequence value for refs and literals."""
    refs: list[ExprRefs] = []
    literals: list[LiteralHit] = []
    if node is None:
        return ExprRefs(), ()

    def visit(item: Marked) -> None:
        if isinstance(item.value, dict):
            for _key, child in item.as_mapping().items():
                visit(child)
        elif isinstance(item.value, tuple):
            for child in item.as_sequence():
                visit(child)
        elif item.value is None:
            return
        else:
            text = str(item.value)
            refs.append(scan_text(text))
            literals.extend(find_literals(text, line=item.line))

    visit(node)
    return merge_all(refs), tuple(literals)


def _parse_with(
    node: Marked | None, *, rel_path: str
) -> tuple[dict[str, str], ExprRefs, tuple[LiteralHit, ...], tuple[Diagnostic, ...]]:
    values: dict[str, str] = {}
    diagnostics: list[Diagnostic] = []
    if node is None:
        return values, ExprRefs(), (), ()
    if not isinstance(node.value, dict):
        diagnostics.append(
            warning("D-GHA-STEP-SHAPE", "with: must be a mapping", file=rel_path, line=node.line)
        )
        return values, ExprRefs(), (), tuple(diagnostics)
    refs, literals = _scan_values(node)
    for key, value_node in node.as_mapping().items():
        if isinstance(value_node.value, (dict, tuple)):
            diagnostics.append(
                warning(
                    "D-GHA-STEP-SHAPE",
                    f"with.{key} must be a scalar",
                    file=rel_path,
                    line=value_node.line,
                )
            )
            continue
        if value_node.value is not None:
            values[key.strip()] = str(value_node.value)
    return values, refs, literals, tuple(diagnostics)


def _parse_aws_auth(
    uses: UsesRef | None,
    with_values: dict[str, str],
    *,
    step_line: int,
    rel_path: str,
    diagnostics: list[Diagnostic],
) -> AwsAuthUse | None:
    if uses is None or not is_action(uses, *AWS_CREDENTIALS_ACTION):
        return None
    role = with_values.get("role-to-assume")
    audience = with_values.get("audience") or "sts.amazonaws.com"
    ref_kind = "NONE"
    role_arn: str | None = None
    role_ref_name: str | None = None
    if role:
        stripped = role.strip()
        if stripped.startswith("arn:aws:iam::") or stripped.startswith("arn:aws-us-gov:iam::"):
            ref_kind = "ARN"
            role_arn = stripped
        else:
            ref_kind = "EXPR"
            references = scan_text(stripped)
            names = sorted({*references.vars, *references.secrets})
            role_ref_name = names[0] if len(names) == 1 else None
            diagnostics.append(
                info(
                    "D-GHA-AWS-ROLE-EXPR",
                    "role-to-assume is not a literal ARN; resolve it through config bindings",
                    file=rel_path,
                    line=step_line,
                )
            )
    static_inputs = ("aws-access-key-id", "aws-secret-access-key", "aws-session-token")
    static_keys = any(with_values.get(name) for name in static_inputs)
    static_secret_refs = tuple(
        sorted(
            {
                secret
                for name in static_inputs
                for secret in scan_text(with_values.get(name, "")).secrets
            }
        )
    )
    return AwsAuthUse(
        role_ref_kind=ref_kind,
        role_arn=role_arn,
        role_ref_name=role_ref_name,
        audience=audience.strip(),
        static_keys=static_keys,
        static_secret_refs=static_secret_refs,
        line=step_line,
    )


def _parse_step(
    node: Marked, index: int, *, rel_path: str, diagnostics: list[Diagnostic]
) -> StepFact | None:
    if not isinstance(node.value, dict):
        diagnostics.append(
            warning("D-GHA-STEP-SHAPE", "step must be a mapping", file=rel_path, line=node.line)
        )
        return None
    mapping = node.as_mapping()
    uses_marked = mapping.get("uses")
    uses: UsesRef | None = None
    if uses_marked is not None and isinstance(uses_marked.value, str):
        uses = parse_uses(uses_marked.value, uses_marked.line)
        if uses.kind == "REMOTE" and uses.owner is not None and uses.repo is not None:
            for owner, repo in UNSUPPORTED_OIDC_CONSUMERS:
                if is_action(uses, owner, repo):
                    diagnostics.append(
                        info(
                            "D-GHA-UNSUPPORTED-CONSUMER",
                            f"OIDC consumer {uses.raw} is not modelled; role binding is unknown",
                            file=rel_path,
                            line=uses.line,
                        )
                    )
    run_marked = mapping.get("run")
    run_text = (
        run_marked.value if run_marked is not None and isinstance(run_marked.value, str) else None
    )
    with_values, with_refs, with_literals, with_diagnostics = _parse_with(
        mapping.get("with"), rel_path=rel_path
    )
    diagnostics.extend(with_diagnostics)
    checkout_ref_untrusted = any(
        contains_head_ref_marker(with_values.get(key, "")) for key in ("ref", "repository")
    )
    env_refs, env_literals = _scan_values(mapping.get("env"))
    run_refs = scan_text(run_text) if run_text is not None else ExprRefs()
    run_literals = (
        find_literals(run_text, line=run_marked.line if run_marked is not None else node.line)
        if run_text
        else ()
    )
    if_marked = mapping.get("if")
    if_refs = (
        scan_condition(str(if_marked.value))
        if if_marked is not None and isinstance(if_marked.value, str)
        else ExprRefs()
    )
    name_marked = mapping.get("name")
    name_refs = (
        scan_text(str(name_marked.value))
        if name_marked is not None and isinstance(name_marked.value, str)
        else ExprRefs()
    )
    refs = merge_all([with_refs, env_refs, run_refs, if_refs, name_refs])
    if checkout_ref_untrusted:
        refs = refs.merge(ExprRefs(head_ref_use=True))
    literals = with_literals + env_literals + run_literals
    aws_auth = _parse_aws_auth(
        uses,
        with_values,
        step_line=node.line,
        rel_path=rel_path,
        diagnostics=diagnostics,
    )
    return StepFact(
        index=index,
        line=node.line,
        name=str(name_marked.value) if name_marked is not None and name_marked.value else None,
        uses=uses,
        refs=refs,
        literals=literals,
        aws_auth=aws_auth,
        has_run=run_text is not None,
    )


def _checkout_line(steps: tuple[StepFact, ...]) -> int | None:
    for step in steps:
        if step.uses is None or not is_action(step.uses, "actions", "checkout"):
            continue
        return step.line
    return None


def _detect_untrusted_checkout(steps: tuple[StepFact, ...]) -> tuple[bool, int | None]:
    """Spec 7.8: a head-ref checkout followed by a run/uses step in a privileged trigger."""
    checkout_index: int | None = None
    for position, step in enumerate(steps):
        if step.uses is None or not is_action(step.uses, "actions", "checkout"):
            continue
        if step.refs.head_ref_use:
            checkout_index = position
            break
    if checkout_index is None:
        return False, None
    for step in steps[checkout_index + 1 :]:
        if step.has_run or step.uses is not None:
            return True, step.line
    return False, None


def _parse_environment(
    node: Marked | None, *, rel_path: str, diagnostics: list[Diagnostic]
) -> tuple[str | None, bool]:
    if node is None:
        return None, False
    if isinstance(node.value, str):
        text = node.value.strip()
        if _has_expression(text):
            diagnostics.append(
                info(
                    "D-EXPR-VALUE",
                    "environment is set by an expression; the environment claim is unknown",
                    file=rel_path,
                    line=node.line,
                )
            )
            return None, True
        return text, False
    if isinstance(node.value, dict):
        name_node = node.as_mapping().get("name")
        if name_node is None or not isinstance(name_node.value, str):
            return None, True
        text = name_node.value.strip()
        if _has_expression(text):
            diagnostics.append(
                info(
                    "D-EXPR-VALUE",
                    "environment name is set by an expression; the environment claim is unknown",
                    file=rel_path,
                    line=name_node.line,
                )
            )
            return None, True
        return text, False
    return None, True


def _parse_runs_on(
    node: Marked | None, *, rel_path: str, diagnostics: list[Diagnostic]
) -> tuple[tuple[str, ...], bool | None]:
    if node is None:
        return (), None
    values = _scalar_strings(node)
    if any(_has_expression(value) for value in values):
        diagnostics.append(
            info(
                "D-EXPR-VALUE",
                "runs-on is set by an expression; runner type is unknown",
                file=rel_path,
                line=node.line,
            )
        )
        return values, None
    self_hosted = any("self-hosted" in value for value in values)
    return values, self_hosted


def _parse_job(
    job_id: str,
    node: Marked,
    *,
    rel_path: str,
    privileged_events: frozenset[str],
    diagnostics: list[Diagnostic],
) -> JobFact | None:
    if not isinstance(node.value, dict):
        diagnostics.append(
            warning(
                "D-GHA-JOB-SHAPE",
                f"job {job_id} must be a mapping",
                file=rel_path,
                line=node.line,
            )
        )
        return None
    mapping = node.as_mapping()
    name_node = mapping.get("name")
    runs_on, self_hosted = _parse_runs_on(
        mapping.get("runs-on"), rel_path=rel_path, diagnostics=diagnostics
    )
    if self_hosted:
        diagnostics.append(
            info(
                "D-GHA-SELF-HOSTED",
                f"job {job_id} targets a self-hosted runner; runner state may persist",
                file=rel_path,
                line=node.line,
            )
        )
    permissions, permission_diagnostics = parse_permissions(
        mapping.get("permissions"), rel_path=rel_path, fallback_line=node.line
    )
    diagnostics.extend(permission_diagnostics)
    environment, environment_unresolved = _parse_environment(
        mapping.get("environment"), rel_path=rel_path, diagnostics=diagnostics
    )
    uses_marked = mapping.get("uses")
    uses_workflow: UsesRef | None = None
    if uses_marked is not None and isinstance(uses_marked.value, str):
        uses_workflow = parse_uses(uses_marked.value, uses_marked.line)
        if not is_reusable_workflow_ref(uses_workflow):
            diagnostics.append(
                warning(
                    "D-GHA-JOB-USES",
                    f"job {job_id} uses: value is not a reusable workflow reference",
                    file=rel_path,
                    line=uses_marked.line,
                )
            )
    secrets_node = mapping.get("secrets")
    secrets_mode = "NONE"
    if secrets_node is not None:
        if isinstance(secrets_node.value, str) and secrets_node.value.strip().lower() == "inherit":
            secrets_mode = "INHERIT"
            diagnostics.append(
                warning(
                    "D-GHA-SECRETS-ALL",
                    f"job {job_id} uses secrets: inherit; secret materialisation is unknown",
                    file=rel_path,
                    line=secrets_node.line,
                )
            )
        elif isinstance(secrets_node.value, dict):
            secrets_mode = "EXPLICIT"
    _, job_with_refs, job_with_literals, job_with_diagnostics = _parse_with(
        mapping.get("with"), rel_path=rel_path
    )
    diagnostics.extend(job_with_diagnostics)
    env_refs, env_literals = _scan_values(mapping.get("env"))
    if_marked = mapping.get("if")
    if_refs = (
        scan_condition(str(if_marked.value))
        if if_marked is not None and isinstance(if_marked.value, str)
        else ExprRefs()
    )
    name_refs = (
        scan_text(str(name_node.value))
        if name_node is not None and isinstance(name_node.value, str)
        else ExprRefs()
    )
    steps: list[StepFact] = []
    steps_node = mapping.get("steps")
    if steps_node is not None:
        if isinstance(steps_node.value, tuple):
            for position, step_node in enumerate(steps_node.value, start=1):
                step = _parse_step(step_node, position, rel_path=rel_path, diagnostics=diagnostics)
                if step is not None:
                    steps.append(step)
        else:
            diagnostics.append(
                warning(
                    "D-GHA-STEP-SHAPE",
                    f"job {job_id} steps must be a sequence",
                    file=rel_path,
                    line=steps_node.line,
                )
            )
    step_refs = merge_all([step.refs for step in steps])
    refs = merge_all([job_with_refs, env_refs, if_refs, name_refs, step_refs])
    untrusted_checkout = False
    untrusted_line: int | None = None
    if privileged_events:
        untrusted_checkout, untrusted_line = _detect_untrusted_checkout(tuple(steps))
        if untrusted_checkout:
            diagnostics.append(
                warning(
                    "D-GHA-UNTRUSTED-CHECKOUT",
                    f"job {job_id} runs pull-request content under a privileged trigger",
                    file=rel_path,
                    line=untrusted_line,
                )
            )
    if refs.secrets_all and secrets_mode != "INHERIT":
        diagnostics.append(
            warning(
                "D-GHA-SECRETS-ALL",
                f"job {job_id} references the whole secrets context; materialisation is unknown",
                file=rel_path,
                line=node.line,
            )
        )
    return JobFact(
        id=job_id,
        line=node.line,
        name=str(name_node.value) if name_node is not None and name_node.value else None,
        runs_on=runs_on,
        self_hosted=self_hosted,
        permissions=permissions,
        environment=environment,
        environment_unresolved=environment_unresolved,
        uses_workflow=uses_workflow,
        secrets_mode=secrets_mode,
        steps=tuple(steps),
        refs=refs,
        untrusted_checkout=untrusted_checkout,
        untrusted_checkout_line=untrusted_line,
        literals=job_with_literals + env_literals,
    )


def parse_workflow(rel_path: str, text: str, *, limits: Limits) -> ParseResult[WorkflowFact]:
    """Parse one workflow file into facts; never raises on hostile input."""
    document, diagnostics = load_marked_document(text, rel_path=rel_path, limits=limits)
    diags = list(diagnostics)
    if document is None:
        return ParseResult(facts=None, diagnostics=tuple(diags))
    if not isinstance(document.value, dict):
        diags.append(error("D-GHA-STRUCT", "workflow must be a mapping", file=rel_path))
        return ParseResult(facts=None, diagnostics=tuple(diags))
    mapping = document.as_mapping()
    name_node = mapping.get("name")
    triggers, trigger_diagnostics = parse_triggers(mapping.get("on"), rel_path=rel_path)
    diags.extend(trigger_diagnostics)
    permissions, permission_diagnostics = parse_permissions(
        mapping.get("permissions"), rel_path=rel_path, fallback_line=document.line
    )
    diags.extend(permission_diagnostics)
    privileged_events = frozenset(
        trigger.event
        for trigger in triggers
        if trigger.event
        in {"pull_request_target", "workflow_run", "issue_comment", "discussion_comment"}
    )
    jobs_node = mapping.get("jobs")
    jobs: dict[str, JobFact] = {}
    if jobs_node is None:
        diags.append(error("D-GHA-STRUCT", "workflow has no jobs block", file=rel_path))
    elif not isinstance(jobs_node.value, dict):
        diags.append(
            error("D-GHA-STRUCT", "jobs must be a mapping", file=rel_path, line=jobs_node.line)
        )
    else:
        for job_id, job_node in jobs_node.as_mapping().items():
            job = _parse_job(
                job_id,
                job_node,
                rel_path=rel_path,
                privileged_events=privileged_events,
                diagnostics=diags,
            )
            if job is not None:
                jobs[job_id] = job
    return ParseResult(
        facts=WorkflowFact(
            path=rel_path,
            name=str(name_node.value) if name_node is not None and name_node.value else None,
            triggers=triggers,
            permissions=permissions,
            jobs=jobs,
        ),
        diagnostics=tuple(diags),
    )


def parse_composite_action(
    rel_path: str, text: str, *, limits: Limits
) -> ParseResult[CompositeActionFact]:
    """Parse a local action.yml/action.yaml for composite steps (spec 7.7)."""
    document, diagnostics = load_marked_document(text, rel_path=rel_path, limits=limits)
    diags = list(diagnostics)
    if document is None:
        return ParseResult(facts=None, diagnostics=tuple(diags))
    if not isinstance(document.value, dict):
        diags.append(error("D-GHA-STRUCT", "action metadata must be a mapping", file=rel_path))
        return ParseResult(facts=None, diagnostics=tuple(diags))
    mapping = document.as_mapping()
    runs = mapping.get("runs")
    using: str | None = None
    steps: tuple[StepFact, ...] = ()
    if runs is not None and isinstance(runs.value, dict):
        using_node = runs.as_mapping().get("using")
        using = str(using_node.value) if using_node is not None and using_node.value else None
        steps_node = runs.as_mapping().get("steps")
        if steps_node is not None and isinstance(steps_node.value, tuple):
            parsed_steps: list[StepFact] = []
            for position, step_node in enumerate(steps_node.value, start=1):
                step = _parse_step(step_node, position, rel_path=rel_path, diagnostics=diags)
                if step is not None:
                    parsed_steps.append(step)
            steps = tuple(parsed_steps)
    name_node = mapping.get("name")
    refs = merge_all([step.refs for step in steps])
    return ParseResult(
        facts=CompositeActionFact(
            path=rel_path,
            name=str(name_node.value) if name_node is not None and name_node.value else None,
            using=using,
            steps=steps,
            refs=refs,
        ),
        diagnostics=tuple(diags),
    )
