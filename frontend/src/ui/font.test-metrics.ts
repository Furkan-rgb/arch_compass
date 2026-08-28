/**
 * IBM Plex Sans's zero advance, read off the shipped font — the one copy of it in the repository.
 *
 * A `ch` is the advance width of the used font's digit zero, so every measure written in `ch`
 * is this number times a size. Two test files argue from it: `ui/markdown.test.tsx` over the
 * seven renderers of a document, and `features/review/finding-detail.test.tsx` over the lede
 * and the argument it stands above. They each held their own hand-copied table of it, which is
 * the same shape as the defect they exist to catch — a measured value copied into prose drifts,
 * and a measured value copied into two files drifts twice. It is here so there is one.
 *
 * **The file is named for the job and not for the face, because the face moved and the name
 * did not.** It was `ui/onest.test-metrics.ts` while the product was set in Onest, and the
 * rename is part of the repair rather than tidying: a module named after a face that has been
 * deleted is a signpost pointing at a road that is gone, and the previous name was the reason
 * `ZERO_ADVANCE_EM` still held Onest's numbers for a whole revision after Onest stopped being
 * downloaded. Whatever the sans is, this is where its zero lives.
 *
 * **It is one number per weight, and under this face they happen to agree.** Onest shipped as a
 * single variable `@font-face` spanning `font-weight: 400 700`, so the browser instanced it at
 * whatever weight an element asked for and the zero narrowed as the instance got heavier —
 * 0.665em at 400 against 0.6618em at 600. Stating the 400 value as "the whole definition of a
 * `ch`" is what made the sixth round of these figures wrong, because the headings and ledes
 * that carried a shared `ch` are all `font-semibold`. IBM Plex Sans ships four static cuts and
 * every one of them advances its zero **600 units on a 1000-unit em**, so a `ch` no longer
 * follows weight. The table stays keyed by weight anyway: the four entries are four
 * measurements that agree, not one measurement generalised, and the next face to arrive here
 * may well disagree with itself again.
 *
 * HOW TO READ THESE OFF THE FONT AGAIN, since nothing here can:
 *
 *     from fontTools.ttLib import TTFont
 *     f = TTFont("frontend/src/assets/fonts/plex-sans-400.woff2")
 *     zero = f.getBestCmap()[ord("0")]                       # -> "zero", glyph id 55
 *     f["hmtx"][zero][0] / f["head"].unitsPerEm              # -> 600 / 1000
 *
 * and again for `plex-sans-500`, `-600` and `-700`. There is no `fvar`, no `HVAR` and no
 * interpolation to get wrong; there is also no shortcut, because "a static family has one
 * advance" is a claim about four files and not about one. All four were read — 600/1000 in
 * each — as were the three mono cuts, which are the same 600/1000 and are why one measure now
 * means one width whatever type is set in it. The four `-ext` subsets carry no digits at all,
 * which is correct: the extended range exists for identifiers that are not ASCII, and a `ch`
 * resolved against a subset with no zero would fall through to the next family in the stack.
 *
 * **What is asserted here is arithmetic, and the browser reading behind it is Onest's.** The
 * `drawn` column below is the rectangle Chromium lays out, and it was measured against
 * `onest.woff2` — served from a built bundle, with `document.fonts.check` waited on for both
 * weights, because `font-display: swap` otherwise answers with a fallback whose zero is
 * 0.6299em and every width comes out five per cent wrong. All nine of those readings came back
 * as `Math.floor(resolved * 64) / 64` exactly, so what survives the face change is the *rule* —
 * a layout unit is 1/64px and Chromium snaps down — and the rule is what is asserted. The nine
 * rectangles themselves have not been re-swept under Plex Sans, and `docs/known-defects.md`
 * carries that as an open item rather than this comment carrying nine numbers nobody measured.
 *
 * Keyed by weight and deliberately not interpolated. A weight with no entry throws rather than
 * falling back to 400, so an element that gains `font-light` or `font-black` stops the suite
 * until somebody has read that advance off the font instead of inheriting a number that was
 * never about it. The four here are the four cuts `styles.css` actually downloads; a fifth
 * weight is a fifth `@font-face` and a fifth measurement, in that order.
 */
export const ZERO_ADVANCE_EM: Record<number, number> = { 400: 0.6, 500: 0.6, 600: 0.6, 700: 0.6 };

/**
 * The advance for one weight, or a loud failure naming what to do about it.
 *
 * The throw is the point, and it is not made redundant by the four entries above agreeing.
 * Returning 400's number for an unmeasured weight is exactly how a heading set at 600 came to
 * be described at 400 for six passes under a face where the two differed by half a per cent —
 * small enough that nobody re-derives it, large enough to make every figure in a comment wrong.
 * Under a static family the same silence would be worse rather than better: an element that
 * gains `font-light` is asking for a cut this product does not download, so its `ch` resolves
 * against whatever the fallback stack hands over, and a number quietly returned here would
 * describe a rectangle no reader is looking at.
 */
export function zeroAdvanceEm(weight: number, context: string): number {
  const advance = ZERO_ADVANCE_EM[weight];
  if (advance === undefined) {
    throw new Error(
      `no measured zero advance at weight ${weight} (${context}) — read it off the hmtx of ` +
        `the shipped plex-sans-${weight}.woff2 and add it to ZERO_ADVANCE_EM in ` +
        `ui/font.test-metrics.ts, or stop setting a weight styles.css does not download`,
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
 * regular, 58ch at 16px regular and 13px semibold — and `Math.floor(resolved * 64) / 64` gave
 * every one of them exactly. `ui/font.test-metrics.test.ts` states that relation as a table so
 * the two figures beside each other in a comment are one figure and a rule.
 *
 * That sweep was run against Onest. What it established is the rule, which is a property of the
 * engine and not of the face; the nine rectangles it established the rule *on* are gone with the
 * face, and the nine below are the same rule applied to Plex Sans's advance rather than nine
 * numbers a browser handed over. Re-running the sweep is an open item in
 * `docs/known-defects.md`, and it is cheap: what it would catch is the rule turning out to be
 * about Onest's hinting rather than about the grid.
 *
 * A layout unit is Chromium's, not CSS's, so this is a fact about one engine. It is asserted
 * rather than assumed for exactly that reason: if the number ever moves, the table fails with
 * both readings in the message instead of a comment quietly going stale.
 *
 * **`count` is zero advances, not characters, and the zero is the wider.** Plex Sans's is
 * 0.600em at every cut this product downloads, and a character of body text on a full line
 * costs less than that — `FULL_LINE_CHARACTER` below is where that second number lives, once,
 * for each of the two corpora it has been measured over, and both of those rows are still
 * Onest's. So a `46ch` measure holds appreciably more than 46 characters. This is written here
 * because this function is
 * where every `ch` figure in the repository is now produced, and because the sentence has been
 * put the wrong way round in four files on this branch, three of them copies of one sentence.
 * `ui/markdown.tsx` argues the same point from the other end, over `62ch` that was read as 62
 * characters and holds 81.
 */
export function chMeasure(count: number, sizePx: number, classes: string) {
  const resolved = count * sizePx * zeroAdvanceFor(classes);
  return { resolved, drawn: Math.floor(resolved * 64) / 64 };
}

/**
 * What one character costs on a line that is actually full — the other half of a `ch`, and the
 * only copy of it.
 *
 * A `ch` is one zero. A reader counts characters. `chMeasure` above turns a `ch` count into a
 * width; this turns a width back into the count a reader would make, and the two together are
 * why "`46ch` holds 46 characters" is wrong by about a third everywhere it has been written on
 * this branch.
 *
 * **One method, two corpora, and the corpus is the whole of the difference.** The method is
 * `ui/prose.tsx`'s, stated there at length: serve the built bundle so the face is the shipped
 * `onest.woff2`; wait on `document.fonts.check` for both weights, because `font-display: swap`
 * otherwise answers with a fallback whose zero is 0.6299em; render the corpus at the measure
 * and size named below; measure each `<p>` with a
 * `Range` per character and cluster the boxes on their vertical centres, one cluster to a line;
 * count each line from its own first visible character up to the next line's, so the space a
 * soft wrap ate belongs to the line it ended; and average over the lines that are *not* the
 * last of their block, because a block's last line is short by construction and describes the
 * ragged edge rather than the sweep.
 *
 * The two rows come out 0.8% apart — 0.5095em against 0.5054em — and that is corpus and not
 * method or size. A judgement is the model arguing in long sentences with qualified names in
 * them; a policy note is one sentence of ordinary prose, and only 13 of the 514 carry a
 * backticked name at all. Neither is "the" advance of this face and neither is wrong. Quote the
 * row whose corpus is the text being argued about, and where the text is neither — a reviewer's
 * own typed question, which nothing in the store records — say which row was used.
 *
 * Both rows are stated as the division that produced them rather than as a decimal, so the two
 * measured figures behind each are visible and a reader can check the arithmetic without a
 * second run. Both divisions are already asserted elsewhere in the tree at the measure named:
 * 617.12px over 75.7 characters in `ui/prose.tsx`, and 398.00px over 60.58 in
 * `features/review/finding-detail.tsx`. `features/review/finding-detail.test.tsx` reads the
 * first of them from here rather than dividing it again, which is the point of the file.
 *
 * **What was re-run, and what was taken on the tree's word.** The policy-note row was swept
 * again from scratch and comes back at 60.58 over 1,531 full lines, to the digit. The
 * judgement row is `ui/prose.tsx`'s render-with-chips sweep and was not reproduced here — what
 * was reproduced is its sibling, the same corpus drawn as the recorded string rather than as
 * the render, which that file records at 3,237 line boxes and 76.24 characters and which comes
 * back at exactly 3,237 and 76.24. That is evidence the harness is the same harness, and it is
 * not a second measurement of 75.7. Anybody moving this row should re-run the render.
 */
export const FULL_LINE_CHARACTER: Record<string, { px: number; sizePx: number; em: number }> = {
  /** The 375 recorded judgements, rendered through `ModelProse` at `58ch` — chips and all. */
  judgements: { px: 617.12 / 75.7, sizePx: 16, em: 617.12 / 75.7 / 16 },
  /** The 514 recorded policy notes, rendered at the `46ch` the policy card caps them to. */
  policyNotes: { px: 398.0 / 60.58, sizePx: 13, em: 398.0 / 60.58 / 13 },
};
