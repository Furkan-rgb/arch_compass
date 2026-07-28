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
 * The conclusion renders itself and delegates the questions.
 *
 * Overview holds no case, no mutation and no run, so it cannot offer an answer box — and
 * the questions need all three. What is defended here is only the seam: questions reach the
 * surface that can act on them, and a review with nothing open shows no section at all
 * rather than an empty heading inviting a reader to look for something not there.
 */
describe("Overview open questions", () => {
  const base = {
    situation: "One operator, one server.",
    themes: [],
    recommended_sequence: [],
    limits: "A static count cannot see runtime registration.",
  };

  const question: OpenQuestion = {
    reference: "Q-1",
    unknown: "The case does not say whether a second vendor is contracted.",
    why_it_matters: "Two verdicts move on this.",
    question: "Is a second speech vendor actually contracted?",
    answer_belongs_in: "expected_future_changes",
    supporting_references: ["BR-001", "BR-003"],
  };

  it("hands its questions to the surface that can answer them", () => {
    const seen: OpenQuestion[][] = [];

    render(
      <Overview
        overview={{ ...base, open_questions: [question] }}
        answering={(questions) => {
          seen.push(questions);
          return <p>answer surface</p>;
        }}
      />,
    );

    expect(seen).toEqual([[question]]);
    expect(screen.getByText("answer surface")).toBeTruthy();
    // The conclusion itself is still there: the questions are an addition, not a takeover.
    expect(screen.getByText("One operator, one server.")).toBeTruthy();
  });

  it("asks for nothing when the case settled everything the verdicts turned on", () => {
    const seen: OpenQuestion[][] = [];

    render(
      <Overview
        overview={{ ...base, open_questions: [] }}
        answering={(questions) => {
          seen.push(questions);
          return <p>answer surface</p>;
        }}
      />,
    );

    expect(seen).toEqual([]);
    expect(screen.queryByText("answer surface")).toBeNull();
    expect(screen.getByText("One operator, one server.")).toBeTruthy();
  });
});
