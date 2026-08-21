import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * The two rules the token layer exists to hold, checked as arithmetic rather than as taste.
 *
 * Both of these were broken once, in a way that looked fine in the file and wrong on screen:
 * a tint of `233 240 252` is blue nineteen points over red, which is invisible on glass at 5%
 * and unmistakable on anything opaque; and `material` sat at 40 degrees, which is orange, only
 * 43 degrees from `held` and reading as an accent competing with a warning rather than as an
 * alert. Neither is the kind of thing a reviewer catches by reading a diff of hex codes.
 */
const CSS = readFileSync(join(__dirname, "..", "styles.css"), "utf8");

/** Every custom property in the file, as (name, value) pairs, in source order. */
function declarations(): Array<{ name: string; value: string }> {
  return [...CSS.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)].map((match) => ({
    name: match[1],
    value: match[2].trim(),
  }));
}

/** sRGB channels of `#rrggbb`, or of `rgb(r g b / a)`, or null if the value is neither. */
function channels(value: string): [number, number, number] | null {
  const hex = /^#([0-9a-f]{6})\b/i.exec(value);
  if (hex) {
    const n = parseInt(hex[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  const rgb = /^rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)/i.exec(value);
  return rgb ? [Number(rgb[1]), Number(rgb[2]), Number(rgb[3])] : null;
}

/** OKLCH lightness, chroma and hue of an sRGB triple. */
function oklch([r, g, b]: [number, number, number]): { l: number; c: number; h: number } {
  const lin = (v: number) => {
    const s = v / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  const [R, G, B] = [lin(r), lin(g), lin(b)];
  const cube = (v: number) => Math.cbrt(v);
  const l = cube(0.4122214708 * R + 0.5363325363 * G + 0.0514459929 * B);
  const m = cube(0.2119034982 * R + 0.6806995451 * G + 0.1073969566 * B);
  const s = cube(0.0883024619 * R + 0.2817188376 * G + 0.6299787005 * B);
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  const A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const Bb = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  return { l: L, c: Math.hypot(A, Bb), h: ((Math.atan2(Bb, A) * 180) / Math.PI + 360) % 360 };
}

/**
 * The one family that carries meaning by hue. Everything outside the exemptions below is grey.
 *
 * This used to be the three verdicts. It is now the accent, and the verdicts are exempt from
 * nothing: `material` is declared as `var(--accent)` so it cannot drift into a second red, and
 * `held` and `cleared` are neutral values that this file's first test now polices like any
 * other grey.
 */
const isAccent = (name: string) => name.startsWith("--accent");

/**
 * The one family allowed chroma without being a verdict, and the reason it is bounded.
 *
 * A syntax palette is not decoration and it is not a fourth signal: it answers a question the
 * verdict scale never asks, which is whether a token is a name somebody chose or the
 * language's own furniture. Weight alone cannot answer it, because half of Python is a
 * keyword and a page of bold says nothing.
 *
 * The exemption is from the *neutrality* rule, not from the hue rule. `keeps code colour off
 * the verdict wheel` below is what stops it becoming the hole this list looks like: a code
 * token may have a temperature, but it may not have one a reader could mistake for a grade.
 */
const isCode = (name: string) => name.startsWith("--code-");

describe("the token layer", () => {
  /**
   * A neutral with unequal channels is a second temperature, and a second temperature costs
   * the verdicts distance from the ground they sit on. The previous system's paper was the
   * same warmth as the `held` amber for exactly this reason.
   */
  it("has no neutral with a temperature", () => {
    const offenders = declarations()
      .filter(({ name }) => !isAccent(name) && !isCode(name))
      .map((entry) => ({ ...entry, rgb: channels(entry.value) }))
      .filter((entry): entry is typeof entry & { rgb: [number, number, number] } => !!entry.rgb)
      .filter(({ rgb }) => Math.max(...rgb) - Math.min(...rgb) > 0)
      .map(({ name, value, rgb }) => `${name}: ${value} — channels differ by ${Math.max(...rgb) - Math.min(...rgb)}`);

    expect(offenders, "chroma is the accent; every other value is grey").toEqual([]);
  });

  /**
   * One hue, and the alarm is what gets it.
   *
   * The failure this catches is a second red: a `--material` given its own hex, a hex away
   * from `--accent`, so that a material badge and the primary button beside it are two reds
   * that nearly match. Declaring the alias rather than the value is what makes that
   * impossible, and this asserts the alias rather than trusting it.
   *
   * The other half is that `held` and `cleared` stay colourless. They were amber and green;
   * they are weight now, and a hue creeping back into either is the scale quietly becoming
   * four colours again.
   */
  it("gives its one hue to the alarm, and leaves the other two verdicts grey", () => {
    const material = declarations().filter(({ name }) => name.startsWith("--material"));
    expect(material.length, "--material is declared in three scopes").toBeGreaterThanOrEqual(3);
    for (const { name, value } of material) {
      expect(value, `${name} should be the accent, not a second red`).toMatch(/^var\(--accent/);
    }

    for (const { name, value } of declarations()) {
      if (!/^--(held|cleared)/.test(name)) continue;
      const rgb = channels(value);
      if (!rgb) continue;
      expect(
        oklch(rgb).c,
        `${name}: ${value} — held and cleared are carried by weight, not by hue`,
      ).toBeLessThan(0.01);
    }
  });

  /**
   * The code palette is exempt from being grey. It is not exempt from staying out of the way.
   *
   * `cleared` green and a syntax green are the collision that matters: an excerpt sits a
   * couple of centimetres below the badge that graded it, and a string in the same hue as
   * "Cleared" reads as a claim about the code rather than as a string. So the code hues are
   * kept on the cool half of the wheel — violet, blue, cyan — where the severity scale never
   * goes, and this asserts the distance rather than trusting the six hex codes to hold it.
   *
   * 35 degrees, not 55 like the verdicts, and the difference is not a weaker rule. `cleared`
   * sits at 160, which is the warm edge of the cool arc, and three code hues spaced evenly
   * across what is left (306, 252, 207) put cyan 42 degrees from it — the closest any of the
   * six pairs comes. A higher bar here would not buy separation; it would force the three
   * code hues together at the violet end, where they stop telling a string from a name. So
   * the bar is set to catch what actually breaks this: a code token that has drifted into
   * red, amber or green.
   */
  it("keeps code colour off the accent", () => {
    for (const theme of ["light", "dark"] as const) {
      const verdicts = new Map<string, number>();
      const code = new Map<string, number>();
      for (const { name, value } of declarations()) {
        const rgb = channels(value);
        if (!rgb) continue;
        // Light is declared first, in `:root`; anything after it is a dark override.
        const take = (into: Map<string, number>) => {
          if (theme === "light" ? !into.has(name) : true) into.set(name, oklch(rgb).h);
        };
        if (name === "--accent") take(verdicts);
        // The comment is the one code token with no hue to keep anywhere.
        else if (isCode(name) && oklch(rgb).c > 0.02) take(code);
      }

      expect([...code.keys()].sort(), `${theme}: the code palette lost its colour`).toEqual([
        "--code-keyword",
        "--code-lit",
        "--code-name",
      ]);

      for (const [codeName, codeHue] of code) {
        for (const [verdictName, verdictHue] of verdicts) {
          const raw = Math.abs(codeHue - verdictHue);
          const gap = Math.min(raw, 360 - raw);
          expect(
            gap,
            `${theme}: ${codeName} is ${Math.round(gap)}° from ${verdictName}`,
          ).toBeGreaterThan(35);
        }
      }
    }
  });
});
