import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown, headingSlug } from "./markdown";
import { zeroAdvanceEm } from "./onest.test-metrics";

/**
 * The measure a rendered document is read at, which is one width and not four.
 *
 * Nothing in the suite read this file at all, which is how the defect it now guards shipped and
 * how it stayed shippable: `MEASURE` was `max-w-[46ch]` for as long as this renderer existed,
 * one string shared by seven text renderers at four font sizes, and a `ch` is relative to the
 * font size of the element it is set on — and on its weight, which is the half every pass of
 * this comment missed until the seventh. So the one name resolved to four widths: **730.63px** on the
 * 24px title, **547.97px** on the 18px section heading, **456.64px** at 15px and **428.26px**
 * on the paragraphs. The hairline `h2` draws to open a section runs *across the measure*,
 * because "a section opens where the text opens", so it overshot the text under it by
 * **119.71px** on every report and every policy in the product, with the title **302.37px**
 * past that again.
 *
 * Those six figures are not read out of this paragraph by anything: they are recomputed and
 * asserted by "resolves the one name `46ch` used to carry to four different widths" below, so
 * a reader who doubts one can change it and watch the suite say so. What the paragraph adds is
 * why they are not 734 / 551 / 459 / 122 / 306, which is what the same arithmetic gives with a
 * 400-weight zero on three headings set at 600.
 *
 * The repair is one line — `max-w-[26.75rem]`, the paragraph's own 46ch at 14px said in a unit
 * that does not move when the type does — and reverting it kept all 421 tests in the suite
 * green. This is the test that was missing.
 *
 * jsdom lays nothing out, so none of this measures a rectangle. What it does instead is resolve
 * the declared measure against the declared font size and weight, which is arithmetic a reader
 * can redo, and assert that the seven answers are one answer. A measure written in a
 * font-relative unit cannot pass that unless every renderer is set at one size, which is the
 * property the rule actually needs.
 *
 * A resolved measure is not quite the rectangle. Chromium snaps a laid-out box to a 1/64px
 * layout unit, so the paragraph it draws is 428.25px against the 428.26px resolved here and the
 * overshoot it draws is 119.72px against 119.71px. Both were measured, in a headless Chromium
 * serving the built stylesheet from its own `/assets` root so `@font-face` finds the shipped
 * `onest.woff2`, with both weights loaded through `document.fonts.load` and asserted through
 * `document.fonts.check` before anything was read — `font-display: swap` otherwise answers with
 * a fallback whose zero is 0.6299em and every width comes out wrong by five per cent. The two
 * are the same number at one decimal place and the difference is the snap, not a disagreement.
 */

/**
 * Onest's zero advance — which is what a `ch` is, and which is **not one number**.
 *
 * It lives in `ui/onest.test-metrics.ts`, with the `fontTools` recipe that reads it off the
 * shipped `onest.woff2` and the Chromium reading that confirms it. It is imported rather than
 * restated because this file is not the only one that argues from it: the finding band's lede
 * is 13px semibold and reaches the same conclusion from the same two numbers, and two hand-kept
 * copies of a measurement is the defect these files exist to catch, one level up.
 *
 * What matters *here* is which entry each row uses. Every Markdown heading below is
 * `font-semibold`, so three of the four rows of the counterfactual resolve against the 600 entry
 * and not the 400 one. Reading them at 400 overstates each by 0.48%, and that is the whole of
 * the sixth round of this file's wrong figures — 734 / 551 / 459 against 730.63 / 547.97 /
 * 456.64.
 */

/**
 * Every weight utility Tailwind has, not only the two this renderer uses.
 *
 * All nine are listed so an unrecognised one cannot be read as the inherited 400. A heading
 * that gains `font-bold` resolves to a weight with no measured advance and throws, which is the
 * failure that says "go and read 700 off the font" — where silently falling back to 400 would
 * report the same heading 0.7% too wide and blame the number.
 *
 * The family utilities `font-display`, `font-sans` and `font-mono` are deliberately not here:
 * they share the prefix and say nothing about weight.
 */
const NAMED_WEIGHTS: Record<string, number> = {
  "font-thin": 100,
  "font-extralight": 200,
  "font-light": 300,
  "font-normal": 400,
  "font-medium": 500,
  "font-semibold": 600,
  "font-bold": 700,
  "font-extrabold": 800,
  "font-black": 900,
};

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

/** The weight a class list declares, in the `font-weight` numbers, defaulting to the inherited 400. */
function fontWeight(classes: string): number {
  for (const [name, weight] of Object.entries(NAMED_WEIGHTS)) {
    if (new RegExp(`(?:^|\\s)${name}(?:\\s|$)`).test(classes)) return weight;
  }
  return 400;
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
  const advance = zeroAdvanceEm(fontWeight(classes), `"${classes}"`);
  return { px: value * size * advance, fontRelative: true };
}

/** The same, off a rendered element. */
function measure(element: Element): { px: number; fontRelative: boolean } | null {
  return resolve(element.className);
}

/**
 * One of each block this renderer can emit, so the assertion sees every one of them rather
 * than the two a realistic document happens to contain.
 *
 * All four heading levels, both list kinds, a quotation, a fence, a table and a rule. The last
 * three are here to be *excluded*: they are the blocks that deliberately take the panel's full
 * width, and a rule that says "everything is capped" cannot be checked without the exceptions
 * it has to leave alone.
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
  "```python",
  "def clock() -> None: ...",
  "```",
  "",
  "| reading | value |",
  "| --- | --- |",
  "| referenced by | 2 |",
  "",
  "---",
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
   * The counterfactual, as an assertion rather than as a number in a paragraph.
   *
   * Every comment in this file, in `ui/markdown.tsx` and in `docs/design-system.md` argues from
   * the same six figures, and six rounds of them have now been wrong — because a number in
   * prose is a copy of a measurement and copies drift. These six do not have to be copied:
   * they are `46 x size x advance` over class lists the renderer itself emits, so the test can
   * hold them and the prose can name the test.
   *
   * The `46ch` is put back onto the shipped class lists rather than written out here, so if a
   * heading's size or weight changes the counterfactual changes with it and this fails instead
   * of quietly describing a document that no longer exists.
   *
   * The heading rows are the point. Each is `font-semibold`, so each resolves against Onest's
   * 600-weight zero and not its 400-weight one, and the spread between the two readings is the
   * whole of the sixth round of wrong numbers: 3.53px on the title, 2.65px on the section
   * heading, 2.21px on the candidate heading and 2.65px on the overshoot.
   */
  it("resolves the one name `46ch` used to carry to four different widths", () => {
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
    const body = asChars("p");

    // 46 x 24 x 0.6618, 46 x 18 x 0.6618, 46 x 15 x 0.6618, 46 x 14 x 0.665. Chromium draws
    // 730.63 / 547.97 / 456.64 / 428.25 against the shipped face, the last one snapped down to a
    // 1/64px layout unit.
    expect([title, section, candidate, body].map((px) => Number(px.toFixed(2)))).toEqual([
      730.63, 547.97, 456.64, 428.26,
    ]);
    // The overshoot the rule draws, which is the half of this a reader sees. 119.71, not the
    // 122.36 that 46 x 4 x 0.665 gives by reading the 600-weight heading at 400.
    expect(Number((section - body).toFixed(2))).toBe(119.71);
    expect(Number((title - body).toFixed(2))).toBe(302.37);
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
