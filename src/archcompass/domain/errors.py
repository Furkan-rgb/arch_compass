"""Explicit application error hierarchy."""

from __future__ import annotations

from archcompass.domain.diagnostics import FailureDiagnostic, format_failure_diagnostics


class ArchCompassError(Exception):
    """Base error exposed to presentation adapters."""


class ConfigurationError(ArchCompassError):
    pass


class NoReasoningModelSelectedError(ConfigurationError):
    """Something asked this workspace to reason, and it has not chosen a model.

    A `ConfigurationError` by inheritance because that is what it is, and its own type
    because it is the one configuration fault whose cure is inside the application. Every
    other one wants a file edited and a process restarted; this one wants a click, and the
    interface can only offer that click if it can tell this case apart from the rest.
    """


class PathValidationError(ArchCompassError):
    pass


class CaseNotFoundError(ArchCompassError):
    pass


class ExampleNotFoundError(ArchCompassError):
    """No bundled example goes by that name.

    Its own type rather than `CaseNotFoundError` or `AtlasNotFoundError`: an example is
    neither until it has been loaded, so this is about the set the package ships rather
    than about anything in this workspace.
    """


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


class PolicyConflictError(ArchCompassError):
    """The corpus already answers this, and the request needs it not to.

    An id another policy holds, or a file this workspace did not write. Neither is a
    malformed request — both are true statements about the corpus as it stands — so
    repeating the request identically fails identically until the corpus changes.
    """


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


class ReviewHasNoReportError(ArchCompassError):
    """The review ended without reaching a verdict, so it has no document to hand over.

    Kept apart from `ReviewStillRunningError`, which is the same absence with an opposite
    remedy: a run in progress will have a report shortly, and one that failed or was
    cancelled never will. Running it again produces a different review, not this one.
    """


class ReviewNotBaselineableError(ArchCompassError):
    """The review reached no verdicts, so there is nothing in it to declare seen.

    A state conflict rather than a malformed request: the review exists and the request is
    right about everything except what that review is. Repeating it fails identically —
    a failed or cancelled run never acquires a report — so the cure is another run.
    """


class ReviewHasNoBranchError(ArchCompassError):
    """The review has no branch lineage, and the thing being asked for lives on a branch.

    Its own type because its cure is unusual and specific: re-index the repository so the
    atlas carries a lineage, then run the review again. Nothing about the request is wrong,
    and nothing about the review is broken — it simply predates the identity model.
    """


class BaselineEntryNotFoundError(ArchCompassError):
    """This branch has no baselined boundary under that fingerprint."""


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
