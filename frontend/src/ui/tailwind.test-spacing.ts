/**
 * A distance a class list declares, in pixels — the one reader of Tailwind's spacing scale.
 *
 * Two test files argue about a gap: `ui/prose.test.tsx` about the breath between two blocks of
 * the model's argument, and `features/review/finding-detail.test.tsx` about the row gap in the
 * Judged band and the margin the rail carries under it. Both need the same conversion and
 * neither can measure one, because jsdom lays nothing out. A second copy of that conversion is
 * the drift `ui/font.test-metrics.ts` was extracted to stop, one subject over, so there is one
 * copy and it is here.
 *
 * **The scale is a fact about the stylesheet, not a convention.** Tailwind v4 resolves every
 * spacing utility as `calc(var(--spacing) * n)`, and `--spacing` is `0.25rem` — the framework
 * default, which `src/styles.css` does not override. Read it back off the built stylesheet
 * rather than off the documentation:
 *
 *     grep -o '\--spacing:[^;]*;' src/archcompass/presentation/web/static/assets/index-*.css
 *     grep -o '\.mt-2{[^}]*}'     src/archcompass/presentation/web/static/assets/index-*.css
 *
 * which give `--spacing:.25rem` and `.mt-2{margin-top:calc(var(--spacing) * 2)}`. So `mt-2` is
 * 8px, `mt-1.5` is 6px and `gap-y-3.5` is 14px, and the day somebody sets a project `--spacing`
 * every figure both of those files assert moves together and this constant is where it moves.
 */
export const SPACING_STEP_PX = 4;

/**
 * The pixels a class list gives `property`, or `null` where it declares none.
 *
 * `null` and not `0`, because "no gap here" and "a gap of nothing" are the two different
 * things a test about a gap has to be able to tell apart: the first block of a paragraph
 * declares no top margin and must not, while `mt-0` on the second would be somebody switching
 * the rhythm off. A caller that means "absent counts as zero" says so at the call site.
 *
 * Arbitrary values are read as well as scale steps, because a distance argued for in the
 * source can legitimately be written either way — and a bound stated in pixels should not
 * start passing vacuously the day a value moves out of the scale. Anything else returns
 * `null`, so a distance that moved to a token or a named utility fails the assertion with the
 * class list in the message instead of passing on a regex that stopped matching.
 *
 * `property` is matched with its own boundary on the left so `mt` cannot read `lg:mt-0`: a
 * responsive variant is a different declaration at a different width, and a test that wants
 * one asks for `lg:mt`.
 */
export function spacingPx(classes: string, property: string): number | null {
  const escaped = property.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const arbitrary = new RegExp(
    `(?:^|\\s)${escaped}-\\[([\\d.]+)(px|rem)\\](?:\\s|$)`,
  ).exec(classes);
  if (arbitrary) return Number(arbitrary[1]) * (arbitrary[2] === "rem" ? 16 : 1);
  const step = new RegExp(`(?:^|\\s)${escaped}-([\\d.]+)(?:\\s|$)`).exec(classes);
  if (step) return Number(step[1]) * SPACING_STEP_PX;
  return null;
}
