"""A branch reads through to the branch it came from, and adopts a repository in one act.

The two halves of Phase B, tested where they meet the storage they depend on. The read-through
is a walk over rows the application writes one at a time — no schema constraint can promise it
is a line rather than a ring — so the assertions here are against a real database rather than
against a stubbed lineage lookup.

What is deliberately *not* asserted here is the delta. A branch inherits standings and the case
from its base; it does not inherit a line of revisions, and `test_delta_review` is where that
distinction is held.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from archcompass.application.standings import MAX_BASE_DEPTH, branch_chain
from archcompass.bootstrap import Runtime
from archcompass.domain.lineage import BranchLineage, RepositoryLineage
from archcompass.domain.triage import DecisionState, StandingDecision
from archcompass.presentation.web import create_app

FIXTURE = "boundary-review"
FINGERPRINT = "bdry_0123456789abcdef01234567"
OTHER = "bdry_ffffffffffffffffffffffff"


def _repository(runtime: Runtime) -> RepositoryLineage:
    return runtime.lineage_repository.get_or_create_repository(
        RepositoryLineage(repo_id="repoid_test", canonical_root="/tmp/repository")
    )


def _branch(runtime: Runtime, name: str, *, base: str | None = None) -> str:
    """A branch lineage to hold opinions on, without indexing anything.

    The base is written through the repository's own narrow setter rather than passed to
    `get_or_create_branch`, because that is the path the application actually uses: the base is
    resolved after the branch exists, when both lineages are in hand.
    """

    repository = _repository(runtime)
    branch = runtime.lineage_repository.get_or_create_branch(
        BranchLineage(
            branch_id=f"branch_test_{name}",
            repo_id=repository.repo_id,
            branch_name=name,
        )
    )
    if base is not None:
        branch = runtime.lineage_repository.set_base_branch(branch.branch_id, base)
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


def test_a_branch_with_no_standing_of_its_own_inherits_the_bases(runtime: Runtime) -> None:
    """The whole reason the column exists: a pull request is not a fresh repository."""

    main = _branch(runtime, "main")
    feature = _branch(runtime, "feature", base=main)
    runtime.triage_service.decide(_decision(main))

    standings = runtime.triage_service.standings_for_branch(feature)

    assert standings[FINGERPRINT].state is DecisionState.ACCEPTED
    assert standings[FINGERPRINT].branch_id == main, (
        "an inherited decision names where it was actually taken"
    )


def test_a_branchs_own_decision_wins_over_the_one_it_reads_through_to(
    runtime: Runtime,
) -> None:
    """Divergence is what deciding differently means, and it must not need an opt-out."""

    main = _branch(runtime, "main")
    feature = _branch(runtime, "feature", base=main)
    runtime.triage_service.decide(_decision(main))
    runtime.triage_service.decide(
        _decision(
            feature,
            state=DecisionState.WAIVED,
            reason="This branch is the one that removes it.",
        )
    )

    standings = runtime.triage_service.standings_for_branch(feature)

    assert standings[FINGERPRINT].state is DecisionState.WAIVED
    assert standings[FINGERPRINT].branch_id == feature
    assert (
        runtime.triage_service.standings_for_branch(main)[FINGERPRINT].state
        is DecisionState.ACCEPTED
    ), "reading through is not writing through: main is untouched"


def test_a_branch_with_no_base_answers_from_its_own_records_alone(
    runtime: Runtime,
) -> None:
    """The default branch, and any branch first seen before its base was ever indexed."""

    main = _branch(runtime, "main")
    orphan = _branch(runtime, "orphan")
    runtime.triage_service.decide(_decision(main))

    assert runtime.triage_service.standings_for_branch(orphan) == {}
    assert branch_chain(runtime.lineage_repository, orphan) == [orphan]


def test_the_chain_is_walked_furthest_first_so_the_nearest_opinion_governs(
    runtime: Runtime,
) -> None:
    """Three deep, which is a release branch off a develop branch off `main`."""

    main = _branch(runtime, "main")
    develop = _branch(runtime, "develop", base=main)
    release = _branch(runtime, "release", base=develop)
    runtime.triage_service.decide(_decision(main))
    runtime.triage_service.decide(_decision(develop, state=DecisionState.PARKED))
    runtime.triage_service.decide(
        _decision(main, boundary_fingerprint=OTHER, state=DecisionState.ACCEPTED)
    )

    assert branch_chain(runtime.lineage_repository, release) == [release, develop, main]
    standings = runtime.triage_service.standings_for_branch(release)
    assert standings[FINGERPRINT].state is DecisionState.PARKED, "the nearer branch answers"
    assert standings[OTHER].state is DecisionState.ACCEPTED, "and the furthest still reaches"


def test_a_cycle_in_the_chain_stops_rather_than_looping(runtime: Runtime) -> None:
    """No schema constraint can see this: it takes two separate writes to build.

    Stopping rather than refusing, because a read that raised would take a team's standings
    away over a row nobody can see — and everything reachable before the loop closed is
    still a true answer.
    """

    first = _branch(runtime, "first")
    second = _branch(runtime, "second", base=first)
    # Only reachable by writing the base of a branch that is already somebody's base.
    runtime.lineage_repository.set_base_branch(first, second)

    chain = branch_chain(runtime.lineage_repository, second)

    assert chain == [second, first]
    assert len(chain) <= MAX_BASE_DEPTH


def test_an_unknown_branch_reads_as_itself_rather_than_as_nothing(runtime: Runtime) -> None:
    """The first pull request against a fresh repository asks about a lineage no run has
    produced, and the honest answer is that nobody has decided anything — not that the read
    failed."""

    assert branch_chain(runtime.lineage_repository, "branch_nobody_has_seen") == [
        "branch_nobody_has_seen"
    ]
    assert runtime.triage_service.standings_for_branch("branch_nobody_has_seen") == {}
    assert runtime.triage_service.standings_for_branch(None) == {}


def test_a_branch_lineage_is_pointed_at_the_default_branch_when_both_exist(
    runtime: Runtime, tmp_path: Any
) -> None:
    """The lazy population a migration could not do, asserted through indexing.

    Order-independent on purpose: whichever of the two branches is indexed first, the feature
    branch ends up pointed at `main`, because the base is resolved every time the branch is
    written rather than only when its row is created.
    """

    import subprocess

    checkout = tmp_path / "repository"
    checkout.mkdir()
    (checkout / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    for arguments in (
        ("init", "--quiet", "-b", "main"),
        ("config", "user.email", "test@example.invalid"),
        ("config", "user.name", "Test"),
        ("add", "."),
        ("commit", "--quiet", "-m", "first"),
    ):
        subprocess.run(
            ["git", "-C", str(checkout), *arguments],
            check=True,
            capture_output=True,
            timeout=30,
        )

    on_main = runtime.repository_service.index(checkout)
    subprocess.run(
        ["git", "-C", str(checkout), "checkout", "--quiet", "-b", "feature"],
        check=True,
        capture_output=True,
        timeout=30,
    )
    on_feature = runtime.repository_service.index(checkout)

    assert on_main.branch_id is not None and on_feature.branch_id is not None
    stored = runtime.lineage_repository.get_branch(on_feature.branch_id)
    assert stored is not None
    assert stored.base_branch_id == on_main.branch_id
    main_lineage = runtime.lineage_repository.get_branch(on_main.branch_id)
    assert main_lineage is not None
    assert main_lineage.base_branch_id is None, "there is nothing behind the default branch"


def test_a_bulk_decision_records_one_decision_per_boundary_under_one_author(
    runtime: Runtime,
) -> None:
    """Adoption, through the endpoint that replaced bulk baselining.

    Forty rows, not one — each with the author, the date and the verdict it was taken against,
    and each appearing in the branch's standings exactly as a decision taken one at a time
    would. That is the whole difference from a baseline: the silence has a name behind it.
    """

    branch_id = _branch(runtime, "main")
    with TestClient(create_app(runtime)) as client:
        recorded = client.post(
            "/api/decisions/bulk",
            json={
                "branch_id": branch_id,
                "state": "accepted",
                "author": "Deniz",
                "review_id": "rev_1",
                "boundaries": [
                    {
                        "boundary_fingerprint": FINGERPRINT,
                        "boundary_reference": "BR-001",
                        "material": True,
                        "verdict_label": "Not earning its place",
                    },
                    {
                        "boundary_fingerprint": OTHER,
                        "boundary_reference": "BR-002",
                        "material": True,
                        "verdict_label": "Not earning its place",
                    },
                ],
            },
        )

    assert recorded.status_code == 201, recorded.text
    body = cast("dict[str, Any]", recorded.json())
    assert body["recorded"] == 2
    assert {item["boundary_fingerprint"] for item in body["decisions"]} == {
        FINGERPRINT,
        OTHER,
    }
    assert {item["author"] for item in body["decisions"]} == {"Deniz"}
    standings = runtime.triage_service.standings_for_branch(branch_id)
    assert set(standings) == {FINGERPRINT, OTHER}
    assert all(item.state is DecisionState.ACCEPTED for item in standings.values())
    assert all(
        len(runtime.triage_service.history(branch_id, key)) == 1 for key in standings
    ), "each boundary got one decision, not a shared bulk record"


def test_a_bulk_waiver_without_a_reason_is_refused_before_anything_is_written(
    runtime: Runtime,
) -> None:
    """The baseline coming back wearing an author's name is exactly what this refuses."""

    branch_id = _branch(runtime, "main")
    with TestClient(create_app(runtime)) as client:
        refused = client.post(
            "/api/decisions/bulk",
            json={
                "branch_id": branch_id,
                "state": "waived",
                "author": "Deniz",
                "review_id": "rev_1",
                "boundaries": [
                    {
                        "boundary_fingerprint": FINGERPRINT,
                        "boundary_reference": "BR-001",
                        "material": True,
                        "verdict_label": "Not earning its place",
                    }
                ],
            },
        )

    assert refused.status_code == 422, refused.text
    assert runtime.triage_service.standings_for_branch(branch_id) == {}


def test_a_bulk_decision_on_an_unknown_branch_writes_nothing(runtime: Runtime) -> None:
    """One transaction, and the branch check runs before it: a half-adopted branch would be
    indistinguishable from a team that worked through half the list."""

    with TestClient(create_app(runtime)) as client:
        refused = client.post(
            "/api/decisions/bulk",
            json={
                "branch_id": "branch_nobody_has_seen",
                "state": "accepted",
                "author": "Deniz",
                "review_id": "rev_1",
                "boundaries": [
                    {
                        "boundary_fingerprint": FINGERPRINT,
                        "boundary_reference": "BR-001",
                        "material": True,
                        "verdict_label": "Not earning its place",
                    }
                ],
            },
        )

    assert refused.status_code == 404, refused.text
    assert (
        runtime.triage_service.standings_for_branch("branch_nobody_has_seen") == {}
    )


def test_a_review_detail_carries_no_baseline_summary(runtime: Runtime) -> None:
    """The baseline is off the surface entirely, and its absence is asserted rather than
    assumed: a field that lingers in the schema is a field a page will go on drawing."""

    with TestClient(create_app(runtime)) as client:
        loaded = client.post(f"/api/examples/{FIXTURE}/load")
        assert loaded.status_code == 201, loaded.text
        root = loaded.json()["root_path"]
        started = client.post("/api/repositories/start", json={"root_path": root})
        assert started.status_code == 200, started.text
        created = client.post(
            "/api/reviews",
            json={"case_id": started.json()["case_id"], "repository_root": root},
        )
        assert created.status_code == 201, created.text
        detail = client.get(f"/api/reviews/{created.json()['review_id']}")
        assert detail.status_code == 200, detail.text
        body = cast("dict[str, Any]", detail.json())

        assert "baseline_summary" not in body
        assert body["boundary_triage"], "the standings join is what is left"
        reviewed = cast("list[dict[str, Any]]", body["report"]["reviewed"])
        assert reviewed
        assert all("disposition" not in item for item in reviewed)
        assert all("delta_state" in item for item in reviewed), (
            "the partition is what replaced it, and it is on the stored document"
        )

        # The routes are gone rather than refusing, which is the difference between a feature
        # withdrawn and a feature broken. The catch-all serves the frontend, so an unknown
        # `/api/...` path is a 404 from it.
        assert client.post(f"/api/reviews/{body['review_id']}/baseline").status_code == 404
        assert client.get(f"/api/branches/{body['branch_id']}/baseline").status_code == 404
