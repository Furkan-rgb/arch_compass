import { describe, expect, it } from "vitest";

import {
  NAMED_WEIGHTS,
  ZERO_ADVANCE_EM,
  chMeasure,
  declaredWeight,
  zeroAdvanceEm,
  zeroAdvanceFor,
} from "./onest.test-metrics";

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
 * the rectangle Chromium lays out, and it was measured rather than derived: `vite build`, the
 * built `assets/` served over HTTP so `@font-face` resolves to the shipped `onest.woff2`, both
 * weights requested with `document.fonts.load` and asserted with `document.fonts.check` before a
 * single rectangle is read — without that check `font-display: swap` answers with a fallback
 * whose zero is 0.6299em and every width below comes out five per cent wrong. A block-level div
 * given `width: <n>ch` at each size and weight was then measured with
 * `getBoundingClientRect`. All nine came back as `Math.floor(resolved * 64) / 64` exactly, so the
 * relation is asserted as a rule below rather than carried as nine more hand-copied numbers.
 */
describe("Onest's font model", () => {
  /**
   * The advances themselves, restated once — here, where a change to them fails a test.
   *
   * This is the only assertion in the repository that quotes the two numbers rather than
   * deriving from them, and it is deliberate: something has to pin them, and a test that fails
   * with "the shipped face's zero moved" is a better place for that than a paragraph nobody runs.
   * Re-read them off `frontend/src/assets/fonts/onest.woff2` with the `fontTools` recipe in
   * `ui/onest.test-metrics.ts` — 665 units on a 1000-unit em at wght 400, 661.8 at 600, the
   * second interpolated from the HVAR AdvWidthMap delta and **not** taken from
   * `varLib.instancer`, which rounds it to 662 and no browser does.
   */
  it("keeps one zero advance per weight, read off the shipped face", () => {
    expect(ZERO_ADVANCE_EM).toEqual({ 400: 0.665, 600: 0.6618 });
    expect(zeroAdvanceEm(400, "the body text")).toBe(0.665);
    expect(zeroAdvanceEm(600, "a heading")).toBe(0.6618);
  });

  /**
   * The throw is the feature, and this is the test that says so.
   *
   * Returning 400's advance for an unmeasured weight is precisely how a heading set at 600 came
   * to be described at 400 for six passes: the error is half a per cent, which is small enough
   * that nobody re-derives it and large enough to make every figure in a comment wrong. So an
   * unmeasured weight stops the suite, and the message says where to go and read one.
   */
  it("refuses to guess an advance for a weight nobody has measured", () => {
    expect(() => zeroAdvanceEm(700, "a heading that gained `font-bold`")).toThrow(
      /no measured zero advance for Onest at weight 700/,
    );
    expect(() => zeroAdvanceFor("text-sm font-bold")).toThrow(/font-bold/);
    expect(() => zeroAdvanceFor("text-lg font-medium")).toThrow(/weight 500/);
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
   * The 14px pair is the whole of round seven. `markdown.tsx`'s `####` label and its paragraphs
   * are both `text-sm`, so a reader who checks only the size concludes they share a measure —
   * and they do not, because the label is `font-semibold`. 46ch is 426.20px on the label and
   * 428.26px on the paragraph, two pixels apart, and the reason the shared measure is written in
   * `rem` is that neither of them should be the one the other inherits.
   */
  it("resolves every `ch` figure the tree argues from", () => {
    const rows: [string, number, number, string, number][] = [
      // count, size, classes, resolved px
      ["markdown.tsx — the document title", 46, 24, "font-semibold", 730.63],
      ["markdown.tsx — the section heading that draws the rule", 46, 18, "font-semibold", 547.97],
      ["markdown.tsx — the candidate heading", 46, 15, "font-semibold", 456.64],
      ["markdown.tsx — the `####` label", 46, 14, "font-semibold", 426.2],
      ["markdown.tsx — the paragraphs, lists and blockquote", 46, 14, "", 428.26],
      ["prose.tsx — the model's argument", 58, 16, "", 617.12],
      ["finding-detail.tsx — the lede, at the argument's 58ch", 58, 13, "font-semibold", 499.0],
      ["finding-detail.tsx — the lede, at the footnote's 46ch", 46, 13, "font-semibold", 395.76],
      ["finding-detail.tsx — the footnote", 46, 12, "", 367.08],
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
   * comments explained that gap in prose each time it came up. It is a rule, it was measured on
   * all nine rows above, and it belongs in one assertion.
   */
  it("snaps a drawn rectangle down to a layout unit, and never by more than one", () => {
    for (const [count, size, classes, drawn] of [
      [46, 24, "font-semibold", 730.625],
      [46, 18, "font-semibold", 547.96875],
      [46, 15, "font-semibold", 456.640625],
      [46, 14, "font-semibold", 426.1875],
      [46, 14, "", 428.25],
      [58, 16, "", 617.109375],
      [58, 13, "font-semibold", 498.984375],
      [46, 13, "font-semibold", 395.75],
      [46, 12, "", 367.078125],
    ] as [number, number, string, number][]) {
      const measured = chMeasure(count, size, classes);
      expect(measured.drawn, `${count}ch at ${size}px "${classes}"`).toBe(drawn);
      expect(measured.resolved - measured.drawn).toBeGreaterThanOrEqual(0);
      expect(measured.resolved - measured.drawn).toBeLessThan(1 / 64);
    }
  });
});
