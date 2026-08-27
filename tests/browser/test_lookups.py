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

**The review carries no investigation of its own, so one is injected.** It is judged by
`DeterministicJudge`, which makes no tool calls at all — `recorded_judgement` in
`workflow/nodes.py` returns `None` the moment `subject.lookups` is empty — so no finding in
this fixture reaches the "Looked up" fold on its own. The first test below therefore measures
the shared column through the evidence excerpt on an open finding, which is real and needs
nothing injected. The second needs the fold itself, and takes the route
`test_policies_grid.py` opened for the same reason: the review is the real review, the bundle
is the real bundle, the components and the stylesheet are the real ones, and one field of one
JSON response is replaced on the way past.

The transcript's own structure — which element a string is in — is covered where a browser is
not needed, in `frontend/src/features/review/investigation.test.tsx`.
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


#: One investigation holding six real lookups, covering every way the fold draws a result.
#:
#: Every row is a lookup that happened, read out of a read-only copy of
#: `.archcompass/workspace.sqlite3` — `core_review_snapshots.review_json ->
#: investigation_manifest[].lookups[]`, 955 lookups over 7 reviews — with its own stored
#: `arguments` beside it. Five of the six results are the stored string **verbatim**: not
#: trimmed, not tidied, not one word moved. Only `search_policies` is cut, to its first four
#: lines, because the one `search_policies` result in the store is 11,205 characters. Nothing
#: here is invented and nothing is a shape somebody imagined the tools might produce.
#:
#: Six rows in one fold is the point: the defect below was never visible in any single result,
#: only in two of them beside each other. Which row, what it draws, and why that one of the
#: many that would have done:
#:
#: * `read_file` -> `NumberedCode` and `ResultNote`. The shortest of the 382 stored reads that
#:   end on the tool's own bracketed sentence, at 479 characters, so the note is one a tool
#:   really wrote rather than one composed to look like it.
#: * `grep` with matches -> `PathList`. A two-path result, so the list draws more than one row.
#: * `glob` -> `PathList` again, off a Python list repr rather than off lines. A three-path
#:   result, for the same reason.
#: * `related_code` -> `NodeRowsResult`. The shortest of the 39, at 174 characters, and it
#:   happens to carry one of each of the two rows that shape has: a node and the arrow under it.
#: * `search_policies` -> `PlainResult`, coloured as Markdown.
#: * `grep` with nothing -> `NoResult`. `No matches found`, which is 38 of the 369 stored greps.
#:
#: That is five components over six rows, and the duplicate is deliberate: a `grep` and a `glob`
#: reach the same list by different routes, and the fold has to set both the same way.
#:
#: **The row that used to sit last was a `flagged_signals` result, and it was made up.** Zero
#: `flagged_signals` lookups exist in the store — `lookup-result.tsx` says so itself, in the
#: paragraph naming the four tools the investigator can reach that nothing has ever called — so
#: the fixture asserted a type on a shape no reader has ever been shown, and a `read_file`
#: fixture beside it dropped a word out of the line it claimed to be quoting. The `grep` that
#: found nothing replaces the first: it is real, and it draws `NoResult`, which nothing here
#: covered before.
LOOKUPS: list[dict[str, Any]] = [
    {
        "tool": "read_file",
        "arguments": {
            "file_path": "/src/archcompass/domain/repository.py",
            "limit": "15",
            "offset": "1",
        },
        "result": (
            " 2  \n"
            " 3  from dataclasses import dataclass\n"
            " 4  from pathlib import Path\n"
            " 5  \n"
            " 6  from archcompass.domain._support import require_text, stable_id\n"
            " 7  \n"
            ' 8  DEFAULT_BRANCH_NAME = "main"\n'
            " 9  \n"
            "10  \n"
            "11  def derive_branch_id(repository_id: str, branch_name: str) -> str:\n"
            '12      return stable_id("branch", repository_id, branch_name)\n'
            "13  \n"
            "14  \n"
            "15  @dataclass(frozen=True, slots=True)\n"
            "16  class RepositoryRef:\n"
            "\n"
            "[Read 15 lines (lines 2-16 of 30 total). 14 lines remaining from offset 16.]"
        ),
    },
    {
        "tool": "grep",
        "arguments": {"pattern": "CachingArchitectureJudge"},
        "result": "/src/archcompass/bootstrap.py\n/src/archcompass/reasoning/cache.py",
    },
    {
        "tool": "glob",
        "arguments": {"pattern": "**/*cache*.py"},
        "result": (
            "['/src/archcompass/reasoning/cache.py', "
            "'/tests/integration/test_cache_headers.py', "
            "'/tests/unit/test_finding_cache_provenance.py']"
        ),
    },
    {
        "tool": "related_code",
        "arguments": {
            "qualified_name": "archcompass.reasoning.adapters.selected",
            "relation": "direct_dependants",
        },
        "result": (
            "1 related nodes\n"
            "  archcompass.bootstrap  [module]  src/archcompass/bootstrap.py:1-624\n"
            "  archcompass.bootstrap --imports--> archcompass.reasoning.adapters.selected"
            "  (by parse)"
        ),
    },
    {
        "tool": "search_policies",
        "arguments": {"query": "single implementation port protocol"},
        "result": (
            "Policy ID: honor-substitution-contracts\n"
            "Every implementation of a contract must be usable wherever the contract is "
            "expected\n"
            "## Intent\n"
            "Keep an abstraction worth depending on, so that holding the interface is enough "
            "and a caller never has to know which implementation it received."
        ),
    },
    {
        "tool": "grep",
        "arguments": {"path": "src/audiobook/assembly/audio.py", "pattern": "qwen"},
        "result": "No matches found",
    },
]

#: Every element in the fold that holds text of its own, as the type a browser resolved for it.
#:
#: `getComputedStyle` and not the class attribute, which is the whole reason the defect below
#: lived: both sizes were declared perfectly correctly, in two different files, and reading
#: either class list would have reported exactly what its author intended. What nothing could
#: see is that the fold drew them beside each other.
#:
#: A `summary` is excluded because the closed label belongs to `Disclosure` and is the same
#: element on every fold in the product; what is being measured is the record inside.
#:
#: Taken on the fold element the locator resolved rather than by hunting the document for a
#: `<details>` whose label says "Looked up". The page holds several folds and an evidence
#: excerpt outside all of them, and a walk that finds its own subject can find a different one.
TYPESET = """
(details) => {
  const out = [];
  for (const element of details.querySelectorAll('*')) {
    if (element.closest('summary')) continue;
    const own = [...element.childNodes].some((n) => n.nodeType === 3 && n.data.trim());
    if (!own) continue;
    const style = getComputedStyle(element);
    out.push({
      size: style.fontSize,
      leading: style.lineHeight,
      text: element.textContent.slice(0, 40).replace(/\\s+/g, ' '),
    });
  }
  return out;
}
"""


def _inject_investigation(page) -> None:  # type: ignore[no-untyped-def]
    """Give every finding in the review the same investigation, holding the six rows above.

    Installed before the first navigation, because the page fetches the review as it mounts.
    The pattern matches a single path segment that is not `runs`, so only the review document
    is rewritten and the run endpoint is left alone.
    """

    def handler(route, request) -> None:  # type: ignore[no-untyped-def]
        response = route.fetch()
        try:
            document: dict[str, Any] = response.json()
        except Exception:  # pragma: no cover - a non-JSON body is not this test's subject
            route.fulfill(response=response)
            return
        document["investigation_manifest"] = [
            {
                "candidate_id": finding["candidate"]["id"],
                "lookups": LOOKUPS,
                "closing": "One implementation, and no test reaches it.",
                "withheld": "",
                "termination": "natural_end",
                "atlas_fingerprint": "content-fingerprint",
                "prompt_identity": "investigate-hinge:v1",
                "model_identity": "fake:deterministic",
            }
            for finding in document.get("findings", [])
        ]
        route.fulfill(response=response, body=json.dumps(document))

    page.route(re.compile(r"/api/reviews/(?!runs)[^/?]+$"), handler)


def test_the_looked_up_fold_is_set_in_one_type(page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    """Which tool the model called does not decide what type a reader reads the answer in.

    The fold drew its record at two sizes and nothing declared either of them as a pair. A
    `read_file` body came through `NumberedCode`, which was extracted from `SourceExcerpt` and
    carried the pinned excerpt's 12px on a 1.65 leading; everything else — the label, the
    extent, the path rows, the node rows, the policy Markdown, the tool's own trailing note and
    the plain fallback — is 11px on `leading-5`. On the six rows below that split the fold 37
    elements to 33, measured by putting `RESULT_TYPE` back to the excerpt's pair and rebuilding;
    by frequency it is 52% to 48%, since 501 of the 955 stored lookups are a `read_file`.

    Two sizes is not the fault. *Undeclared* two is, and it is the same one the Policies fold
    beside this spent a pass having removed, where a note was set at 14px or at 13px depending
    on whether a policy happened to bear on the finding.

    **This asserts the pair and not the size, and that is the repair the last pass owed.** The
    assertion read `style.fontSize` alone, so "11px on a 20px leading" — which is what
    `RESULT_TYPE` says about this fold in as many words — was a sentence nothing could fail on
    its second half. It was already false on its second half: the `PathRef` inside a node row
    declares a size and no leading, so its two text-bearing elements resolve to 11px on the
    16.5px they inherit while every other element in the record resolves to 11px on 20px. A
    caveat kept in a comment is the shape this branch has spent five passes removing; the pair
    is checked here instead, and `RESULT_TYPE` now names the exception rather than reading past
    it.

    So the fold is asserted to resolve to exactly three (size, leading) pairs, with a count on
    each of the two that are not the record:

    * **11px / 20px** — the record, which is everything the fold draws about a lookup.
    * **11px / 16.5px** — the two elements inside the one `PathRef` a node row carries. That
      component declares `text-[11px]` and no leading, so it takes the document's own leading,
      which is a **unitless 1.5** and therefore resolves against the element's own size rather
      than against the root's: 11 x 1.5. Measured, not assumed — a bare `<div>` with nothing on
      it but a font size comes back 16.5px at 11, 18px at 12, 19.5px at 13 and 24px at 16, which
      is what a unitless leading does and what a length would not.
    * **13px / 24px** — `investigation.closing`, a sentence the judging model wrote, drawn at
      the product's reading size like every other model paragraph. Stated rather than filtered
      out, because a filter would also hide a second paragraph arriving at that size.

    A fourth pair fails here whether it arrives at 12px or anywhere else.
    """

    _inject_investigation(page)
    wait_for_review(page, review_url)
    show_everything(page)
    open_first_candidate(page)
    fold = page.locator("details", has=page.get_by_text("Looked up", exact=True)).first
    fold.wait_for(state="visible", timeout=REVIEW_TIMEOUT_MS)
    fold.get_by_text("Looked up", exact=True).click()
    # Waited for *inside the fold*, not anywhere on the page. Every open finding already draws a
    # `pre > code` in its evidence excerpt, so a page-wide wait is satisfied by an element this
    # test is not about and lets the walk below run against a fold that has not opened yet.
    fold.locator("pre > code").first.wait_for(state="visible", timeout=20_000)

    typeset = fold.evaluate(TYPESET)
    assert len(typeset) >= 20, (
        f"only {len(typeset)} elements in the fold carry text of their own, which is fewer "
        "than the six injected results can draw — the investigation did not reach the surface"
    )

    pairs: dict[tuple[str, str], list[str]] = {}
    for row in typeset:
        pairs.setdefault((row["size"], row["leading"]), []).append(row["text"])
    drawn = {pair: (len(texts), texts[0]) for pair, texts in pairs.items()}
    record, reference, closing = ("11px", "20px"), ("11px", "16.5px"), ("13px", "24px")
    assert set(pairs) == {record, reference, closing}, (
        f"the fold sets its text in {sorted(pairs)} rather than in 11px/20px for the record, "
        f"11px/16.5px inside the node row's PathRef and 13px/24px for the model's closing "
        f"sentence: {drawn}"
    )
    # The record is the fold; the other two pairs are one component and one paragraph of it. If
    # either count grows, the assertion above is passing on a fold that is mostly its exceptions.
    assert len(pairs[closing]) == 1, (
        f"{len(pairs[closing])} elements are at the reading size, and only the closing sentence "
        f"should be: {pairs[closing]}"
    )
    assert len(pairs[reference]) == 2, (
        f"{len(pairs[reference])} elements carry a PathRef's inherited leading, and only the "
        f"path and its line span inside the one node row should: {pairs[reference]}"
    )
