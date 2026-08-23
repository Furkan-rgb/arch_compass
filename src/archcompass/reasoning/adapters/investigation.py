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
from archcompass.reasoning.adapters.langchain import (
    candidate_text,
    case_text,
    structured_output,
)
from archcompass.reasoning.adapters.tool_loop import (
    investigate_with_tools,
    recorded_investigation,
)
from archcompass.reasoning.ports import InvestigatorSource, SourceInvestigator

HINGE_CONTRACT = (
    "You judged this candidate and stopped, because your verdict turned on something the "
    "evidence you were shown does not say. You now have read-only lookups into the same "
    "repository. Use them to find out whether the question you were going to put to a "
    "person is one the repository already answers.\n\n"
    "The lookups take qualified names, and the candidate you are judging already names "
    "everything you need. Ask what implements, depends on, calls or tests it — those settle "
    "most hinges. Read the code only where the structure does not settle it, and search only "
    "when you do not already know a name.\n\n"
    "Then say whether the hinge is settled. Settling it is not the goal: 'I checked and the "
    "repository is silent on this' is as useful an answer as one that resolves, and a "
    "confident wrong answer is worth less than an honest question. If the lookups changed "
    "what is actually unknown, say so as a narrower question rather than the original one."
    "\n\n"
    # Stated out loud because `HingeResolutionOutput` enforces it and a JSON schema cannot
    # express it. Left unsaid, a model that had settled the question answered `resolved`
    # with what it had found and nothing else — well-formed JSON, refused by the validator,
    # and the whole investigation thrown away by the node that catches everything. The
    # judgement contract has always spelled its own cross-field rules out for the same
    # reason; this one had not.
    "Say what the lookups established either way. Settling the hinge means giving the "
    "verdict yourself: say whether the finding is material and why, and recommend a "
    "response only if it is material. If the lookups settled nothing, say so by leaving the "
    "verdict null and the reasoning empty, and give the narrower question instead. Give a "
    "verdict or a narrower question, never both: a question means it is not settled, and it "
    "is the question that will be put to a person."
)


# Why there is no `resolved` flag, kept out of the docstring on purpose.
#
# Pydantic puts a class docstring into `model_json_schema()["description"]`, and the Google
# adapter forwards that to the model as documentation for the schema it must honour. So
# every sentence here would be sent, on every hinge call, as guidance — and a paragraph
# describing a field the model must not emit is the last thing to hand it.
#
# There was a `resolved: bool`. A model answering under a constrained grammar would set it
# true and then simply stop after `findings`: every field a resolution needs was optional,
# so omitting them satisfied the JSON schema and failed the cross-field rule underneath it,
# and the whole investigation was thrown away. Stating the rule in the contract did not fix
# it and neither did quoting the violation back; what fixed it was not offering the shape.
#
# So resolving is not a claim made beside the verdict, it *is* the verdict. `material` and
# `reasoning` are required fields with no default, which is what makes a grammar-constrained
# model emit them and decide rather than fall off the end of the object.
class HingeResolutionOutput(BaseModel):
    """What the lookups established, and the verdict they support if they support one.

    The policy bearings are deliberately absent. This pass is never shown the policies at
    all, so there is no identifier it could cite and nothing to validate — a bearing cannot
    be added, moved or invented because there is nothing to move. What it may settle is one
    thing: whether the question was worth a person's interruption.

    A hinge is settled when `material` and `reasoning` say what it settled to. `null` and an
    empty reasoning are the honest way to say the repository was silent, and a narrower
    question belongs in `hinge` instead of a verdict.
    """

    #: What the lookups established, required either way. "Checked, and the repository is
    #: silent" is as much a finding as an answer, and the two are opposite facts about the
    #: question underneath.
    findings: str = Field(min_length=1)
    #: The verdict the lookups support, or `null` where they support none. Required rather
    #: than defaulted: a model that may omit this omits it.
    material: bool | None
    #: Why, and empty exactly when there is no verdict to explain.
    reasoning: str | None
    recommended_response: str | None = None
    #: A narrower hinge, where the lookups changed what is actually unknown. Empty leaves
    #: the original standing.
    hinge: str | None = None

    @property
    def resolved(self) -> bool:
        """Settled, meaning there is a verdict, a reason for it, and no question left.

        A narrower question outranks a verdict offered beside it, and deliberately so. The
        contract asks for one or the other; a model that sends both has said it is still
        uncertain, and reading that as settled would drop the better question and put a
        confident verdict in its place — the exact trade the charter refuses.
        """

        return (
            self.material is not None
            and bool((self.reasoning or "").strip())
            and not (self.hinge or "").strip()
        )

    @model_validator(mode="after")
    def a_resolution_settles_the_verdict(self) -> HingeResolutionOutput:
        """Make the answer coherent rather than refuse it.

        This raised, and raising was the wrong instrument for what it was checking. These
        are conditions *between* fields, which a JSON schema cannot express and a grammar
        therefore cannot enforce — so the only thing holding them was a sentence in the
        prompt, and a model that missed the sentence lost its whole investigation. Three
        schemas in, a 27B local model had found a new way past each version: `resolved`
        without a verdict, a verdict without reasoning, a recommendation on a question it
        had not answered. Every one of those cost a hinge that had been checked.

        And refusing bought nothing, because there is nothing to protect. `_apply` already
        ignores a recommendation on the unresolved path and already ignores one on a
        finding that is not material, so the shapes this used to reject were shapes the
        application discarded anyway. Normalising says the same thing sooner, in one place,
        where a reader of `HingeResolutionOutput` can see what an incoherent answer becomes.

        What is not normalised away is uncertainty. Nothing here invents a verdict or drops
        a question; every rule below moves in the direction of asking a person.
        """

        # A verdict with nothing behind it is not a verdict. `_apply` would fall back to the
        # judgement's own reasoning, which reads as though the lookups had confirmed it.
        if self.material is not None and not (self.reasoning or "").strip():
            object.__setattr__(self, "material", None)
        # Only a settled, material finding recommends anything. Both halves are already
        # enforced downstream; stating them here means one account rather than two.
        if self.recommended_response and not (self.resolved and self.material):
            object.__setattr__(self, "recommended_response", None)
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
