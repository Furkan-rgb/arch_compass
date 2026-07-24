"""Explicit application error hierarchy."""

from __future__ import annotations

from archcompass.domain.diagnostics import FailureDiagnostic, format_failure_diagnostics


class ArchCompassError(Exception):
    """Base error exposed to presentation adapters."""


class ConfigurationError(ArchCompassError):
    pass


class PathValidationError(ArchCompassError):
    pass


class CaseNotFoundError(ArchCompassError):
    pass


class CaseRevisionConflictError(ArchCompassError):
    pass


class AtlasNotFoundError(ArchCompassError):
    pass


class StaleAtlasError(ArchCompassError):
    """Stored repository evidence no longer matches the repository."""


class AtlasQueryValidationError(ArchCompassError):
    pass


class PolicyFormatError(ArchCompassError):
    pass


class PolicyNotFoundError(ArchCompassError):
    pass


class PersistenceError(ArchCompassError):
    pass


class RunNotFoundError(ArchCompassError):
    pass


class ProviderError(ArchCompassError):
    pass


class ModelOutputValidationError(ArchCompassError):
    pass


class ClusterPartitionError(ModelOutputValidationError):
    """Exact-partition failure carrying only allowlisted diagnostics."""

    def __init__(self, diagnostics: list[FailureDiagnostic]) -> None:
        if not diagnostics:
            raise ValueError("ClusterPartitionError requires at least one diagnostic")
        self.diagnostics = list(diagnostics)
        super().__init__(format_failure_diagnostics(self.diagnostics))


class EvidenceReferenceError(ArchCompassError):
    pass


class ConversationNotFoundError(ArchCompassError):
    pass


class ConversationRevisionConflictError(ArchCompassError):
    pass


class ConversationValidationError(ArchCompassError):
    pass


class ConversationRetrievalError(ArchCompassError):
    pass
