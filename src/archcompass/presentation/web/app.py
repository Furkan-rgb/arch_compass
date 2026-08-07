"""FastAPI adapter for the Arch Compass workspace, local or hosted."""

# Pyright cannot see FastAPI's decorator registration as a function reference.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import logging
import re
from collections.abc import Iterator, Sequence
from datetime import datetime
from pathlib import Path
from queue import Queue
from threading import BoundedSemaphore, Thread
from typing import Annotated, Any, Literal, cast

import yaml
from fastapi import Body, Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    ValidationError,
    model_validator,
)

from archcompass.application.cases import WrittenAnswer
from archcompass.application.repository_tree import folder_tree
from archcompass.application.review_source import MAX_CONTEXT_LINES
from archcompass.application.reviews import JudgedCandidate
from archcompass.application.standings import standing_for
from archcompass.bootstrap import Runtime
from archcompass.domain.atlas import AtlasQueryResult, AtlasVersion, FindingCandidate
from archcompass.domain.case import ArchitectureCase, CaseRevision, CaseUpdate
from archcompass.domain.checkout import CheckoutRefresh, RepositoryCheckout
from archcompass.domain.errors import (
    ArchCompassError,
    AtlasNotFoundError,
    BranchNotFoundError,
    CaseNotFoundError,
    CaseRevisionConflictError,
    CaseValidationError,
    ConversationNotFoundError,
    ConversationRetrievalError,
    ConversationRevisionConflictError,
    ConversationValidationError,
    ExampleNotFoundError,
    ModelOutputValidationError,
    NoReasoningModelSelectedError,
    NothingToReviewError,
    PathValidationError,
    PersistenceError,
    PolicyConflictError,
    PolicyFormatError,
    PolicyNotFoundError,
    ProviderError,
    RepositoryCheckoutError,
    ReviewHasNoReportError,
    ReviewNotCancellableError,
    ReviewNotFoundError,
    ReviewStillRunningError,
    StaleAtlasError,
)
from archcompass.domain.fingerprint import boundary_fingerprint
from archcompass.domain.lineage import RepositoryBranch
from archcompass.domain.policy import (
    PolicyDocument,
    PolicyDraft,
    PolicySourceRegistration,
)
from archcompass.domain.review import (
    BoundaryExcerpt,
    BoundaryReview,
    ReviewedBoundary,
    ReviewStatus,
)
from archcompass.domain.review_conversation import ReviewConversation, ReviewMessage
from archcompass.domain.scope import RepositoryFolderTree
from archcompass.domain.triage import DecisionComment, DecisionState, StandingDecision
from archcompass.domain.workspace import (
    BoundaryReviewSummary,
    CaseSummary,
    RepositorySummary,
)
from archcompass.presentation.web.restrictions import (
    FetchBudget,
    HostedRefusal,
    HostedRestrictions,
    RunBudget,
)
from archcompass.presentation.web.runtimes import (
    RuntimeProvider,
    SingleRuntimeProvider,
    session_token,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProblemDetail(APIModel):
    code: str
    message: str
    retryable: bool = False
    field_errors: list[str] = Field(default_factory=list[str])


_PROBLEM_RESPONSE_DESCRIPTIONS = {
    404: "The requested pinned resource was not found.",
    409: "The request conflicts with the current persisted revision or pinned state.",
    422: "The request or generated evidence did not satisfy the validated contract.",
    503: "A configured model provider is temporarily unavailable.",
}


def _problem_responses(
    *statuses: Literal[404, 409, 422, 503],
) -> dict[int | str, dict[str, Any]]:
    return {
        status: {
            "model": ProblemDetail,
            "description": _PROBLEM_RESPONSE_DESCRIPTIONS[status],
        }
        for status in statuses
    }


class RepositoryPathRequest(APIModel):
    root_path: str = Field(min_length=1)


class RepositoryIndexRequest(RepositoryPathRequest):
    """A repository to index, and optionally the folders to leave out of the analysis.

    The scope is optional and stays optional. A client that has never heard of it sends the
    payload it always sent and gets the scope this repository was last indexed under — which
    is what somebody who narrowed a review and then pressed re-index means, and is also why
    omitting the field cannot mean "all of it". Saying "all of it" is sending `[]`.
    """

    excluded_paths: list[str] | None = None


class RepositoryCheckoutRequest(APIModel):
    """A repository named by address, or by a path on this machine.

    One field for both because they are one question — "which repository" — and asking the
    caller to say which kind they are holding would only make them classify a string the
    service classifies better.
    """

    url: str = Field(min_length=1)
    #: The branch to review. Left out, the remote's own default is used, which is what
    #: someone pasting an address without further thought means.
    branch: str | None = None


class StartFromRepositoryRequest(APIModel):
    """Which repository to open, and whether to carry on from where it was left.

    Continuing is the default because a repeat visit almost always means the same
    conversation: the questions the last run asked and the answers the reader gave are on
    that case, and starting beside them would ask for them again. Starting clean is the
    stated exception — a different question about the same code — and it has to be stated
    rather than reached by deleting something.
    """

    root_path: str = Field(min_length=1)
    start_clean: bool = False


class AtlasExploreRequest(APIModel):
    root_path: str = Field(min_length=1)
    operation: Literal[
        "children",
        "dependencies",
        "dependants",
        "callers",
        "implementations",
        "tests",
        "forward_neighbourhood",
        "reverse_neighbourhood",
        "search",
        "shortest_path",
        "cycles",
        "signals",
    ]
    node_id: str | None = None
    target_id: str | None = None
    terms: list[str] = Field(default_factory=list, max_length=10)
    signal_codes: list[str] = Field(default_factory=list, max_length=10)
    depth: int = Field(default=1, ge=1, le=5)
    limit: int = Field(default=50, ge=1, le=100)

    @model_validator(mode="after")
    def validate_operation_fields(self) -> AtlasExploreRequest:
        if self.operation == "search" and not self.terms:
            raise ValueError("search requires at least one term")
        if self.operation not in {"search", "cycles", "signals"} and self.node_id is None:
            raise ValueError(f"{self.operation} requires node_id")
        if self.operation == "shortest_path" and self.target_id is None:
            raise ValueError("shortest_path requires target_id")
        return self


class ReviewContextRequest(APIModel):
    """The nodes a map is being drawn around, asked for together.

    Together rather than one at a time because a node's edges are only drawable once its
    neighbours are known, and a client that asked per node would be told about edges whose
    other end it never received.
    """

    root_path: str = Field(min_length=1)
    node_ids: list[str] = Field(min_length=1, max_length=40)
    limit: int = Field(default=25, ge=1, le=100)


class ReviewRequest(APIModel):
    case_id: str = Field(min_length=1)
    repository_root: str = Field(min_length=1)
    #: The first pass whose questions produced this case revision, where this run is the
    #: second pass of an elicitation. Absent for every review that was not reached by
    #: answering, which is the ordinary start. Supplying it is what stops the run asking
    #: again: a second pass concludes rather than eliciting, and the loop terminates.
    elicited_from: str | None = Field(default=None, min_length=1)


class SubmittedAnswer(APIModel):
    """One answer: which question it settles, and what the reader typed before saving.

    No question and no destination. Both are the question's own properties, read from the
    review by the server — a client that could send the question could put words in a review's
    mouth, and one that could name the field could give an answer a weight its question never
    asked for, with nothing afterwards able to tell either apart from a question that did.

    `recorded_text` is the answer verbatim. It used to be a line the browser composed by
    joining the question's subject to the reply, because the case had nowhere to keep the pair;
    the case keeps pairs now (ADR 0014), so this is the reader's words and nothing else.
    """

    question_reference: str = Field(pattern=r"^Q-[0-9]+$")
    recorded_text: str = Field(min_length=1, max_length=4000)


class ReviewAnswersRequest(APIModel):
    #: Only the questions that were answered. Skipping is normal and is recorded as absence,
    #: so a blank entry is refused rather than stored as an answer nobody gave.
    answers: list[SubmittedAnswer] = Field(min_length=1)


class ReviewConversationCreateRequest(APIModel):
    review_id: str = Field(min_length=1)
    title: str | None = Field(default=None, min_length=1)
    #: `Q-n` to talk about one open question rather than the review as a whole (§6C.7).
    #: The only form of conversation a review still waiting on answers will open, and
    #: resolved against that review's own report — a reference it did not ask is refused.
    question_reference: str | None = Field(default=None, pattern=r"^Q-[0-9]+$")


class ReviewQuestionRequest(APIModel):
    question: str = Field(min_length=1, max_length=4000)


class DecisionRequest(APIModel):
    """A disposition somebody took, together with the verdict they took it against.

    The verdict context is sent by the client rather than looked up here, and that is the
    point of it: it records what was actually on the reader's screen. Resolving it server-side
    from the review would record what the server believes now, which is the one thing the
    field exists to be able to disagree with.
    """

    branch_id: str = Field(min_length=1)
    boundary_fingerprint: str = Field(min_length=1)
    state: DecisionState
    author: str = Field(min_length=1)
    #: Required when waiving, and the request is refused without it rather than stored as a
    #: silent waiver.
    reason: str | None = None
    review_id: str = Field(min_length=1)
    boundary_reference: str = Field(pattern=r"^BR-[0-9]{3}$")
    material: bool
    verdict_label: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_as_a_decision(self) -> DecisionRequest:
        """Refuse here whatever the domain would refuse, using the domain to decide.

        Building the aggregate is the check. Restating its rules in this model would be two
        places for one invariant, and the one that drifts is always the copy — while this way
        a body that cannot become a `StandingDecision` fails as a 422 naming the field, rather
        than as a 500 raised on the line that tried.
        """

        self.as_decision()
        return self

    def as_decision(self) -> StandingDecision:
        return StandingDecision(
            branch_id=self.branch_id,
            boundary_fingerprint=self.boundary_fingerprint,
            state=self.state,
            author=self.author,
            reason=self.reason,
            review_id=self.review_id,
            boundary_reference=self.boundary_reference,
            material=self.material,
            verdict_label=self.verdict_label,
        )


class BulkDecisionBoundary(APIModel):
    """One boundary in a bulk decision, with the verdict the reader took it against.

    The verdict context is per boundary and cannot be hoisted onto the request, for the same
    reason a single decision carries it: it records what was actually on screen. Forty
    boundaries were forty different verdicts, and a single `material` on the envelope would be
    a claim about all of them that is false for most.
    """

    boundary_fingerprint: str = Field(min_length=1)
    boundary_reference: str = Field(pattern=r"^BR-[0-9]{3}$")
    material: bool
    verdict_label: str = Field(min_length=1)


class BulkDecisionRequest(APIModel):
    """One disposition, taken over many boundaries at once, by one person.

    What replaced bulk baselining. The shape is deliberately the same shape as deciding one
    boundary — a state, an author, a reason where one is required — repeated over a list,
    because that is exactly what it does: it writes N standing decisions, each with a name on
    it, rather than one administrative act that silences a list nobody read.
    """

    branch_id: str = Field(min_length=1)
    state: DecisionState
    author: str = Field(min_length=1)
    #: Required when waiving, refused without it, exactly as a single decision is. A bulk
    #: waiver with no reason would be the baseline coming back wearing an author's name.
    reason: str | None = None
    review_id: str = Field(min_length=1)
    #: At least one: a bulk decision over nothing is a request that means nothing, and
    #: answering it with a cheerful zero would hide a client that failed to build its list.
    boundaries: list[BulkDecisionBoundary] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_as_decisions(self) -> BulkDecisionRequest:
        """Refuse here whatever the domain would refuse, using the domain to decide.

        Building the aggregates is the check, as it is for a single decision. Every one of them
        is built, not just the first: a list with a duplicate fingerprint or a malformed
        reference in the fortieth entry has to fail as a 422 naming the field rather than as a
        500 raised partway through the write.
        """

        self.as_decisions()
        return self

    def as_decisions(self) -> list[StandingDecision]:
        return [
            StandingDecision(
                branch_id=self.branch_id,
                boundary_fingerprint=item.boundary_fingerprint,
                state=self.state,
                author=self.author,
                reason=self.reason,
                review_id=self.review_id,
                boundary_reference=item.boundary_reference,
                material=item.material,
                verdict_label=item.verdict_label,
            )
            for item in self.boundaries
        ]


class BulkDecisionResponse(APIModel):
    """What one bulk decision wrote, and everything it now stands as."""

    branch_id: str
    recorded: int
    decisions: list[StandingDecision]


class DecisionCommentRequest(APIModel):
    """One remark in a boundary's thread. Its position is assigned by the server."""

    author: str = Field(min_length=1)
    body: str = Field(min_length=1)


class BranchDecisionsResponse(APIModel):
    """Everything one branch currently thinks about the boundaries it has opinions on.

    Comment counts are reported separately from decisions rather than beside them, because
    the two sets differ: a boundary can be argued about before anyone decides anything, and a
    count folded into the decision list would have nowhere to put that thread. A fingerprint
    missing from either map is the honest absence — undecided, or undiscussed.
    """

    branch_id: str
    #: One per boundary this branch has decided on, latest decision only.
    decisions: list[StandingDecision]
    #: Fingerprint to number of comments, for every discussed boundary on the branch.
    comment_counts: dict[str, int]


class JoinedDecision(APIModel):
    """The current decision as a review's reader needs to see it."""

    decision_id: str
    state: DecisionState
    author: str
    reason: str | None = None
    decided_at: datetime
    #: False when this run's verdict for the boundary differs from the one the decision was
    #: taken against. Not an expiry — the decision still stands — but the reader is told the
    #: ground moved, and re-affirming it is a human act.
    taken_on_current_verdict: bool


class BoundaryTriage(APIModel):
    """What triage knows about one boundary of one review.

    Carried beside the report rather than inside it: a `ReviewedBoundary` is part of an
    immutable judgement, and joining a team's later opinion into that document would make the
    review look like it had changed its mind.
    """

    #: The `BR-nnn` this boundary has in this review — how a client matches it to the report.
    reference: str
    #: Its structural identity, which is what a decision is actually filed under.
    fingerprint: str
    #: Absent where nobody has decided, and for every review that predates branch lineages:
    #: with no branch there is nothing to look the decision up on.
    decision: JoinedDecision | None = None
    comment_count: int = 0




class AnswerProse(APIModel):
    """A fragment of the answer being written, to append to whatever came before.

    Text only, and never a citation: grounding comes from positional flags that do not exist
    until the whole reply has arrived, so there is nothing here a reader could mistake for
    something the review supports. Fragments may stop before the answer does — a reply that
    needs the one sanctioned repair round is rewritten unstreamed — so this is provisional
    until the `answered` line.
    """

    event: Literal["prose"] = "prose"
    text: str


class QuestionAnswered(APIModel):
    """The appended message — the same object `POST .../messages` returns.

    This line is the record, and it replaces rather than completes whatever prose arrived
    before it: the message carries the validated answer and its grounding, and a turn that
    failed carries the failure even if fragments were shown first.
    """

    event: Literal["answered"] = "answered"
    message: ReviewMessage


class QuestionFailed(APIModel):
    """The turn could not be attempted, so no message was appended.

    Distinct from a failed message: a question refused before it reached the reasoner — blank,
    too long, a conversation that is gone — never becomes part of the history, and the status
    code cannot say so once the response has started.
    """

    event: Literal["failed"] = "failed"
    problem: ProblemDetail


AnswerProgressLine = Annotated[
    AnswerProse | QuestionAnswered | QuestionFailed,
    Field(discriminator="event"),
]


class AnswerProgress(RootModel[AnswerProgressLine]):
    """One line of `POST /api/review-conversations/{id}/messages/stream`."""


class DirectoryEntry(APIModel):
    """One subdirectory of the directory being browsed."""

    name: str
    path: str


class DirectoryListing(APIModel):
    """One local directory as a folder picker reads it: where it is, and what is under it."""

    path: str
    #: Null at the filesystem root, which is where climbing stops.
    parent: str | None
    directories: list[DirectoryEntry]


class BundledExample(APIModel):
    """One example repository shipped with ArchCompass, ready to review.

    A repository and a name for it, and deliberately no case: the review asks what it needs
    to know, and the answers write the case. The repository path is absolute and resolved
    on the server, because the browser cannot know where the package was installed.
    """

    name: str
    title: str
    description: str
    repository_root: str


class ReviewStarted(APIModel):
    """The run has a record, so it has an identity — the stream's first line.

    Sent before detection, because this is the moment the review can be opened: everything
    that could refuse the run has passed, and a client that has this can leave the page it
    started from and watch the run where it lives.
    """

    event: Literal["started"] = "started"
    review_id: str
    case_id: str
    case_revision: int
    #: Which pass this is, echoed back so a watcher can draw the run's stages without
    #: having to remember what it asked for. A client that reloaded onto a stream it did
    #: not start has no other way to know.
    elicited_from: str | None = None


class ReviewDetected(APIModel):
    """The deterministic sweep finished, so the run now has a known length.

    The boundaries are named in judgement order, which is the order the review will store
    them in and the order every later position refers to.
    """

    event: Literal["detected"] = "detected"
    total: int
    boundaries: list[str]


class ReviewJudged(APIModel):
    """One boundary judged. `position` counts from one, in the detected order."""

    event: Literal["judged"] = "judged"
    position: int
    total: int
    abstraction: str
    material: bool
    #: The review this verdict was carried forward from, where it was not reached in this
    #: run. Null on every verdict the run actually paid a model call for, and on every line
    #: written before this field existed — so a client that sees nothing here is looking at
    #: a judged boundary, which is what it assumed all along.
    verdict_reused_from: str | None = None
    #: How many verdicts have been carried so far, this one included. Sent rather than left
    #: to the client to accumulate, so a watcher that joined the stream late — or dropped a
    #: line — still has the run's own count instead of a tally of what it happened to see.
    carried: int = 0


class ReviewEliciting(APIModel):
    """Every boundary is judged; the first pass is composing what it needs to ask.

    Distinct from `summarising` because it is a different call with a different outcome: one
    ends in a conclusion, the other may end in a run that stops and waits for a person.
    Exactly one of the two arrives in any run.
    """

    event: Literal["eliciting"] = "eliciting"
    total: int


class ReviewSummarising(APIModel):
    """Every boundary is judged; one call remains, over all of them at once."""

    event: Literal["summarising"] = "summarising"
    total: int


class ReviewCompleted(APIModel):
    """The composed, persisted review — the same object the non-streaming route returns."""

    event: Literal["completed"] = "completed"
    review: BoundaryReview


class ReviewUnchanged(APIModel):
    """The run refused itself: nothing has moved since the branch's latest revision.

    A terminal line and not a failure — the workspace worked the whole partition out and
    the answer was that a revision would repeat the one before it, so nothing was recorded.
    Emitted before a `started` line could exist, because refusal happens before the run has
    a record.
    """

    event: Literal["unchanged"] = "unchanged"
    #: The revision this repository is already up to date with.
    current_against: str
    message: str


class ReviewFailed(APIModel):
    """The run failed. Nothing was persisted; the case and atlas are untouched."""

    event: Literal["failed"] = "failed"
    problem: ProblemDetail


ReviewProgressLine = Annotated[
    ReviewStarted
    | ReviewDetected
    | ReviewJudged
    | ReviewEliciting
    | ReviewSummarising
    | ReviewCompleted
    | ReviewUnchanged
    | ReviewFailed,
    Field(discriminator="event"),
]


class ReviewProgress(RootModel[ReviewProgressLine]):
    """One line of `POST /api/reviews/stream`, discriminated by `event`."""


class NDJSONStreamingResponse(StreamingResponse):
    """A stream of one JSON object per line.

    Declared as a class so the OpenAPI document says `application/x-ndjson` where the
    schema is: a body that is a sequence of lines is not one JSON document, and describing
    it as `application/json` would tell a generated client the wrong thing to parse.
    """

    media_type = "application/x-ndjson"


class PolicySourceRequest(APIModel):
    source: str = Field(min_length=1)


class ModelIdentity(APIModel):
    provider: str
    model: str
    #: Whether this model reasons before answering: `true` required, `false` forbidden,
    #: absent left to the model. Part of what was chosen, so part of what is reported.
    thinking: bool | None = None


class WorkspaceModels(APIModel):
    """The one model a review needs, and what is currently known about it.

    An embedding identity was reported here too, for a policy index that no longer exists:
    every policy is presented whole to the judging stage, so nothing is embedded and there
    is nothing for a reader to check about a model that decided nothing (ADR 0013).
    """

    #: Absent where this workspace has not chosen a model and nothing configured one for it.
    #: A state to display rather than an error to raise: everything a review does not need a
    #: model for still works, and the interface asks for one where it is actually required.
    reasoning: ModelIdentity | None = None
    #: What the last run against this model said when it failed. Empty when the last run
    #: succeeded, when none has run, or once a probe has since found the provider healthy.
    #: The half of a model's health no probe can see: a spent quota lists perfectly well.
    failure: str = ""
    #: This process was told which model to use on its command line, so the model is not the
    #: workspace's to change while it lasts. The chooser says so instead of offering a
    #: choice that would be ignored.
    pinned: bool = False


class WorkspaceSummaryResponse(APIModel):
    #: Where this workspace's state lives, for a reader who may want to open it. A hosted
    #: workspace says what it is instead of where it is: its directory is named after the
    #: session cookie, and that cookie is HttpOnly precisely so a page cannot read it.
    workspace: str
    models: WorkspaceModels
    #: Whether this is the hosted demo, where the folder picker is off and only the bundled
    #: examples can be reviewed. Defaults to false, so a client written against a local
    #: workspace reads the same document it always did.
    hosted: bool = False
    #: The hosts this workspace will fetch a repository from, when it fetches rather than
    #: clones. Empty on a local workspace, which clones from anywhere its git can reach.
    #: Sent so the start step can name them in the field rather than leave a reader to find
    #: the list one refusal at a time.
    source_hosts: list[str] = Field(default_factory=list)


class AvailableModelResponse(APIModel):
    """One model a provider currently offers, in one of the thinking modes it has.

    A model that reasons both ways appears twice, once per mode, because the two are
    genuinely different choices: they cost differently and answer differently. A model with
    one mode appears once.
    """

    provider: str
    model: str
    thinking: bool | None = None
    label: str = ""
    input_token_limit: int | None = None
    output_token_limit: int | None = None
    is_selected: bool = False


class ProviderAvailabilityResponse(APIModel):
    """Whether one enabled provider answered, and what it said if it did not."""

    provider: str
    available: bool
    #: Why not, naming the cure where there is one. Empty when available.
    detail: str = ""
    probed_at: datetime


class ModelCatalogResponse(APIModel):
    providers: list[ProviderAvailabilityResponse]
    candidates: list[AvailableModelResponse]


class ModelSelectionRequest(APIModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    #: Absent means the model's own default, which is a third choice rather than the absence
    #: of one — so it is sent as null rather than omitted where a page means it.
    thinking: bool | None = None


class PolicySourceRemovalResponse(APIModel):
    removed: bool


class ReviewDetailResponse(BoundaryReview):
    """A stored review as it is read, with what the team has since made of it.

    One join, and it is the only one left. The baseline comparison used to sit here too — a
    `new`/`changed`/`known` disposition per boundary, recomputed on every read — and it is gone
    with the baseline itself. What replaced it was already on the document: the revision
    partition, recorded when the run made the comparison. A client finds the summary at
    `report.delta` — the counts, the revision it was compared with, and the boundaries that
    closed — and each boundary's own state at `report.reviewed[].delta_state`. Nothing here
    recomputes either, and nothing copies them to the top level: one path to a value is the
    only way two paths cannot disagree.

    The distinction the removal turned on is worth keeping in view. A delta is a fact about two
    immutable revisions, so it is stored. A standing decision is a fact about *now* — it moves
    the moment somebody decides something — so it is joined at read time and never written into
    the review, which would freeze an answer that is supposed to move.
    """

    #: One entry per reviewed boundary, in report order — the team's standing decisions and
    #: threads, joined on at read time. Empty for a review that reached no verdicts.
    boundary_triage: list[BoundaryTriage] = Field(default_factory=list[BoundaryTriage])


def _acquire_runtime(request: Request) -> Runtime:
    """The workspace this request is served from.

    A dependency rather than something the routes close over, because which workspace that
    is stopped being a property of the process the moment one deployment served more than
    one visitor. Everything the provider decides — one workspace or one per session — it
    decides here, once per request.
    """

    provider: RuntimeProvider = request.app.state.runtimes
    return provider.acquire(request)


#: What a deployment learns from, which is not the same as what it shows a visitor. A demo
#: that only ever answers "this repository is more than I will analyse" tells the person in
#: front of it something useful and tells the people running it nothing: not how often it
#: happens, not by how much, and so not whether the limit is in the right place or the
#: analyser is in the wrong shape.
#:
#: One line per refusal, to standard output, which is where a container's logs are read from.
#: No counters, no metrics endpoint, no store: the question is "is this limit the thing
#: standing between visitors and a review", and a week of lines answers it.
_refusals = logging.getLogger("archcompass.refusals")


def _log_refusal(request: Request, code: str, message: str) -> None:
    """Say what was declined and why, in the words the visitor was given.

    The message carries the numbers — how many megabytes, how many modules, which address —
    because they were written for a reader and are the same facts a deployment wants. Logged
    rather than parsed into fields for the same reason nothing here is counted: a line is
    enough to answer the question this exists to answer.
    """

    _refusals.info(
        "refused %s %s: %s — %s", request.method, request.url.path, code, message
    )


def _acquire_restrictions(request: Request) -> HostedRestrictions:
    restrictions: HostedRestrictions = request.app.state.restrictions
    return restrictions


def spend_model_budget(request: Request) -> None:
    """Admit one run against this session's and this instance's daily budget.

    Declared on the routes that make model calls rather than on all of them: reading a
    stored review costs nothing, and a demo that rationed reading would be measuring the
    wrong thing. Nothing is metered in local mode, where there is no budget object.
    """

    budget: RunBudget | None = request.app.state.budget
    if budget is not None:
        budget.admit(session_token(request))


def spend_fetch_budget(request: Request) -> None:
    """Admit one repository fetch against this session's and this instance's daily budget.

    Separate from the model budget because a fetch spends something else — bandwidth, and the
    room a container has left on a filesystem that is usually memory. Nothing is metered in
    local mode, where there is no budget object.
    """

    budget: FetchBudget | None = request.app.state.fetch_budget
    if budget is not None:
        budget.admit(session_token(request))


#: How long a request waits for the one indexing slot before giving up. Long enough that an
#: ordinary queue behind one repository clears, short enough that a caller is told rather
#: than left holding a connection open for the whole of somebody else's analysis.
INDEX_QUEUE_SECONDS = 90


def serialise_indexing(request: Request) -> Iterator[None]:
    """Let one analysis run at a time, where they share a machine.

    Analysis is the expensive thing this server does — a repository at the hosted size limit
    peaks in the hundreds of megabytes — and two of them overlapping is how a container sized
    for one of them dies. Cloud Run's own concurrency setting cannot express this: it cannot
    tell an index from somebody reading a stored review, and throttling both to protect one
    would make the demo feel broken for everybody who is only reading.

    Queued rather than refused, because the wait is seconds and the alternative is asking
    somebody to press the button again. Nothing is serialised where there is no lock, which
    is every local workspace: it has one user, who is not racing themselves.
    """

    lock: BoundedSemaphore | None = request.app.state.index_lock
    if lock is None:
        yield
        return
    if not lock.acquire(timeout=INDEX_QUEUE_SECONDS):
        raise HostedRefusal(
            503,
            "busy",
            "This demo is analysing another repository and only does one at a time. Try "
            "again in a moment.",
        )
    try:
        yield
    finally:
        lock.release()


RuntimeDep = Annotated[Runtime, Depends(_acquire_runtime)]
RestrictionsDep = Annotated[HostedRestrictions, Depends(_acquire_restrictions)]
#: What the routes that spend model tokens carry. A dependency with no value, so it is
#: declared beside the route's own decorator arguments rather than in its signature.
SpendsModelBudget = Depends(spend_model_budget)
#: The same, for the one route that puts a repository on this instance's disk.
SpendsFetchBudget = Depends(spend_fetch_budget)
#: What the routes that build an atlas carry, so two never build one at once.
SerialisesIndexing = Depends(serialise_indexing)


def create_app(
    runtime: Runtime | RuntimeProvider,
    *,
    hosted: bool = False,
    budget: RunBudget | None = None,
    fetch_budget: FetchBudget | None = None,
) -> FastAPI:
    """The HTTP surface over one workspace, or over a provider that chooses one per request.

    A bare `Runtime` is still accepted because that is what a local run has: the CLI opens
    one workspace before the server starts, and wrapping it in a provider at every call site
    would be ceremony around a thing that never varies.
    """

    runtimes = (
        SingleRuntimeProvider(runtime) if isinstance(runtime, Runtime) else runtime
    )
    app = FastAPI(
        title="Arch Compass Local API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        responses=_problem_responses(422),
    )
    # On the app rather than in a closure so the dependencies can be module-level functions:
    # a dependency named in an annotation is resolved against module globals, and one
    # defined inside `create_app` cannot be referred to from a route's signature at all.
    app.state.runtimes = runtimes
    app.state.restrictions = HostedRestrictions(hosted=hosted)
    app.state.budget = budget
    app.state.fetch_budget = fetch_budget
    # One slot, and only where a machine is shared. `BoundedSemaphore` rather than a plain
    # one so a release that was never acquired is an error here rather than a slow leak of
    # permits that quietly stops serialising anything.
    app.state.index_lock = BoundedSemaphore(1) if hosted else None

    @app.exception_handler(HostedRefusal)
    async def hosted_refusal(request: Request, error: HostedRefusal) -> JSONResponse:
        _log_refusal(request, error.code, error.message)
        return JSONResponse(
            status_code=error.status_code,
            content=ProblemDetail(
                code=error.code,
                message=error.message,
            ).model_dump(mode="json"),
        )

    @app.exception_handler(ArchCompassError)
    async def archcompass_error(
        request: Request, error: ArchCompassError
    ) -> JSONResponse:
        status, code, retryable = _classify_error(error)
        # 4xx only. A 500 is this program being wrong and belongs in a traceback; a 422 or a
        # 409 is the workspace declining on purpose, which is the thing worth counting.
        if 400 <= status < 500:
            _log_refusal(request, code, str(error))
        return JSONResponse(
            status_code=status,
            content=ProblemDetail(
                code=code,
                message=str(error),
                retryable=retryable,
            ).model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(
        _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        fields = [
            ".".join(str(item) for item in detail["loc"])
            + ": "
            + str(detail["msg"])
            for detail in error.errors()
        ]
        # The fields are in the message, not only beside it. "The request did not match the
        # API contract" is true of every possible cause and points at none of them; a reader
        # who saw `body.elicited_from: Extra inputs are not permitted` would have known in one
        # glance that their page and their server disagreed about what a review request is.
        detail = f" ({'; '.join(fields)})" if fields else ""
        return JSONResponse(
            status_code=422,
            content=ProblemDetail(
                code="validation_error",
                message=f"The request did not match the API contract{detail}.",
                field_errors=fields,
            ).model_dump(mode="json"),
    )

    @app.get("/api/workspace")
    def workspace_summary(
        runtime: RuntimeDep, hosted_mode: RestrictionsDep
    ) -> WorkspaceSummaryResponse:
        return _summary(runtime, hosted_mode)

    @app.get("/api/models")
    def model_catalog(runtime: RuntimeDep) -> ModelCatalogResponse:
        """Every enabled provider, whether it answered, and what it offered.

        A GET that performs work: each provider is asked, over the network, with its own
        short budget. It also writes, in one narrow sense — a provider that answers clears a
        failure recorded against the current selection. Idempotent, and the alternative was
        making the chooser's first paint a mutation.
        """

        catalog = runtime.model_catalog_service.catalog()
        return ModelCatalogResponse(
            providers=[
                ProviderAvailabilityResponse(
                    provider=provider.provider,
                    available=provider.available,
                    detail=provider.detail,
                    probed_at=provider.probed_at,
                )
                for provider in catalog.providers
            ],
            candidates=[
                AvailableModelResponse(
                    provider=candidate.provider,
                    model=candidate.model,
                    thinking=candidate.thinking,
                    label=candidate.label,
                    input_token_limit=candidate.input_token_limit,
                    output_token_limit=candidate.output_token_limit,
                    is_selected=candidate.is_selected,
                )
                for candidate in catalog.candidates
            ],
        )

    @app.put("/api/models/selection", responses=_problem_responses(409))
    def select_model(
        runtime: RuntimeDep,
        hosted_mode: RestrictionsDep,
        request: ModelSelectionRequest,
    ) -> WorkspaceSummaryResponse:
        """Choose the model this workspace reasons with, until it chooses another.

        Returns the whole summary rather than the selection, so the page that asked can
        replace what its chip is reading instead of fetching it again.
        """

        runtime.model_catalog_service.select(
            request.provider, request.model, request.thinking
        )
        return _summary(runtime, hosted_mode)

    @app.delete("/api/models/selection", status_code=204)
    def clear_model_selection(runtime: RuntimeDep) -> Response:
        """Forget the choice, leaving this workspace with no model until it makes another.

        The way back out of a choice that turned out to be wrong. There is no file to edit
        instead, and on a hosted workspace there never was one.
        """

        runtime.model_catalog_service.clear()
        return Response(status_code=204)

    @app.get("/api/cases")
    def list_cases(
        runtime: RuntimeDep,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[CaseSummary]:
        return runtime.case_service.list(limit=limit)

    @app.post("/api/cases", status_code=201)
    def create_case(runtime: RuntimeDep, case: ArchitectureCase) -> CaseRevision:
        return runtime.case_service.create(case)

    @app.post("/api/cases/import-yaml", status_code=201)
    def import_case_yaml(
        runtime: RuntimeDep,
        source: Annotated[str, Body(media_type="text/yaml")],
    ) -> CaseRevision:
        try:
            case = ArchitectureCase.model_validate(yaml.safe_load(source))
        except (yaml.YAMLError, ValidationError, TypeError, ValueError) as error:
            raise ModelOutputValidationError(f"Invalid architecture case YAML: {error}") from error
        return runtime.case_service.create(case)

    @app.get("/api/cases/{case_id}")
    def get_case(runtime: RuntimeDep, case_id: str, revision: int | None = None) -> CaseRevision:
        return runtime.case_service.show(case_id, revision)

    @app.patch("/api/cases/{case_id}")
    def update_case(runtime: RuntimeDep, case_id: str, update: CaseUpdate) -> CaseRevision:
        return runtime.case_service.update(case_id, update)

    @app.get("/api/cases/{case_id}/history")
    def case_history(runtime: RuntimeDep, case_id: str) -> list[CaseRevision]:
        return runtime.case_service.history(case_id)

    @app.get("/api/repositories")
    def list_repositories(
        runtime: RuntimeDep,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[RepositorySummary]:
        return runtime.repository_service.list(limit=limit)

    @app.get("/api/branches")
    def list_branches(runtime: RuntimeDep) -> list[RepositoryBranch]:
        """Every branch lineage this workspace has seen, with the repository it belongs to.

        The listing above answers "which checkouts have been indexed", which is a question
        about this machine. This one answers "which repositories and lines of work does this
        workspace know about", which is the question that survives the checkout moving.
        """

        return runtime.repository_service.branches()

    @app.post(
        "/api/repositories/index",
        status_code=201,
        dependencies=[SerialisesIndexing],
    )
    def index_repository(
        runtime: RuntimeDep,
        hosted_mode: RestrictionsDep,
        request: RepositoryIndexRequest,
    ) -> AtlasVersion:
        return runtime.repository_service.index(
            hosted_mode.repository_root(Path(request.root_path), runtime),
            excluded_paths=request.excluded_paths,
        )

    @app.post("/api/repositories/tree", responses=_problem_responses(422))
    def repository_tree(
        runtime: RuntimeDep,
        hosted_mode: RestrictionsDep,
        request: RepositoryPathRequest,
    ) -> RepositoryFolderTree:
        """What is in this repository, two levels deep, so a caller can choose what to skip.

        Validated through the same restriction as indexing, because it reads the same
        directories: a route that would list any folder on the server is the folder picker
        this deployment already refuses, wearing a different name.

        Spends no budget. Walking a directory costs neither model tokens nor disk, and the
        listing exists to make a *smaller* analysis possible — rationing it would ration the
        cheap step that avoids the expensive one.
        """

        return folder_tree(hosted_mode.repository_root(Path(request.root_path), runtime))

    # 200 rather than 201: this route stopped always creating something the moment a repeat
    # visit began continuing the case it already had, and a client told "created" about a case
    # written last week has been told the wrong thing about the only fact it could act on.
    @app.post(
        "/api/repositories/checkout",
        status_code=201,
        responses=_problem_responses(409, 422),
        dependencies=[SpendsFetchBudget],
    )
    def checkout_repository(
        runtime: RuntimeDep,
        hosted_mode: RestrictionsDep,
        request: RepositoryCheckoutRequest,
    ) -> RepositoryCheckout:
        """Make the named repository available on this machine, and say where it landed.

        Nothing is indexed here. The answer is a folder, which is what `/api/repositories/index`
        and `/api/repositories/start` have always taken — so a repository pasted as a URL joins
        the existing flow at exactly the point a repository chosen with the picker does.

        201 for a checkout that was updated as much as for one that was cloned: something was
        written to disk either way, and `created` says which of the two happened.
        """

        # A workspace that was given hosts to fetch from has no business running git: the
        # whole reason it exists is that an extracted archive cannot carry hooks, submodules,
        # filters, credentials or a transport nobody asked for. Checked here rather than
        # inside the checkout service, because which of the two ways a repository arrives is
        # a property of the deployment, and the deployment is what this layer knows.
        source_service = runtime.source_service
        if source_service is not None:
            return source_service.fetch(request.url, branch=request.branch)
        hosted_mode.checkout()
        return runtime.checkout_service.checkout(request.url, branch=request.branch)

    @app.post(
        "/api/repositories/refresh",
        responses=_problem_responses(409, 422),
    )
    def refresh_repository(
        runtime: RuntimeDep,
        hosted_mode: RestrictionsDep,
        request: RepositoryPathRequest,
    ) -> CheckoutRefresh:
        """Pull whatever has landed on the remote since, for a folder Arch Compass cloned.

        Takes a path rather than an address because a path is what a page reviewing a
        repository has: the URL was typed once, at the start, and nothing downstream of that
        carries it. The address is read back out of the checkout instead.

        A folder that is not one of ours answers rather than refuses — `managed: false`, and
        nothing written. That is the ordinary case for a repository reviewed where it lies,
        and the caller is meant to carry on and run its review against what is on disk.

        The hosted restriction is the checkout one, unchanged: a demo that will not clone a
        repository will not fetch into one either, and it has no managed checkouts for this
        to be about in the first place.
        """

        # Nothing to bring up to date, and that is an answer rather than a refusal. Every run
        # begins by asking for this unconditionally — it is how a managed checkout is made
        # current before it is reviewed — so a workspace whose repositories are extracted
        # archives has to say "nothing was touched" here, exactly as it does for somebody
        # else's working copy. Refusing would fail every review on the way to its first
        # model call. Asking for it again is what re-fetches: paste the address.
        source_service = runtime.source_service
        if source_service is not None:
            # The one place a run can notice that its code is gone, and the one place that
            # can do something about it. This workspace deletes the least recently used
            # source to stay inside its memory, so a repository reviewed an hour ago may
            # have been swept since — and every run begins by asking for this, which makes
            # it exactly where "bring the code up to date" should mean "and bring it back
            # if it is not there". Fetched again at the revision it was served the first
            # time, so the line numbers the atlas holds still point at the same code.
            restored = source_service.restore(Path(request.root_path))
            return CheckoutRefresh(
                root_path=request.root_path, managed=restored, updated=False
            )
        hosted_mode.checkout()
        return runtime.checkout_service.refresh(request.root_path)

    @app.post(
        "/api/repositories/start",
        responses=_problem_responses(404, 422),
        dependencies=[SerialisesIndexing],
    )
    def start_from_repository(
        runtime: RuntimeDep,
        hosted_mode: RestrictionsDep,
        request: StartFromRepositoryRequest,
    ) -> CaseRevision:
        """Index a repository and answer with the case to review it against.

        The whole of the first step for someone who has not authored a case. Both halves
        happen here so the flow either produces something reviewable or fails outright,
        rather than leaving a case pointing at an atlas that was never built. A bundled
        example arrives here too, once its repository has been indexed.

        A first visit opens a case with nothing written in it yet. A repeat visit continues
        the newest case reviewed on this **branch**, so the answers the reader has already
        given are still there to be judged against — `start_clean: true` is how they say the
        next run is about a different question and should begin with an empty case again.

        The branch rather than the repository, because a branch is the scope everything
        durable lives in: its standings, its revisions, and its case. Two branches of one
        repository are two pieces of work, and a feature branch inheriting `main`'s case would
        be handed answers about code it has not written.

        Which case that is, is the application's to decide and not the client's: a browser
        that picked one would be reading the review history to guess at the case that history
        is about, and two clients would guess differently.
        """

        root = hosted_mode.repository_root(Path(request.root_path), runtime)
        version = runtime.repository_service.index(root)
        if request.start_clean:
            return runtime.case_service.start_from_repository(root)
        return runtime.case_service.continue_from_repository(
            root, branch_id=version.branch_id
        )

    @app.get("/api/repositories/summary")
    def repository_summary(runtime: RuntimeDep, root_path: str) -> AtlasQueryResult:
        return runtime.atlas_service.summary(Path(root_path))

    @app.get("/api/repositories/hotspots")
    def repository_hotspots(
        runtime: RuntimeDep,
        root_path: str,
        metric: str = "reverse_dependency_reach",
    ) -> AtlasQueryResult:
        return runtime.atlas_service.hotspots(Path(root_path), metric)

    @app.get("/api/repositories/inspect")
    def repository_inspect(runtime: RuntimeDep, root_path: str, node_id: str) -> AtlasQueryResult:
        return runtime.atlas_service.inspect(Path(root_path), node_id)

    @app.post("/api/repositories/review-context")
    def repository_review_context(
        runtime: RuntimeDep, request: ReviewContextRequest
    ) -> AtlasQueryResult:
        """The subgraph around a review's boundaries, for the map that opens beside it.

        Ids the atlas no longer holds are skipped rather than refused — the result names the
        ones it found, so a map drawn from a rebuilt atlas is short a node rather than absent.
        """

        return runtime.atlas_service.review_context(
            Path(request.root_path),
            request.node_ids,
            limit=request.limit,
        )

    @app.post("/api/repositories/explore")
    def repository_explore(runtime: RuntimeDep, request: AtlasExploreRequest) -> AtlasQueryResult:
        repository = Path(request.root_path)
        if request.operation == "search":
            return runtime.atlas_service.search(
                repository, request.terms, limit=request.limit
            )
        if request.operation == "cycles":
            return runtime.atlas_service.cycles(repository, limit=request.limit)
        if request.operation == "signals":
            return runtime.atlas_service.signals(
                repository,
                codes=request.signal_codes,
                limit=request.limit,
            )
        assert request.node_id is not None
        if request.operation == "children":
            return runtime.atlas_service.children(
                repository, request.node_id, limit=request.limit
            )
        if request.operation == "shortest_path":
            assert request.target_id is not None
            return runtime.atlas_service.shortest_path(
                repository, request.node_id, request.target_id
            )
        if request.operation in {"forward_neighbourhood", "reverse_neighbourhood"}:
            return runtime.atlas_service.neighbourhood(
                repository,
                request.node_id,
                direction=cast(
                    Literal["forward_neighbourhood", "reverse_neighbourhood"],
                    request.operation,
                ),
                depth=request.depth,
                limit=request.limit,
            )
        relation_kinds = {
            "dependencies": "direct_dependencies",
            "dependants": "direct_dependants",
            "callers": "known_callers",
            "implementations": "implementations",
            "tests": "related_tests",
        }
        return runtime.atlas_service.relationships(
            repository,
            request.node_id,
            kind=cast(
                Literal[
                    "direct_dependencies",
                    "direct_dependants",
                    "known_callers",
                    "implementations",
                    "related_tests",
                ],
                relation_kinds[request.operation],
            ),
            limit=request.limit,
        )

    @app.get("/api/filesystem/directories")
    def list_directories(
        hosted_mode: RestrictionsDep, path: str | None = None
    ) -> DirectoryListing:
        """Browse this machine's folders, so a repository root can be chosen rather than typed.

        With no `path`, the home directory. Read-only, one directory per request: only the
        names immediately inside it. Safe because the workspace binds 127.0.0.1 and serves the
        one person whose files these already are — which is exactly why the hosted demo, where
        neither half of that sentence holds, refuses it.
        """

        hosted_mode.browsing()
        return _directory_listing(Path(path) if path else Path.home())

    @app.get("/api/examples")
    def list_examples(runtime: RuntimeDep) -> list[BundledExample]:
        return [
            BundledExample(
                name=item.name,
                title=item.title,
                description=item.description,
                repository_root=item.repository_root,
            )
            for item in runtime.bundled_example_service.list()
        ]

    @app.post(
        "/api/examples/{name}/load",
        dependencies=[SerialisesIndexing],
        status_code=201,
        responses=_problem_responses(404, 422),
    )
    def load_example(runtime: RuntimeDep, name: str) -> AtlasVersion:
        """Index the example's repository so it can be started from like any other.

        No case comes back, because none is shipped. The caller continues through
        `/api/repositories/start` with the root this answers with, which is the same path a
        repository chosen in the folder picker takes.
        """

        return runtime.bundled_example_service.load(name)

    @app.post(
        "/api/reviews",
        status_code=201,
        dependencies=[SpendsModelBudget],
        responses=_problem_responses(404, 422, 503),
    )
    def create_review(runtime: RuntimeDep, request: ReviewRequest) -> BoundaryReview:
        return runtime.review_service.review(
            request.case_id,
            repository_root=Path(request.repository_root),
            elicited_from=request.elicited_from,
        )

    @app.post(
        "/api/reviews/stream",
        response_class=NDJSONStreamingResponse,
        dependencies=[SpendsModelBudget],
        responses={
            200: {
                "model": ReviewProgress,
                "description": (
                    "The same review as POST /api/reviews, as newline-delimited JSON: one "
                    "ReviewProgress object per line, ending in a completed or failed line."
                ),
            },
            **_problem_responses(422),
        },
    )
    def stream_review(runtime: RuntimeDep, request: ReviewRequest) -> NDJSONStreamingResponse:
        """The review a person watches: countable, because detection knows the length.

        Everything that can go wrong after the first line arrives as a `failed` line
        carrying the same `ProblemDetail` the non-streaming route would have returned. Once
        a response has started, its status code can no longer say anything, so the stream
        has to end in a verdict about itself.
        """

        return NDJSONStreamingResponse(
            _review_progress_lines(runtime, request),
            # Buffering would defeat the point: progress that arrives all at once at the
            # end is the unexplained wait this route exists to replace.
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/reviews")
    def list_reviews(
        runtime: RuntimeDep,
        case_id: str | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[BoundaryReviewSummary]:
        return runtime.review_repository.list(case_id=case_id, limit=limit)

    @app.get(
        "/api/reviews/{review_id}",
        responses=_problem_responses(404, 422),
    )
    def get_review(runtime: RuntimeDep, review_id: str) -> ReviewDetailResponse:
        """The stored review, plus what the team has since decided about its boundaries.

        One join, and no deeper: the standing decision on each boundary, read through the
        branch this run was on and the branch that branch came from. `ReviewService` never
        reads decisions — that is the one invariant of the triage design — so a decision can
        never reach the reasoning that produced a verdict.
        """

        return _with_standings(runtime, runtime.review_repository.get(review_id))

    @app.get(
        "/api/reviews/{review_id}/source",
        responses=_problem_responses(404, 422),
    )
    def review_source(
        runtime: RuntimeDep,
        review_id: str,
        reference: Annotated[str | None, Query(pattern=r"^BR-[0-9]{3}$")] = None,
        context_lines: Annotated[int, Query(ge=0, le=MAX_CONTEXT_LINES)] = 0,
    ) -> list[BoundaryExcerpt]:
        """The code this review's findings were measured from.

        Delivery, not retrieval: every participant already carries the span a deterministic
        detector chose when the verdict was reached, so there is nothing to search for and
        nothing for a caller to select. `reference` narrows to one boundary because a page
        asks for what it is about to draw; `context_lines` is how much surrounding code to
        unfold, bounded by the workspace rather than by the request.

        A boundary whose code cannot be shown answers with the reason instead of the text —
        the repository has changed since the review ran, is gone, or the boundary was never
        written. That is a 200 carrying a stated absence, not a 404: the finding exists and
        is worth reading either way.
        """

        review = runtime.review_repository.get(review_id)
        return runtime.review_source_service.for_review(
            review,
            reference=reference,
            context_lines=context_lines,
        )

    @app.get(
        "/api/reviews/{review_id}/report",
        response_class=Response,
        responses={
            200: {
                "content": {"text/markdown": {}},
                "description": "The stored report, as a file named after the review.",
            },
            **_problem_responses(404, 409, 422),
        },
    )
    def review_report(runtime: RuntimeDep, review_id: str) -> Response:
        """The review as the Markdown document it was already written as.

        The stored string, handed over unchanged. It was rendered once, at the moment the
        review concluded, from the report pinned to the case revision and the atlas that
        produced it — rendering it again here would let the exported file drift from the
        record it claims to be, on nothing more than a change to the renderer.

        A review with no report is a conflict rather than a 404: the review is there, and
        what is absent is a document that either has not been written yet or never will be.
        """

        review = runtime.review_repository.get(review_id)
        if review.markdown_report is None:
            if review.status is ReviewStatus.RUNNING:
                raise ReviewStillRunningError(
                    "That review is still running, so there is no report to export yet."
                )
            raise ReviewHasNoReportError(
                f"That review is {review.status.value} and reached no verdicts, so there "
                "is no report to export."
            )
        return Response(
            content=review.markdown_report,
            media_type="text/markdown",
            headers={
                "content-disposition": (
                    f'attachment; filename="{_report_filename(review_id)}"'
                )
            },
        )

    @app.post(
        "/api/reviews/{review_id}/answers",
        status_code=201,
        responses=_problem_responses(404, 409, 422),
    )
    def answer_review_questions(
        runtime: RuntimeDep,
        review_id: str,
        request: ReviewAnswersRequest,
    ) -> CaseRevision:
        """Record a round of answers as one case revision that says what it answered.

        Its own route rather than a `PATCH /api/cases/{id}` the browser composes, because
        provenance written that way is optional by construction: a client that forgot it
        produced a revision which had silently lost the link back to the question. Here the
        link cannot be omitted — it is the thing the route exists to write.

        The server resolves each `Q-n` against this review's own report and reads the
        destination field from the question. A client sends the reference and the line the
        reader saw, and nothing that decides where it goes (§12.0).
        """

        review = runtime.review_repository.get(review_id)
        return runtime.case_service.answer(
            review,
            [
                WrittenAnswer(
                    question_reference=item.question_reference,
                    recorded_text=item.recorded_text,
                )
                for item in request.answers
            ],
        )

    @app.post(
        "/api/reviews/{review_id}/cancel",
        responses=_problem_responses(404, 409, 422),
    )
    def cancel_review(runtime: RuntimeDep, review_id: str) -> BoundaryReview:
        """Ask a running review to stop, and answer with the record that says it will.

        The run reads that record between model calls, so this returns before the work has
        actually stopped: what is settled here is the outcome, not the timing. A review that
        finished a moment ago is a review that finished, and says so rather than pretending
        to have been cancelled.
        """

        if not runtime.review_repository.cancel(review_id):
            stored = runtime.review_repository.get(review_id)
            raise ReviewNotCancellableError(
                f"That review is {stored.status.value}, not running, so there is nothing "
                "to cancel."
            )
        return runtime.review_repository.get(review_id)

    @app.delete(
        "/api/reviews/{review_id}",
        status_code=204,
        responses=_problem_responses(404, 409, 422),
    )
    def delete_review(runtime: RuntimeDep, review_id: str) -> Response:
        """Remove a review and the question threads hung off it.

        Deleting is not editing: it removes the record rather than leaving one that says
        something else, which is what immutability is about. A running review is refused —
        cancel it first, so the work stops before its record goes.
        """

        runtime.review_repository.delete(review_id)
        return Response(status_code=204)

    @app.post(
        "/api/review-conversations",
        status_code=201,
        responses=_problem_responses(404, 422),
    )
    def create_review_conversation(
        runtime: RuntimeDep,
        request: ReviewConversationCreateRequest,
    ) -> ReviewConversation:
        return runtime.review_conversation_service.create(
            request.review_id,
            title=request.title,
            question_reference=request.question_reference,
        )

    @app.get(
        "/api/review-conversations",
        responses=_problem_responses(404, 422),
    )
    def list_review_conversations(runtime: RuntimeDep, review_id: str) -> list[ReviewConversation]:
        return runtime.review_conversation_service.list(review_id)

    @app.get(
        "/api/review-conversations/{conversation_id}",
        responses=_problem_responses(404, 422),
    )
    def get_review_conversation(runtime: RuntimeDep, conversation_id: str) -> ReviewConversation:
        return runtime.review_conversation_service.show(conversation_id)

    @app.post(
        "/api/review-conversations/{conversation_id}/messages",
        status_code=201,
        dependencies=[SpendsModelBudget],
        responses=_problem_responses(404, 409, 422, 503),
    )
    def ask_review_question(
        runtime: RuntimeDep,
        conversation_id: str,
        request: ReviewQuestionRequest,
    ) -> ReviewMessage:
        return runtime.review_conversation_service.ask(conversation_id, request.question)

    @app.post(
        "/api/review-conversations/{conversation_id}/messages/stream",
        response_class=NDJSONStreamingResponse,
        dependencies=[SpendsModelBudget],
        responses={
            200: {
                "model": AnswerProgress,
                "description": (
                    "The same turn as POST .../messages, as newline-delimited JSON: any "
                    "number of prose fragments, then one answered or failed line."
                ),
            },
            **_problem_responses(404, 409, 422, 503),
        },
    )
    def stream_review_question(
        runtime: RuntimeDep,
        conversation_id: str,
        request: ReviewQuestionRequest,
    ) -> NDJSONStreamingResponse:
        """The same turn, with the answer's prose arriving as it is written.

        A second transport for one flow, not a second flow: the same application call appends
        the same message, and this route adds only when its text reaches the reader. A
        provider that cannot stream sends no fragments and the answered line arrives on its
        own, which is why there is no capability to query first.
        """

        return NDJSONStreamingResponse(
            _answer_progress_lines(runtime, conversation_id, request.question),
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.get(
        "/api/branches/{branch_id}/decisions",
        responses=_problem_responses(404),
    )
    def branch_decisions(runtime: RuntimeDep, branch_id: str) -> BranchDecisionsResponse:
        """What this branch currently thinks, across every boundary anyone has triaged.

        One row per boundary with an opinion, not one per boundary that exists: the
        unreviewed state is absence, and a listing that invented rows for it would be
        asserting that somebody had looked.
        """

        return BranchDecisionsResponse(
            branch_id=branch_id,
            decisions=runtime.triage_service.decisions_for_branch(branch_id),
            comment_counts=runtime.triage_service.comment_counts(branch_id),
        )

    @app.post(
        "/api/decisions",
        status_code=201,
        responses=_problem_responses(404, 422),
    )
    def record_decision(runtime: RuntimeDep, request: DecisionRequest) -> StandingDecision:
        """Record a disposition toward one boundary, and return what now stands.

        Always an append, including when it contradicts what the same author said an hour
        ago. The previous decision stays readable through the history route, because "we
        accepted this in March and waived it in August" is the sentence a team most needs
        to be able to reconstruct.
        """

        return runtime.triage_service.decide(request.as_decision())

    @app.post(
        "/api/decisions/bulk",
        status_code=201,
        responses=_problem_responses(404, 422),
    )
    def record_decisions(
        runtime: RuntimeDep, request: BulkDecisionRequest
    ) -> BulkDecisionResponse:
        """Take one disposition over many boundaries, and record it as many decisions.

        How a team adopts a legacy repository now that the baseline is gone. The first run over
        a code base that has been alive for years lands dozens of boundaries, and asking for
        dozens of requests would end with the tool closed — but the answer is not a button that
        silences a list nobody read. It is this: select them, decide once, and every boundary
        gets a real decision with an author, a date and a reason where one is required, all
        written together so a half-adopted branch cannot exist.

        201 because this creates records, and it is not idempotent: pressing it twice appends a
        second decision per boundary, exactly as deciding twice by hand does. That is the
        append-only rule and not an oversight — what a team thought in March stays readable
        after they change their mind in August.
        """

        decisions = runtime.triage_service.decide_many(request.as_decisions())
        return BulkDecisionResponse(
            branch_id=request.branch_id,
            recorded=len(decisions),
            decisions=decisions,
        )

    @app.get(
        "/api/decisions/{branch_id}/{fingerprint}/history",
        responses=_problem_responses(404),
    )
    def decision_history(
        runtime: RuntimeDep, branch_id: str, fingerprint: str
    ) -> list[StandingDecision]:
        """Every disposition ever recorded for this boundary, oldest first."""

        return runtime.triage_service.history(branch_id, fingerprint)

    @app.get(
        "/api/decisions/{branch_id}/{fingerprint}/comments",
        responses=_problem_responses(404),
    )
    def decision_comments(
        runtime: RuntimeDep, branch_id: str, fingerprint: str
    ) -> list[DecisionComment]:
        """The thread on this boundary, in the order it was written."""

        return runtime.triage_service.comments(branch_id, fingerprint)

    @app.post(
        "/api/decisions/{branch_id}/{fingerprint}/comments",
        status_code=201,
        responses=_problem_responses(404, 422),
    )
    def add_decision_comment(
        runtime: RuntimeDep,
        branch_id: str,
        fingerprint: str,
        request: DecisionCommentRequest,
    ) -> DecisionComment:
        """Append one remark. No decision has to exist first, and none is implied by it."""

        return runtime.triage_service.comment(
            DecisionComment(
                branch_id=branch_id,
                boundary_fingerprint=fingerprint,
                author=request.author,
                body=request.body,
            )
        )

    @app.get("/api/policies")
    def list_policies(
        runtime: RuntimeDep, repository_root: str | None = None
    ) -> list[PolicyDocument]:
        return runtime.policy_service.catalog(
            repository_root=(
                Path(repository_root) if repository_root is not None else None
            )
        )

    @app.get("/api/policies/sources")
    def list_policy_sources(runtime: RuntimeDep) -> list[PolicySourceRegistration]:
        return runtime.policy_service.list_sources()

    @app.post("/api/policies/sources", status_code=201)
    def add_policy_source(
        runtime: RuntimeDep,
        hosted_mode: RestrictionsDep,
        request: PolicySourceRequest,
    ) -> PolicySourceRegistration:
        """Read a folder of Markdown policies from this machine into every review.

        Refused on the hosted demo: the folder named would be one of the server's. Writing
        policies here is not — those live in the session's own workspace, and `POST
        /api/policies` still answers.
        """

        hosted_mode.policy_source()
        return runtime.policy_service.add_source(Path(request.source))

    @app.delete("/api/policies/sources")
    def remove_policy_source(runtime: RuntimeDep, source: str) -> PolicySourceRemovalResponse:
        return PolicySourceRemovalResponse(
            removed=runtime.policy_service.remove_source(Path(source))
        )

    @app.post("/api/policies", status_code=201, responses=_problem_responses(409, 422))
    def create_policy(runtime: RuntimeDep, draft: PolicyDraft) -> PolicyDocument:
        """Write a policy of this workspace's own into `<workspace>/.archcompass/policies`.

        A real Markdown file in the format every other policy is in, so nothing about it is
        second-class: the next review reads it from disk with the rest of the corpus, and it
        remains editable in an editor after this page has forgotten about it.
        """

        return runtime.policy_service.create(draft)

    @app.put(
        "/api/policies/{policy_id}",
        responses=_problem_responses(404, 409, 422),
    )
    def update_policy(runtime: RuntimeDep, policy_id: str, draft: PolicyDraft) -> PolicyDocument:
        """Rewrite one of this workspace's policies. Anything read from elsewhere is a 409."""

        return runtime.policy_service.update(policy_id, draft)

    @app.delete(
        "/api/policies/{policy_id}",
        status_code=204,
        responses=_problem_responses(404, 409),
    )
    def delete_policy(runtime: RuntimeDep, policy_id: str) -> Response:
        runtime.policy_service.delete(policy_id)
        return Response(status_code=204)

    @app.get("/api/policies/{policy_id}", responses=_problem_responses(404))
    def get_policy(
        runtime: RuntimeDep,
        policy_id: str, repository_root: str | None = None
    ) -> PolicyDocument:
        return runtime.policy_service.get(
            policy_id,
            repository_root=(
                Path(repository_root) if repository_root is not None else None
            ),
        )

    @app.api_route(
        "/api/{api_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        include_in_schema=False,
    )
    def unknown_api_route(api_path: str) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=ProblemDetail(
                code="not_found",
                message=f"API route /api/{api_path} was not found",
            ).model_dump(mode="json"),
        )

    @app.get("/{path:path}", include_in_schema=False, response_model=None)
    def spa(path: str) -> FileResponse | JSONResponse:
        candidate = (STATIC_DIR / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(STATIC_DIR.resolve()):
            return FileResponse(candidate, headers=_static_cache_headers(candidate))
        index = STATIC_DIR / "index.html"
        if index.is_file():
            return FileResponse(index, headers=_static_cache_headers(index))
        return JSONResponse(
            status_code=503,
            content=ProblemDetail(
                code="frontend_not_built",
                message="The Arch Compass frontend assets have not been built.",
            ).model_dump(mode="json"),
        )

    return app


def _summary(
    runtime: Runtime, restrictions: HostedRestrictions
) -> WorkspaceSummaryResponse:
    """What this workspace is pointed at, without asking any provider anything.

    Read on every page load, which is why it costs one row and no network. Whether a
    model is reachable is a different question with a different price, and it is asked
    by the chooser at the moment someone is waiting to choose.
    """

    status = runtime.model_catalog_service.status()
    selection = status.selection
    return WorkspaceSummaryResponse(
        # The path is withheld on the hosted demo rather than shortened: it ends in the
        # session token, and a page that could read it could hand another visitor's
        # workspace to anyone.
        workspace="Hosted demo workspace" if restrictions.hosted else str(runtime.workspace),
        models=WorkspaceModels(
            reasoning=(
                ModelIdentity(
                    provider=status.provider,
                    model=status.model,
                    thinking=status.thinking,
                )
                if status.provider and status.model
                else None
            ),
            failure=selection.failure_detail if selection else "",
            pinned=status.pinned,
        ),
        hosted=restrictions.hosted,
        source_hosts=sorted(runtime.source_service.hosts) if runtime.source_service else [],
    )


def _static_cache_headers(served: Path) -> dict[str, str]:
    """
    How long a browser may keep a built file.

    The build gives every asset a content hash and empties the output directory, so an
    asset's name changes the moment its bytes do and the old name stops existing. That
    makes the assets safe to keep forever — and makes `index.html`, which is the only
    file that knows the current names, the one file that must never be kept: a stale copy
    asks for hashed names that were deleted by the build, so the app half-loads from a
    cache the user cannot see and a plain reload does not clear.
    """

    if served.parent.name == "assets":
        return {"cache-control": "public, max-age=31536000, immutable"}
    return {"cache-control": "no-cache"}


#: Everything a downloaded filename is allowed to keep. Review identifiers are generated
#: and already safe, but this name leaves in a header a browser writes straight to disk, so
#: it is built from what survives the filter rather than from what arrived in the path.
_UNSAFE_IN_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def _report_filename(review_id: str) -> str:
    """Named after the review, because a folder of these has to stay tellable apart."""

    return f"archcompass-review-{_UNSAFE_IN_FILENAME.sub('-', review_id)}.md"


def _directory_listing(requested: Path) -> DirectoryListing:
    """One directory read for the picker, or a `PathValidationError` naming what went wrong.

    Read here rather than behind an application service: a listing holds no workspace state
    and is asked for by exactly one screen.

    Dot-directories are left out — `.git`, `.venv` and `.mypy_cache` are most of what sits in
    a project root and none is a repository anyone means to index. The picker keeps a path
    field for the reader who does.
    """

    try:
        directory = requested.expanduser().resolve(strict=True)
    except OSError as error:
        raise PathValidationError(f"There is nothing at {requested}.") from error
    if not directory.is_dir():
        raise PathValidationError(f"{directory} is a file, not a folder.")
    try:
        children = sorted(
            (child for child in directory.iterdir() if not child.name.startswith(".")),
            key=lambda child: child.name.casefold(),
        )
    except OSError as error:
        raise PathValidationError(f"{directory} cannot be read.") from error
    return DirectoryListing(
        path=str(directory),
        # A root is its own parent, which is how the filesystem says there is nowhere above it.
        parent=None if directory.parent == directory else str(directory.parent),
        directories=[
            DirectoryEntry(name=child.name, path=str(child))
            for child in children
            if child.is_dir()
        ],
    )


def _abstraction_name(candidate: FindingCandidate) -> str:
    """The boundary a person recognises: the abstraction, not the candidate's identity."""

    first = candidate.participants[0] if candidate.participants else None
    return first.qualified_name if first is not None else "unnamed boundary"


def _review_progress_lines(runtime: Runtime, request: ReviewRequest) -> Iterator[str]:
    """Run one review in a worker thread and yield each line as the run produces it.

    A thread, not a job queue (master plan §18). The work is still exactly this request's
    work: a client that navigates away leaves the run to finish or fail on its own, and the
    review it produces is the same either way. What streaming buys is that the caller learns
    the review's identity before the first model call and the length of the sequence after
    detection, instead of learning both after the last one.

    The queue is the only shared state, it lives as long as the request, and the application
    service still owns detection, judgement order and composition: this function chooses
    nothing about the review, it only reports it.
    """

    lines: Queue[str | None] = Queue()

    def emit(
        event: ReviewStarted
        | ReviewDetected
        | ReviewJudged
        | ReviewEliciting
        | ReviewSummarising
        | ReviewCompleted
        | ReviewUnchanged
        | ReviewFailed,
    ) -> None:
        lines.put(event.model_dump_json())

    def report_start(review: BoundaryReview) -> None:
        emit(
            ReviewStarted(
                review_id=review.review_id,
                case_id=review.case_id,
                case_revision=review.case_revision,
                elicited_from=review.elicited_from,
            )
        )

    detected = 0

    def report_detection(candidates: Sequence[FindingCandidate]) -> None:
        nonlocal detected
        detected = len(candidates)
        emit(
            ReviewDetected(
                total=detected,
                boundaries=[_abstraction_name(item) for item in candidates],
            )
        )

    carried = 0

    def report_verdict(judged: JudgedCandidate, position: int, total: int) -> None:
        nonlocal carried
        if judged.reused_from is not None:
            carried += 1
        emit(
            ReviewJudged(
                position=position,
                total=total,
                abstraction=_abstraction_name(judged.candidate),
                material=judged.verdict.material,
                verdict_reused_from=judged.reused_from,
                carried=carried,
            )
        )

    def run() -> None:
        try:
            review = runtime.review_service.review(
                request.case_id,
                repository_root=Path(request.repository_root),
                elicited_from=request.elicited_from,
                on_started=report_start,
                on_detected=report_detection,
                on_verdict=report_verdict,
                on_eliciting=lambda: emit(ReviewEliciting(total=detected)),
                on_summarising=lambda: emit(ReviewSummarising(total=detected)),
            )
        except NothingToReviewError as unchanged:
            # Its own line, not a `failed` one: the run did exactly what it promised, and a
            # client that showed this as an error would be scolding the reader for having
            # an up-to-date repository. Every caller of this stream gets the same answer,
            # whichever page or client started it — that is the point of refusing in the
            # service rather than in a button.
            emit(
                ReviewUnchanged(
                    current_against=unchanged.current_against,
                    message=str(unchanged),
                )
            )
        except ArchCompassError as error:
            # The status is deliberately dropped: the response is already a 200 by the time
            # the run fails, and a code in the body that disagreed with it would be worse
            # than one that says nothing.
            _status, code, retryable = _classify_error(error)
            emit(
                ReviewFailed(
                    problem=ProblemDetail(
                        code=code,
                        message=str(error),
                        retryable=retryable,
                    )
                )
            )
        except Exception:
            # Broad on purpose: a stream that simply closes tells the reader nothing, and
            # this is the last place that can still say the run failed. Only ArchCompass's
            # own errors are written out for a person to read, so an unexpected one is
            # reported without forwarding its text.
            emit(
                ReviewFailed(
                    problem=ProblemDetail(
                        code="archcompass_error",
                        message="The review failed unexpectedly, and nothing was saved.",
                    )
                )
            )
        else:
            emit(ReviewCompleted(review=review))
        finally:
            lines.put(None)

    worker = Thread(target=run, daemon=True, name="archcompass-review")
    worker.start()
    while (line := lines.get()) is not None:
        yield f"{line}\n"


def _answer_progress_lines(
    runtime: Runtime,
    conversation_id: str,
    question: str,
) -> Iterator[str]:
    """Ask one question in a worker thread and yield each line as the answer is written.

    The same shape as `_review_progress_lines`, for the same reason: a thread and a queue that
    live exactly as long as this request, no job queue, and an application service that still
    owns the turn. This function chooses nothing — not whether the reply streams, not what the
    message contains, not whether the turn succeeded — it only reports.

    A refusal reaching here as `failed` rather than as a status code is not a downgrade: the
    response is already a 200 by the time the reasoner is called, and the alternative is a
    stream that closes without saying anything. A question rejected before the response starts
    still gets its status, because validation of the body happens before this runs.
    """

    lines: Queue[str | None] = Queue()

    def emit(event: AnswerProse | QuestionAnswered | QuestionFailed) -> None:
        lines.put(event.model_dump_json())

    def run() -> None:
        try:
            message = runtime.review_conversation_service.ask(
                conversation_id,
                question,
                on_prose=lambda text: emit(AnswerProse(text=text)),
            )
        except ArchCompassError as error:
            # The status is deliberately dropped: it can no longer be said, and a code in the
            # body disagreeing with the 200 already sent would be worse than one that is
            # silent about it.
            _status, code, retryable = _classify_error(error)
            emit(
                QuestionFailed(
                    problem=ProblemDetail(code=code, message=str(error), retryable=retryable)
                )
            )
        except Exception:
            # Broad on purpose, and the text is not forwarded: this is the last place that can
            # still say the turn failed, and only ArchCompass's own errors are written for a
            # person to read.
            emit(
                QuestionFailed(
                    problem=ProblemDetail(
                        code="archcompass_error",
                        message="That question failed unexpectedly, and nothing was saved.",
                    )
                )
            )
        else:
            emit(QuestionAnswered(message=message))
        finally:
            lines.put(None)

    worker = Thread(target=run, daemon=True, name="archcompass-review-question")
    worker.start()
    while (line := lines.get()) is not None:
        yield f"{line}\n"


def _with_standings(runtime: Runtime, review: BoundaryReview) -> ReviewDetailResponse:
    """Attach what *now* knows about a review's boundaries: the standing decisions.

    The join happens here, at read time, and never at write time. A review is an immutable
    record of one run; what the team has decided about its boundaries is a fact about the
    present, and a stored copy of it would go stale the first time somebody used the feature.

    Read through the base branch, so a review on a feature branch shows what `main` already
    settled rather than presenting every boundary as undecided. An inherited decision names the
    branch it was actually taken on, which is what lets a page distinguish "we decided this"
    from "we have not disagreed with `main`".

    Entries exist for every reviewed boundary, decided or not: the fingerprint alone is what a
    client needs to post a decision, and a boundary is not going to be triaged by a page that
    cannot name it. A review from before branch lineages carries no decisions — stated by
    leaving them absent rather than by guessing a branch, because a decision filed under a
    guess would be attributed to a team that never took it.
    """

    payload = review.model_dump()
    report = review.report
    if report is None:
        return ReviewDetailResponse.model_validate(payload)

    standings = runtime.triage_service.standings_for_branch(review.branch_id)
    comment_counts = (
        {}
        if review.branch_id is None
        else runtime.triage_service.comment_counts(review.branch_id)
    )
    triage = [
        BoundaryTriage(
            reference=boundary.reference,
            fingerprint=fingerprint,
            decision=_joined(standing_for(boundary, standings), boundary),
            comment_count=comment_counts.get(fingerprint, 0),
        )
        for boundary in report.reviewed
        for fingerprint in (boundary.fingerprint or boundary_fingerprint(boundary.candidate),)
    ]
    payload["boundary_triage"] = [item.model_dump() for item in triage]
    return ReviewDetailResponse.model_validate(payload)


def _joined(
    decision: StandingDecision | None, boundary: ReviewedBoundary
) -> JoinedDecision | None:
    if decision is None:
        return None
    return JoinedDecision(
        decision_id=decision.decision_id,
        state=decision.state,
        author=decision.author,
        reason=decision.reason,
        decided_at=decision.decided_at,
        taken_on_current_verdict=decision.taken_on(
            material=boundary.material,
            verdict_label=boundary.verdict_label,
        ),
    )


def _classify_error(error: ArchCompassError) -> tuple[int, str, bool]:
    if isinstance(error, NothingToReviewError):
        # Its own code, because it is not a fault to fix: the request was understood and
        # the answer is that there is nothing to do. A client can tell it apart from every
        # conflict that asks the caller to change something.
        return 409, "nothing_changed", False
    if isinstance(
        error,
        (
            CaseNotFoundError,
            ExampleNotFoundError,
            AtlasNotFoundError,
            ReviewNotFoundError,
            PolicyNotFoundError,
            ConversationNotFoundError,
            BranchNotFoundError,
        ),
    ):
        return 404, "not_found", False
    if isinstance(
        error,
        (
            CaseRevisionConflictError,
            ConversationRevisionConflictError,
            PolicyConflictError,
            ReviewHasNoReportError,
            ReviewNotCancellableError,
            ReviewStillRunningError,
            StaleAtlasError,
        ),
    ):
        # Retryable only where repeating the request could succeed. A review that has
        # already finished will not start running again, so cancelling it never will.
        return 409, "state_conflict", isinstance(
            error,
            (ConversationRevisionConflictError, ReviewStillRunningError, StaleAtlasError),
        )
    if isinstance(
        error,
        (
            CaseValidationError,
            PathValidationError,
            PolicyFormatError,
            ModelOutputValidationError,
            ConversationValidationError,
            ConversationRetrievalError,
        ),
    ):
        return 422, "validation_error", False
    if isinstance(error, RepositoryCheckoutError):
        # Not 422: the request is well formed and this is a true statement about the
        # repository. Retryable, because most of what reaches here is a remote that was
        # unreachable at the moment it was asked.
        return 409, "checkout_failed", True
    if isinstance(error, NoReasoningModelSelectedError):
        # 409 rather than 503: nothing is unavailable, and nothing about the request is
        # malformed — the workspace simply has not chosen yet.
        return 409, "no_model_selected", False
    if isinstance(error, ProviderError):
        return 503, "provider_unavailable", True
    if isinstance(error, PersistenceError):
        return 500, "persistence_error", False
    return 400, "archcompass_error", False
