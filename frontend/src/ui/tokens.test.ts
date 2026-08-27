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

/** WCAG relative luminance, which is a different curve from OKLCH's lightness. */
function luminance([r, g, b]: [number, number, number]): number {
  const lin = (v: number) => {
    const s = v / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function contrast(a: [number, number, number], b: [number, number, number]): number {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

/**
 * The value each token resolves to in one theme.
 *
 * Light is `:root`, which is declared first, so the first occurrence of a name is its light
 * value; every later one is a dark override and the last of those is what a dark reader
 * gets. This is the same reading `keeps code colour off the accent` below makes, hoisted
 * because two tests now need it.
 */
function resolved(theme: "light" | "dark"): Map<string, [number, number, number]> {
  const values = new Map<string, [number, number, number]>();
  for (const { name, value } of declarations()) {
    const rgb = channels(value);
    if (!rgb) continue;
    if (theme === "light" && values.has(name)) continue;
    values.set(name, rgb);
  }
  return values;
}

/** The alpha of `rgb(r g b / N%)` or `rgb(r g b / N)`, and 1 for a value that states none. */
function alpha(value: string): number {
  const percent = /\/\s*([\d.]+)%/.exec(value);
  if (percent) return Number(percent[1]) / 100;
  const fraction = /\/\s*([\d.]+)\s*\)/.exec(value);
  return fraction ? Number(fraction[1]) : 1;
}

/** `top` at opacity `a`, painted over the opaque `bottom`. */
function over(
  top: [number, number, number],
  a: number,
  bottom: [number, number, number],
): [number, number, number] {
  return [0, 1, 2].map((i) => top[i] * a + bottom[i] * (1 - a)) as [number, number, number];
}

/** How far apart two greys are, in levels of the 0-255 ramp. */
function levels(a: [number, number, number], b: [number, number, number]): number {
  return Math.max(...[0, 1, 2].map((i) => Math.abs(a[i] - b[i])));
}

/**
 * One token's value in one theme, kept with its alpha, which `resolved` throws away.
 *
 * Same light-is-first reading as `resolved`, and the same skip: `.band` redeclares `--rule`
 * as `var(--band-rule)`, which is not a colour and is not this token's value anywhere a
 * `channels` call can see.
 */
function declared(
  theme: "light" | "dark",
  name: string,
): { rgb: [number, number, number]; a: number } {
  let found: { rgb: [number, number, number]; a: number } | null = null;
  for (const declaration of declarations()) {
    if (declaration.name !== name) continue;
    const rgb = channels(declaration.value);
    if (!rgb) continue;
    if (theme === "light" && found) continue;
    found = { rgb, a: alpha(declaration.value) };
  }
  if (!found) throw new Error(`${name} is not declared as a colour in ${theme}`);
  return found;
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

  /**
   * A hairline is a hairline because of how close it is to the surface it separates.
   *
   * `--rule` is the whole structural device of this system and the one value in it that had
   * nothing asserting anything about its colour. What rests on it: the docket draws a run of
   * same-verdict rows as one three-pixel column of colour and lets `divide-y divide-rule` cut
   * it into rows. That reads as a boundary and not as damage for exactly one reason — the
   * line is about 26 levels of grey off the panel it crosses. 10% black on `#ffffff`
   * composites to 229.5, and 11% white on `#0d0d0d` to 39.6.
   *
   * The failure this exists for is not the rule going missing. It is the rule going *loud*.
   * Drop `divide-rule` and keep `divide-y` and the border falls back to `currentColor`, which
   * is `--ink`: 245 levels off the surface in light, at exactly the same one pixel of width.
   * `tests/browser/` asserts that the docket's row rule is the value of this token rather
   * than merely present, and a browser cannot see a hex code to say whether the value is a
   * sane one. That half is arithmetic, so it is here.
   */
  it("keeps the rule a hairline against the surface it separates", () => {
    for (const theme of ["light", "dark"] as const) {
      const surface = resolved(theme).get("--surface")!;
      const ink = resolved(theme).get("--ink")!;
      const rule = declared(theme, "--rule");
      const painted = over(rule.rgb, rule.a, surface);

      const hairline = levels(painted, surface);
      expect(
        hairline,
        `${theme}: --rule paints ${hairline.toFixed(1)} levels off --surface — that is a line`,
      ).toBeLessThan(40);
      expect(
        hairline,
        `${theme}: --rule paints ${hairline.toFixed(1)} levels off --surface — nothing is there`,
      ).toBeGreaterThan(8);

      // And the distance that makes asserting this colour in a browser worth the trouble:
      // the fallback a lost token leaves behind is an order of magnitude louder.
      const shout = levels(ink, surface);
      expect(
        shout / hairline,
        `${theme}: currentColor is only ${(shout / hairline).toFixed(1)}x the rule's contrast`,
      ).toBeGreaterThan(5);
    }
  });

  /**
   * The ramp has to be readable on every ground the ramp itself defines.
   *
   * `--ink-3` was `#737373` in both themes, on the argument that a value near the middle
   * reads correctly on either ground. It did not: two of its eight ground-and-theme pairs
   * cleared 4.5:1, and the six that failed included the canvas in light and every surface in
   * dark. The tier carries the docket's meta line, every `Label` and every empty state, so
   * the text explaining the interface was the least readable text in it.
   *
   * What made that survivable for so long is that nothing measured it. A hex code that looks
   * mid-grey in a diff is indistinguishable from one that is, and the four grounds moved
   * twice under it — `--sunken` went from black to the brightest of the dark four — without
   * anything re-checking what still sat on them. So this is the arithmetic rather than the
   * taste: every ink against every ground of its own theme, at the AA bar for body text.
   *
   * The four grounds are the ones an ink is ever painted on. `--overlay` and `--chrome` are
   * not among them — both are translucent and composite over whichever of the four is behind
   * them, so a ratio against either would be a ratio against nothing.
   */
  it("keeps every ink readable on every ground it is painted on", () => {
    const GROUNDS = ["--canvas", "--surface", "--surface-2", "--sunken"] as const;
    const failures: string[] = [];

    for (const theme of ["light", "dark"] as const) {
      const values = resolved(theme);
      const inks = [...values.keys()].filter((name) => /^--ink(-\d+)?$/.test(name));
      expect(inks.sort(), `${theme}: the ink ramp is three steps`).toEqual([
        "--ink",
        "--ink-2",
        "--ink-3",
      ]);

      for (const ink of inks) {
        for (const ground of GROUNDS) {
          const ratio = contrast(values.get(ink)!, values.get(ground)!);
          if (ratio < 4.5) {
            failures.push(`${theme}: ${ink} on ${ground} is ${ratio.toFixed(2)}:1`);
          }
        }
      }
    }

    expect(failures, "an ink that fails AA on a ground is unreadable text, not a quiet one").toEqual(
      [],
    );
  });

  /**
   * The one part of the ramp nothing measured, on the one ground it is ever painted on.
   *
   * `keeps every ink readable on every ground it is painted on` above was written because
   * nothing had ever checked the ink ramp's arithmetic. `isCode` existed when it was written
   * and the loop never used it, so the four `--code-*` values were the exemption that was
   * never audited — and a syntax palette is where saturation is spent, which is exactly where
   * a contrast failure hides. This is that audit.
   *
   * **4.5:1, not 3:1.** A highlighted token is body text: `ui/code.tsx` draws an excerpt at
   * 12px and `features/review/lookup-result.tsx` draws a lookup at 11px. Neither is large
   * text under any reading of the WCAG threshold, and 11px is the smallest text in the
   * product.
   *
   * **One ground, and it is established rather than assumed.** Every element that renders
   * `hljs-` spans sits on `--sunken`: `SourceExcerpt` and the `pre` in `ui/markdown.tsx`
   * declare `bg-sunken` themselves, and `ResultBox` in `features/review/lookup-result.tsx`
   * declares it for both shapes that reach it. `NumberedCode` has no fill of its own and its
   * only two callers are the first and the third. So the second assertion below is not
   * decoration: it proves `--sunken` is the *tightest* of the four grounds in both themes —
   * the darkest one in light, the lightest one in dark — which is what makes a single ratio
   * here a bound on all four, and what would fail if the elevation ramp were reordered under
   * this test.
   */
  it("keeps every code colour readable on the ground code is painted on", () => {
    const failures: string[] = [];

    for (const theme of ["light", "dark"] as const) {
      const values = resolved(theme);
      const sunken = values.get("--sunken")!;
      const code = [...values.keys()].filter(isCode);
      expect(code.sort(), `${theme}: the code palette is four roles`).toEqual([
        "--code-comment",
        "--code-keyword",
        "--code-lit",
        "--code-name",
      ]);

      for (const role of code) {
        const ratio = contrast(values.get(role)!, sunken);
        if (ratio < 4.5) {
          failures.push(`${theme}: ${role} on --sunken is ${ratio.toFixed(2)}:1`);
        }
      }

      // `--sunken` is the worst case, so clearing it clears the other three grounds.
      const ink = values.get("--ink")!;
      for (const ground of ["--canvas", "--surface", "--surface-2"] as const) {
        expect(
          contrast(ink, values.get(ground)!),
          `${theme}: ${ground} is a tighter ground than --sunken, so the bar above is measured on the wrong one`,
        ).toBeGreaterThan(contrast(ink, sunken));
      }
    }

    expect(
      failures,
      "code at 11px is body text, and a token under 4.5:1 is a colour that stopped being readable",
    ).toEqual([]);
  });

  /**
   * A token declared in two of the three scopes is a theme bug that only one reader sees.
   *
   * `index.html` stamps `data-theme` before first paint, so `:root[data-theme="dark"]` is what
   * normally runs; the `prefers-color-scheme` block is the fallback for a reader whose browser
   * never executed that script. A value added to one dark block and not the other is invisible
   * to whoever writes it and wrong for everyone on the other path — and the code palette is
   * the family most likely to be edited one hue at a time.
   */
  it("declares every code colour in all three scopes, with the two dark ones agreeing", () => {
    const byName = new Map<string, string[]>();
    for (const { name, value } of declarations()) {
      if (!isCode(name)) continue;
      byName.set(name, [...(byName.get(name) ?? []), value]);
    }

    expect([...byName.keys()].sort(), "the code palette is four roles").toEqual([
      "--code-comment",
      "--code-keyword",
      "--code-lit",
      "--code-name",
    ]);

    for (const [name, values] of byName) {
      expect(values.length, `${name}: light, the media query and the attribute — three`).toBe(3);
      expect(values[1], `${name}: the two dark declarations disagree`).toBe(values[2]);
    }
  });

  /**
   * Four roles a reader can tell apart, measured as distance rather than asserted as taste.
   *
   * The complaint this exists for is that an excerpt reads flat, and the diagnosis is in the
   * comment above `--code-keyword` in `styles.css`: tokenising all 501 stored `read_file`
   * lookups says 48.11% of a block's non-space characters carry no class at all and are drawn
   * in `--ink`, so the palette's colours are always a minority of what is on screen and each
   * one has to survive being read *against* that ink. Contrast against the ground is a
   * different question and the test above it is where that lives; this is about telling the
   * five things in a block apart from each other.
   *
   * OKLab ΔE, not hue, because hue alone is what was wrong. The dark palette used to be three
   * pastels spanning 0.103 of lightness and 0.012 of chroma — separated on paper by 96 degrees
   * of hue and, at the 11px `features/review/lookup-result.tsx` renders at, barely at all.
   *
   * The three bars are the three questions, and each sits about a quarter below the tightest
   * pair it governs so a nudge does not fail it and a reversal does:
   *
   *   0.20  a coloured role against the plain ink — is this token classified at all?
   *         Tightest: `--code-keyword` in dark, 0.273.
   *   0.15  the name against the literal — is this a name or a written-out value?
   *         Tightest: dark, 0.196. It was 0.111 before the literal moved off cyan.
   *   0.09  the name against the keyword — ours or the language's? Tightest: dark, 0.117.
   *         The lowest bar of the three on purpose: this is the one pair the palette does not
   *         carry by colour alone, because `.hljs-keyword` is also the only role set in the
   *         mono's 600 weight, and `styles.css` loads exactly two cuts of IBM Plex Mono, so
   *         there is no third weight to give a second role even if one were wanted.
   *
   * A fourth clause holds the arc itself: the three hues span 130° in light and 136° in dark,
   * where they spanned 81° and 96° before the literal moved off cyan, and the bar is 110°.
   * That is the same decision the 0.15 bar above is a consequence of, said in the units it was
   * made in — and it is what catches the light half of that move, which the ΔE bar does not:
   * light was already 0.173 there, comfortably over 0.15, while its hue span was not.
   *
   * `--code-comment` against `--code-lit` is the tightest pair in the set at 0.092 in light,
   * and it has no bar. A docstring and a `#` comment are both prose inside code; reading one
   * as the other costs a reader nothing, and buying distance there would have to come out of
   * a pair that matters. Naming it here is what stops it being an oversight.
   */
  it("keeps the four code roles apart from each other and from the ink they sit in", () => {
    /** OKLab ΔE — the straight-line distance, which is what OKLab is for. */
    const distance = (a: [number, number, number], b: [number, number, number]) => {
      const oklab = ([r, g, bl]: [number, number, number]) => {
        const { l, c, h } = oklch([r, g, bl]);
        return [l, c * Math.cos((h * Math.PI) / 180), c * Math.sin((h * Math.PI) / 180)];
      };
      const [x, y] = [oklab(a), oklab(b)];
      return Math.hypot(x[0] - y[0], x[1] - y[1], x[2] - y[2]);
    };

    for (const theme of ["light", "dark"] as const) {
      const values = resolved(theme);
      const get = (name: string) => values.get(name)!;
      const ink = get("--ink");

      for (const role of ["--code-keyword", "--code-name", "--code-lit", "--code-comment"]) {
        const apart = distance(get(role), ink);
        expect(
          apart,
          `${theme}: ${role} is ${apart.toFixed(3)} from --ink, which is most of the block`,
        ).toBeGreaterThan(0.2);
      }

      const fromLiteral = distance(get("--code-name"), get("--code-lit"));
      expect(
        fromLiteral,
        `${theme}: a name and a literal are ${fromLiteral.toFixed(3)} apart`,
      ).toBeGreaterThan(0.15);

      const fromKeyword = distance(get("--code-name"), get("--code-keyword"));
      expect(
        fromKeyword,
        `${theme}: a name and a keyword are ${fromKeyword.toFixed(3)} apart`,
      ).toBeGreaterThan(0.09);

      // And the arc the three are spread across, which is the decision the ΔE bars are the
      // consequence of. A plain max-minus-min is the right reading only because every code
      // hue is between 170 and 310 degrees — `keeps code colour off the accent` above is what
      // holds them there, and a value that escaped that arc would fail it first.
      const hues = ["--code-keyword", "--code-name", "--code-lit"].map((n) => oklch(get(n)).h);
      const span = Math.max(...hues) - Math.min(...hues);
      expect(
        span,
        `${theme}: the three code hues span ${Math.round(span)}°`,
      ).toBeGreaterThan(110);
    }
  });
});
