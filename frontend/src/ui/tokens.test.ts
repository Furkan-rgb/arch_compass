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

/** The three, and nothing else, carry colour. Everything here must be grey. */
const VERDICTS = ["material", "held", "cleared"];
const isVerdict = (name: string) => VERDICTS.some((verdict) => name.startsWith(`--${verdict}`));

describe("the token layer", () => {
  /**
   * A neutral with unequal channels is a second temperature, and a second temperature costs
   * the verdicts distance from the ground they sit on. The previous system's paper was the
   * same warmth as the `held` amber for exactly this reason.
   */
  it("has no neutral with a temperature", () => {
    const offenders = declarations()
      .filter(({ name }) => !isVerdict(name))
      .map((entry) => ({ ...entry, rgb: channels(entry.value) }))
      .filter((entry): entry is typeof entry & { rgb: [number, number, number] } => !!entry.rgb)
      .filter(({ rgb }) => Math.max(...rgb) - Math.min(...rgb) > 0)
      .map(({ name, value, rgb }) => `${name}: ${value} — channels differ by ${Math.max(...rgb) - Math.min(...rgb)}`);

    expect(offenders, "chroma is spent on verdicts; every other value is grey").toEqual([]);
  });

  /**
   * Three hues bunched at one end of the wheel are three shades of one signal.
   *
   * Even spacing is the whole trick: `material` at 40 degrees was 43 from `held` but 80 from
   * `cleared`, so the pair a reader most needs to tell apart — act on it, versus waiting on
   * someone — were the two sitting closest together.
   */
  it("keeps the three verdicts far apart, and evenly", () => {
    for (const theme of ["light", "dark"] as const) {
      // The dark values are declared twice on purpose (attribute selector and media query);
      // taking the last occurrence of each is enough to compare the set.
      const found = new Map<string, ReturnType<typeof oklch>>();
      for (const { name, value } of declarations()) {
        const verdict = VERDICTS.find((v) => name === `--${v}`);
        const rgb = verdict && channels(value);
        if (!verdict || !rgb) continue;
        // Light is declared first, in `:root`; anything after it is a dark override.
        if (theme === "light" ? !found.has(verdict) : true) found.set(verdict, oklch(rgb));
      }

      const hues = VERDICTS.map((verdict) => found.get(verdict)!.h).sort((a, b) => a - b);
      const gaps = [hues[1] - hues[0], hues[2] - hues[1]];
      for (const gap of gaps) {
        expect(gap, `${theme}: two verdict hues are ${Math.round(gap)}° apart`).toBeGreaterThan(55);
      }
      expect(
        Math.abs(gaps[0] - gaps[1]),
        `${theme}: the gaps are ${gaps.map(Math.round).join("° and ")}° — spaced unevenly`,
      ).toBeLessThan(25);
    }
  });
});
