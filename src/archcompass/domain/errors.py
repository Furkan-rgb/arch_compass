"""Explicit application error hierarchy."""

from __future__ import annotations


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


class PolicyEmbeddingsMissingError(ConfigurationError):
    """No prebuilt policy embeddings exist for this embedding model and policy corpus.

    Policy embeddings must be generated ahead of time using scripts/build_policy_index.py
    rather than embedded on the fly during a review.
    """


class PathValidationError(ArchCompassError):
    pass


class ScopeValidationError(PathValidationError):
    """The folders a request asked to leave out are not a scope this can apply.

    A `PathValidationError` by inheritance because that is what it is — a malformed path in a
    request — and its own type because the remedy is about the exclusion list rather than
    about the repository: the folder named is fine, the way it was written is not.
    """


class RepositoryCheckoutError(ArchCompassError):
    """A repository was named and could not be made available to review.

    Its own type rather than a `PathValidationError`, which is what a malformed request gets:
    everything here is a well-formed request about a repository that will not cooperate — an
    unreachable remote, a branch it does not have, a working copy that is somebody else's to
    move. The message is the whole of the remedy, so it names what to do rather than what
    failed.
    """


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


class NothingToReviewError(ArchCompassError):
    """A revision was asked for and nothing has moved since the branch's last one.

    Raised before anything is written, which is the point: a revision that would change
    nothing is reported, not recorded. The branch's line is a history of what happened to
    the code, not of who pressed what.

    Carries the revision the repository is current against, because "nothing has changed"
    is a statement relative to something and a caller — CI reporting a standing, a page
    offering the record — needs to be able to open that something.
    """

    def __init__(self, message: str, *, current_against: str) -> None:
        super().__init__(message)
        self.current_against = current_against


class ReviewNotCancellableError(ArchCompassError):
    """The review is not running, so there is nothing to stop."""


class ReviewSupersededError(ArchCompassError):
    """Answers arrived for a snapshot the review has already moved past.

    A review that asks twice is recorded twice, under one sequence, and both snapshots say
    `awaiting_answers` for ever — a snapshot is immutable, so round one's copy goes on
    saying it long after round two opened. Neither the snapshot nor the execution's status
    can therefore tell a retry from a stale submission, and the difference is not academic:
    replaying round one's answers into round two's interrupt hands the case a set of
    equivalence keys it already holds, which raises inside the graph, fails the round, and
    leaves the answers a person actually typed nowhere but in a review blob.

    What tells them apart is which snapshot the execution currently stands on. This is
    raised when that is not the one the answers were written against, and it is not
    retryable: the questions on screen are not the questions the review is waiting for, and
    the way forward is to read the review again, not to send this again.
    """


class ReviewStillRunningError(ArchCompassError):
    """The review is being produced right now, and the request needs it not to be."""


class ReviewHasNoReportError(ArchCompassError):
    """The review ended without reaching a verdict, so it has no document to hand over.

    Kept apart from `ReviewStillRunningError`, which is the same absence with an opposite
    remedy: a run in progress will have a report shortly, and one that failed or was
    cancelled never will. Running it again produces a different review, not this one.
    """


class ProviderError(ArchCompassError):
    pass


class ModelOutputValidationError(ArchCompassError):
    pass


class BranchNotFoundError(ArchCompassError):
    """This workspace has never seen that line of work.

    Its own type rather than a validation error: the request is well formed and the branch id
    is a hash nobody types by hand, so reaching this almost always means the workspace has not
    indexed the repository yet — which is a thing to do, not a thing to fix in the request.
    """


class ConversationNotFoundError(ArchCompassError):
    pass


class ConversationRevisionConflictError(ArchCompassError):
    pass


class ConversationValidationError(ArchCompassError):
    pass


class ConversationRetrievalError(ArchCompassError):
    pass
