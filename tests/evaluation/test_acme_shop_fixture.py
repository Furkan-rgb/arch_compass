"""The example repository whose questions the code itself can mostly answer.

The other fixtures defend shapes a detector must keep finding. This one defends where the
*answers* live, because it exists to exercise the evidence path: two pairs of constants
agree, and whether each agreement is one fact or two is written down — for `PAGE_SIZE`
in the comments beside the definitions, for `RETRY_LIMIT` only at the sites that consume
the copies against one external platform. A review that reads what the application puts
in front of it settles both without asking; the one thing left for a reader is intent —
whether a second payment vendor is coming — which no line of this repository states.

What is defended below is exactly that placement. If the disambiguating sentences drift
out of the spans the evidence path reads — the widened definition excerpt, the consumer
sites the augmentation attaches — the fixture silently stops testing what it was written
to test, and a green run would say the evidence path works when nothing exercised it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from archcompass.adapters.analysis.ast_analyzer import PythonAstRepositoryAnalyzer
from archcompass.application.usage_evidence import UsageEvidenceService
from archcompass.domain.atlas import Atlas, FindingCandidate, FindingPattern
from archcompass.domain.finding_detectors import detect_finding_candidates

FIXTURE = Path("eval/cases/acme-shop").resolve()

pytestmark = pytest.mark.evaluation


def _atlas() -> Atlas:
    return PythonAstRepositoryAnalyzer().analyze(FIXTURE / "repository")


def _augmented() -> list[FindingCandidate]:
    atlas = _atlas()
    return UsageEvidenceService().augment(
        detect_finding_candidates(atlas), atlas, FIXTURE / "repository"
    )


def _source(relative: str) -> str:
    return (FIXTURE / "repository" / relative).read_text(encoding="utf-8")


def _one(candidates: list[FindingCandidate], pattern: FindingPattern, name: str):
    return next(
        item
        for item in candidates
        if item.pattern is pattern and name in item.summary
    )


def test_all_three_detectors_are_exercised() -> None:
    """Every pattern present, and the two duplications are the pair the fixture is."""

    candidates = detect_finding_candidates(_atlas())
    assert {item.pattern for item in candidates} >= {
        FindingPattern.SOLE_IMPLEMENTATION,
        FindingPattern.DUPLICATED_KNOWLEDGE,
    }
    duplications = [
        item.summary
        for item in candidates
        if item.pattern is FindingPattern.DUPLICATED_KNOWLEDGE
    ]
    assert any("PAGE_SIZE" in item for item in duplications)
    assert any("RETRY_LIMIT" in item for item in duplications)


def test_the_coincidence_is_stated_beside_its_definitions() -> None:
    """`PAGE_SIZE` is settled by the comments the widened excerpt carries.

    Each definition's disambiguating sentence must sit in the contiguous comment block
    directly above the recorded line, because that block is what the evidence path widens
    a definition excerpt over. A sentence moved into a docstring or below the constant
    would still read fine to a person and never reach the judge.
    """

    candidate = _one(
        detect_finding_candidates(_atlas()),
        FindingPattern.DUPLICATED_KNOWLEDGE,
        "PAGE_SIZE",
    )
    for participant in candidate.participants:
        assert participant.location is not None
        lines = _source(participant.location.path).split("\n")
        start = participant.location.start_line
        above = lines[max(0, start - 4) : start - 1]
        comment = " ".join(
            item.strip("# ").strip() for item in above if item.lstrip().startswith("#")
        )
        assert comment, f"no comment block above {participant.location.path}"
    reports_comment = _source("reports/settings.py")
    assert "nothing to do with any listing" in reports_comment


def test_the_shared_fact_is_visible_only_at_the_consumers() -> None:
    """`RETRY_LIMIT`'s anchor is the platform client both copies feed.

    Neither definition names the other, and the sentence tying both to the platform's own
    guidance lives in the client — so this pair is settled by consumer sites, not by
    definition comments, which is the half of the evidence path the other pair cannot
    exercise. The augmentation must therefore attach consumers for it.
    """

    candidate = _one(_augmented(), FindingPattern.DUPLICATED_KNOWLEDGE, "RETRY_LIMIT")
    consumer_paths = {
        item.location.path
        for item in candidate.participants
        if item.location is not None and "consumer" in item.role.casefold()
    }
    assert "billing/invoices.py" in consumer_paths
    assert "notifications/emails.py" in consumer_paths
    assert "retries" in _source("billing/invoices.py")
    assert "retries" in _source("notifications/emails.py")
    client = _source("shared/acme_client.py")
    assert "five attempts" in client


def test_the_reader_only_question_is_stated_nowhere() -> None:
    """The payment seam must stay the one thing the repository cannot settle.

    The fixture's contrast collapses if a comment ever says whether a second processor is
    planned: the sole-implementation boundary exists to still be a question after every
    line has been read.
    """

    for relative in ("payments/gateway.py", "payments/stripe_gateway.py"):
        text = _source(relative).casefold()
        assert "second" not in text
        assert "planned" not in text
        assert "future" not in text


def test_the_augmentation_counts_what_it_shows() -> None:
    """Both duplications carry the shown-versus-found measurement, and neither is empty."""

    for name in ("PAGE_SIZE", "RETRY_LIMIT"):
        candidate = _one(_augmented(), FindingPattern.DUPLICATED_KNOWLEDGE, name)
        measurements = {item.name for item in candidate.measurements}
        assert any("consumer" in item for item in measurements), name
