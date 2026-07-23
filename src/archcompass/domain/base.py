"""Shared primitives used by domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Base for immutable, strict application data."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def stable_id(prefix: str, *parts: str, length: int = 24) -> str:
    payload = "\0".join(parts).encode("utf-8")
    return f"{prefix}_{sha256(payload).hexdigest()[:length]}"


def canonical_json(model: BaseModel | dict[str, Any]) -> str:
    if isinstance(model, BaseModel):
        return model.model_dump_json(indent=None, exclude_none=False)
    import json

    return json.dumps(model, sort_keys=True, separators=(",", ":"), default=str)

