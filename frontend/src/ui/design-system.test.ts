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

/** A file that may name something this file otherwise forbids, and the reason it may. */
type Allowlist = ReadonlyMap<string, string>;

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

function offenders(
  pattern: RegExp,
  allowed: { has(file: string): boolean } = new Set<string>(),
): string[] {
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

/**
 * Any utility naming one of the three severity signals, or the accent that is now one of them.
 *
 * Every position, because the v2 palette is reached through four of them — a word in
 * `text-*`, a pill in `bg-*`, a rail in `border-l-*`, a drawn mark in `fill-*` — and a
 * pattern that only knew about the first two was how `border-l-material` sat in the docket
 * for a release. `-edge`, `-wash`, `-fill`, `-strong` and `-on-fill` are all suffixes of the
 * same budget, so the tail is greedy rather than enumerated; an alpha at a call site is
 * caught by the `/\d` tail and then argued with by the alpha rule further down.
 */
const SIGNAL =
  /\b(?:bg|text|border|border-[lrtbxyse]|ring|from|to|via|decoration|fill|stroke|outline|shadow)-(?:accent|material|held|cleared)(?:-[a-z0-9]+)*(?:\/\d+)?\b/;

/**
 * Who may name a signal, and what each one paints with it.
 *
 * This is the successor to the "four files may say `-accent`" budget, and the reason it had to
 * be rewritten is that the thing it was counting stopped being one colour. `--accent` resolves
 * to `--material` now, and there are three more hues beside it — so a budget written over the
 * string `accent` could be walked around by typing `text-material`, which is the same red under
 * the name the tone tables use.
 *
 * The rule that replaces it is about entitlement rather than about a string: **a component is
 * entitled to a signal or it is handed one.** The six entitlements are `ui/badge.tsx` (the pill
 * and the status dot), `ui/meta.tsx` (the two tone tables every row and rail paints through),
 * `ui/button.tsx` (the primary action the decision bar takes, and the destructive one),
 * `ui/brand.tsx` (the identity), `ui/tabs.tsx` (the selected tab's underline) and `ui/field.tsx`
 * (a rejected field). Everything else asks for a `<Badge tone=…>` or reads `TONE_EDGE`, and
 * gets its colour without naming one.
 *
 * Four entries are not entitlements but fixed states, and they are the ones to argue with
 * first: three feature call sites and `ui/states.tsx` paint a state that never varies — a
 * clarification card is only ever shown while a review is held, an `ErrorNotice` is only ever a
 * failure — so there is no descriptor to read and no tone to be handed. Each is on `verdict-hues.test.ts`'s allowlist for
 * the same reason and with the same wording, which is the duplication this file is choosing: the
 * sibling asks *did this hue come from a tone*, line by line, exempting any line that mentions
 * one; this one asks *may this file name a hue at all*, with no escape a call site can write. A
 * file has to satisfy both, and the second is what the sibling's `\btone\b` exemption cannot say.
 *
 * `--mark` is not in this set. It is the fourth signal and it has its own budget below, because
 * the question it answers — does this go somewhere — is not the question the other three answer.
 */
const SIGNAL_BUDGET: Allowlist = new Map([
  ["ui/badge.tsx", "the pill's three tiers, its glyph, and the status dot"],
  ["ui/meta.tsx", "TONE_TEXT and TONE_EDGE: the tables everything else paints through"],
  ["ui/button.tsx", "the primary action, and the destructive one at an edge"],
  ["ui/brand.tsx", "the mark: the identity"],
  ["ui/tabs.tsx", "the selected tab's underline — an indicator, never a slab"],
  ["ui/field.tsx", "a rejected field is the red end of the scale"],
  ["ui/states.tsx", "ErrorNotice — a failed request is the red end of the scale"],
  ["features/review/docket.tsx", "the clarification card, shown only while the review is held"],
  [
    "features/review/decision-bar.tsx",
    "a decision taken against a verdict that has since moved is waiting on a person again",
  ],
  ["features/landing/specimen.tsx", "a specimen bearing; those really are verdicts"],
]);

/** Every utility that can reach `--mark`, in the same shape and for the same reason. */
const MARK =
  /\b(?:bg|text|border|border-[lrtbxyse]|ring|from|to|via|decoration|fill|stroke|outline)-mark(?:-[a-z0-9]+)*(?:\/\d+)?\b/;

/**
 * `--mark` is the budget of one: the single chroma that is not a verdict.
 *
 * It exists so a reader can see the way back to the source a claim came from, which the
 * charter asks for on every surface. The moment it paints a button it is an accent again,
 * and the argument for having it disappears.
 *
 * `ui/code.tsx` and `features/start/start-page.tsx` were on this list and have come off it.
 * Neither names a mark utility — `code.tsx` carries a comment about one and `start-page.tsx`
 * carries a comment arguing *against* one for its links — and an entry that exempts nothing is
 * worse than no entry, because it silently licenses the next blue somebody adds to that file.
 * That is the sibling file's own rule about allowlists, applied here; the test at the bottom is
 * what would have caught these two.
 */
const MARK_BUDGET: Allowlist = new Map([
  ["ui/meta.tsx", "PathRef: the route to a file, and the one place that gesture is drawn"],
  ["ui/markdown.tsx", "an authored document linking out of itself"],
  ["features/review/finding-detail.tsx", "the first location, and the way into an editor"],
  // `CandidateRef`: the third job this rule already names, which until now had nothing
  // spending it. A model's answer cites a finding by identifier inside its own sentence,
  // and the mark is what makes that identifier the way to the row rather than a footnote
  // number. It lives in `ui/prose.tsx` because that is the file which parses the citation;
  // one link written twice is the drift this allowlist exists to stop.
  ["ui/prose.tsx", "CandidateRef: a cited finding, inside the model's own sentence"],
]);

/** A chromatic background: the four washes, and the bare tokens behind them. */
const CHROMATIC_FILL = /\bbg-(?:material|held|cleared|mark)(?:-wash)?(?:\/\d+)?\b/;

/** A word set in the graphic tier. */
const EDGE_TIER_ON_A_WORD = /\btext-(?:material|held|cleared|mark)-edge\b/;

/**
 * The text tier spent on something nobody reads a letterform in.
 *
 * `(?![a-z-])` is what separates the tiers: `border-l-material-edge` is the rule being obeyed
 * and `border-l-material` is the rule being broken, and they differ by a suffix. The
 * `decoration` arm carries a lookbehind so it only fires on a *resting* underline — see the
 * test.
 */
const TEXT_TIER_ON_A_GRAPHIC =
  /(?:\b(?:border|border-[lrtbxyse]|fill|stroke)|(?<![\w:-])decoration)-(?:material|held|cleared|mark)(?![a-z-])/;

/** Something that genuinely left the page. */
const LIFT = /\bshadow-(?:float|hero|panel|sm|md|lg|xl|2xl|inner)\b/;

/**
 * Things that genuinely leave the page. The palette is the third: it is summoned over
 * whatever you were reading, from any route, and has to read as being in front of it
 * rather than as a block that appeared in the flow. The shortcut sheet is the palette's
 * twin — same gesture, same overlay, same "in front of what you were doing" — and an
 * entry is added here rather than the sheet borrowing a rim, because a rim would say it
 * is a panel in the flow and it is not.
 */
const LIFTED: Allowlist = new Map([
  ["ui/drawer.tsx", "the drawer"],
  ["ui/command-palette.tsx", "the palette, summoned over whatever you were reading"],
  ["ui/shortcuts.tsx", "the shortcut sheet, the palette's twin"],
  ["features/landing/specimen.tsx", "the specimen card, the landing page's one lifted object"],
]);

/**
 * The block label's recipe, at the one size and the one tracking the scale gives it.
 *
 * Both orderings, because a class list is written by hand and `uppercase` lands on either side
 * of the size about as often. The tracking is not in the pattern: a copy that got the size
 * right and the tracking wrong is the *worst* case here, not an exempt one, and the test below
 * is what keeps the pattern honest about the size.
 */
const LABEL_RECIPE = /text-\[11px\][^"'`]*uppercase|uppercase[^"'`]*text-\[11px\]/;

describe("the design system", () => {
  it("reaches for a signal only from a component entitled to one", () => {
    expect(
      offenders(SIGNAL, SIGNAL_BUDGET),
      "ask for a tone — <Badge tone=…> or TONE_EDGE from ui/meta.tsx — rather than naming a hue",
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
   *
   * The face moved under this rule and the rule did not notice, which is the point of it being
   * about a count rather than about a name: Onest became IBM Plex Sans, the mono was already
   * IBM Plex Mono, and one sans plus one mono is the same architecture it was.
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

  it("spends the one non-verdict chroma on getting to the source", () => {
    expect(
      offenders(MARK, MARK_BUDGET),
      "--mark navigates to a file, a policy or a cited finding, and does nothing else",
    ).toEqual([]);
  });

  /**
   * Colour signals; neutrals ground. This is the law with the largest blast radius and the
   * one a component breaks by being reasonable.
   *
   * A wash is a badge fill, capped at roughly 120×24px, and nothing else in the product has a
   * chromatic background — not a panel, not a fold body, not a table head, not an empty state,
   * not a selected row. The moment a hue fills a region it has stopped signalling and started
   * decorating, and a reader who sees colour everywhere stops reading it as meaning anything.
   *
   * Three shipped v1 examples, and none of them looked wrong in the diff that added it: the
   * clarification card painted a ~1000×64px header in `bg-held-soft`, the specimen's "Hinges
   * on" callout ran the full width of the card in the same amber, and `ErrorNotice` — the
   * largest block in the product that could be red — sat on `bg-material-soft`. All three are
   * now a neutral ground with the signal on an edge, a glyph and a word, which is the
   * arrangement the redundancy law asks for anyway.
   *
   * The `-soft` tokens were deleted rather than retuned, and that is worth knowing here because
   * of *how* those three were found: not by a failing build. A class naming a token that no
   * longer exists compiles, ships, and paints nothing. This guard reads the class list, so it
   * fails on the name whether or not the token behind it resolves.
   *
   * `bg-accent-fill` is the one chromatic fill the system keeps outside a badge — the primary
   * action and the brand tile — and it is deliberately not caught here, because the argument for
   * it is that a primary action is allowed to be the loudest thing on a screen. What holds it to
   * those two files is the signal budget at the top of this file, not this rule.
   */
  it("keeps every chromatic fill inside a badge", () => {
    const allowed = new Map([["ui/badge.tsx", "the pill, and the four washes exist for it"]]);
    expect(
      offenders(CHROMATIC_FILL, allowed),
      "a wash is a badge fill — give the region a neutral ground and put the signal on an edge",
    ).toEqual([]);
  });

  /**
   * The two tiers, and the half of the rule that is a contrast failure rather than a waste.
   *
   * WCAG asks 4.5:1 of a word and 3:1 of a meaningful graphic, and the palette is built on that
   * split: the bare token is text and clears 4.5 on all four grounds and on its own wash; the
   * `-edge` token is saturated *because* it only ever has to clear 3. So a word set in
   * `--cleared-edge` is not a stylistic slip, it is a measured failure — `#009754` on `--sunken`
   * in light is 3.01:1, which is the graphic floor exactly and two thirds of the text one.
   *
   * `ui/badge.tsx` is exempt, and this is the one place the pattern cannot tell what it is
   * looking at. `GLYPH_TONES` sets `text-material-edge` on the badge's `Mark`, which is a drawn
   * icon inheriting `currentColor` — a graphic painted through a text utility, because that is
   * how a stroked SVG is coloured. It is the graphic tier applied correctly and it reads as this
   * rule being broken. The exemption is file-level and therefore also covers `TONES`, three
   * lines up, which paints the word; those three lines are the badge's whole colour surface and
   * they sit under a comment arguing the split, which is the best containment available.
   */
  it("never sets a word in the edge tier", () => {
    const allowed = new Map([["ui/badge.tsx", "GLYPH_TONES: an SVG takes its colour from text-*"]]);
    expect(
      offenders(EDGE_TIER_ON_A_WORD, allowed),
      "the -edge tier clears 3:1, not 4.5:1 — a word takes the bare token",
    ).toEqual([]);
  });

  /**
   * And the other half: the text tier on something nobody reads a letterform in.
   *
   * A 3px rail down a docket row, a 1px control border, a dot, a bar, an underline. Spending
   * `--material` on any of them wastes the signal — the tier the eye catches first when it scans
   * a column is the saturated one, and the deep red exists to survive being a *word* on a
   * near-white ground. `TONE_EDGE` was `border-l-material` for a release: correct hue, correct
   * component, and the rail that carries the product's central judgement drawn in the value
   * tuned for 14px prose.
   *
   * One state is deliberately let through, and it is a carve-out rather than an oversight. An
   * underline that rests at `-edge` and goes to the bare token under a pointer is the one
   * graphic in the system whose job is to become *more* readable when it is being reached for;
   * `PathRef` in `ui/meta.tsx` and the anchor in `ui/markdown.tsx` both draw it that way. So the
   * `decoration` arm fires only on a resting value — anything with a variant in front of it,
   * `hover:` included, is skipped. The cost is that `sm:decoration-mark` would slip; the
   * alternative was enumerating the variants, which is a longer list than the rule.
   */
  it("never spends the text tier on a graphic", () => {
    expect(
      offenders(TEXT_TIER_ON_A_GRAPHIC),
      "an edge, a rail, a dot or a rule takes the -edge token — the bare one is for a word",
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
   * A mark is drawn, never typed.
   *
   * `▲ ◆ ● ○ ◐` were the one part of the interface no shipped face carried, so every one of
   * them fell through to whatever the operating system had — arriving at three different
   * optical sizes on three different baselines, beside a word set in 11px uppercase. A latin
   * subset puts Geometric Shapes out of reach whichever sans is loaded, so the face change did
   * not touch this. Lucide draws them now, and the failure mode this catches is the cheap one:
   * somebody typing the character back into a string because it is one keystroke and looks
   * right in the editor.
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

  /**
   * A rim is not a shadow, and this is the distinction the whole elevation system rests on.
   *
   * `shadow-rim` is one inset hairline of light along a surface's top edge: no blur, no
   * offset, nothing leaves the page. It exists because the ground is now the void, and on
   * black a hairline border loses the top of a panel — the border and the ground meet at
   * almost the same value. So a rim is allowed on any surface, and `ui/panel.tsx` puts one
   * on every raised panel without a call site having to ask.
   *
   * A *lift* — `shadow-float`, `shadow-hero` — is still only for the drawer, the two summoned
   * sheets and the landing hero, which are the things on screen that genuinely left the page.
   * The old rule was "structure is separated by a rule, not lifted off the page", and that half
   * has not changed; what changed is that a rule alone is no longer enough to draw an edge.
   */
  it("lifts only the things that leave the page", () => {
    expect(
      offenders(LIFT, LIFTED),
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
   * `text-[11px] font-bold uppercase tracking-[0.08em]` is the top row of the type scale — the
   * voice that names a block, an attribution or a group. `ui/panel.tsx` exports it as `Label`.
   *
   * The scale moved under it: 10px at `0.13em` became 11px at `0.08em`, because 10px bold
   * uppercase is under the practical floor for the tier that carries every label in the product,
   * and the wide tracking was compensating for the size in the wrong direction. The sweep that
   * moved the hand-rolled copies onto the new values is done — `0.13em` appears nowhere in
   * `src/` any more — but it moved them rather than deleting them, so the recipe is still
   * retyped **thirty times across eleven files**:
   *
   *   features/atlas/controls.tsx (7), features/atlas/detail.tsx (7),
   *   features/landing/landing-page.tsx (5), features/landing/specimen.tsx (4), and one each in
   *   features/atlas/explorer.tsx, features/landing/exhibit.tsx, components/ui/select.tsx,
   *   ui/badge.tsx, ui/brand.tsx, ui/states.tsx and ui/toast.tsx.
   *
   * `.todo` rather than green, because turning it on today fails on files this change does not
   * own — and because twenty-three of the thirty are not `Label` in disguise at all: they are
   * `<Mono>` or `font-mono`, so replacing them would drop the face. That is a design question
   * (`docs/design-system.md` puts labels in the sans and mono is for the machine quoting
   * itself), and it wants deciding rather than replacing. `ui/badge.tsx`, `ui/states.tsx`,
   * `ui/brand.tsx` and `ui/toast.tsx` are the other kind of exception — components with their
   * own reason for a label-sized word, in a file that could export it — and `ui/brand.tsx` sets
   * the wordmark's subtitle at `font-semibold` so it does not compete with the wordmark above
   * it. Either `Label` grows to cover them or they stay exceptions with a comment saying why,
   * but not silently, which is what they are now.
   */
  it.todo("says a block label once, in ui/panel.tsx", () => {
    expect(
      offenders(LABEL_RECIPE, new Set(["ui/panel.tsx"])),
      "use <Label> from ui/panel.tsx — the recipe is one place, at 11px and tracking 0.08em",
    ).toEqual([]);
  });

  /**
   * The guard above is `.todo`, so nothing runs its pattern. This is what stops that pattern
   * from quietly ceasing to describe the thing it hunts.
   *
   * A size in a regex is a copy of a decision made in `ui/panel.tsx`, and the last time the
   * scale moved this file kept hunting `text-[10px]` — which after the sweep matched almost
   * nothing, so turning the guard on would have passed for the wrong reason. A `.todo` cannot
   * fail; a stale `.todo` is therefore invisible twice over. Asserting the pattern still matches
   * `Label`'s own class list is the cheapest way to tie the two together: move the recipe and
   * this fails, naming the line to change.
   */
  it("hunts for the recipe Label actually draws", () => {
    const label = readFileSync(join(ROOT, "ui/panel.tsx"), "utf8");
    const recipe = "text-[11px] font-bold uppercase tracking-[0.08em] text-ink-3";
    expect(label, "ui/panel.tsx no longer draws the documented label recipe").toContain(recipe);
    expect(
      LABEL_RECIPE.test(recipe),
      "the hand-rolled-label guard no longer matches the recipe Label itself draws",
    ).toBe(true);
  });

  /**
   * A tone is a ground on the ramp, never an alpha of one.
   *
   * This is the rule the whole system nearly lost to, and it lost to it silently. Five washes
   * were written as `bg-sunken/60`, `bg-sunken/40`, `bg-sunken/70`, `bg-sunken/50` and
   * `bg-surface/40`, and every one of them looked like a small, local, obviously-fine choice.
   * They are not, because an alpha does not composite the same distance on two grounds: sixty
   * per cent of `#e7e5e2` over an `#f1eeeb` canvas lands 0.016 in OKLCH lightness away — under
   * the 0.020 every step on the ramp clears — and the identical declaration in dark lands
   * 0.090. So each one was a real step in dark and very nearly nothing in light — a tone system
   * that worked in one theme. The clarification card, the one block in the product that stops
   * every candidate below it, was among them: unmissable in dark, almost invisible in light.
   *
   * The ink ramp had the same fault for the same reason. `text-ink-3/50` composites to
   * `#b2b1ae` on a white panel, 2.14:1 — below the 4.5:1 that `tokens.test.ts` measures the
   * ramp itself against, and reached by a route that file cannot see. That is what makes this
   * a separate guard rather than a note in the other one: `tokens.test.ts` proves the declared
   * values are readable, and an alpha at a call site is how a component gets an undeclared
   * value that was never measured.
   *
   * **The signals are on this list now, and they were the harder half.** `border-material/25`
   * on a badge, `border-material/30` on an error notice, `hover:bg-material/15` on the
   * destructive button and `decoration-mark/50` on a link were four undeclared reds and blues
   * mixed at four call sites, and the last of them composited to 2.47:1 in light — under even
   * the 3:1 a graphic is held to. The two tiers are what replaced them: an `-edge` token is
   * already the lighter, more saturated value an alpha was being used to fake, and it has been
   * measured on all four grounds in both themes.
   *
   * The rule, then: if a value you want is not on the ramp, name it in `styles.css` where the
   * next reader and the contrast test can both find it. Do not mix it here.
   *
   * `--overlay`, `--chrome`, `--rim` and the three rule tokens are all *declared* with an alpha,
   * which is a different thing and is fine — they are named values with one definition, and a
   * scrim over unknown content has to be translucent to do its job at all. What is forbidden is
   * minting a new one at a call site.
   */
  it("never mixes a tone out of an alpha of a ramp token", () => {
    expect(
      offenders(
        /\b(?:bg|text|border|border-[lrtbxyse]|from|to|via|fill|stroke|decoration|ring)-(?:canvas|sunken|surface|surface-2|control|control-2|ink|ink-2|ink-3|band-field|band|accent|material|held|cleared|mark)(?:-(?:edge|wash|fill|strong))?\/\d/,
      ),
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

  /**
   * Every allowlist above names a file that exists and still needs the exemption.
   *
   * An entry that has stopped being load-bearing is worse than no entry, because the next hue
   * somebody adds to that file inherits a licence nobody granted it — and because the entry
   * reads, to whoever is deciding, as evidence that this file is a place signals live. Two were
   * already dead when this test was written: `ui/code.tsx` and `features/start/start-page.tsx`
   * sat on the `--mark` budget, and both of them name the mark only in a comment explaining why
   * they do not paint it.
   *
   * The direction entries are supposed to move is off these lists. `features/review/surfaces.tsx`
   * came off the sibling file's by saying `<Badge tone="cleared">` and letting `ui/badge.tsx`
   * paint it, which is what every entry here should eventually be able to do — except the six
   * components that *are* the paint.
   */
  it("has allowlists that still name files needing them", () => {
    const present = new Set(sourceFiles(ROOT));
    const rules: [string, RegExp, Allowlist][] = [
      ["the signal budget", SIGNAL, SIGNAL_BUDGET],
      ["the --mark budget", MARK, MARK_BUDGET],
      ["the lift allowlist", LIFT, LIFTED],
    ];

    const dead = rules.flatMap(([rule, pattern, allowed]) =>
      [...allowed].flatMap(([file, why]) => {
        if (!present.has(file)) return [`${rule}: ${file} — no such file (${why})`];
        const source = withoutComments(readFileSync(join(ROOT, file), "utf8"));
        return pattern.test(source) ? [] : [`${rule}: ${file} — exempts nothing (${why})`];
      }),
    );

    expect(dead, "an allowlist entry that exempts nothing licenses the next one added beside it").toEqual(
      [],
    );
  });
});
