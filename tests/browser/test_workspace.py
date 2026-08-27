"""End-to-end: the built workbench, a real browser, and a real workspace server.

The bootstrap lives in `conftest.py` now, because `test_mobile.py` reads the same running
review and producing a second one would double the cost of the suite. What it sets up is
unchanged and described there.
"""

from __future__ import annotations

import re
from itertools import pairwise

import pytest
from playwright.sync_api import expect

from tests.browser.harness import REVIEW_TIMEOUT_MS, open_first_candidate

pytestmark = pytest.mark.browser


def _visible(locator, timeout: int = 20_000) -> bool:
    """Wait for a locator, then report it. `is_visible()` does not wait, and every screen
    here arrives through a lazily loaded route chunk."""

    locator.first.wait_for(state="visible", timeout=timeout)
    return True


def test_the_landing_page_leads_into_a_review(page, workspace_url: str) -> None:  # type: ignore[no-untyped-def]
    page.goto(f"{workspace_url}/", wait_until="networkidle")

    assert _visible(
        page.get_by_role(
            "heading",
            name="Write your guidance once. Every review weighs it.",
        )
    )
    # The hero's claim is that a verdict rests on guidance somebody wrote, so the policy it
    # names has to be one the bundled corpus really ships.
    assert _visible(page.get_by_text("Delay abstractions until variation is credible"))
    assert _visible(page.get_by_text("6 found").first)
    # The product's own claim about itself, stated plainly rather than hedged.
    assert _visible(page.get_by_text("It does not roam the repository"))
    page.get_by_role("button", name="Can I use Ollama?").click()
    assert _visible(page.get_by_text("Yes, for both roles").first)

    page.get_by_role("link", name="Review a repository").first.click()
    page.wait_for_url("**/start")
    assert _visible(page.get_by_role("heading", name="Review a repository", level=1))


def test_a_review_produces_a_workbench_with_a_clarification(page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    page.goto(review_url, wait_until="networkidle")

    # The docket is the page, not a tab on it, and it opens on what needs a human.
    page.get_by_text("settled").first.wait_for(timeout=REVIEW_TIMEOUT_MS)
    page.get_by_text("question unanswered").first.wait_for(timeout=REVIEW_TIMEOUT_MS)
    assert _visible(page.get_by_role("button", name="Save and rejudge"))
    assert _visible(page.get_by_role("button", name="Conclude with remaining uncertainty"))
    assert _visible(page.get_by_text("Review lineage"))

    # A finding reads as an assessment in three voices, with its provenance folded away
    # until asked for.
    page.get_by_role("button", name="All", exact=False).click()
    page.locator("[data-candidate]").first.click()
    assert _visible(page.get_by_text("Measured").first)
    assert _visible(page.get_by_text("Judged").first)
    assert _visible(page.get_by_text("Standing decision").first)
    # Who judged is attribution and is said out loud: the charter's whole point is that a
    # reader always knows which of the three voices is speaking, and a sentence whose author
    # is one disclosure away is a sentence presented as nobody's. So the identity sits on the
    # `Judged` line itself, above the model's paragraph — which is what `docs/design-system.md`
    # promises the model's voice is ("the reading size, under a line naming the model that
    # produced it").
    #
    # The same identity is recorded a second time inside `Provenance`, where it is one of the
    # inputs to the analysis hash rather than an attribution — and that copy is folded, which
    # is what a disclosure is for.
    #
    # **Asserted by where each copy is, not by counting a string on the page.** This used to
    # count two matches of `judge:deterministic-v1` and call the first one the attribution
    # line. It never was: that literal is the *prompt* identity
    # (`DETERMINISTIC_JUDGE_PROMPT_IDENTITY`), and the deterministic judge's model identity is
    # `fake:deterministic-architecture-v4` — so both matches were inside `Provenance`, one in
    # its closed summary and one in its `Prompt` row, and the attribution line was never read.
    # Shortening that summary to twelve characters of prompt identity took one of the two away
    # and nothing a reader sees moved. A count over the whole page cannot tell those apart;
    # scoping each half to the element that carries the promise can, and it survives the next
    # reformat of either line.
    model = "fake:deterministic-architecture-v4"
    # The parent of the voice word is the attribution line, so this asserts adjacency — the
    # identity is *on* the `Judged` line — rather than merely somewhere in the finding.
    judged_line = page.get_by_text("Judged", exact=True).first.locator("xpath=..")
    expect(judged_line).to_contain_text(model)

    provenance = page.locator("details", has=page.get_by_text("Provenance", exact=True)).first
    recorded = provenance.get_by_text(model)
    assert recorded.count() == 1
    # `is_visible()` rather than `_visible()`: the helper waits for the thing to appear, which
    # is right for asserting presence and is twenty seconds of nothing when asserting absence.
    assert not recorded.is_visible()
    provenance.get_by_text("Provenance", exact=True).click()
    assert _visible(recorded)

    # Reading something else about the review does not cost your place in the list: the same
    # row is still open when you come back.
    #
    # `expect` rather than a bare `count()`, because which surface is on screen is a URL
    # change now — `?tab=delta` — and a router navigation renders in a transition rather than
    # in the click that asked for it. A count read in the same tick reads the docket before it
    # has painted, which is a race the assertion had all along and only now loses.
    page.get_by_role("tab", name="Delta").click()
    expect(page).to_have_url(re.compile(r"\?tab=delta$"))
    page.get_by_role("tab", name="Docket").click()
    expect(page.locator("[data-candidate][aria-expanded='true']")).to_have_count(1)

    # Retrieval is auditable from behind the judgement it audits, naming the retriever that
    # ran — and deterministic retrieval takes the whole corpus and embeds nothing, which the
    # provenance says rather than naming a model it never called.
    page.get_by_role("button", name="Judgement context").first.click()
    drawer = page.get_by_role("dialog", name="Judgement context")
    drawer.wait_for()
    drawer.get_by_role("tab", name="Provenance").click()
    assert _visible(drawer.get_by_text("full-corpus-test-oracle").first)
    assert _visible(drawer.get_by_text("non-embedding strategy").first)
    drawer.get_by_role("button", name="Close panel").click()

    # The embedding this workspace would use is still stated in the shell, beside the
    # reasoning model, because they are two independent selections.
    assert _visible(page.get_by_role("link", name="Embedding").first)
    assert "nomic-embed-text" in page.get_by_role("link", name="Embedding").first.inner_text()


def test_the_judged_rails_rule_stops_where_its_words_stop(page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    """The one claim about the Judged band that jsdom is structurally unable to check.

    The rail beside the model's argument draws a hairline down its left edge, and a grid item
    stretches down its row by default — so the rule ran the height of the *argument* rather than
    the height of the rail: 239px of margin note at the top of an 1,147px border on the longest
    recorded reasoning, and the rest of it a line with nothing beside it. `lg:self-start` is the
    fix and it is one class, which is what makes it the kind of thing somebody deletes as
    redundant.

    `finding-detail.test.tsx` asserts that class and says in its own comment that it cannot do
    better: jsdom applies no stylesheet and computes no layout, so it can see that
    `lg:self-start` was written and never that it resolved to anything. That is a real gap and
    this is where it closes.

    Two assertions, and they are not the same one twice.

    The first is the mechanism, read out of the cascade. `align-self: start` on the item beats
    `align-items` on the container, so this is the whole of the guarantee and it is exactly what
    a deleted class costs.

    The second is the effect, read off a rectangle — and it is a bound rather than a proof on
    this fixture, which is worth saying plainly. The deterministic judge writes a short
    reasoning, so here the *rail* is the taller of the two and the row's height is its own; the
    defect only paints when the argument is taller. So this bites on a `min-h-full`, a stray
    bottom padding, or any future fixture whose argument outgrows its rail, and it is silent on
    the case that produced the original 908px. That case is the first assertion's.

    Desktop only, deliberately. Below `lg` the grid is one column, the rail carries no border at
    all, and there is nothing here to be true or false.
    """

    page.goto(review_url, wait_until="networkidle")
    page.get_by_role("button", name="All", exact=False).click()
    open_first_candidate(page)
    page.get_by_text("Judged").first.wait_for(timeout=REVIEW_TIMEOUT_MS)

    measured = page.evaluate(
        """
        () => {
          // The argument is the one block on the surface set at the reading size, which is the
          // same property `design-system.test.ts` enforces — so this finds it by the thing that
          // is guarded rather than by a class list that may be rewritten.
          const argument = [...document.querySelectorAll('[class*="text-[16px]"]')][0];
          if (!argument) return null;
          const grid = argument.parentElement;
          // The last of the grid's three children, not the second. The verdict's sentence is a
          // grid item now — placed in the argument's own column so its cap cannot take it past
          // the argument's edge, which the test below measures — so the rail is the argument's
          // neighbour by placement rather than by index.
          const rail = grid.lastElementChild;
          const style = getComputedStyle(rail);
          const last = rail.lastElementChild;
          return {
            columns: getComputedStyle(grid).gridTemplateColumns.split(" ").length,
            alignSelf: style.alignSelf,
            border: style.borderLeftWidth,
            railBottom: rail.getBoundingClientRect().bottom,
            contentBottom: last.getBoundingClientRect().bottom,
          };
        }
        """
    )
    assert measured is not None, "no block at the reading size — the argument moved or lost 16px"
    # The band really is two columns at this width, or the rest of this is about nothing.
    assert measured["columns"] == 2, measured

    # The rule is drawn at all. Without this the two below pass on a rail with no edge, which is
    # a different bug wearing the same numbers.
    assert measured["border"] == "1px", measured
    # Chromium reports `align-self: start` back as `flex-start`, so both spellings of the
    # one value are accepted and `stretch` — which is the default and the defect — is not.
    assert measured["alignSelf"] in {"start", "flex-start"}, measured

    # And it stops where the words stop. One pixel of slack for the sub-pixel rounding a
    # fractional line height leaves on a bounding box; the defect this replaces was 908px.
    overhang = measured["railBottom"] - measured["contentBottom"]
    assert overhang <= 1, f"the rail's rule runs {overhang:.0f}px past its own content"


#: Every docket row's verdict edge, its row's box, and the hairline the list draws under it.
#:
#: Read off the `<ul>` the docket names rather than off a class list, and one entry per list so
#: that "the row after this one" is never a row in a different group. The edge is the only
#: direct-child `<span aria-hidden>` a row draws; it carries no text, so there is nothing else
#: to find it by, and that is the point — nothing here asserts on a class.
DOCKET_EDGES = """
() => [...document.querySelectorAll('ul[aria-label^="Candidates"]')].map((list) =>
  [...list.children].map((item) => {
    const article = item.firstElementChild;
    const edge = article.querySelector(':scope > span[aria-hidden="true"]');
    const edgeStyle = getComputedStyle(edge);
    const itemStyle = getComputedStyle(item);
    const edgeBox = edge.getBoundingClientRect();
    const rowBox = item.getBoundingClientRect();
    const articleBox = article.getBoundingClientRect();
    // What `--rule` resolves to at this row, in the notation `borderBottomColor` answers
    // in, so the two can be compared as strings. A probe rather than a literal: `.band`
    // re-declares `--rule`, so the value is whatever the token means *here*. A
    // `display: none` span computes a colour and no layout, and every box above is
    // already a number.
    const probe = document.createElement('span');
    probe.style.display = 'none';
    probe.style.color = 'var(--rule)';
    item.appendChild(probe);
    const ruleToken = getComputedStyle(probe).color;
    probe.remove();
    return {
      top: edgeBox.top,
      bottom: edgeBox.bottom,
      left: edgeBox.left,
      right: edgeBox.right,
      width: edgeStyle.borderLeftWidth,
      style: edgeStyle.borderLeftStyle,
      colour: edgeStyle.borderLeftColor,
      opacity: edgeStyle.opacity,
      visibility: edgeStyle.visibility,
      depth: edgeStyle.zIndex,
      articleTop: articleBox.top,
      articleBottom: articleBox.bottom,
      rowLeft: rowBox.left,
      rowRight: rowBox.right,
      rule: itemStyle.borderBottomWidth,
      ruleColour: itemStyle.borderBottomColor,
      ruleToken,
      ink: itemStyle.color,
      last: item === list.lastElementChild,
    };
  }),
)
"""

#: Sub-pixel slack, kept as insurance rather than because a measurement needs it.
#:
#: The boxes here are fractional — a row's `<article>`, which is the box every claim below is
#: made against, is 88.89px tall at 1440 and 108.39px at 390, and the first row's edge ends at
#: y=1077.03. (The `<li>` around it is a pixel taller either way, 89.89 and 109.39, because it
#: carries the row rule.) So this arithmetic looks like it has to round.
#: It does not. Every pair compared below is laid out against the same box, so an edge's top
#: and bottom agree with its row's to +0.00 on all six rows, at both widths, in both themes,
#: and every gap between consecutive edges is exactly 1.00. The slack is here against a
#: future layout that does round, and half a pixel is the size for it: everything this test
#: exists to catch is off by one pixel or by nine, never by a fraction.
EDGE_SLACK_PX = 0.5

#: What a computed colour comes back as when nothing is painted. Chromium answers every
#: `transparent` — the keyword, `divide-transparent`, an unset border — in this one spelling.
TRANSPARENT = "rgba(0, 0, 0, 0)"


def sweep_the_verdict_edges(lists: list[list[dict]]) -> int:
    """Every claim about the docket's verdict column, over one measurement of it.

    Called twice by the test below, on two different dockets: the column as it loads, where
    this fixture's judge has held all six candidates and every edge is coloured, and the same
    column with one row settled. The claims are about a column of rows and not about a column
    of *coloured* rows, so making them twice is what turns the second into something a run
    has actually seen.

    Returns how many consecutive pairs it compared, so the caller can refuse a docket that
    listed one row per group and would have made the continuity claims vacuous.
    """

    rows = [row for listed in lists for row in listed]
    assert rows, "the docket listed no candidates — there is no column here to measure"

    # The edge is drawn, at the width and in the stroke this is about. Without these two the
    # rest passes on a docket whose verdicts are three pixels of nothing, or three pixels of
    # dashes — different bugs wearing the same numbers, and the second is the reported defect
    # at its maximum: not one hole in the rail per row but one every other pixel.
    assert all(row["width"] == "3px" for row in rows), rows
    assert all(row["style"] == "solid" for row in rows), rows

    # And it is painted. These three say nothing about the box, which is the reason they are
    # here: every other claim in this function reads a border colour or a bounding rectangle,
    # and all three of `opacity: 0`, `visibility: hidden` and a negative `z-index` leave both
    # of those exactly as a healthy docket reports them. Each one deletes the whole verdict
    # column — measured against the docket at 1440 in light, all three erase the same 1561
    # pixels, every one of them in the rail's own three columns — and each was applied,
    # rebuilt and run against the rest of this sweep unchanged, which passed.
    #
    # `z-index` is the odd one and is included for the same reason as the other two. The
    # `<ul>` is `bg-surface`, which is opaque, so a rail given a stacking order behind it is
    # as gone as one at zero opacity. `auto` or `0` are the two spellings of "wherever the
    # document put it", which is where this belongs; anything negative is behind the ground.
    assert all(row["opacity"] == "1" for row in rows), rows
    assert all(row["visibility"] == "visible" for row in rows), rows
    assert all(row["depth"] in {"auto", "0"} for row in rows), rows

    # Every edge is exactly its row's height and starts exactly at its row's left edge.
    #
    # The height is the claim that carries the mixed column. The left edge is what makes the
    # hairline below a cut a reader sees: the edge is pinned to the panel's own content box,
    # and `abs` rather than `<=` is deliberate — an edge that had drifted inboard by any
    # amount at all would still be under the row rule, and would be a stripe down the middle
    # of a row rather than the panel's coloured margin.
    for row in rows:
        assert abs(row["top"] - row["articleTop"]) <= EDGE_SLACK_PX, row
        assert abs(row["bottom"] - row["articleBottom"]) <= EDGE_SLACK_PX, row
        assert abs(row["left"] - row["rowLeft"]) <= EDGE_SLACK_PX, row

    # The hairline is painted, in the hairline's own colour, and it reaches across the three
    # pixels the edge occupies.
    #
    # The colour is not decoration here, it is the whole argument. `--rule` in light is 10%
    # black on white, so the line that cuts the rail composites to 229.5 — 25.5 levels under
    # the surface, in one pixel — and reads as a boundary; anything else there reads as
    # damage. Two ways to lose it, and neither changes a width: `divide-transparent` deletes
    # every row separator on the docket and puts the user's white notch back at 1px instead
    # of 9, and dropping `divide-rule` while keeping `divide-y` falls back to `currentColor`
    # and paints a near-black line the width of the panel. Measured under that second
    # mutation, the row rule comes back `rgb(10, 10, 10)` where the token is
    # `rgba(0, 0, 0, 0.1)`. "Not transparent" catches the first and misses the second, so this
    # asserts the value: the border is what `--rule` resolves to at this row, read off a
    # throwaway probe because `.band` re-declares the token and a literal here would be a
    # second copy of it. `--rule` is nearly the surface colour on purpose, and that is a claim
    # about the token rather than about the docket — `ui/tokens.test.ts` holds it.
    for row in rows:
        if row["last"]:
            # `divide-y` skips the last row, because the panel's own border closes the list.
            continue
        assert row["rule"] == "1px", row
        # The probe answered with something, and something other than the text colour it
        # would inherit if `--rule` had gone missing — without this the comparison below
        # could pass by both sides being wrong in the same direction.
        assert row["ruleToken"] not in {TRANSPARENT, row["ink"]}, row
        assert row["ruleColour"] == row["ruleToken"], row
        assert row["rowRight"] >= row["right"] - EDGE_SLACK_PX, row

    # And the cut is that hairline and nothing more. Compared within one list only: two groups
    # are two `<ul>`s with a heading between them, and the space there is a section break.
    runs = 0
    for listed in lists:
        for above, below in pairwise(listed):
            runs += 1
            gap = below["top"] - above["bottom"]
            assert gap >= 1 - EDGE_SLACK_PX, (
                f"consecutive verdict edges are {gap:.2f}px apart — a run of one verdict "
                "fuses into a bar that reads as the panel's own border"
            )
            assert gap <= 1 + EDGE_SLACK_PX, (
                f"consecutive verdict edges are {gap:.2f}px apart — the row rule is one "
                "pixel, so anything wider is a notch in the edge rather than a boundary"
            )
    return runs


def settle_a_row_with_a_neighbour_either_side(page) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    """Accept one candidate that has a row above it and a row below it, and say which one.

    The bulk bar rather than the row's own decision bar, and the difference matters to what
    is being measured. Deciding from inside a row opens a panel under it and hands the
    reviewer the next row; checking a box and pressing Accept settles a row without opening
    anything, so the docket stays a column of closed rows and the column is the subject.

    Returns the row's position as (list, row), because the caller identifies it by where it
    sits: the docket's order does not depend on decisions, so the index is stable across the
    re-render this causes.
    """

    lists = page.locator('ul[aria-label^="Candidates"]')
    for index in range(lists.count()):
        rows = lists.nth(index).locator("> li")
        if rows.count() < 3:
            continue
        row = rows.nth(1)
        # The box is `opacity-0` until the row is hovered, which hides it from a reader and
        # from nothing else — it has a box, it takes a click, and Playwright agrees.
        row.get_by_role("checkbox").check()
        page.get_by_role("button", name="Accept all").click()
        # The decision is a request to a real workspace, so wait for the thing being waited
        # for: the row's own edge giving up its colour. Nothing else on the row says as
        # early or as exactly that this row is now settled.
        edge = row.locator('article > span[aria-hidden="true"]')
        expect(edge).to_have_css("border-left-color", TRANSPARENT, timeout=REVIEW_TIMEOUT_MS)
        return index, 1
    raise AssertionError(
        "no docket group listed three rows — there is no row here with a neighbour on both "
        "sides, and a settled row at the end of a list does not exercise a mixed column"
    )


def test_the_verdict_edge_is_cut_only_by_the_row_rule(page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    """A run of same-verdict rows is one run of colour, cut where every row is cut.

    The user's report was "there is a gap on the red part": two consecutive material rows,
    each with its verdict as a left edge, and a white notch in the red between them. It was a
    decision rather than a fault. The edge was `inset-y-1`, four pixels of air at each end,
    written to stop a run of same-verdict rows — the common case on a second visit — fusing
    into one unbroken bar that read as the panel's own border rather than as six verdicts.

    That defect was real and the answer was the wrong size. Four pixels above a row boundary,
    four below, and the list's own 1px divider between them is a **nine pixel** break: swept
    on this fixture at 1440, an edge from y=992.14 to y=1073.03 in an 89px row, the next
    beginning at y=1082.03. Every other seam on this surface is one pixel. Nine is not a
    boundary, it is a hole, and the eye reads a hole in a rule as something failing to paint.

    What the notch was for, the list already did. `divide-y` puts a `--rule` hairline on every
    row boundary and it spans the `<li>`'s whole width — the three pixels the edge occupies
    included, because the edge starts at the list's content box and so does the border. So a
    full-height edge is cut once per row, by the one pixel that cuts everything else.

    The half of the old defect that mattered has not come back, and it is worth being exact
    about which half. Six identical verdicts do read as one column of colour with hairline
    ticks in it rather than as six separate marks — but six identical verdicts *are* one run,
    and the question the edge exists to answer is where the red starts, which a continuous
    shape answers better than six pieces do. What made the old bar a defect was that it could
    be taken for the panel's own chrome, and it cannot: the panel's border is one pixel of
    `--rule` on all four sides — 10% black in light, 11% white in dark — where this is three
    pixels of an opaque verdict hue on one, the dimmest of them `--cleared`, which is
    `--ink-3`. Nothing else about the panel is coloured. Where consecutive verdicts differ the
    column visibly breaks into per-row segments, which is exactly where the difference is
    worth seeing.

    Three claims, and they fail in different directions, which is why there are three.

    *Continuity*: consecutive edges are no further apart than that hairline. Restoring
    `inset-y-1` — or any inset — puts nine pixels here and this is what says so.

    *Separation*: they are no closer either. Deleting `divide-y` from the `<ul>`, or writing
    the rule back onto the `<article>` where `:last-child` matched every row and it painted on
    none — the bug this list has already had once — closes the gap to zero and refuses the
    verdicts as six. The two together are the whole property: **exactly one pixel, exactly the
    row's own.**

    *The rule reaches, and is a rule*: the hairline spans the edge's own x and is painted in
    `--rule`. Inset the list's padding past the edge and the gap stays a pixel while the red
    runs straight through it; take the colour off and the gap is still a pixel while the line
    is either invisible or near-black across the whole docket.

    Under all three, the invariant that makes a **mixed** column safe: every edge is exactly
    its row's height, settled or not. `settled` picks the colour and never the box, so a
    settled row is a full-height transparent edge and its neighbours are unaffected by it.
    That claim used to be asserted over a column it had never seen — this fixture's judge
    holds all six candidates, and no browser check decides anything before this one, so every
    edge was coloured every time it ran. So this settles a row in the middle of a run and
    sweeps again. That second sweep is the mixed column.

    Geometry, all of it, so jsdom can see none of it: it applies no stylesheet and computes no
    layout, and the notch stood for as long as it did because the class that drew it was one
    nothing could fail.
    """

    page.goto(review_url, wait_until="networkidle")
    page.get_by_role("button", name="All", exact=False).click()
    page.locator("[data-candidate]").first.wait_for(timeout=REVIEW_TIMEOUT_MS)

    lists = page.evaluate(DOCKET_EDGES)
    rows = [row for listed in lists for row in listed]
    assert [row for row in rows if row["colour"] != TRANSPARENT], (
        "no row states a verdict as an edge — every one of them is transparent"
    )
    assert sweep_the_verdict_edges(lists) >= 1, (
        "the docket listed one row per group — nothing here is a run"
    )

    # And again with a mixed column, which is the state this surface spends its life in and
    # the one nothing had ever measured.
    listed, settled = settle_a_row_with_a_neighbour_either_side(page)
    mixed = page.evaluate(DOCKET_EDGES)
    assert sweep_the_verdict_edges(mixed) >= 1, "the docket lost its rows to a decision"

    # The row that was decided gave up its colour and kept its box, and the rows either side
    # of it kept both. This is the whole of what `settled` is allowed to change.
    assert mixed[listed][settled]["colour"] == TRANSPARENT, mixed[listed][settled]
    for neighbour in (settled - 1, settled + 1):
        assert mixed[listed][neighbour]["colour"] != TRANSPARENT, mixed[listed][neighbour]


#: The widths the lede's residual was found at, plus the two either side of where it closes.
#:
#: `lg` is 1024 and the Judged band splits into two columns there, so the argument stops being
#: the width of the section and becomes a `1fr` track beside a 20rem rail. The rail is fixed and
#: the track is not, so the narrower the viewport the narrower the argument — and the verdict's
#: sentence above it was capped at a *constant* 616px. Swept before the repair: 34.00px past the
#: argument's right edge at 1024, 18.00px at 1040, and agreeing to the deliberate -1.11px from
#: about 1060 up. 1280 is where the rail widens to 26rem, which moves the track again.
JUDGED_BAND_WIDTHS = (1024, 1040, 1060, 1280, 1440)

#: How far short of the argument's right edge the lede is allowed to stop, and how far past it.
#:
#: Past: nothing. The two are drawn one above the other and read as sharing an edge, and the
#: whole subject here is a case where they did not. One pixel of slack for the sub-pixel
#: rounding a fractional track width leaves on a bounding box.
#:
#: Short: the lede's own `max-w-[38.5rem]` is 616px against the argument's `58ch` = 617.12px, so
#: at any width where both caps bite the lede stops 1.12px short by a deliberate choice of round
#: number over matching `ch` count. Anything much larger than that means the sentence has been
#: given a cap of its own again.
LEDE_EDGE_SLACK_PX = 1.5


def test_the_lede_never_reaches_past_the_argument_it_stands_over(page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    """Defect 9's residual, measured across the widths that produced it.

    The verdict's sentence sits directly above the model's argument and reads as sharing its
    right edge. `finding-detail.test.tsx` asserts that in jsdom by resolving both declared
    measures against both declared font sizes — which was the repair for the two of them wearing
    one `58ch`, and which is **blind by construction to this**: a declared measure is a cap, and
    what a block is drawn at is the smaller of that cap and the box it sits in. jsdom computes no
    layout, so it never has the second term. Two caps a pixel apart in boxes 34px apart pass it.

    Which is what the band did. The sentence stood above the grid at the section's full width,
    capped at 616px; the argument stood in a `1fr` track beside a 20rem rail. At 1024 that track
    is 582px. The repair is containment — the sentence is now placed in the argument's own column
    — and jsdom asserts *that*, as a fact about the document. This asserts the rectangles it
    produces, which is the half a class list cannot promise.

    Held at every width above `lg`, and checked below it too: there the band is one column, both
    blocks are laid out in the section, and the caps are all that separate them. The claim is the
    same claim and it is worth knowing it holds on both sides of the breakpoint.
    """

    page.goto(review_url, wait_until="networkidle")
    page.get_by_role("button", name="All", exact=False).click()
    open_first_candidate(page)
    page.get_by_text("Judged").first.wait_for(timeout=REVIEW_TIMEOUT_MS)
    page.evaluate("() => document.fonts.ready")

    for width in (390, *JUDGED_BAND_WIDTHS):
        page.set_viewport_size({"width": width, "height": 1000})
        measured = page.evaluate(
            """
            () => {
              // The argument is the one block on the surface set at the reading size, which is
              // the property `design-system.test.ts` enforces — so it is found by the thing that
              // is guarded rather than by a class list somebody may rewrite.
              const argument = [...document.querySelectorAll('[class*="text-[16px]"]')][0];
              if (!argument) return null;
              // The lede is the 13px semibold sentence above it, and it is identified by its
              // place rather than by its words: the three strings `lib/format` can put here are
              // product copy and this file does not own them.
              const above = [...document.querySelectorAll('p[class*="text-[13px]"]')].filter(
                (node) =>
                  node.compareDocumentPosition(argument) & Node.DOCUMENT_POSITION_FOLLOWING,
              );
              const lede = above[above.length - 1];
              if (!lede) return null;
              return {
                ledeRight: lede.getBoundingClientRect().right,
                argumentRight: argument.getBoundingClientRect().right,
                argumentWidth: argument.getBoundingClientRect().width,
                columns: getComputedStyle(argument.parentElement).gridTemplateColumns,
              };
            }
            """
        )
        assert measured is not None, f"at {width}px the band has no argument and lede to compare"

        past = measured["ledeRight"] - measured["argumentRight"]
        assert past <= LEDE_EDGE_SLACK_PX, (
            f"at {width}px the verdict's sentence ends {past:.2f}px past the argument it stands "
            f"over — argument column {measured['argumentWidth']:.0f}px, tracks "
            f"{measured['columns']}"
        )
        assert past >= -LEDE_EDGE_SLACK_PX, (
            f"at {width}px the sentence stops {-past:.2f}px short of the argument. Both are "
            "capped by the same column, so the only gap they can honestly show is the 1.12px "
            "between 38.5rem and 58ch — anything wider is a second measure that has grown back"
        )


def test_the_report_leads_with_the_summary_and_says_it_once(page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    """The one claim in the product that spans Python and TypeScript with a shared literal.

    `workflow/report.py` writes the summary into the document under a run-in label, because
    the document is downloaded and attached to pull requests and has to stand on its own.
    `surfaces.tsx` hoists the same paragraph out of the document and sets it in the model's
    voice, and drops it from what it renders below so the reader does not meet it twice.

    Neither side can see the other's copy of the label. This can: it opens a real report and
    counts the sentence.
    """

    page.goto(review_url, wait_until="networkidle")
    page.get_by_role("tab", name="Report").click()

    # The deterministic provider writes the stand-in, so the sentence is known here.
    summary = page.get_by_text("This summary was composed deterministically")
    assert _visible(summary.first)
    assert summary.count() == 1
    # Attributed, like every other paragraph the model is responsible for.
    assert _visible(page.get_by_text("In summary").first)
    # And the document underneath is whole.
    assert _visible(page.get_by_text("Where this came from").first)


def test_answering_a_clarification_completes_the_revision(page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    """A question is answered by picking, and the box is what you reach for when none fit.

    This used to type into the textarea, because a question arrived with nothing to pick
    from and the box was the only way to answer. That is the shape the charter forbids —
    *never make someone type what they could pick* — and it was invisible for as long as the
    round could produce a blank box. The model now has to propose two to four answers, so
    the common case is a click and the box is the escape hatch it was meant to be.
    """

    page.goto(review_url, wait_until="networkidle")
    page.get_by_text("question unanswered").first.wait_for(timeout=REVIEW_TIMEOUT_MS)
    first_url = page.url

    choices = page.get_by_role("radio")
    choices.first.wait_for(timeout=REVIEW_TIMEOUT_MS)
    # The proposed answers, plus the one that is always offered last whatever was proposed.
    assert choices.count() >= 3
    own = page.get_by_role("radio", name="Something else", exact=False)
    assert own.count() == 1
    # Never a closed set: choosing it opens the box, and the box is empty rather than
    # pre-filled with the model's sentence.
    own.click()
    written = page.get_by_placeholder("Add the architectural context").first
    assert _visible(written)
    assert written.input_value() == ""

    # Answered by picking, which is the way through this round that the product is for.
    choices.first.click()
    page.get_by_role("button", name="Save and rejudge").click()

    # Answering does not navigate to the run's own address — that used to swap the heading,
    # the findings and the surface for a progress list, on a review the reader was already
    # looking at. But it does not leave them on the record their answer superseded either.
    # The page waits where it is and then carries them to the revision they asked for, which
    # is the whole reason they answered.
    #
    # Waiting on the URL rather than on a click: nothing here presses anything after "Save
    # and rejudge", and arriving anywhere at all is the assertion.
    page.wait_for_url(lambda url: url != first_url, timeout=REVIEW_TIMEOUT_MS)
    page.get_by_text("Review 1", exact=False).first.wait_for(timeout=REVIEW_TIMEOUT_MS)
    # And it is the current record, not another earlier one: the banner that says otherwise
    # is drawn on every superseded record, and this page must not be showing it.
    assert page.get_by_role("link", name="Read the current record").count() == 0

    # Back does not go to the record that announces itself as out of date. The follow
    # replaces rather than pushes, so the way back from here is where the reader came from.
    assert page.url != first_url

    page.get_by_role("tab", name="Docket").click()
    assert _visible(page.get_by_text("Review lineage"))
    assert _visible(page.get_by_text("case revision 2", exact=False).first)
    # One review, one entry. Answering did not add a revision to the rail.
    assert page.get_by_text("One immutable revision").count() == 1

    # And the round it asked is readable as a round, with what was said to it — which existed
    # nowhere before and is the reason a reader can tell a second round from the first.
    page.get_by_role("tab", name="Rounds").click()
    assert _visible(page.get_by_text("Round 1", exact=False).first)


#: The nine `##` sections the workspace parser requires, in the editor's own order, each
#: with prose of its own rather than the prompt the form prints beside it. Bold and a bullet
#: sit under Guidance so the preview has real Markdown to render.
_POLICY_SECTIONS = (
    ("Intent", "Keep the decision about *what to do* out of the code that talks to a vendor."),
    (
        "Guidance",
        "An adapter **translates** between a vendor's shape and ours, and nothing more.\n\n"
        "- No branching in an adapter on anything the domain could decide\n"
        "- No default that is really a policy\n\n"
        # Below the ramp's fourth step, which is where `ui/markdown.tsx` had no renderer at
        # all: a `#####` and a `######` came out as the browser's own block element, at the
        # panel's full width over paragraphs stopping at the measure. They are here so the
        # assertion below has one of each to measure, and the prose under them is long enough
        # to wrap at any measure this renderer could be given.
        "##### Where an adapter ends\n\n"
        "The line is the record it hands back, and everything past that line is a decision "
        "the domain owns rather than a translation of somebody else's shape.\n\n"
        "###### And where it begins\n\n"
        "At the vendor's own vocabulary, which is the only thing an adapter is allowed to "
        "know that nothing else in the system knows.",
    ),
    ("Signals", "A vendor client with an `if` on a domain enum in it."),
    ("Diagnostic questions", "Would this branch survive swapping the vendor out?"),
    ("Likely consequences", "The rule is discovered twice and the two copies disagree."),
    ("Exceptions", "A retry policy the vendor's own SDK owns is theirs, not ours."),
    ("Positive example", "`git_cli.py` shells out and returns records; `service.py` decides."),
    ("Counterexample", "An HTTP client that decides which repositories are allowed."),
    ("Related policies", "The one about ports being stated in domain terms."),
)


def _authored_policy_body() -> str:
    return "\n\n".join(f"## {name}\n\n{prose}" for name, prose in _POLICY_SECTIONS) + "\n"


def test_policies_render_as_markdown_and_navigation_survives_a_phone(  # type: ignore[no-untyped-def]
    page, workspace_url: str
) -> None:
    page.goto(f"{workspace_url}/policies", wait_until="networkidle")

    page.get_by_role("button", name="Author policy").click()
    page.get_by_label("Title").fill("Adapters translate, they do not decide")
    page.get_by_label("Description").fill("Keep decisions in the domain.")

    # The form opens on the scaffold the workspace parser requires — nine empty `##` headings
    # — and will not save until each one has prose that is not the prompt beside it. This
    # test used to append a tenth section and press the button, which stopped working the
    # day the scaffold stopped writing its own prompts into the draft (`sections.ts:64-79`),
    # and had been reported as a click on a disabled control ever since. Writing all nine is
    # what an author does, so it is what this does.
    body = page.get_by_label("Policy body")
    body.fill(_authored_policy_body())
    page.get_by_role("tab", name="Preview").click()
    # `exact=True` on every one of these. `get_by_role(name=...)` matches a *substring* by
    # default, and the corpus listed under this form is 54 collapsible cards whose headings
    # each carry a strength descriptor — so the loose spelling matched 54 headings and the
    # one it was actually asking about was whichever came first in the DOM. The claim is that
    # `## Guidance` became a heading element, and a heading whose whole name is "Guidance" is
    # what says so.
    assert _visible(page.get_by_role("heading", name="Guidance", exact=True))
    assert _visible(page.get_by_text("No branching in an adapter"))
    _every_block_stops_at_one_edge(page)
    page.get_by_role("button", name="Create policy").click()

    # It is a real policy the next review reads, and its body renders as a document.
    card = page.get_by_role("button", name="Adapters translate, they do not decide")
    card.first.wait_for(timeout=30_000)
    card.first.click()
    assert _visible(page.get_by_role("heading", name="Guidance", exact=True))

    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("button", name="Open navigation").click()
    # *Navigation*, not *ArchCompass*. The drawer used to take the product's name as its
    # heading and say "review workbench" under it — two lines of branding at the top of the
    # one surface that exists to say where you can go, sharing no word with the control that
    # opened it or with the landmark inside it. The name moved to the description and the
    # heading now says what the sheet holds. What this test is about is unchanged: the
    # navigation on a phone is a real dialog, opened by name, and its links go where they say.
    drawer = page.get_by_role("dialog", name="Navigation")
    drawer.wait_for()
    drawer.get_by_role("link", name="Architecture cases").click()
    page.wait_for_url("**/cases")
    assert _visible(page.get_by_role("heading", name="Architecture cases", level=1))


#: The blocks a rendered document is allowed to draw past its measure, keyed by the tag.
#:
#: A fence and a table scroll inside themselves, so capping them would take the panel's width
#: away from the excerpt or the readings somebody came to read; a rule is not text at all and
#: spans what it divides. `ui/markdown.tsx` argues all three where the wrapper is left at
#: `max-w-none`, and `ui/markdown.test.tsx` holds the same three names.
_REACHES_PAST_THE_MEASURE = ("PRE", "HR")


def _every_block_stops_at_one_edge(page) -> None:  # type: ignore[no-untyped-def]
    """The measure a document is read at, as rectangles rather than as declared class lists.

    `ui/markdown.test.tsx` asserts this in jsdom, which lays nothing out: it resolves each
    declared measure against the declared type and checks the answers agree. That is the right
    test for the arithmetic and it cannot see the failure this one is about — an element with
    **no renderer at all**, which declares nothing to resolve and is drawn by the browser's own
    sheet at the full width of the panel. `#####` and `######` shipped that way, at 1168px over
    paragraphs stopping at 428px, and every measure assertion in the suite passed because every
    element that *had* a measure agreed about it.

    So this asks the layout engine instead. Every direct child of the rendered document either
    stops at the one edge the text blocks share or is one of the two that deliberately reach
    past it. A table is excluded by ancestry rather than by tag, because it is drawn inside an
    `overflow-x-auto` wrapper that is a plain `<div>` and a `<div>` is not a name worth
    excepting on.

    Delete the `h5` and `h6` entries from `RENDERERS`, rebuild, and this reports
    ``2 different right edges: [('H3', [428, ...]), ('H5', [1092]), ('H6', [1092]),
    ('P', [428, ...]), ('UL', [428])]`` — 1092px because that is the policy preview's own
    panel, where the finding's is 1168px. Which is the second reason this is a rectangle and
    not a class list: the number depends on the panel, and only one of the two blocks in that
    comparison has a number of its own at all.
    """
    document = page.locator("div.max-w-none").filter(
        has=page.get_by_role("heading", name="Guidance", exact=True)
    )
    blocks = document.locator("> *")
    widths: dict[str, list[float]] = {}
    for index in range(blocks.count()):
        block = blocks.nth(index)
        box = block.bounding_box()
        if box is None or box["width"] == 0:
            continue
        tag = block.evaluate("element => element.tagName")
        if tag in _REACHES_PAST_THE_MEASURE or block.locator("table").count():
            continue
        widths.setdefault(tag, []).append(round(box["width"], 2))

    measured = {width for group in widths.values() for width in group}
    assert len(measured) == 1, (
        "the blocks of a rendered document stop at "
        f"{len(measured)} different right edges: {sorted(widths.items())}"
    )
    # The two levels that had no renderer, named rather than left to the count: a fifth and a
    # sixth heading have to actually be in the document for the rule above to be about them.
    assert "H6" in widths, "the fixture no longer renders a heading below the ramp's fourth step"


#: The narrowest phone worth designing for, and the widest that still counts as one. 320 is
#: where `html` sets its own floor, so a page that overflows there overflows by construction
#: rather than by content.
PHONE_WIDTHS = (320, 390, 430)

#: Every page reachable without running a review. The workbench itself is covered by the
#: review test above; these are the ones a visitor lands on first.
STANDING_PAGES = ("/", "/start", "/reviews", "/repositories", "/cases", "/policies", "/settings")


def test_no_page_scrolls_sideways_on_a_phone(page, workspace_url: str) -> None:  # type: ignore[no-untyped-def]
    """A phone may scroll down. Scrolling *across* is always a layout that did not fit.

    This is a rule a comment cannot hold, because nothing about the offending markup looks
    wrong: a flex or grid item is `min-width: auto` by default, and this interface puts
    absolute paths and mono identifiers on screen that are wider than a phone. One of them
    anywhere in a column makes the column that wide, then the page. The base stylesheet
    removes that floor and the panel description breaks long paths; this notices when
    something reintroduces it.
    """

    offenders: list[str] = []
    for width in PHONE_WIDTHS:
        page.set_viewport_size({"width": width, "height": 844})
        for path in STANDING_PAGES:
            page.goto(f"{workspace_url}{path}", wait_until="networkidle")
            overflow = page.evaluate(
                "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            if overflow > 0:
                offenders.append(f"{path} at {width}px overflows by {overflow}px")

    assert not offenders, "; ".join(offenders)


def test_the_header_call_to_action_stands_down_on_a_phone(page, workspace_url: str) -> None:  # type: ignore[no-untyped-def]
    """The landing header's call to action stands down; the workspace topbar's does not.

    It wrapped onto two lines and squeezed the wordmark against the menu button.

    Asserted through the rendered result rather than the class list, because the class list
    said it was hidden while the cascade said otherwise: `hidden` on a component that sets
    its own `inline-flex` is two display utilities on one element, and `cn` did not resolve
    the conflict until it was taught to. Only the browser knows which won, so the browser is
    what is asked.
    """

    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{workspace_url}/", wait_until="networkidle")
    header = page.locator("header")
    assert header.get_by_role("link", name="Review a repository").count() == 0
    # Still stated on the page it belongs to, a screen-length below.
    assert _visible(page.get_by_role("link", name="Review a repository").first)

    page.goto(f"{workspace_url}/reviews", wait_until="networkidle")
    # The workspace topbar keeps its call to action at every width, which is the opposite of
    # what the landing header above does, and the difference is deliberate. A visitor reading
    # the landing page has the same link a screen below; somebody working has this bar and
    # nothing else, and the drawer is two taps. Below `sm` the wordtext beside the mark gives
    # up its room to pay for it — the chrome stops saying which product it is, which was
    # weighed and chosen rather than overlooked.
    #
    # So what is asked is not that the link stands down. It is that buying the room did not
    # break the bar's shape: the link is there, the bar does not wrap or scroll inside itself,
    # and the page does not go sideways. That is the guard this assertion used to be.
    assert _visible(page.locator("header").get_by_role("link", name="New review"))
    # `.first`, because the page's own `PageHeader` is a `<header>` too and the bar is the
    # one the shell renders above it. The bar itself is that header's single row.
    bar = page.locator("header").first.locator("> div").first
    assert bar.evaluate("e => e.scrollWidth <= e.clientWidth")
    assert page.evaluate(
        "() => document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )

    # And at a width that has room for the wordtext too.
    page.set_viewport_size({"width": 1440, "height": 960})
    assert _visible(page.locator("header").get_by_role("link", name="New review"))


#: Every tab of the review page. The docket is where a reviewer actually spends their time,
#: and the other three are different layouts — a list, a rendered report, a transcript.
WORKBENCH_TABS = ("Docket", "Delta", "Report", "Ask")


def test_the_workbench_fits_a_phone_on_every_tab(page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    """Two ways for a tab to not fit, and this asks about both.

    The page scrolling sideways is the visible one. The other is a box that overflows inside
    an ancestor which hides it — the finding is `overflow-hidden`, so a participant chip
    wider than the column was not escaping the panel, it was being sliced mid-identifier
    inside it, and the page measured clean the whole time.

    The example repository's names are short (`ports.Clock`), so this will not reproduce the
    identifier that found the bug; `overflow.test.tsx` holds that case. This one is about the
    layout itself, which does not depend on how long a name happens to be.
    """

    clipped = """() => {
      const out = [];
      for (const el of document.querySelectorAll('body *')) {
        const over = el.scrollWidth - el.clientWidth;
        if (over <= 1) continue;
        const style = getComputedStyle(el);
        if (style.overflowX !== 'hidden' && style.overflowX !== 'clip') continue;
        const names = el.className.baseVal ?? el.className ?? '';
        // Truncation and line clamping clip on purpose, and say so in the class list.
        if (/\\btruncate\\b|\\bsr-only\\b|line-clamp/.test(names)) continue;
        out.push(`${names.slice(0, 60)} by ${over}px`);
      }
      return out;
    }"""

    offenders: list[str] = []
    for width in PHONE_WIDTHS:
        page.set_viewport_size({"width": width, "height": 844})
        page.goto(review_url, wait_until="networkidle")
        for tab in WORKBENCH_TABS:
            page.get_by_role("tab", name=tab).first.click()
            page.wait_for_timeout(250)
            across = page.evaluate(
                "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            if across > 0:
                offenders.append(f"{tab} at {width}px scrolls across by {across}px")
            for hidden in page.evaluate(clipped):
                offenders.append(f"{tab} at {width}px clips {hidden}")

    assert not offenders, "; ".join(offenders)
