"""The phone, checked by a browser that has a layout engine.

`src/features/review/overflow.test.tsx` asks the same question in jsdom, which has no
layout: every box there is 0x0, so it can assert about class lists and about what renders,
and it cannot assert that anything fits. This file is the half that measures — a real
Chromium at 390x844, reporting itself as a phone, over the same real review the rest of the
suite reads.

Two checks, both of which name what broke rather than that something did:

* **Nothing pushes the document sideways.** A phone may scroll down. Scrolling *across* is
  always a layout that did not fit, and this interface puts absolute paths, dotted
  identifiers and content hashes on screen in mono — any one of them, in a box that will
  not shrink, makes the column that wide and then the page.
* **Every row is a target.** 44px in the smaller dimension, which is the charter's fifth
  principle and the size of the part of a thumb that lands where it was aimed.

Both are written against roles, landmarks and `data-candidate`, because the copy on these
pages is being rewritten while this is written. That attribute is not read by the
application — `docket.tsx:671` is the only line outside a test that names it, and it writes
it; the keyboard walk steps through `finding.candidate.id` in React state. What makes it a
sound anchor is what it holds rather than who reads it: the candidate identity the walk
steps through and the key a decision is filed under, written by the row itself, so it
survives a redesign of the row. The older wording here claimed the application navigated by
the attribute, which was measured false.
Where a word appears it is one of the product's own nouns and it is matched as a
case-insensitive substring.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.browser.harness import (
    REVIEW_TIMEOUT_MS,
    close_dialog,
    open_first_candidate,
    open_judgement_context,
    show_everything,
    surface_tabs,
    wait_for_review,
)

pytestmark = pytest.mark.browser

#: The floor from the charter's fifth principle, and from WCAG 2.5.5 (AAA) / the platform
#: guidance both vendors publish. The smaller dimension of the hit area, not the larger.
TAP_TARGET_MINIMUM = 44

#: Sub-pixel slack. A box laid out at a fractional width can round to a hair past the
#: viewport without anybody being able to see or scroll it, and a check that fires on a
#: third of a pixel is a check that gets deleted.
TOLERANCE_PX = 1


# --------------------------------------------------------------------------------------
# Does this page fit?
# --------------------------------------------------------------------------------------

#: Asked in the browser because only the browser knows. Two independent questions, because
#: the two failures are different and each one hides the other.
#:
#: 1. *Can the document actually be scrolled sideways?* Asked by asking for a scroll and
#:    seeing whether one happened. The usual `scrollWidth > clientWidth` cannot answer it:
#:    under `overflow-x: clip` an element stops being a scroll container while still
#:    reporting the wider `scrollWidth`, so the subtraction says "scrolls by 60px" about a
#:    page that will not move a pixel. False positives are how a check stops being believed.
#:
#: 2. *Is anything reaching past the right edge anyway?* The inverse, and the worse bug.
#:    `clip` does not make a layout fit; it makes the part that did not fit unreachable —
#:    no scrollbar, no gesture, the content is simply gone. So the DOM is walked too, and a
#:    state is clean only when both answers are empty.
#:
#: The rule for question 2, which is the whole difficulty: an element that reaches past the
#: right edge is only the *document's* problem when nothing between it and the document
#: catches the overflow. So each candidate's containing-block chain is walked upwards, and
#: it is dropped the moment an ancestor is found with `overflow-x` other than `visible` —
#: that ancestor either scrolls it (a tab strip, a code block, a wide table, all of which
#: are allowed to be wider than the phone *inside themselves*) or clips it. The chain is the
#: containing-block chain rather than the parent chain, because an absolutely positioned box
#: is not clipped by an unpositioned ancestor and a fixed one is not clipped by anything.
#:
#: Note that the scroll container itself is never reported by this rule and does not need to
#: be: a tab strip that scrolls is laid out at its column's width, so its own right edge is
#: inside the viewport. Only its contents overflow, and its contents are exactly what the
#: ancestor walk drops.
_FITS = r"""(tolerance) => {
  const doc = document.documentElement;
  const viewport = doc.clientWidth;

  const scroller = document.scrollingElement || doc;
  const resting = scroller.scrollLeft;
  scroller.scrollLeft = 10000;
  const scrolled = Math.round(scroller.scrollLeft - resting);
  scroller.scrollLeft = resting;

  const describe = (el) => {
    const raw =
      typeof el.className === 'string'
        ? el.className
        : (el.className && el.className.baseVal) || '';
    const classes =
      raw.trim().split(/\s+/).filter(Boolean).slice(0, 8).map((c) => '.' + c).join('');
    const role = el.getAttribute('role') ? `[role=${el.getAttribute('role')}]` : '';
    const label = el.getAttribute('aria-label');
    return (
      el.tagName.toLowerCase() +
      (el.id ? '#' + el.id : '') +
      role +
      (label ? `[aria-label="${label.slice(0, 32)}"]` : '') +
      classes
    );
  };

  const ancestry = (el) => {
    const parts = [];
    let p = el.parentElement;
    for (; p && p !== document.body && parts.length < 3; p = p.parentElement) {
      parts.unshift(describe(p));
    }
    return parts.join(' > ');
  };

  // Walk the containing-block chain and return the first ancestor that catches the
  // overflow, or null when nothing does and the document is therefore the one wearing it.
  const caughtBy = (el) => {
    let position = getComputedStyle(el).position;
    if (position === 'fixed') return null;
    for (let p = el.parentElement; p && p !== document.documentElement; p = p.parentElement) {
      const style = getComputedStyle(p);
      const establishes =
        style.position !== 'static' ||
        style.transform !== 'none' ||
        style.filter !== 'none' ||
        style.perspective !== 'none' ||
        style.contain.includes('paint') ||
        style.contain.includes('layout');
      // An absolutely positioned box hangs off its nearest positioned ancestor, so every
      // unpositioned box in between is not its containing block and does not clip it.
      if (position === 'absolute' && !establishes) continue;
      if (style.overflowX !== 'visible') return p;
      if (style.position === 'fixed') return null;
      position = style.position === 'absolute' ? 'absolute' : 'static';
    }
    return null;
  };

  const wide = [];
  for (const el of document.querySelectorAll('body *')) {
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 && rect.height <= 0) continue;
    const over = rect.right - viewport;
    if (over <= tolerance) continue;
    if (!el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) continue;
    if (caughtBy(el)) continue;
    wide.push(el);
  }

  // Report the innermost offenders only. A box that is too wide makes every ancestor it
  // is in too wide, and printing the whole chain from `#root` down buries the one element
  // anybody can act on. What is left is the content that did not fit; `path` still names
  // the boxes around it.
  const innermost = wide.filter((el) => !wide.some((other) => other !== el && el.contains(other)));

  const offenders = innermost.slice(0, 12).map((el) => {
    const rect = el.getBoundingClientRect();
    return {
      selector: describe(el),
      path: ancestry(el),
      text: (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 80),
      width: rect.width,
      right: rect.right,
      over: rect.right - viewport,
    };
  });

  return {
    scrolled,
    viewport,
    offenders,
    suppressed: Math.max(0, innermost.length - offenders.length),
  };
}"""


def _settle(page, pause: int = 200) -> None:  # type: ignore[no-untyped-def]
    """Let the drawers finish arriving before measuring anything.

    A drawer slides in from `translateX(100%)`, which puts its right edge at twice the
    viewport for the length of the animation. Measured mid-flight it is an offender every
    time, and a flaky one. Infinite animations are excluded because the composing indicator
    pulses forever and `finished` on it never settles.
    """

    page.wait_for_timeout(pause)
    page.evaluate(
        """() => Promise.all(
             document.getAnimations()
               .filter((a) => a.effect && a.effect.getComputedTiming().iterations !== Infinity)
               .map((a) => a.finished.catch(() => {}))
           )"""
    )


def _fit_failures(page, state: str) -> list[str]:  # type: ignore[no-untyped-def]
    """Measure one state and phrase whatever is wrong with it in full.

    Everything a person needs at 2am is in the message: which state, which element, how
    wide it is, how far past the edge it reaches, what it says, and what it sits inside.
    """

    _settle(page)
    probe: dict[str, Any] = page.evaluate(_FITS, TOLERANCE_PX)
    viewport = probe["viewport"]
    failures: list[str] = []

    if probe["scrolled"] > 0:
        failures.append(
            f"{state}: the document scrolls sideways by {probe['scrolled']}px "
            f"at a {viewport}px viewport"
        )

    for item in probe["offenders"]:
        failures.append(
            f"{state}: {item['selector']} is {item['width']:.0f}px wide and its right edge "
            f"reaches {item['over']:.0f}px past the {viewport}px viewport"
            + (f"\n        inside {item['path']}" if item["path"] else "")
            + (f"\n        text: {item['text']!r}" if item["text"] else "")
        )

    if probe["suppressed"]:
        failures.append(f"{state}: and {probe['suppressed']} further element(s) past the edge")

    return failures


def _assert_fits(failures: list[str]) -> None:
    assert not failures, "\n  - " + "\n  - ".join(failures)


#: Everything reachable without a review. The workbench has its own test below, because
#: getting to each of its states is several clicks rather than a URL.
STANDING_PAGES = ("/", "/start")


@pytest.mark.parametrize("path", STANDING_PAGES)
def test_a_standing_page_fits_a_phone(phone_page, workspace_url: str, path: str) -> None:  # type: ignore[no-untyped-def]
    phone_page.goto(f"{workspace_url}{path}", wait_until="networkidle")
    _assert_fits(_fit_failures(phone_page, f"{path} at 390px"))


def test_the_fit_check_tells_a_scroller_apart_from_a_page_that_does_not_fit(  # type: ignore[no-untyped-def]
    phone_page, workspace_url: str
) -> None:
    """The rule above, proved on a real page rather than asserted in a comment.

    A check that never fires and a check that fires on everything are the same check, and
    the difference between them here is one rule — an element past the right edge is only
    reported when nothing between it and the document catches it. So: the landing page is
    clean, a box appended to it that nothing catches is reported, and the *same box* moved
    inside a scroll container is not. That last one is the tab strip, the code block and
    the wide table, which are all allowed to be wider than the phone inside themselves.
    """

    phone_page.goto(f"{workspace_url}/", wait_until="networkidle")
    assert not _fit_failures(phone_page, "the landing page")

    phone_page.evaluate(
        """() => {
             const wide = document.createElement('div');
             wide.id = 'deliberately-too-wide';
             wide.style.width = '900px';
             wide.style.height = '20px';
             wide.textContent = 'x'.repeat(200);
             document.body.append(wide);
           }"""
    )
    reported = _fit_failures(phone_page, "with a 900px box in ordinary flow")
    assert any("deliberately-too-wide" in line for line in reported), reported

    phone_page.evaluate(
        """() => {
             const scroller = document.createElement('div');
             scroller.style.overflowX = 'auto';
             document.body.append(scroller);
             scroller.append(document.getElementById('deliberately-too-wide'));
           }"""
    )
    assert not _fit_failures(phone_page, "with the same box inside a scroller")


def test_the_review_workbench_fits_a_phone_in_every_state(phone_page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    """Every surface, the queue, and the drawer behind a finding — measured in one pass.

    Collected rather than asserted state by state, because the first failure is rarely the
    only one and a redesign wants the whole list. The states are walked in the order a
    person walks them, which is also the order that keeps them reachable.
    """

    wait_for_review(phone_page, review_url)
    failures: list[str] = []

    # Each surface: a finding, a list of changes, a rendered report, a transcript. Four
    # different layouts, and the tab's own text is read off the tab rather than written
    # here, so renaming one renames it in the failure message too.
    tabs = surface_tabs(phone_page)
    count = tabs.count()
    assert count >= 2, "the review page no longer has a tablist of surfaces"
    for index in range(count):
        tab = tabs.nth(index)
        label = tab.inner_text().strip().splitlines()[0]
        tab.click()
        failures += _fit_failures(phone_page, f"review surface {label!r} at 390px")

    # The docket is the page at 390px exactly as it is at 1440px — there is no phone-only
    # sheet to open, which is the point of it being one column.
    tabs.first.click()
    failures += _fit_failures(phone_page, "review docket at 390px")

    # Widened to the filter that hides nothing, which is the state that has to hold the
    # most rows and the longest identifiers.
    show_everything(phone_page)
    failures += _fit_failures(phone_page, "review docket, all candidates, at 390px")

    # A row opens in place, under itself, with the list still around it.
    open_first_candidate(phone_page)
    failures += _fit_failures(phone_page, "review docket, finding open, at 390px")

    # The drawer, and each of its own tabs — provenance is where the longest
    # machine-produced strings in the product live, so it is the likeliest to give way.
    #
    # Worth knowing when reading a failure here: a drawer sets `overflow: hidden` on the
    # body while it is open, so the "does the document scroll" half of the check is
    # trivially clean in these states and the DOM walk is doing all the work.
    drawer = open_judgement_context(phone_page)
    drawer_tabs = drawer.get_by_role("tab")
    assert drawer_tabs.count() >= 2, "the judgement context no longer has tabs to walk"
    for index in range(drawer_tabs.count()):
        tab = drawer_tabs.nth(index)
        label = tab.inner_text().strip().splitlines()[0]
        tab.click()
        failures += _fit_failures(phone_page, f"judgement context {label!r} at 390px")
    close_dialog(phone_page)

    _assert_fits(failures)


# --------------------------------------------------------------------------------------
# Can a thumb hit it?
# --------------------------------------------------------------------------------------

#: The exemptions are in here rather than in a list of selectors in Python, because each
#: one is a property of the element at the moment it is measured and only the browser can
#: see it. Each returns the reason it is exempt, and the reasons are reported alongside the
#: violations so the exemption list stays visible rather than becoming somewhere to hide.
_TAP_TARGETS = r"""(minimum) => {
  const interactive = 'button, a[href], summary, [role="button"], [role="tab"]';

  const label = (el) => {
    const aria = el.getAttribute('aria-label');
    if (aria && aria.trim()) return aria.trim();
    const by = el.getAttribute('aria-labelledby');
    if (by) {
      const text = by
        .split(/\s+/)
        .map((id) => (document.getElementById(id) || {}).textContent || '')
        .join(' ')
        .replace(/\s+/g, ' ')
        .trim();
      if (text) return text.slice(0, 60);
    }
    const own = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
    if (own) return own.slice(0, 60);
    const title = el.getAttribute('title');
    if (title) return title.trim();
    return '(no accessible name)';
  };

  const describe = (el) => {
    const raw =
      typeof el.className === 'string'
        ? el.className
        : (el.className && el.className.baseVal) || '';
    const classes =
      raw.trim().split(/\s+/).filter(Boolean).slice(0, 6).map((c) => '.' + c).join('');
    return el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + classes;
  };

  const exemption = (el) => {
    const style = getComputedStyle(el);
    const raw = typeof el.className === 'string' ? el.className : '';

    // Visually hidden until focused. A skip link is 1px on purpose and is a target for a
    // keyboard, which has no thumb.
    if (/\bsr-only\b/.test(raw)) return 'visually hidden until focused';

    // Nothing to hit: a disabled control cannot be activated, and one hidden from the
    // accessibility tree is not being offered.
    if (el.hasAttribute('disabled') || el.getAttribute('aria-disabled') === 'true') {
      return 'disabled';
    }
    if (el.closest('[aria-hidden="true"]')) return 'hidden from the accessibility tree';

    // WCAG 2.5.8's own exception, and the only one that is about design rather than about
    // the element not being a target at all: a control set inline in a sentence is sized by
    // the text it sits in, and padding it out would break the line. Both halves are
    // required — it must compute to `display: inline`, and there must be real running text
    // beside it — so a button styled to look like a link does not slip through.
    //
    // The tag used to be the third half, and it was `A`. The rule it was aimed at is a real
    // control disguised as a link, and `CandidateRef` in `ui/prose.tsx` is the other way
    // round: a citation inside a model's sentence, which is an inline link in every sense
    // WCAG means and has no `href` only because the docket's open row is page state rather
    // than a URL. Padding it out is not the alternative — a reference is measured on its
    // *smaller* dimension, and a leaf of five characters cannot reach 44px across without
    // spacing the sentence out around it. So the exemption is about the shape and the
    // context, and `display: inline` plus running text beside it is the whole of the shape:
    // a `<button>` is `inline-block` by default and takes a deliberate class to get here.
    if ((el.tagName === 'A' || el.tagName === 'BUTTON') && style.display === 'inline') {
      const parent = el.parentElement;
      const prose = parent
        ? Array.from(parent.childNodes).some(
            (node) => node.nodeType === 3 && node.textContent.trim().length > 1,
          )
        : false;
      if (prose) return 'inline control in running text (WCAG 2.5.8 inline exception)';
    }

    return null;
  };

  const violations = [];
  const exempt = [];
  const seen = new Set();

  for (const el of document.querySelectorAll(interactive)) {
    if (!el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    const smaller = Math.min(rect.width, rect.height);
    if (smaller + 0.5 >= minimum) continue;

    const entry = {
      name: label(el),
      selector: describe(el),
      width: rect.width,
      height: rect.height,
    };
    const reason = exemption(el);
    if (reason) {
      exempt.push({ ...entry, reason });
      continue;
    }
    // One row of a list that repeats a shape thirty times is one finding, not thirty.
    const key = entry.selector + '|' + Math.round(rect.width) + 'x' + Math.round(rect.height);
    if (seen.has(key)) continue;
    seen.add(key);
    violations.push(entry);
  }

  return { violations, exempt };
}"""


def _tap_failures(page, state: str) -> tuple[list[str], list[str]]:  # type: ignore[no-untyped-def]
    _settle(page)
    probe: dict[str, Any] = page.evaluate(_TAP_TARGETS, TAP_TARGET_MINIMUM)
    failures = [
        f"{state}: {item['name']!r} is {item['width']:.0f}x{item['height']:.0f}px "
        f"({min(item['width'], item['height']):.0f}px in its smaller dimension, "
        f"needs {TAP_TARGET_MINIMUM}px) — {item['selector']}"
        for item in probe["violations"]
    ]
    waived = [
        f"{state}: {item['name']!r} {item['width']:.0f}x{item['height']:.0f}px — {item['reason']}"
        for item in probe["exempt"]
    ]
    return failures, waived


def test_every_tap_target_in_the_review_is_wide_enough_for_a_thumb(  # type: ignore[no-untyped-def]
    phone_page, review_url: str
) -> None:
    """ "Every row is a target": 44px minimum, on the surface where the work happens.

    The accessible name is computed here rather than taken from Playwright's accessibility
    snapshot: this is an approximation of the real algorithm (`aria-label`, then
    `aria-labelledby`, then text, then `title`), which is enough to say *which* control is
    too small and cheap enough to run on every state without a round trip per element.
    """

    wait_for_review(phone_page, review_url)
    phone_page.locator("[role='tabpanel']").first.wait_for(
        state="visible", timeout=REVIEW_TIMEOUT_MS
    )

    failures: list[str] = []
    waived: list[str] = []
    seen: set[str] = set()

    def measure(state: str) -> None:
        found, exempt = _tap_failures(phone_page, state)
        # The header, the tablist and the decision bar are on screen in every state below.
        # Reporting each of them four times turns thirteen problems into fifty lines.
        for line in found + exempt:
            control = line.split(": ", 1)[1]
            if control in seen:
                continue
            seen.add(control)
            (failures if line in found else waived).append(line)

    # The three states where a phone is actually being tapped: the docket as it opens, an
    # open finding with its decision bar, and the drawer that audits the judgement.
    measure("review docket at 390px")

    open_first_candidate(phone_page)
    measure("review docket, finding open, at 390px")

    open_judgement_context(phone_page)
    measure("judgement context at 390px")
    close_dialog(phone_page)

    # The Ask surface, which is the fourth place on this page a thumb lands and was the one
    # state this sweep never reached. It is here because its composer now holds its button
    # *inside* the field — the arrangement where a target is most easily squeezed to fit the
    # box around it — and because the openers beside it are `sm` controls that reach the floor
    # only through `pointer-coarse`.
    #
    # The box is typed into first, and that is not decoration. `Ask` is disabled while there
    # is nothing to send, `exemption` above quite correctly refuses to measure a control that
    # cannot be activated, and a state that only ever shows the disabled one measures the
    # composer's button never. A word in the field is what puts it on screen as a target.
    surface_tabs(phone_page).last.click()
    composer = phone_page.locator("textarea[aria-label]").first
    composer.wait_for(state="visible", timeout=20_000)
    composer.fill("Why is the gateway held?")
    measure("ask surface at 390px")

    # Kept in the output rather than swallowed: an exemption nobody ever reads is a hole
    # rather than an exemption. pytest shows it on failure, or on demand with `-s`.
    print("\nTap targets exempted with a reason:")
    for line in waived or ["(none)"]:
        print(f"  {line}")

    assert not failures, "\n  - " + "\n  - ".join(failures)


@pytest.mark.parametrize("width", (1024, 1180))
def test_the_hero_puts_the_judgement_beside_the_copy_on_a_tablet(  # type: ignore[no-untyped-def]
    browser, workspace_url: str, width: int
) -> None:
    """The one thing the landing page exists to show, above the fold on a tablet.

    The split was gated behind `xl`, so no tablet ever saw it: at 1024 the copy ran the full
    width with the right half empty, the atlas stacked underneath it, and the judgement — the
    specimen the hero is built around — sat a screen and a half down. The section went from
    880px on a desk to 1712px on an iPad.

    Two assertions, because fixing the first alone broke the second: the card has to sit
    beside the copy, and the section has to be tall enough to hold it. The section is
    `overflow-hidden`, so a figure that outgrows it is not pushed down, it is cut off — which
    is what a floor chosen before the card was measured did to its last three lines.

    A real context rather than a narrowed desktop, for the reason `phone_page` gives.
    """

    context = browser.new_context(
        viewport={"width": width, "height": 900}, device_scale_factor=1
    )
    page = context.new_page()
    try:
        page.goto(f"{workspace_url}/", wait_until="networkidle")
        page.wait_for_selector("h1")
        geometry = page.evaluate(
            """() => {
                 const section = document.querySelector('section');
                 const heading = document.querySelector('h1');
                 const card = Array.from(document.querySelectorAll('div')).find(
                   (node) =>
                     /GUIDANCE/.test(node.innerText || '') &&
                     node.getBoundingClientRect().width < 500,
                 );
                 if (!section || !heading || !card) return null;
                 const box = (node) => {
                   const rect = node.getBoundingClientRect();
                   return { left: rect.left, right: rect.right, bottom: rect.bottom };
                 };
                 return {
                   section: box(section),
                   heading: box(heading),
                   card: box(card),
                   sectionHeight: section.getBoundingClientRect().height,
                 };
               }"""
        )
        assert geometry is not None, "the hero, its heading and its specimen must all render"

        # Beside, not below: the card starts to the right of where the copy ends.
        assert geometry["card"]["left"] >= geometry["heading"]["right"], (
            f"at {width}px the judgement is not beside the copy — card starts at "
            f"{geometry['card']['left']:.0f} and the headline ends at "
            f"{geometry['heading']['right']:.0f}"
        )
        # And whole: the section is `overflow-hidden`, so this is the difference between
        # the card being on screen and its last lines being cut off.
        assert geometry["card"]["bottom"] <= geometry["section"]["bottom"], (
            f"at {width}px the judgement is clipped by "
            f"{geometry['card']['bottom'] - geometry['section']['bottom']:.0f}px — the hero "
            "needs a floor that the specimen fits inside"
        )
        # A stacked hero is roughly twice a split one, which is the shape of the regression.
        assert geometry["sectionHeight"] < 1200, (
            f"at {width}px the hero is {geometry['sectionHeight']:.0f}px tall, which is the "
            "stacked layout rather than the split one"
        )
    finally:
        context.close()


# --------------------------------------------------------------------------------------
# Where the way out of a held finding sits, on the width where the rail stacks
# --------------------------------------------------------------------------------------

#: How far **Answer it** may sit from the question it answers, in CSS pixels, at 390x844.
#:
#: Four, today: `mt-1` on the control and nothing else between it and the `<p>` its
#: `aria-describedby` names. The bound is a line box rather than the measurement, so an honest
#: change of margin does not fail it and a change of *place* does — which is the whole subject.
#:
#: `docs/known-defects.md` carries the other half of this: below `lg` the rail stacks under the
#: argument, so the control is reached after the model's paragraph. What that entry got wrong
#: for two passes was how far. It reasoned from a 2,139-character argument standing above an
#: **Answer it**, and no held finding can carry one:
#: `FindingOutput.the_verdict_carries_what_it_is_allowed_to` in `reasoning/adapters/langchain.py`
#: refuses a hinge on any verdict but `held`, and `finding-detail.tsx` draws no control without
#: a hinge. The arguments this control can ever stand under run 156 to 971 characters across the
#: 69 recorded held judgements, and swept over all 69 with their own hinges it lands 275px to
#: 956px below the *top* of the argument, median 624px — and 4px below the question.
ANSWER_IT_FROM_ITS_QUESTION_PX = 26


def test_the_way_out_of_a_held_finding_is_the_first_control_a_phone_reaches(  # type: ignore[no-untyped-def]
    phone_page, review_url: str
) -> None:
    """Where **Answer it** sits below `lg`, as three rectangles instead of an argument.

    Below `lg` the Judged band is one column and the rail stacks under the argument, so
    everything in the rail is reached by scrolling past the model's paragraph. That is the cost
    of an open row and every verdict pays it. What this pins is that the held row's extra
    control is not the one being buried: it arrives first — before **Judgement context**, and
    long before Accept / Park / Waive, which every row carries — and it arrives attached to the
    question it answers rather than a screen away from it.

    The distances to the other two controls are asserted as an *order* and not as a budget.
    They are whatever the argument, the readings and the excerpts of a given finding come to,
    and a bound on them would be a bound on how much the model wrote.

    jsdom holds the other half, in `features/review/finding-detail.test.tsx`: a cleared finding
    has no hinge and so no control here at all, which is why nothing in this layout may depend
    on one existing.
    """

    wait_for_review(phone_page, review_url)
    show_everything(phone_page)
    open_first_candidate(phone_page)
    phone_page.locator("[class*='max-w-[58ch]']").first.wait_for(
        state="visible", timeout=REVIEW_TIMEOUT_MS
    )
    phone_page.evaluate("() => document.fonts.ready")

    where = phone_page.evaluate(
        """() => {
             const argument = document.querySelector(
               '[class*="max-w-[58ch]"][class*="text-[16px]"]',
             );
             if (!argument) return null;
             const named = (pattern) =>
               [...document.querySelectorAll("button")].filter((control) =>
                 pattern.test((control.textContent || "").trim()),
               );
             const ways = named(/^Answer it/);
             const answer = ways[0];
             if (!answer) return null;
             const question = document.getElementById(answer.getAttribute("aria-describedby"));
             if (!question) return null;
             const context = named(/judgement context/i)[0];
             const decisions = named(/^(Accept and act|Park|Waive)$/);
             const top = (node) => node.getBoundingClientRect().top;
             const bottom = (node) => node.getBoundingClientRect().bottom;
             return {
               ways: ways.length,
               fromItsQuestion: top(answer) - bottom(question),
               belowArgument: top(answer) - bottom(argument),
               contextBelowArgument: context ? top(context) - bottom(argument) : null,
               decisionsBelowArgument: decisions.length
                 ? Math.min(...decisions.map(top)) - bottom(argument)
                 : null,
             };
           }"""
    )
    assert where is not None, "the first row of this review is not a held finding with a way out"

    # One control for one action. The repair this test replaces proposed a second one on the
    # phone, which `features/review/review-workbench.test.tsx` holds the line against elsewhere.
    assert where["ways"] == 1, f"{where['ways']} ways out of one held finding"

    assert where["fromItsQuestion"] <= ANSWER_IT_FROM_ITS_QUESTION_PX, (
        f"**Answer it** is {where['fromItsQuestion']:.0f}px below the question it answers, past "
        f"the {ANSWER_IT_FROM_ITS_QUESTION_PX}px this layout allows — the pair reads as one "
        "thing or it reads as a control in a corner"
    )

    assert where["contextBelowArgument"] is not None, "an open finding has a Judgement context"
    assert where["decisionsBelowArgument"] is not None, "an open finding has a decision bar"

    # **Below the argument, before the ordering.** The three distances are signed, and an
    # ordering is a *relative* claim: it survives the one term this test is really about going
    # negative, because the other two are measured from the same edge and fall with it. That is
    # not a hypothetical. Move the rail above `<ModelProse>` in `finding-detail.tsx`, rebuild
    # the bundle and run this test, and it passed with **Answer it** drawn above the model's
    # paragraph on a phone. `docs/known-defects.md` names this test as what stops that shape
    # changing, so the shape has to be what it measures. jsdom catches the same move as a
    # document-order failure (`finding-detail.test.tsx`, "puts the rail after the argument");
    # this is the half that knows the rail was *drawn* after it.
    #
    # Measured, on this review's first held row at 390x844 with the rail hoisted: **Answer it**
    # at **-202.17px**, **Judgement context** at **+631.38px**, the decision bar at
    # **+1,625.55px**, ascending — one term negative and two positive, and the ordering
    # assertion below is satisfied by all three. Only the first term *can* go negative: the
    # other two are drawn below the grid that the rail and the argument share, so hoisting the
    # rail inside that grid cannot lift them past it. The argument on this row is 79.17px tall,
    # which is the whole of why the first distance is 202px, and it is why the -1,058 / -938 /
    # 682 this comment used to carry does not reproduce here — that triple was taken over a
    # different row, and a distance measured against one judgement is a fact about that
    # judgement's length.
    #
    # Zero, not a margin: the two boxes are the argument and a control below it, and any
    # positive gap is a layout decision rather than a property. What is being refused is a
    # negative one.
    assert where["belowArgument"] >= 0, (
        f"**Answer it** is drawn {-where['belowArgument']:.0f}px *above* the bottom of the "
        "model's argument — the rail is painting before the paragraph it is a margin note on, "
        "which is the stacked reading order this layout is built on running backwards"
    )
    assert (
        where["belowArgument"] < where["contextBelowArgument"] < where["decisionsBelowArgument"]
    ), (
        "on a phone the way out of a held finding is reached before the controls every row "
        f"carries: **Answer it** at {where['belowArgument']:.0f}px below the argument, "
        f"**Judgement context** at {where['contextBelowArgument']:.0f}px, the decision bar at "
        f"{where['decisionsBelowArgument']:.0f}px"
    )


#: The widest run of characters the model has ever written that a line breaker may not split.
#:
#: `(src.audiobook.preparation.providers.base.NarrationPreparationProvider)` — 71 characters,
#: brackets included, because UAX #14 forbids a break after an opening bracket and before a
#: closing one. It set **541.7px** in Onest at the reading size, against the **324px** column a
#: phone gives the model's paragraph — a reading that has not been repeated since the face moved
#: to IBM Plex Sans, and which `docs/known-defects.md` carries as the first of the sweeps to
#: re-run. `ui/prose.test-corpus.ts` carries the measurement and the recipe; this file only needs
#: the string, and the string is what it asserts about. Nothing here depends on the figure.
WIDEST_UNBREAKABLE_TOKEN = "(src.audiobook.preparation.providers.base.NarrationPreparationProvider)"

#: Put the widest recorded name into the argument and report what the block is drawn at.
#:
#: The text is replaced on the paragraph the component rendered rather than injected into a box
#: of the test's own, because what is under test is the *shipped* block: its measure, its
#: wrapping and every ancestor between it and the document. React is not re-rendering while this
#: runs, so the node keeps the class list it was given.
_WIDEST_NAME_IN_THE_ARGUMENT = """(token) => {
  const argument = document.querySelector('[class*="max-w-[58ch]"][class*="text-[16px]"]');
  if (!argument) return null;
  const block = argument.querySelector('p');
  if (!block) return null;
  block.textContent = `The candidate is ${token} and it has one implementation here.`;
  const style = getComputedStyle(block);
  return {
    overflowWrap: style.overflowWrap,
    wordBreak: style.wordBreak,
    column: block.clientWidth,
    ink: block.scrollWidth,
  };
}"""

#: The same block with the permission withdrawn, which is what deleting the class does.
_WITHOUT_THE_BREAK = """() => {
  const block = document.querySelector(
    '[class*="max-w-[58ch]"][class*="text-[16px]"] p',
  );
  block.style.overflowWrap = 'normal';
  block.style.wordBreak = 'normal';
  return { column: block.clientWidth, ink: block.scrollWidth };
}"""


def test_a_name_wider_than_the_column_folds_instead_of_widening_the_phone(  # type: ignore[no-untyped-def]
    phone_page, review_url: str
) -> None:
    """The one class that keeps a qualified name inside a 324px column, measured where it acts.

    `ModelProse` sets `wrap-anywhere` on every block it draws. Take it off and 48 of the 375
    recorded judgements draw wider than the column a phone gives that block, the worst by 218px:
    the widest unbreakable run the model has written set 541.7px against a 324px column in Onest.
    Deleting
    the class was silent in the whole suite. It was
    silent *here* too, and for a reason worth naming rather than fixing quietly: the fit check
    above already measures horizontal overflow on every state of this workbench at 390px, and
    the deterministic review it drives has never produced a name long enough to reach it. A
    guarantee held by what one fixture happens to say is not a guarantee, so the content is
    supplied instead of hoped for.

    The control is the second half and it is what makes the first half mean anything: the same
    block, the same measurement, with the permission withdrawn — if that does not report, the
    assertion above is passing on a page where nothing was ever at risk.

    `ui/prose.test.tsx` holds the other half, which is that the block declares the permission at
    all. This is the half that knows nothing between the paragraph and the document takes it
    away again.
    """

    wait_for_review(phone_page, review_url)
    show_everything(phone_page)
    open_first_candidate(phone_page)
    phone_page.locator("[class*='max-w-[58ch]']").first.wait_for(
        state="visible", timeout=REVIEW_TIMEOUT_MS
    )
    # The shipped face has to be in before any width is read: `font-display: swap` otherwise
    # answers with a fallback whose zero is 0.6299em, and every figure is five per cent wrong.
    phone_page.evaluate("() => document.fonts.ready")

    drawn = phone_page.evaluate(_WIDEST_NAME_IN_THE_ARGUMENT, WIDEST_UNBREAKABLE_TOKEN)
    assert drawn is not None, "no block at the reading size in an open finding"
    assert drawn["column"] <= 390, (
        f"the argument is {drawn['column']}px wide inside a 390px phone, so the column this "
        "test is about is not the one on screen"
    )

    assert drawn["ink"] <= drawn["column"], (
        f"the model's paragraph draws {drawn['ink']}px of text inside a {drawn['column']}px "
        f"column: a {WIDEST_UNBREAKABLE_TOKEN!r} the line breaker may not split has pushed the "
        "column open instead of folding inside it"
    )
    _assert_fits(_fit_failures(phone_page, "a finding whose argument names the widest candidate"))

    # And the check is not vacuous. Take the permission away and the same page reports.
    without = phone_page.evaluate(_WITHOUT_THE_BREAK)
    assert without["ink"] > without["column"], (
        "with the anywhere-break withdrawn the paragraph still fits its column, so the "
        "assertion above was never at risk on this row and proves nothing about the class"
    )


def test_the_keyboard_hints_never_paint_where_there_is_no_keyboard(  # type: ignore[no-untyped-def]
    phone_page, review_url: str
) -> None:
    """The docket's key caps, on a screen with a thumb in front of it.

    They are guarded twice and this measures the second guard, because the first one cannot
    be measured here and cannot be trusted alone. `useHasKeyboard` keeps the caps out of the
    DOM, which is worth having — eleven nodes a screen reader would otherwise announce as
    keys nobody can press — but it seeds its state from `matchMedia` during render and falls
    back to `true` where the API is missing, so there is a window where it answers for a
    keyboard that is not there. Under a device emulator that window opens on roughly one cold
    load in three, which is how this was found: a set of screenshots taken for a design review
    had `j k walk A P W decide` sitting above the findings on a phone.

    So the stylesheet backstops the hook, and this test lies to the hook to prove it. Every
    media query is made to answer `true` before any page script runs — the worst case the
    fallback and the render-time seed can produce together — and the assertion is that the
    caps are still not *painted*. jsdom applies no stylesheet, so no vitest test can see this;
    a real engine resolving a real media query is the only thing that can.
    """
    page = phone_page
    page.context.add_init_script(
        "const real = window.matchMedia.bind(window);"
        "window.matchMedia = (q) => {"
        "  const m = real(q);"
        "  return new Proxy(m, { get: (t, k) => k === 'matches' ? true :"
        "    (typeof t[k] === 'function' ? t[k].bind(t) : t[k]) });"
        "};"
    )
    page.goto(review_url, wait_until="networkidle")
    page.wait_for_timeout(1200)

    assert page.evaluate("() => matchMedia('(hover: hover) and (pointer: fine)').matches"), (
        "the lie did not take, so this run would pass for the wrong reason"
    )

    painted = [
        cap.inner_text().strip()
        for cap in page.locator("kbd").all()
        if cap.is_visible()
    ]
    assert not painted, f"key caps painted on a phone: {painted}"
