from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel

from nhi_blast.parsers.gha.literals import redact_literals


def redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    identifiers: dict[str, str] = {}

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            identifier = value.get("id")
            if isinstance(identifier, str) and redact_literals(identifier) != identifier:
                identifiers[identifier] = (
                    "redacted:" + hashlib.sha256(identifier.encode()).hexdigest()
                )
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    def clean(value: Any) -> Any:
        if isinstance(value, str):
            return identifiers.get(value, redact_literals(value))
        if isinstance(value, list):
            return [clean(child) for child in value]
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, child in value.items():
                safe_key = redact_literals(key)
                if safe_key != key:
                    safe_key += ":" + hashlib.sha256(key.encode()).hexdigest()
                result[safe_key] = clean(child)
            return result
        return value

    collect(payload)
    result: dict[str, Any] = clean(payload)
    return result


def redact_model[T: BaseModel](model: T) -> T:
    payload = model.model_dump(mode="json", by_alias=True, exclude_none=True)
    cleaned = redact_payload(payload)
    return model if cleaned == payload else type(model).model_validate(cleaned)
