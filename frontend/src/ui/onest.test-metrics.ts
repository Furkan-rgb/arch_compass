/**
 * Onest's zero advance, read off the shipped font — the one copy of it in the repository.
 *
 * A `ch` is the advance width of the used font's digit zero, so every measure written in `ch`
 * is this number times a size. Two test files argue from it: `ui/markdown.test.tsx` over the
 * seven renderers of a document, and `features/review/finding-detail.test.tsx` over the lede
 * and the argument it stands above. They each held their own hand-copied table of it, which is
 * the same shape as the defect they exist to catch — a measured value copied into prose drifts,
 * and a measured value copied into two files drifts twice. It is here so there is one.
 *
 * **It is one number per weight, not one number.** `styles.css` gives Onest a single
 * `@font-face` spanning `font-weight: 400 700`, so the shipped `onest.woff2` is a variable font
 * and the browser instances it at whatever weight the element asks for; the zero narrows as the
 * instance gets heavier. Stating the 400 value as "the whole definition of a `ch`" is what made
 * the sixth round of these figures wrong, because the headings and ledes that carried a shared
 * `ch` are all `font-semibold`.
 *
 * HOW TO READ THESE OFF THE FONT AGAIN, since nothing here can:
 *
 *     from fontTools.ttLib import TTFont
 *     from fontTools.varLib.models import normalizeLocation
 *     from fontTools.varLib.varStore import VarStoreInstancer
 *     f = TTFont("frontend/src/assets/fonts/onest.woff2")
 *     zero = f.getBestCmap()[ord("0")]                       # -> "zero"
 *     base = f["hmtx"][zero][0]                              # -> 665 units on a 1000-unit em
 *     axes = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in f["fvar"].axes}
 *     hvar = f["HVAR"].table                                 # axes -> {"wght": (100, 400, 900)}
 *     inst = VarStoreInstancer(hvar.VarStore, f["fvar"].axes,
 *                              normalizeLocation({"wght": 600}, axes))
 *     base + inst[hvar.AdvWidthMap.mapping[zero]]            # -> 661.8
 *
 * The `wght` axis runs 100–900 with its default at 400 and the file carries no `avar` table, so
 * the delta interpolates linearly: −8 units at 900 puts 600 at 400's 665 minus 3.2. Do **not**
 * take 662 from `fontTools.varLib.instancer` — that is 661.8 rounded to an integer unit, and no
 * browser rounds it.
 *
 * Chromium agrees to five decimals. A `width: 100ch` box against the shipped face, with both
 * weights loaded through `document.fonts.load` and confirmed through `document.fonts.check`
 * before anything is read, draws 1064px at 16px/400 and 1058.875px at 16px/600 — 0.665em and
 * 0.6618em, the second snapped down to a 1/64px layout unit. Without the `fonts.check` the
 * `font-display: swap` in `styles.css` answers with a fallback whose zero is 0.6299em and every
 * width comes out five per cent wrong.
 *
 * Keyed by weight and deliberately not interpolated. A weight with no entry throws rather than
 * falling back to 400, so an element that gains `font-medium` or `font-bold` stops the suite
 * until somebody has read that advance off the font instead of inheriting a number that was
 * never about it.
 */
export const ZERO_ADVANCE_EM: Record<number, number> = { 400: 0.665, 600: 0.6618 };

/**
 * The advance for one weight, or a loud failure naming what to do about it.
 *
 * The throw is the point. Returning 400's number for an unmeasured weight is exactly how a
 * heading set at 600 came to be described at 400 for six passes, and a silent half-per-cent
 * error is the kind nobody re-derives.
 */
export function zeroAdvanceEm(weight: number, context: string): number {
  const advance = ZERO_ADVANCE_EM[weight];
  if (advance === undefined) {
    throw new Error(
      `no measured zero advance for Onest at weight ${weight} (${context}) — read it off the ` +
        `HVAR delta of the shipped onest.woff2 and add it to ZERO_ADVANCE_EM in ` +
        `ui/onest.test-metrics.ts`,
    );
  }
  return advance;
}

/**
 * Every weight utility Tailwind has, not only the two this product happens to set.
 *
 * All nine are listed so an unrecognised one cannot be read as the inherited 400. A heading that
 * gains `font-bold` resolves to 700, 700 has no measured advance, and `zeroAdvanceEm` throws —
 * which is the failure that says "go and read 700 off the font". Falling back to 400 instead
 * would report that heading 0.7% too wide and put the blame on the number rather than on the
 * class that changed.
 *
 * The family utilities `font-display`, `font-sans` and `font-mono` are deliberately absent. They
 * share the prefix and say nothing about weight, and matching them would resolve a `ch` against
 * a weight nobody declared.
 *
 * This table stood twice — in `ui/markdown.test.tsx` and again in
 * `features/review/finding-detail.test.tsx` — beside two copies of the advances above. That is
 * the defect those two files exist to catch, one layer up: the seventh round of wrong figures on
 * this surface was a `ch` resolved at the wrong weight, written in a comment whose whole subject
 * was that a `ch` follows weight. Two copies of the constant a pass exists to correct is the same
 * bug wearing a different hat, so there is one copy and both files import it.
 */
export const NAMED_WEIGHTS: Record<string, number> = {
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

/**
 * The weight a class list declares, in the `font-weight` numbers, defaulting to the inherited 400.
 *
 * 400 is the right default and not a guess: `styles.css` sets the document at 400, so a block
 * declaring no weight utility really is set there. The guess this file refuses to make is the
 * other one — resolving an advance for a weight nobody measured — and that refusal lives in
 * `zeroAdvanceEm`, not here.
 */
export function declaredWeight(classes: string): number {
  for (const [name, weight] of Object.entries(NAMED_WEIGHTS)) {
    if (new RegExp(`(?:^|\\s)${name}(?:\\s|$)`).test(classes)) return weight;
  }
  return 400;
}

/**
 * The zero advance a class list's own type resolves to, or a loud failure naming the class list.
 *
 * This is the call both test files make, and having it here rather than in each of them is the
 * point: a `ch` on a class list is one question — which weight, and what is that weight's zero —
 * and it now has one answer.
 */
export function zeroAdvanceFor(classes: string): number {
  return zeroAdvanceEm(declaredWeight(classes), `"${classes}"`);
}

/**
 * The width a `ch` measure resolves to, in px, and the rectangle Chromium draws for it.
 *
 * Two numbers rather than one, because the tree's comments quote both and the difference between
 * them is a rule rather than a second measurement. `resolved` is `count x size x advance`, which
 * is arithmetic any reader can redo. `drawn` is that snapped **down** to a 1/64px layout unit,
 * which is what a `getBoundingClientRect` in a headless Chromium comes back with: measured on all
 * nine of the widths this repository argues from — 46ch at 24/18/15/14px semibold and 14/13/12px
 * regular, 58ch at 16px regular and 13px semibold — and `Math.floor(resolved * 64) / 64` gives
 * every one of them exactly. `ui/onest.test-metrics.test.ts` states that measurement as a table
 * so the two figures beside each other in a comment are one figure and a rule.
 *
 * A layout unit is Chromium's, not CSS's, so this is a fact about one engine. It is asserted
 * rather than assumed for exactly that reason: if the number ever moves, the table fails with
 * both readings in the message instead of a comment quietly going stale.
 */
export function chMeasure(count: number, sizePx: number, classes: string) {
  const resolved = count * sizePx * zeroAdvanceFor(classes);
  return { resolved, drawn: Math.floor(resolved * 64) / 64 };
}
