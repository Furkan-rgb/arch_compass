"""One whole review, driven over the HTTP API, kept so many tests can read one run.

Provider-independent on purpose. What a review costs differs enormously between a metered
hosted key and a model on the machine under the desk, but what a review *is* does not: the
same repository is indexed, the same candidates are judged, the same questions are answered
on the same execution thread, and the same decision and follow-up are recorded afterwards.
So the driver lives here and each provider's conftest supplies only the runtime.

Nothing here asserts on what a model said. That belongs to the test modules, and the whole
point of running this against more than one provider is that the assertions are the same
sentences about shape either way.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from archcompass.bootstrap import Runtime
from archcompass.presentation.web.app import create_app

#: The node that investigates hinges, and the message it logs when one is lost.
#:
#: Named here because the graph is deliberately built to survive this: an investigation is an
#: improvement to a question, so `investigate_hinges` catches everything, logs, and lets the
#: unimproved hinge go on to the person it was always going to reach. That is right for a
#: running review and blinding for a test — a run where every investigation failed produces
#: the same empty manifest as a run where the model was confident throughout, and the
#: assertions on that manifest skip themselves in both.
INVESTIGATION_LOGGER = "archcompass.workflow.nodes"
INVESTIGATION_LOST = "was not investigated"

#: The answer typed when a question arrived with a blank box rather than options.
FALLBACK_ANSWER = (
    "One team owns this service end to end, and we expect a second provider behind "
    "these boundaries within two quarters."
)


@dataclass(frozen=True)
class Lifecycle:
    """Every response one review produced, captured once and asserted on many times.

    `resumed` is `None` when the first pass completed outright. That is a legitimate outcome
    and not a flaky one: a review waits for answers only when the model states a hinge on at
    least one finding, and whether it needs human context to judge this repository is its
    call, not the test's. The clarification assertions skip themselves in that case and say
    why, rather than being written to always pass.
    """

    started: dict[str, Any]
    first: dict[str, Any]
    resumed: dict[str, Any] | None
    final: dict[str, Any]
    decision: dict[str, Any]
    conversation: dict[str, Any]
    #: A thread held about one clarification question, while the review was still waiting on
    #: it — every turn of it, in order. `()` where the first pass asked nothing, which is the
    #: same legitimate outcome `resumed` documents.
    clarification: tuple[dict[str, Any], ...]
    corpus_policy_ids: frozenset[str]
    repository_root: str
    #: The Markdown a reader downloads, the rail they scroll, and the case they can open —
    #: read back after the review ended rather than taken from the response that ended it.
    #: A review is not finished when the graph returns; it is finished when the surfaces
    #: that outlive it can answer for it.
    report: str
    listing: tuple[dict[str, Any], ...]
    case_history: tuple[dict[str, Any], ...]
    #: What asking for a second review of the *unchanged* repository answered, and what the
    #: review listing held immediately afterwards. `None` where the caller did not ask.
    unchanged_refusal: dict[str, Any] | None
    listing_after_refusal: tuple[dict[str, Any], ...]
    #: A second review, run after the repository was changed under it. `None` where the
    #: caller supplied no change — see `run_lifecycle`.
    subsequent: dict[str, Any] | None
    #: Why each hinge that was investigated and lost was lost, in the order they were lost.
    #: Empty is the passing shape. See `dropped_investigations` for why the responses above
    #: cannot answer this on their own.
    dropped_investigations: tuple[BaseException | None, ...]


@contextmanager
def dropped_investigations(losses: list[BaseException | None]) -> Iterator[None]:
    """Collect the exceptions `investigate_hinges` swallows, without changing what it does.

    A handler rather than `caplog`, because the review runs once in a module-scoped fixture
    and `caplog` is per test. The exception is kept rather than the message: an exhausted
    quota and a model that cannot honour its output schema are both a lost investigation
    here, and only one of them is a defect the suite should fail on.
    """

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if INVESTIGATION_LOST not in record.getMessage():
                return
            losses.append(record.exc_info[1] if record.exc_info else None)

    logger = logging.getLogger(INVESTIGATION_LOGGER)
    handler = _Collector(level=logging.WARNING)
    logger.addHandler(handler)
    try:
        yield
    finally:
        logger.removeHandler(handler)


def run_lifecycle(
    runtime: Runtime,
    repository: str,
    *,
    change: Callable[[], None] | None = None,
) -> Lifecycle:
    """Index, review, answer until it stops asking, then everything that comes after.

    "After" is the half a lifecycle test usually stops short of, and it is where a
    demonstration actually lives: the answered review has to be readable as a document, it
    has to appear once rather than twice in the list somebody scrolls, the case has to hold
    the answers a person typed, a decision has to attach to it, a follow-up question has to
    be answerable from it — and the next review has to be judged against what was learned
    rather than starting from an empty case again.

    `change` buys that last one, for the price of a second full judging pass and a
    repository the caller owns and can edit. It is called between the two reviews, and what
    happens on either side of it is the point: asking for a review of code that has not
    moved is refused rather than charged for, and asking after it has moved produces the
    next review in the lineage, judged against the case the answers are now on. The local
    suite pays for this because a GPU already committed for three minutes can spend two
    more; the hosted suite does not, because there the same coverage is a second helping of
    a metered daily quota.
    """

    corpus = frozenset(
        policy.id
        for policy in runtime.policy_service.catalog(repository_root=Path(repository))
    )
    assert corpus, "the corpus is empty; the retrieval assertions would prove nothing"

    losses: list[BaseException | None] = []
    with dropped_investigations(losses), TestClient(create_app(runtime)) as client:
        started = client.post("/api/repositories/start", json={"root_path": repository})
        assert started.status_code == 200, started.text
        case_id = started.json()["case_id"]

        # The case is left as `start` opened it: empty.
        #
        # This used to state a goal and a constraint whose decisive fact was deliberately
        # missing, so that the model had something to be uncertain about and the
        # clarification round would run. That was the test arranging the conditions the
        # product is supposed to create on its own, and it hid the real behaviour: on an
        # empty case the model judged everything on the policy corpus and never asked.
        #
        # Nothing can state a constraint any more, and the judgement contract now says an
        # empty case out loud and gives asking first-class standing. So an empty case is the
        # honest input, and whether a round happens is the model's call — which is what
        # `Lifecycle.resumed` being optional has always documented.

        first = client.post(
            "/api/reviews",
            json={"case_id": case_id, "repository_root": repository},
        )
        assert first.status_code == 201, first.text
        opened = first.json()

        # Before a single question is answered, because that is the only time this surface
        # exists: a reader stuck on a question the review is still waiting on. Three turns,
        # not one — a thread is where this conversation goes wrong, and one message cannot
        # show it. See `test_a_thread_about_a_question_moves`.
        clarification: list[dict[str, Any]] = []
        if opened["questions"]:
            thread = client.post(
                "/api/review-conversations",
                json={
                    "review_id": opened["id"],
                    "question_id": opened["questions"][0]["id"],
                },
            )
            assert thread.status_code == 201, thread.text
            thread_id = thread.json()["id"]
            for asked in (
                "What is this question actually asking?",
                "What does it do? In simple terms",
                "Is it really needed? Or are you saying it isn't?",
            ):
                turn = client.post(
                    f"/api/review-conversations/{thread_id}/messages",
                    json={"question": asked},
                )
                assert turn.status_code == 200, turn.text
                clarification.append(turn.json()["messages"][-1])

        resumed: dict[str, Any] | None = None
        rounds: list[dict[str, Any]] = []
        waiting = opened
        while waiting["status"] == "awaiting_answers":
            # Answered, not skipped, and resumed without `stop`. Both halves matter and only
            # one of them used to be here: skipping resumes the graph without revising the
            # case, and `stop` routes the revised case straight to the composer, so either
            # one on its own leaves the rejudgement this file exists to exercise unrun. It
            # did, silently, for as long as the flag was set — the second review came back
            # with round one's findings copied verbatim and every assertion below still
            # passed, because none of them compared the two rounds.
            #
            # A loop rather than one resume, because answering is not guaranteed to end the
            # review: a model that still cannot judge on what it now knows may ask again,
            # and the graph allows it up to three rounds. Two of those are a real shape this
            # has to survive, so the driver answers until the review stops asking rather
            # than asserting that one answer was enough.
            answered_questions = [
                {
                    "question_id": question["id"],
                    "status": "answered",
                    # Chosen from what the model offered wherever it offered anything, which
                    # is the path a person takes: the options are the product's answer to
                    # "never make someone type what they could pick". Typed prose is the
                    # fallback for a question asked with a blank box.
                    "value": (
                        question["options"][0]
                        if question["options"]
                        else FALLBACK_ANSWER
                    ),
                    "actor": "architect",
                }
                for question in waiting["questions"]
            ]
            response = client.post(
                f"/api/reviews/{waiting['id']}/answers",
                json={"answers": answered_questions, "stop": False},
            )
            assert response.status_code == 200, response.text
            waiting = response.json()
            rounds.append(waiting)
            if resumed is None:
                resumed = waiting

        final = rounds[-1] if rounds else opened

        decision = client.post(
            "/api/decisions",
            json={
                "review_id": final["id"],
                "candidate_id": final["findings"][0]["candidate"]["id"],
                "disposition": "accept",
                "author": "architect",
                "reasoning": "This boundary is intentional.",
            },
        )
        assert decision.status_code == 201, decision.text

        conversation = client.post(
            "/api/review-conversations", json={"review_id": final["id"]}
        )
        assert conversation.status_code == 201, conversation.text
        message = client.post(
            f"/api/review-conversations/{conversation.json()['id']}/messages",
            json={"question": "Which finding is the most expensive to leave alone?"},
        )
        assert message.status_code == 200, message.text

        # Read back through the surfaces that outlive the run, rather than from the response
        # that ended it. A review the graph composed and the workbench cannot open is a
        # review that did not happen as far as anybody using this is concerned.
        report = client.get(f"/api/reviews/{final['id']}/report")
        assert report.status_code == 200, report.text

        history = client.get(f"/api/cases/{case_id}/history")
        assert history.status_code == 200, history.text

        unchanged_refusal: dict[str, Any] | None = None
        listing_after_refusal: tuple[dict[str, Any], ...] = ()
        subsequent: dict[str, Any] | None = None
        if change is not None:
            # First, unchanged. The answers moved the case, but the last round was already
            # judged against them, so there is genuinely nothing left to do and the product
            # says so instead of spending a judging pass to reach the same verdicts.
            unchanged = client.post(
                "/api/reviews",
                json={"case_id": case_id, "repository_root": repository},
            )
            problem = (
                unchanged.json()
                if unchanged.headers.get("content-type", "").startswith("application/json")
                else {}
            )
            unchanged_refusal = {"status_code": unchanged.status_code, **problem}
            # Immediately, and before anything else is asked for. What is being checked is
            # that the refusal left nothing behind, and a listing read later would have the
            # legitimate second review in it and no way to tell the two apart.
            refused_listing = client.get("/api/reviews", params={"view": "summary"})
            assert refused_listing.status_code == 200, refused_listing.text
            listing_after_refusal = tuple(refused_listing.json())

            # Then changed, which is the shape a second demonstration actually has.
            change()
            reindexed = client.post(
                "/api/repositories/start",
                json={"root_path": repository},
            )
            assert reindexed.status_code == 200, reindexed.text
            assert reindexed.json()["case_id"] == case_id, (
                "re-indexing a changed repository started a different case"
            )

            again = client.post(
                "/api/reviews",
                json={"case_id": case_id, "repository_root": repository},
            )
            assert again.status_code == 201, again.text
            subsequent = again.json()
            while subsequent["status"] == "awaiting_answers":
                # Stopped rather than answered: what this second review is here to show is
                # the delta and the lineage, and whether it also wants to ask is its own
                # business. Stopping still records the round, as explicit skips.
                stopped = client.post(
                    f"/api/reviews/{subsequent['id']}/answers",
                    json={"answers": [], "stop": True},
                )
                assert stopped.status_code == 200, stopped.text
                subsequent = stopped.json()

        # Read last, and that ordering is the whole of it. This used to be fetched before
        # the refused review was ever asked for, so the assertion that a refusal leaves no
        # snapshot behind was reading a listing taken before there was anything to leave —
        # it could not have failed, which is the one thing a regression test may not be.
        listing = client.get("/api/reviews", params={"view": "summary"})
        assert listing.status_code == 200, listing.text

        return Lifecycle(
            started=started.json(),
            first=opened,
            resumed=resumed,
            final=final,
            decision=decision.json(),
            conversation=message.json(),
            clarification=tuple(clarification),
            corpus_policy_ids=corpus,
            repository_root=repository,
            report=report.text,
            listing=tuple(listing.json()),
            case_history=tuple(history.json()),
            unchanged_refusal=unchanged_refusal,
            listing_after_refusal=listing_after_refusal,
            subsequent=subsequent,
            dropped_investigations=tuple(losses),
        )
