"""Where a boundary stands against what its branch has already seen.

Three states and one rule about which of them a boundary is in, so the tests are about the
rule rather than about storage: `disposition_of` is what decides whether run two is quiet,
and it takes a mapping rather than a repository precisely so it can be argued with here.
"""

from __future__ import annotations

from tests.reasoning_support import reviewed_boundary

from archcompass.domain.baseline import (
    BaselineEntry,
    BoundaryDisposition,
    baseline_entries_for,
    disposition_of,
)
from archcompass.domain.review import ReviewedBoundary

BRANCH = "branch_0123456789abcdef"


def _boundary(name: str, *, material: bool, fingerprint: str | None) -> ReviewedBoundary:
    return reviewed_boundary("BR-001", name, material=material).model_copy(
        update={"fingerprint": fingerprint}
    )


def _entry(fingerprint: str, *, material: bool, label: str = "Earning its place") -> BaselineEntry:
    return BaselineEntry(
        branch_id=BRANCH,
        boundary_fingerprint=fingerprint,
        material=material,
        verdict_label=label,
        added_from_review="rev_previous",
    )


def test_a_boundary_the_branch_has_never_seen_is_new() -> None:
    boundary = _boundary("Port", material=False, fingerprint="bdry_one")

    assert disposition_of(boundary, {}) is BoundaryDisposition.NEW
    assert (
        disposition_of(boundary, {"bdry_other": _entry("bdry_other", material=False)})
        is BoundaryDisposition.NEW
    )


def test_a_baselined_boundary_judged_the_same_way_is_known() -> None:
    boundary = _boundary("Port", material=False, fingerprint="bdry_one")
    baseline = {"bdry_one": _entry("bdry_one", material=False)}

    assert disposition_of(boundary, baseline) is BoundaryDisposition.KNOWN


def test_a_verdict_that_moved_since_it_was_baselined_is_changed() -> None:
    """The case or the corpus moved, nobody touched the code, and the answer is different."""

    became_material = _boundary("Port", material=True, fingerprint="bdry_one")
    became_immaterial = _boundary("Port", material=False, fingerprint="bdry_one")

    assert (
        disposition_of(became_material, {"bdry_one": _entry("bdry_one", material=False)})
        is BoundaryDisposition.CHANGED
    )
    assert (
        disposition_of(became_immaterial, {"bdry_one": _entry("bdry_one", material=True)})
        is BoundaryDisposition.CHANGED
    )


def test_a_reworded_label_over_the_same_materiality_is_still_known() -> None:
    """Materiality is the load-bearing bit, and the label is presentation.

    The two cannot disagree today — the label is derived from the pattern and the verdict —
    and this is the guard for the day the vocabulary is revised: an edit to a phrase must
    not re-surface every baselined boundary in every repository as changed.
    """

    boundary = _boundary("Port", material=False, fingerprint="bdry_one")
    stale_label = {
        "bdry_one": _entry("bdry_one", material=False, label="Words nobody uses any more")
    }

    assert disposition_of(boundary, stale_label) is BoundaryDisposition.KNOWN


def test_a_boundary_with_no_fingerprint_is_in_no_baseline() -> None:
    """A review stored before fingerprints existed. There is nothing to look it up by."""

    boundary = _boundary("Port", material=False, fingerprint=None)

    assert disposition_of(boundary, {}) is BoundaryDisposition.NEW


def test_entries_are_built_only_from_boundaries_that_have_an_identity() -> None:
    entries = baseline_entries_for(
        "rev_now",
        BRANCH,
        [
            _boundary("Port", material=False, fingerprint="bdry_one"),
            _boundary("Gateway", material=True, fingerprint=None),
        ],
    )

    assert [entry.boundary_fingerprint for entry in entries] == ["bdry_one"]
    assert entries[0].branch_id == BRANCH
    assert entries[0].added_from_review == "rev_now"
    # Copied off the boundary rather than looked up later, so the entry survives the review.
    assert entries[0].material is False
    assert entries[0].verdict_label == "Earning its place"
