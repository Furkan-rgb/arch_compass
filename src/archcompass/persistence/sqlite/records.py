"""Strict decoding of stored JSON documents.

Domain models validate the current schema only: migration heuristics never run
against live model output. Rows written by an earlier, unreleased schema therefore
fail validation, and this module turns that failure into an explicit instruction
rather than a raw Pydantic traceback.

What to do about it differs by record, so the caller supplies the remedy. A review can
be run again; a case is what someone typed, and nothing can regenerate it.
"""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from archcompass.domain.errors import UnreadableStoredRecordError


def decode_stored_json[Record: BaseModel](
    model: type[Record],
    document: str,
    *,
    description: str,
    remedy: str,
) -> Record:
    """Validate ``document`` or explain what to do about the row that failed."""

    try:
        return model.model_validate_json(document)
    except ValidationError as error:
        raise UnreadableStoredRecordError(
            f"{description} was written by an unsupported earlier schema and cannot be "
            f"read. {remedy} Details: {error}"
        ) from error
