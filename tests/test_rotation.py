"""Dependency-aware rotation planning and SCC batches (M4)."""

from __future__ import annotations

from pathlib import Path

from nhi_blast.analysis.partition import partition_graph
from nhi_blast.analysis.rotation import plan_rotation
from nhi_blast.analysis.selectors import parse_selector, resolve_starts
from nhi_blast.core.evidence import EvidenceClass
from tests.test_graph_builder import PUBLISH_JOB, build_fixture

KEY_A = "cred:aws:secret:cycle/aws-access-key-a:stored"
KEY_B = "cred:aws:secret:cycle/aws-access-key-b:stored"
LEAF = "cred:aws:ssm:/cycle/api-token-leaf:stored"


def test_fx11_rotation_cycle_is_one_batch_before_the_leaf(fixtures_dir: Path) -> None:
    graph = build_fixture(fixtures_dir, "fx11-rotation-cycle").graph
    job_id = "job:.github/workflows/deploy.yml#deploy"
    result = partition_graph(graph, [job_id])

    plan = plan_rotation(
        graph,
        result.partition,
        selector_kind="job",
        start_nodes=[job_id],
    )

    assert len(plan.rotation) == 2
    batch, leaf = plan.rotation
    assert batch.batch
    assert batch.generation == 0
    assert batch.order == 1
    assert [credential.id for credential in batch.credentials] == [KEY_A, KEY_B]
    assert batch.depends_on == ()
    assert any("Freeze" in action for action in batch.actions)
    assert any("Re-enable" in action for action in batch.actions)
    assert not leaf.batch
    assert leaf.generation == 1
    assert leaf.order == 2
    assert [credential.id for credential in leaf.credentials] == [LEAF]
    assert leaf.depends_on == (KEY_A, KEY_B)
    assert plan.containment[0].phase.value == "containment"
    assert plan.verify[0].phase.value == "verify"
    assert any("dependency cycle" in note for note in plan.notes)


def test_fx07_rotation_uses_criticality_and_containment_before_verification(
    fixtures_dir: Path,
) -> None:
    graph = build_fixture(fixtures_dir, "fx07-incident").graph
    starts = resolve_starts(parse_selector("action:tj-actions/changed-files@v45"), graph, jobs=())
    result = partition_graph(graph, starts)

    plan = plan_rotation(
        graph,
        result.partition,
        selector_kind="action",
        start_nodes=starts,
    )

    assert [credential.id for step in plan.rotation for credential in step.credentials] == [
        "cred:aws:secret:prod/db-master:stored",
        "cred:aws:ssm:/prod/stripe/live_key:stored",
        "cred:aws:ssm:/legacy/ci-token:stored",
        "cred:aws:secret:prod/app-config:stored",
        f"cred:{PUBLISH_JOB}:SLACK_WEBHOOK_URL",
    ]
    assert [step.order for step in plan.rotation] == [1, 2, 3, 4, 5]
    assert {step.generation for step in plan.rotation} == {0}
    assert not any(step.batch for step in plan.rotation)
    assert all(step.depends_on == () for step in plan.rotation)
    containment_actions = plan.containment[0].actions
    assert any("Pin" in action for action in containment_actions)
    assert any("Disable" in action for action in containment_actions)
    assert any("review run logs" in action for action in containment_actions)
    assert any("Revoke active sessions" in action for action in containment_actions)
    assert any("trust" in action for action in containment_actions)
    assert plan.verify[0].confidence is EvidenceClass.ASSUMED
    assert any(
        action.startswith("VERIFY:") and "CloudTrail" in action for action in plan.verify[0].actions
    )
    assert any("Periodic rotation" in note for note in plan.notes)


def test_rotation_plan_is_deterministic(fixtures_dir: Path) -> None:
    graph = build_fixture(fixtures_dir, "fx11-rotation-cycle").graph
    job_id = "job:.github/workflows/deploy.yml#deploy"
    partition = partition_graph(graph, [job_id]).partition

    first = plan_rotation(
        graph, partition, selector_kind="job", start_nodes=[job_id]
    ).model_dump_json()
    second = plan_rotation(
        graph, partition, selector_kind="job", start_nodes=[job_id]
    ).model_dump_json()

    assert first == second
