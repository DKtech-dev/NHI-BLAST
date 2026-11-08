"""Which input families each rule depends on, and how completeness statuses rank.

A finding that disappears is only "no longer observed under comparable analysis" when
none of the families it depends on lost information between the two reports. The table
is deliberately inclusive: a family that does not apply to the scan has the same status on
both sides and blocks nothing.
"""

from __future__ import annotations

from nhi_blast.core.models import CompletenessStatus, InputFamily

F = InputFamily
S = CompletenessStatus

# Lower is more informative. A status that ranks higher in HEAD than in BASE is a loss.
STATUS_RANK: dict[CompletenessStatus, int] = {
    S.NOT_APPLICABLE: 0,
    S.ANALYSED: 0,
    S.PARTIALLY_ANALYSED: 1,
    S.NOT_PROVIDED: 2,
    S.NOT_SUPPORTED: 2,
}

_WORKFLOW_SIDE = (F.GHA_WORKFLOWS, F.GHA_LOCAL_COMPOSITES, F.GHA_REMOTE_CALLEES)
_TRUST_SIDE = (
    F.OIDC_SUBJECT_BINDING,
    F.TF_PLAN_STATE,
    F.TF_HCL,
    F.TF_LOCAL_MODULES,
    F.IAM_IDENTITY_POLICIES,
)
_ALWAYS = (F.ANALYSIS_BUDGET,)

RULE_FAMILIES: dict[str, tuple[InputFamily, ...]] = {
    "NHB-OIDC-001": (*_WORKFLOW_SIDE, *_TRUST_SIDE, *_ALWAYS),
    "NHB-OIDC-002": (*_WORKFLOW_SIDE, *_TRUST_SIDE, *_ALWAYS),
    "NHB-OIDC-003": (*_WORKFLOW_SIDE, *_TRUST_SIDE, *_ALWAYS),
    "NHB-OIDC-004": (*_WORKFLOW_SIDE, *_TRUST_SIDE, *_ALWAYS),
    "NHB-OIDC-005": (*_WORKFLOW_SIDE, *_TRUST_SIDE, *_ALWAYS),
    "NHB-OIDC-006": (*_TRUST_SIDE, *_ALWAYS),
    "NHB-OIDC-007": (*_WORKFLOW_SIDE, F.GH_ENVIRONMENT_PROTECTION, *_TRUST_SIDE, *_ALWAYS),
    "NHB-GHA-001": (*_WORKFLOW_SIDE, *_ALWAYS),
    "NHB-GHA-002": (*_WORKFLOW_SIDE, *_ALWAYS),
    "NHB-GHA-003": (*_WORKFLOW_SIDE, *_ALWAYS),
    "NHB-GHA-004": (*_WORKFLOW_SIDE, *_ALWAYS),
    "NHB-GHA-005": (*_WORKFLOW_SIDE, *_ALWAYS),
    "NHB-CRED-001": (*_WORKFLOW_SIDE, *_ALWAYS),
    # Reachability and survival findings depend on every family the analysis reads.
    "NHB-SURV-001": tuple(InputFamily),
    "NHB-ROT-001": tuple(InputFamily),
    "NHB-ROT-002": tuple(InputFamily),
}


def families_for(rule: str) -> tuple[InputFamily, ...]:
    """Families a rule depends on; an unknown rule depends on all of them."""
    return RULE_FAMILIES.get(rule, tuple(InputFamily))


def status_worse(base: CompletenessStatus, head: CompletenessStatus) -> bool:
    return STATUS_RANK[head] > STATUS_RANK[base]
