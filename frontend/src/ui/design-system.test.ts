import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * The rules in `docs/design-system.md` that a comment cannot hold on its own.
 *
 * The first system had exactly these rules written down and none of them enforced, and the
 * indigo accent ended up in 29 of 40 components — every one of them a local decision that
 * looked reasonable. `verdict-hues.test.ts` is the sibling of this file and guards the
 * other half: that a verdict's hue is only spent on a verdict.
 */
const ROOT = join(__dirname, "..");

function sourceFiles(directory: string, prefix = ""): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.isDirectory()) return sourceFiles(join(directory, entry.name), relative);
    if (!/\.tsx?$/.test(entry.name) || entry.name.includes(".test.")) return [];
    return [relative];
  });
}

function offenders(pattern: RegExp, allowed: ReadonlySet<string> = new Set()): string[] {
  return sourceFiles(ROOT)
    .filter((file) => !allowed.has(file))
    .flatMap((file) =>
      readFileSync(join(ROOT, file), "utf8")
        .split("\n")
        .map((text, index) => ({ file, line: index + 1, text: text.trim() }))
        .filter((entry) => pattern.test(entry.text))
        .map((entry) => `${entry.file}:${entry.line} — ${entry.text}`),
    );
}

describe("the design system", () => {
  /**
   * There is an accent again, and this is the budget on it.
   *
   * The first system had an indigo accent and the same written rule, unenforced, and the
   * indigo reached 29 of 40 components — every one of them a local decision that looked
   * reasonable. So the accent is back on the terms it lost the first time: it means one thing,
   * look here, and it is spent in four places. Three of them are components and they are named
   * below. The fourth is a material verdict, which is painted from a tone in `lib/format` and
   * guarded by `verdict-hues.test.ts` rather than here.
   *
   * A focus ring is deliberately not on this list. It answers "where is the keyboard", which
   * is a question about the reader rather than about the content, and a red ring makes every
   * tab press read as a validation failure.
   */
  it("spends the accent in the places it was given, and nowhere else", () => {
    const allowed = new Set([
      "ui/brand.tsx", //  the mark: the identity
      "ui/button.tsx", // the primary action, and the destructive one at a wash
      "ui/tabs.tsx", //   the selected tab's underline — an indicator, never a slab
    ]);
    expect(
      offenders(/\b(?:bg|text|border|ring|from|to|via|decoration|fill|stroke)-accent(?:-[a-z-]+)?\b/, allowed),
      "the accent is the mark, the primary action, a link to the source, and a material verdict",
    ).toEqual([]);
  });

  /**
   * There is no serif to reach for either.
   *
   * The thesis has not changed — a reader should be able to tell who is speaking without
   * reading a word — but the serif is no longer what says it. Three faces read as authored;
   * one family at 400/500/600 reads as engineered, which is what this product is. So the
   * model's voice is carried by placement, by the attribution line naming who produced the
   * sentence, and by that sentence being the only reading-size text in the article.
   *
   * `--font-read` is deleted rather than aliased, for the same reason the accent tokens were:
   * an alias would let `font-read` keep compiling to something, and the class would drift back
   * one reasonable-looking commit at a time while quietly meaning nothing.
   */
  it("has no second face to reach for", () => {
    expect(
      offenders(/\bfont-(?:read|serif)\b/),
      "the model's voice is placement, attribution and the reading size — not a typeface",
    ).toEqual([]);
  });

  /**
   * `--mark` is the budget of one: the single chroma that is not a verdict.
   *
   * It exists so a reader can see the way back to the source a claim came from, which the
   * charter asks for on every surface. The moment it paints a button it is an accent again,
   * and the argument for having it disappears.
   */
  it("spends the one non-verdict chroma on getting to the source", () => {
    const allowed = new Set([
      "ui/meta.tsx",
      "ui/code.tsx",
      "ui/markdown.tsx",
      "features/review/finding-detail.tsx",
      "features/start/start-page.tsx",
    ]);
    expect(
      offenders(/\b(?:bg|text|border|ring|decoration)-mark\b/, allowed),
      "--mark navigates to a file, a policy or a cited finding, and does nothing else",
    ).toEqual([]);
  });

  /**
   * Not a hue rule, but the same shape of bug: a rule that only holds if nobody writes the
   * one line that quietly breaks it.
   *
   * `line-clamp-2` clamps by setting `display: -webkit-box`. Put `block` on the same element
   * and there are two display declarations on it, in two different tailwind-merge groups —
   * so `cn` keeps both and the stylesheet's own order decides. `block` is written later, so
   * `block` wins, the clamp silently does nothing, and the class list still says
   * `line-clamp-2`. Four elements carried that for a while; the delta's summaries ran to six
   * lines on a phone while claiming to be capped at two.
   */
  it("lets a line clamp be the thing that sets the display", () => {
    expect(
      offenders(/\bline-clamp-\d+\b[^"'`]*\b(?:block|flex|inline-flex|inline-block|grid)\b|\b(?:block|flex|inline-flex|inline-block|grid)\b[^"'`]*\bline-clamp-\d+\b/),
      "line-clamp sets display itself; another display utility beside it wins and cancels the clamp",
    ).toEqual([]);
  });

  /**
   * A rim is not a shadow, and this is the distinction the whole elevation system rests on.
   *
   * `shadow-rim` is one inset hairline of light along a surface's top edge: no blur, no
   * offset, nothing leaves the page. It exists because the ground is now the void, and on
   * black a hairline border loses the top of a panel — the border and the ground meet at
   * almost the same value. So a rim is allowed on any surface, and `ui/panel.tsx` puts one
   * on every raised panel without a call site having to ask.
   *
   * A *lift* — `shadow-float`, `shadow-hero` — is still only for the drawer and the landing
   * hero, which are the two things on screen that genuinely left the page. The old rule was
   * "structure is separated by a rule, not lifted off the page", and that half has not
   * changed; what changed is that a rule alone is no longer enough to draw an edge.
   */
  /**
   * A mark is drawn, never typed.
   *
   * `▲ ◆ ● ○ ◐` were the one part of the interface neither Onest nor IBM Plex Mono
   * contains, so every one of them fell through to whatever the operating system had —
   * arriving at three different optical sizes on three different baselines, beside a word set
   * in 11px uppercase. Lucide draws them now, and the failure mode this catches is the cheap
   * one: somebody typing the character back into a string because it is one keystroke and
   * looks right in the editor.
   *
   * Three blocks, not one. This covered Geometric Shapes alone, and underneath it the delta
   * surface quietly kept `✓` for "addressed" and `→` between two verdicts — the identical
   * defect, one Unicode block over, for as long as the guard had existed. Now:
   *
   * - `←`-`⇿` arrows. `ui/icons.tsx` has `ArrowRight`, `ArrowLeft`, `ArrowUp`, `DriftedIcon`.
   * - `✓`-`✘` ticks and crosses. These always belong to a verdict or a delta, so they come
   *   from `ui/mark.tsx` and are chosen from its vocabulary rather than typed at a call site.
   * - `■`-`◿` geometric shapes, the original offenders.
   *
   * What this still cannot catch is an *ASCII* character used as an icon: `~`, `+` and `=`
   * sat in `DELTA_STATES` beside that `✓` and no pattern can tell those from operators. They
   * broke the same rule, and that half is enforced by review.
   *
   * Comment lines are skipped rather than allowlisted, because a doc comment naming the marks
   * it draws is a description of the thing and not the thing. A file-level exemption would
   * have covered the code in that file too. The pattern below can hold the characters
   * literally because `sourceFiles` never scans a `.test.` file.
   */
  it("draws a mark rather than typing one", () => {
    expect(
      offenders(/^(?![*/])[^\n]*[←-⇿✓-✘■-◿]/),
      "use <Mark shape=…> or an icon from ui/icons.tsx — a pasted glyph falls back to the system font",
    ).toEqual([]);
  });

  it("lifts only the things that leave the page", () => {
    // Three things genuinely leave the page. The palette is the third: it is summoned over
    // whatever you were reading, from any route, and has to read as being in front of it
    // rather than as a block that appeared in the flow.
    const allowed = new Set([
      "ui/drawer.tsx",
      "ui/command-palette.tsx",
      "features/landing/specimen.tsx",
    ]);
    expect(
      offenders(/\bshadow-(?:float|hero|panel|sm|md|lg|xl|2xl|inner)\b/, allowed),
      "structure is separated by a rule and a rim, not lifted off the page",
    ).toEqual([]);
  });

  /**
   * The other half of the same rule: a rim has to come from the token, not from somebody
   * hand-rolling an inset shadow that happens to look like one. An arbitrary
   * `shadow-[inset_0_1px_0_…]` is how a second, slightly-different rim gets into the system,
   * and two rims a percent apart read as a rendering bug rather than as a decision.
   */
  it("has one rim, and it comes from the token", () => {
    expect(
      offenders(/\bshadow-\[[^\]]*inset/),
      "use shadow-rim — the rim is --rim, declared once per theme",
    ).toEqual([]);
  });
});
