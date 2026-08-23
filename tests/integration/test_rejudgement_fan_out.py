"""Every candidate a clarification round re-judges keeps the verdict it was re-judged to.

This is one bug's regression test, and the bug is worth stating because nothing about the
shape of it is obvious.

`review_candidate` is fanned out with `Send`, and the payload used to be the whole state —
including `findings`, which by round two holds round one's verdict for every candidate. The
candidate subgraph declares an output schema, and that schema projects the subgraph's *final
merged state* rather than the writes its nodes made: so each branch handed back every
finding it had been given, plus its own. `merge_mappings` applies those returns in task
order, and every branch but the last therefore had its fresh verdict overwritten by a
sibling's copy of the stale one.

Two things hid it. The hinge pass runs immediately afterwards and re-judges exactly the
findings that reverted, so with the lookups on — the default — the round came out right.
(`rejudge_investigated` is what re-judges now; `investigate_hinges` only records lookups.)
And every graph test in the suite judges a single candidate, which is the one case where a
branch has no sibling to be overwritten by.

So this test needs a repository with several candidates, a round of answers, and the
lookups off. It uses the deterministic provider, whose judge holds every candidate while the
case has no answers and clears it once anything has been answered — which makes "did the
re-judgement survive" a question with a yes-or-no answer rather than a matter of prose.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from archcompass.bootstrap import build_runtime, pinned_model
from archcompass.presentation.web.app import create_app
from archcompass.reasoning.adapters.providers import DETERMINISTIC_MODEL

#: Six boundaries with one implementation each. The count is the point — one candidate
#: cannot show this, and the detectors have to produce more than one from the same run.
REPOSITORY = Path("examples/cases/boundary-review/repository")


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARCHCOMPASS_PROVIDERS", "fake")
    # Off, and this is the load-bearing line. With the lookups on, the node after the
    # fan-out re-judges every finding that reverted and the bug is invisible — which is
    # exactly how it survived. This test has to see the fan-out's own output.
    monkeypatch.setenv("ARCHCOMPASS_HINGE_INVESTIGATION", "0")
    runtime = build_runtime(tmp_path, pin=pinned_model("fake", DETERMINISTIC_MODEL))
    return TestClient(create_app(runtime))


def test_a_clarification_round_rejudges_every_candidate_and_keeps_every_verdict(
    workspace: TestClient,
) -> None:
    repository = str(REPOSITORY.resolve())
    started = workspace.post("/api/repositories/start", json={"root_path": repository})
    assert started.status_code == 200, started.text

    first = workspace.post(
        "/api/reviews",
        json={"case_id": started.json()["case_id"], "repository_root": repository},
    )
    assert first.status_code == 201, first.text
    waiting = first.json()

    assert waiting["status"] == "awaiting_answers"
    assert len(waiting["findings"]) > 1, (
        "one candidate cannot show this: a branch needs a sibling to be overwritten by"
    )
    assert {finding["verdict"] for finding in waiting["findings"]} == {"held"}

    answered = workspace.post(
        f"/api/reviews/{waiting['id']}/answers",
        json={
            "answers": [
                {
                    "question_id": question["id"],
                    "status": "answered",
                    "value": question["options"][0] if question["options"] else "Yes.",
                    "actor": "architect",
                }
                for question in waiting["questions"]
            ],
            "stop": False,
        },
    )
    assert answered.status_code == 200, answered.text
    rejudged = answered.json()

    # The verdicts before the status, because they are the cause and it is the symptom: a
    # reverted finding is still held, still hinged, and asks its question again — so the
    # first thing a reader of a failure sees should be which candidates lost their
    # re-judgement, not that the review did not finish.
    verdicts = {
        finding["candidate"]["id"]: finding["verdict"] for finding in rejudged["findings"]
    }
    assert verdicts.keys() == {
        finding["candidate"]["id"] for finding in waiting["findings"]
    }, "the round changed which candidates exist"
    reverted = sorted(
        candidate_id for candidate_id, verdict in verdicts.items() if verdict == "held"
    )
    assert not reverted, (
        f"{len(reverted)} of {len(verdicts)} candidates came back with the verdict they "
        "had before the answers, so the fan-out returned a stale copy over the "
        f"re-judgement: {reverted}"
    )
    assert rejudged["status"] == "completed"
