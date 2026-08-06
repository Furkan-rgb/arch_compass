"""Background knowledge a review conversation is answered against.

Not evidence, and kept apart from it deliberately. The review says what was found in one
repository; this says what the review's words *mean* — what a boundary is, what the detector
cannot see, what a policy actually argues. Background can explain a verdict and can never
revise one, and an answer's citations are boundaries alone.

Presented whole, never retrieved or ranked, for the same reason the policy corpus is
presented whole to every candidate: the corpus is about 45,000 characters against an input
budget near 490,000, so it fits several times over, and ranking it would only introduce a
way to hide the passage that mattered. That is not a guess — an embedding index over this
corpus was built and measured, and it missed the primer's own "what the detector cannot see"
section when asked exactly that question. A retrieval step is worth its failure modes when
the evidence does not fit. Here it does.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from archcompass.domain.base import DomainModel
from archcompass.domain.policy import PolicyDocument


class MethodKnowledge(DomainModel):
    """Everything the advisor knows about its own method, in one value.

    Assembled by the application, like every other input to a reasoning stage: the model is
    handed what it may use rather than a handle it could resolve for itself.
    """

    #: The bundled primer, whole. Markdown as authored — it is read by a model, and the
    #: headings are what make its sections findable in a long prompt.
    method: str = Field(min_length=1)
    #: The corpus as prose to be asked about, rather than as lenses to judge with. The same
    #: documents the judging stage sees, in the same order, so an answer about "what this
    #: policy says" cannot describe a policy the review was never shown.
    policies: list[PolicyDocument] = Field(default_factory=list[PolicyDocument])
    #: Why the corpus is missing, in one sentence, when it is. An empty `policies` on its
    #: own reads as "this workspace has no policies", and a stage told that would answer
    #: policy questions with a confident nothing; a corpus that could not be *read* is a
    #: different fact and the stage must be able to say which one it was handed.
    policy_corpus_unavailable: str = ""

    @model_validator(mode="after")
    def a_reason_stands_in_for_the_corpus_it_explains(self) -> MethodKnowledge:
        if self.policy_corpus_unavailable and self.policies:
            raise ValueError(
                "A reason the corpus is unavailable cannot sit beside a served corpus"
            )
        return self
