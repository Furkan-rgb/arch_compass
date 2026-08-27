import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DRAWS_NO_CLASS, EMITS, Markdown, headingSlug } from "./markdown";
import { chMeasure, zeroAdvanceFor } from "./onest.test-metrics";

/**
 * The measure a rendered document is read at, which is one width and not five.
 *
 * Nothing in the suite read this file at all, which is how the defect it now guards shipped and
 * how it stayed shippable: `MEASURE` was `max-w-[46ch]` for as long as this renderer existed,
 * one string shared across the text renderers at four font sizes, and a `ch` is relative to the
 * font size of the element it is set on — and to its weight, which is the half every pass of
 * this comment missed until the seventh. So the one name resolved to five widths, on four sizes:
 * the 24px title, the 18px section heading, the 15px candidate heading, the 14px `####` label
 * and the 14px paragraphs, where the last two differ only because the label is `font-semibold`
 * and the paragraph is not. The hairline `h2` draws to open a section runs *across the measure*,
 * because "a section opens where the text opens", so it overshot the text under it on every
 * report and every policy in the product, with the title further past it again.
 *
 * **No figure for any of that is written in this paragraph, and that is the change.** They are
 * recomputed by "resolves the one name `46ch` used to carry to five different widths" below,
 * which puts `46ch` back onto the class lists the renderer itself emits, and by
 * `ui/onest.test-metrics.test.ts`, which holds the same widths in one table beside the other
 * surfaces that argue from them. Six rounds of this comment carried the numbers instead, and
 * five of those rounds shipped at least one that was wrong — including the round whose entire
 * subject was that a `ch` follows weight. A figure in prose is a copy of a measurement, and
 * copies drift; the repair is not to be more careful with the copy.
 *
 * The 14px pair is the one worth reading twice, because it is round seven. The `####` label and
 * the paragraph are both `text-sm` — same size, same file, ten lines apart — and their own 46ch
 * differ by two pixels, because one of them is set at 600 and the other at 400. Anybody
 * checking that they match by checking the size gets the right answer for the wrong reason and
 * writes it down.
 *
 * The repair in the renderer is one line — `max-w-[26.75rem]`, the paragraph's own 46ch at 14px
 * said in a unit that does not move when the type does — and reverting it kept all 421 tests in
 * the suite green. This is the test that was missing.
 *
 * jsdom lays nothing out, so none of this measures a rectangle. What it does instead is resolve
 * the declared measure against the declared font size and weight, which is arithmetic a reader
 * can redo, and assert that the seven answers are one answer. A measure written in a
 * font-relative unit cannot pass that unless every renderer is set at one size and one weight,
 * which is the property the rule actually needs.
 *
 * A resolved measure is not quite the rectangle: Chromium lays a box out on a 1/64px grid and
 * snaps down, so a browser reads every width here at or just under the figure resolved. That
 * gap is a rule rather than a second measurement — `Math.floor(resolved * 64) / 64` on all nine
 * widths this repository argues from, measured in a headless Chromium serving the built
 * stylesheet from its own `/assets` root so `@font-face` finds the shipped `onest.woff2`, with
 * both weights loaded through `document.fonts.load` and asserted through `document.fonts.check`
 * before anything was read; `font-display: swap` otherwise answers with a fallback whose zero is
 * 0.6299em and every width comes out five per cent wrong. `chMeasure` applies the rule and
 * `ui/onest.test-metrics.test.ts` asserts it against the nine rectangles it was measured on.
 */

/**
 * Onest's font model — the zero advance, which is what a `ch` is, and the weight it follows.
 *
 * None of it is here. `ui/onest.test-metrics.ts` owns the two advances, the nine weight
 * utilities and the resolver that throws rather than guess an advance for a weight nobody has
 * measured, together with the `fontTools` recipe that reads them off the shipped `onest.woff2`
 * and the Chromium reading that confirms them.
 *
 * It is imported rather than restated because this file is not the only one that argues from it:
 * `features/review/finding-detail.test.tsx` reaches the same conclusions about a 13px semibold
 * lede from the same two numbers, and for a while both files kept their own copy of all of it.
 * That is the defect these files exist to catch, one layer up — a measurement copied into two
 * places drifts in two directions, and the second copy is what tells you, afterwards.
 *
 * What matters *here* is which entry each row uses. Every Markdown heading below is
 * `font-semibold`, so four of the five rows of the counterfactual resolve against the 600 entry
 * and not the 400 one. Reading them at 400 overstates each by 0.48%, which is small enough that
 * six passes did not re-derive it and large enough to make every figure in a comment wrong.
 */

/** Tailwind's own steps, for the renderers that take a named size rather than an arbitrary one. */
const NAMED_SIZES: Record<string, number> = {
  "text-xs": 12,
  "text-sm": 14,
  "text-base": 16,
  "text-lg": 18,
  "text-xl": 20,
  "text-2xl": 24,
  "text-3xl": 30,
};

/** The font size an element declares, in px, or `null` if it declares none. */
function fontSize(classes: string): number | null {
  const arbitrary = /(?:^|\s)text-\[([\d.]+)px\]/.exec(classes);
  if (arbitrary) return Number(arbitrary[1]);
  for (const [name, px] of Object.entries(NAMED_SIZES)) {
    if (new RegExp(`(?:^|\\s)${name}(?:\\s|$)`).test(classes)) return px;
  }
  return null;
}

/**
 * The right edge a class list's measure resolves to, in px, and whether that number moves when
 * the type does.
 *
 * `ch` and `em` are the font-relative units a measure can be written in, and they are the whole
 * subject: a measure shared across sizes stated in either of them is not one measure.
 *
 * A `ch` is resolved against the size **and the weight**, because it is the advance of the zero
 * of the element's own used font and the used font here is a variable instance. Resolving it
 * against the size alone is the defect one level down from the one this file guards: it reads
 * every heading as though it were set at 400 and reports each of them 0.48% too wide.
 */
function resolve(classes: string): { px: number; fontRelative: boolean } | null {
  const found = /(?:^|\s)max-w-\[([\d.]+)(ch|rem|em|px)\]/.exec(classes);
  if (!found) return null;
  const value = Number(found[1]);
  const unit = found[2];
  const size = fontSize(classes);
  if (unit === "px") return { px: value, fontRelative: false };
  if (unit === "rem") return { px: value * 16, fontRelative: false };
  if (size === null) return null;
  if (unit === "em") return { px: value * size, fontRelative: true };
  return { px: value * size * zeroAdvanceFor(classes), fontRelative: true };
}

/** The same, off a rendered element. */
function measure(element: Element): { px: number; fontRelative: boolean } | null {
  return resolve(element.className);
}

/**
 * One of every construct the grammar has, so the assertions see every element the pipeline can
 * emit rather than the ones a realistic document happens to contain.
 *
 * Written from the grammar and not from a sample, which is the whole repair. A fixture built
 * from a plausible document is a fixture somebody chose, and the eleven tags this renderer had
 * no entry for were eleven tags no plausible document contained: `#####` and `######`, a task
 * checkbox, a deletion, a hard break, an image, a list item, a footnote reference and the
 * section it points into, and the table's own `tbody` and `tr`. Rendered fuller, a `#####` drew
 * at **1168px** — the panel's whole width, at 16px and 400 weight — over paragraphs stopping at
 * 428px, which is the widest single mismatch measured anywhere in the product.
 *
 * The fence, the table and the rule are here to be *excluded*: they are the blocks that
 * deliberately take the panel's full width, and a rule that says "everything is capped" cannot
 * be checked without the exceptions it has to leave alone.
 */
const DOCUMENT = [
  "# The report",
  "",
  "A paragraph of the document, long enough to wrap at any measure this renderer might be given.",
  "",
  "## A section",
  "",
  "Another paragraph, under the hairline that opens the section above it.",
  "",
  "### A candidate",
  "",
  "- a list item",
  "- and another",
  "",
  "1. a numbered item",
  "2. and another",
  "",
  "> a quotation from somewhere else",
  "",
  "#### A note",
  "",
  "A paragraph under the note, which is the level the measure was missing from.",
  "",
  "##### A fifth level",
  "",
  "A paragraph under the fifth level, which had no renderer at all and drew at 1168px.",
  "",
  "###### A sixth level",
  "",
  "A paragraph under the sixth level, which is the other one.",
  "",
  "- [ ] an unchecked task",
  "- [x] a checked task",
  "",
  "A line with *emphasis*, **strength**, ~~a deletion~~, `an.identifier` and a [link](https://example.com)",
  "with a hard break after it.  ",
  "The line after the hard break.",
  "",
  "![a diagram](diagram.png)",
  "",
  "```python",
  "def clock() -> None: ...",
  "```",
  "",
  "| reading | value |",
  "| --- | --- |",
  "| referenced by | 2 |",
  "",
  "---",
  "",
  "A sentence carrying a footnote reference.[^1]",
  "",
  "[^1]: The note itself, which arrives in a section GFM opens with a heading it hides.",
].join("\n");

/**
 * The tags of the blocks that are allowed to reach past the measure, and why each one does.
 *
 * A fence and a table are the two things `Markdown`'s own doc comment keeps the wrapper at
 * `max-w-none` for: both scroll inside themselves, and capping them would take the panel's
 * width away from the excerpt or the readings a reader came to the report to see. A rule is
 * not text at all — it is the document's own divider, and it spans what it divides.
 *
 * `DIV` is the table: `table` renders inside an `overflow-x-auto` wrapper, so the block the
 * document actually contains is that wrapper rather than the `<table>` inside it.
 */
const FULL_WIDTH_BLOCKS: Record<string, string> = {
  PRE: "a fence scrolls inside itself rather than wrapping",
  DIV: "a table scrolls inside its own wrapper",
  HR: "a rule spans what it divides",
};

/**
 * The renderers that draw a block a reader scrolls past, keyed by what each one emits — which
 * is not what it is keyed by in the component map.
 *
 * The heading levels each render one step down, because a document set inside a panel opens
 * under the page's own `h1` rather than beside it, and `table` renders inside the
 * `overflow-x-auto` wrapper that scrolls it, so the element the document contains is the
 * wrapper. Both are decisions made in `ui/markdown.tsx` and neither can be derived from the
 * key, which is why this is a written mapping and not a transformation.
 *
 * `h5` and `h6` both emit `H6` and that is not a typo: the ramp is four steps deep and there is
 * no seventh element to shift a sixth level into, which `DEEPEST` argues where it is declared.
 */
const BLOCK_TAGS: Record<string, string> = {
  h1: "H2",
  h2: "H3",
  h3: "H4",
  h4: "H5",
  h5: "H6",
  h6: "H6",
  p: "P",
  ul: "UL",
  ol: "OL",
  blockquote: "BLOCKQUOTE",
  pre: "PRE",
  table: "DIV",
  hr: "HR",
  section: "SECTION",
};

/**
 * The rest of them, which draw inside a block rather than being one.
 *
 * Six are inline — a name in a chip, an emphasis, a strong run, a deletion, a link, a footnote
 * reference — one is a line ending, and the others are the interiors of a list and a table.
 * None of them takes a measure, because the block around it already stopped where the measure
 * stops; a chip that carried one would cap a word.
 *
 * `img` is here rather than above, and it is the one entry worth arguing. It is a block, but
 * Markdown puts a lone image inside a paragraph, so the element the document contains is that
 * paragraph and the image is capped by it. Listing it as a block would demand a direct child of
 * the wrapper that the grammar cannot produce.
 */
const INSIDE_A_BLOCK = [
  "strong", "em", "del", "code", "a", "sup", "br",
  "img", "li", "input", "thead", "tbody", "tr", "th", "td",
];

/**
 * The classes the pipeline itself attaches, which say nothing about whether this file drew the
 * element wearing one.
 *
 * `mdast-util-to-hast` marks the footnotes block `footnotes` and `remark-gfm` marks a task item
 * `task-list-item` and a footnote's return arrow `data-footnote-backref`. All three arrive on
 * elements that had no renderer, so a check for "carries a class" reads them as handled — and
 * the `section` wearing the first of them was the widest undrawn block in the document.
 */
const SUPPLIED_BY_THE_PIPELINE = ["footnotes", "task-list-item", "data-footnote-backref"];

describe("Markdown", () => {
  /**
   * Half the rule, and the half that was not being checked: every block that sets text carries
   * a measure at all.
   *
   * This was `expect(measured.length).toBeGreaterThanOrEqual(8)` against a fixture that
   * rendered nine, which is a count and not a requirement — and the gap between the two is a
   * silent mutation. Delete `MEASURE` from the `ol` renderer and eight blocks are left, all
   * agreeing on one edge, and the whole suite passes; the numbered list then runs to the
   * panel's edge while the paragraphs beside it stop at 428px, which is the exact defect this
   * file exists for. The `h4` renderer really had shipped that way, and the count is why.
   *
   * So the assertion is over the blocks the document *contains* rather than over the ones that
   * happen to answer. Each direct child of the wrapper is either capped or is one of the three
   * kinds named above as deliberately full-width, and anything else fails carrying its own tag
   * and class list. A renderer that loses its measure has nowhere to hide in that, because the
   * element it produced is still in the document.
   *
   * Direct children only, because the measure is a property of a block and a blockquote holds
   * a paragraph that carries one of its own — inert, since the quotation's own cap is already
   * narrower than the paragraph's by the indent. The edge assertion below sees that nested one;
   * this one is about the blocks a reader scrolls past.
   */
  it("gives every block that sets text a measure, and nothing else one", () => {
    const { container } = render(<Markdown>{DOCUMENT}</Markdown>);
    const wrapper = container.firstElementChild!;
    const blocks = Array.from(wrapper.children);

    // The fixture has to actually contain the exceptions, or "everything else is capped" is a
    // rule about a document with no fence and no table in it.
    const excepted = blocks.filter((block) => block.tagName in FULL_WIDTH_BLOCKS);
    expect(
      excepted.map((block) => block.tagName).sort(),
      "the fixture no longer renders one of each block that may reach past the measure",
    ).toEqual(Object.keys(FULL_WIDTH_BLOCKS).sort());

    const uncapped = blocks
      .filter((block) => !(block.tagName in FULL_WIDTH_BLOCKS))
      .filter((block) => measure(block) === null);
    expect(
      uncapped.map((block) => `${block.tagName}: ${block.className}`),
      "a block of the document sets text and stops nowhere — it runs to the edge of the panel " +
        "while every block above and below it stops at the measure",
    ).toEqual([]);
  });

  /**
   * The fixture's own claim — "one of each block this renderer can emit" — asked of the
   * renderer rather than believed.
   *
   * The rule above is over the blocks `DOCUMENT` contains, so it is exactly as complete as
   * `DOCUMENT` is, and a renderer nobody put in the fixture is a renderer nobody's assertion
   * reaches. That is the `h4` failure one level up: the count next door said eight of nine
   * agreed and the fixture would have said nothing at all about a tenth. Requiring rather than
   * counting has to go all the way up, or the requirement is over a set somebody chose.
   *
   * So the set is `EMITS`, exported by the renderer, and adding a tag to it fails this until
   * its author says which of the two kinds it is — a block a reader scrolls past, which needs
   * one in `DOCUMENT`, or something drawn inside one, which does not. Neither can be satisfied
   * by editing this file alone, which is the point.
   *
   * This used to read the keys off the source with `/^ {10}(\w+): \(/`, which is a claim about
   * indentation: the map has since moved to module scope and the same regex would have gone on
   * passing at zero matches against an empty expectation if the two sides had ever agreed. An
   * imported list cannot be wrong about where it lives.
   *
   * The tag each block renderer emits is not the tag it is keyed by: the heading levels are
   * rendered one step down so a document inside a panel does not open on an `h1`, and `table`
   * renders inside the `overflow-x-auto` wrapper that scrolls it. The mapping is what makes
   * "the fixture contains one" checkable, and it is written down rather than derived because a
   * renderer's key and its output are two decisions.
   */
  it("renders one of every block the renderer can emit, which is what makes the rule above a rule", () => {
    expect(
      [...EMITS].sort(),
      "a tag was added to or removed from `EMITS` in `ui/markdown.tsx` and nothing here says " +
        "whether it draws a block of its own",
    ).toEqual([...Object.keys(BLOCK_TAGS), ...INSIDE_A_BLOCK].sort());

    const { container } = render(<Markdown>{DOCUMENT}</Markdown>);
    const drawn = new Set(
      Array.from(container.firstElementChild!.children).map((block) => block.tagName),
    );
    expect(
      Object.entries(BLOCK_TAGS)
        .filter(([, tag]) => !drawn.has(tag))
        .map(([key, tag]) => `${key} renders a <${tag.toLowerCase()}> the fixture never draws`),
      "a block this renderer can emit is not in `DOCUMENT`, so the measure rule above says " +
        "nothing about it",
    ).toEqual([]);
  });

  /**
   * The half a type cannot reach: an element the *pipeline* emits that `EMITS` does not list.
   *
   * `RENDERERS` is a `Record` over `EMITS`, so a tag on that list cannot be forgotten — leave
   * one out and `tsc` names it. What no type here can know is whether the list is the whole of
   * what `remark-gfm` and `mdast-util-to-hast` hand to `components`, because that set lives in
   * two dependencies and is not a type this file can import. A tag missing from the list gets
   * no renderer, and no renderer means the browser's own sheet: for a block element that is the
   * full width of the panel, which is how a `#####` came to draw at **1168px** against a 428px
   * paragraph in a file whose entire subject is one shared measure.
   *
   * So the signature is checked instead of the cause. An element this file drew carries a class
   * from this file; an element that fell through carries none. Three may legitimately carry
   * none and they are named in `DRAWS_NO_CLASS` with the reason each one has — which is why the
   * exceptions are a written list in the renderer rather than a `filter` here: adding a fourth
   * is then a decision somebody records, not a line in a test nobody reads.
   *
   * "None" has to mean *none from this file*, which is the subtlety and not a nicety. The
   * pipeline puts classes of its own on three elements, and an element wearing one of those and
   * nothing else has still fallen through: `section.footnotes` ran the panel's full 1168px
   * while carrying a class, so a plain emptiness check would have reported it drawn. They are
   * stripped before the count. `sr-only` is deliberately not among them, because that one this
   * file really does write — see "leaves GFM's hidden footnote label hidden" below.
   *
   * This is the assertion that would have failed on the shipped renderer, in a suite where all
   * eight of the others passed. It reports **H5, H6, DEL, INPUT, IMG, SUP, SECTION and TR**.
   */
  it("draws every element the pipeline emits, so none arrives with the browser's own sheet", () => {
    const { container } = render(<Markdown>{DOCUMENT}</Markdown>);
    const undrawn = Array.from(container.firstElementChild!.querySelectorAll("*")).filter(
      (element) =>
        !DRAWS_NO_CLASS.includes(element.tagName) &&
        element.className
          .split(/\s+/)
          .filter((name) => name && !SUPPLIED_BY_THE_PIPELINE.includes(name)).length === 0,
    );
    expect(
      [...new Set(undrawn.map((element) => element.tagName))],
      "an element of the document reached the page with no class from `ui/markdown.tsx` — it is " +
        "drawn by the browser's own sheet, which for a block is the full width of the panel",
    ).toEqual([]);
  });

  /**
   * The footnote label, which is the one heading in a GFM document that must not be drawn.
   *
   * `remark-gfm` opens the footnotes block with `<h2 class="sr-only" id="footnote-label">`, and
   * the `h2` renderer threw both away and substituted its own — so a document with a single
   * footnote in it grew a visible section headed "Footnotes", opened by the hairline that
   * `h2` draws across the measure, which its author never wrote. It is worth its own assertion
   * because it is the one case where the correct rendering of an element is *not to render it*,
   * and every other rule in this file would read that as success.
   */
  it("leaves GFM's hidden footnote label hidden", () => {
    const { container } = render(<Markdown>{DOCUMENT}</Markdown>);
    const notes = container.querySelector("section")!;
    const label = notes.querySelector("h2, h3, h4, h5, h6")!;
    expect(label.textContent, "the footnotes block no longer opens on a heading").toBe("Footnotes");
    expect(
      label.className,
      "GFM hides its own footnote label and this renderer drew it, with the section rule that " +
        "opens a heading of that level",
    ).toBe("sr-only");
  });

  /**
   * A footnote reference points into this document, and a link that does not leave must not
   * open a tab. The `a` renderer forced `target="_blank"` on every link it drew, so pressing a
   * footnote marker opened a blank page scrolled to a fragment that is not in it.
   */
  it("opens a new tab only for a link that leaves the document", () => {
    const { container } = render(<Markdown>{DOCUMENT}</Markdown>);
    const outward = container.querySelector('a[href^="http"]')!;
    const inward = container.querySelector('a[href^="#"]')!;
    expect(outward.getAttribute("target")).toBe("_blank");
    expect(inward.getAttribute("target"), "a link into this same document opened a tab").toBeNull();
  });

  /**
   * The other half: the measures that exist are one measure.
   *
   * Break it by putting `max-w-[46ch]` back on `MEASURE` in `ui/markdown.tsx`: the renderers
   * then resolve to 730.63, 547.97, 456.64 and 428.26px and this fails naming all four. Those
   * are the numbers the test below recomputes; the 734.2 / 550.6 / 458.9 this line used to
   * carry is the same arithmetic with a 400-weight zero on three headings set at 600.
   */
  it("gives every block of a document one right edge", () => {
    const { container } = render(<Markdown>{DOCUMENT}</Markdown>);
    const measured = Array.from(container.querySelectorAll("*"))
      .map((element) => ({ element, measure: measure(element) }))
      .filter((entry) => entry.measure !== null);

    const edges = [...new Set(measured.map((entry) => entry.measure!.px.toFixed(2)))];
    expect(
      edges,
      `${measured.length} measured blocks end at ${edges.length} different right edges: ` +
        measured
          .map((entry) => `${entry.element.tagName}@${entry.measure!.px.toFixed(1)}px`)
          .join(", "),
    ).toHaveLength(1);
  });

  /**
   * The same rule from the other side, and the reason the one above is not merely tidiness.
   *
   * A `ch` or an `em` is a promise that the width follows the type. That is right where one
   * element owns its own measure — `ui/prose.tsx` sets the model's argument in `ch` for exactly
   * that reason — and it is a bug the moment one string is shared by elements at four sizes,
   * because then the name says one measure and the layout draws four. A shared measure is
   * stated in an absolute unit or it is not shared.
   */
  it("states that measure in a unit that does not move with the type", () => {
    const { container } = render(<Markdown>{DOCUMENT}</Markdown>);
    const relative = Array.from(container.querySelectorAll("*")).filter(
      (element) => measure(element)?.fontRelative,
    );
    expect(
      relative.map((element) => `${element.tagName}: ${element.className}`),
      "a measure shared by four font sizes cannot be written in a font-relative unit",
    ).toEqual([]);
  });

  /**
   * Where the absolute value came from, which was a sentence in `ui/markdown.tsx` and nothing
   * else.
   *
   * `MEASURE` is `26.75rem` because that is the paragraph's own `46ch` — the block a document is
   * actually read in — said in a unit that does not move when the type does. That claim was
   * prose, and prose is what has been wrong here six times: change the body renderer to
   * `text-base` and the sentence becomes false while every other assertion in this file stays
   * green, because they all check that the seven measures *agree*, not that they agree on the
   * right number.
   *
   * A quarter of a pixel of slack, and it is used: 26.75rem is 428px against 428.26px resolved,
   * because the class list is rounded to a quarter-rem so it reads as a value somebody chose.
   * Half a pixel is therefore the loosest bound that still means "this number came from that
   * one" — a body size one Tailwind step either way moves it by more than 30px.
   */
  it("keeps the absolute measure at the paragraph's own 46ch", () => {
    const { container } = render(<Markdown>{DOCUMENT}</Markdown>);
    const paragraph = container.querySelector("p")!;
    const declared = measure(paragraph);
    expect(declared, `cannot read a measure off "${paragraph.className}"`).not.toBeNull();
    const asChars = resolve(`${paragraph.className} max-w-[46ch]`.replace(/max-w-\[[\d.]+rem\]/, ""));
    expect(asChars, "the paragraph no longer declares a font size to resolve a `ch` against").not.toBeNull();
    expect(
      Math.abs(declared!.px - asChars!.px),
      `the shared measure is ${declared!.px}px and the paragraph's own 46ch is ${asChars!.px}px — ` +
        "one of the two moved, and `ui/markdown.tsx` says they are the same number",
    ).toBeLessThan(0.5);
  });

  /**
   * The counterfactual, as an assertion rather than as a number in a paragraph.
   *
   * Every comment in this file, in `ui/markdown.tsx` and in `docs/design-system.md` argues from
   * these figures, and six rounds of them have now been wrong — because a number in prose is a
   * copy of a measurement and copies drift. None of them has to be copied: each is
   * `46 x size x advance` over a class list the renderer itself emits, so the test can hold them
   * and the prose can name the test.
   *
   * The `46ch` is put back onto the shipped class lists rather than written out here, so if a
   * heading's size or weight changes the counterfactual changes with it and this fails instead
   * of quietly describing a document that no longer exists. The one thing written out is the
   * expected width, and the assertion is a whole row at a time so a failure prints the five
   * beside each other — which is how a weight mistake becomes visible, because on its own each
   * number looks fine.
   *
   * The heading rows are the point. All four are `font-semibold`, so each resolves against
   * Onest's 600-weight zero and not its 400-weight one, and the spread between the two readings
   * is the whole of the sixth round of wrong numbers: 3.53px on the title, 2.65px on the section
   * heading, 2.21px on the candidate heading, 2.06px on the `####` label and 2.65px on the
   * overshoot.
   *
   * The `h5` row is the seventh round, and it is the reason the assertion is five wide rather
   * than four. `markdown.tsx` said of the `####` label that it "is `text-sm`, the same 14px the
   * paragraphs are set at, so 26.75rem is this element's own 46ch and no number moves" — in a
   * file whose subject one screen earlier is that a `ch` follows weight. The label is
   * `text-sm font-semibold`. Its own 46ch is two pixels short of the paragraph's, and the shared
   * `rem` measure is the paragraph's, not its own.
   */
  it("resolves the one name `46ch` used to carry to five different widths", () => {
    const { container } = render(<Markdown>{DOCUMENT}</Markdown>);
    const asChars = (selector: string) => {
      const element = container.querySelector(selector);
      expect(element, `the renderer no longer emits ${selector}`).not.toBeNull();
      const reverted = element!.className.replace(/max-w-\[[\d.]+rem\]/, "max-w-[46ch]");
      expect(reverted, `${selector} does not carry the shared measure`).toContain("max-w-[46ch]");
      return resolve(reverted)!.px;
    };

    const title = asChars("h2");
    const section = asChars("h3.border-t");
    const candidate = asChars("h4");
    const label = asChars("h5");
    const body = asChars("p");

    // 46 x 24 x 0.6618, 46 x 18 x 0.6618, 46 x 15 x 0.6618, 46 x 14 x 0.6618, 46 x 14 x 0.665 —
    // the same five `chMeasure` holds in `ui/onest.test-metrics.test.ts`, where the rectangles
    // Chromium draws for them are asserted against the layout-unit rule.
    expect([title, section, candidate, label, body].map((px) => Number(px.toFixed(2)))).toEqual([
      730.63, 547.97, 456.64, 426.2, 428.26,
    ]);
    // The overshoot the rule draws, which is the half of this a reader sees. 119.71, not the
    // 122.36 that 46 x 4 x 0.665 gives by reading the 600-weight heading at 400.
    expect(Number((section - body).toFixed(2))).toBe(119.71);
    expect(Number((title - body).toFixed(2))).toBe(302.37);
    // And the label undershoots, which is the sign nobody looked at: a `ch` at one size can land
    // either side of another `ch` at that same size, because the weight decides which.
    expect(Number((label - body).toFixed(2))).toBe(-2.06);
    // Both readings of the label agree, which is what makes the row above a measurement of the
    // shipped element rather than of a class list written out in this file.
    expect(Number(chMeasure(46, 14, "font-semibold").resolved.toFixed(2))).toBe(426.2);
  });

  /**
   * The hairline is the half a reader sees, and it is worth asserting on its own because it is
   * the element the 119.71px overshoot was measured on. `h2` renders as an `h3` carrying both
   * the measure and the `border-t` that opens the section, so its measure *is* where the rule
   * stops.
   */
  it("stops the rule that opens a section where the text under it stops", () => {
    const { container } = render(<Markdown>{DOCUMENT}</Markdown>);
    const rule = container.querySelector("h3.border-t");
    expect(rule, "the section heading no longer draws the rule that opens a section").not.toBeNull();
    const paragraph = container.querySelector("p");
    const ruleEdge = measure(rule!);
    const textEdge = measure(paragraph!);
    expect(ruleEdge, `cannot read a measure off "${rule!.className}"`).not.toBeNull();
    expect(textEdge, `cannot read a measure off "${paragraph!.className}"`).not.toBeNull();
    expect(
      ruleEdge!.px - textEdge!.px,
      "the rule opening a section overshoots the paragraphs under it",
    ).toBe(0);
  });

  it("slugs a heading down to something both halves of the contents strip can compute", () => {
    expect(headingSlug("## `ports.Clock` — the boundary")).toBe("ports-clock-the-boundary");
    expect(headingSlug("ports.Clock")).toBe("ports-clock");
  });
});
