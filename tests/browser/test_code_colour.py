"""The syntax palette as a browser actually paints it.

Every claim `frontend/src/styles.css` makes about code colour is a claim about a *rule* — a
selector list, a cascade, a `var()` that has to resolve differently under `data-theme`. jsdom
applies no stylesheet at all, so the vitest suite can see the hex codes in the file and the
class names in the markup and nothing that connects them: `frontend/src/ui/tokens.test.ts`
measures the four values as arithmetic and cannot tell whether a single one of them ever
reaches a token on screen.

That gap is exactly where this branch's other defect lived — the nine-pixel notch in the
docket's verdict edge, drawn by a class nothing could fail. A selector list is the same shape
of risk: `.hljs-params` was added to the `--code-name` group because the role covered 3.22% of
a block and the parameter list is 4.29% more, and a typo in that list, a rule ordering that
lets `.hljs-string` win inside a signature, or a `--code-name` that stops resolving would all
leave every existing test green and every signature grey.

**What this can and cannot reach.** The review this suite runs is judged by
`DeterministicJudge`, which makes no tool calls, so no finding carries an investigation and the
11px lookup transcript is not on screen anywhere in this suite — the same limit
`test_lookups.py` states. What is on screen is the same highlighted markup through the evidence
excerpt on every open finding, drawn by the same `NumberedCode` and coloured by the same rules.
So this measures the palette on the 12px surface and makes no claim about the 11px one.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from tests.browser.harness import REVIEW_TIMEOUT_MS, show_everything, wait_for_review

pytestmark = pytest.mark.browser

#: Every highlighted token on the page, as the colour a browser resolved for it.
#:
#: `getComputedStyle().color` is the whole point: it is the end of the cascade, with the
#: selector list applied, `var(--code-…)` resolved against whichever theme block won, and the
#: inherited value filled in for a span no rule matched. Reading the class attribute would
#: prove only that highlight.js ran, which is what vitest already knows.
#:
#: `pre` is sampled too, and it is not decoration. It is what the 48.11% of a block that
#: carries no class at all is drawn in, so it is the value every coloured role has to be
#: distinguishable from — and the value a role collapses to when its own rule stops matching.
PAINTED = """
() => {
  const roles = {};
  const add = (key, element) => {
    (roles[key] ||= []).push(getComputedStyle(element).color);
  };
  for (const code of document.querySelectorAll('pre > code')) {
    add('plain', code.parentElement);
    for (const span of code.querySelectorAll('span')) {
      // The innermost span owns the character: highlight.js nests a `hljs-built_in` inside a
      // `hljs-params`, and it is the inner one a reader sees.
      if (span.querySelector('span')) continue;
      for (const name of span.classList) {
        if (name.startsWith('hljs-')) add(name, span);
      }
    }
  }
  return roles;
}
"""


def _one(roles: dict[str, list[str]], name: str) -> str:
    """The single colour a role is painted in, or a failure naming what was found instead."""

    painted = roles.get(name)
    assert painted, f"no {name} token is on screen, so nothing about it was measured"
    distinct = set(painted)
    assert len(distinct) == 1, f"{name} is painted {len(distinct)} different colours: {distinct}"
    return painted[0]


def _open_until(page, wanted: str) -> dict[str, list[str]]:  # type: ignore[no-untyped-def]
    """Every row of the docket opened in turn, until one of them draws the role asked for.

    A finding's evidence is whatever the detector selected out of the repository under review,
    so which token classes reach the page is a property of that repository and not of this
    suite. The first row's excerpt happens to hold no parameter list at all. Opening rows until
    one does is what keeps this a test of the stylesheet rather than a test of which candidate
    the deterministic judge happened to rank first.
    """

    rows = page.locator("[data-candidate]")
    rows.first.wait_for(state="visible", timeout=REVIEW_TIMEOUT_MS)
    code = page.locator("pre > code")
    for index in range(rows.count()):
        rows.nth(index).click()
        try:
            code.first.wait_for(state="visible", timeout=10_000)
        except PlaywrightTimeout:
            # A finding whose evidence carries no excerpt. There is nothing to sample and it is
            # not a failure of anything this file is about.
            rows.nth(index).click()
            continue
        roles = page.evaluate(PAINTED)
        if wanted in roles:
            return roles
        # A row is a toggle, and two open rows would mix two findings' excerpts into one
        # sample, so this one closes before the next one opens.
        rows.nth(index).click()
        code.first.wait_for(state="detached", timeout=10_000)
    return {}


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_a_parameter_is_painted_as_a_name(page, review_url: str, theme: str) -> None:  # type: ignore[no-untyped-def]
    """A parameter wears the colour a definition wears, and no other role's.

    This is the one half of the palette change that is a rule rather than a value, and it is
    the half arithmetic cannot see. `--code-name` used to mean "what somebody named" and reach
    only `hljs-title` and its siblings; it now means "where a name is bound", which is what
    puts `hljs-params` in the group. Measured against the resolved colour of `hljs-title` in
    the same document rather than against a hex code, so this stays true when the palette moves
    again — what it holds is that the two are one role, which is the claim the selector makes.

    Both themes, because the value comes through `var(--code-name)` and the dark override is
    declared twice in `styles.css` — once under `prefers-color-scheme` and once under the
    attribute this sets. A palette edited in one of those and not the other is wrong for
    exactly half its readers, which is what `ui/tokens.test.ts` polices in the file and this
    confirms on screen.
    """

    wait_for_review(page, review_url)
    page.evaluate(f"document.documentElement.setAttribute('data-theme', {theme!r})")
    show_everything(page)

    roles = _open_until(page, "hljs-params")
    name = _one(roles, "hljs-title")
    assert _one(roles, "hljs-params") == name, (
        f"{theme}: a parameter is painted {_one(roles, 'hljs-params')} "
        f"where a definition is painted {name}"
    )

    # And that the group it joined is still a group of one colour and not the block's ink. A
    # `--code-name` that failed to resolve would make both of the assertions above pass by
    # making every span inherit the same grey.
    assert name != _one(roles, "plain"), (
        f"{theme}: a name is painted {name}, which is what the uncoloured half of the block is "
        "painted — the name rule is not reaching anything"
    )
    for other in ("hljs-keyword", "hljs-string"):
        assert _one(roles, other) != name, (
            f"{theme}: {other} and hljs-title are both painted {name}"
        )
