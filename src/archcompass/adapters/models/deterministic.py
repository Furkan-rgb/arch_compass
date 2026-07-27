"""Deterministic model substitutes for tests and reproducible evaluations."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from hashlib import sha256
from typing import ClassVar

from archcompass.domain.atlas import (
    FindingCandidate,
)
from archcompass.domain.case import (
    ArchitectureCase,
)
from archcompass.domain.knowledge import MethodKnowledge
from archcompass.domain.policy import PolicyDocument
from archcompass.domain.review import (
    BoundaryReview,
    CandidateVerdict,
    OverviewStatement,
    PolicyBearing,
    ReviewedBoundary,
    ReviewOverview,
)
from archcompass.domain.review_conversation import ReviewAnswer, ReviewMessage
from archcompass.ports.reasoning import ReasoningTask


class DeterministicEmbeddingProvider:
    def __init__(self, dimensions: int = 64) -> None:
        self._dimensions = dimensions

    @property
    def identity(self) -> tuple[str, str, int]:
        return ("fake", "deterministic-token-hash-v1", self._dimensions)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        tokens = re.findall(r"[a-z0-9-]+", text.casefold())
        for token in tokens:
            digest = sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimensions
            vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0
        magnitude = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / magnitude for value in vector]


class DeterministicReasoningProvider:
    _PROMPTS: ClassVar[dict[ReasoningTask, str]] = {
        ReasoningTask.JUDGE_FINDING_CANDIDATE: "judge-finding-candidate:v3",
        ReasoningTask.SUMMARISE_REVIEW: "summarise-review:v2",
        ReasoningTask.ANSWER_REVIEW_QUESTION: "answer-review-question:v1",
    }

    @property
    def model_identity(self) -> str:
        return "fake:deterministic-architecture-v3"

    def prompt_identity(self, task: ReasoningTask) -> str:
        return self._PROMPTS[task]

    def judge_finding_candidate(
        self,
        case: ArchitectureCase,
        candidate: FindingCandidate,
        policies: list[PolicyDocument],
    ) -> CandidateVerdict:
        del case
        # The one call a substitute can make from the measurements alone: indirection
        # that nothing depends on is in front of nothing. Every other candidate is
        # reported as fine, which is both the honest default here and the answer a real
        # model should give most of the time.
        dependants = next(
            (
                item.value
                for item in candidate.measurements
                if item.name == "dependants_of_abstraction"
            ),
            None,
        )
        material = dependants == 0
        # Bearing is derived from the candidate's own pattern words against each policy's
        # title and tags. Recognising particular policy IDs would make the substitute a
        # function of the bundled corpus rather than of its inputs.
        words = {word for word in candidate.pattern.value.split("_") if len(word) > 3}
        bearings = [
            PolicyBearing(
                policy_id=policy.id,
                policy_title=policy.title,
                how=(
                    f"{policy.title} names the same shape this candidate reports: "
                    f"{candidate.summary}"
                ),
            )
            for policy in policies
            if any(word in " ".join([policy.title, *policy.tags]).lower() for word in words)
        ]
        return CandidateVerdict(
            candidate_id=candidate.candidate_id,
            material=material,
            rationale=(
                (
                    "Nothing in this snapshot depends on the abstraction, so the boundary "
                    "currently sits in front of a single concrete implementation with no "
                    "caller reading the contract."
                )
                if material
                else (
                    f"{dependants if dependants is not None else 'Several'} references reach "
                    "the abstraction, so the boundary is load-bearing here and the "
                    "implementation count alone does not establish a problem."
                )
            ),
            policy_bearings=bearings,
            recommended_response=(
                "Name the concrete implementation directly until a second one exists."
                if material
                else ""
            ),
        )

    def summarise_review(
        self,
        case: ArchitectureCase,
        boundaries: list[ReviewedBoundary],
    ) -> ReviewOverview:
        # Composed from the verdicts themselves, so the substitute cites boundaries that
        # genuinely carry what each statement says. A fixture that always cited everything
        # would make the grounding assertions in tests vacuous.
        material = [item for item in boundaries if item.material]
        cleared = [item for item in boundaries if not item.material]
        themes: list[OverviewStatement] = []
        if material:
            themes.append(
                OverviewStatement(
                    text=(
                        f"{len(material)} of {len(boundaries)} were found not to be "
                        "earning their place."
                    ),
                    supporting_references=[item.reference for item in material],
                )
            )
        if cleared:
            themes.append(
                OverviewStatement(
                    text=(
                        f"{len(cleared)} of {len(boundaries)} were found to be earning "
                        "their place."
                    ),
                    supporting_references=[item.reference for item in cleared],
                )
            )
        # Relayed from the candidates rather than described here: the detector states what
        # it could not see, and a double that restated it in its own words would be
        # asserting the detector's vocabulary instead of passing it through.
        stated: list[str] = []
        for item in boundaries:
            if item.candidate.limitations and item.candidate.limitations not in stated:
                stated.append(item.candidate.limitations)
        return ReviewOverview(
            situation=(
                f"{case.title}. {case.problem_statement}"
                if case.problem_statement
                else case.title
            ),
            themes=themes,
            recommended_sequence=[
                OverviewStatement(
                    text=material[0].recommended_response,
                    supporting_references=[item.reference for item in material],
                )
            ]
            if material and material[0].recommended_response
            else [],
            limits=" ".join(stated) or "The detector stated no limitation.",
        )

    def stream_review_answer(
        self,
        review: BoundaryReview,
        history: list[ReviewMessage],
        question: str,
        knowledge: MethodKnowledge,
        on_prose: Callable[[str], None],
    ) -> ReviewAnswer:
        """The same answer, handed over a word at a time.

        Implemented here so the streaming path has something to run against without a live
        model: the route, the application service and the browser all behave as they do
        against a real provider, and the assertion that a preview never becomes the stored
        record is checkable offline.

        Split on whitespace rather than by characters or tokens. A fragment boundary is
        arbitrary in every real transport too, and words make a test's expectations readable
        without pretending to imitate how any particular provider chunks its output.
        """

        answer = self.answer_review_question(review, history, question, knowledge)
        for index, word in enumerate(answer.answer.split(" ")):
            on_prose(word if index == 0 else f" {word}")
        return answer

    def answer_review_question(
        self,
        review: BoundaryReview,
        history: list[ReviewMessage],
        question: str,
        knowledge: MethodKnowledge,
    ) -> ReviewAnswer:
        report = review.report
        if report is None:
            raise ValueError("A review without a report cannot be questioned")
        # Grounded on whichever boundaries share a word with the question, which is a
        # function of the inputs rather than of a fixture. A substitute that always cited
        # everything would make the grounding assertions in tests vacuous.
        words = {word for word in re.findall(r"[a-z0-9]+", question.casefold()) if len(word) > 3}
        supporting = [
            item
            for item in report.reviewed
            if words & set(re.findall(r"[a-z0-9]+", item.candidate.summary.casefold()))
        ]
        # The background is counted but never cited. Counting it makes the wiring
        # observable — a test can prove the whole corpus reached this stage — while leaving
        # `supporting_references` boundaries-only, which is the rule the real stage obeys.
        consulted = (
            f" Background consulted: the method primer and {len(knowledge.policies)} "
            "policies, whole."
            if knowledge.method
            else ""
        )
        return ReviewAnswer(
            answer=(
                f"{report.headline} "
                + (
                    "The boundaries this question touches are: "
                    + "; ".join(item.candidate.summary for item in supporting)
                    if supporting
                    else "This review does not cover what the question asks about."
                )
                + consulted
                + f" (turn {len(history) + 1})"
            ),
            supporting_references=[item.reference for item in supporting],
        )
