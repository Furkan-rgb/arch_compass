"""Safe, structured diagnostics for consultation failures."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from archcompass.domain.base import DomainModel

ForceHandle = Annotated[str, StringConstraints(pattern=r"^F[1-9][0-9]*$")]


class FailureDiagnosticCode(StrEnum):
    """Allowlisted failure details that are safe to persist and display."""

    CLUSTER_COUNT_OUT_OF_RANGE = "cluster_count_out_of_range"
    UNKNOWN_FORCE_REFERENCES = "unknown_force_references"
    MISSING_FORCE_REFERENCES = "missing_force_references"
    DUPLICATE_FORCE_REFERENCES = "duplicate_force_references"
    DUPLICATE_CLUSTER_IDS = "duplicate_cluster_ids"


class FailureDiagnostic(DomainModel):
    """Machine-readable detail without model prose, paths, or internal IDs."""

    code: FailureDiagnosticCode
    force_handles: list[ForceHandle] = Field(default_factory=list[ForceHandle])
    count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_code_specific_fields(self) -> FailureDiagnostic:
        if len(self.force_handles) != len(set(self.force_handles)):
            raise ValueError("Failure diagnostic force handles must be unique")
        handles_required = self.code in {
            FailureDiagnosticCode.MISSING_FORCE_REFERENCES,
            FailureDiagnosticCode.DUPLICATE_FORCE_REFERENCES,
        }
        count_required = self.code in {
            FailureDiagnosticCode.CLUSTER_COUNT_OUT_OF_RANGE,
            FailureDiagnosticCode.UNKNOWN_FORCE_REFERENCES,
            FailureDiagnosticCode.DUPLICATE_CLUSTER_IDS,
        }
        if handles_required and not self.force_handles:
            raise ValueError(f"{self.code} requires force handles")
        if not handles_required and self.force_handles:
            raise ValueError(f"{self.code} cannot contain force handles")
        if count_required and self.count is None:
            raise ValueError(f"{self.code} requires a count")
        if (
            self.code != FailureDiagnosticCode.CLUSTER_COUNT_OUT_OF_RANGE
            and self.count == 0
        ):
            raise ValueError(f"{self.code} requires a positive count")
        if not count_required and self.count is not None:
            raise ValueError(f"{self.code} cannot contain a count")
        return self


def format_failure_diagnostic(diagnostic: FailureDiagnostic) -> str:
    """Render only allowlisted fields into an actionable sentence."""
    if diagnostic.code == FailureDiagnosticCode.CLUSTER_COUNT_OUT_OF_RANGE:
        return (
            "Expected between 1 and 4 concern clusters; "
            f"the model returned {diagnostic.count}."
        )
    if diagnostic.code == FailureDiagnosticCode.UNKNOWN_FORCE_REFERENCES:
        noun = "reference" if diagnostic.count == 1 else "references"
        return (
            f"The model returned {diagnostic.count} unrecognized force {noun}; "
            "only the supplied F-number handles are allowed."
        )
    if diagnostic.code == FailureDiagnosticCode.MISSING_FORCE_REFERENCES:
        return f"Missing force handles: {', '.join(diagnostic.force_handles)}."
    if diagnostic.code == FailureDiagnosticCode.DUPLICATE_FORCE_REFERENCES:
        return f"Repeated force handles: {', '.join(diagnostic.force_handles)}."
    noun = "ID" if diagnostic.count == 1 else "IDs"
    return f"The model returned {diagnostic.count} duplicate concern cluster {noun}."


def format_failure_diagnostics(diagnostics: list[FailureDiagnostic]) -> str:
    """Render a compact public message for a structured diagnostic collection."""
    if not diagnostics:
        return "Structured model output failed validation"
    details = " ".join(format_failure_diagnostic(item) for item in diagnostics)
    return f"Concern clustering did not form an exact partition. {details}"
