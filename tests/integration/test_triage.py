"""Standing decisions and their discussion, through storage and through the API.

Against a real database and a real review, because everything interesting here is about how
two records that were written apart are read back together: the latest decision per boundary,
the thread that outlives it, and the join onto a review that knows nothing about either.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from archcompass.bootstrap import Runtime
from archcompass.domain.errors import BranchNotFoundError
from archcompass.domain.lineage import BranchLineage, RepositoryLineage
from archcompass.domain.triage import DecisionComment, DecisionState, StandingDecision
from archcompass.presentation.web import create_app

FIXTURE = "boundary-review"
FINGERPRINT = "bdry_0123456789abcdef01234567"


def _branch(runtime: Runtime, *, name: str = "main") -> str:
    """A branch lineage to hold opinions on, without indexing anything."""

    repository = runtime.lineage_repository.get_or_create_repository(
        RepositoryLineage(repo_id="repoid_test", canonical_root="/tmp/repository")
    )
    branch = runtime.lineage_repository.get_or_create_branch(
        BranchLineage(
            branch_id=f"branch_test_{name}",
            repo_id=repository.repo_id,
            branch_name=name,
        )
    )
    return branch.branch_id


def _decision(branch_id: str, **overrides: Any) -> StandingDecision:
    fields: dict[str, Any] = {
        "branch_id": branch_id,
        "boundary_fingerprint": FINGERPRINT,
        "state": DecisionState.ACCEPTED,
        "author": "Deniz",
        "review_id": "rev_1",
        "boundary_reference": "BR-001",
        "material": True,
        "verdict_label": "Not earning its place",
    }
    fields.update(overrides)
    return StandingDecision(**fields)


def test_the_latest_decision_is_what_stands_and_the_earlier_one_survives(
    runtime: Runtime,
) -> None:
    branch_id = _branch(runtime)
    earlier = datetime(2026, 8, 4, 9, tzinfo=UTC)

    runtime.triage_service.decide(_decision(branch_id, decided_at=earlier))
    runtime.triage_service.decide(
        _decision(
            branch_id,
            state=DecisionState.WAIVED,
            reason="Intentional seam for the billing split.",
            decided_at=earlier + timedelta(hours=2),
        )
    )

    current = runtime.triage_service.decisions_for_branch(branch_id)
    assert [item.state for item in current] == [DecisionState.WAIVED]
    history = runtime.triage_service.history(branch_id, FINGERPRINT)
    assert [item.state for item in history] == [
        DecisionState.ACCEPTED,
        DecisionState.WAIVED,
    ]


def test_two_decisions_in_the_same_instant_keep_the_order_they_were_written(
    runtime: Runtime,
) -> None:
    """Timestamps tie; insertion order does not. The second write is the one that stands."""

    branch_id = _branch(runtime)
    instant = datetime(2026, 8, 4, 9, tzinfo=UTC)

    runtime.triage_service.decide(_decision(branch_id, decided_at=instant))
    runtime.triage_service.decide(
        _decision(branch_id, state=DecisionState.PARKED, decided_at=instant)
    )

    current = runtime.triage_service.decisions_for_branch(branch_id)
    assert [item.state for item in current] == [DecisionState.PARKED]


def test_each_boundary_reports_only_its_own_current_decision(runtime: Runtime) -> None:
    branch_id = _branch(runtime)
    other = "bdry_ffffffffffffffffffffffff"

    runtime.triage_service.decide(_decision(branch_id))
    runtime.triage_service.decide(
        _decision(branch_id, boundary_fingerprint=other, state=DecisionState.PARKED)
    )

    current = runtime.triage_service.decisions_for_branch(branch_id)
    assert {item.boundary_fingerprint: item.state for item in current} == {
        FINGERPRINT: DecisionState.ACCEPTED,
        other: DecisionState.PARKED,
    }


def test_a_thread_numbers_itself_and_needs_no_decision_to_exist(runtime: Runtime) -> None:
    branch_id = _branch(runtime)

    for body in ("Why is this here?", "Because billing needed it.", "Then it stays."):
        runtime.triage_service.comment(
            DecisionComment(
                branch_id=branch_id,
                boundary_fingerprint=FINGERPRINT,
                author="Rae",
                body=body,
                # Deliberately wrong, and deliberately ignored: the server numbers the thread.
                ordinal=1,
            )
        )

    thread = runtime.triage_service.comments(branch_id, FINGERPRINT)
    assert [item.ordinal for item in thread] == [1, 2, 3]
    assert [item.body for item in thread][-1] == "Then it stays."
    assert runtime.triage_service.comment_counts(branch_id) == {FINGERPRINT: 3}
    # Nothing was decided, and the thread is there anyway.
    assert runtime.triage_service.decisions_for_branch(branch_id) == []


def test_a_branch_this_workspace_has_never_seen_is_refused(runtime: Runtime) -> None:
    with pytest.raises(BranchNotFoundError, match="branch_unknown"):
        runtime.triage_service.decide(_decision("branch_unknown"))


def _reviewed_through_the_api(client: TestClient) -> dict[str, Any]:
    """A finished review of a bundled example, which is always the second of two passes."""

    loaded = client.post(f"/api/examples/{FIXTURE}/load")
    assert loaded.status_code == 201, loaded.text
    root = loaded.json()["root_path"]
    started = client.post("/api/repositories/start", json={"root_path": root})
    assert started.status_code == 200, started.text
    case_id = started.json()["case_id"]
    first = client.post("/api/reviews", json={"case_id": case_id, "repository_root": root})
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


def _first_boundary(client: TestClient, review_id: str) -> dict[str, Any]:
    detail = client.get(f"/api/reviews/{review_id}")
    assert detail.status_code == 200, detail.text
    dispositions = detail.json()["boundary_triage"]
    assert dispositions, "the example review reaches at least one boundary"
    return cast("dict[str, Any]", dispositions[0])


def test_a_decision_reaches_the_branch_listing_and_the_review_it_was_taken_on(
    runtime: Runtime,
) -> None:
    with TestClient(create_app(runtime)) as client:
        review = _reviewed_through_the_api(client)
        review_id = review["review_id"]
        branch_id = review["branch_id"]
        assert branch_id, "a review of an indexed repository is attributed to a branch"
        boundary = _first_boundary(client, review_id)
        assert boundary["decision"] is None
        assert boundary["fingerprint"].startswith("bdry_")

        reviewed = next(
            item
            for item in review["report"]["reviewed"]
            if item["reference"] == boundary["reference"]
        )
        recorded = client.post(
            "/api/decisions",
            json={
                "branch_id": branch_id,
                "boundary_fingerprint": boundary["fingerprint"],
                "state": "waived",
                "author": "Deniz",
                "reason": "Intentional seam for the billing split.",
                "review_id": review_id,
                "boundary_reference": boundary["reference"],
                "material": reviewed["material"],
                "verdict_label": reviewed["verdict_label"],
            },
        )
        assert recorded.status_code == 201, recorded.text
        assert recorded.json()["state"] == "waived"

        listed = client.get(f"/api/branches/{branch_id}/decisions")
        assert listed.status_code == 200, listed.text
        assert [item["boundary_fingerprint"] for item in listed.json()["decisions"]] == [
            boundary["fingerprint"]
        ]

        joined = _first_boundary(client, review_id)["decision"]
        assert joined is not None
        assert joined["state"] == "waived"
        assert joined["author"] == "Deniz"
        assert joined["reason"] == "Intentional seam for the billing split."
        # Taken against exactly the verdict this run reached.
        assert joined["taken_on_current_verdict"] is True


def test_a_decision_taken_against_another_verdict_says_so(runtime: Runtime) -> None:
    """The attention rule the interface draws: the ground moved, and nothing expired."""

    with TestClient(create_app(runtime)) as client:
        review = _reviewed_through_the_api(client)
        review_id = review["review_id"]
        boundary = _first_boundary(client, review_id)
        reviewed = next(
            item
            for item in review["report"]["reviewed"]
            if item["reference"] == boundary["reference"]
        )

        recorded = client.post(
            "/api/decisions",
            json={
                "branch_id": review["branch_id"],
                "boundary_fingerprint": boundary["fingerprint"],
                "state": "accepted",
                "author": "Deniz",
                "review_id": review_id,
                "boundary_reference": boundary["reference"],
                # What an earlier run had concluded, which is not what this one says.
                "material": not reviewed["material"],
                "verdict_label": "Something the run no longer says",
            },
        )
        assert recorded.status_code == 201, recorded.text

        joined = _first_boundary(client, review_id)["decision"]
        assert joined is not None
        assert joined["state"] == "accepted"
        assert joined["taken_on_current_verdict"] is False


def test_a_waiver_without_a_reason_is_refused_by_the_api(runtime: Runtime) -> None:
    with TestClient(create_app(runtime)) as client:
        branch_id = _branch(runtime)

        refused = client.post(
            "/api/decisions",
            json={
                "branch_id": branch_id,
                "boundary_fingerprint": FINGERPRINT,
                "state": "waived",
                "author": "Deniz",
                "review_id": "rev_1",
                "boundary_reference": "BR-001",
                "material": True,
                "verdict_label": "Not earning its place",
            },
        )

        assert refused.status_code == 422, refused.text
        problem = refused.json()
        assert problem["code"] == "validation_error"
        assert "why it was waived" in problem["message"]
        assert problem["field_errors"]


def test_deciding_on_an_unknown_branch_is_a_404(runtime: Runtime) -> None:
    with TestClient(create_app(runtime)) as client:
        refused = client.post(
            "/api/decisions",
            json={
                "branch_id": "branch_nobody_has_seen",
                "boundary_fingerprint": FINGERPRINT,
                "state": "accepted",
                "author": "Deniz",
                "review_id": "rev_1",
                "boundary_reference": "BR-001",
                "material": True,
                "verdict_label": "Not earning its place",
            },
        )

        assert refused.status_code == 404, refused.text
        assert refused.json()["code"] == "not_found"
        assert client.get("/api/branches/branch_nobody_has_seen/decisions").status_code == 404


def test_the_history_route_keeps_every_disposition_ever_recorded(runtime: Runtime) -> None:
    with TestClient(create_app(runtime)) as client:
        branch_id = _branch(runtime)
        body = {
            "branch_id": branch_id,
            "boundary_fingerprint": FINGERPRINT,
            "author": "Deniz",
            "review_id": "rev_1",
            "boundary_reference": "BR-001",
            "material": True,
            "verdict_label": "Not earning its place",
        }
        assert client.post("/api/decisions", json={**body, "state": "parked"}).status_code == 201
        assert (
            client.post(
                "/api/decisions",
                json={**body, "state": "waived", "reason": "Deliberate, and documented."},
            ).status_code
            == 201
        )

        history = client.get(f"/api/decisions/{branch_id}/{FINGERPRINT}/history")

        assert history.status_code == 200, history.text
        assert [item["state"] for item in history.json()] == ["parked", "waived"]


def test_the_thread_round_trips_and_is_counted_on_the_branch(runtime: Runtime) -> None:
    with TestClient(create_app(runtime)) as client:
        branch_id = _branch(runtime)
        thread = f"/api/decisions/{branch_id}/{FINGERPRINT}/comments"

        first = client.post(thread, json={"author": "Rae", "body": "Why is this here?"})
        assert first.status_code == 201, first.text
        assert first.json()["ordinal"] == 1
        second = client.post(thread, json={"author": "Deniz", "body": "Billing needed it."})
        assert second.status_code == 201, second.text
        assert second.json()["ordinal"] == 2

        listed = client.get(thread)
        assert listed.status_code == 200, listed.text
        assert [item["body"] for item in listed.json()] == [
            "Why is this here?",
            "Billing needed it.",
        ]

        counts = client.get(f"/api/branches/{branch_id}/decisions").json()["comment_counts"]
        assert counts == {FINGERPRINT: 2}


def test_a_review_without_a_branch_is_shown_its_boundaries_and_no_decisions(
    runtime: Runtime,
) -> None:
    """Reviews written before lineages existed carry no branch, so nothing is joined.

    The fingerprints are still reported: they are a property of the boundary, not of the
    triage, and a client needs them the moment such a repository is indexed again.
    """

    with TestClient(create_app(runtime)) as client:
        review = _reviewed_through_the_api(client)
        boundary = _first_boundary(client, review["review_id"])
        recorded = client.post(
            "/api/decisions",
            json={
                "branch_id": review["branch_id"],
                "boundary_fingerprint": boundary["fingerprint"],
                "state": "accepted",
                "author": "Deniz",
                "review_id": review["review_id"],
                "boundary_reference": boundary["reference"],
                "material": True,
                "verdict_label": "Not earning its place",
            },
        )
        assert recorded.status_code == 201, recorded.text
        assert _first_boundary(client, review["review_id"])["decision"] is not None
        stored = runtime.review_repository.get(review["review_id"])
        # Reaching past the repository on purpose: nothing writes a null branch any more, and
        # this is what a row written before migration 024 looks like.
        with runtime.database.connect() as connection:
            connection.execute(
                "UPDATE boundary_reviews SET branch_id = NULL, review_json = ? "
                "WHERE review_id = ?",
                (
                    stored.model_copy(update={"branch_id": None}).model_dump_json(),
                    review["review_id"],
                ),
            )
            connection.commit()

        detail = client.get(f"/api/reviews/{review['review_id']}")

        assert detail.status_code == 200, detail.text
        dispositions = detail.json()["boundary_triage"]
        assert dispositions
        assert all(item["decision"] is None for item in dispositions)
        assert all(item["fingerprint"].startswith("bdry_") for item in dispositions)
