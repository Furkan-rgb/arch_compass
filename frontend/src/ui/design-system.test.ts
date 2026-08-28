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

/**
 * The file with its comments blanked out, and its line numbering intact.
 *
 * Every rule below is a rule about what the *code* does, and this codebase argues for its
 * decisions in prose sitting directly above the code that makes them — so the comment
 * explaining why a class was removed contains that class, and a guard reading raw lines
 * reports the explanation as the offence. The alpha rule found fifteen of those and not one
 * real violation; it would have been unusable without this.
 *
 * Blanked rather than dropped, so a match still reports the line number a reader can open.
 *
 * Two regexes rather than a character scanner, and that is the second attempt. A scanner has
 * to track string state to know that `//` inside `"https://…"` is not a comment — and then it
 * has to understand JSX, because an apostrophe in `<p>the reviewer's answer</p>` is not a
 * string delimiter, and treating it as one leaves the scanner quoted for the rest of the
 * file. The lookbehind buys the URL case for one character and nothing else has to be
 * understood at all.
 */
function withoutComments(source: string): string {
  return (
    source
      // Block comments, JSX ones included — `{/* … */}` is a `/* … */` with a brace on it.
      // Newlines are kept so a match still reports a line number a reader can open.
      .replace(/\/\*[\s\S]*?\*\//g, (block) => block.replace(/[^\n]/g, " "))
      // Line comments. The negative lookbehind is for `https://…` inside a class list or a
      // doc link: a colon before the slashes means a URL, not the start of a comment.
      .replace(/(?<!:)\/\/[^\n]*/g, (line) => " ".repeat(line.length))
  );
}

function offenders(pattern: RegExp, allowed: ReadonlySet<string> = new Set()): string[] {
  return sourceFiles(ROOT)
    .filter((file) => !allowed.has(file))
    .flatMap((file) => {
      const raw = readFileSync(join(ROOT, file), "utf8").split("\n");
      return withoutComments(readFileSync(join(ROOT, file), "utf8"))
        .split("\n")
        .map((text, index) => ({ file, line: index + 1, text: text.trim() }))
        .filter((entry) => pattern.test(entry.text))
        // Reported from the raw line, because a blanked one is not something to go and read.
        .map((entry) => `${entry.file}:${entry.line} — ${raw[entry.line - 1].trim()}`);
    });
}

/**
 * Each `className=` value in a file, with the line it starts on.
 *
 * Whole expressions rather than lines, because a class list here is routinely a `cn(...)` call
 * spanning four of them and the rule below is about what **one element** declares — a size in
 * the second string of a call answers for a measure in the first. A line scanner reports those
 * as offences and is therefore unusable, which is the same lesson `withoutComments` records one
 * function up.
 */
function classNameExpressions(source: string): { line: number; expression: string }[] {
  const found: { line: number; expression: string }[] = [];
  for (const match of source.matchAll(/className=/g)) {
    const start = match.index + match[0].length;
    let end = start;
    if (source[start] === '"') {
      end = source.indexOf('"', start + 1) + 1;
    } else if (source[start] === "{") {
      let depth = 0;
      for (end = start; end < source.length; end += 1) {
        if (source[end] === "{" || source[end] === "(") depth += 1;
        else if (source[end] === "}" || source[end] === ")") depth -= 1;
        if (depth === 0) break;
      }
      end += 1;
    } else {
      continue;
    }
    found.push({
      line: source.slice(0, match.index).split("\n").length,
      expression: source.slice(start, end),
    });
  }
  return found;
}

describe("the design system", () => {
  /**
   * There is an accent again, and this is the budget on it.
   *
   * The first system had an indigo accent and the same written rule, unenforced, and the
   * indigo reached 29 of 40 components — every one of them a local decision that looked
   * reasonable. So the accent is back on the terms it lost the first time: it means one thing,
   * look here, and it is spent in five places: the mark, the primary action, a link to the
   * source a claim came from, a material verdict, and a review that is running. Four files may
   * say `-accent` and they are named below; the material verdict is painted from a tone in
   * `lib/format` and guarded by `verdict-hues.test.ts` rather than here.
   *
   * The fifth job is the newest and the one to argue with first. `StatusDot`'s `running` dot
   * is the accent spent on work being in flight — not on a grade, which is why it is not a
   * sixth `Tone`. The alternative was to type `tone="material"` at the call site: no `-accent`
   * string, no entry here, and no test anywhere would have failed, because the red would have
   * been painted by `bg-material` inside a file `verdict-hues.test.ts` already allows. That is
   * the budget being widened invisibly, which is the failure both of these files exist to
   * stop. Widening it in the open, in one line a reader can delete, is the honest version.
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
      // `StatusDot`'s `running` fill, and nothing else in the file. This is a file-level
      // allowlist for a one-line licence, so it is the entry most likely to be leant on by
      // the next accent somebody wants here: a badge, a tag, a wash behind a count. None of
      // those is "look here" — they are the shapes the first accent grew through.
      "ui/badge.tsx",
    ]);
    expect(
      offenders(/\b(?:bg|text|border|ring|from|to|via|decoration|fill|stroke)-accent(?:-[a-z-]+)?\b/, allowed),
      "the accent is the mark, the primary action, a link to the source, a running review, and a material verdict",
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
   * The reading size is the model's, and there is one block in the product set at it.
   *
   * This guard is written because two files already claimed it existed. `ui/prose.tsx` and
   * `features/review/finding-detail.tsx` both told the next reader that "`design-system.test.ts`
   * fails the build on a second block set at the reading size anywhere in the tree", and
   * nothing in this file had ever read a type size. A convergence defended by a comment naming
   * an absent test is worse than one defended by nothing, because the comment stops the next
   * person from checking. That failure is the same shape as the drift the rule is about, one
   * level up, so the honest repair is the test rather than a smaller claim.
   *
   * What it protects: with the serif gone, the whole of what tells a reader the model is
   * speaking is placement, the attribution line, and 16px used for nothing else. The model's
   * argument on a finding, the review's synopsis and a conversation answer had reached `58ch`,
   * `46ch` and `62ch` — three treatments of one voice — and they now go through `ModelProse`,
   * which is the only place in the tree that may set the size.
   *
   * `text-base` is 16px as well, and it is not the same thing: every one of the seven in the
   * tree is a *title*, and what makes it one is the display face or the bold weight written
   * beside it. So a reading-size class on a line that also names a weight is a heading and is
   * let through — which is the one distinction this pattern cannot make on its own, and the
   * one place a body paragraph could still slip past. It would have to be a bold one.
   */
  it("sets the reading size in one place, so the model has one voice", () => {
    const allowed = new Set([
      "ui/prose.tsx", // `ModelProse`: the model's paragraph, wherever it is drawn
      // The wordmark's tile, which is a drawn glyph sized in `em` rather than a sentence —
      // there is no text in it for a measure or a leading to apply to.
      "ui/brand.tsx",
    ]);
    expect(
      offenders(/\btext-\[(?:16px|1rem)\]|\btext-base\b/, allowed).filter(
        (line) => !/\bfont-(?:display|semibold|bold)\b/.test(line),
      ),
      "the reading size is ModelProse's — a second block at 16px is a second model voice",
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
      // `CandidateRef`: the third job this rule already names, which until now had nothing
      // spending it. A model's answer cites a finding by identifier inside its own sentence,
      // and the mark is what makes that identifier the way to the row rather than a footnote
      // number. It lives in `ui/prose.tsx` because that is the file which parses the citation;
      // one link written twice is the drift this allowlist exists to stop.
      "ui/prose.tsx",
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
    // Things that genuinely leave the page. The palette is the third: it is summoned over
    // whatever you were reading, from any route, and has to read as being in front of it
    // rather than as a block that appeared in the flow. The shortcut sheet is the palette's
    // twin — same gesture, same overlay, same "in front of what you were doing" — and an
    // entry is added here rather than the sheet borrowing a rim, because a rim would say it
    // is a panel in the flow and it is not.
    const allowed = new Set([
      "ui/drawer.tsx",
      "ui/command-palette.tsx",
      "ui/shortcuts.tsx",
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

  /**
   * The block label is a recipe, and a recipe that is retyped is a recipe that drifts.
   *
   * `text-[10px] font-bold uppercase tracking-…` is the top row of the type scale — the voice
   * that names a block, an attribution or a group. `ui/panel.tsx` exports it as `Label`, and
   * it was still hand-rolled twenty-one times across fourteen files, at **five different
   * tracking values**: `0.08em`, `0.1em`, `0.11em`, `0.13em` and `0.14em`. The documented
   * value is `0.13em`. Nobody chose the other four; each is one paste away from a neighbour,
   * and at this size letterspacing is most of what the label looks like.
   *
   * `.todo` rather than green, because turning it on today fails on files this change does
   * not own. What is left, by file:
   *
   *   features/atlas/detail.tsx (6), features/atlas/controls.tsx (5),
   *   features/reviews/reviews-page.tsx (3), features/review/finding-detail.tsx (3),
   *   features/review/revision-rail.tsx (2), features/review/docket.tsx (2),
   *   features/landing/specimen.tsx (2), and one each in
   *   features/settings/settings-page.tsx, features/review/trajectory.tsx,
   *   features/review/review-page.tsx, features/review/decision-bar.tsx,
   *   features/review/context-rail.tsx, features/review/clarification.tsx,
   *   features/review/atlas-surface.tsx, features/landing/exhibit.tsx,
   *   features/atlas/explorer.tsx, components/ui/select.tsx and ui/brand.tsx.
   *
   * Two of those are not simply `Label` in disguise and want a decision rather than a
   * replacement: `components/ui/select.tsx` sets its group label in **mono**, and
   * `ui/brand.tsx` sets the wordmark's subtitle at `font-semibold` so it does not compete
   * with the wordmark above it. Either `Label` grows to cover them or they stay exceptions
   * with a comment saying why — but not silently, which is what they are now.
   */
  it.todo("says a block label once, in ui/panel.tsx", () => {
    expect(
      offenders(/text-\[10px\][^"'`]*uppercase|uppercase[^"'`]*text-\[10px\]/, new Set(["ui/panel.tsx"])),
      "use <Label> from ui/panel.tsx — the recipe is one place, at tracking 0.13em",
    ).toEqual([]);
  });

  /**
   * A tone is a ground on the ramp, never an alpha of one.
   *
   * This is the rule the whole system nearly lost to, and it lost to it silently. Five washes
   * were written as `bg-sunken/60`, `bg-sunken/40`, `bg-sunken/70`, `bg-sunken/50` and
   * `bg-surface/40`, and every one of them looked like a small, local, obviously-fine choice.
   * They are not, because an alpha does not composite the same distance on two grounds:
   * sixty per cent of `#ebebeb` over a `#f5f5f5` canvas lands six values away, and sixty per
   * cent of `#1f1f1f` over `#000000` lands nineteen. So each one was a real step in dark and
   * very nearly nothing in light — a tone system that worked in one theme. The clarification
   * card, the one block in the product that stops every candidate below it, was among them:
   * unmissable in dark, almost invisible in light.
   *
   * The ink ramp had the same fault for the same reason. `text-ink-3/50` composited to
   * `#afafaf` on a white panel, 2.0:1 — below the 4.5:1 that `tokens.test.ts` measures the
   * ramp itself against, and reached by a route that file cannot see. That is what makes this
   * a separate guard rather than a note in the other one: `tokens.test.ts` proves the declared
   * values are readable, and an alpha at a call site is how a component gets an undeclared
   * value that was never measured.
   *
   * The rule, then: if a value you want is not on the ramp, name it in `styles.css` where the
   * next reader and the contrast test can both find it. Do not mix it here.
   *
   * `--overlay`, `--chrome`, `--accent-soft`, `--held-soft`, `--cleared-soft` and the two rule
   * tokens are all *declared* with an alpha, which is a different thing and is fine — they are
   * named values with one definition, and a scrim over unknown content has to be translucent
   * to do its job at all. What is forbidden is minting a new one at a call site.
   */
  it("never mixes a tone out of an alpha of a ramp token", () => {
    expect(
      offenders(/\b(?:bg|text|border|from|to|via|fill|stroke)-(?:canvas|sunken|surface|surface-2|control|control-2|ink|ink-2|ink-3|band)\/\d/),
      "name the value in styles.css — an alpha composites to a different step in each theme",
    ).toEqual([]);
  });
  /**
   * A `ch` is resolved against the size the element's own text is set at, or it is resolved
   * against something nobody reading the line can see.
   *
   * `ch` is the advance of the digit zero in the element's **own** used font. Written on a block
   * that declares its size, it is a promise that the width follows the type, and that is what
   * `ui/prose.tsx` sets the model's argument in and what `Footnote` caps its rationale with.
   * Written on a block that declares no size, it silently resolves against an ancestor — in this
   * tree, the root's 16px — and the number in the class list is then a fact about the document
   * rather than about the text under it.
   *
   * Four had gone that way, and each was wrong by a different amount:
   *
   * - `<ul className="grid max-w-[46ch] gap-2">` in the Policies fold, 489.44px around a note
   *   set at 14px whose own 46ch is 428.26px;
   * - `<div className="grid max-w-[64ch] gap-2">` around the Ask composer, 680.96px around a
   *   `Textarea` set at `text-sm` whose own 64ch is 595.84px;
   * - two column wrappers on the landing page, `58ch` and `62ch`, each holding a stack of three
   *   or four sizes that a unit following one size cannot describe at all.
   *
   * This is the same fault `ui/markdown.tsx` carries a doc comment about, where one `46ch` on
   * seven renderers meant five widths — and it is the strictly worse half of it, because there
   * at least each width could be read off the class list that stated it.
   *
   * The rule is deliberately local to one element and does not chase the inherited size. A size
   * that arrives from an ancestor may well be the right one; what it can never be is checkable
   * by the person reading the line, and a measure nobody can check is how all five of these
   * lasted. The repair is either to state the size or to state the width in `rem`.
   */
  it("resolves every font-relative measure against a size the same element declares", () => {
    const named = /(?:^|[\s"'`])text-(?:xs|sm|base|lg|xl|2xl|3xl|4xl|5xl|6xl|7xl|8xl|9xl)(?=[\s"'`,]|$)/;
    const arbitrary = /(?:^|[\s"'`])text-\[(?:[\d.]+px|clamp\()[^\]]*\](?=[\s"'`,]|$)/;
    const fontRelative = /(?:max-|min-)?w-\[[\d.]+(?:ch|em)\]/;

    const unsized = sourceFiles(ROOT).flatMap((file) =>
      classNameExpressions(readFileSync(join(ROOT, file), "utf8"))
        .filter(({ expression }) => fontRelative.test(expression))
        .filter(({ expression }) => !named.test(expression) && !arbitrary.test(expression))
        .map(({ line, expression }) => `${file}:${line} — ${expression.split(/\s+/).join(" ")}`),
    );

    expect(
      unsized,
      "a `ch` or `em` width is declared on an element that sets no font size, so it resolves " +
        "against an ancestor and nothing in that class list says what it draws",
    ).toEqual([]);
  });
});
