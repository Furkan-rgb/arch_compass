from __future__ import annotations

import ast
from pathlib import Path

import pytest

from archcompass.application.core_defaults import DeterministicRevisionCalculator
from archcompass.domain import (
    Answer,
    AnswerStatus,
    ArchitectureCase,
    Candidate,
    CaseFacet,
    ChangeCause,
    Finding,
    Participant,
    Question,
    RepositoryAtlas,
    RepositoryRef,
    RetrievalProvenance,
    Review,
    ReviewDelta,
    ReviewStatus,
    Verdict,
)
from archcompass.domain._support import utc_now


def test_case_revision_is_immutable_and_records_an_answer() -> None:
    original = ArchitectureCase.create("Keep changes local")
    question = Question.create(
        text="Is another provider planned?",
        facet=CaseFacet.EXPECTED_CHANGE,
        candidate_ids=("candidate_b", "candidate_a"),
        round=1,
    )
    answer = Answer(question, AnswerStatus.ANSWERED, "No", "reader", utc_now())

    revised = original.with_answer(answer)

    assert original.answers == ()
    assert revised.revision == original.revision + 1
    assert revised.answers == (answer,)
    assert question.candidate_ids == ("candidate_a", "candidate_b")


def test_one_clarification_submission_creates_one_revision() -> None:
    original = ArchitectureCase.create("Keep ownership explicit")
    first = Question.create(
        text="Who owns the boundary?",
        facet=CaseFacet.DECISION,
        candidate_ids=("candidate-1",),
        round=1,
    )
    second = Question.create(
        text="Is latency constrained?",
        facet=CaseFacet.CONSTRAINT,
        candidate_ids=("candidate-2",),
        round=1,
    )

    revised = original.with_answers(
        (
            Answer(first, AnswerStatus.ANSWERED, "Platform", "user", utc_now()),
            Answer(second, AnswerStatus.SKIPPED, None, "user", utc_now()),
        )
    )

    assert revised.revision == original.revision + 1
    assert len(revised.answers) == 2


def test_skipped_answer_carries_no_invented_value() -> None:
    question = Question.create(
        text="Who owns this?",
        facet=CaseFacet.DECISION,
        candidate_ids=("candidate_a",),
        round=1,
    )
    skipped = Answer(question, AnswerStatus.SKIPPED, None, "reader", utc_now())
    assert skipped.value is None
    with pytest.raises(ValueError, match="cannot have a value"):
        Answer(question, AnswerStatus.SKIPPED, "unknown", "reader", utc_now())


def test_domain_has_no_infrastructure_imports() -> None:
    root = Path(__file__).parents[2] / "src" / "archcompass" / "domain"
    forbidden = {"pydantic", "langchain", "langgraph", "fastapi", "google", "ollama"}
    for source in root.glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imported = {
            node.module.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        } | {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        assert imported.isdisjoint(forbidden), source


def test_finding_with_hinge_cannot_recommend_a_response() -> None:
    candidate = Candidate.identified(
        pattern="dependency_direction",
        summary="Ownership is unclear",
        participants=(Participant("domain.order", "source"),),
    )

    with pytest.raises(ValueError, match="uncertainty hinge"):
        Finding(
            candidate,
            Verdict.MATERIAL,
            "The answer could change the verdict.",
            (),
            (),
            hinge="the owning team",
            recommended_response="Move the module.",
        )


def test_revision_calculator_rejudges_for_policy_model_and_prompt_changes(
    tmp_path: Path,
) -> None:
    repository = RepositoryRef("repo", tmp_path, "branch", "content")
    atlas = RepositoryAtlas("atlas", repository)
    case = ArchitectureCase.create("Keep dependencies inward")
    candidate = Candidate.identified(
        pattern="dependency_direction",
        summary="Domain imports an adapter",
        participants=(Participant("domain.order", "source"),),
    )
    finding = Finding(candidate, Verdict.CLEARED, "No conflict was found.", (), ())
    now = utc_now()
    previous = Review(
        "review-1",
        1,
        repository,
        atlas,
        case,
        (finding,),
        (),
        ReviewStatus.COMPLETED,
        ReviewDelta(new=(candidate,)),
        now,
        now,
        retrieval_manifest=(
            RetrievalProvenance(
                candidate.id,
                "any-strategy",
                "1",
                "old-corpus",
                ("policy-a",),
            ),
        ),
        model_identity="old-model",
        prompt_identity="old-prompt",
    )
    calculator = DeterministicRevisionCalculator(
        corpus_fingerprint=lambda _: "new-corpus",
        model_identity=lambda: "new-model",
        prompt_identity=lambda: "new-prompt",
    )

    delta = calculator.calculate((candidate,), case, previous, repository)

    assert delta.changed[0].causes == (
        ChangeCause.POLICIES,
        ChangeCause.MODEL,
        ChangeCause.PROMPT,
    )


def test_revision_calculator_records_succession_and_resurfacing(tmp_path: Path) -> None:
    repository = RepositoryRef("repo", tmp_path, "branch", "content")
    atlas = RepositoryAtlas("atlas", repository)
    case = ArchitectureCase.create("Keep dependencies inward")
    predecessor = Candidate.identified(
        pattern="dependency_direction",
        summary="Old boundary",
        participants=(Participant("old.Port", "source"),),
    )
    successor = Candidate.identified(
        pattern="dependency_direction",
        summary="Renamed boundary",
        participants=(Participant("new.Port", "source"),),
    )
    resurfaced = Candidate.identified(
        pattern="sole_implementation",
        summary="Port returned",
        participants=(Participant("Port", "interface"),),
    )
    now = utc_now()

    def review(review_id: str, sequence: int, candidate: Candidate) -> Review:
        return Review(
            review_id,
            sequence,
            repository,
            atlas,
            case,
            (Finding(candidate, Verdict.CLEARED, "Cleared.", (), ()),),
            (),
            ReviewStatus.COMPLETED,
            ReviewDelta(new=(candidate,)),
            now,
            now,
        )

    older = review("older", 1, resurfaced)
    previous = review("previous", 2, predecessor)

    delta = DeterministicRevisionCalculator().calculate(
        (successor, resurfaced), case, previous, repository, (previous, older)
    )

    changes = {str(item.candidate.id): item for item in delta.changed}
    assert changes[str(successor.id)].predecessor_id == predecessor.id
    assert changes[str(successor.id)].causes == (ChangeCause.SHAPE,)
    assert changes[str(resurfaced.id)].causes == (ChangeCause.RESURFACED,)
    assert delta.addressed == ()
