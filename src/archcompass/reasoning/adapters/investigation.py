"""The second look a hinged finding gets, and what it is allowed to change.

A judgement that stopped to ask a person is handed a toolbox and asked one question: is this
something the repository already answers? What comes back may settle the verdict or narrow
the question, and may touch nothing else — the verdict it reaches is about a candidate the
application chose, against policies it was already shown.
"""

from __future__ import annotations

from dataclasses import replace

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field, model_validator

from archcompass.domain import (
    ArchitectureCase,
    Finding,
    RepositoryAtlas,
    RepositoryRef,
    Verdict,
)
from archcompass.ports.capabilities import InvestigatedFinding
from archcompass.ports.investigation import InvestigatorSource, SourceInvestigator
from archcompass.reasoning.adapters.langchain import (
    candidate_text,
    case_text,
    structured_output,
)
from archcompass.reasoning.adapters.tool_loop import (
    investigate_with_tools,
    recorded_investigation,
)

HINGE_CONTRACT = (
    "You judged this candidate and stopped, because your verdict turned on something the "
    "evidence you were shown does not say. You now have read-only lookups into the same "
    "repository. Use them to find out whether the question you were going to put to a "
    "person is one the repository already answers.\n\n"
    "Start with find_code on a qualified name from the candidate; every other lookup needs "
    "an id it returns. Ask what implements, depends on, calls or tests the thing you are "
    "judging — those settle most hinges. Read the code only where the structure does not "
    "settle it.\n\n"
    "Then say whether the hinge is settled. Settling it is not the goal: 'I checked and the "
    "repository is silent on this' is as useful an answer as one that resolves, and a "
    "confident wrong answer is worth less than an honest question. If the lookups changed "
    "what is actually unknown, say so as a narrower question rather than the original one."
)


class HingeResolutionOutput(BaseModel):
    """What the lookups established, and whether they settled the question.

    The verdict and the policy bearings are deliberately absent. This pass is never shown a
    numbered policy list, so there is no position it could cite and nothing to validate —
    a bearing cannot be added, moved or invented because there is nothing to move. What it
    may settle is one thing: whether the question was worth a person's interruption.
    """

    resolved: bool
    #: What the lookups established, required either way. "Checked, and the repository is
    #: silent" is as much a finding as an answer, and the two are opposite facts about the
    #: question underneath.
    findings: str = Field(min_length=1)
    material: bool | None = None
    reasoning: str | None = None
    recommended_response: str | None = None
    #: A narrower hinge, where the lookups changed what is actually unknown. Empty leaves
    #: the original standing.
    hinge: str | None = None

    @model_validator(mode="after")
    def a_resolution_settles_the_verdict(self) -> HingeResolutionOutput:
        if self.resolved:
            if self.material is None or not (self.reasoning or "").strip():
                raise ValueError("a resolved hinge must state a verdict and its reasoning")
            if self.hinge:
                raise ValueError("a resolved hinge is not still hinged")
        elif self.material is not None or self.recommended_response:
            raise ValueError("an unresolved hinge settles nothing and recommends nothing")
        if self.recommended_response and not self.material:
            raise ValueError("only a material finding may recommend a response")
        return self


def resolution_prompt(
    finding: Finding, case: ArchitectureCase, transcript: str = ""
) -> str:
    """The finding put back to the model that reached it, with whatever it has looked up.

    The same text opens the investigation and closes it. Opening with it means the model
    chooses lookups against exactly the finding it will afterwards be asked to settle;
    closing with it means what it answers from is the record a reader will be shown.

    It carries no contract of its own. The loop sends `HINGE_CONTRACT` as a system message
    and the structured call prepends it, so putting it here too would state the rules twice
    on the opening turn.
    """

    bearings = "\n".join(
        f"- '{item.policy.title}' ({item.policy.strength.value}): {item.reasoning}"
        for item in finding.policies
    )
    return "\n\n".join(
        (
            f"CASE\n{case_text(case)}",
            f"CANDIDATE\n{candidate_text(finding.candidate)}",
            f"YOUR REASONING\n{finding.reasoning}",
            f"WHAT YOUR VERDICT TURNS ON\n{finding.hinge}",
            *(("POLICIES YOU FOUND IT BEARS ON\n" + bearings,) if bearings else ()),
            # Omitted rather than empty on the opening turn: telling a model it looked
            # nothing up before it has had the chance reads as an instruction not to.
            *((f"WHAT YOU LOOKED UP\n{transcript}",) if transcript else ()),
        )
    )


class LangChainHingeInvestigator:
    """One bounded conversation per hinge, then one structured call to conclude it."""

    def __init__(
        self,
        model: BaseChatModel,
        investigators: InvestigatorSource,
        *,
        model_identity: str = "",
    ) -> None:
        self._model = model
        self._investigators = investigators
        self._model_identity = model_identity

    def supports_tools(self) -> bool:
        return True

    def investigate(
        self,
        finding: Finding,
        case: ArchitectureCase,
        *,
        repository: RepositoryRef,
        atlas: RepositoryAtlas,
    ) -> InvestigatedFinding:
        if finding.verdict is not Verdict.HELD or not finding.hinge:
            raise ValueError("only a held finding with a hinge can be investigated")
        offered = self._investigators.for_review(repository, atlas)
        if offered.investigator is None:
            return InvestigatedFinding(
                finding,
                recorded_investigation(
                    None,
                    candidate_id=str(finding.candidate.id),
                    withheld=offered.withheld,
                    atlas_fingerprint=repository.content_id,
                    model_identity=self._model_identity,
                ),
            )
        transcript = investigate_with_tools(
            self._model,
            offered.investigator,
            system=HINGE_CONTRACT,
            opening=resolution_prompt(finding, case),
            subject=f"the hinge on {finding.candidate.summary}",
        )
        output = structured_output(
            self._model,
            HingeResolutionOutput,
            f"{HINGE_CONTRACT}\n\n{resolution_prompt(finding, case, transcript)}",
            subject="a hinge resolution",
            model_identity=self._model_identity,
        )
        return self._apply(
            finding, output, offered.investigator, repository=repository
        )

    def _apply(
        self,
        finding: Finding,
        output: HingeResolutionOutput,
        investigator: SourceInvestigator,
        *,
        repository: RepositoryRef,
    ) -> InvestigatedFinding:
        record = recorded_investigation(
            investigator,
            candidate_id=str(finding.candidate.id),
            resolved=output.resolved,
            atlas_fingerprint=repository.content_id,
            model_identity=self._model_identity,
        )
        identity = "" if record is None else record.identity
        if not output.resolved:
            # A narrowed hinge is still a hinge, and the question generator reads nothing
            # else — so this is a strictly better question reaching the same person.
            return InvestigatedFinding(
                replace(
                    finding,
                    hinge=(output.hinge or finding.hinge),
                    investigation_identity=identity,
                ),
                record,
            )
        # `replace` is the mechanism, not the idiom: every field not named here is carried
        # untouched, so "may not change" is the default and this list is the whole licence.
        # `verdict` moves only out of HELD, which is the only state this pass ever sees.
        return InvestigatedFinding(
            replace(
                finding,
                verdict=Verdict.MATERIAL if output.material else Verdict.CLEARED,
                reasoning=output.reasoning or finding.reasoning,
                hinge=None,
                recommended_response=(
                    output.recommended_response if output.material else None
                ),
                investigation_identity=identity,
            ),
            record,
        )
