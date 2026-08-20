"""The labelled test set: what is asked, and which policies are the right answer.

Candidate cases are not stored as text. They are detected from the shipped example
repositories by the production analyser and detectors at load time, and the YAML holds only
the labels, joined by repository and participant list. That join is checked in both
directions — an unmatched label and an unlabelled candidate are both errors — so a detector
change is a loud failure here rather than a test set that silently got smaller.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

from archcompass.analysis.adapters.ast_analyzer import PythonAstRepositoryAnalyzer
from archcompass.analysis.analyzer import DataclassCandidateDetector
from archcompass.analysis.detectors import detect_finding_candidates
from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    CaseConstraint,
    CaseDecision,
    Participant,
    Policy,
    PolicyContext,
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
EXAMPLE_REPOSITORIES = Path("eval/cases")

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


def _authored_case(document: dict[str, object]) -> ArchitectureCase:
    context = dict(document.get("policy_context") or {})
    constraints = tuple(
        CaseConstraint(text=str(item["text"]))
        for item in list(document.get("constraints") or [])
    )
    decisions = tuple(
        CaseDecision(text=str(item["text"])) for item in list(document.get("decisions") or [])
    )
    base = ArchitectureCase.create()
    return base.revise(
        constraints=constraints,
        decisions=decisions,
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
    repositories = {
        name: _authored_case(value) for name, value in document["repositories"].items()
    }
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
        case = repositories[repository]
        if not with_constraints:
            case = case.revise(constraints=(), decisions=())
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
