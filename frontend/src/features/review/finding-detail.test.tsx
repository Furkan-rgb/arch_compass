import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Finding, Review } from "../../api";
import { verdictOf } from "../../lib/format";
import { zeroAdvanceEm } from "../../ui/onest.test-metrics";
import { plainProse } from "../../ui/prose";
import { reviewFixture } from "../../test-fixtures";
import { FindingBody } from "./finding-detail";

/**
 * The Judged band — the model's argument and what the product says around it.
 *
 * Nothing in the suite read a measure, a size or a line break in this file, and that is how
 * the defect this replaces shipped: the model's paragraph was capped at `46ch` inside a
 * 1126px band for as long as it existed, under a comment claiming it took the full width. A
 * wrong measure is invisible to every other test in the product, because it breaks nothing —
 * it just makes the one paragraph the product exists to show worse to read.
 *
 * jsdom lays nothing out, so none of this can assert pixels it has measured. What it asserts
 * instead is the two things that decide the pixels: the order of the DOM, which is what a
 * phone reads down, and the typesetting each block declares, which is arithmetic anybody can
 * check. Both are stated as properties — "wide enough to hold a qualified name", "one block
 * at the reading size" — rather than as the class strings that happen to express them today,
 * so changing the token cannot be made to pass by updating the expected string.
 */

/**
 * Onest's zero advance, which is what a `ch` is — and which is one number per weight.
 *
 * It lives in `ui/onest.test-metrics.ts`, with the `fontTools` recipe that reads it off the
 * shipped `onest.woff2` and the Chromium reading that confirms it, because `ui/markdown.test.tsx`
 * argues from the same two numbers over a document's seven renderers. Two files keeping their
 * own copy of one measurement is the drift these files exist to catch, so there is one copy.
 *
 * It matters *here* because the block this file compares the argument against is the lede, and
 * the lede is 13px **semibold**. A `58ch` written on both is 617.12px on the argument and
 * 499.00px on the lede — not the 501px a 400-weight reading gives, and not the 498.99px an
 * earlier pass here printed, which is neither the resolved 498.997 nor the 498.98 Chromium
 * draws. Every number below is derived from these, so a face change moves the arithmetic and
 * the bounds keep meaning what they say.
 */

/**
 * The weight a class list declares, in `font-weight` numbers, defaulting to the inherited 400.
 *
 * All nine of Tailwind's weight utilities are listed, not only the one this band uses, so an
 * unrecognised one cannot be read as 400 — it resolves to a weight with no measured advance and
 * `zeroAdvance` throws. The family utilities `font-display`, `font-sans` and `font-mono` share
 * the prefix and say nothing about weight, so they are not here.
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

function declaredWeight(classes: string): number {
  for (const [name, weight] of Object.entries(NAMED_WEIGHTS)) {
    if (new RegExp(`(?:^|\\s)${name}(?:\\s|$)`).test(classes)) return weight;
  }
  return 400;
}

/** The zero advance a class list's own type resolves to, or a loud failure. */
function zeroAdvance(classes: string): number {
  return zeroAdvanceEm(declaredWeight(classes), `"${classes}"`);
}

/**
 * What one character of *this corpus* costs on a line that is actually full, which is neither
 * the advance of a lowercase letter nor the average of every line drawn.
 *
 * **75.7**, and here is how to get it again. Serve the built bundle, so the face is the shipped
 * `onest.woff2` and the CSS is the real one. Render all 375 recorded strings through the real
 * `ModelProse` — chips and all, because a backticked name is drawn as a mono chip a little wider
 * than the Onest it displaces. Measure each `<p>` with a Range per character and cluster the
 * boxes on their vertical centres, one cluster to a line. That comes to 3,248 line boxes, of
 * which 2,082 are not the last of their block, and those 2,082 carry 75.7 characters on average.
 *
 * And say which characters, because a soft wrap happens at a space that is drawn on no line and
 * that space has to belong somewhere. It is counted as belonging to **the line it ended**, over
 * the block's *rendered* text — the characters on screen, so a chip counts as the name inside it
 * and not as the backticks around it. `ui/prose.tsx` argues that convention at length and states
 * what the other reading gives; the short version is that these spans partition the block, so
 * they sum to its own length and 75.7 is checkable against something other than a second run of
 * the same script.
 *
 * Two other numbers are available here and both are the wrong one. The mean glyph advance over
 * the whole rendered corpus is 7.49px — 1,569,778px of boxes over 209,493 characters, spaces
 * included — which ignores that a ragged right edge leaves a word's worth of room on most lines.
 * The average over *every* line is 64.5, which folds in each block's short last line and so
 * describes the ragging rather than the sweep. What a measure is judged on is the line an eye
 * has to come back across, and that is the full one.
 *
 * The **73** that stood here, in `ui/prose.tsx` and in `docs/design-system.md`, was attributed to
 * measuring the string rather than the render, and that diagnosis is wrong in the direction as
 * well as the digit. Flattening every chip back to Onest body text and re-running the same sweep
 * gives 3,237 line boxes and **76.07** characters: narrower text fits *more* of it on a line, so
 * the string reads about half a character **generous**, never eleven characters short. It loses
 * eleven line boxes, which is the part of that sentence that was true. 73.1 is this sweep at
 * **56ch**, which is where a 73 most plausibly came from, and no method stated in any of the
 * three files reproduces 3,326 lines at all. It is deleted rather than corrected: a counterfactual
 * whose method nobody wrote down is a number that cannot be checked, and this surface has shipped
 * six rounds of those.
 */
const AVERAGE_CHARACTER_PX = 617.12 / 75.7;

/**
 * The widest thing the model has ever written that cannot be broken across a line.
 *
 * `(src.audiobook.preparation.providers.base.NarrationPreparationProvider)` at 541.7px — 71
 * characters, brackets included, because UAX #14 forbids a break after an opening bracket and
 * before a closing one. Measured by putting the token through a real `ModelProse` with the
 * measure lifted so it cannot wrap and reading a Range over the paragraph's own text node; the
 * 543.0px three passes have carried is 1.3px out and came from a probe span rather than from the
 * component. 48 distinct tokens across 51 of the 375 recorded strings are wider
 * than the 324px column a phone gives this block. This is the floor on the measure and the
 * reason the measure is not a matter of taste: under it, the name the argument is *about* is
 * split across two lines by `wrap-anywhere`, which is the least legible thing this band can do
 * to the one word a reader is checking.
 *
 * Set in Onest, which is the half of the number that gets lost, and the half a re-measurement
 * of this file kept trying to put back. The corpus holds two names of 74 characters that
 * measure 601.3px and 583.1px as Onest body text, and neither is a candidate for this floor:
 * both are backticked in every string they appear in, so `INLINE_CODE` draws them as mono
 * chips — 620.9px each, wider than the measure — carrying `max-w-full` and `wrap-anywhere`,
 * where a name too wide for its column folds inside a box that says the fragments are one
 * name. `ui/prose.tsx` makes that argument at length beside the measure. Raising this constant
 * to cover them would be widening the measure to clear a token this block never sets.
 */
const WIDEST_TOKEN_PX = 541.7;

/**
 * The typesetting a block declares, read off it and converted into the units the arguments
 * above are made in.
 *
 * Returns `null` for anything it cannot read, so a block that moves to a named utility or a
 * token fails the assertion with the class list in the message rather than passing silently
 * on a regex that stopped matching.
 */
function typeset(element: Element) {
  const classes = element.className;
  const size = /text-\[([\d.]+)px\]/.exec(classes);
  const measure = /max-w-\[([\d.]+)ch\]/.exec(classes);
  const leading = /leading-\[([\d.]+)\]/.exec(classes);
  if (!size || !measure || !leading) return null;
  const fontPx = Number(size[1]);
  const measurePx = Number(measure[1]) * zeroAdvance(classes) * fontPx;
  return {
    fontPx,
    measurePx,
    leading: Number(leading[1]),
    charactersPerLine: measurePx / AVERAGE_CHARACTER_PX,
  };
}

/**
 * The right edge a block's declared measure resolves to, in px, and whether that number moves
 * when the type does.
 *
 * `typeset` above reads `ch` only, because the argument is the one block it is asked about. This
 * reads the units a *shared* measure can be written in, which is a different question and the
 * one defect 9 is about: a `ch` is relative to the font size of the element it is set on, so one
 * class on two elements at two sizes is two widths wearing one name.
 */
function rightEdge(element: Element): { px: number; fontRelative: boolean } | null {
  const classes = element.className;
  const found = /(?:^|\s)max-w-\[([\d.]+)(ch|rem|em|px)\]/.exec(classes);
  if (!found) return null;
  const value = Number(found[1]);
  const unit = found[2];
  if (unit === "px") return { px: value, fontRelative: false };
  if (unit === "rem") return { px: value * 16, fontRelative: false };
  const size = /(?:^|\s)text-\[([\d.]+)px\]/.exec(classes);
  if (!size) return null;
  return {
    px: value * Number(size[1]) * (unit === "ch" ? zeroAdvance(classes) : 1),
    fontRelative: true,
  };
}

/** Every element under `root`, so a rule can be asserted over a whole region at once. */
const elements = (root: HTMLElement) => Array.from(root.querySelectorAll("*"));

/**
 * Three recorded judgements, taken from the workspace database rather than written here.
 *
 * A fixture sentence is 60 characters and proves nothing about a 500-character paragraph.
 * These are what the models produced: bracketed policy references that Markdown would read
 * as links, a quotation with its own full stops inside it, and — the one the previous pass's
 * corpus survey missed — a judgement that argues through a numbered list.
 */
const RECORDED = {
  median:
    "The codebase defines a thin adapter interface `NarrationPreparationProvider` " +
    "(implemented by `OllamaProvider`) with a single concrete implementation used to wrap a " +
    "local service. This follows standard provider separation without accumulating " +
    "unnecessary parameterization, wrong abstractions, or leaked transport rules. It complies " +
    "with policy [2] by establishing a credible boundary for providers and [3] by containing " +
    "the volatile Ollama dependency behind an adapter.",
  quoting:
    "The candidate detection exposes duplicated constant definitions of `_REPOSITORY` in two " +
    "independent test modules (`tests.integration.test_scoped_review` and " +
    "`tests.unit.test_scope_selection`) with drifted or distinct structures. This directly " +
    "violates Policy [1] ('Keep each architectural fact in one authoritative place') and " +
    "Policy [7] ('Keep one conceptual change local'), as the duplicated knowledge creates " +
    "maintenance hazards and potential divergence across tests.",
  numbered:
    "The candidate is `audiobook.synthesis.providers.base.SynthesisProvider`, an abstraction " +
    "with a single implementation. \n\nHowever, looking at the architecture and policies:\n" +
    "1. `delay-premature-abstraction` warns against paying interface and registry costs for " +
    "imagined variation.\n2. But `contain-dependencies` shows that a provider adapter " +
    "boundary separating heavy external ML dependencies from the rest of the application is a " +
    "standard architectural containment boundary.\n\nThus, the structure clears its costs.",
};

/** The held finding — the one that carries a hinge, a question and the way out to the round. */
function held(review: Review): Finding {
  return review.findings.find((finding) => finding.verdict === "held")!;
}

function draw(finding: Finding, review = reviewFixture(), onAnswer = vi.fn()) {
  const { container } = render(
    <MemoryRouter>
      <FindingBody review={review} finding={finding} onAnswer={onAnswer} />
    </MemoryRouter>,
  );
  const body = container.firstElementChild as HTMLElement;
  return { body, band: body.firstElementChild as HTMLElement, onAnswer };
}

/** The model's argument: the one block on the surface set at the reading size. */
function argument(body: HTMLElement) {
  const found = elements(body).filter((element) => /text-\[16px\]/.test(element.className));
  return found as HTMLElement[];
}

/** Where `element` sits relative to `other` in the document a screen reader walks. */
const comesBefore = (element: Element, other: Element) =>
  Boolean(element.compareDocumentPosition(other) & Node.DOCUMENT_POSITION_FOLLOWING);

describe("the Judged band", () => {
  /**
   * The defect this is here to stop coming back: at 390 the rail stacked *below* the
   * argument, so "Judgement is waiting on context the repository cannot supply." — the one
   * sentence the product writes to introduce 1,700px of model prose — was read after it. The
   * fix moved the sentence in the DOM rather than painting it earlier with an `order` class,
   * and that distinction is the half a screenshot cannot check: `order` would put the reading
   * order and the keyboard order in disagreement, which costs exactly the readers who can
   * least afford 1,700px of unbroken paragraph.
   *
   * So the assertion is document order, which is the same at every width because nothing here
   * reorders, plus the absence of anything that could reorder it.
   */
  it("says what the verdict means before the argument, and does it in the DOM", () => {
    const review = reviewFixture();
    const finding = held(review);
    const { body, band } = draw(finding);

    const voice = screen.getByText("Judged");
    const lede = screen.getByText(verdictOf(finding.verdict).description!);
    const [prose] = argument(body);

    expect(comesBefore(voice, lede)).toBe(true);
    expect(comesBefore(lede, prose)).toBe(true);

    // Nothing in the band paints out of order, so the order above is the order at 390, at
    // 1024 and at 1440. A single `order-*` anywhere here would make that claim false.
    const reordered = elements(band).filter((element) =>
      /(^|\s)(?:[a-z]+:)?order-/.test(element.className),
    );
    expect(reordered.map((element) => element.className)).toEqual([]);

    // And it is not a tab stop, so the keyboard path is unchanged by having moved it.
    expect(lede.tagName).toBe("P");
    expect(lede.getAttribute("tabindex")).toBeNull();
  });

  /**
   * The design system's central claim, which is also the only thing marking the model's voice
   * now that the serif is gone: 16px is the model's, "its own size, used nowhere else". The
   * lede sits directly above the argument and is the obvious candidate for being promoted
   * into it by somebody making the band read better, at which point the band has two voices
   * in one and no way to tell them apart.
   */
  it("sets one block at the reading size, and the model's words are in it", () => {
    const review = reviewFixture();
    const finding = { ...held(review), reasoning: RECORDED.median };
    const { body } = draw(finding, review);

    const reading = argument(body);
    expect(reading).toHaveLength(1);
    expect(reading[0].textContent).toContain("thin adapter interface");

    // The product's own sentence about the verdict is under it, in size and in ink. It is
    // promoted out of the 12px footnote it used to be glued into and stops short of the
    // reading size deliberately.
    const lede = screen.getByText(verdictOf(finding.verdict).description!);
    expect(lede.className).toMatch(/text-\[13px\]/);
    expect(lede.className).toMatch(/font-semibold/);
    expect(lede.className).toMatch(/text-ink-2/);
  });

  /**
   * The measure, asserted as the two things it is actually bounded by rather than as the
   * number that satisfies them today.
   *
   * The floor is the corpus: a qualified name has to fit on one line, and the widest recorded
   * one is 541.7px. `46ch` — the value this band shipped with, and the value the synopsis still
   * carried until this pass — is 489.5px and fails it. Both bounds are computed from the declared
   * type, so a measure changed without an argument fails here even if the token it is written
   * in changes with it.
   *
   * The ceiling is the return sweep, and the quantity it is stated in has to be said exactly,
   * because the file next door states a different one about the same block and both are right.
   * `charactersPerLine` is the average of the lines a reader has to sweep back across — every
   * line that is not the last of its block — which is 75.7 at 617.12px. The *fullest* line the
   * same corpus reaches at the same measure is 90, and `ui/prose.tsx` says so beside the
   * measure. So 78 here is a ceiling and not a target: 62ch, the value this replaced, measures
   * 81.6 on average and 96 at its fullest, and 96 is past what `leading-[1.65]` gets an eye
   * back from — which is why the leading is asserted in the same breath.
   *
   * How much room is left is worth stating exactly, because the sentence that stood here said
   * "about five characters to spare" and there are **2.3**: 58ch measures 75.7 against a bound
   * of 78, and this test's own arithmetic crosses 78 at 635.9px, which is 59.8ch. Measured
   * directly rather than interpolated, the sweep runs 73.1 at 56ch, 75.7 at 58, 77.3 at 59 and
   * 78.7 at 60 — so the bound really does fall between 59ch and 60ch, and the arithmetic and the
   * browser agree about where. That is honest rather than comfortable, and the floor above is
   * why: 541.7px of qualified name has to fit on one line, so the band this can be chosen from
   * starts high.
   *
   * `AVERAGE_CHARACTER_PX` is derived from this block's own current measure, so today the
   * average comes back at 75.7 by construction and the bound cannot fail. That is deliberate
   * and it is not circular in the way that matters: the constant is a property of the *face
   * and the corpus*, not of the measure, so it stays put when somebody widens `58ch` — which
   * is the change this exists to catch, and the change that moves `charactersPerLine` off 75.7
   * and into the bound.
   */
  it("gives the argument a measure that holds a qualified name and a line that can be swept", () => {
    const { body } = draw(held(reviewFixture()));
    const [prose] = argument(body);

    const set = typeset(prose);
    expect(set, `cannot read the typesetting off "${prose.className}"`).not.toBeNull();
    expect(set!.fontPx).toBe(16);
    expect(set!.measurePx).toBeGreaterThanOrEqual(WIDEST_TOKEN_PX);
    expect(set!.charactersPerLine).toBeGreaterThanOrEqual(60);
    expect(set!.charactersPerLine).toBeLessThanOrEqual(78);
    // A measure at the top of that band is only readable because the line under it is far
    // enough away to find. This is the leading paying for the measure, and the two move
    // together or neither is true.
    expect(set!.leading).toBeGreaterThanOrEqual(1.5);
  });

  /**
   * The lede's cap, which is a guard rather than a measure, and which was defect 9 written out
   * in one class.
   *
   * The verdict's sentence sits directly above the argument, so the two read as sharing a right
   * edge — and for as long as this band existed they were written as though they did: the lede
   * carried the argument's own `max-w-[58ch]`. A `ch` is relative to the font size of the
   * element it is on, so 58 of them is 617.1px on the 16px argument and 501.3px on this 13px
   * line. One class, two elements twenty lines apart, two widths. The correction is `38.5rem`,
   * which is 616px whatever this line is ever set at.
   *
   * Nothing in this file could see that. `typeset` reads the argument and only the argument, so
   * putting `58ch` back keeps all ten of these green — which is exactly what a guard for one
   * value that is also written next door has to catch. Break it by putting `max-w-[58ch]` back
   * on the lede.
   *
   * Two assertions, because two things are wrong with `58ch` here and only one of them is the
   * width. The edges have to agree — within a pixel and a bit, since 38.5rem is 616px against
   * the argument's 617.12 and the guard is deliberately the round number rather than a matching
   * `ch` count. And the unit has to be one that does not move with the type, because a measure
   * that follows the font size is a promise this line cannot keep for the block below it.
   */
  it("caps the lede at the argument's own edge, in a unit that does not follow the type", () => {
    const review = reviewFixture();
    const finding = held(review);
    const { body } = draw(finding);

    const lede = screen.getByText(verdictOf(finding.verdict).description!);
    const [prose] = argument(body);
    const ledeEdge = rightEdge(lede);
    const proseEdge = rightEdge(prose);

    expect(ledeEdge, `cannot read a measure off "${lede.className}"`).not.toBeNull();
    expect(proseEdge, `cannot read a measure off "${prose.className}"`).not.toBeNull();
    expect(
      Math.abs(ledeEdge!.px - proseEdge!.px),
      `the lede ends at ${ledeEdge!.px.toFixed(1)}px and the argument under it at ` +
        `${proseEdge!.px.toFixed(1)}px, so the two do not share the edge they read as sharing`,
    ).toBeLessThanOrEqual(2);
    expect(
      ledeEdge!.fontRelative,
      `"${lede.className}" caps a 13px line in a unit that follows the font size, which is the ` +
        "one class two font sizes two widths this band already shipped once",
    ).toBe(false);
  });

  /**
   * What `58ch` on both blocks actually drew, recomputed rather than quoted.
   *
   * The comment beside the lede in `finding-detail.tsx` argues from this pair, and both halves
   * of it were wrong for six rounds — 501px, because the lede is `font-semibold` and a `ch` was
   * being resolved at 400 on a block set at 600. A number in a comment is a copy of a
   * measurement and copies drift, so the copy is here where it can fail.
   *
   * The classes are written out because this is a counterfactual: neither block carries `58ch`
   * any more, and putting it back on a live class list would be asserting about a document that
   * does not exist. What keeps it honest is the sizes and the weight, which are read off the
   * shipped blocks by the test above.
   */
  it("resolves one `58ch` on the lede and the argument to two different widths", () => {
    const argumentEdge = rightEdge({ className: "max-w-[58ch] text-[16px]" } as Element)!;
    const ledeEdge = rightEdge({
      className: "max-w-[58ch] text-[13px] font-semibold",
    } as Element)!;

    // 58 x 16 x 0.665 and 58 x 13 x 0.6618, which is the resolved cap. Chromium draws 617.11
    // and 498.98 against the shipped face, each snapped down to a 1/64px layout unit — so a
    // rectangle measured in a browser reads up to 0.02px under the figure asserted here, and
    // that is the snap rather than a disagreement.
    expect(Number(argumentEdge.px.toFixed(2))).toBe(617.12);
    expect(Number(ledeEdge.px.toFixed(2))).toBe(499.0);
    // 118.12, not the 115.70 that reading the semibold lede at 400 gives.
    expect(Number((argumentEdge.px - ledeEdge.px).toFixed(2))).toBe(118.12);
  });

  /**
   * The half of defect 9 that comparing two declared measures cannot see, and the reason the
   * comparison above is no longer the guard.
   *
   * `rightEdge` reads two numbers off two class lists and asks whether they agree. Both numbers
   * are honest and the question is the wrong one, because a declared measure is a *cap* and
   * what a block is actually drawn at is `min(cap, the width of the box it is in)`. Put the two
   * blocks in boxes of different widths and two caps a pixel apart draw two edges 34 apart, and
   * nothing in jsdom can tell — jsdom computes no layout, so it never has the second term.
   *
   * That is exactly what the band did. The verdict's sentence stood above the grid, in the full
   * width of the section, capped at 38.5rem = 616px; the argument stood in a `1fr` track beside
   * a 20rem rail and a 2rem gap. Swept in a browser: at a 1024px viewport the argument's column
   * is 582px and the sentence's right edge is **34.00px** past it, 18.00px at 1040, and only
   * from about 1060 up do the two agree to the deliberate 1.11px. It was invisible because the
   * three strings `lib/format` can put here are 51, 60 and 60 characters and none of them
   * reaches 582px — a guarantee held by the length of three strings is not a guarantee.
   *
   * So the property is stated as containment instead of as arithmetic. The sentence and the
   * argument are in the same grid, in the same column of it, and the sentence is therefore
   * bounded by the argument's own track at every width there will ever be. That is checkable
   * without a layout engine, which is the point: it is a fact about the document, not about the
   * pixels. Break it by taking the `<p>` back out of the grid, or by moving either one to a
   * different `col-start` — and `tests/browser/test_workspace.py` measures the rectangles the
   * containment produces, on the widths the residual was found at.
   */
  it("puts the lede inside the argument's own column, where no cap can take it wider", () => {
    const review = reviewFixture();
    const finding = held(review);
    const { body } = draw(finding);

    const lede = screen.getByText(verdictOf(finding.verdict).description!);
    const [prose] = argument(body);
    const grid = prose.parentElement!;

    expect(
      lede.parentElement,
      "the verdict's sentence is laid out beside the grid rather than inside it, so its cap is " +
        "the only thing standing between it and the panel's full width",
    ).toBe(grid);

    // Placed rather than auto-flowed, so the column each one takes is written down and can be
    // compared. Auto-placement would put the argument in the rail's column anyway, so this is
    // not a stylistic preference — but which cell each takes is the whole assertion.
    const column = (element: Element) =>
      /(?:^|\s)lg:col-start-(\d+)/.exec(element.className)?.[1] ?? null;
    expect(column(lede), `no column placed on "${lede.className}"`).not.toBeNull();
    expect(
      column(lede),
      `the lede is placed in column ${column(lede)} and the argument in ${column(prose)}, which ` +
        "are two tracks of different widths — the residual defect 9 was reopened by",
    ).toBe(column(prose));

    // And above it, not beside it: same column, earlier row. Without this the pair could share
    // a track and still be drawn side by side.
    const row = (element: Element) =>
      Number(/(?:^|\s)lg:row-start-(\d+)/.exec(element.className)?.[1] ?? NaN);
    expect(row(lede)).toBeLessThan(row(prose));
  });

  /**
   * The rhythm, and the guarantee that comes with it: the model's string is cut on its own
   * sentence boundaries and every part is a raw slice, so the words on screen are the words
   * that were recorded. A splitter that trimmed, normalised or dropped anything would be
   * editing a judgement, which is the one thing this product may not do.
   *
   * Against `plainProse(source)` and not against `source`, and the difference is the whole
   * subject of the file the assertion is about. A backticked name is drawn as a `<code>` chip,
   * and a chip's `textContent` is the name without its delimiters — so the recorded string and
   * what a reader sees differ by exactly the backticks, on both of these fixtures and on 64 of
   * the 375 recorded judgements. `plainProse` is the product's own answer to "what does this
   * paragraph say, as a string", so comparing to it checks the two things that matter at once:
   * every word survived the cut, and every delimiter was consumed by a chip rather than left
   * on screen. Comparing to the raw source instead asserts that the renderer did not run.
   */
  it("cuts the argument into its own sentences and loses nothing", () => {
    // A name from each fixture, and a different one in each, because the point is that the
    // *span* survived the cut and a name only proves that in the string it came from. The
    // quoted one is the harder case: its span sits in a bracketed aside two words after the
    // full stop that ends the sentence before it.
    const quoted = { [RECORDED.median]: "NarrationPreparationProvider", [RECORDED.quoting]: "_REPOSITORY" };

    for (const source of [RECORDED.median, RECORDED.quoting]) {
      const review = reviewFixture();
      const { body, band } = draw({ ...held(review), reasoning: source }, review);
      const [prose] = argument(body);
      const paragraphs = Array.from(prose.querySelectorAll("p"));

      expect(paragraphs.length).toBeGreaterThan(1);
      expect(paragraphs.map((p) => p.textContent).join(" ")).toBe(plainProse(source));
      // Every part still renders its quoted names as names, so no cut landed inside a span —
      // which would put two literal backticks on screen, one on each side of the break.
      expect(prose.textContent).not.toContain("`");
      const chips = within(band).getAllByText(quoted[source]);
      expect(chips.length).toBeGreaterThan(0);
      expect(chips[0].tagName).toBe("CODE");
    }
  });

  /**
   * `whitespace-pre-line` is a device, not a guard, and the pass before this one had it the
   * other way round on the evidence of a 231-string sample. Two of the 375 recorded
   * judgements break a paragraph of their own, and one of the two argues through a numbered
   * list under that break. Rendered without this the list runs together into one paragraph;
   * split naively, "1." is cut off the point it numbers and left trailing the block above.
   */
  it("keeps the line breaks a model actually wrote", () => {
    const review = reviewFixture();
    const { body } = draw({ ...held(review), reasoning: RECORDED.numbered }, review);
    const [prose] = argument(body);
    const paragraphs = Array.from(prose.querySelectorAll("p"));

    for (const paragraph of paragraphs) {
      expect(paragraph.className).toContain("whitespace-pre-line");
    }
    // The numbered points are one block with the model's own breaks in it, and each number is
    // still attached to the point it introduces.
    const list = paragraphs.find((p) => p.textContent?.includes("1."))!;
    expect(list.textContent).toMatch(/policies:\n1\. /);
    expect(list.textContent).toMatch(/variation\.\n2\. /);
    expect(paragraphs.some((p) => p.textContent?.trim().endsWith("1."))).toBe(false);
  });

  /**
   * The band's shape: one column on a phone, two from `lg`. The rail comes after the argument
   * in the DOM, which is what makes the stacked order below `lg` read correctly — and it is
   * why the verdict's sentence had to leave the rail rather than be reordered inside it.
   */
  it("puts the rail after the argument, in one column below lg and two above", () => {
    const review = reviewFixture();
    const finding = held(review);
    const { body, band } = draw(finding);
    const [prose] = argument(body);
    const grid = prose.parentElement!;

    expect(grid.className).toContain("grid");
    // No unprefixed track list: below `lg` this is one column, which is the stacking the
    // reading order above depends on.
    expect(grid.className).not.toMatch(/(^|\s)grid-cols-/);
    const tracks = /(?:^|\s)lg:grid-cols-\[([^\]]+)\]/.exec(grid.className);
    expect(tracks, `no lg track list in "${grid.className}"`).not.toBeNull();
    expect(tracks![1].split("_")).toHaveLength(2);

    // The last of the grid's three children, not the second: the verdict's sentence is inside
    // this grid now — see the containment test below — so the rail is the argument's neighbour
    // by placement rather than by index.
    const rail = grid.lastElementChild as HTMLElement;
    expect(comesBefore(prose, rail)).toBe(true);
    // The rail's rule ends where the rail's content ends. A grid item stretches down its row
    // by default, so without this the hairline ran the height of the *argument* — 239px of
    // margin note at the top of an 1,147px border on the longest recorded reasoning, and the
    // rest of it a line with nothing beside it. The border and the alignment are one decision:
    // a rail that draws an edge has to be told where to stop drawing it.
    //
    // These two lines are the weakest assertions in the file and it is worth saying which way.
    // Every other bound here is arithmetic a reader can redo — a measure times an advance, a
    // document order, a variant's own class list. These two name a *layout property* that jsdom
    // does not compute, so they can only see whether the class was written, never whether the
    // rule stopped. They catch the regression that actually happened, which was somebody
    // deleting `lg:self-start` as redundant; they would not catch an `items-stretch` on the
    // grid, a `min-h-full` on the rail, or a child that grows it. The real guard is a rectangle
    // read in a browser and it belongs in `tests/browser/`, which is where the layout is.
    expect(rail.className).toMatch(/\blg:border-l\b/);
    expect(rail.className).toMatch(/\blg:self-start\b/);
    // The rail's first line sits on the argument's first line rather than a gap below it,
    // because the sentence that used to open the rail is now above the whole grid.
    const first = rail.firstElementChild!;
    expect(first.className).toContain("mt-0");
    expect(within(band).getByText(/Judged against case revision/)).toBe(first);
  });

  /**
   * The demotion, and the reason it is a test rather than a preference.
   *
   * `--held` is `#0a0a0a` because the design system deliberately took the chroma off a held
   * verdict — "present, not an alarm" — and a filled `--accent-fill` button put the alarm
   * colour back on the held row four centimetres below it, as the only chromatic object in
   * 1,272px of body. `verdict-hues.test.ts` cannot see that, because the red arrives through
   * `ui/button.tsx`, which is on the accent allowlist for its own reasons. This is where it
   * is visible: no accent anywhere inside an open finding.
   */
  it("spends no accent inside an open finding", () => {
    const review = reviewFixture();
    const { body } = draw(held(review));
    const chromatic = elements(body).filter((element) => /-accent/.test(element.className));
    expect(chromatic.map((element) => element.className)).toEqual([]);
  });

  /**
   * Where the way out to the round lives, which is the other half of the same decision. It
   * was demoted rather than moved: it navigates (`onOpen("clarification")`), it writes no
   * record, and it belongs beside the question it answers rather than among Accept / Park /
   * Waive, where a fourth control that decides nothing would read as a fourth disposition.
   */
  it("offers the way out to the round from beside the question it answers", () => {
    const review = reviewFixture();
    const finding = held(review);
    const { onAnswer } = draw(finding);

    const button = screen.getByRole("button", { name: /Answer it/ });
    const described = document.getElementById(button.getAttribute("aria-describedby")!);
    expect(described?.textContent).toBe(finding.hinge);
    // Inside the block that holds the question, not in the decision bar and not in a corner
    // of the band.
    expect(described!.parentElement!.contains(button)).toBe(true);
    // The accessible name is the visible words. It used to fold the whole question into an
    // `aria-label`, which left nothing to say for anyone driving the page by voice.
    expect(button.textContent?.trim()).toBe("Answer it");
    expect(button.getAttribute("aria-label")).toBeNull();
    // The 44px floor survives the demotion — `size="md"` carries it, so the hand-written
    // `min-h-11` beside it could go.
    expect(button.className).toContain("min-h-11");
    expect(onAnswer).not.toHaveBeenCalled();
  });

  /**
   * The two controls in an open row that decide nothing are not drawn as decisions.
   *
   * `secondary` is the decision bar's recipe — the control film, a rim, an edge to pick the box
   * up by — and in an open finding it means *this writes a `StandingDecision`*. "Answer it" and
   * "Judgement context" both leave the row and write nothing, so wearing it had five controls
   * saying the same thing about themselves, two of them falsely.
   *
   * The recipe is what is asserted because the recipe is the whole of the difference. That is
   * not the rail's `lg:border-l` problem a few tests above, where a class string stands in for
   * a layout property jsdom cannot see: a variant IS a class list, so this reads the thing
   * itself. Break it by putting `variant="secondary"` back on either control.
   *
   * The two absences are matched unprefixed. `buttonClass` puts `disabled:bg-control` and
   * `aria-disabled:border-rule-control` on every button in the product, so a substring test
   * here would read the off state as the resting one and fail on all six variants.
   */
  it("draws a way out of the row as a way out, not as a disposition", () => {
    const review = reviewFixture();
    render(
      <MemoryRouter>
        <FindingBody
          review={review}
          finding={held(review)}
          onAnswer={vi.fn()}
          onOpenContext={vi.fn()}
        />
      </MemoryRouter>,
    );

    for (const name of [/Answer it/, /Judgement context/]) {
      const control = screen.getByRole("button", { name });
      expect(control.className, `${name} should be underlined`).toContain("underline");
      // The two classes that are the `secondary` recipe: the film, and the edge on it.
      expect(control.className, `${name} should have no film`).not.toMatch(/(?:^|\s)bg-control\b/);
      expect(control.className, `${name} should have no edge`).not.toMatch(
        /(?:^|\s)border-rule-control\b/,
      );
    }
  });

  /**
   * A cleared finding is the shape the rail is thinnest on: it carries neither a hinge nor a
   * recommendation, so the whole rail is one footnote. The band still has to introduce itself,
   * which is the property that survives whatever the rail becomes.
   *
   * Not by `domain/finding.py`, which this used to name. `Finding.__post_init__` forbids a hinge
   * *beside* a recommendation and a recommendation on a non-material finding, and it takes a
   * cleared finding carrying a hinge alone without complaint. The refusal is
   * `FindingOutput.the_verdict_carries_what_it_is_allowed_to` in
   * `reasoning/adapters/langchain.py`, and it is why 306 of the 375 recorded judgements — every
   * cleared and material one — have no control in this rail at all. That is also the bound on
   * how far down a phone the one control here can be pushed, which `tests/browser/test_mobile.py`
   * measures, because this file cannot.
   */
  it("leads a cleared finding with its verdict too", () => {
    const review = reviewFixture();
    const cleared = review.findings.find((finding) => finding.verdict === "cleared")!;
    const { body } = draw(cleared, review);

    const lede = screen.getByText(verdictOf("cleared").description!);
    const [prose] = argument(body);
    expect(comesBefore(lede, prose)).toBe(true);
    expect(screen.queryByRole("button", { name: /Answer it/ })).toBeNull();
  });
});
