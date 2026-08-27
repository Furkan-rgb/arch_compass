import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { VERDICT_ORDER, verdictOf } from "../lib/format";
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
 */
const HUES = /\b(?:bg|text|border|ring|from|to|via|decoration|accent)-(?:material|held|cleared)\b/;

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
 * as `border-l-material` — repainting every held row in the docket in the accent red, which
 * is the product's central judgement stated wrongly in the register a column is read in
 * first — and every gate in the repository stayed green.
 *
 * Two tables have to agree for a row to be right, and either can be edited alone.
 * `lib/format`'s `VERDICTS` maps a wire verdict to a tone; `TONE_EDGE` and `TONE_TEXT` above
 * map that tone to a class. So the claim is made across both, as the composition the docket
 * actually performs.
 *
 * Written as `border-l-${verdict}` rather than as a second copy of the table on purpose. A
 * test that listed the five classes and checked they all appeared would pass a *swap* of two
 * entries, where every class is still used and only the pairing is wrong; deriving the
 * expected class from the verdict's own name fails that, fails the mutation above, and fails
 * a `VERDICTS` entry pointed at the wrong tone. All three were run. Only the three verdict
 * tones are claimed here — `neutral` and `marked` are not verdicts, and nothing names them.
 *
 * What this cannot see is everything downstream of the class. jsdom applies no stylesheet, so
 * `border-l-held` here is a string and not a colour, and this file cannot tell whether the
 * docket reaches for these tables at all. Both are on screen, and
 * `test_a_rail_states_the_verdict_of_its_own_row` in `tests/browser/test_workspace.py`
 * measures them in Chromium against a docket dealt three different verdicts.
 */
describe("a verdict's hue", () => {
  it("is the one named after that verdict", () => {
    expect(VERDICT_ORDER.map((verdict) => TONE_EDGE[verdictOf(verdict).tone])).toEqual(
      VERDICT_ORDER.map((verdict) => `border-l-${verdict}`),
    );
    expect(VERDICT_ORDER.map((verdict) => TONE_TEXT[verdictOf(verdict).tone])).toEqual(
      VERDICT_ORDER.map((verdict) => `text-${verdict}`),
    );
  });
});
