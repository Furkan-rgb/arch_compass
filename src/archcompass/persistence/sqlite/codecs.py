"""Pydantic validation at the persistence edge of the dataclass domain."""

from __future__ import annotations

from typing import TypeVar

from pydantic import TypeAdapter, ValidationError

from archcompass.domain.errors import UnreadableStoredRecordError

Record = TypeVar("Record")


class DataclassRecordCodec[Record]:
    def __init__(self, record_type: type[Record]) -> None:
        self._adapter = TypeAdapter(record_type)

    def encode(self, record: Record) -> str:
        return self._adapter.dump_json(record).decode()

    def decode(self, document: str, *, description: str) -> Record:
        try:
            return self._adapter.validate_json(document)
        except ValidationError as error:
            raise UnreadableStoredRecordError(
                f"{description} is not a valid current dataclass-domain record: {error}"
            ) from error
