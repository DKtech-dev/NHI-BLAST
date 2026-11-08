"""Offline containment what-if on a saved report (schema nhi-blast-whatif/1.0).

The model never reads or changes live state. It replays the saved scenarios, applies
the interventions of a plan to a copy of the saved graph and reports the difference.
"""

from __future__ import annotations

WHATIF_SCHEMA = "nhi-blast-whatif/1.0"
PLAN_SCHEMA = "nhi-blast-interventions/1.0"
HEADER = "Offline model. Not executed. Verify in your account."

__all__ = ["HEADER", "PLAN_SCHEMA", "WHATIF_SCHEMA"]
