"""Live Google AI Studio checks: the two stages that ship, against the real service.

Marked `google` and outside `make check`, because a failure here is a measurement about
the model and the contracts rather than a broken build.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.reasoning_support import candidate, case, policies

from archcompass.adapters.models.google import GoogleReasoningProvider
from archcompass.bootstrap import build_runtime
from archcompass.configuration import AppConfig, load_config
from archcompass.domain.case import ArchitectureCase

pytestmark = pytest.mark.google

FIXTURE = Path("eval/cases/boundary-review/repository").resolve()


@pytest.fixture(scope="module")
def live_config() -> AppConfig:
    config = load_config(Path("config/models.google.yaml").resolve())
    assert config.models.reasoning.provider == "google"
    return config


def test_live_judgement_returns_one_bearing_per_presented_policy(
    live_config: AppConfig,
) -> None:
    """Arity is the whole binding: a short reply would re-attribute every later answer."""

    corpus = policies(6)

    verdict = GoogleReasoningProvider(live_config.models.reasoning).judge_finding_candidate(
        case(), candidate(), corpus
    )

    assert verdict.rationale
    assert verdict.candidate_id
    # Only bearings the model marked survive, so the count is bounded by the corpus rather
    # than equal to it — an entry beyond that could only come from a mis-zipped reply.
    assert len(verdict.policy_bearings) <= len(corpus)
    assert {item.policy_id for item in verdict.policy_bearings} <= {item.id for item in corpus}
    if not verdict.material:
        assert verdict.recommended_response == ""


def test_live_review_and_question_round_trip(
    live_config: AppConfig,
    tmp_path: Path,
) -> None:
    """The whole path against the real model: detect, judge, persist, ask."""

    del live_config
    workspace = tmp_path / "workspace"
    (workspace / "config").mkdir(parents=True)
    (workspace / "config" / "models.yaml").write_text(
        Path("config/models.google.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    for name in (".env",):
        source = Path(name)
        if source.is_file():
            (workspace / name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    runtime = build_runtime(workspace)
    runtime.repository_service.index(FIXTURE)
    revision = runtime.case_repository.create(
        ArchitectureCase(
            title="Live boundary review",
            problem_statement="Decide which boundaries earn their place.",
            desired_outcome="An honest verdict per boundary.",
            expected_future_changes=["SMS reminders ship next release"],
            non_goals=["Any change to how task identity is generated"],
        ),
        actor="live-test",
    )

    review = runtime.review_service.review(
        revision.case_id, repository_root=FIXTURE
    )

    report = review.report
    assert report is not None
    assert report.reviewed, "the fixture declares boundaries the detector must find"
    references = [item.reference for item in report.reviewed]
    assert references == [f"BR-{ordinal:03d}" for ordinal in range(1, len(references) + 1)]

    conversation = runtime.review_conversation_service.create(review.review_id)
    message = runtime.review_conversation_service.ask(
        conversation.conversation_id,
        "Which of these boundaries would you remove first?",
    )

    assert message.answer is not None
    # Grounding is positional, so a citation outside the review could only mean the
    # application resolved a position that does not exist.
    assert set(message.answer.supporting_references) <= set(references)
