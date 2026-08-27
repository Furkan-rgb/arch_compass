"""The two columns of a numbered code block, measured in a browser.

`NumberedCode` in `frontend/src/ui/code.tsx` renders line numbers as a column beside the code
rather than as characters inside it, and its whole correctness is a claim about geometry: "the
two columns line up because they share a line height and neither of them wraps". jsdom applies
no stylesheet and computes no layout, so nothing in the vitest suite can read that claim — it
can see that the numbers are in a different element, and nothing more. The nine-pixel notch the
docket's verdict edge shipped with — `features/review/docket.tsx` measures it, at y=1073 against
a next row starting at y=1082 — survived precisely because the class drawing it was one nothing
could fail.

**Why this module exists now.** That component was lifted out of `SourceExcerpt` so a second
surface could use it: `features/review/lookup-result.tsx` draws the body of a `read_file`
lookup, which is 501 of the 955 lookups in the store, and which arrives from the tool with its
numbers baked into the text as a right-aligned gutter. Splitting that gutter off and handing
the numbers to this column is what lets the body be coloured as one Python document instead of
as a string that starts `  1  `. The extraction moved class lists between elements, which is
the kind of change that keeps every existing test green and moves a rectangle.

**What a browser here cannot reach, said plainly.** The review this suite runs is judged by
`DeterministicJudge`, which makes no tool calls at all — `recorded_judgement` in
`workflow/nodes.py` returns `None` the moment `subject.lookups` is empty — so no finding in
this fixture carries an investigation and the `read_file` rendering itself is not on screen
anywhere in this suite. What is on screen is the component that draws it, through the evidence
excerpts on every open finding. So this measures the shared column, and the transcript's own
structure is covered where a browser is not needed, in
`frontend/src/features/review/investigation.test.tsx`.
"""

from __future__ import annotations

import pytest

from tests.browser.harness import open_first_candidate, show_everything, wait_for_review

pytestmark = pytest.mark.browser

#: Where every line box and every number box is, in one pass over the page.
#:
#: A line of code is not an element — the block is one `<pre><code>` holding text and the
#: highlighter's spans — so a line's rectangle has to come from a `Range` over its characters.
#: This walks the text nodes once, indexes every character, and measures each line from its
#: first character to its last. A line with no characters (a blank line in the file) has no
#: rectangle and is reported as `null` rather than guessed at.
COLUMNS = """
() => {
  const blocks = [];
  for (const code of document.querySelectorAll('pre > code')) {
    const pre = code.parentElement;
    const gutter = pre.previousElementSibling;
    if (!gutter || gutter.getAttribute('aria-hidden') !== 'true') continue;

    const characters = [];
    const walker = document.createTreeWalker(code, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      for (let index = 0; index < node.data.length; index += 1) {
        characters.push([node, index, node.data[index]]);
      }
    }

    const lines = [];
    let start = 0;
    for (let index = 0; index <= characters.length; index += 1) {
      if (index === characters.length || characters[index][2] === '\\n') {
        if (index > start) {
          const range = document.createRange();
          range.setStart(characters[start][0], characters[start][1]);
          range.setEnd(characters[index - 1][0], characters[index - 1][1] + 1);
          const rect = range.getBoundingClientRect();
          lines.push({top: rect.top, bottom: rect.bottom});
        } else {
          lines.push(null);
        }
        start = index + 1;
      }
    }

    blocks.push({
      lines: lines,
      numbers: [...gutter.children].map((child) => {
        const rect = child.getBoundingClientRect();
        return {text: child.textContent, top: rect.top, bottom: rect.bottom};
      }),
    });
  }
  return blocks;
}
"""


def test_a_line_number_sits_on_the_line_it_numbers(page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    """Every number is beside its own line, and the two columns never drift apart.

    The failure this is written against is the quiet one. Both columns are flex children of a
    stretching row, so the *block* is the same height whatever happens inside it — a second
    leading on either column, or a gutter wide enough to wrap a four-digit number, moves every
    line after the first while leaving the block exactly where it was. Nothing but a rectangle
    can see that, and the excerpt is where a reader is being told which lines of a file a claim
    is about.

    Measured as centres rather than tops, because the number and the line it belongs to are set
    at the same size but are not the same glyphs; a centre is what "beside" means. The tolerance
    is one CSS pixel, which is four layout units — enough to absorb the 1/64px grid Chromium
    snaps a rectangle to, and far too small to absorb a line of drift.
    """

    wait_for_review(page, review_url)
    show_everything(page)
    open_first_candidate(page)
    page.locator("pre > code").first.wait_for(state="visible", timeout=20_000)

    blocks = page.evaluate(COLUMNS)
    assert blocks, "no numbered code block is on screen, so nothing here was measured"

    measured = 0
    for block in blocks:
        numbers, lines = block["numbers"], block["lines"]
        # One number to a line, before any of them is asked where it is. A column that has
        # fallen a row behind lines up on nothing, and reads as an off-by-one in the source.
        assert len(numbers) == len(lines), f"{len(numbers)} numbers over {len(lines)} lines"
        for index, (number, line) in enumerate(zip(numbers, lines, strict=True)):
            if line is None:
                # A blank line in the file. It has a number and no characters, so there is no
                # rectangle to compare against; the lines on either side of it carry the check.
                continue
            centre = (line["top"] + line["bottom"]) / 2
            beside = (number["top"] + number["bottom"]) / 2
            assert abs(centre - beside) <= 1.0, (
                f"line {index + 1} is numbered {number['text']!r} "
                f"{abs(centre - beside):.2f}px away from where the line is drawn"
            )
            measured += 1

    # A guard on the guard. Every assertion above is inside two loops, and a page that drew no
    # numbers or a walk that found no characters would pass all of them by running none.
    assert measured >= 3, f"only {measured} lines carried a rectangle to measure"
