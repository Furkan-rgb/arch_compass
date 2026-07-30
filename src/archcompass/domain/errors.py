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


class CaseValidationError(ArchCompassError):
    """A case cannot be written as asked — a reference that does not resolve, a blank answer.

    Distinct from `CaseNotFoundError`: the case is there and the request is wrong about it.
    """


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


class UnreadableStoredRecordError(PersistenceError):
    """A stored row predates the current schema and cannot be reinterpreted.

    ArchCompass does not guess at the meaning of a record written by an earlier,
    unreleased schema. What to do instead depends on the record — derived output is
    produced again, user-authored input has to be written again — so the message
    carries the remedy its reader can actually act on.
    """


class ReviewNotFoundError(ArchCompassError):
    """No stored review under that identifier."""


class ReviewCancelledError(ArchCompassError):
    """The run was asked to stop, and did, between one model call and the next.

    Not a failure: the record already says the review was cancelled, and the run raises
    only to unwind the work it was in the middle of.
    """


class ReviewNotCancellableError(ArchCompassError):
    """The review is not running, so there is nothing to stop."""


class ReviewStillRunningError(ArchCompassError):
    """The review is being produced right now, and the request needs it not to be."""


class ProviderError(ArchCompassError):
    pass


class PromptBudgetExceededError(ArchCompassError):
    """The serialized request cannot fit the model's context window.

    Deliberately not a `ProviderError`: the provider is healthy and an identical
    retry fails identically. Ollama would silently discard the front of an oversize
    prompt - the system prompt first - so this refuses to send and names the sizes
    instead of producing degraded output that fails validation with no attributable
    cause.
    """


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
