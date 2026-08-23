"""The second look a hinged finding gets, and what it is allowed to establish.

A judgement that stopped to ask a person is handed a toolbox and asked to find out what the
repository says. It establishes facts. It does not decide what they mean.

That division is the whole of this module now, and it was not always. This pass used to
return a verdict of its own — `material`, its reasoning, a recommended response, and a
narrowed hinge — which was written straight over the verdict the judge had reached. Measured
on a local model across twelve investigations, four came back with `material` set one way
and every sentence of their own reasoning arguing the other: "the boundary is deliberate…
the abstraction is earning its place" beside a verdict of material. No validator can catch
that, because agreement between a boolean and a paragraph is not a property a JSON schema
can express — three versions of a cross-field validator each found a new way to be defeated.

It was never a validation problem. Two components were minting architecture verdicts under
two different contracts, and the one with the weaker view — policy titles, no bodies, a
prompt that never asks it to weigh guidance — could overwrite the one that had read them.
So this one stopped deciding. What it returns is the record of what it looked up, and the
judge that produced the hinge is handed that record and asked again.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from archcompass.domain import (
    ArchitectureCase,
    Finding,
    RecordedInvestigation,
    RepositoryAtlas,
    RepositoryRef,
    Verdict,
)
from archcompass.reasoning.adapters.langchain import candidate_text, case_text
from archcompass.reasoning.adapters.tool_loop import (
    investigate_with_tools,
    recorded_investigation,
)
from archcompass.reasoning.ports import InvestigatorSource

HINGE_CONTRACT = (
    "You judged this candidate and stopped, because your verdict turned on something the "
    "evidence you were shown does not say. You now have read-only lookups into the same "
    "repository. Use them to find out whether the question you were going to put to a "
    "person is one the repository already answers.\n\n"
    "The lookups take qualified names, and the candidate you are judging already names "
    "everything you need. Ask what implements, depends on, calls or tests it — those settle "
    "most hinges. Read the code only where the structure does not settle it, and search only "
    "when you do not already know a name.\n\n"
    "Do not decide the verdict. You are not being asked whether the finding is material, "
    "whether the boundary is justified, or what should be done about it — that judgement is "
    "made once, elsewhere, with the policies in front of it, and it will be made again with "
    "whatever you establish here. Finding nothing is a real outcome and a useful one: 'the "
    "repository is silent on this' is what tells a person their answer is genuinely needed. "
    "Stop when further lookups would not change what is known."
)


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
    """One bounded conversation per hinge. No second call, and no verdict.

    It used to end with a structured call that returned `material`, `reasoning`, a
    recommendation and a narrowed hinge. Deleting it costs nothing and buys back a model
    call: the only field of that schema carrying observations — `findings`, required with
    `min_length=1` — was read by no call site in the repository. The model was compelled to
    write down what it had learned into a field nothing has ever consumed, while the record
    a reader actually sees was assembled from the transcript beside it.
    """

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
    ) -> RecordedInvestigation | None:
        """What the repository said, recorded. `None` where there was nothing to record.

        The finding does not come back changed, because nothing here is entitled to change
        it. Whether these observations settle the hinge is the judge's to answer, and the
        node above calls it with them.
        """

        if finding.verdict is not Verdict.HELD or not finding.hinge:
            raise ValueError("only a held finding with a hinge can be investigated")
        offered = self._investigators.for_review(repository, atlas)
        if offered.investigator is None:
            return recorded_investigation(
                None,
                candidate_id=str(finding.candidate.id),
                withheld=offered.withheld,
                atlas_fingerprint=repository.content_id,
                model_identity=self._model_identity,
            )
        investigate_with_tools(
            self._model,
            offered.investigator,
            system=HINGE_CONTRACT,
            opening=resolution_prompt(finding, case),
            subject=f"the hinge on {finding.candidate.summary}",
        )
        return recorded_investigation(
            offered.investigator,
            candidate_id=str(finding.candidate.id),
            atlas_fingerprint=repository.content_id,
            model_identity=self._model_identity,
        )
