"""The local HTTP surface: the whole review loop, and the contracts a client relies on."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from archcompass.bootstrap import Runtime
from archcompass.domain.review import ReviewStatus
from archcompass.presentation.web import create_app

FIXTURE = "boundary-review"


def _example(client: TestClient) -> tuple[str, str]:
    """An example chosen in the workspace: repository indexed, and a case about it.

    Two calls because the browser makes two. An example ships no case — loading it hands
    back a repository, which is then started from like any repository a user picks.
    """

    loaded = client.post(f"/api/examples/{FIXTURE}/load")
    assert loaded.status_code == 201, loaded.text
    root = loaded.json()["root_path"]
    started = client.post("/api/repositories/start", json={"root_path": root})
    assert started.status_code == 200, started.text
    return started.json()["case_id"], root


def _reviewed(client: TestClient) -> dict[str, Any]:
    """A review that reached a conclusion, which is always the second of two passes.

    The first pass on an unwritten case asks rather than concludes, so every surface that
    shows a finished review is looking at a second pass — with or without an answer having
    been written between them.
    """

    case_id, root = _example(client)
    first = client.post(
        "/api/reviews", json={"case_id": case_id, "repository_root": root}
    )
    assert first.status_code == 201, first.text
    second = client.post(
        "/api/reviews",
        json={
            "case_id": case_id,
            "repository_root": root,
            "elicited_from": first.json()["review_id"],
        },
    )
    assert second.status_code == 201, second.text
    return cast("dict[str, Any]", second.json())


def test_the_api_covers_the_whole_review_loop(runtime: Runtime) -> None:
    """Pick an example, review it, read it back, ask about it — in one client session."""

    with TestClient(create_app(runtime)) as client:
        workspace = client.get("/api/workspace")
        assert workspace.status_code == 200
        assert workspace.json()["models"]["reasoning"]["provider"] == "fake"

        examples = client.get("/api/examples")
        assert examples.status_code == 200
        listed = {item["name"]: item for item in examples.json()}
        assert FIXTURE in listed
        # A name and a sentence about the repository, and no case: what the review needs to
        # know it asks for, which is the flow a visitor is here to see.
        assert listed[FIXTURE]["title"]
        assert listed[FIXTURE]["description"]

        review = _reviewed(client)
        review_id = review["review_id"]
        assert review["status"] == "succeeded"
        assert review["report"]["reviewed"]
        assert review["markdown_report"]

        fetched = client.get(f"/api/reviews/{review_id}")
        assert fetched.status_code == 200
        assert fetched.json()["review_id"] == review_id

        summaries = client.get("/api/reviews")
        assert summaries.status_code == 200
        # Both passes are listed. The first one asked and is kept as it was; nothing is
        # replaced by the run that answered it.
        assert review_id in {item["review_id"] for item in summaries.json()}
        assert sorted(item["status"] for item in summaries.json()) == [
            "awaiting_answers",
            "succeeded",
        ]

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


def test_every_shipped_example_is_a_repository_with_a_name_and_no_case(
    runtime: Runtime,
) -> None:
    """What the front door offers: repositories to point at, described in one line each.

    A case shipped beside one would answer the questions before a visitor was asked them,
    and the first pass would conclude instead of eliciting — so the absence is asserted on
    disk rather than trusted to stay absent.
    """

    with TestClient(create_app(runtime)) as client:
        listed = client.get("/api/examples").json()

    assert len(listed) >= 2
    for example in listed:
        assert set(example) == {"name", "title", "description", "repository_root"}
        assert example["title"] and example["description"]
        root = Path(example["repository_root"])
        assert root.is_dir()
        assert (root.parent / "example.yaml").is_file()
        assert not (root.parent / "case.yaml").exists()
        assert not (root.parent / "expected.yaml").exists()


def test_loading_an_example_indexes_it_and_creates_nothing_else(runtime: Runtime) -> None:
    """The load is an indexing step, so what comes back is the atlas and not a case.

    The route exists because the hosted demo has no folder picker: it is how a repository
    the visitor may index gets named. Everything after it is the ordinary path.
    """

    with TestClient(create_app(runtime)) as client:
        loaded = client.post(f"/api/examples/{FIXTURE}/load")

        assert loaded.status_code == 201, loaded.text
        version = loaded.json()
        assert Path(version["root_path"]).is_dir()
        assert version["version_id"]
        assert [item["root_path"] for item in client.get("/api/repositories").json()] == [
            version["root_path"]
        ]
        assert client.get("/api/cases").json() == []

        missing = client.post("/api/examples/no-such-example/load")
        assert missing.status_code == 404, missing.text
        assert missing.json()["code"] == "not_found"


def test_a_streamed_review_counts_its_boundaries_before_judging_them(
    runtime: Runtime,
) -> None:
    """The run has to be countable, which means detection must be reported on its own.

    A stream that only spoke after the first verdict would leave the longest wait in the
    review — the first model call — with nothing to show, which is the wait the streaming
    route exists to replace.
    """

    with TestClient(create_app(runtime)) as client:
        case_id, repository_root = _example(client)
        # The pass that concludes, because that is the one whose last line carries a
        # finished review. The first pass is watched the same way and ends by asking.
        first = client.post(
            "/api/reviews", json={"case_id": case_id, "repository_root": repository_root}
        )
        assert first.status_code == 201, first.text

        with client.stream(
            "POST",
            "/api/reviews/stream",
            json={
                "case_id": case_id,
                "repository_root": repository_root,
                "elicited_from": first.json()["review_id"],
            },
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
        assert started.status_code == 200, started.text
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
        assert started.status_code == 200, started.text
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


def test_a_finished_review_downloads_as_the_markdown_it_was_written_as(
    runtime: Runtime,
) -> None:
    """Export hands over the stored document, not a second rendering of the same review.

    Byte-for-byte against `markdown_report` is the whole assertion. A route that re-rendered
    would pass every test about headings and still be wrong: the file a reader keeps has to
    be the report the workspace stored when the review concluded, so the two cannot drift.
    """

    with TestClient(create_app(runtime)) as client:
        review = _reviewed(client)
        review_id = review["review_id"]

        exported = client.get(f"/api/reviews/{review_id}/report")

    assert exported.status_code == 200, exported.text
    assert exported.text == review["markdown_report"]
    assert exported.headers["content-type"].startswith("text/markdown")
    # The header is what makes this a download rather than a page: without the filename the
    # browser saves the review under its route, and every export lands as `report`.
    disposition = exported.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert f'filename="archcompass-review-{review_id}.md"' in disposition


def test_a_review_with_no_report_refuses_the_download_rather_than_serving_nothing(
    runtime: Runtime,
) -> None:
    """The two absences a reader can meet, told apart by whether waiting would help.

    A run in progress will have a report shortly; one that was stopped never will. Both are
    conflicts rather than 404s — the review is there, and it is the document that is not.
    """

    with TestClient(create_app(runtime)) as client:
        assert client.get("/api/reviews/rev_missing/report").status_code == 404

        finished = _reviewed(client)
        # Written into the store rather than raced against a real run: the substitute
        # provider finishes faster than a request can be made against a running review.
        running = runtime.review_repository.get(finished["review_id"]).model_copy(
            update={
                "review_id": "rev_stillrunning",
                "status": ReviewStatus.RUNNING,
                "report": None,
                "markdown_report": None,
            }
        )
        runtime.review_repository.begin(running)

        waiting = client.get(f"/api/reviews/{running.review_id}/report")
        assert waiting.status_code == 409, waiting.text
        assert waiting.json()["code"] == "state_conflict"
        assert "still running" in waiting.json()["message"]
        # Worth asking again, and the only one of the two that is.
        assert waiting.json()["retryable"] is True

        assert runtime.review_repository.cancel(running.review_id)
        stopped = client.get(f"/api/reviews/{running.review_id}/report")
        assert stopped.status_code == 409, stopped.text
        assert "cancelled" in stopped.json()["message"]
        assert stopped.json()["retryable"] is False


def test_the_api_answers_a_whole_map_in_one_request(runtime: Runtime) -> None:
    """The route behind the atlas tab opening with context rather than isolated boxes.

    Asked one node at a time — `/inspect`, which is what the workspace did before — each
    answer is the node alone, so every edge out of it names a neighbour the client was never
    given and has to be dropped. Defended here is that one request carries both ends of every
    edge it reports, and that an id the atlas no longer holds is skipped rather than refused.
    """

    repository = str(Path("eval/cases/speech-vendor/repository").resolve())

    with TestClient(create_app(runtime)) as client:
        indexed = client.post("/api/repositories/index", json={"root_path": repository})
        assert indexed.status_code == 201, indexed.text
        summary = client.get("/api/repositories/summary", params={"root_path": repository})
        anchors = summary.json()["node_ids"][:3]
        assert len(anchors) == 3

        response = client.post(
            "/api/repositories/review-context",
            json={"root_path": repository, "node_ids": [*anchors, "node_departed"]},
        )

        assert response.status_code == 200, response.text
        context = response.json()
        # The stale id is absent from what was found, and did not take the others with it.
        assert context["node_ids"] == anchors
        assert "3 of 4 requested nodes found" in context["summary"]
        returned = {item["node_id"] for item in context["node_summaries"]}
        assert set(anchors) <= returned
        assert len(returned) > len(anchors), "neighbours are what makes this a map"
        # Every reported edge is drawable: both endpoints came back in the same answer.
        for edge in context["relationships"]:
            assert edge["source_id"] in returned
            assert edge["target_id"] in returned
        assert all(value["node_id"] in returned for value in context["metric_values"])
        assert all(signal["node_id"] in returned for signal in context["signals"])

        # Ids that are all stale are an empty map with a sentence, not a 4xx the tab would
        # have to render as a failure.
        empty = client.post(
            "/api/repositories/review-context",
            json={"root_path": repository, "node_ids": ["node_departed"]},
        )
        assert empty.status_code == 200, empty.text
        assert empty.json()["node_summaries"] == []
        assert "None of the 1 requested nodes" in empty.json()["summary"]


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
        review = _reviewed(client)
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
        "/api/examples",
        "/api/reviews",
        "/api/reviews/stream",
        "/api/reviews/{review_id}",
        "/api/review-conversations",
        "/api/review-conversations/{conversation_id}/messages",
        "/api/review-conversations/{conversation_id}/messages/stream",
        "/api/reviews/{review_id}/report",
        "/api/repositories/explore",
        "/api/repositories/review-context",
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
        review_id = _reviewed(client)["review_id"]

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
        # Only this one. The first pass it answered is a review in its own right and is
        # not swept up by deleting the run that concluded.
        assert review_id not in {
            item["review_id"] for item in client.get("/api/reviews").json()
        }
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


def test_the_folder_picker_is_shown_directories_and_never_files(
    runtime: Runtime,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Directories only, dot-directories omitted, ordered case-insensitively by name."""

    home = tmp_path / "home"
    for name in ("Ledger", "atlas", ".git", "Warehouse"):
        (home / name).mkdir(parents=True)
    (home / "notes.md").write_text("not a repository", encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))

    with TestClient(create_app(runtime)) as client:
        listing = client.get("/api/filesystem/directories")

    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["path"] == str(home)
    assert body["parent"] == str(tmp_path)
    assert [item["name"] for item in body["directories"]] == [
        "atlas",
        "Ledger",
        "Warehouse",
    ]
    # Absolute, because that is the whole reason this route exists.
    assert [item["path"] for item in body["directories"]] == [
        str(home / "atlas"),
        str(home / "Ledger"),
        str(home / "Warehouse"),
    ]


def test_the_folder_picker_descends_one_directory_at_a_time(
    runtime: Runtime, tmp_path: Path
) -> None:
    """Browsing is one request per directory, and the way back up comes with the listing."""

    (tmp_path / "projects" / "warehouse").mkdir(parents=True)

    with TestClient(create_app(runtime)) as client:
        listing = client.get(
            "/api/filesystem/directories", params={"path": str(tmp_path / "projects")}
        )

    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["parent"] == str(tmp_path)
    assert [item["name"] for item in body["directories"]] == ["warehouse"]


def test_the_filesystem_root_says_there_is_nowhere_above_it(runtime: Runtime) -> None:
    """Null rather than the root again: a picker climbs until this says stop."""

    with TestClient(create_app(runtime)) as client:
        listing = client.get("/api/filesystem/directories", params={"path": "/"})

    assert listing.status_code == 200, listing.text
    assert listing.json()["parent"] is None


def test_browsing_somewhere_unbrowsable_refuses_with_a_problem_detail(
    runtime: Runtime, tmp_path: Path
) -> None:
    """A missing path or a file is refused as a `ProblemDetail` the page can print."""

    (tmp_path / "case.yaml").write_text("title: not a folder\n", encoding="utf-8")

    with TestClient(create_app(runtime)) as client:
        missing = client.get(
            "/api/filesystem/directories", params={"path": str(tmp_path / "gone")}
        )
        a_file = client.get(
            "/api/filesystem/directories", params={"path": str(tmp_path / "case.yaml")}
        )

    assert missing.status_code == 422
    assert missing.json()["code"] == "validation_error"
    assert str(tmp_path / "gone") in missing.json()["message"]
    assert a_file.status_code == 422
    assert "not a folder" in a_file.json()["message"]


#: The nine headings `parse_policy` requires, each given a sentence. Written out rather than
#: borrowed from a bundled file, because what these tests are about is a body someone typed.
AUTHORED_SECTIONS = (
    "Intent",
    "Guidance",
    "Signals",
    "Diagnostic questions",
    "Likely consequences",
    "Exceptions",
    "Positive example",
    "Counterexample",
    "Related policies",
)


def _authored_body() -> str:
    return "\n".join(
        f"## {heading}\nWhat this policy says about {heading.lower()}."
        for heading in AUTHORED_SECTIONS
    )


def _draft(**overrides: object) -> dict[str, object]:
    return {
        "title": "Keep imports pointing inward",
        "description": "A module that imports its caller has no boundary left to defend.",
        "body": _authored_body(),
        "tags": ["dependencies", "layering"],
        "strength": "preferred",
        **overrides,
    }


def test_a_policy_authored_over_the_api_is_a_file_the_corpus_reads(
    runtime: Runtime,
) -> None:
    """Created, edited and deleted through the API; Markdown on disk the whole time.

    The point of the round trip is that nothing about an authored policy is a second class
    of record: it is written where the workspace keeps its own, read back through the same
    parser as the bundled corpus, and listed beside it.
    """

    authored = runtime.workspace / ".archcompass" / "policies"

    with TestClient(create_app(runtime)) as client:
        created = client.post("/api/policies", json=_draft())
        assert created.status_code == 201, created.text
        policy = created.json()
        # The id is derived from the title rather than sent: one name for the thing, and it
        # is the name every citation of it will use.
        assert policy["id"] == "keep-imports-pointing-inward"
        assert policy["scope"] == "general"
        assert policy["origin"] == "workspace"
        assert policy["tags"] == ["dependencies", "layering"]

        written = authored / "keep-imports-pointing-inward.md"
        assert written.is_file()
        assert written.read_text(encoding="utf-8").startswith("---\n")
        assert policy["source_path"] == str(written)

        listed = client.get("/api/policies")
        assert listed.status_code == 200
        catalog = {item["id"]: item for item in listed.json()}
        assert catalog["keep-imports-pointing-inward"]["origin"] == "workspace"
        # Everything else in reach is somebody else's file, and says so.
        assert {
            item["origin"]
            for item in catalog.values()
            if item["id"] != "keep-imports-pointing-inward"
        } == {"external"}

        edited = client.put(
            "/api/policies/keep-imports-pointing-inward",
            json=_draft(
                title="Keep every import pointing inward",
                strength="required",
                tags=["layering"],
            ),
        )
        assert edited.status_code == 200, edited.text
        # The title moved and the id did not follow it: an id is what a review cites.
        assert edited.json()["id"] == "keep-imports-pointing-inward"
        assert edited.json()["title"] == "Keep every import pointing inward"
        assert edited.json()["strength"] == "required"
        assert [path.name for path in authored.glob("*.md")] == [
            "keep-imports-pointing-inward.md"
        ]

        deleted = client.delete("/api/policies/keep-imports-pointing-inward")
        assert deleted.status_code == 204, deleted.text
        assert not written.exists()
        assert client.get("/api/policies/keep-imports-pointing-inward").status_code == 404


def test_an_authored_policy_cannot_take_an_id_the_corpus_already_holds(
    runtime: Runtime,
) -> None:
    """Two policies under one id is a corpus that will not load, so it is refused first."""

    with TestClient(create_app(runtime)) as client:
        collision = client.post(
            "/api/policies", json=_draft(title="Delay premature abstraction")
        )

    assert collision.status_code == 409, collision.text
    assert collision.json()["code"] == "state_conflict"
    assert "delay-premature-abstraction" in collision.json()["message"]
    assert not (runtime.workspace / ".archcompass" / "policies").exists()


def test_policies_read_from_elsewhere_are_not_this_workspace_to_rewrite(
    runtime: Runtime,
) -> None:
    """Bundled rules are read here, not owned here, and both writes say so as a conflict."""

    with TestClient(create_app(runtime)) as client:
        bundled = client.get("/api/policies/delay-premature-abstraction")
        assert bundled.status_code == 200
        assert bundled.json()["origin"] == "external"

        edited = client.put("/api/policies/delay-premature-abstraction", json=_draft())
        deleted = client.delete("/api/policies/delay-premature-abstraction")

        assert edited.status_code == 409, edited.text
        assert deleted.status_code == 409, deleted.text
        assert "does not own" in deleted.json()["message"]
        # Refused rather than half-applied: the bundled file is still the one it was.
        unchanged = client.get("/api/policies/delay-premature-abstraction")
        assert unchanged.json()["content_hash"] == bundled.json()["content_hash"]


def test_a_policy_that_cannot_be_read_back_is_never_left_on_disk(
    runtime: Runtime,
) -> None:
    """The check is the parser, not a second opinion about what a policy looks like.

    A body missing sections is written, parsed, refused and removed, so the corpus never
    holds a file the next review would fail to load — and an edit refused that way leaves
    the policy it was an edit of exactly as it was.
    """

    authored = runtime.workspace / ".archcompass" / "policies"

    with TestClient(create_app(runtime)) as client:
        refused = client.post(
            "/api/policies",
            json=_draft(body="## Intent\nSomething, but not the nine sections."),
        )
        assert refused.status_code == 422, refused.text
        assert refused.json()["code"] == "validation_error"
        assert "missing sections" in refused.json()["message"]
        assert list(authored.glob("*")) == []

        # A title with nothing to make an id out of is refused by the contract instead.
        assert client.post("/api/policies", json=_draft(title="...")).status_code == 422

        assert client.post("/api/policies", json=_draft()).status_code == 201
        written = authored / "keep-imports-pointing-inward.md"
        before = written.read_text(encoding="utf-8")
        broken = client.put(
            "/api/policies/keep-imports-pointing-inward",
            json=_draft(body="## Intent\nNot enough of a policy to store."),
        )

        assert broken.status_code == 422, broken.text
        assert written.read_text(encoding="utf-8") == before
        assert list(authored.glob("*.md.staged")) == []


def test_a_repository_is_checked_out_by_address_and_then_started_from(
    tmp_path: Path, runtime: Runtime
) -> None:
    """The route a pasted URL takes: clone, then join the flow a picked folder is already on.

    A local directory stands in for the remote, so this asks git to do the real work over a
    real transport without leaving the machine.
    """

    remote = tmp_path / "remote"
    remote.mkdir()
    (remote / "store.py").write_text("class Store:\n    pass\n", encoding="utf-8")
    for arguments in (
        ("init", "-b", "main"),
        ("config", "user.email", "test@example.invalid"),
        ("config", "user.name", "Test"),
        ("add", "."),
        ("commit", "-m", "first"),
    ):
        subprocess.run(
            ["git", "-C", str(remote), *arguments],
            check=True,
            capture_output=True,
            timeout=30,
        )

    with TestClient(create_app(runtime)) as client:
        cloned = client.post(
            "/api/repositories/checkout",
            json={"url": f"file://{remote}", "branch": None},
        )
        assert cloned.status_code == 201, cloned.text
        checkout = cloned.json()
        assert checkout["created"] is True
        assert checkout["branch_name"] == "main"
        assert checkout["managed"] is True

        started = client.post(
            "/api/repositories/start", json={"root_path": checkout["root_path"]}
        )
        assert started.status_code == 200, started.text

        again = client.post(
            "/api/repositories/checkout", json={"url": f"file://{remote}"}
        )
        assert again.status_code == 201, again.text
        assert again.json()["root_path"] == checkout["root_path"]
        assert again.json()["created"] is False

        missing = client.post(
            "/api/repositories/checkout",
            json={"url": f"file://{remote}", "branch": "nowhere"},
        )
        assert missing.status_code == 409, missing.text
        assert missing.json()["code"] == "checkout_failed"
        assert "no branch called nowhere" in missing.json()["message"]

        nonsense = client.post(
            "/api/repositories/checkout", json={"url": "not a repository"}
        )
        assert nonsense.status_code == 422, nonsense.text
        assert nonsense.json()["code"] == "validation_error"

        # The other end of the same directory: a page holding the folder asks for whatever
        # has landed since, without ever having seen the address.
        subprocess.run(
            ["git", "-C", str(remote), "commit", "--allow-empty", "-m", "second"],
            check=True,
            capture_output=True,
            timeout=30,
        )
        refreshed = client.post(
            "/api/repositories/refresh", json={"root_path": checkout["root_path"]}
        )
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json() == {
            "root_path": checkout["root_path"],
            "managed": True,
            "updated": True,
            "branch_name": "main",
        }

        unmanaged = client.post(
            "/api/repositories/refresh", json={"root_path": str(remote)}
        )
        assert unmanaged.status_code == 200, unmanaged.text
        assert unmanaged.json()["managed"] is False
        assert unmanaged.json()["updated"] is False
