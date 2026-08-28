"""The Policies fold uses the width it has, and each card keeps the measure it was given.

Geometry, so jsdom can see none of it. A grid track written as
`repeat(auto-fill,minmax(0,24.3rem))` is a class list nothing without a layout engine can
fail: jsdom applies no stylesheet, computes no boxes, and would report the same success for
`grid`, for `grid-cols-1`, and for the `max-w` on the list this replaced. The nine-pixel notch
this branch already shipped in the verdict rail survived on exactly that. So the two claims
the fold makes are asked of a real Chromium serving the real bundle, as rectangles:

* at a wide panel the cards sit **side by side**, each one still capped at its own measure,
  with the note inside still drawing at the width `finding-detail.tsx` derives;
* at a narrow one they **stack**, one column filling the width, which is the phone.

And a third, because it is the half a column count does not cover: the cards sit at their
**natural** height rather than stretching to match. The store's worst real pair of notes on
one finding is 1,080 characters against 340, and a stretched short card there is a hairline
box enclosing several hundred pixels of the same colour as the fold around it.

**The policies are injected, and nothing else is.** `DeterministicJudge.judge` passes `()`
for a finding's policies — it reaches no provider, so it has no reasoning about a policy to
record — which means the review this suite runs renders the fold's *empty state* and never
the list. The alternative to injecting is a suite that cannot see this surface at all. So the
review is the real review, the bundle is the real bundle, the component and the stylesheet
are the real ones, and one field of one JSON response is replaced on the way past.

The two note lengths are the store's, not invented: `.archcompass/workspace.sqlite3` holds
514 distinct policy notes over 519 occurrences, and over the 168 stored findings carrying
more than one policy the widest pair is 1,080 characters beside 340. The text itself is
filler, because this file measures rectangles and not words.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from tests.browser.harness import (
    REVIEW_TIMEOUT_MS,
    open_first_candidate,
    show_everything,
    wait_for_review,
)

pytestmark = pytest.mark.browser

#: `24.3rem` at the root's 16px. The derivation is in `finding-detail.tsx` and is not repeated
#: here: the note's `46ch` at its 13px is 358.80px, the card spends 30px on `px-3.5` and its two
#: hairlines, and 388.80 is 24.3rem exactly.
#:
#: `46ch` is 46 advances of the zero and not 46 characters. It was 428.0 while the sans was
#: Onest, whose zero advanced 0.665em where IBM Plex Sans's advances 0.600em; the derivation is
#: unchanged and every term in it moved.
CARD_PX = 388.8

#: What is left for the note once the card has taken its padding and its two hairlines.
NOTE_PX = CARD_PX - 30.0

#: `gap-2`. A second column needs `CARD_PX + GAP_PX` more room than the first.
GAP_PX = 8.0

#: Sub-pixel slack, for the same reason `test_mobile.py` carries one: a box laid out at a
#: fractional width rounds, and a check that fires on a third of a pixel gets deleted.
TOLERANCE_PX = 1.0

#: The two note lengths measured in the store, as the widest real spread one finding holds.
LONG_NOTE = (
    "The boundary this policy protects is crossed by the participant named above. " * 15
)[:1080]
SHORT_NOTE = ("A second policy bears on the same candidate for a different reason. " * 6)[:340]


def _inject_policies(page) -> None:  # type: ignore[no-untyped-def]
    """Give every finding in the review two policies, with the store's widest real pair.

    Installed before the first navigation, because the page fetches the review as it mounts.
    `/api/reviews/runs` and `/api/reviews` itself are left alone — the pattern below matches
    a single path segment that is not `runs`, so only the review document is rewritten.
    """

    def handler(route, request) -> None:  # type: ignore[no-untyped-def]
        response = route.fetch()
        try:
            document: dict[str, Any] = response.json()
        except Exception:  # pragma: no cover - a non-JSON body is not this test's subject
            route.fulfill(response=response)
            return
        for finding in document.get("findings", []):
            finding["policies"] = [
                {
                    "policy_id": "boundaries.deliberate",
                    "policy_title": "Cross a boundary only where the case says so",
                    "reasoning": LONG_NOTE,
                },
                {
                    "policy_id": "abstraction.delay",
                    "policy_title": "Delay abstractions until variation is credible",
                    "reasoning": SHORT_NOTE,
                },
            ]
        route.fulfill(response=response, body=json.dumps(document))

    page.route(re.compile(r"/api/reviews/(?!runs)[^/?]+$"), handler)


def _open_the_policies_fold(page):  # type: ignore[no-untyped-def]
    """The open Policies disclosure of the first row in the docket.

    Found by the word the fold is labelled with rather than by position among the three
    folds, because the other two are owned elsewhere and either may move.
    """

    show_everything(page)
    open_first_candidate(page)
    fold = page.locator("details", has=page.get_by_text("Policies", exact=True)).first
    fold.wait_for(state="visible", timeout=REVIEW_TIMEOUT_MS)
    fold.get_by_text("Policies", exact=True).click()
    cards = fold.locator("ul > li")
    cards.first.wait_for(state="visible", timeout=REVIEW_TIMEOUT_MS)
    assert cards.count() == 2, (
        f"the injected policies did not reach the list: {cards.count()} cards drawn. "
        "Either the review response shape moved or the fold is rendering its empty state."
    )
    return fold, cards


def _boxes(cards) -> list[dict[str, float]]:  # type: ignore[no-untyped-def]
    return [cards.nth(index).bounding_box() for index in range(cards.count())]


def _available_px(fold) -> float:  # type: ignore[no-untyped-def]
    """The content width of the disclosure body the list is laid into.

    Measured on the *parent* rather than on the `<ul>` itself, and the distinction is the
    whole defect: a `max-w` on the list makes the list report one card's width in a fold that is
    1,126px wide, so a guard that read the list would conclude there was no room for a second column
    and skip the assertion that this surface exists to make. Asking the parent asks how much
    room the grid was given, which is the number that does not move when the grid is wrong.
    """

    return float(
        fold.locator("ul").first.evaluate(
            "el => { const box = el.parentElement, style = getComputedStyle(box);"
            " return box.clientWidth - parseFloat(style.paddingLeft)"
            " - parseFloat(style.paddingRight); }"
        )
    )


def test_the_policies_fold_lays_its_cards_across_a_wide_panel(page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    """Two policies, one row, and each card still stopping at its own measure.

    This is the report the change answers: two cards stacked down a panel nearly two
    thousand pixels wide. The fix is columns rather than width, so both halves are asserted
    — the cards are beside each other *and* neither of them got wider to get there.
    """

    _inject_policies(page)
    page.set_viewport_size({"width": 2560, "height": 1400})
    wait_for_review(page, review_url)
    fold, cards = _open_the_policies_fold(page)

    available = _available_px(fold)
    assert available >= 2 * CARD_PX + GAP_PX, (
        f"the fold body is only {available:.2f}px wide at a 2560px viewport, which is less "
        f"than the {2 * CARD_PX + GAP_PX:.0f}px two columns need — so this test is no longer "
        "measuring the case the report was about. The docket's `max-w-[76rem]` column has "
        "narrowed."
    )

    first, second = _boxes(cards)
    assert abs(first["y"] - second["y"]) <= TOLERANCE_PX, (
        f"the two policy cards are still on separate rows: y {first['y']:.2f} and "
        f"{second['y']:.2f}, in a fold body {available:.2f}px wide with room for "
        f"{int((available + GAP_PX) // (CARD_PX + GAP_PX))} columns. This is the report the "
        "grid track was written for."
    )
    assert second["x"] - first["x"] >= CARD_PX, (
        f"the second card starts {second['x'] - first['x']:.2f}px after the first, which is "
        f"less than one {CARD_PX:.0f}px track"
    )

    # The measure survives the columns, which is the whole point of moving the cap on to the
    # track instead of widening the card. Both halves: the card, and the text inside it.
    for index, box in enumerate((first, second)):
        assert abs(box["width"] - CARD_PX) <= TOLERANCE_PX, (
            f"card {index} draws at {box['width']:.2f}px rather than {CARD_PX:.0f}px — the "
            "cap moved off the grid track and the note is no longer reading at its measure"
        )
    notes = fold.locator("ul > li p")
    for index in range(notes.count()):
        width = notes.nth(index).bounding_box()["width"]
        assert abs(width - NOTE_PX) <= TOLERANCE_PX, (
            f"the note in card {index} reads at {width:.2f}px rather than {NOTE_PX:.0f}px — "
            "`finding-detail.tsx` derives 24.3rem from exactly this number"
        )


def test_the_policy_cards_sit_at_their_natural_height(page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    """`items-start`, so a short card beside a long one is not a box full of nothing.

    A grid item stretches to its row by default. With the store's widest real pair on one
    finding — 1,080 characters beside 340 — that default gives the short card several hundred
    pixels of empty `--surface-2` inside a hairline it shares with the fold around it, which
    reads as a rule drawn in the wrong place rather than as a card.
    """

    _inject_policies(page)
    page.set_viewport_size({"width": 2560, "height": 1400})
    wait_for_review(page, review_url)
    _, cards = _open_the_policies_fold(page)

    long_card, short_card = _boxes(cards)
    assert long_card["height"] > short_card["height"] + 100, (
        f"the cards are {long_card['height']:.2f}px and {short_card['height']:.2f}px tall "
        "side by side, which is a stretched row: a 1,080-character note and a 340-character "
        "one cannot honestly be the same height"
    )


def test_the_policies_fold_falls_back_to_one_column_when_it_is_narrow(  # type: ignore[no-untyped-def]
    page, review_url: str
) -> None:
    """One track below 436px of fold, filling the width it has. This is the phone.

    `auto-fill` floors its repetition count at one and the single `minmax(0,24.3rem)` track
    shrinks to the space available, so the card is the column and the column is the fold —
    which is what the `max-w` on the `ul` did here before, unchanged.
    """

    _inject_policies(page)
    page.set_viewport_size({"width": 390, "height": 844})
    wait_for_review(page, review_url)
    fold, cards = _open_the_policies_fold(page)

    available = _available_px(fold)
    assert available < CARD_PX + GAP_PX, (
        f"the fold body is {available:.2f}px wide at 390px, which is room for a second "
        "column — so this test is not measuring the fallback it claims to"
    )

    first, second = _boxes(cards)
    assert abs(first["x"] - second["x"]) <= TOLERANCE_PX, (
        f"the cards are side by side at 390px: x {first['x']:.2f} and {second['x']:.2f}"
    )
    assert second["y"] >= first["y"] + first["height"] - TOLERANCE_PX, (
        f"the second card does not sit below the first: y {second['y']:.2f} against "
        f"{first['y']:.2f} + {first['height']:.2f}"
    )
    for index, box in enumerate((first, second)):
        assert abs(box["width"] - available) <= TOLERANCE_PX, (
            f"card {index} draws at {box['width']:.2f}px in a {available:.2f}px fold — the "
            "single track is no longer taking the width it has"
        )
