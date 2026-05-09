"""JSON-safe serialization helpers for PHX2 dataclasses."""

from dataclasses import fields
from datetime import datetime
from enum import Enum
from typing import Any, Dict


def to_json_safe(value: Any) -> Any:
    """Convert common typed values to JSON-safe Python primitives."""

    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if isinstance(value, list):
        return [to_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [to_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_json_safe(item) for key, item in value.items()}
    return value


class SerializableDataclass:
    """Mixin for dataclasses that need JSON-safe dict output."""

    def to_dict(self) -> Dict[str, Any]:
        return {
            field.name: to_json_safe(getattr(self, field.name))
            for field in fields(self)
        }
