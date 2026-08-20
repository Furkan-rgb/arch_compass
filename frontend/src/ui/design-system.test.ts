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
  it("has no accent hue to reach for", () => {
    // The tokens are deleted rather than deprecated, which means a leftover `text-accent`
    // compiles to nothing at all and disappears in review. This is what notices.
    expect(
      offenders(/\b(?:bg|text|border|ring|from|to|via|decoration)-accent\b/),
      "chrome is ink in this system — see docs/design-system.md",
    ).toEqual([]);
  });

  /**
   * The serif is the model's voice and only the model's voice.
   *
   * This is the whole thesis of the system: a reader can tell who is speaking without
   * reading a word, because the machine is in mono, the model is in the serif and a person
   * acts in the sans. Spending `font-read` on a heading somewhere would cost exactly that,
   * and would cost it one reasonable-looking commit at a time.
   */
  it("keeps the serif on the model's voice", () => {
    const allowed = new Set([
      "features/review/finding-detail.tsx",
      "features/review/surfaces.tsx",
      "features/review/clarification.tsx",
    ]);
    expect(
      offenders(/\bfont-read\b/, allowed),
      "the serif sets what the model concluded, never a label or a heading",
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

  it("keeps a shadow for something that actually floats", () => {
    // A panel has a rule. `shadow-float` and `shadow-hero` are for a drawer and for the
    // landing hero, which are the only two things on screen that leave the page.
    const allowed = new Set([
      "ui/drawer.tsx",
      "features/landing/landing-page.tsx",
      "features/landing/preview.tsx",
    ]);
    expect(
      offenders(/\bshadow-(?:float|hero|panel|sm|md|lg|xl)\b/, allowed),
      "structure is separated by a rule, not lifted off the page",
    ).toEqual([]);
  });
});
