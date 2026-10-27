"""Trigger parsing and normalisation (spec 7.3)."""

from __future__ import annotations

from nhi_blast.core.diagnostics import Diagnostic, warning
from nhi_blast.parsers.gha.facts import Trigger
from nhi_blast.parsers.yaml_marked import Marked

_FILTER_KEYS = {
    "branches": "branches",
    "branches-ignore": "branches_ignore",
    "tags": "tags",
    "tags-ignore": "tags_ignore",
    "paths": "paths",
    "paths-ignore": "paths_ignore",
    "types": "types",
}


def _string_list(node: Marked | None) -> tuple[str, ...]:
    if node is None:
        return ()
    if isinstance(node.value, str):
        return (node.value,)
    if isinstance(node.value, tuple):
        return tuple(str(item.value) for item in node.value if item.value is not None)
    return ()


def parse_triggers(
    node: Marked | None, *, rel_path: str
) -> tuple[tuple[Trigger, ...], tuple[Diagnostic, ...]]:
    if node is None:
        return (), (
            warning("D-GHA-ON-MISSING", "workflow has no on: trigger block", file=rel_path),
        )
    diagnostics: list[Diagnostic] = []
    triggers: list[Trigger] = []
    if isinstance(node.value, str):
        triggers.append(Trigger(event=node.value.strip(), line=node.line))
    elif isinstance(node.value, tuple):
        for item in node.value:
            if isinstance(item.value, str):
                triggers.append(Trigger(event=item.value.strip(), line=item.line))
            else:
                diagnostics.append(
                    warning(
                        "D-GHA-TRIGGER-SHAPE",
                        "on: sequence entries must be event names",
                        file=rel_path,
                        line=item.line,
                    )
                )
    elif isinstance(node.value, dict):
        for event, value_node in node.as_mapping().items():
            event_name = event.strip()
            fields: dict[str, tuple[str, ...]] = {}
            if isinstance(value_node.value, dict):
                for key, field_node in value_node.as_mapping().items():
                    attribute = _FILTER_KEYS.get(key.strip())
                    if attribute is not None:
                        fields[attribute] = _string_list(field_node)
            elif isinstance(value_node.value, tuple):
                if event_name == "schedule":
                    fields["types"] = tuple(
                        str(entry.get("cron").value)
                        for entry in value_node.value
                        if isinstance(entry.value, dict) and entry.get("cron") is not None
                    )
                else:
                    fields["types"] = _string_list(value_node)
            triggers.append(
                Trigger(
                    event=event_name,
                    branches=fields.get("branches", ()),
                    branches_ignore=fields.get("branches_ignore", ()),
                    tags=fields.get("tags", ()),
                    tags_ignore=fields.get("tags_ignore", ()),
                    paths=fields.get("paths", ()),
                    paths_ignore=fields.get("paths_ignore", ()),
                    types=fields.get("types", ()),
                    line=value_node.line,
                )
            )
    else:
        diagnostics.append(
            warning(
                "D-GHA-TRIGGER-SHAPE",
                "on: must be a string, sequence or mapping",
                file=rel_path,
                line=node.line,
            )
        )
    unique = {trigger.sort_key(): trigger for trigger in triggers}
    return tuple(unique[key] for key in sorted(unique)), tuple(diagnostics)
