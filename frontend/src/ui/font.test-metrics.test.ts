import { describe, expect, it } from "vitest";

import {
  NAMED_WEIGHTS,
  ZERO_ADVANCE_EM,
  chMeasure,
  declaredWeight,
  zeroAdvanceEm,
  zeroAdvanceFor,
} from "./font.test-metrics";

/**
 * The one place every `ch` figure in the tree is computed, so that no comment has to hold one.
 *
 * Seven rounds of wrong numbers have shipped on this surface, and the seventh was written into a
 * comment by the sixth round's repair — a heading described at weight 400 in a paragraph whose
 * entire subject was that a `ch` follows weight. The pattern is not carelessness. A number
 * written in prose is a copy of a measurement, and copies drift; being careful is what the
 * previous six passes tried.
 *
 * So the figures are not written in prose any more. Each one is `count x size x advance` over the
 * type its own block declares, computed here, and the comments that argue from a figure name this
 * test instead of restating it. Change an advance, a size or a weight and this file says which
 * figures moved and by how much — which is the thing a comment can never do.
 *
 * **Where the two columns come from.** `resolved` is arithmetic and needs no browser. `drawn` is
 * the rectangle Chromium lays out, and the rule relating the two was measured rather than
 * derived: `vite build`, the built `assets/` served over HTTP so `@font-face` resolves to the
 * shipped woff2, every weight requested with `document.fonts.load` and asserted with
 * `document.fonts.check` before a single rectangle is read — without that check
 * `font-display: swap` answers with a fallback whose zero is 0.6299em and every width below
 * comes out five per cent wrong. A block-level div given `width: <n>ch` at each size and weight
 * was then measured with `getBoundingClientRect`. All nine came back as
 * `Math.floor(resolved * 64) / 64` exactly, so the relation is asserted as a rule below rather
 * than carried as nine more hand-copied numbers.
 *
 * **That sweep was Onest's, and the face is IBM Plex Sans.** The rule is a property of
 * Chromium's 1/64px layout grid and carries over; the nine rectangles do not, and they have not
 * been re-swept. Both columns below are therefore arithmetic today, which is worth saying out
 * loud because the second test reads as a browser assertion and currently is not one.
 */
describe("the shipped face's font model", () => {
  /**
   * The advances themselves, restated once — here, where a change to them fails a test.
   *
   * This is the only assertion in the repository that quotes the numbers rather than deriving
   * from them, and it is deliberate: something has to pin them, and a test that fails with "the
   * shipped face's zero moved" is a better place for that than a paragraph nobody runs. It is
   * also the assertion that did **not** fail when the face moved, because it pins a constant
   * rather than reading the font — Onest's 0.665 and 0.6618 sat here green for a whole revision
   * after `onest.woff2` was deleted from the tree. What makes that survivable is the four
   * entries being four readings of four files: re-read them off
   * `frontend/src/assets/fonts/plex-sans-{400,500,600,700}.woff2` with the `fontTools` recipe in
   * `ui/font.test-metrics.ts` — 600 units on a 1000-unit em in every one, with no `fvar`, no
   * `HVAR` and nothing to interpolate.
   *
   * The four agreeing is a fact about IBM Plex Sans and not a rule of the system. Onest's zero
   * narrowed from 665 units at 400 to 661.8 at 600 because it was one variable file, and the
   * whole of round six was a shared `ch` resolved at the wrong end of that. The table stays
   * keyed by weight so the next face is allowed to disagree with itself again.
   */
  it("keeps one zero advance per weight, read off the shipped face", () => {
    expect(ZERO_ADVANCE_EM).toEqual({ 400: 0.6, 500: 0.6, 600: 0.6, 700: 0.6 });
    expect(zeroAdvanceEm(400, "the body text")).toBe(0.6);
    expect(zeroAdvanceEm(600, "a heading")).toBe(0.6);
    expect(zeroAdvanceEm(700, "a block label")).toBe(0.6);
  });

  /**
   * The throw is the feature, and this is the test that says so.
   *
   * Returning 400's advance for an unmeasured weight is precisely how a heading set at 600 came
   * to be described at 400 for six passes under the variable face: the error was half a per
   * cent, which is small enough that nobody re-derives it and large enough to make every figure
   * in a comment wrong. Under four static cuts that all measure the same, the throw is guarding
   * something else and something worse — a weight with no entry is a weight `styles.css` does
   * not download, so its `ch` resolves against whatever the fallback stack hands over, and the
   * only honest answer is to stop rather than to hand back 0.6.
   *
   * Which is why the weights probed here moved with the face. 700 used to be the unmeasured one
   * and is now a cut the product ships; 300 and 900 are the two ends nothing downloads.
   */
  it("refuses to guess an advance for a weight nobody has measured", () => {
    expect(() => zeroAdvanceEm(300, "a heading that gained `font-light`")).toThrow(
      /no measured zero advance at weight 300/,
    );
    expect(() => zeroAdvanceFor("text-sm font-black")).toThrow(/font-black/);
    expect(() => zeroAdvanceFor("text-lg font-thin")).toThrow(/weight 100/);
  });

  /**
   * Which weight a class list is actually asking for, including the two ways of asking for none.
   *
   * `font-display`, `font-sans` and `font-mono` are the trap: they share the prefix, they say
   * nothing about weight, and a table that matched them would resolve a `ch` against a weight no
   * element declared. The word-boundary match is what keeps `font-semibold` out of a class list
   * that only contains `font-semibold-ish` — and, more usefully, keeps a substring match from
   * reading `font-bold` inside `font-extrabold`.
   */
  it("reads the weight a class list declares, and only a weight", () => {
    expect(declaredWeight("text-sm font-semibold uppercase")).toBe(600);
    expect(declaredWeight("my-3 text-sm leading-7 text-ink-2")).toBe(400);
    expect(declaredWeight("font-display text-lg tracking-tight")).toBe(400);
    expect(declaredWeight("font-mono text-[0.86em]")).toBe(400);
    expect(declaredWeight("font-extrabold")).toBe(800);
    expect(Object.keys(NAMED_WEIGHTS)).toHaveLength(9);
    expect(Object.keys(NAMED_WEIGHTS).some((name) => /^font-(display|sans|mono)$/.test(name))).toBe(
      false,
    );
  });

  /**
   * Every derived width this repository argues from, in one table.
   *
   * Each row names the block that sets it and the file whose comment used to carry the number.
   * The point of collecting them here rather than asserting each beside its own component is
   * that the mistakes have always been *between* the rows: the same `46ch` read at 400 on a
   * block set at 600, or one row's figure quoted in another row's comment. Side by side, a
   * weight mismatch is visible as an arithmetic difference instead of invisible as a habit.
   *
   * The 14px pair is the whole of round seven, and it is the row the face change settled.
   * `markdown.tsx`'s `####` label and its paragraphs are both `text-sm`, so a reader who checked
   * only the size concluded they shared a measure — and under Onest they did not, because the
   * label is `font-semibold` and a variable face's zero narrows with the instance: 426.20px on
   * the label against 428.26px on the paragraph, two pixels apart. Under Plex Sans's four static
   * cuts they are both 386.40px and the pair really does agree.
   *
   * The row is kept, at the same two class lists, precisely because it now agrees. A shared
   * measure that is true of this face and was false of the last one is a coincidence the system
   * is not allowed to start relying on — the reason a measure shared across sizes is still
   * written in `rem` is unchanged, and this row is where a face that reintroduces the spread
   * would announce itself instead of quietly moving one of the two edges.
   */
  it("resolves every `ch` figure the tree argues from", () => {
    const rows: [string, number, number, string, number][] = [
      // count, size, classes, resolved px
      ["markdown.tsx — the document title", 46, 24, "font-semibold", 662.4],
      ["markdown.tsx — the section heading that draws the rule", 46, 18, "font-semibold", 496.8],
      ["markdown.tsx — the candidate heading", 46, 15, "font-semibold", 414.0],
      ["markdown.tsx — the `####` label", 46, 14, "font-semibold", 386.4],
      ["markdown.tsx — the paragraphs, lists and blockquote", 46, 14, "", 386.4],
      ["prose.tsx — the model's argument", 58, 16, "", 556.8],
      ["finding-detail.tsx — the lede, at the argument's 58ch", 58, 13, "font-semibold", 452.4],
      ["finding-detail.tsx — the lede, at the footnote's 46ch", 46, 13, "font-semibold", 358.8],
      ["finding-detail.tsx — the footnote", 46, 12, "", 331.2],
    ];
    for (const [where, count, size, classes, expected] of rows) {
      const { resolved } = chMeasure(count, size, classes);
      expect(Number(resolved.toFixed(2)), `${count}ch at ${size}px "${classes}" — ${where}`).toBe(
        expected,
      );
    }
  });

  /**
   * The relation between the arithmetic and the rectangle, so a comment never has to hold both.
   *
   * Chromium lays a box out on a 1/64px grid and snaps **down**, so the drawn width is always at
   * or just under the resolved one — by up to 0.0156px, which is why a resolved figure and a
   * browser reading of it agree to one decimal place and disagree at three. Six rounds of these
   * comments explained that gap in prose each time it came up. It is a rule, and it belongs in
   * one assertion.
   *
   * **Say what this is today.** The rule was measured on all nine rows above — a headless
   * Chromium, the built stylesheet, the face waited on — and every one came back at
   * `Math.floor(resolved * 64) / 64`. That sweep was run against Onest. The nine numbers here
   * are the same rule applied to Plex Sans's advance and have not been read off a browser, so
   * this test currently asserts arithmetic against arithmetic and would not catch the rule
   * itself turning out to be about the old face. Re-running the sweep is in
   * `docs/known-defects.md`; keeping the row shapes and the exact-snap assertion is what makes
   * re-running it a comparison rather than a fresh guess.
   */
  it("snaps a drawn rectangle down to a layout unit, and never by more than one", () => {
    for (const [count, size, classes, drawn] of [
      [46, 24, "font-semibold", 662.390625],
      [46, 18, "font-semibold", 496.796875],
      [46, 15, "font-semibold", 414],
      [46, 14, "font-semibold", 386.390625],
      [46, 14, "", 386.390625],
      [58, 16, "", 556.796875],
      [58, 13, "font-semibold", 452.390625],
      [46, 13, "font-semibold", 358.796875],
      [46, 12, "", 331.1875],
    ] as [number, number, string, number][]) {
      const measured = chMeasure(count, size, classes);
      expect(measured.drawn, `${count}ch at ${size}px "${classes}"`).toBe(drawn);
      expect(measured.resolved - measured.drawn).toBeGreaterThanOrEqual(0);
      expect(measured.resolved - measured.drawn).toBeLessThan(1 / 64);
    }
  });
});
