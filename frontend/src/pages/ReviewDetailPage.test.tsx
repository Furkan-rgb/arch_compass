/**
 * An answer is markdown, and the parts of it that matter most are the ones plain text
 * destroys: a fenced code block, inline code, a list.
 *
 * The streaming case gets its own test because it is the one that is not obviously fine — a
 * fence that has been opened and not yet closed is the normal state of an answer half way
 * through arriving, and rendering it as a wall of prose that then rearranges itself into a
 * code block would be worse than waiting.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AnswerProse, Overview } from "./ReviewDetailPage";
import type { OpenQuestion } from "../types";

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
 * The questions a review hands back (master plan §6C).
 *
 * They are the one part of the conclusion that asks the reader for something, so what is
 * defended here is that they arrive with everything needed to act on them — which verdicts
 * move, and where an answer goes — and that a review with nothing open shows no section at
 * all rather than an empty heading inviting a reader to look for something that is not there.
 */
describe("Overview open questions", () => {
  const base = {
    situation: "One operator, one server.",
    themes: [],
    recommended_sequence: [],
    limits: "A static count cannot see runtime registration.",
  };

  it("asks the question, names the verdicts it settles, and says where the answer goes", () => {
    render(
      <Overview
        overview={{
          ...base,
          open_questions: [
            {
              reference: "Q-1",
              unknown: "The case does not say whether a second vendor is contracted.",
              why_it_matters: "Two verdicts move on this.",
              question: "Is a second speech vendor actually contracted?",
              answer_belongs_in: "expected_future_changes",
              supporting_references: ["BR-001", "BR-003"],
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("What the case does not say")).toBeTruthy();
    expect(screen.getByText("Is a second speech vendor actually contracted?")).toBeTruthy();
    expect(screen.getByText("Q-1")).toBeTruthy();
    expect(screen.getByText("expected_future_changes")).toBeTruthy();
    // The citations are links to the boundaries, so a reader who doubts the question can
    // reach the verdicts that raised it.
    expect(screen.getByText("BR-001")).toBeTruthy();
    expect(screen.getByText("BR-003")).toBeTruthy();
  });

  it("shows no section when the case settled everything the verdicts turned on", () => {
    render(<Overview overview={{ ...base, open_questions: [] }} />);

    expect(screen.queryByText("What the case does not say")).toBeNull();
    // The rest of the conclusion is still there: nothing open is a result, not an absence.
    expect(screen.getByText("One operator, one server.")).toBeTruthy();
  });
});

describe("Overview answer path", () => {
  // Annotated rather than inferred: `answer_belongs_in` is a closed set, and a bare object
  // literal widens it to `string`. The compiler refusing that is the frontend half of the
  // rule that the destination is chosen from an enum and never named freely (§12.0).
  const question: OpenQuestion = {
    reference: "Q-1",
    unknown: "The case does not say whether a second vendor is contracted.",
    why_it_matters: "Two verdicts move on this.",
    question: "Is a second speech vendor actually contracted?",
    answer_belongs_in: "expected_future_changes",
    supporting_references: ["BR-001"],
  };
  const base = {
    situation: "One operator, one server.",
    themes: [],
    recommended_sequence: [],
    limits: "A static count cannot see runtime registration.",
    open_questions: [question],
  };

  it("hands the reader to the case editor rather than writing the answer itself", () => {
    const opened = vi.fn();
    render(<Overview overview={base} onAnswer={opened} />);

    fireEvent.click(screen.getByRole("button", { name: "Answer it in the case" }));

    // What the advisor supplies is the question; the revision is the user's own (§6C.4).
    expect(opened).toHaveBeenCalledTimes(1);
  });

  it("offers no answer button where the loop cannot be walked", () => {
    // No repository indexed means revising cannot run a new review, and a button that
    // fails is worse than none.
    render(<Overview overview={base} onAnswer={null} />);

    expect(screen.queryByRole("button", { name: "Answer it in the case" })).toBeNull();
    expect(screen.getByText("Is a second speech vendor actually contracted?")).toBeTruthy();
  });
});
