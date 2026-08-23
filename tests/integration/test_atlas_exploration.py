"""Every question the map can put to the atlas, asked over HTTP.

There were no tests here at all. Twelve operations, reachable only through this one route,
and the sole thing binding the request model's spelling of them to the query records' was
that a rename would have to be made in both places — which is exactly what had already gone
wrong: the route carried a dictionary translating `shortest_path` into
`shortest_dependency_path`, and the frontend held a third list in the route's vocabulary.
The generated client and `tsc` now catch a name that drifts. Nothing caught an operation
that stopped *answering*.

So this asks all twelve of a real atlas and checks each gives back the shape its own kind
implies, rather than asserting on particular nodes: the point is that the wiring holds, not
that `warehouse-sync` has a specific import in it. The two failure modes a rename actually
produces — an operation dispatched to the wrong query, and one whose required arguments the
validator does not require — are what the parametrised cases below are shaped around.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from archcompass.bootstrap import Runtime
from archcompass.presentation.web.app import create_app

#: Every operation the request model accepts, with what it takes and what it comes back as.
#: Kept as data rather than as twelve test bodies because the assertion is the same each
#: time; `test_the_route_asks_about_every_operation_the_request_model_accepts` is what stops
#: this list drifting out of step with the model, so a thirteenth operation cannot arrive
#: untested.
_NODE_ANCHORED = (
    "subsystem_summary",
    "direct_dependencies",
    "direct_dependants",
    "known_callers",
    "implementations",
    "related_tests",
    "forward_neighbourhood",
    "reverse_neighbourhood",
)
_WHOLE_ATLAS = ("search_nodes", "cyclic_components", "signals")


@pytest.fixture
def explored(runtime: Runtime):  # type: ignore[no-untyped-def]
    """A client, an analysed repository, and the nodes of its atlas to ask about.

    Seeded through `search_nodes` because there is no route that hands back a whole atlas —
    the map is always a bounded answer to a question. One term rather than several: terms are
    conjunctive, so a list of every package name in the example matches nothing at all.
    """

    repository = str(Path("examples/cases/warehouse-sync/repository").resolve())
    with TestClient(create_app(runtime)) as client:
        started = client.post("/api/repositories/start", json={"root_path": repository})
        assert started.status_code == 200, started.text
        found = client.post(
            "/api/repositories/explore",
            json={
                "root_path": repository,
                "operation": "search_nodes",
                "terms": ["storage"],
                "limit": 60,
            },
        )
        assert found.status_code == 200, found.text
        nodes = found.json()["node_ids"]
        assert len(nodes) >= 2, "the example repository stopped producing an atlas"
        yield client, repository, nodes


def test_every_node_anchored_operation_answers_about_the_node_it_was_asked_about(
    explored,  # type: ignore[no-untyped-def]
) -> None:
    client, repository, nodes = explored
    for operation in _NODE_ANCHORED:
        node_id = nodes[0]
        response = client.post(
            "/api/repositories/explore",
            json={"root_path": repository, "operation": operation, "node_id": node_id, "limit": 20},
        )
        assert response.status_code == 200, f"{operation}: {response.text}"
        answer = response.json()
        # The echo is what proves the dispatch: two operations mapped onto one query would
        # come back naming the same kind, and every one of these has its own.
        assert answer["query"]["kind"] == operation, f"{operation} answered as another query"
        assert node_id in answer["node_ids"] or not answer["node_ids"], (
            f"{operation} answered about elements that do not include the one asked about"
        )


def test_the_two_neighbourhoods_are_not_the_same_question(explored) -> None:  # type: ignore[no-untyped-def]
    """The one pair that shares a query record, and so the one that can silently collapse.

    `forward_neighbourhood` and `reverse_neighbourhood` both build a `NeighbourhoodQuery`
    and differ only by the `direction` the route passes. A rename that dropped the direction
    would leave both operations working, both echoing their own kind, and both answering the
    same thing — which no other assertion in this file would notice.
    """

    client, repository, nodes = explored
    # A node with dependencies in one direction only is what tells the two apart; the first
    # node that is not isolated will do, and the atlas is ordered so one exists.
    for node in nodes:
        answers = {
            direction: client.post(
                "/api/repositories/explore",
                json={
                    "root_path": repository,
                    "operation": direction,
                    "node_id": node,
                    "depth": 2,
                    "limit": 40,
                },
            ).json()
            for direction in ("forward_neighbourhood", "reverse_neighbourhood")
        }
        forward = set(answers["forward_neighbourhood"]["node_ids"])
        reverse = set(answers["reverse_neighbourhood"]["node_ids"])
        if forward != reverse:
            return
    raise AssertionError(
        "no node in this atlas has a different forward and reverse neighbourhood, so the "
        "direction the route passes is untested"
    )


def test_the_whole_atlas_operations_need_no_node(explored) -> None:  # type: ignore[no-untyped-def]
    client, repository, _ = explored
    for operation in _WHOLE_ATLAS:
        body: dict[str, Any] = {"root_path": repository, "operation": operation, "limit": 20}
        if operation == "search_nodes":
            body["terms"] = ["warehouse"]
        response = client.post("/api/repositories/explore", json=body)
        assert response.status_code == 200, f"{operation}: {response.text}"
        assert response.json()["query"]["kind"] == operation


def test_shortest_dependency_path_takes_two_nodes(explored) -> None:  # type: ignore[no-untyped-def]
    client, repository, nodes = explored
    response = client.post(
        "/api/repositories/explore",
        json={
            "root_path": repository,
            "operation": "shortest_dependency_path",
            "node_id": nodes[0],
            "target_id": nodes[1],
            "limit": 40,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["query"]["kind"] == "shortest_dependency_path"


@pytest.mark.parametrize(
    ("body", "missing"),
    [
        ({"operation": "direct_dependencies"}, "node_id"),
        ({"operation": "subsystem_summary"}, "node_id"),
        ({"operation": "forward_neighbourhood"}, "node_id"),
        ({"operation": "shortest_dependency_path", "node_id": "x"}, "target_id"),
        ({"operation": "search_nodes"}, "terms"),
    ],
)
def test_an_operation_missing_its_argument_is_refused_rather_than_crashed(
    explored,  # type: ignore[no-untyped-def]
    body: dict[str, Any],
    missing: str,
) -> None:
    """422, not 500. A validator gap here is a `None` dereferenced inside the query service."""

    client, repository, _ = explored
    response = client.post(
        "/api/repositories/explore", json={"root_path": repository, **body, "limit": 20}
    )
    assert response.status_code == 422, f"{body} was accepted without {missing}: {response.text}"


def test_an_unknown_operation_is_refused(explored) -> None:  # type: ignore[no-untyped-def]
    """Including the names this route used to answer to, which are now nobody's vocabulary."""

    client, repository, nodes = explored
    for retired in ("shortest_path", "cycles", "search", "children", "callers", "dependants"):
        response = client.post(
            "/api/repositories/explore",
            json={
                "root_path": repository,
                "operation": retired,
                "node_id": nodes[0],
                "limit": 20,
            },
        )
        assert response.status_code == 422, f"the route still answers to {retired!r}"


def test_the_route_asks_about_every_operation_the_request_model_accepts() -> None:
    """The lists above are the request model's own, or the coverage above is a subset.

    Read off the model rather than written out, because a thirteenth operation added to the
    Literal and to the dispatch would otherwise be a thirteenth operation nothing here asks
    about — and the whole reason this file exists is that exactly that had happened.
    """

    from typing import get_args

    from archcompass.presentation.web.routes.repositories import AtlasExploreRequest

    declared = set(get_args(AtlasExploreRequest.model_fields["operation"].annotation))
    covered = {*_NODE_ANCHORED, *_WHOLE_ATLAS, "shortest_dependency_path"}
    assert declared == covered, f"untested operations: {sorted(declared ^ covered)}"
