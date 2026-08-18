"""Dependency-free ArchCompass domain concepts."""

from archcompass.domain.atlas import RepositoryAtlas
from archcompass.domain.candidate import Candidate, CandidateId, Participant
from archcompass.domain.case import (
    Answer,
    AnswerStatus,
    ArchitectureCase,
    CaseConstraint,
    CaseDecision,
    CaseFacet,
    PolicyContext,
    Question,
)
from archcompass.domain.decision import DecisionDisposition, StandingDecision
from archcompass.domain.finding import Finding, PolicyBearing, Verdict
from archcompass.domain.policy import Policy, PolicyScope, PolicyStrength
from archcompass.domain.repository import RepositoryRef
from archcompass.domain.review import (
    AddressedCandidate,
    CandidateChange,
    ChangeCause,
    RetrievalProvenance,
    Review,
    ReviewDelta,
    ReviewStatus,
)
from archcompass.domain.values import Evidence, SourceLocation

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
