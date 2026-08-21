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

Both are written against roles, landmarks and the data attributes the application itself
navigates with, because the copy on these pages is being rewritten while this is written.
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
    // the element not being a target at all: a link set inline in a sentence is sized by
    // the text it sits in, and padding it out would break the line. Both halves are
    // required — it must compute to `display: inline`, and there must be real running text
    // beside it — so a button styled to look like a link does not slip through.
    if (el.tagName === 'A' && style.display === 'inline') {
      const parent = el.parentElement;
      const prose = parent
        ? Array.from(parent.childNodes).some(
            (node) => node.nodeType === 3 && node.textContent.trim().length > 1,
          )
        : false;
      if (prose) return 'inline link in running text (WCAG 2.5.8 inline exception)';
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

    # Kept in the output rather than swallowed: an exemption nobody ever reads is a hole
    # rather than an exemption. pytest shows it on failure, or on demand with `-s`.
    print("\nTap targets exempted with a reason:")
    for line in waived or ["(none)"]:
        print(f"  {line}")

    assert not failures, "\n  - " + "\n  - ".join(failures)
