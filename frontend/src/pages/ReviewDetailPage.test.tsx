/**
 * An answer is markdown, and the parts of it that matter most are the ones plain text
 * destroys: a fenced code block, inline code, a list.
 *
 * The streaming case gets its own test because it is the one that is not obviously fine — a
 * fence that has been opened and not yet closed is the normal state of an answer half way
 * through arriving, and rendering it as a wall of prose that then rearranges itself into a
 * code block would be worse than waiting.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Overview, answersBehind, verdictChanges } from "./ReviewDetailPage";
import { AnswerProse } from "../markdown";
import type { OpenQuestion, RecordedAnswer, ReviewedBoundary } from "../types";

describe("AnswerProse", () => {
  it("renders a fenced block as code, keeping its line breaks", () => {
    const answer = [
      "Import it from the one module that owns it:",
      "",
      "```python",
      "# In preflight/voices.py",
      "from provider.qwen import BUILT_IN_VOICES",
      "```",
    ].join("\n");

    const { container } = render(<AnswerProse text={answer} />);

    const block = container.querySelector("pre code");
    expect(block).not.toBeNull();
    expect(block?.textContent).toContain("from provider.qwen import BUILT_IN_VOICES");
    // Two lines, not one: a code block that lost its newlines is not a code block.
    expect(block?.textContent?.trimEnd().split("\n")).toHaveLength(2);
    // The language survives as a class, so highlighting can be added without touching this.
    expect(block?.className).toContain("language-python");
  });

  it("renders inline code, emphasis and lists as themselves", () => {
    const { container } = render(
      <AnswerProse
        text={"**Do this first.** Give `BUILT_IN_VOICES` one owner:\n\n- move it\n- import it"}
      />,
    );

    expect(container.querySelector("strong")?.textContent).toBe("Do this first.");
    expect(container.querySelector("code")?.textContent).toBe("BUILT_IN_VOICES");
    expect(container.querySelectorAll("li")).toHaveLength(2);
  });

  it("renders a fence that has not been closed yet as code", () => {
    // What a streamed answer looks like part way through: the block is open and the closing
    // fence has not arrived. It has to read as code from the first line, not become code
    // later once the answer finishes.
    const partial = "As it would look:\n\n```python\nfrom provider.qwen import BUILT_IN";

    const { container } = render(<AnswerProse text={partial} />);

    expect(container.querySelector("pre code")?.textContent).toContain(
      "from provider.qwen import BUILT_IN",
    );
  });

  it("colours a block that named its language", () => {
    const { container } = render(
      <AnswerProse
        text={
          '```python\nfrom provider.qwen import BUILT_IN_VOICES\n\nVOICE = "alloy"  # one owner\n```'
        }
      />,
    );

    // The tokens are what the stylesheet colours; without them a block is monochrome.
    expect(container.querySelectorAll("pre code .token.keyword").length).toBeGreaterThan(0);
    expect(container.querySelectorAll("pre code .token.string").length).toBeGreaterThan(0);
    expect(container.querySelectorAll("pre code .token.comment").length).toBeGreaterThan(0);
    expect(container.querySelector("pre code")?.className).toContain("language-python");
  });

  it("leaves a block that named no language, or an unknown one, uncoloured", () => {
    // Guessing is worse than plain text: a short snippet is ambiguous between half the
    // grammars carried, and a wrong guess colours the wrong words with total confidence.
    const bare = render(<AnswerProse text={"```\nsome plain text\n```"} />);
    expect(bare.container.querySelectorAll("pre code .token")).toHaveLength(0);

    // And a fence naming something not carried renders as plain code rather than throwing.
    const unknown = render(<AnswerProse text={"```brainfuck\n+++.\n```"} />);
    expect(unknown.container.querySelectorAll("pre code .token")).toHaveLength(0);
    expect(unknown.container.querySelector("pre code")?.textContent).toContain("+++.");
  });

  it("escapes markup rather than rendering it", () => {
    // Answers are model-authored text. `rehype-raw` is deliberately not installed, so HTML
    // in an answer is shown as the characters it is.
    const { container } = render(
      <AnswerProse text={'Avoid <img src=x onerror="alert(1)"> in the docstring.'} />,
    );

    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText(/onerror/)).toBeTruthy();
  });
});

/**
 * The conclusion is a conclusion, and asks for nothing.
 *
 * It used to carry the questions too, on the reasoning that a review should show its value
 * before naming its price. Measurement overturned that: on the bundled example four of five
 * first-pass verdicts moved once the questions were answered, so the "value" the questions
 * were placed after was mostly wrong. Asking now happens on its own surface, before any
 * conclusion exists — and a review that has concluded has, by construction, nothing to ask.
 */
describe("Overview", () => {
  const base = {
    situation: "One operator, one server.",
    themes: [],
    recommended_sequence: [],
    limits: "A static count cannot see runtime registration.",
  };

  it("renders the bottom line and what the review could not see", () => {
    render(<Overview overview={base} />);

    expect(screen.getByText("One operator, one server.")).toBeTruthy();
    expect(screen.getByText(/static count cannot see runtime registration/)).toBeTruthy();
  });

  it("has no answer surface, because a concluded review is not still asking", () => {
    // Structural rather than cosmetic: the summarising stage has no field for a question,
    // so a conclusion carrying one could only have come from somewhere it should not.
    render(<Overview overview={base} />);

    expect(screen.queryByText("What it needs to know")).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
  });
});

/**
 * What the reader's own answers changed, read off the two stored passes.
 *
 * The one place the product's central claim is checkable rather than asserted — and it costs
 * no model call, because both passes are stored and the only difference between them is what
 * the case says. Matching by reference is safe because detection is deterministic: the same
 * atlas gives the same boundary the same `BR-nnn` in both passes.
 */
describe("verdictChanges", () => {
  const boundary = (reference: string, name: string, material: boolean): ReviewedBoundary => ({
    reference,
    candidate: {
      pattern: "sole_implementation",
      summary: `package.${name} is implemented only by package.${name}Adapter.`,
      participants: [
        {
          node_id: name.toLowerCase(),
          qualified_name: `package.${name}`,
          role: "Declares the abstraction.",
        },
      ],
      limitations: "A static count cannot see runtime registration.",
    },
    material,
    rationale: "Argued from the case.",
    verdict_label: material ? "Not earning its place" : "Earning its place",
  });

  it("reports only the verdicts that actually moved, and which way", () => {
    const before = [
      boundary("BR-001", "Feed", true),
      boundary("BR-002", "Ledger", false),
      boundary("BR-003", "Digest", false),
    ];
    const after = [
      boundary("BR-001", "Feed", false),
      boundary("BR-002", "Ledger", false),
      boundary("BR-003", "Digest", true),
    ];

    expect(verdictChanges(before, after)).toEqual([
      { reference: "BR-001", title: "package.Feed", from: true, to: false },
      { reference: "BR-003", title: "package.Digest", from: false, to: true },
    ]);
  });

  it("reports no change as no change rather than as nothing to say", () => {
    const same = [boundary("BR-001", "Feed", false)];

    // A round that moved nothing is a result: those verdicts never rested on what the
    // reader was asked about. The caller says so; this returns the empty list honestly.
    expect(verdictChanges(same, same)).toEqual([]);
  });

  it("ignores a boundary the earlier pass never judged", () => {
    // Cannot happen while the atlas is pinned, and is still not guessed at: a boundary with
    // nothing to compare against has not "changed", and claiming it had would be inventing
    // a movement out of an absence.
    expect(verdictChanges([], [boundary("BR-001", "Feed", true)])).toEqual([]);
  });
});

/**
 * Which of the reader's own sentences moved a verdict.
 *
 * The join exists on both sides already — a question names the boundaries it would settle,
 * and the answered revision names the questions it answered — so this reads a record rather
 * than inferring a cause. It is the reason that record was worth storing: without it a
 * second pass can say four verdicts moved and cannot say which sentence moved any of them.
 */
describe("answersBehind", () => {
  const question = (reference: string, cites: string[]): OpenQuestion => ({
    reference,
    what_the_review_saw: "Two modules wrap one supplier.",
    unknown: `whether ${reference} matters`,
    why_it_matters: "A verdict moves.",
    question: `Is ${reference} settled?`,
    answer_belongs_in: "expected_future_changes",
    supporting_references: cites,
  });

  const recorded = (reference: string, text: string): RecordedAnswer => ({
    question_reference: reference,
    answer_belongs_in: "expected_future_changes",
    recorded_text: text,
  });

  it("names the answer to a question that cited the boundary", () => {
    const behind = answersBehind(
      "BR-001",
      [question("Q-1", ["BR-001", "BR-005"]), question("Q-2", ["BR-003"])],
      [recorded("Q-1", "A second warehouse arrives next quarter.")],
    );

    expect(behind).toEqual([
      {
        question: "Is Q-1 settled?",
        recordedText: "A second warehouse arrives next quarter.",
      },
    ]);
  });

  it("says nothing where the question that cited it was skipped", () => {
    // A verdict can move because a question about a different boundary changed what the
    // case says overall. Claiming a cause there would be inventing one.
    expect(
      answersBehind("BR-001", [question("Q-1", ["BR-001"])], [recorded("Q-2", "Elsewhere.")]),
    ).toEqual([]);
  });

  it("names every answer where more than one question settled the same boundary", () => {
    const behind = answersBehind(
      "BR-001",
      [question("Q-1", ["BR-001"]), question("Q-2", ["BR-001"])],
      [recorded("Q-1", "First."), recorded("Q-2", "Second.")],
    );

    expect(behind.map((item) => item.recordedText)).toEqual(["First.", "Second."]);
  });
});
