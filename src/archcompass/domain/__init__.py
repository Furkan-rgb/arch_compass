"""Domain models, in the order the advisory flow uses them.

What a review is made of, with no knowledge of where any of it is stored or who asked for
it: the atlas a repository is analysed into, the case it is judged against, the policies
that bear on it, the detectors that find boundaries, and the review itself. Read `review.py`
first — a `BoundaryReview` is the record everything else here exists to produce.
"""

from archcompass.domain.atlas import (
    Atlas,
    AtlasEdge,
    AtlasNode,
    AtlasVersion,
    EdgeType,
    FindingCandidate,
    FindingMeasurement,
    FindingParticipant,
    FindingPattern,
    NodeType,
    SourceLocation,
)
from archcompass.domain.case import ArchitectureCase, CaseRevision, CaseStatement
from archcompass.domain.finding_detectors import detect_finding_candidates
from archcompass.domain.policy import PolicyDocument, PolicyScope, PolicyStrength
from archcompass.domain.review import (
    BoundaryReview,
    BoundaryReviewReport,
    CandidateVerdict,
    PolicyBearing,
    ReviewedBoundary,
    ReviewStatus,
)
from archcompass.domain.review_conversation import (
    ReviewAnswer,
    ReviewConversation,
    ReviewMessage,
)

__all__ = [
    "ArchitectureCase",
    "Atlas",
    "AtlasEdge",
    "AtlasNode",
    "AtlasVersion",
    "BoundaryReview",
    "BoundaryReviewReport",
    "CandidateVerdict",
    "CaseRevision",
    "CaseStatement",
    "EdgeType",
    "FindingCandidate",
    "FindingMeasurement",
    "FindingParticipant",
    "FindingPattern",
    "NodeType",
    "PolicyBearing",
    "PolicyDocument",
    "PolicyScope",
    "PolicyStrength",
    "ReviewAnswer",
    "ReviewConversation",
    "ReviewMessage",
    "ReviewStatus",
    "ReviewedBoundary",
    "SourceLocation",
    "detect_finding_candidates",
]
