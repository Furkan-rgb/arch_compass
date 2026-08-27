import { describe, expect, it } from "vitest";

import { buttonClass, type ButtonVariant } from "./button";

/**
 * What a size is worth once a variant has been merged on top of it.
 *
 * `buttonClass` composes two records through tailwind-merge, and the order decides which wins
 * where they collide. It used to be the variant last; it is now the size first, so that a
 * variant may refuse a size's padding — which is the whole of how `link` gets its `px-0`.
 *
 * That reorder is a change to every button in the product on the strength of one claim: no
 * other variant names a class in any group a size names. The claim is true by reading, and it
 * is the kind that breaks silently — the next variant that writes `text-xs` into the registry
 * now wins over the size, where before it lost. So it is asserted rather than read, in the
 * units a reader thinks in: a `md` button is 44 pixels tall with 14 pixels of side padding at
 * the control size, whatever it is wearing.
 */
const RECIPES: ButtonVariant[] = ["primary", "secondary", "ghost", "quiet", "danger"];

describe("a button's geometry", () => {
  it("keeps its size whatever variant is merged on top of it", () => {
    for (const variant of RECIPES) {
      const md = buttonClass(variant, "md");
      expect(md, variant).toContain("min-h-11");
      expect(md, variant).toContain("gap-2");
      expect(md, variant).toContain("px-3.5");
      expect(md, variant).toContain("text-sm");

      const sm = buttonClass(variant, "sm");
      expect(sm, variant).toContain("min-h-8");
      expect(sm, variant).toContain("pointer-coarse:min-h-11");
      expect(sm, variant).toContain("px-2.5");
      expect(sm, variant).toContain("text-xs");

      const lg = buttonClass(variant, "lg");
      expect(lg, variant).toContain("min-h-12");
      expect(lg, variant).toContain("px-5");
      expect(lg, variant).toContain("text-[15px]");
    }
  });

  /**
   * And the variant still wins where it is meant to. `primary` sets a text *colour* and `md`
   * sets a font *size*, which are two tailwind-merge groups wearing one prefix — the one place
   * the reorder could plausibly have cost something, and the reason both are asserted here.
   */
  it("lets a variant keep its colour beside a size's font size", () => {
    const primary = buttonClass("primary", "md");
    expect(primary).toContain("text-accent-on-fill");
    expect(primary).toContain("text-sm");
    expect(buttonClass("secondary", "lg")).toContain("text-ink");
    expect(buttonClass("secondary", "lg")).toContain("text-[15px]");
  });

  /**
   * The one variant that refuses a size, and the reason the order is what it is. A way out of
   * a row is a line of underlined words rather than a box, so the words are the target and a
   * size's side padding would draw the box back around them. The height is not refused: 44px
   * is a touch requirement and does not depend on how a control is drawn.
   */
  it("lets a link refuse the padding and keep the touch box", () => {
    const link = buttonClass("link", "md");
    expect(link).toContain("px-0");
    expect(link).not.toContain("px-3.5");
    expect(link).toContain("min-h-11");
    expect(link).toContain("underline");
    // No fill and no edge to pick the box up by, which is what separates it from `secondary`.
    // Matched unprefixed, because the base recipe carries `disabled:bg-control` and
    // `aria-disabled:border-rule-control` on every button in the product — a substring test
    // here reads those as the resting state and fails on all six variants.
    expect(link).not.toMatch(/(?:^|\s)bg-control\b/);
    expect(link).not.toMatch(/(?:^|\s)border-rule-control\b/);

    const small = buttonClass("link", "sm");
    expect(small).toContain("px-0");
    expect(small).not.toContain("px-2.5");
    expect(small).toContain("pointer-coarse:min-h-11");
  });
});
