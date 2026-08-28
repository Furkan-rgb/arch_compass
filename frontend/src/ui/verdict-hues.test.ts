import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { render } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";

import { VERDICT_ORDER, verdictOf } from "../lib/format";
import { VerdictBadge } from "./badge";
import { TONE_EDGE, TONE_TEXT } from "./meta";

/**
 * Red, amber and green mean one thing here, and it is not "nice box".
 *
 * `material`, `held` and `cleared` are a severity scale the workbench reads at a glance: act
 * on it, waiting on a person, settled. Every screen sits inside one shell, so a hue spent on
 * something else is not a local decision — a finished clone in `cleared` green, a pinned
 * setting in `held` amber and a delta count in both read as grades, and the attention queue's
 * rows lose the only signal they had. That shipped six times before anyone noticed, which is
 * what a rule living only in a comment costs.
 *
 * The distinction this draws is not "which file" but "where the hue came from". Painting a
 * tone that `lib/format` handed you is the whole point of having tones. Reaching for one of
 * the three because a box wanted colour is the bug. So a line naming a hue passes when it
 * also names the tone it is painting, and otherwise has to be a panel whose entire subject
 * is one of the three states.
 *
 * The fourth hue is deliberately not here. `--mark` is provenance and not a grade — a path,
 * a corpus id, the route back to a source — so "outside a verdict" is where it belongs and
 * this file would be the wrong guard for it. `ui/design-system.test.ts` holds that one, with
 * an allowlist of its own.
 */

/**
 * Everything that can put one of the three on screen, in every tier the palette now has.
 *
 * Two widenings, and the second is the one that was actually costing something.
 *
 * **The tier suffix is spelled out.** Each hue is declared twice — `--material` for a word at
 * 4.5:1, `--material-edge` for a graphic at 3:1 — plus a wash that fills a badge, so a
 * verdict arrives as `text-material`, `border-material-edge` or `bg-material-wash`. The v1
 * pattern matched all three by accident of `\b` landing on the hyphen; naming them says what
 * the set is, and the tier that does not exist is a separate claim, one test down.
 *
 * **The utility list was missing the directional borders**, and that is where a verdict is
 * most often painted: `border-l-held-edge` is the bar down the left of a docket row, the
 * thing a reader reads before any word on any row. `\bborder-(?:material|held|cleared)\b`
 * cannot match it, because the utility is `border-l-` and the boundary never lands. Three
 * files hand-write one today — `docket.tsx`, `decision-bar.tsx`, `specimen.tsx`, all
 * allowlisted — and the guard could not see any of them, so the rule was unenforced in the
 * one place a fourth file would most plausibly copy it from. `fill-` and `stroke-` are here
 * for the same reason at a smaller scale: a mark is an `<svg>`, and those are how you paint
 * one without naming a text colour.
 *
 * The graphic half is split out as `DRAWS` rather than written inline, because the third test
 * below needs it on its own: every utility in it draws a line or a shape and none of them can
 * draw a word, which is what makes the tier it must take decidable from the class alone.
 */
const DRAWS = "(?:border(?:-[trblxyse])?|divide|ring|outline|fill|stroke)";
const PAINTS = `(?:bg|text|decoration|accent|caret|shadow|from|via|to|${DRAWS})`;
const SIGNAL = "(?:material|held|cleared)";

const HUES = new RegExp(`\\b${PAINTS}-${SIGNAL}(?:-edge|-wash)?\\b`);

/**
 * A hue named in a tier the system does not have, which is a class that resolves to nothing.
 *
 * Two forms, one failure. `bg-material-soft` is the v1 wash under its old name — the tokens
 * were **renamed** rather than retuned, so every one of those call sites now emits a class
 * Tailwind generates no rule for. `border-material/30` is an alpha of the text tier, which is
 * the same mistake arriving by arithmetic: it composites to a real step in dark and to almost
 * nothing in light, so the element has an edge in one theme and a smudge in the other, and
 * `ui/badge.tsx` carries the paragraph arguing exactly that about the chip it used to be on.
 *
 * This is a different claim from the one above and it is checked over every file, allowlist
 * included, because the allowlist answers *may this file name a verdict's hue* and says
 * nothing about which spelling. `ui/badge.tsx` is the file most entitled to a wash and the
 * file where a dead wash would be least visible.
 *
 * **Nothing else in the repository can see it.** It is not a type error, it is not a build
 * error, and the page renders — with no fill at all, which reads as a design decision rather
 * than as a broken class. `tokens.test.ts` proves the declared tokens are readable; it cannot
 * know which names a component reached for. That is how `ui/button.tsx`'s destructive variant
 * and every `ErrorNotice` in the product spent the first half of this revision painting no
 * background, in the two files nothing else was looking at.
 */
const OFF_THE_TIER_LADDER = new RegExp(
  `\\b${PAINTS}-${SIGNAL}(?:-(?!edge\\b|wash\\b)[a-z]+|(?:-edge|-wash)?/\\d)`,
);

/** A graphic drawn in the word's tier: `border-l-held`, where `border-l-held-edge` was meant. */
const THE_WORD_TIER_ON_A_GRAPHIC = new RegExp(`\\b${DRAWS}-${SIGNAL}(?!-edge)\\b`);

/** Painting a tone that something else decided: `descriptor.tone === "held" && …`. */
const FROM_A_TONE = /\btone\b/;

/**
 * Panels whose subject is one of the three states, written out rather than looked up.
 *
 * Each is a fixed state rather than a value that varies, so there is no descriptor to read:
 * a clarification panel is only ever shown while the review is held.
 *
 * `features/review/surfaces.tsx` was on this list — an addressed candidate is one that has
 * gone away — and came off it, which is the direction entries are supposed to move. The Delta
 * surface used to tint a glyph `text-cleared` at the call site; it now says
 * `<Badge tone="cleared">` and lets `ui/badge.tsx` paint it, so it needs no exemption at all.
 * An entry that has stopped being load-bearing is worse than no entry, because it silently
 * licenses the next hue somebody adds to that file.
 */
const ALLOWED = new Map([
  ["lib/format.ts", "the one table that decides which value takes which tone"],
  ["ui/badge.tsx", "paints a tone; never chooses one"],
  ["ui/meta.tsx", "paints a tone; never chooses one"],
  ["ui/states.tsx", "ErrorNotice — a failed request is the red end of the scale"],
  ["ui/field.tsx", "a rejected field is the red end of the scale"],
  ["ui/button.tsx", "the destructive variant is the red end of the scale"],
  [
    "features/review/decision-bar.tsx",
    "a decision taken against a verdict that has since moved is waiting on a person again",
  ],
  ["features/review/docket.tsx", "the clarification card, shown only while the review is held"],
  ["features/landing/specimen.tsx", "a specimen bearing; those really are verdicts"],
]);

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
 * The tier rule needs it and the location rule above does not, which is worth saying rather
 * than leaving as an inconsistency: this codebase argues for a decision in prose sitting
 * directly above the code making it, so the paragraph explaining why `bg-held-soft` was
 * removed contains `bg-held-soft`. Four such paragraphs exist today and every one of them is
 * in a file the allowlist exempts — luck, not design, and the tier rule reads every file.
 *
 * The same two regexes as `withoutComments` in `ui/design-system.test.ts`, where the argument
 * for them lives. Copied rather than imported, because importing a module that calls
 * `describe` at its top level would enrol that file's suite in this one's run.
 */
function withoutComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (block) => block.replace(/[^\n]/g, " "))
    .replace(/(?<!:)\/\/[^\n]*/g, (line) => " ".repeat(line.length));
}

describe("the verdict palette", () => {
  it("is reached for only where a verdict is what is being shown", () => {
    const root = join(__dirname, "..");
    const offenders = sourceFiles(root)
      .filter((file) => !ALLOWED.has(file))
      .flatMap((file) =>
        readFileSync(join(root, file), "utf8")
          .split("\n")
          .map((line, index) => ({ file, line: index + 1, text: line.trim() }))
          .filter((entry) => HUES.test(entry.text) && !FROM_A_TONE.test(entry.text)),
      );

    expect(
      offenders.map((entry) => `${entry.file}:${entry.line} — ${entry.text}`),
      "use Notice for a standing note, or Badge with a tone from lib/format",
    ).toEqual([]);
  });

  it("spends a hue in one of the two tiers and the one wash it has", () => {
    const root = join(__dirname, "..");
    const offenders = sourceFiles(root).flatMap((file) => {
      const raw = readFileSync(join(root, file), "utf8").split("\n");
      return withoutComments(raw.join("\n"))
        .split("\n")
        .map((text, index) => ({ line: index + 1, text }))
        .filter((entry) => OFF_THE_TIER_LADDER.test(entry.text))
        // Reported from the raw line: a blanked one is not something to go and read.
        .map((entry) => `${file}:${entry.line} — ${raw[entry.line - 1].trim()}`);
    });

    expect(
      offenders,
      "a word takes `--material`, a graphic takes `--material-edge`, a badge's fill takes " +
        "`--material-wash`, and there is no fourth — `-soft` was deleted with the v1 washes " +
        "and an alpha of a signal is a value nothing measured",
    ).toEqual([]);
  });

  /**
   * And the tier a hue arrives in, where the class says which of the two jobs it is doing.
   *
   * `--material` is the word at 4.5:1 and `--material-edge` is the graphic at 3:1, and the
   * whole reason the edge tier is allowed to be that saturated is that no word is ever set in
   * it. Spend the word's token on a 3px bar and the bar is painted in the value that had to
   * darken to stay readable — the signal is not wrong, it is wasted, which is why nothing ever
   * caught it. `TONE_EDGE` shipped a whole revision as `border-l-material` / `border-l-held` /
   * `border-l-cleared`, on the most-read graphic in the product, and every gate stayed green.
   * So this one reads every file and takes no `tone` escape either: the line that shipped
   * wrong was a line in a tone table, in the file most entitled to name a hue.
   *
   * **This guard runs one way only, and the reason is worth stating.** A border, a divider, a
   * ring, an outline, a `fill` and a `stroke` cannot draw a word, so the tier they take is
   * decidable from the class. The reverse is not: `text-material-edge` is how `ui/badge.tsx`
   * paints the badge's *mark*, because an `<svg>` takes `currentColor` and there is no
   * `glyph-` utility to tell it apart from a sentence. So an `-edge` token in a text position
   * is a contrast failure this file cannot see, and `tests/browser/` is where it would be
   * caught, by reading a resolved colour off a real page.
   *
   * `bg-` is deliberately not on the list, and that is an open question rather than an
   * oversight. `StatusDot` fills `bg-material` / `bg-held` / `bg-cleared` for a 6px dot, which
   * L3 files under graphics — but the same map fills `bg-accent` for a running review, and
   * there is no `--accent-edge` to move that one to. Three of six moving is a map with mixed
   * tiers. It is a decision for whoever owns `ui/badge.tsx`, and it should be made rather than
   * inherited from this file's silence.
   */
  it("draws a graphic in the graphic tier", () => {
    const root = join(__dirname, "..");
    const offenders = sourceFiles(root).flatMap((file) => {
      const raw = readFileSync(join(root, file), "utf8").split("\n");
      return withoutComments(raw.join("\n"))
        .split("\n")
        .map((text, index) => ({ line: index + 1, text }))
        .filter((entry) => THE_WORD_TIER_ON_A_GRAPHIC.test(entry.text))
        .map((entry) => `${file}:${entry.line} — ${raw[entry.line - 1].trim()}`);
    });

    expect(
      offenders,
      "a rule, a ring or a bar is a graphic with 3:1 to clear — it takes `-edge`, and the " +
        "bare token is the one the word needed",
    ).toEqual([]);
  });

  it("has an allowlist that still describes real files", () => {
    // An entry that outlived its file would quietly exempt nothing, and the next one added
    // beside it would look just as load-bearing.
    const present = new Set(sourceFiles(join(__dirname, "..")));
    expect([...ALLOWED.keys()].filter((file) => !present.has(file))).toEqual([]);
  });
});

/**
 * And which of the three a verdict gets, which nothing was holding.
 *
 * The test above asks *where* the three hues may be named. It never asks what any of them is
 * paired with, and the difference is the whole of this defect: `TONE_EDGE.held` was retyped
 * as `border-l-material-edge` — repainting every held row in the docket in the accent red,
 * which is the product's central judgement stated wrongly in the register a column is read in
 * first — and every gate in the repository stayed green.
 *
 * Two tables have to agree for a row to be right, and either can be edited alone.
 * `lib/format`'s `VERDICTS` maps a wire verdict to a tone; `TONE_EDGE` and `TONE_TEXT` above
 * map that tone to a class. So the claim is made across both, as the composition the docket
 * actually performs.
 *
 * Written as `border-l-${verdict}-edge` rather than as a second copy of the table on purpose.
 * A test that listed the five classes and checked they all appeared would pass a *swap* of
 * two entries, where every class is still used and only the pairing is wrong; deriving the
 * expected class from the verdict's own name fails that, fails the mutation above, and fails
 * a `VERDICTS` entry pointed at the wrong tone. All three were run. Only the three verdict
 * tones are claimed here — `neutral` and `marked` are not verdicts, and nothing names them.
 *
 * The `-edge` is a constant on the end rather than a second thing derived, because it is not
 * a property of *which* verdict this is: it is the tier every left edge is drawn in, an edge
 * being a graphic with 3:1 to clear rather than a word with 4.5:1. A verdict's identity is
 * still the only variable in the string.
 *
 * What this cannot see is everything downstream of the class. jsdom applies no stylesheet, so
 * `border-l-held-edge` here is a string and not a colour, and this file cannot tell whether
 * the docket reaches for these tables at all. Both are on screen, and
 * `test_a_rail_states_the_verdict_of_its_own_row` in `tests/browser/test_workspace.py`
 * measures them in Chromium against a docket dealt three different verdicts.
 */
describe("a verdict's hue", () => {
  it("is the one named after that verdict", () => {
    expect(VERDICT_ORDER.map((verdict) => TONE_EDGE[verdictOf(verdict).tone])).toEqual(
      VERDICT_ORDER.map((verdict) => `border-l-${verdict}-edge`),
    );
    expect(VERDICT_ORDER.map((verdict) => TONE_TEXT[verdictOf(verdict).tone])).toEqual(
      VERDICT_ORDER.map((verdict) => `text-${verdict}`),
    );
  });
});

/**
 * And now the half of the palette that carries the readers the hue channel does not reach.
 *
 * `docs/design-system.md` calls this the load-bearing rule rather than a belt-and-braces one,
 * and the measurement is why: simulated with Viénot, Brettel & Mollon, the three verdicts
 * separate under deuteranopia by **ΔE 4.3–6.0 in the light theme**. That is not a tuning
 * failure, it is the shape of the constraint — four hues each clearing 4.5:1 on a near-white
 * ground are confined to a narrow band of lightness, and red and green converge there under
 * the commonest dichromacy. So for a reader with a red-green deficiency — the commonest
 * there is, and not rare — the hue is the *redundancy* and the glyph, the word and the edge
 * are the signal. Everything above this line is about which colour a verdict gets; this is
 * about the reader for whom that question has no answer.
 *
 * **Asserted over the rendered component, because the property is about the component.** No
 * arrangement of token values can state it: `ui/tokens.test.ts` could prove all three hues
 * distinct and a `Badge` that had quietly stopped drawing its mark would still be three words
 * in three greys. The mutation this is written against is the one the type system now also
 * catches — `glyph` was optional on `Badge`, so `<Badge tone="material">Material</Badge>`
 * compiled — and the two guards are worth having both: `tsc` fails a call site that omits the
 * mark, and this fails a component that accepts one and draws nothing.
 *
 * The three carriers are checked one at a time rather than only as a whole, because the whole
 * is too easy to satisfy. Strip the colour from three badges and compare the markup: two
 * verdicts wearing one icon still differ by their word, so the composite passes while a real
 * carrier has collapsed. Each `it` below fails on the loss of one carrier; the last fails on
 * the loss of a carrier nobody enumerated.
 */

/** The icon a verdict's badge actually drew, read off the document rather than off `VERDICTS`. */
function markOf(verdict: string): string {
  const { container } = render(createElement(VerdictBadge, { verdict }));
  const svg = container.querySelector("svg");
  expect(svg, `a "${verdict}" badge drew no mark at all — colour is now its only carrier`)
    .not.toBeNull();
  // Lucide stamps every icon with its own name — `class="lucide lucide-circle-check …"` — so
  // the identity is in the rendered tree and this never has to import the table that chose it.
  const found = /(?:^|\s)lucide-([a-z0-9-]+)(?:\s|$)/.exec(svg!.getAttribute("class") ?? "");
  expect(
    found,
    `cannot read an icon name off "${svg!.getAttribute("class")}" — if Lucide stopped ` +
      "stamping one, compare the drawn geometry instead",
  ).not.toBeNull();
  return found![1];
}

/** Any class that carries one of the four hues, in any tier and at any alpha. */
const A_HUE = /(?:^|-)(?:material|held|cleared|mark)(?:-edge|-wash)?(?:\/\d+)?$/;

/**
 * A verdict's badge as a monochrome screen draws it: every hue-bearing class removed.
 *
 * `title` goes with them. It holds the verdict's own description, which differs per verdict
 * and is drawn on nothing until a pointer rests on it — leaving it in would let a tooltip
 * stand in for a mark.
 *
 * `stripped` is the count of classes taken out, and it is returned rather than inferred from
 * the markup because the markup moves for other reasons: removing the `title` changes the
 * outer HTML on its own, so "the badge came back different" is not evidence that a hue was
 * ever found. The first version of the test below asserted exactly that and passed while the
 * pattern matched nothing at all.
 */
function inGreyscale(verdict: string): { stripped: number; drawn: string } {
  const { container } = render(createElement(VerdictBadge, { verdict }));
  const pill = container.firstElementChild as Element;
  let stripped = 0;
  for (const element of [pill, ...pill.querySelectorAll("*")]) {
    element.removeAttribute("title");
    // `getAttribute`/`setAttribute` rather than `className`, which is a read-only
    // `SVGAnimatedString` on the mark and would throw. Left alone where there is no class at
    // all, so the two paths of the tick do not each gain an empty one.
    const painted = element.getAttribute("class");
    if (painted === null) continue;
    const worn = painted.split(/\s+/).filter(Boolean);
    const kept = worn.filter((name) => !A_HUE.test(name));
    stripped += worn.length - kept.length;
    element.setAttribute("class", kept.join(" "));
  }
  return { stripped, drawn: pill.outerHTML };
}

describe("a verdict in greyscale", () => {
  /**
   * The mark, which is the carrier that reads before the word does and the only one that
   * survives at the size a docket row draws a verdict at.
   *
   * `ui/mark.test.tsx` asserts a neighbouring property — that no two of the sixteen *shapes*
   * resolve to one icon — and it cannot see this one, because it knows nothing about which
   * shape a verdict wears. Point `VERDICTS.held.glyph` at `"check"` and that file stays green
   * while held and cleared become the same badge with two words on it.
   */
  it("draws a mark, and no two verdicts draw the same one", () => {
    const drawn = VERDICT_ORDER.map((verdict) => ({ verdict, mark: markOf(verdict) }));
    const shared = drawn.filter(
      (one) => drawn.some((other) => other.verdict !== one.verdict && other.mark === one.mark),
    );
    expect(
      shared.map((entry) => `${entry.verdict} wears ${entry.mark}`),
      "two verdicts wearing one mark are one badge with two words on it once the hue goes",
    ).toEqual([]);
  });

  /**
   * The word, which is the carrier that needs no key at all — and the one a reader falls back
   * to when the badge is 15px and the mark is a ring with something in it.
   */
  it("says the verdict in words", () => {
    const said = VERDICT_ORDER.map((verdict) => ({
      verdict,
      label: (() => {
        const { container } = render(createElement(VerdictBadge, { verdict }));
        return (container.textContent ?? "").trim();
      })(),
    }));

    expect(
      said.filter((entry) => entry.label !== verdictOf(entry.verdict).label),
      "a badge prints the label `lib/format` decided, or the word is not the verdict's",
    ).toEqual([]);
    expect(new Set(said.map((entry) => entry.label)).size, "two verdicts read as one word").toBe(
      VERDICT_ORDER.length,
    );
  });

  /**
   * The edge, which is the third statement and the one greyscale takes the *meaning* out of
   * rather than the presence.
   *
   * Worth being exact about, because it is the carrier this rule is easiest to overclaim for.
   * Rendered without hue, `border-l-material-edge` and `border-l-held-edge` are the same grey
   * — the edge cannot say *which* verdict a row is. What it still says is that the row was
   * judged at all: a graphic tier edge clears 3:1 on every ground in both themes, against the
   * 1.69:1 in light that `--rule-strong` gives a row with nothing to report, and that
   * difference is a lightness one and survives. So the claim here is presence, and a step off
   * the edge a plain row gets; the two tests above are the ones that have to be distinct.
   *
   * It is read off `TONE_EDGE` rather than off a rendered row because the badge does not draw
   * it — the row does, from this table, in `docket.tsx`, `reviews-page.tsx`, `surfaces.tsx`
   * and `exhibit.tsx`. Rendering a row here would mean building one, and a row built by a test
   * is a row that agrees with the test.
   */
  it("has a left edge as well, and it is not the one a plain row gets", () => {
    const edges = VERDICT_ORDER.map((verdict) => ({
      verdict,
      edge: TONE_EDGE[verdictOf(verdict).tone],
    }));

    expect(
      edges.filter((entry) => !/^border-l-\S+$/.test(entry.edge)),
      "a verdict with no left edge has one statement fewer than the design system promises",
    ).toEqual([]);
    expect(
      edges.filter(
        (entry) => entry.edge === TONE_EDGE.neutral || entry.edge === TONE_EDGE.marked,
      ),
      "an edge a judged row shares with an unjudged one is a bar that says nothing",
    ).toEqual([]);
  });

  /**
   * And the property itself, stated over the markup: strip every hue and the three badges are
   * still three different things.
   *
   * This is the assertion that does not depend on somebody having enumerated the carriers. The
   * three above are the carriers we know about; a fourth device could arrive — a weight, a
   * shape, a second element — and this is what would keep it honest, because it compares what
   * was rendered rather than what was listed.
   *
   * The first assertion is what stops it passing for the wrong reason. If `A_HUE` matched
   * nothing — a class shape changed, a hue arrived through an arbitrary value — the comparison
   * below would be comparing three *coloured* badges, find them different, and report that
   * greyscale is safe. So each badge has to lose a class to the stripping first, counted
   * rather than read off the markup, which moves for other reasons.
   */
  it("is still three different things with every hue taken out", () => {
    const badges = VERDICT_ORDER.map((verdict) => ({ verdict, ...inGreyscale(verdict) }));

    expect(
      badges.filter((badge) => badge.stripped === 0).map((badge) => badge.verdict),
      "no hue was found to strip, so what follows would be comparing three coloured badges",
    ).toEqual([]);

    const collapsed = badges.flatMap((one, index) =>
      badges
        .slice(index + 1)
        .filter((other) => other.drawn === one.drawn)
        .map((other) => `${one.verdict} and ${other.verdict} render identically without hue`),
    );
    expect(
      collapsed,
      "a verdict carried by its colour alone is a verdict a red-green reader cannot read",
    ).toEqual([]);
  });
});
