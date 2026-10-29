from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel

from nhi_blast.parsers.gha.literals import redact_literals


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    identifiers: dict[str, str] = {}
    pending: list[Any] = [payload]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            identifier = current.get("id")
            if isinstance(identifier, str) and redact_literals(identifier) != identifier:
                identifiers[identifier] = "redacted:" + _digest(identifier)
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)

    def place(parent: Any, key: Any, child: Any, stack: list[tuple[Any, Any]]) -> None:
        if isinstance(child, str):
            parent[key] = identifiers.get(child, redact_literals(child))
        elif isinstance(child, dict):
            nested: dict[str, Any] = {}
            parent[key] = nested
            stack.append((child, nested))
        elif isinstance(child, list):
            items: list[Any] = [None] * len(child)
            parent[key] = items
            stack.append((child, items))
        else:
            parent[key] = child

    result: dict[str, Any] = {}
    stack: list[tuple[Any, Any]] = [(payload, result)]
    while stack:
        source, target = stack.pop()
        if isinstance(source, dict):
            for key, child in source.items():
                safe_key = key
                if isinstance(key, str):
                    cleaned_key = redact_literals(key)
                    if cleaned_key != key:
                        cleaned_key += ":" + _digest(key)
                    safe_key = cleaned_key
                place(target, safe_key, child, stack)
        else:
            for index, child in enumerate(source):
                place(target, index, child, stack)
    return result


def redact_model[T: BaseModel](model: T) -> T:
    payload = model.model_dump(mode="json", by_alias=True, exclude_none=True)
    cleaned = redact_payload(payload)
    return model if cleaned == payload else type(model).model_validate(cleaned)
