"""Dependency-free ArchCompass domain concepts."""

# Public re-exports are the package API.
# pyright: reportUnusedImport=false

from archcompass.domain.core import (  # noqa: F401
    AddressedCandidate,
    Answer,
    AnswerStatus,
    ArchitectureCase,
    Candidate,
    CandidateChange,
    CandidateId,
    CaseConstraint,
    CaseDecision,
    CaseFacet,
    ChangeCause,
    DecisionDisposition,
    Evidence,
    Finding,
    Participant,
    Policy,
    PolicyBearing,
    PolicyContext,
    PolicyScope,
    PolicyStrength,
    Question,
    RepositoryAtlas,
    RepositoryRef,
    RetrievalProvenance,
    Review,
    ReviewDelta,
    ReviewStatus,
    SourceLocation,
    StandingDecision,
    Verdict,
)
from archcompass.domain.core import __all__ as __all__
