"""The small, dependency-free ArchCompass domain vocabulary.

These are ordinary immutable Python values.  Parsing JSON, validating model replies,
checkpointing workflows, and storing records are boundary concerns and deliberately live
outside this package.
"""

from archcompass.domain.core.atlas import RepositoryAtlas
from archcompass.domain.core.candidate import Candidate, CandidateId, Participant
from archcompass.domain.core.case import (
    Answer,
    AnswerStatus,
    ArchitectureCase,
    CaseConstraint,
    CaseDecision,
    CaseFacet,
    PolicyContext,
    Question,
)
from archcompass.domain.core.decision import DecisionDisposition, StandingDecision
from archcompass.domain.core.finding import Finding, PolicyBearing, Verdict
from archcompass.domain.core.policy import Policy, PolicyScope, PolicyStrength
from archcompass.domain.core.repository import RepositoryRef
from archcompass.domain.core.review import (
    AddressedCandidate,
    CandidateChange,
    ChangeCause,
    RetrievalProvenance,
    Review,
    ReviewDelta,
    ReviewStatus,
)
from archcompass.domain.core.values import Evidence, SourceLocation

__all__ = [
    "AddressedCandidate",
    "Answer",
    "AnswerStatus",
    "ArchitectureCase",
    "Candidate",
    "CandidateChange",
    "CandidateId",
    "CaseConstraint",
    "CaseDecision",
    "CaseFacet",
    "ChangeCause",
    "DecisionDisposition",
    "Evidence",
    "Finding",
    "Participant",
    "Policy",
    "PolicyBearing",
    "PolicyContext",
    "PolicyScope",
    "PolicyStrength",
    "Question",
    "RepositoryAtlas",
    "RepositoryRef",
    "RetrievalProvenance",
    "Review",
    "ReviewDelta",
    "ReviewStatus",
    "SourceLocation",
    "StandingDecision",
    "Verdict",
]
