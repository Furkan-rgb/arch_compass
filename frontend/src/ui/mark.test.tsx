import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { MarkShape } from "../lib/format";
import { Mark } from "./mark";

/**
 * The four registers a mark is chosen from, and the separation `ui/mark.tsx` calls
 * load-bearing rather than decorative.
 *
 * That word was doing no work. The whole of the register system is a `Record<MarkShape,
 * LucideIcon>` — sixteen lines, four comment headings, and nothing anywhere that could tell a
 * tick from a flag. Point `flag` at `CircleCheck` and every test in the product stays green
 * while an accepted finding starts wearing the mark the model uses for *cleared*: "I have
 * committed to act on this" drawn as "assessed and found unproblematic". That is the charter's
 * one separation — the model's verdict against the person's decision — deleted in a character,
 * silently, in the file whose comment says it may never happen.
 *
 * The same hole covers the other three claims that comment makes. A required policy may never
 * wear the caution triangle, because a policy is emphasis and not alarm. A delta may never
 * borrow a verdict's sign, because arriving, leaving and being judged differently are
 * comparisons and none of them says whether the candidate is any good — the tick `addressed`
 * used to carry was exactly that mistake, and it survived the last guard because the guard
 * looked at one Unicode block.
 *
 * So the property is stated as disjointness and asserted over the whole vocabulary: four
 * registers, no icon shared by two of them. That is stronger than the three named prohibitions
 * and it needs no maintenance, because it fails on any pair rather than on the pairs somebody
 * thought of.
 */

/** Which register each shape belongs to. */
type Register = "sign" | "step" | "decision" | "delta";

/**
 * The vocabulary, filed. This is a `Record<MarkShape, …>` on purpose: a seventeenth shape
 * added to `lib/format.ts` fails `tsc -b` here until somebody has decided which of the four
 * registers it belongs to, which is the decision `ui/mark.tsx` says is the part a library
 * cannot supply.
 */
const REGISTER: Record<MarkShape, Register> = {
  // What is being graded: the model's verdict, and a review's own state.
  alert: "sign",
  pause: "sign",
  check: "sign",
  failed: "sign",
  running: "sign",
  stopped: "sign",
  // A position on a scale that is not a grade — how binding a policy is, how far an atlas is
  // from the code on disk.
  solid: "step",
  hollow: "step",
  dashed: "step",
  // What a person decided.
  flag: "decision",
  clock: "decision",
  slash: "decision",
  // How a candidate moved between two revisions.
  plus: "delta",
  minus: "delta",
  swap: "delta",
  equals: "delta",
};

const SHAPES = Object.keys(REGISTER) as MarkShape[];

/**
 * Which icon a shape is actually drawn with, read off what Lucide rendered rather than off the
 * table that chose it.
 *
 * Lucide stamps every icon with its own name — `class="lucide lucide-circle-check …"` — so
 * the identity is in the document and the test never has to import the table it is checking.
 * The bare `lucide` cannot match: the pattern requires the hyphen and a name after it.
 */
function icon(shape: MarkShape): string {
  const { container } = render(<Mark shape={shape} />);
  const svg = container.querySelector("svg");
  expect(svg, `<Mark shape="${shape}"> drew no icon at all`).not.toBeNull();
  const found = /(?:^|\s)lucide-([a-z0-9-]+)(?:\s|$)/.exec(svg!.getAttribute("class") ?? "");
  expect(
    found,
    `cannot read an icon name off "${svg!.getAttribute("class")}" — if Lucide stopped ` +
      "stamping one, compare the drawn geometry instead",
  ).not.toBeNull();
  return found![1];
}

describe("the marks", () => {
  /**
   * The separation, as the one property that implies all three of the named prohibitions: no
   * icon is worn by two registers.
   *
   * Break it by pointing `flag` at `CircleCheck`, `solid` at `TriangleAlert`, or `equals` at
   * `CircleCheck` — the three the comment in `ui/mark.tsx` argues against by name, and the
   * three nothing could see.
   */
  it("never lends an icon from one register to another", () => {
    const drawn = new Map<string, { shape: MarkShape; register: Register }[]>();
    for (const shape of SHAPES) {
      const name = icon(shape);
      drawn.set(name, [...(drawn.get(name) ?? []), { shape, register: REGISTER[shape] }]);
    }

    // Every shape resolved to something, and no two shapes share an icon at all — which is the
    // stricter half and true today: sixteen shapes, sixteen icons. Stated separately from the
    // register rule because it is a different claim: two *signs* wearing one icon would be a
    // legible mistake, and two registers sharing one is a lie about what the mark means.
    expect(drawn.size, "two shapes are drawn with the same icon").toBe(SHAPES.length);

    const shared = [...drawn.entries()]
      .filter(([, worn]) => new Set(worn.map((entry) => entry.register)).size > 1)
      .map(
        ([name, worn]) =>
          `${name} is worn by ${worn.map((e) => `${e.shape} (${e.register})`).join(" and ")}`,
      );
    expect(
      shared,
      "a mark that crosses registers says the wrong kind of thing about what it marks",
    ).toEqual([]);
  });

  /**
   * The three prohibitions the comment states in words, asserted in the words it states them
   * in — so a failure names the rule that was broken rather than a pair of icon names.
   *
   * These are consequences of the test above and they are here anyway. The disjointness rule
   * catches the mutation; this one explains it, which is what somebody reading a red suite at
   * 2am actually needs.
   */
  it("keeps a person's decision, a policy's strength and a delta off the verdict's signs", () => {
    const tick = icon("check");
    const caution = icon("alert");
    const waiting = icon("pause");
    const verdictSigns = new Set([tick, caution, waiting]);

    for (const shape of SHAPES.filter((s) => REGISTER[s] === "decision")) {
      expect(
        icon(shape),
        `accepting a finding is a commitment to act on it, not a report that it went away — ` +
          `"${shape}" may not wear the verdict's tick`,
      ).not.toBe(tick);
    }
    for (const shape of SHAPES.filter((s) => REGISTER[s] === "step")) {
      expect(
        icon(shape),
        `a required policy is the one to read first, not an alarm — "${shape}" may not wear ` +
          "the caution triangle",
      ).not.toBe(caution);
    }
    for (const shape of SHAPES.filter((s) => REGISTER[s] === "delta")) {
      expect(
        verdictSigns.has(icon(shape)),
        `a delta is a comparison and says nothing about whether a candidate is any good — ` +
          `"${shape}" may not borrow a verdict's sign`,
      ).toBe(false);
    }
  });

  /**
   * Every mark is out of the accessibility tree and out of the tab order, because in all of
   * these places the descriptor's own word sits right beside it: announcing the mark would say
   * everything twice, and stopping on it would cost a tab press for nothing.
   *
   * **The two halves are guarding two different things and it is worth saying which.** Delete
   * `focusable="false"` from `Mark` and this fails — that attribute is the component's own, and
   * it is there because an inline `<svg>` is a tab stop in some engines whatever `aria-hidden`
   * says. Delete `aria-hidden="true"` and this **passes**, because Lucide stamps `aria-hidden`
   * on every icon it renders and the prop is only restating it. That assertion is therefore a
   * guard against the library rather than against this file: it fails the day an upgrade stops
   * doing it, or the day a call site spreads an `aria-hidden={false}` through `...props`. Both
   * are worth failing on; neither is what the comment in `ui/mark.tsx` claims to be holding, and
   * a test that let a reader think otherwise would be the defect this file is a repair for.
   */
  it("announces nothing, because the word is already beside it", () => {
    for (const shape of SHAPES) {
      const { container } = render(<Mark shape={shape} />);
      const svg = container.querySelector("svg")!;
      expect(svg.getAttribute("aria-hidden"), `<Mark shape="${shape}"> is announced`).toBe("true");
      expect(svg.getAttribute("focusable"), `<Mark shape="${shape}"> is a tab stop`).toBe("false");
    }
  });
});
