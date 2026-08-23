"""The labelled test set: what is asked, and which policies are the right answer.

Candidate cases are not stored as text. They are detected from the shipped example
repositories by the production analyser and detectors at load time, and the YAML holds only
the labels, joined by repository and participant list. That join is checked in both
directions — an unmatched label and an unlabelled candidate are both errors — so a detector
change is a loud failure here rather than a test set that silently got smaller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

import yaml

from archcompass.analysis.adapters.ast_analyzer import PythonAstRepositoryAnalyzer
from archcompass.analysis.analyzer import DataclassCandidateDetector
from archcompass.analysis.detectors import detect_finding_candidates
from archcompass.domain import (
    Answer,
    AnswerStatus,
    ArchitectureCase,
    Candidate,
    CaseFacet,
    Participant,
    Policy,
    PolicyContext,
    Question,
)
from archcompass.policies.retrieval import retrieval_query

__all__ = [
    "EvalCase",
    "LabelledCase",
    "candidate_cases",
    "detected_candidates",
    "intent_cases",
    "label_coverage",
    "load_cases",
]

CANDIDATE_LABELS = Path("evaluation/dataset/candidate-labels.yaml")
INTENT_CASES = Path("evaluation/dataset/intent-cases.yaml")
EXAMPLE_REPOSITORIES = Path("examples/cases")

#: Graded gain for nDCG. Everything else in the harness reads bearings alone.
GRADES = {"bearing": 3, "supporting": 2, "adjacent": 1}


@dataclass(frozen=True, slots=True)
class LabelledCase:
    """One labelled situation, before it has been turned into a query."""

    id: str
    kind: str
    pattern: str
    bearing: frozenset[str]
    supporting: frozenset[str]
    adjacent: frozenset[str]
    notes: str = ""

    @property
    def grades(self) -> dict[str, int]:
        return {
            **dict.fromkeys(self.adjacent, GRADES["adjacent"]),
            **dict.fromkeys(self.supporting, GRADES["supporting"]),
            **dict.fromkeys(self.bearing, GRADES["bearing"]),
        }

    @property
    def labelled(self) -> frozenset[str]:
        return self.bearing | self.supporting | self.adjacent


@dataclass(frozen=True, slots=True)
class EvalCase:
    """A labelled situation with the exact text the retriever will be given.

    `candidate` and `case` are carried for the candidate cases so the notebook can re-derive
    the query under an ablation — without the constraints, for instance — instead of
    reproducing `retrieval_query` by hand and measuring something slightly different.
    """

    labels: LabelledCase
    query: str
    repository: str | None = None
    candidate: Candidate | None = None
    case: ArchitectureCase | None = None

    @property
    def id(self) -> str:
        return self.labels.id

    @property
    def kind(self) -> str:
        return self.labels.kind

    @property
    def pattern(self) -> str:
        return self.labels.pattern

    @property
    def bearing(self) -> frozenset[str]:
        return self.labels.bearing

    @property
    def grades(self) -> dict[str, int]:
        return self.labels.grades


@cache
def detected_candidates(root: Path) -> tuple[tuple[str, Candidate], ...]:
    """Every candidate the shipped detectors find in the example repositories.

    Cached because parsing five repositories takes a few seconds and the notebook asks for
    them from several cells.
    """

    found: list[tuple[str, Candidate]] = []
    for example in sorted((root / EXAMPLE_REPOSITORIES).iterdir()):
        repository = example / "repository"
        if not repository.is_dir():
            continue
        atlas = PythonAstRepositoryAnalyzer().analyze(repository)
        names = {node.atlas_id: node.qualified_name for node in atlas.nodes}
        for item in detect_finding_candidates(atlas):
            # The production conversion from a detector record to the domain candidate the
            # retriever is given. Reused rather than reimplemented for the usual reason: a
            # second version of it would let this measure a candidate no review ever sees.
            found.append(
                (example.name, DataclassCandidateDetector._candidate(item, repository, names))
            )
    return tuple(found)


#: The stem each authored facet is put to the case as, because a case now carries intent as
#: answered questions and nothing else. `retrieval_query` embeds `f"{question.text} {value}"`,
#: so what reaches the retriever is the dataset's own sentence with this in front of it —
#: which is what a review's own clarification round produces, rather than a second shape for
#: intent that only the evaluation knows about.
_FACET_STEMS = (
    (CaseFacet.CONSTRAINT, "constraints", "What constrains this architecture?"),
    (CaseFacet.DECISION, "decisions", "What has already been decided here?"),
)


def _authored_intent(document: dict[str, object]) -> tuple[tuple[CaseFacet, str, str], ...]:
    """The facet, its stem, and every sentence the dataset authored under it, joined.

    One entry per facet rather than one per sentence: `with_answers` refuses two answers
    with the same equivalence key, and the key is the facet plus the candidates the question
    was asked about — which for one candidate is the facet alone.
    """

    found = []
    for facet, key, stem in _FACET_STEMS:
        said = " ".join(
            str(dict(item)["text"]).strip()  # type: ignore[arg-type]
            for item in list(document.get(key) or [])
        ).strip()
        if said:
            found.append((facet, stem, said))
    return tuple(found)


def _authored_case(
    document: dict[str, object],
    *,
    candidate_id: str,
    with_intent: bool,
) -> ArchitectureCase:
    """The case a review of this candidate is judged against, as a review would hold it.

    Built per candidate rather than per repository because a `Question` names the candidates
    it was asked about, and a case's intent is now the answers to those questions. The
    dataset still authors intent per repository — it is a fact about the codebase, not about
    one finding — and it is put to every candidate of that repository, which is what a
    reviewer answering once for the whole repository produces.
    """

    context = dict(document.get("policy_context") or {})
    case = ArchitectureCase.create()
    intent = _authored_intent(document) if with_intent else ()
    if intent:
        case = case.open_revision().with_answers(
            tuple(
                Answer(
                    question=Question.create(
                        text=stem,
                        facet=facet,
                        candidate_ids=(candidate_id,),
                        round=1,
                    ),
                    status=AnswerStatus.ANSWERED,
                    value=said,
                    actor="evaluation-dataset",
                    answered_at=datetime.now(UTC),
                )
                for facet, stem, said in intent
            )
        )
    return case.revise(
        policy_context=PolicyContext(
            user=context.get("user"),
            organisation=context.get("organisation"),
            repository=context.get("repository"),
        ),
    )


def _slug(participants: tuple[Participant, ...]) -> str:
    return "|".join(sorted(item.qualified_name for item in participants))


def candidate_cases(root: Path, *, with_constraints: bool = True) -> tuple[EvalCase, ...]:
    """The labelled detector output, as queries built the way a review builds them."""

    document = yaml.safe_load((root / CANDIDATE_LABELS).read_text(encoding="utf-8"))
    repositories = dict(document["repositories"])
    available = {
        (repository, _slug(candidate.participants)): candidate
        for repository, candidate in detected_candidates(root)
    }
    claimed: set[tuple[str, str]] = set()
    cases: list[EvalCase] = []
    for entry in document["cases"]:
        repository = str(entry["repository"])
        key = (repository, "|".join(sorted(str(item) for item in entry["participants"])))
        candidate = available.get(key)
        if candidate is None:
            raise ValueError(
                f"No detected candidate in {repository} has participants "
                f"{sorted(entry['participants'])}. The label is stale or the detectors changed."
            )
        if key in claimed:
            raise ValueError(f"Two labels claim the same candidate: {key}")
        claimed.add(key)
        case = _authored_case(
            repositories[repository],
            candidate_id=str(candidate.id),
            with_intent=with_constraints,
        )
        labels = LabelledCase(
            id=f"{repository}/{candidate.pattern}/{_short(candidate)}",
            kind="candidate",
            pattern=candidate.pattern,
            bearing=frozenset(str(item) for item in entry.get("bearing") or ()),
            supporting=frozenset(str(item) for item in entry.get("supporting") or ()),
            adjacent=frozenset(str(item) for item in entry.get("adjacent") or ()),
            notes=" ".join(str(entry.get("notes", "")).split()),
        )
        if not labels.bearing:
            raise ValueError(f"{labels.id} has no bearing policies, so recall is undefined")
        cases.append(
            EvalCase(
                labels=labels,
                query=retrieval_query(candidate, case),
                repository=repository,
                candidate=candidate,
                case=case,
            )
        )
    unlabelled = sorted(set(available) - claimed)
    if unlabelled:
        raise ValueError(
            "Detected candidates carry no label, so they would silently leave the test "
            f"set: {unlabelled}"
        )
    return tuple(cases)


def _short(candidate: Candidate) -> str:
    """A readable tail for the case id: the participants, without their packages."""

    return ",".join(
        sorted(item.qualified_name.rsplit(".", 1)[-1] for item in candidate.participants)
    )


def intent_cases(root: Path) -> tuple[EvalCase, ...]:
    document = yaml.safe_load((root / INTENT_CASES).read_text(encoding="utf-8"))
    cases: list[EvalCase] = []
    for entry in document["cases"]:
        labels = LabelledCase(
            id=f"intent/{entry['id']}",
            kind="intent",
            pattern="intent",
            bearing=frozenset(str(item) for item in entry.get("bearing") or ()),
            supporting=frozenset(str(item) for item in entry.get("supporting") or ()),
            adjacent=frozenset(str(item) for item in entry.get("adjacent") or ()),
        )
        if not labels.bearing:
            raise ValueError(f"{labels.id} has no bearing policies, so recall is undefined")
        cases.append(EvalCase(labels=labels, query=" ".join(str(entry["query"]).split())))
    return tuple(cases)


def load_cases(root: Path, *, with_constraints: bool = True) -> tuple[EvalCase, ...]:
    """The whole test set, candidate cases first, with every labelled id checked."""

    return candidate_cases(root, with_constraints=with_constraints) + intent_cases(root)


def label_coverage(
    cases: tuple[EvalCase, ...], corpus: tuple[Policy, ...]
) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """Which policies the labels name, which are never named, and which do not exist.

    The third is a correctness check on the dataset — a typo in a policy id would otherwise
    make a case permanently unanswerable and depress every score by a fixed amount. The
    second is honesty about coverage: a corpus policy that appears in no label is a policy
    this evaluation says nothing about.
    """

    known = {policy.id for policy in corpus}
    named = {policy_id for case in cases for policy_id in case.labels.labelled}
    return frozenset(named & known), frozenset(known - named), frozenset(named - known)
