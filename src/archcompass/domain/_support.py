"""Private helpers shared by immutable domain records."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def stable_id(prefix: str, *parts: str, length: int = 24) -> str:
    payload = "\0".join(parts).encode()
    return f"{prefix}_{sha256(payload).hexdigest()[:length]}"


def require_text(value: str, name: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must not be blank")


def freeze_sequences(instance: object, *field_names: str) -> None:
    """Normalize boundary/checkpoint sequences back to immutable tuples."""

    for name in field_names:
        value = getattr(instance, name)
        if not isinstance(value, tuple):
            object.__setattr__(instance, name, tuple(value))


def freeze_pairs(instance: object, *field_names: str) -> None:
    """Normalize a sequence and each two-value entry within it."""

    for name in field_names:
        value = getattr(instance, name)
        normalized = tuple(tuple(item) for item in value)
        if value != normalized or not isinstance(value, tuple):
            object.__setattr__(instance, name, normalized)
