"""Resource and safety limits (spec 6.2).

Every limit is configurable through the [limits] section of the config file; defaults
match the specification. Breaching a limit produces a diagnostic and skips the
offending input rather than aborting the scan.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any

MIB = 1024 * 1024


@dataclass(frozen=True, slots=True)
class Limits:
    max_yaml_policy_file_bytes: int = 5 * MIB
    max_tf_json_bytes: int = 64 * MIB
    max_files: int = 20_000
    max_yaml_nodes: int = 200_000
    max_yaml_depth: int = 64
    alias_expansion_factor: int = 10
    max_graph_nodes: int = 500_000
    scenario_time_budget_seconds: float = 60.0
    max_closure_depth: int = 3
    max_composite_depth: int = 5

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> Limits:
        known = {f.name for f in fields(cls)}
        unknown = set(values) - known
        if unknown:
            msg = f"unknown limit(s): {', '.join(sorted(unknown))}"
            raise ValueError(msg)
        int_minimums = {
            "max_yaml_policy_file_bytes": 1,
            "max_tf_json_bytes": 1,
            "max_files": 1,
            "max_yaml_nodes": 1,
            "max_yaml_depth": 1,
            "alias_expansion_factor": 1,
            "max_graph_nodes": 1,
            "max_closure_depth": 0,
            "max_composite_depth": 0,
        }
        parsed: dict[str, Any] = {}
        for name, minimum in int_minimums.items():
            if name not in values:
                continue
            value = values[name]
            if isinstance(value, bool) or not isinstance(value, int):
                msg = f"{name} must be an integer"
                raise TypeError(msg)
            if value < minimum:
                msg = f"{name} must be at least {minimum}"
                raise ValueError(msg)
            parsed[name] = value
        if "scenario_time_budget_seconds" in values:
            budget = values["scenario_time_budget_seconds"]
            if isinstance(budget, bool) or not isinstance(budget, (int, float)):
                msg = "scenario_time_budget_seconds must be a number"
                raise TypeError(msg)
            try:
                finite_budget = float(budget)
            except OverflowError:
                msg = "scenario_time_budget_seconds must be finite"
                raise ValueError(msg) from None
            if not math.isfinite(finite_budget):
                msg = "scenario_time_budget_seconds must be finite"
                raise ValueError(msg)
            if finite_budget < 0:
                msg = "scenario_time_budget_seconds must be non-negative"
                raise ValueError(msg)
            parsed["scenario_time_budget_seconds"] = finite_budget
        return cls(**parsed)

    def as_dict(self) -> dict[str, int | float]:
        return {f.name: getattr(self, f.name) for f in fields(self)}
