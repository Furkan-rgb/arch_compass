"""The local HTTP surface: the whole review loop, and the contracts a client relies on."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from archcompass.bootstrap import Runtime
from archcompass.presentation.web import create_app

FIXTURE = "boundary-review"


def test_the_api_covers_the_whole_review_loop(runtime: Runtime) -> None:
    """Pick an example, review it, read it back, ask about it — in one client session."""

    with TestClient(create_app(runtime)) as client:
        workspace = client.get("/api/workspace")
        assert workspace.status_code == 200
        assert workspace.json()["models"]["reasoning"]["provider"] == "fake"

        examples = client.get("/api/bundled-cases")
        assert examples.status_code == 200
        listed = {item["name"]: item for item in examples.json()}
        assert FIXTURE in listed
        # Only an example that ships answers can be scored; the flag is what the workspace
        # uses to say so, and a client that trusted it wrongly would grade against nothing.
        assert listed[FIXTURE]["has_expected_answers"] is True

        loaded = client.post(f"/api/bundled-cases/{FIXTURE}/load")
        assert loaded.status_code == 201, loaded.text
        case_id = loaded.json()["case_id"]

        created = client.post(
            "/api/reviews",
            json={"case_id": case_id, "repository_root": listed[FIXTURE]["repository_root"]},
        )
        assert created.status_code == 201, created.text
        review = created.json()
        review_id = review["review_id"]
        assert review["status"] == "succeeded"
        assert review["report"]["reviewed"]
        assert review["markdown_report"]

        fetched = client.get(f"/api/reviews/{review_id}")
        assert fetched.status_code == 200
        assert fetched.json()["review_id"] == review_id

        summaries = client.get("/api/reviews")
        assert summaries.status_code == 200
        assert [item["review_id"] for item in summaries.json()] == [review_id]

        conversation = client.post(
            "/api/review-conversations", json={"review_id": review_id}
        )
        assert conversation.status_code == 201, conversation.text
        conversation_id = conversation.json()["conversation_id"]

        answered = client.post(
            f"/api/review-conversations/{conversation_id}/messages",
            json={"question": "What did you make of the TaskFormatter boundary?"},
        )
        assert answered.status_code == 201, answered.text
        message = answered.json()
        assert message["answer"]["answer"]
        known = {item["reference"] for item in review["report"]["reviewed"]}
        # Every citation resolves; references are assigned by the application from
        # position, so an unknown one could only mean the application invented it.
        assert set(message["answer"]["supporting_references"]) <= known

        history = client.get(f"/api/review-conversations/{conversation_id}")
        assert history.status_code == 200
        assert len(history.json()["messages"]) == 1

        scored = client.get(f"/api/reviews/{review_id}/score")
        assert scored.status_code == 200, scored.text
        result = scored.json()
        assert result is not None, "a bundled example that ships answers must be gradable"
        assert result["example"] == FIXTURE
        assert result["total"] == len(review["report"]["reviewed"])
        # Nothing may be silently excluded: an uncovered boundary means the example drifted
        # from its own key, and a score over the remainder would look complete.
        assert result["unscored"] == []
        assert {item["reference"] for item in result["boundaries"]} == known


def test_a_streamed_review_counts_its_boundaries_before_judging_them(
    runtime: Runtime,
) -> None:
    """The run has to be countable, which means detection must be reported on its own.

    A stream that only spoke after the first verdict would leave the longest wait in the
    review — the first model call — with nothing to show, which is the wait the streaming
    route exists to replace.
    """

    with TestClient(create_app(runtime)) as client:
        loaded = client.post(f"/api/bundled-cases/{FIXTURE}/load")
        case_id = loaded.json()["case_id"]
        repository_root = {
            item["name"]: item for item in client.get("/api/bundled-cases").json()
        }[FIXTURE]["repository_root"]

        with client.stream(
            "POST",
            "/api/reviews/stream",
            json={"case_id": case_id, "repository_root": repository_root},
        ) as response:
            assert response.status_code == 200, response.read()
            assert response.headers["content-type"].startswith("application/x-ndjson")
            events = [json.loads(line) for line in response.iter_lines() if line.strip()]

    # The identity comes first, before any model call. It is what lets a client stop
    # watching from the page it started on and go to the review itself, which by then
    # exists and can be opened, reloaded or cancelled from anywhere. That the row is
    # readable and running at that point is settled in `test_running_reviews.py`, where the
    # assertion can be made from inside the run.
    assert events[0]["event"] == "started"
    review_id = events[0]["review_id"]
    assert events[0]["case_id"] == case_id

    assert events[1]["event"] == "detected"
    total = events[1]["total"]
    assert total > 0
    assert len(events[1]["boundaries"]) == total

    judged = [event for event in events if event["event"] == "judged"]
    # One line per boundary, in order, each naming the boundary it settled.
    assert [event["position"] for event in judged] == list(range(1, total + 1))
    assert [event["abstraction"] for event in judged] == events[1]["boundaries"]

    assert events[-1]["event"] == "completed"
    review = events[-1]["review"]
    assert review["status"] == "succeeded"
    assert len(review["report"]["reviewed"]) == total
    # The same review throughout: the one announced at the start is the one composed at
    # the end, so a page opened on that identifier mid-run becomes the page holding it.
    assert review["review_id"] == review_id
    assert client.get(f"/api/reviews/{review_id}").status_code == 200


def test_the_api_walks_both_passes_of_an_elicitation(runtime: Runtime) -> None:
    """The whole flow over HTTP, exactly as the browser walks it.

    Point at a repository with no case written, get every boundary judged, get back the
    questions, answer them into the case, and carry on. What is defended is that the halt is
    real at the transport level — the first pass reports `awaiting_answers` and the client
    cannot mistake it for a result — and that naming it on the second request is what turns
    the second run into one that concludes instead of asking again.
    """

    repository = str(Path("eval/cases/warehouse-sync/repository").resolve())

    with TestClient(create_app(runtime)) as client:
        started = client.post("/api/repositories/start", json={"root_path": repository})
        assert started.status_code == 201, started.text
        case_id = started.json()["case_id"]
        # Nothing written: the entry for someone who has a repository and no case.
        assert started.json()["snapshot"]["problem_statement"] == ""

        first = client.post(
            "/api/reviews",
            json={"case_id": case_id, "repository_root": repository},
        )
        assert first.status_code == 201, first.text
        first_review = first.json()

        assert first_review["status"] == "awaiting_answers"
        assert first_review["elicited_from"] is None
        questions = first_review["report"]["overview"]["open_questions"]
        assert questions, "a repository with no case must come back asking"
        # Judged in full, and the verdicts are kept — they are what the questions were built
        # from, and the citations below would point at nothing otherwise.
        reviewed = first_review["report"]["reviewed"]
        assert len(reviewed) == 5
        known = {item["reference"] for item in reviewed}
        for question in questions:
            assert set(question["supporting_references"]) <= known

        # The listing says the same thing, which is the point of the status: a run holding
        # for answers must not sit among the finished ones reporting a verdict split.
        listed = {item["review_id"]: item for item in client.get("/api/reviews").json()}
        assert listed[first_review["review_id"]]["status"] == "awaiting_answers"

        # It is refused as a subject for questions, too. Its verdicts are exactly the ones
        # the run said it could not settle, so discussing them would hand back through a
        # side door the set the page deliberately withholds.
        conversation = client.post(
            "/api/review-conversations",
            json={"review_id": first_review["review_id"]},
        )
        assert conversation.status_code == 404
        assert "waiting on answers" in conversation.json()["message"]

        # The answer, through the route that cannot lose what it answered. The client sends
        # the reference and the answer the reader typed, and nothing else: the workspace pairs
        # it with the question from its own report and reads the force from there.
        assert questions[0]["answer_belongs_in"] == "expected_future_changes"
        answered = client.post(
            f"/api/reviews/{first_review['review_id']}/answers",
            json={
                "answers": [
                    {
                        "question_reference": questions[0]["reference"],
                        "recorded_text": (
                            "A second warehouse is under contract and arrives next quarter."
                        ),
                    }
                ]
            },
        )
        assert answered.status_code == 201, answered.text
        revision = answered.json()
        assert revision["revision"] == 2

        # The arrow back: this revision says which review it answered and with what, so a
        # verdict that moves below can be attributed to the sentence that moved it (§6C.4).
        assert revision["answered"]["review_id"] == first_review["review_id"]
        recorded = revision["answered"]["answers"]
        assert [item["question_reference"] for item in recorded] == [
            questions[0]["reference"]
        ]
        assert recorded[0]["answer_belongs_in"] == "expected_future_changes"

        # And the case now carries the pair, over the wire, both halves attributed: the
        # review's question verbatim and the reader's own answer. Nothing was appended to the
        # five deciding lists, because the answer is not filed anywhere — it is weighed.
        assert revision["snapshot"]["clarifications"] == [
            {
                "id": revision["snapshot"]["clarifications"][0]["id"],
                "question": questions[0]["question"],
                "answer": (
                    "A second warehouse is under contract and arrives next quarter."
                ),
                "bears_on": "expected_future_changes",
            }
        ]
        assert revision["snapshot"]["expected_future_changes"] == []

        # A reference this review never asked is refused rather than recorded.
        refused = client.post(
            f"/api/reviews/{first_review['review_id']}/answers",
            json={"answers": [{"question_reference": "Q-99", "recorded_text": "Nothing."}]},
        )
        assert refused.status_code == 422
        assert "asked no question Q-99" in refused.json()["message"]

        second = client.post(
            "/api/reviews",
            json={
                "case_id": case_id,
                "repository_root": repository,
                "elicited_from": first_review["review_id"],
            },
        )
        assert second.status_code == 201, second.text
        second_review = second.json()

    # The second pass concludes and does not ask again.
    assert second_review["status"] == "succeeded"
    assert second_review["elicited_from"] == first_review["review_id"]
    assert second_review["report"]["overview"]["open_questions"] == []
    assert second_review["case_revision"] == 2
    # Same repository, same atlas — so a verdict that moved is attributable to the answer.
    assert second_review["atlas_version_id"] == first_review["atlas_version_id"]
    assert [item["reference"] for item in second_review["report"]["reviewed"]] == [
        item["reference"] for item in reviewed
    ]


def test_the_api_serves_the_code_a_finding_was_measured_from(runtime: Runtime) -> None:
    """The route behind "show me the problematic code" (ADR 0013).

    Delivery rather than search: the review already records which lines are the evidence, so
    the request names a boundary and the workspace answers with the code at its spans. What
    is defended here is the transport shape — that the spans resolve, that the reply says
    where each block came from and what it contributes, and that unfolding asks for more of
    the same lines rather than for something else.
    """

    repository = str(Path("eval/cases/speech-vendor/repository").resolve())

    with TestClient(create_app(runtime)) as client:
        started = client.post("/api/repositories/start", json={"root_path": repository})
        assert started.status_code == 201, started.text
        created = client.post(
            "/api/reviews",
            json={"case_id": started.json()["case_id"], "repository_root": repository},
        )
        assert created.status_code == 201, created.text
        review = created.json()
        reference = review["report"]["reviewed"][0]["reference"]

        response = client.get(
            f"/api/reviews/{review['review_id']}/source",
            params={"reference": reference, "context_lines": 0},
        )
        assert response.status_code == 200, response.text
        excerpts = response.json()

        assert excerpts, "a review of a real repository records spans to read"
        for excerpt in excerpts:
            assert excerpt["reference"] == reference
            assert excerpt["location"]["path"].endswith(".py")
            assert excerpt["role"]
            # Exactly one of the code and the reason there is none.
            assert bool(excerpt["text"]) != bool(excerpt["unavailable"])

        # Unfolding returns more of the same file, not a different span.
        wider = client.get(
            f"/api/reviews/{review['review_id']}/source",
            params={"reference": reference, "context_lines": 4},
        ).json()
        assert wider[0]["location"] == excerpts[0]["location"]
        assert len(wider[0]["text"].splitlines()) > len(excerpts[0]["text"].splitlines())

        # A boundary this review does not contain is an empty answer rather than an error:
        # asking about a finding that is not there is not a failure of the route.
        assert (
            client.get(
                f"/api/reviews/{review['review_id']}/source",
                params={"reference": "BR-999"},
            ).json()
            == []
        )


def test_a_streamed_review_that_fails_says_so_in_the_stream(
    runtime: Runtime,
    tmp_path: Path,
) -> None:
    """The status code is already 200 when the run fails, so the body has to carry it."""

    with TestClient(create_app(runtime)) as client:
        created = client.post("/api/cases", json={
            "title": "Unindexed",
            "problem_statement": "Nothing has been indexed yet.",
            "desired_outcome": "An honest error, mid-stream.",
        })

        with client.stream(
            "POST",
            "/api/reviews/stream",
            json={
                "case_id": created.json()["case_id"],
                "repository_root": str(tmp_path),
            },
        ) as response:
            assert response.status_code == 200
            events = [json.loads(line) for line in response.iter_lines() if line.strip()]

        assert [event["event"] for event in events] == ["failed"]
        problem = events[0]["problem"]
        assert problem["code"] == "not_found"
        assert "repo index" in problem["message"]
        # Nothing was persisted: a failed run leaves no half-review behind.
        assert client.get("/api/reviews").json() == []


def test_a_streamed_answer_ends_in_the_message_that_was_appended(runtime: Runtime) -> None:
    """The prose is a preview; the `answered` line is the record.

    Both are asserted against the history afterwards, because that is the only copy that
    matters: a route that streamed one answer and stored another would pass any test that
    looked only at the stream.
    """

    with TestClient(create_app(runtime)) as client:
        loaded = client.post(f"/api/bundled-cases/{FIXTURE}/load")
        case_id = loaded.json()["case_id"]
        repository_root = {
            item["name"]: item for item in client.get("/api/bundled-cases").json()
        }[FIXTURE]["repository_root"]
        review = client.post(
            "/api/reviews",
            json={"case_id": case_id, "repository_root": repository_root},
        ).json()
        conversation = client.post(
            "/api/review-conversations", json={"review_id": review["review_id"]}
        )
        conversation_id = conversation.json()["conversation_id"]

        with client.stream(
            "POST",
            f"/api/review-conversations/{conversation_id}/messages/stream",
            json={"question": "What did you make of the TaskFormatter boundary?"},
        ) as response:
            assert response.status_code == 200, response.read()
            assert response.headers["content-type"].startswith("application/x-ndjson")
            events = [json.loads(line) for line in response.iter_lines() if line.strip()]

        prose = [event for event in events if event["event"] == "prose"]
        assert len(prose) > 1
        assert events[-1]["event"] == "answered"
        message = events[-1]["message"]
        assert "".join(event["text"] for event in prose) == message["answer"]["answer"]
        known = {item["reference"] for item in review["report"]["reviewed"]}
        assert set(message["answer"]["supporting_references"]) <= known

        history = client.get(f"/api/review-conversations/{conversation_id}").json()
        assert len(history["messages"]) == 1
        assert history["messages"][0]["answer"]["answer"] == message["answer"]["answer"]


def test_a_streamed_question_that_cannot_be_asked_says_so_in_the_stream(
    runtime: Runtime,
) -> None:
    """A conversation that does not exist is a `failed` line, and appends nothing."""

    with TestClient(create_app(runtime)) as client, client.stream(
        "POST",
        "/api/review-conversations/conv-missing/messages/stream",
        json={"question": "Is anyone there?"},
    ) as response:
        assert response.status_code == 200
        events = [json.loads(line) for line in response.iter_lines() if line.strip()]

    assert [event["event"] for event in events] == ["failed"]
    assert events[0]["problem"]["code"] == "not_found"


def test_unknown_identifiers_return_stable_problem_details(runtime: Runtime) -> None:
    """A client distinguishes "not there" from "malformed" by code, not by prose."""

    with TestClient(create_app(runtime)) as client:
        missing = client.get("/api/reviews/rev_missing")
        assert missing.status_code == 404
        body = missing.json()
        assert body["code"]
        assert body["message"]

        malformed = client.post("/api/reviews", json={"case_id": ""})
        assert malformed.status_code == 422

        unknown_route = client.get("/api/not-a-route")
        assert unknown_route.status_code == 404
        assert unknown_route.json()["code"]


def test_a_review_of_an_unindexed_repository_fails_rather_than_reporting_nothing(
    runtime: Runtime,
    tmp_path: Path,
) -> None:
    """Zero boundaries and no atlas would serialise identically. They must not."""

    with TestClient(create_app(runtime)) as client:
        created = client.post("/api/cases", json={
            "title": "Unindexed",
            "problem_statement": "Nothing has been indexed yet.",
            "desired_outcome": "An honest error.",
        })
        assert created.status_code == 201, created.text

        attempted = client.post(
            "/api/reviews",
            json={
                "case_id": created.json()["case_id"],
                "repository_root": str(tmp_path),
            },
        )

        assert attempted.status_code == 404
        assert "repo index" in attempted.json()["message"]


def test_a_review_of_unscored_code_reports_no_score_rather_than_a_made_up_one(
    runtime: Runtime,
    tmp_path: Path,
) -> None:
    """Someone's own repository has no right answer; inventing one would be worse than none.

    Written here rather than borrowed from `eval/cases`. Both bundled examples ship an
    answer key on purpose, and a test that relied on one of them not having one would go
    green or red depending on a decision about the examples rather than about scoring.
    """

    own_code = tmp_path / "someones-own-repository"
    own_code.mkdir()
    (own_code / "gateway.py").write_text(
        "from typing import Protocol\n\n\n"
        "class Gateway(Protocol):\n"
        "    def send(self, message: str) -> None: ...\n\n\n"
        "class HttpGateway(Gateway):\n"
        "    def send(self, message: str) -> None:\n"
        "        print(message)\n",
        encoding="utf-8",
    )
    atlas = runtime.analyzer.analyze(own_code)
    runtime.atlas_repository.save(atlas)

    with TestClient(create_app(runtime)) as client:
        created = client.post("/api/cases", json={
            "title": "Unscored",
            "problem_statement": "A repository that ships no answer key.",
            "desired_outcome": "An honest absence of a score.",
        })
        review = client.post("/api/reviews", json={
            "case_id": created.json()["case_id"],
            "repository_root": atlas.version.root_path,
        })
        assert review.status_code == 201, review.text

        scored = client.get(f"/api/reviews/{review.json()['review_id']}/score")

        assert scored.status_code == 200
        assert scored.json() is None


def test_a_validation_failure_says_which_field_was_wrong(runtime: Runtime) -> None:
    """The message a reader sees has to point at something.

    "The request did not match the API contract" is true of every possible cause and points at
    none of them. The field is what makes the difference between an error and a diagnosis.
    """

    with TestClient(create_app(runtime)) as client:
        refused = client.post("/api/reviews", json={"case_id": "c"})

    assert refused.status_code == 422
    problem = refused.json()
    assert problem["field_errors"]
    for field in problem["field_errors"]:
        assert field in problem["message"]


def test_the_openapi_contract_declares_the_review_surface(runtime: Runtime) -> None:
    """The generated TypeScript client is derived from this; a gap here is a silent any."""

    with TestClient(create_app(runtime)) as client:
        document = client.get("/api/openapi.json")

    assert document.status_code == 200
    paths = document.json()["paths"]
    for route in (
        "/api/bundled-cases",
        "/api/reviews",
        "/api/reviews/stream",
        "/api/reviews/{review_id}",
        "/api/review-conversations",
        "/api/review-conversations/{conversation_id}/messages",
        "/api/review-conversations/{conversation_id}/messages/stream",
        "/api/reviews/{review_id}/score",
        "/api/repositories/explore",
    ):
        assert route in paths, route

    schemas = document.json()["components"]["schemas"]
    assert "BoundaryReview" in schemas
    assert "ReviewedBoundary" in schemas
    assert "ReviewConversation" in schemas
    # The progress line is a declared contract, not an undocumented convention: a client
    # that had to guess the shape would be parsing prose.
    assert schemas["ReviewProgress"]["discriminator"]["propertyName"] == "event"
    assert schemas["AnswerProgress"]["discriminator"]["propertyName"] == "event"
    stream = document.json()["paths"]["/api/reviews/stream"]["post"]["responses"]["200"]
    assert "application/x-ndjson" in stream["content"]
    answers = paths["/api/review-conversations/{conversation_id}/messages/stream"]["post"]
    assert "application/x-ndjson" in answers["responses"]["200"]["content"]
    # The old consultation surface is gone, not merely unused by the workspace.
    assert not any(path.startswith("/api/consultations") for path in paths)
    assert not any(path.startswith("/api/runs") for path in paths)


def test_cancelling_and_deleting_a_review_over_the_api(runtime: Runtime) -> None:
    """Both refusals and both successes, in the order a person meets them."""

    with TestClient(create_app(runtime)) as client:
        loaded = client.post(f"/api/bundled-cases/{FIXTURE}/load")
        case_id = loaded.json()["case_id"]
        repository_root = client.get("/api/repositories").json()[0]["root_path"]
        review = client.post(
            "/api/reviews",
            json={"case_id": case_id, "repository_root": repository_root},
        )
        assert review.status_code == 201, review.text
        review_id = review.json()["review_id"]

        # Cancelling something that already finished is a conflict, not a quiet success:
        # a client told "cancelled" would report a stop that never happened.
        refused = client.post(f"/api/reviews/{review_id}/cancel")
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "state_conflict"
        assert "succeeded" in refused.json()["message"]
        # And not worth retrying — a finished review will not start running again.
        assert refused.json()["retryable"] is False

        conversation = client.post(
            "/api/review-conversations", json={"review_id": review_id}
        )
        assert conversation.status_code == 201, conversation.text

        removed = client.delete(f"/api/reviews/{review_id}")
        assert removed.status_code == 204, removed.text
        assert client.get(f"/api/reviews/{review_id}").status_code == 404
        assert client.get("/api/reviews").json() == []
        # The threads went with it: one whose review is gone has nothing to be about.
        assert (
            client.get(
                f"/api/review-conversations?review_id={review_id}"
            ).json()
            == []
        )
        assert client.delete(f"/api/reviews/{review_id}").status_code == 404


def test_the_openapi_contract_declares_cancelling_and_deleting(runtime: Runtime) -> None:
    with TestClient(create_app(runtime)) as client:
        document = client.get("/api/openapi.json").json()

    assert "post" in document["paths"]["/api/reviews/{review_id}/cancel"]
    assert "delete" in document["paths"]["/api/reviews/{review_id}"]
    # A 204 has no body, and a generated client that tried to parse one would throw on the
    # single response that means the request worked.
    delete = document["paths"]["/api/reviews/{review_id}"]["delete"]["responses"]
    assert "204" in delete
    assert "content" not in delete["204"]
