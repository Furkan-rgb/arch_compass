import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * The colour laws, checked as arithmetic rather than as taste.
 *
 * Every rule in this file was broken once in a way that looked fine in the file and wrong on
 * screen, which is the whole argument for measuring them here. A tint of `233 240 252` is blue
 * nineteen points over red — invisible on glass at 5% and unmistakable on anything opaque.
 * `--material` sat at 40 degrees, which is orange, 43 degrees from `held`, and read as an
 * accent competing with a warning rather than as an alert. And the defect the whole of v2 came
 * from: `--ink-2` and `--ink-3` measured 6.12:1 and 7.49:1 against their ground, both
 * comfortably AA, and **1.22:1 against each other** — so a label and the value beside it were
 * one colour with two names, and the test that measured each ink against each ground was right
 * to pass. None of the three is the kind of thing a reviewer catches by reading a diff of hex
 * codes.
 *
 * What changed at v2, and what this file was rewritten for: the old first test asserted that
 * every token outside `--accent` and `--code-*` had equal RGB channels. The system it was
 * written for spent its entire chroma budget on one red and paid for it twice — two of three
 * verdicts went grey and stopped separating down a column, and provenance had to borrow the
 * alarm colour to say "this goes somewhere". v2 has four signal hues and warm greys, so that
 * rule now reports 77 declarations across 36 tokens, and every one of them is the design. The replacement is not
 * weaker: **the set of four is closed**, and a token carrying chroma has to be one of them.
 * That catches a fifth hue arriving anywhere, which "no chroma" only caught by forbidding the
 * four as well.
 *
 * `docs/design-system.md` is the contract; this file is what fails the build when the
 * stylesheet stops honouring it.
 */
const CSS = readFileSync(join(__dirname, "..", "styles.css"), "utf8");

/** The stylesheet with its comments blanked, line numbering intact. */
function withoutCssComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, (block) => block.replace(/[^\n]/g, " "));
}

/** Every custom property in a chunk of CSS, as (name, value) pairs, in source order. */
function properties(css: string): Array<{ name: string; value: string }> {
  return [...css.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)].map((match) => ({
    name: match[1],
    value: match[2].trim(),
  }));
}

/** Every custom property in the file, whichever block it is declared in. */
function declarations(): Array<{ name: string; value: string }> {
  return properties(withoutCssComments(CSS));
}

/**
 * Every innermost declaration block in the stylesheet, with the selector chain that reaches it.
 *
 * A brace scanner rather than a regex, because the two things this file has to locate are both
 * nested: the theme scopes live one level inside `@media`, and the rule that decides whether a
 * `--code-*` token is painted somewhere legitimate is a question about *which selector* the
 * `var()` sits under. `prelude` is the chain joined by spaces — `@media (…) :root:not(…)` — so
 * a block can be addressed by exactly the thing that makes it that block.
 *
 * Innermost only: a block whose body still contains a brace is a wrapper, and its properties
 * belong to its children rather than to it.
 *
 * `selector` is the block's own line, kept beside the chain because the two questions want
 * different halves: a theme scope is addressed by the whole chain — the fallback block is a
 * `:root` and so is the light one — while a rule is *a code rule* on the strength of its own
 * selector list, whatever at-rule it happens to be wrapped in. Asking the chain there would
 * report a `.hljs-comment` moved inside an `@media print` as a syntax colour painted loose.
 */
function blocks(): Array<{ prelude: string; selector: string; body: string }> {
  const css = withoutCssComments(CSS);
  const found: Array<{ prelude: string; selector: string; body: string }> = [];
  const open: Array<{ selector: string; at: number }> = [];

  for (let index = 0; index < css.length; index += 1) {
    if (css[index] === "{") {
      const before = css.slice(0, index);
      const cut = Math.max(before.lastIndexOf("{"), before.lastIndexOf("}"));
      open.push({ selector: before.slice(cut + 1).trim().replace(/\s+/g, " "), at: index });
      continue;
    }
    if (css[index] !== "}") continue;
    const block = open.pop();
    if (!block) continue;
    const body = css.slice(block.at + 1, index);
    if (body.includes("{")) continue;
    found.push({
      prelude: [...open.map((o) => o.selector), block.selector].join(" "),
      selector: block.selector,
      body,
    });
  }

  return found;
}

/**
 * The four blocks that declare a token's value, addressed by their selector.
 *
 * This replaces reading the file by position — "light is the first declaration of a name, dark
 * is the last" — which was true until `.on-band` arrived. That block redeclares the twelve
 * signal tokens and the three inks *after* both dark blocks, so the last declaration of
 * `--ink` in the file is now the band's, not the dark theme's. They happen to be the same hex
 * today, which is exactly the kind of accident that turns into a false pass: change the dark
 * ramp, forget the band, and every dark figure in this file would be measured against a value
 * no dark reader sees.
 *
 * Naming the scopes also makes a rename fail loudly rather than emptying the maps and passing
 * vacuously, which is what `scope()` throwing is for.
 */
const SCOPES = {
  light: ":root",
  darkFallback: '@media (prefers-color-scheme: dark) :root:not([data-theme="light"])',
  darkAttribute: ':root[data-theme="dark"]',
  band: ".on-band",
} as const;

function scope(which: keyof typeof SCOPES): Array<{ name: string; value: string }> {
  const block = blocks().find((candidate) => candidate.prelude === SCOPES[which]);
  if (!block) throw new Error(`${SCOPES[which]} is not a block in styles.css any more`);
  return properties(block.body);
}

/** What a reader of one theme gets, later declaration winning. */
function themeDeclarations(theme: "light" | "dark"): Array<{ name: string; value: string }> {
  if (theme === "light") return scope("light");
  return [...scope("light"), ...scope("darkFallback"), ...scope("darkAttribute")];
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

/** The shorter way round the wheel between two hues, in degrees. */
function arc(a: number, b: number): number {
  const raw = Math.abs(a - b) % 360;
  return Math.min(raw, 360 - raw);
}

/** The value each token resolves to in one theme. */
function resolved(theme: "light" | "dark"): Map<string, [number, number, number]> {
  const values = new Map<string, [number, number, number]>();
  for (const { name, value } of themeDeclarations(theme)) {
    const rgb = channels(value);
    if (rgb) values.set(name, rgb);
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

/** One token's value in one theme, kept with its alpha, which `resolved` throws away. */
function declared(
  theme: "light" | "dark",
  name: string,
): { rgb: [number, number, number]; a: number } {
  let found: { rgb: [number, number, number]; a: number } | null = null;
  for (const declaration of themeDeclarations(theme)) {
    if (declaration.name !== name) continue;
    const rgb = channels(declaration.value);
    if (rgb) found = { rgb, a: alpha(declaration.value) };
  }
  if (!found) throw new Error(`${name} is not declared as a colour in ${theme}`);
  return found;
}

/**
 * The closed set. Four hues carry meaning in this product and nothing else carries any.
 *
 * Each is the hue `docs/design-system.md` names it at, in OKLCH degrees: the alarm red that is
 * also the brand's, an amber for what is waiting on a person, a green for what is settled, and
 * a blue that is not a severity at all — `--mark` says *where this came from*, which is the one
 * thing v1 had no colour for and therefore said in the alarm red.
 *
 * They are the constants rather than the tokens on purpose. A test that read the hue out of the
 * stylesheet and then checked the stylesheet against it would assert nothing; these four
 * numbers are the document, and the tokens are what is being measured against them.
 */
const SIGNALS = { material: 27, held: 84, cleared: 158, mark: 250 } as const;

/**
 * How far a token of one family may sit from its family's nominal hue.
 *
 * Not zero, and the reason is the ramp rather than sloppiness: a signal is three tiers in two
 * themes, and each of the six values is picked to hit a contrast floor on a different ground.
 * Holding all six to one hue would cost lightness where lightness is the constrained axis. The
 * widest drift in the shipped set is light `--held` at `#835000`, which measures 68.3° against
 * the 84° the document names it at — an amber that had to go brown to clear 4.5:1 on a
 * near-white ground.
 *
 * 20 is chosen from both sides. It is comfortably above that 15.7° drift, and comfortably below
 * the 28.5° at which two families' windows would touch: the tightest neighbours on the wheel
 * are `material` and `held`, 57° apart. `the four hues are far enough apart to be a set` below
 * asserts that second half rather than leaving it to this comment, so moving a nominal hue
 * fails here rather than quietly merging two signals.
 */
const HUE_WINDOW = 20;

/** `--material`, `--held-edge`, `--cleared-wash`, `--mark-edge-on-band` — and nothing else. */
const SIGNAL_TOKEN = /^--(material|held|cleared|mark)(-edge|-wash)?(-on-band)?$/;

function familyOf(name: string): keyof typeof SIGNALS | null {
  const match = SIGNAL_TOKEN.exec(name);
  return match ? (match[1] as keyof typeof SIGNALS) : null;
}

/**
 * The one family allowed chroma without being a signal, and the reason it is bounded.
 *
 * A syntax palette is not decoration and it is not a fifth signal: it answers a question the
 * verdict scale never asks, which is whether a token is a name somebody chose or the language's
 * own furniture. Weight alone cannot answer it, because half of Python is a keyword and a page
 * of bold says nothing.
 *
 * The exemption is from the *closed set*, not from being kept out of the way. What stops it
 * being the hole this list looks like used to be an angle — a code hue stays 35° from the
 * accent — and is now `keeps the code palette inside a code block, and the signals outside one`
 * below. See that test for why the angle could not survive four signals.
 */
const isCode = (name: string) => name.startsWith("--code-");

/** The four grounds an ink or a signal is ever painted on. */
const GROUNDS = ["--canvas", "--surface", "--surface-2", "--sunken"] as const;

/** The three tiers of a signal, and what each is allowed to paint. */
const TIERS = [
  { suffix: "", floor: 4.5, paints: "a word" },
  { suffix: "-edge", floor: 3, paints: "an edge, a glyph, a bar, a dot" },
] as const;

describe("the token layer", () => {
  /**
   * Four hues, and the set is closed.
   *
   * Two claims, and they fail in opposite directions. The first is that a token named after a
   * signal is that signal's hue in every tier and both themes — a `--held-edge` that drifted
   * red is a warning wearing the alarm's colour, and the docket draws a column of them. The
   * second is that nothing else carries chroma at all: an offender here is a fifth hue, and a
   * fifth hue is what turns a signal into a theme.
   *
   * **0.006 is where a grey stops being grey.** The v2 grounds and inks are warm on purpose —
   * `docs/design-system.md` calls it "below the point a reader can name the hue, above the
   * point a grey reads as dead rather than chosen" — and they measure 0.0039 to 0.0056 of
   * chroma. So the bar sits just over the warmest of them and just under everything that means
   * something: the palest thing in the signal set is `--material-wash` at 0.0225, three and a half
   * times clear of it. The old rule was equal RGB channels, which this replaces on both ends: it
   * permits the warmth the ramps are built on, and it catches a hue that arrives at 0.02 —
   * which equal channels caught too, but only by also condemning the four signals.
   *
   * The washes are asserted to carry *some* chroma and nothing bounds them from above here,
   * because something else already does: a wash that saturated would fail `keeps both tiers of
   * every signal over the floor their tier answers to` against the very text it is a fill for.
   *
   * The set is listed as well as measured, and that is not belt-and-braces: every test below
   * looks its tokens up by name, so a `--mark-wash` that was deleted rather than mistuned would
   * fail four tests with a type error and none of them with a sentence. Twenty-four names —
   * four families, three tiers, and the same twelve again for the strip that does not invert.
   */
  it("carries four signal hues, and no fifth", () => {
    const drift: string[] = [];
    const greyed: string[] = [];
    const expected = (Object.keys(SIGNALS) as Array<keyof typeof SIGNALS>)
      .flatMap((family) => ["", "-edge", "-wash"].map((tier) => `--${family}${tier}`))
      .flatMap((token) => [token, `${token}-on-band`])
      .sort();

    for (const theme of ["light", "dark"] as const) {
      expect(
        [...resolved(theme).keys()].filter(familyOf).sort(),
        `${theme}: a signal is three tiers, on the page and on the band`,
      ).toEqual(expected);

      for (const [name, rgb] of resolved(theme)) {
        const family = familyOf(name);
        if (!family) continue;
        const { c, h } = oklch(rgb);
        const away = arc(h, SIGNALS[family]);
        if (away > HUE_WINDOW) {
          drift.push(`${theme}: ${name} is ${away.toFixed(1)}° from ${family}'s ${SIGNALS[family]}°`);
        }
        // A wash is a tint and the other two tiers are the hue itself, so they are held to
        // different floors — but both floors are "this still reads as its own colour".
        const floor = /-wash(-on-band)?$/.test(name) ? 0.01 : 0.09;
        if (c < floor) greyed.push(`${theme}: ${name} carries ${c.toFixed(3)} chroma`);
      }
    }

    expect(drift, "a signal that drifted is a different signal wearing the same name").toEqual([]);
    expect(greyed, "a signal that lost its chroma is a signal that stopped signalling").toEqual([]);

    // And the closed half: everything else in the file, in either theme, is grey or is code.
    const strangers = [...new Set(
      declarations()
        .map((entry) => ({ ...entry, rgb: channels(entry.value) }))
        .filter((entry): entry is typeof entry & { rgb: [number, number, number] } => !!entry.rgb)
        .filter(({ name }) => !familyOf(name) && !isCode(name))
        .map((entry) => ({ ...entry, ...oklch(entry.rgb) }))
        .filter(({ c }) => c > 0.006)
        .filter(({ h }) => !Object.values(SIGNALS).some((hue) => arc(h, hue) <= HUE_WINDOW))
        .map(({ name, value, h, c }) => `${name}: ${value} — ${c.toFixed(3)} chroma at ${h.toFixed(0)}°`),
    )];

    expect(
      strangers,
      "a hue outside the four is a fifth signal, whatever the token is called",
    ).toEqual([]);
  });

  /**
   * The windows the test above measures against have to stay disjoint, or it asserts nothing.
   *
   * `material` and `held` are the tightest pair at 57°, so at `HUE_WINDOW` 20 there are 17°
   * between the two windows. This is here rather than in a comment because the failure it
   * catches is a plausible edit — moving a nominal hue to match a token somebody retuned — and
   * the consequence is not a failing test but a passing one that has stopped distinguishing an
   * amber from a red.
   */
  it("keeps the four hues far enough apart to be a set", () => {
    const names = Object.keys(SIGNALS) as Array<keyof typeof SIGNALS>;
    for (const a of names) {
      for (const b of names) {
        if (a >= b) continue;
        const gap = arc(SIGNALS[a], SIGNALS[b]);
        expect(gap, `${a} and ${b} are ${gap}° apart`).toBeGreaterThan(2 * HUE_WINDOW);
      }
    }
  });

  /**
   * One red, declared once.
   *
   * The failure this catches is a second red: `--material` and `--accent` given their own
   * hexes, a hex apart, so that a material badge and the primary button beside it are two reds
   * that nearly match. Declaring one as an alias of the other is what makes that impossible,
   * and this asserts the alias rather than trusting it.
   *
   * **The alias runs the other way now, and the direction is the point.** v1 had
   * `--material: var(--accent)`, which was right while red was an accent that a verdict
   * borrowed. v2 has four signals and no accent of its own: red is the alarm, `--material` is
   * its name, and `--accent` is the older name kept so the primary action and the brand mark do
   * not have to be renamed in forty files. So `--accent: var(--material)` — and a `--material`
   * declared as `var(--accent)` would now be a cycle rather than a definition.
   *
   * `--accent-fill`, `--accent-on-fill` and `--accent-strong` are not aliases and are not
   * checked here: a fill and the ink on it are their own decisions, and the light fill happens
   * to equal the light `--material` while the dark one deliberately does not. What holds them
   * to the red is `carries four signal hues, and no fifth` above, which measures the hue rather
   * than the spelling.
   */
  it("declares the alarm once, so a second red cannot appear beside it", () => {
    const accent = declarations().filter(({ name }) => name === "--accent");
    expect(accent.length, "--accent is declared where it is handed over").toBeGreaterThanOrEqual(1);
    for (const { value } of accent) {
      expect(value, "--accent is the alarm's other name, not a second red").toBe("var(--material)");
    }

    // And the definition it points at is a real value in all three theme scopes, so the alias
    // resolves for every reader rather than for the one whose theme happened to declare it.
    for (const which of ["light", "darkFallback", "darkAttribute"] as const) {
      const material = scope(which).find(({ name }) => name === "--material");
      expect(material?.value, `${SCOPES[which]} declares --material`).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });

  /**
   * A step nobody can see is not a step.
   *
   * v1's light ramp went `#ffffff`, `#fafafa`, `#f5f5f5` — 0.015 in OKLCH lightness between
   * adjacent grounds, which is under the threshold of sight. An opened fold, a panel header and
   * a table strip were all the same white, and `Tag` painting `bg-surface-2` inside a fold that
   * also painted `bg-surface-2` produced four "Measured as" boxes that were outlines around
   * nothing. Contrast against an ink could not see any of it: both values cleared AA on both
   * grounds, because they were the same ground.
   *
   * 0.020 is the bar and the shipped ramp clears it in every step — 0.021 to 0.028 in light,
   * 0.043 to 0.057 in dark. The order is asserted with it, because the ramp is not a mirror:
   * **light means elevation**, so in light the page sits under the panels and `--sunken` is
   * below the page, while in dark nothing is darker than the page and `--sunken` is the *top*
   * of the ramp — a film of white laid over the void rather than a hole dug below it. Those are
   * two different orderings of the same four tokens, and a component reaching for "the quiet
   * inset" gets the right answer in both only because the tokens are ordered this way.
   *
   * `--control` and `--control-2` are not in the ramp: in light they duplicate `--surface` and
   * `--sunken`, and in dark they are alphas that composite over whichever ground is behind
   * them, so a step measured against them would be a step measured against nothing.
   */
  it("steps the ground ramp far enough for the step to be seen", () => {
    const ORDER = {
      light: ["--sunken", "--canvas", "--surface-2", "--surface"],
      dark: ["--canvas", "--surface", "--surface-2", "--sunken"],
    } as const;

    for (const theme of ["light", "dark"] as const) {
      const values = resolved(theme);
      const byLightness = [...GROUNDS].sort((a, b) => oklch(values.get(a)!).l - oklch(values.get(b)!).l);
      expect(byLightness, `${theme}: the elevation ramp is not in the documented order`).toEqual([
        ...ORDER[theme],
      ]);

      for (let i = 1; i < byLightness.length; i += 1) {
        const step = oklch(values.get(byLightness[i])!).l - oklch(values.get(byLightness[i - 1])!).l;
        expect(
          step,
          `${theme}: ${byLightness[i - 1]} to ${byLightness[i]} is ${step.toFixed(3)} in OKLCH L`,
        ).toBeGreaterThanOrEqual(0.02);
      }
    }
  });

  /**
   * Two inks that pass on the same ground can still be one colour.
   *
   * This is the defect the whole redesign came from and the one thing no test in the old file
   * could see. The Provenance fold's key measured 6.12:1 and its value 7.49:1 — both AA, both
   * correct, and 1.22:1 against *each other*, which is a definition list where the label and
   * the content are the same grey separated by a pixel of size and a change of case. Every
   * assertion in `keeps every ink readable on every ground it is painted on` below passed
   * throughout, because every one of them measures an ink against a ground.
   *
   * 0.09 in OKLCH lightness is the bar and the shipped ramp puts the tiers 0.10 and 0.20 apart
   * in both themes. Measured as contrast the same pair is 1.54:1 in light and 1.45:1 in dark,
   * against v1's 1.22:1 — which is the honest way to say what this bought: not a large number,
   * because two inks that both have to clear 4.5:1 on the same ground cannot be far apart in
   * luminance, but the difference between a division you can see and one you cannot.
   *
   * OKLCH lightness rather than a contrast ratio, because a ratio between two foregrounds is
   * not what WCAG's curve was fitted for, and because the failure is perceptual: the question
   * is whether a reader sees two greys, not whether one is legible on the other.
   */
  it("keeps the ink tiers apart from each other, not only from the ground", () => {
    for (const theme of ["light", "dark"] as const) {
      const values = resolved(theme);
      const tiers = ["--ink", "--ink-2", "--ink-3"] as const;
      const byLightness = [...tiers].sort((a, b) => oklch(values.get(a)!).l - oklch(values.get(b)!).l);

      for (let i = 1; i < byLightness.length; i += 1) {
        const [under, over_] = [byLightness[i - 1], byLightness[i]];
        const apart = oklch(values.get(over_)!).l - oklch(values.get(under)!).l;
        expect(
          apart,
          `${theme}: ${under} and ${over_} are ${apart.toFixed(3)} apart in OKLCH L, ` +
            `which is ${contrast(values.get(under)!, values.get(over_)!).toFixed(2)}:1`,
        ).toBeGreaterThanOrEqual(0.09);
      }
    }
  });

  /**
   * A hairline is a hairline because of how close it is to the surface it separates.
   *
   * `--rule` is the whole structural device of this system and the one value in it that had
   * nothing asserting anything about its colour. What rests on it: the docket draws a run of
   * same-verdict rows as one three-pixel column of colour and lets `divide-y divide-rule` cut
   * it into rows. That reads as a boundary and not as damage for exactly one reason — the line
   * is about 28 levels of grey off the panel it crosses. 11% black on `#fffffc` composites to
   * 227.0, and 12% white on `#181614` to 51.7.
   *
   * The failure this exists for is not the rule going missing. It is the rule going *loud*.
   * Drop `divide-rule` and keep `divide-y` and the border falls back to `currentColor`, which
   * is `--ink`: 233 levels off the surface in light, at exactly the same one pixel of width —
   * eight times the contrast of the line it replaced. `tests/browser/` asserts that the
   * docket's row rule is the value of this token rather than merely present, and a browser
   * cannot see a hex code to say whether the value is a sane one. That half is arithmetic, so
   * it is here.
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
   * `--ink-3` was `#737373` in both themes, on the argument that a value near the middle reads
   * correctly on either ground. It did not: two of its eight ground-and-theme pairs cleared
   * 4.5:1, and the six that failed included the canvas in light and every surface in dark. The
   * tier carries the docket's meta line, every `Label` and every empty state, so the text
   * explaining the interface was the least readable text in it.
   *
   * What made that survivable for so long is that nothing measured it. A hex code that looks
   * mid-grey in a diff is indistinguishable from one that is, and the four grounds have moved
   * twice under it — `--sunken` went from black to the brightest of the dark four — without
   * anything re-checking what still sat on them. So this is the arithmetic rather than the
   * taste: every ink against every ground of its own theme, at the AA bar for body text. The
   * tightest cell in the shipped ramp is `--ink-3` on `--sunken` in dark, at 4.62:1.
   *
   * The four grounds are the ones an ink is ever painted on. `--overlay` and `--chrome` are not
   * among them — both are translucent and composite over whichever of the four is behind them,
   * so a ratio against either would be a ratio against nothing.
   */
  it("keeps every ink readable on every ground it is painted on", () => {
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
   * The two tiers, and the line between them is WCAG's own.
   *
   * A signal is declared twice: `--material` for a word and `--material-edge` for a graphic.
   * That is not a light and a dark variant, it is the two things WCAG asks different amounts
   * of — 4.5:1 of body text, 3:1 of a user-interface component or a meaningful graphic — and
   * splitting on that line is what lets the edge tier be genuinely saturated while the word
   * stays readable. A word set in the edge tier is a contrast failure; a 3px edge painted in
   * the text tier is a signal spent on the one place the eye catches first.
   *
   * Both tiers are measured on all four grounds because a verdict is not confined to one: a
   * badge sits on a panel, a docket row's edge is drawn on `--surface` and again on `--sunken`
   * when the row is hovered, and an empty state's glyph sits on the canvas. The shipped floors
   * are 5.28:1 for a word — `--cleared` on `--sunken` in light, the tightest cell in the set,
   * and the reason `docs/design-system.md` lists green as the hue with the least headroom — and
   * 3.01:1 for an edge, `--cleared-edge` on `--sunken` in light.
   *
   * **And on its own wash, which is the pairing the grounds do not cover.** A badge is the one
   * place all three tiers of one signal meet: `bg-material-wash` with `border-material-edge`
   * and `text-material` on it. The wash is not a ground — nothing else is ever painted on it —
   * so it is asserted here against its own family rather than added to `GROUNDS`. The tightest
   * pairs are `--material` on `--material-wash` in dark at 4.87:1 and `--material-edge` on the
   * same wash at 3.50:1.
   */
  it("keeps both tiers of every signal over the floor their tier answers to", () => {
    const failures: string[] = [];

    for (const theme of ["light", "dark"] as const) {
      const values = resolved(theme);
      for (const family of Object.keys(SIGNALS) as Array<keyof typeof SIGNALS>) {
        for (const { suffix, floor, paints } of TIERS) {
          const token = `--${family}${suffix}`;
          const wash = `--${family}-wash`;
          for (const ground of [...GROUNDS, wash]) {
            const ratio = contrast(values.get(token)!, values.get(ground)!);
            if (ratio < floor) {
              failures.push(
                `${theme}: ${token} on ${ground} is ${ratio.toFixed(2)}:1, under ${floor} for ${paints}`,
              );
            }
          }
        }
      }
    }

    expect(failures, "a signal that fails its floor is a signal nobody can read").toEqual([]);
  });

  /**
   * The one strip that does not invert, and the twelve values that let it hold the same four
   * signals.
   *
   * The topbar and the landing page's field band are permanently dark, so they cannot borrow
   * `--ink` or `--surface` from a theme that might be light — and neither can the signals. A
   * `--material` badge on the band in the light theme would paint `#961114` on `--band`: 2.05:1,
   * a red that has gone black. `.on-band` is the handover, and this asserts that it hands over
   * *all twelve* rather than the two verdicts and a wash the v1 block corrected, which left
   * `--mark` on the rail at 2.36:1.
   *
   * Measured against `--band` rather than assumed from the dark theme. The twelve `-on-band`
   * values are the dark theme's signal set today and `--band` is the dark theme's `--surface`,
   * so every figure here is one the dark half of the test above has already proved — but that
   * is a fact about the current values, not a property of the band, and writing it as an
   * inheritance would stop measuring the moment either moved. The floors here are the same two
   * floors: 4.5:1 for a word, 3:1 for a graphic. The tightest cells are `--material-on-band` at
   * 6.24:1 and `--material-edge-on-band` at 4.49:1, with the same pair on their own wash at
   * 4.87:1 and 3.50:1.
   */
  it("hands the band all four signals, not the two the theme happened to break", () => {
    const remapped = new Map(scope("band").map(({ name, value }) => [name, value]));
    const values = new Map(
      scope("light")
        .map(({ name, value }) => [name, channels(value)] as const)
        .filter((entry): entry is readonly [string, [number, number, number]] => !!entry[1]),
    );
    const band = values.get("--band")!;
    const failures: string[] = [];

    for (const family of Object.keys(SIGNALS) as Array<keyof typeof SIGNALS>) {
      for (const suffix of ["", "-edge", "-wash"] as const) {
        const token = `--${family}${suffix}`;
        expect(
          remapped.get(token),
          `.on-band leaves ${token} at the theme's value, which is the wrong ground`,
        ).toBe(`var(${token}-on-band)`);
      }

      const wash = values.get(`--${family}-wash-on-band`)!;
      for (const { suffix, floor, paints } of TIERS) {
        const token = `--${family}${suffix}-on-band`;
        for (const [groundName, ground] of [["--band", band], [`--${family}-wash-on-band`, wash]] as const) {
          const ratio = contrast(values.get(token)!, ground);
          if (ratio < floor) {
            failures.push(
              `${token} on ${groundName} is ${ratio.toFixed(2)}:1, under ${floor} for ${paints}`,
            );
          }
        }
      }
    }

    expect(failures, "a signal on the band is read on the band, not on the page").toEqual([]);
  });

  /**
   * The one part of the ramp nothing measured, on the one ground it is ever painted on.
   *
   * `keeps every ink readable on every ground it is painted on` above was written because
   * nothing had ever checked the ink ramp's arithmetic. `isCode` existed when it was written
   * and the loop never used it, so the four `--code-*` values were the exemption that was never
   * audited — and a syntax palette is where saturation is spent, which is exactly where a
   * contrast failure hides. This is that audit.
   *
   * **4.5:1, not 3:1.** A highlighted token is body text: `ui/code.tsx` draws an excerpt at
   * 12px and `features/review/lookup-result.tsx` draws a lookup at 11px. Neither is large text
   * under any reading of the WCAG threshold.
   *
   * **One ground, and it is established rather than assumed.** Every element that renders
   * `hljs-` spans sits on `--sunken`: `SourceExcerpt` and the `pre` in `ui/markdown.tsx`
   * declare `bg-sunken` themselves, and `ResultBox` in `features/review/lookup-result.tsx`
   * declares it for both shapes that reach it. `NumberedCode` has no fill of its own and its
   * only two callers are the first and the third. So the second assertion below is not
   * decoration: it proves `--sunken` is the *tightest* of the four grounds in both themes — the
   * darkest one in light, the lightest one in dark — which is what makes a single ratio here a
   * bound on all four, and what would fail if the elevation ramp were reordered under this
   * test.
   *
   * `--code-comment` moved with the v2 ramp rather than staying where it was: `#8a8a8a`
   * measures 4.08:1 on the dark `--sunken` at `#2d2b29`, so the value that had cleared this bar
   * for two years stopped clearing it when the ground under it moved. That is the whole reason
   * a test measures a pair rather than asserting a token.
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
   * to whoever writes it and wrong for everyone on the other path — and the code palette is the
   * family most likely to be edited one hue at a time.
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
   * And the same claim for everything else in the ramp, which nothing was making.
   *
   * The rule above is the code palette's because that is the family that has historically been
   * edited one hue at a time, but the defect is not a property of code: the two dark blocks are
   * a hundred lines apart and byte-identical, and *any* value corrected in one of them is
   * correct for whichever half of the readership took the other path. v2 doubled the number of
   * tokens with two dark declarations — twelve signals and four grounds where there were three
   * verdicts — so the odds of that edit have gone up rather than down.
   *
   * Whitespace-normalised, and only here: `--shadow-float` is one declaration wrapped across
   * three lines, and the media query's copy is indented two spaces deeper than the attribute
   * block's because it is nested one level deeper. Comparing those raw reports a difference
   * that is the file's own shape. The code rule above compares raw values and is right to, on
   * the narrower claim that a four-hex palette is written one hex to a line.
   */
  it("keeps the two dark blocks saying the same thing", () => {
    const fallback = new Map(scope("darkFallback").map((d) => [d.name, d.value.replace(/\s+/g, " ")]));
    const attribute = new Map(scope("darkAttribute").map((d) => [d.name, d.value.replace(/\s+/g, " ")]));

    const disagreements = [...new Set([...fallback.keys(), ...attribute.keys()])]
      .filter((name) => fallback.get(name) !== attribute.get(name))
      .map((name) => `${name}: ${fallback.get(name) ?? "(absent)"} vs ${attribute.get(name) ?? "(absent)"}`);

    expect(
      disagreements,
      "a reader whose browser never ran the theme script takes the other block",
    ).toEqual([]);

    // A dark override with nothing to override is a token half the product has never seen.
    const light = new Set(scope("light").map((d) => d.name));
    expect(
      [...fallback.keys()].filter((name) => !light.has(name)),
      "a token declared only in dark has no value for a light reader",
    ).toEqual([]);
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
   *         Tightest: `--code-keyword` in dark, 0.266.
   *   0.15  the name against the literal — is this a name or a written-out value?
   *         Tightest: dark, 0.196. It was 0.111 before the literal moved off cyan.
   *   0.09  the name against the keyword — ours or the language's? Tightest: dark, 0.117.
   *         The lowest bar of the three on purpose: this is the one pair the palette does not
   *         carry by colour alone, because `.hljs-keyword` is also the only role set in the
   *         mono's 600 weight, and `styles.css` loads three cuts of IBM Plex Mono of which the
   *         block uses two, so there is no third weight to give a second role even if one were
   *         wanted.
   *
   * A fourth clause holds the arc itself: the three hues span 130° in light and 136° in dark,
   * where they spanned 81° and 96° before the literal moved off cyan, and the bar is 110°. That
   * is the same decision the 0.15 bar above is a consequence of, said in the units it was made
   * in — and it is what catches the light half of that move, which the ΔE bar does not: light
   * was already 0.173 there, comfortably over 0.15, while its hue span was not.
   *
   * **The span is computed on the circle now.** It used to be a plain max-minus-min, which was
   * the right reading only because `keeps code colour off the accent` held every code hue
   * between 170° and 310°. That test is gone — see the one below for why four signals made it
   * unsatisfiable — and with it the guarantee that the three hues do not straddle 0°. The
   * circular reading is the largest gap between neighbours subtracted from 360, which agrees
   * with the old arithmetic on the shipped palette to the digit and does not depend on a rule
   * that no longer exists.
   *
   * `--code-comment` against `--code-lit` is the tightest pair in the set at 0.096 in light,
   * and it has no bar. A docstring and a `#` comment are both prose inside code; reading one as
   * the other costs a reader nothing, and buying distance there would have to come out of a
   * pair that matters. Naming it here is what stops it being an oversight.
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

      // The arc the three are spread across, which is the decision the ΔE bars are the
      // consequence of. Sorted round the wheel, the span is 360 minus the widest gap between
      // neighbours — the complement of the empty arc, which is the reading that survives a
      // palette straddling 0°.
      const hues = ["--code-keyword", "--code-name", "--code-lit"]
        .map((n) => oklch(get(n)).h)
        .sort((a, b) => a - b);
      const gaps = hues.map((hue, i) => (i === 0 ? hue + 360 - hues[hues.length - 1] : hue - hues[i - 1]));
      const span = 360 - Math.max(...gaps);
      expect(span, `${theme}: the three code hues span ${Math.round(span)}°`).toBeGreaterThan(110);
    }
  });

  /**
   * Context isolation: a signal never appears inside a code block, and a code colour never
   * appears outside one.
   *
   * **This replaces a rule that four signals made unsatisfiable, and the collision is measured
   * rather than asserted.** The v1 rule was *a `--code-*` hue stays 35° from the accent*, which
   * was easy while the accent was the only hue on the wheel. Against the four signals two of
   * the three code roles now sit inside that window: `--code-name` at 264.4° is 10.3° from
   * `--mark` in light and 14.0° from it in dark, and `--code-lit` at 172.2° is 18.2° from
   * `--cleared` in light and 15.0° in dark. There is one gap on the wheel wide enough to hold
   * three separated hues — the 137° between `--mark` and `--material` — and putting the whole
   * syntax palette in the violets to satisfy an angle would make Python look like nothing
   * anybody writes it in.
   *
   * So the rule moves from *what value a token holds* to *where it may appear*, which is a
   * stricter question and a cheaper one to answer. Two disjoint contexts mean a hue can be
   * reused across them without ambiguity, for the same reason a road sign and a chart may both
   * use green: nobody reads one in the other's frame. A string inside a `<pre>` is a string
   * whatever green it is, as long as no verdict is ever painted in there beside it.
   *
   * Four assertions, and together they close both halves for anything a stylesheet or a class
   * list can do:
   *
   *  1. Every `var(--code-*)` in the stylesheet sits under an `.hljs-` selector. A custom
   *     property is only paint where a `var()` reads it, so this is the complete list of places
   *     the four values are painted at all.
   *  2. `@theme` maps none of them. That is what stops `text-code-name` existing as a utility —
   *     a token Tailwind never generates a class for cannot be reached from a `className`, so
   *     assertion 1 does not have to be re-proved for every component in the product.
   *  3. No source file writes one. `var(--code-name)` in a `style` attribute or an arbitrary
   *     value like `text-[var(--code-lit)]` is the one route left past assertion 2, and the
   *     atlas proves it is a route this codebase uses: `features/atlas/map.tsx` paints SVG
   *     strokes from `var(--ink-3)` and `var(--rule-strong)` exactly that way.
   *  4. No `.hljs-` rule paints a signal, and no `<pre>` element carries a signal utility on
   *     itself. Those are the two things that decide the colours inside a code block: the
   *     block's own class list, and the four rules that colour the spans `highlight()` emits.
   *
   * **What this cannot see, and where it is covered.** The markup inside a `<pre>` is generated
   * by highlight.js and carries `hljs-` classes only, so there is no third painter to check —
   * but that is a fact about a library rather than something asserted here. jsdom applies no
   * stylesheet either, so nothing in vitest can tell whether a selector list reaches a token on
   * screen; `tests/browser/test_code_colour.py` reads the *resolved* colour of an `hljs-params`
   * span in a real excerpt, in both themes, and that is the half of this rule a browser has to
   * answer.
   */
  it("keeps the code palette inside a code block, and the signals outside one", () => {
    const SIGNAL_VAR = /var\(\s*--(material|held|cleared|mark|accent)\b/;
    const CODE_VAR = /var\(\s*--code-/;

    // 1. Every place a code colour is painted is a code block.
    const painted = blocks().filter((block) => CODE_VAR.test(block.body));
    expect(painted.length, "the code palette is painted somewhere").toBeGreaterThan(0);
    expect(
      painted
        .filter((block) => !block.selector.split(",").every((one) => one.trim().startsWith(".hljs-")))
        .map((block) => block.prelude),
      "a --code-* token painted outside a highlighted span is a syntax colour used as decoration",
    ).toEqual([]);

    // And the mirror: nothing a code block paints is a signal.
    expect(
      blocks()
        .filter((block) => block.selector.includes(".hljs-"))
        .filter((block) => SIGNAL_VAR.test(block.body))
        .map((block) => block.prelude),
      "a verdict hue inside an excerpt grades the code rather than tokenising it",
    ).toEqual([]);

    // 2. No utility can name one, because `@theme` maps none of them.
    expect(
      declarations()
        .filter(({ name }) => /^--color-code-/.test(name))
        .map(({ name }) => name),
      "a --color-code-* mapping mints text-code-name and opens the second route in",
    ).toEqual([]);

    // 3. And no component writes one by hand.
    expect(
      sourceOffenders((text) => CODE_VAR.test(text)),
      "a --code-* token reached from a component is a syntax colour outside a code block",
    ).toEqual([]);

    // 4. No `<pre>` carries a signal. The set of files that draw one is small enough to name,
    //    so a fourth arrives here rather than arriving unmeasured.
    const drawn = sourceFiles().filter((file) => /<pre[\s>]/.test(withoutComments(read(file))));
    expect(drawn.sort(), "a new code block wants its class list read").toEqual([
      "features/review/lookup-result.tsx",
      "ui/code.tsx",
      "ui/markdown.tsx",
    ]);

    const inside: string[] = [];
    for (const file of drawn) {
      const source = withoutComments(read(file));
      for (const match of source.matchAll(/<pre[\s>]/g)) {
        const close = source.indexOf("</pre>", match.index);
        const element = source.slice(match.index, close === -1 ? source.length : close);
        const signal = SIGNAL_CLASS.exec(element);
        if (signal) inside.push(`${file}: <pre …> carries ${signal[0]}`);
      }
    }
    expect(inside, "a signal painted inside a code block is a grade on somebody's source").toEqual(
      [],
    );
  });
});

/** `text-material`, `border-l-held-edge`, `bg-mark-wash`, `decoration-accent-strong`. */
const SIGNAL_CLASS =
  /\b(?:bg|text|border|border-[xylrtbse]{1,2}|ring|from|to|via|decoration|fill|stroke|outline|caret|accent)-(?:material|held|cleared|mark|accent)(?:-[a-z0-9-]+)?\b/;

const SOURCE_ROOT = join(__dirname, "..");

function sourceFiles(directory: string = SOURCE_ROOT, prefix = ""): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.isDirectory()) return sourceFiles(join(directory, entry.name), relative);
    if (!/\.tsx?$/.test(entry.name) || entry.name.includes(".test.")) return [];
    return [relative];
  });
}

const read = (file: string) => readFileSync(join(SOURCE_ROOT, file), "utf8");

/**
 * A source file with its comments blanked out, and its line numbering intact.
 *
 * This codebase argues for its decisions in prose sitting directly above the code that makes
 * them, so the comment explaining why a token was moved contains that token's name, and a guard
 * reading raw lines reports the explanation as the offence. `ui/code.tsx` and `ui/markdown.tsx`
 * both carry paragraphs naming `--mark`; `ui/markdown.tsx` quotes `var(--accent)` in a
 * correction of an older comment. Every one of those is prose about a decision, and none of
 * them paints anything.
 *
 * The same pair of regexes lives in `ui/design-system.test.ts`, whose header carries the
 * argument for why it is two regexes and not a character scanner. Copied rather than shared
 * because this project has no module for test helpers and inventing one to hold ten lines would
 * put a build-order dependency between two files that currently have none.
 */
function withoutComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (block) => block.replace(/[^\n]/g, " "))
    .replace(/(?<!:)\/\/[^\n]*/g, (line) => " ".repeat(line.length));
}

function sourceOffenders(matches: (text: string) => boolean): string[] {
  return sourceFiles().flatMap((file) => {
    const raw = read(file).split("\n");
    return withoutComments(read(file))
      .split("\n")
      .map((text, index) => ({ line: index + 1, text }))
      .filter((entry) => matches(entry.text))
      .map((entry) => `${file}:${entry.line} — ${raw[entry.line - 1].trim()}`);
  });
}
