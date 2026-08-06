"""The fingerprint holds still while everything run-scoped about a candidate moves."""

from tests.reasoning_support import candidate

from archcompass.domain.atlas import FindingParticipant, FindingPattern
from archcompass.domain.fingerprint import boundary_fingerprint


def test_the_same_structure_fingerprints_the_same_across_runs() -> None:
    first = candidate()
    second = candidate()
    assert first.candidate_id != second.candidate_id
    assert boundary_fingerprint(first) == boundary_fingerprint(second)


def test_participant_order_is_presentation_not_identity() -> None:
    original = candidate()
    reordered = original.model_copy(
        update={"participants": list(reversed(original.participants))}
    )
    assert boundary_fingerprint(original) == boundary_fingerprint(reordered)


def test_prose_and_measurements_do_not_reach_identity() -> None:
    original = candidate()
    reworded = original.model_copy(
        update={
            "summary": "Entirely different words about the same structure.",
            "measurements": [],
            "limitations": "Different caveat.",
        }
    )
    assert boundary_fingerprint(original) == boundary_fingerprint(reworded)


def test_a_different_pattern_is_a_different_boundary() -> None:
    original = candidate()
    other = original.model_copy(update={"pattern": FindingPattern.DUPLICATED_KNOWLEDGE})
    assert boundary_fingerprint(original) != boundary_fingerprint(other)


def test_a_different_participant_is_a_different_boundary() -> None:
    original = candidate()
    swapped = original.model_copy(
        update={
            "participants": [
                original.participants[0],
                FindingParticipant(
                    node_id="other",
                    qualified_name="package.OtherAdapter",
                    role="A different implementation.",
                ),
            ]
        }
    )
    assert boundary_fingerprint(original) != boundary_fingerprint(swapped)
