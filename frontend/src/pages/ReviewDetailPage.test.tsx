/**
 * An answer is markdown, and the parts of it that matter most are the ones plain text
 * destroys: a fenced code block, inline code, a list.
 *
 * The streaming case gets its own test because it is the one that is not obviously fine — a
 * fence that has been opened and not yet closed is the normal state of an answer half way
 * through arriving, and rendering it as a wall of prose that then rearranges itself into a
 * code block would be worse than waiting.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";

import { api, ApiError } from "../api";
import { RunProvider } from "../run";
import {
  AskAction,
  ExportAction,
  Overview,
  ReviewDetailPage,
  ReviewUnavailable,
  answersBehind,
  chainAround,
  findingForNode,
  verdictChanges,
} from "./ReviewDetailPage";
import { AnswerProse } from "../markdown";
import type {
  BoundaryReviewSummary,
  OpenQuestion,
  RecordedAnswer,
  ReviewDetail,
  ReviewStatus,
  ReviewedBoundary,
} from "../types";

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
 * The way into the question panel, which is only open on a review that can answer.
 *
 * The rule is the backend's and this only mirrors it: `ReviewConversationService._load`
 * admits `succeeded` and refuses everything else for a conversation about a whole review.
 * A looser gate here would put the reader in front of a 404 they did nothing to earn; a
 * stricter one would hide a surface the workspace would have served.
 *
 * The button stays on screen in every refused state. Dropping it would mean a reader who
 * only ever opens running or held reviews never learns the feature exists.
 */
describe("AskAction", () => {
  const openFor = (status: ReviewStatus) => {
    const toggle = vi.fn();
    // Scoped to its own container rather than the document, so a case that mounts the
    // control more than once still asks about the one it just rendered.
    const { container } = render(
      <TooltipProvider>
        <AskAction status={status} expanded={false} onToggle={toggle} />
      </TooltipProvider>,
    );
    return {
      toggle,
      button: within(container).getByRole("button", { name: /Ask about this review/ }),
    };
  };

  it("refuses a running review, and says it is the run and not a fault", async () => {
    const { toggle, button } = openFor("running");

    expect(button).toHaveProperty("disabled", true);
    fireEvent.click(button);
    expect(toggle).not.toHaveBeenCalled();

    // A disabled button dispatches no pointer events, so the reason hangs off the span
    // above it. Hovering that is the whole reason the wrapper exists.
    fireEvent.focus(button.parentElement!);
    await waitFor(() =>
      expect(screen.getByText(/still running — ask once the verdicts are in/)).toBeTruthy(),
    );
  });

  it("refuses a held review, and points at the questions rather than only saying no", async () => {
    // Held is refused for a different reason than running: the report exists, and its
    // verdicts are the ones the run said it could not settle. A conversation about one of
    // those open questions is a different request and stays allowed, so the copy sends the
    // reader there instead of leaving them with a dead control.
    const { toggle, button } = openFor("awaiting_answers");

    expect(button).toHaveProperty("disabled", true);
    fireEvent.click(button);
    expect(toggle).not.toHaveBeenCalled();

    fireEvent.focus(button.parentElement!);
    await waitFor(() => expect(screen.getByText(/Answer the open questions/)).toBeTruthy());
  });

  it("opens on a review that concluded, with nothing in the way", () => {
    const { toggle, button } = openFor("succeeded");

    expect(button).toHaveProperty("disabled", false);
    // No tooltip wrapper on the happy path: the button is its own affordance, and the
    // browser test reaches it by role and name.
    expect(button.parentElement?.tagName).not.toBe("SPAN");
    fireEvent.click(button);
    expect(toggle).toHaveBeenCalledTimes(1);
  });

  it("refuses a review that reached no verdicts at all", () => {
    // Failed and cancelled reach the `Unfinished` page before this renders, so this is
    // about the helper being total rather than about a screen anyone sees.
    for (const status of ["failed", "cancelled"] as ReviewStatus[]) {
      const { button } = openFor(status);
      expect(button).toHaveProperty("disabled", true);
    }
  });
});

/**
 * Taking the review away, as the file the workspace already wrote.
 *
 * A link and not a button, which is the whole of what makes it work: the browser saves what
 * the server marks as an attachment, so there is no body read here and nothing for the test
 * to stub. What is worth defending is that it points at the review it is on, and that it is
 * not on screen at all before there is a document behind it.
 */
describe("ExportAction", () => {
  it("links to the review's own report once one has been written", () => {
    render(<ExportAction reviewId="rev_abc" available />);

    const link = screen.getByRole("link", { name: /Export Markdown/ });
    expect(link).toHaveAttribute("href", "/api/reviews/rev_abc/report");
    // Without this a refusal navigates the reader off their review onto a page of JSON.
    expect(link).toHaveAttribute("download");
  });

  it("is absent while the review has no report to hand over", () => {
    // A run still going has nothing to export, and a greyed control explaining that would
    // be one more thing on a page that is already waiting.
    render(<ExportAction reviewId="rev_abc" available={false} />);

    expect(screen.queryByRole("link", { name: /Export/ })).toBeNull();
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
 *
 * `recorded_text` is the answer as the reader typed it. While answers were composed into case
 * lines it was that composition, so this section printed the question and then most of it
 * again underneath; the pair is stored now, and what is quoted is a person's own reply.
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

/**
 * The map's way back to the finding, which is the other half of a link the ledger already had.
 *
 * A finding could show its boundary on the map and the map could not name the finding, so a
 * reader who followed the first link had nothing to follow home. The reference is what the
 * ledger files a row under, so resolving to it is all the callback needs: the row's DOM id is
 * that reference, and the tab it lives in is force-mounted.
 */
describe("findingForNode", () => {
  const reviewed = [
    {
      reference: "BR-001",
      material: true,
      candidate: {
        participants: [
          { node_id: "clock", qualified_name: "ports.Clock" },
          { node_id: "system_clock", qualified_name: "adapters.SystemClock" },
        ],
      },
    },
    {
      reference: "BR-002",
      material: false,
      candidate: {
        participants: [{ node_id: "store", qualified_name: "ports.Store" }],
      },
    },
  ] as unknown as ReviewedBoundary[];

  it("names the finding a judged boundary belongs to", () => {
    expect(findingForNode("clock", reviewed)).toBe("BR-001");
    expect(findingForNode("store", reviewed)).toBe("BR-002");
  });

  it("names it from the implementation behind it too", () => {
    // Both participants are drawn, and a reader who selected either is asking about the same
    // finding — the boundary and the single class behind it are its two halves.
    expect(findingForNode("system_clock", reviewed)).toBe("BR-001");
  });

  it("names nothing for the neighbourhood, which no finding is about", () => {
    // Most of the map is what reaches these boundaries. Answering with a reference there would
    // send the reader to a row about something else.
    expect(findingForNode("adapters.Report", reviewed)).toBeNull();
    expect(findingForNode("clock", [])).toBeNull();
  });
});

/**
 * A review can go while someone is reading it — deleting one from the reviews list in another
 * tab is the ordinary way that happens — and what this page did then was a red strip on an
 * empty canvas with no link anywhere on it. The reader was left with the back button.
 *
 * The two cases are asserted separately because their recoveries are opposites: a deleted
 * review is settled and must not offer a retry that can only fetch the same absence, while
 * anything else might be the network and must.
 */
describe("ReviewUnavailable", () => {
  const shown = (error: unknown, onRetry?: () => void) =>
    render(
      <MemoryRouter initialEntries={["/reviews/rev-1"]}>
        <ReviewUnavailable reviewId="rev-1" error={error} onRetry={onRetry} />
      </MemoryRouter>,
    );

  it("routes a deleted review back to the list instead of stranding the reader", () => {
    shown(new ApiError("No review with that id.", 404, "not_found"), () => {});

    // The header states the record's name, which for a page whose record has gone is the
    // fact that it has gone. It is a breadcrumb rather than a heading — see `PageHeader`.
    expect(screen.getByText("This review is no longer here")).toBeVisible();
    // Two ways on: the breadcrumb the header carries, and the link in the sentence below it.
    const back = screen.getAllByRole("link", { name: /reviews/i });
    expect(back.length).toBeGreaterThanOrEqual(2);
    for (const link of back) expect(link).toHaveAttribute("href", "/reviews");
    // The server's own words are still the strip, honestly framed and not paraphrased.
    expect(screen.getByRole("alert")).toHaveTextContent("No review with that id.");
  });

  it("offers no retry for a review that has been deleted", () => {
    // Asking again asks for the same nothing. A control that cannot change its own outcome
    // is worse than no control.
    shown(new ApiError("No review with that id.", 404, "not_found"), () => {});

    expect(screen.queryByRole("button")).toBeNull();
  });

  it("offers the read again where the failure might not be settled", () => {
    const onRetry = vi.fn();
    shown(new ApiError("The workspace could not read that review.", 500), onRetry);

    expect(screen.getByText("This review could not be read")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Read it again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});

describe("chainAround", () => {
  const pass = (fields: Partial<BoundaryReviewSummary>): BoundaryReviewSummary => ({
    review_id: "rev_1",
    case_id: "case_a",
    case_revision: 1,
    atlas_version_id: "atlas_1",
    status: "succeeded",
    boundaries_reviewed: 6,
    boundaries_material: 2,
    boundaries_detected: 6,
    created_at: "2026-08-05T10:00:00Z",
    updated_at: "2026-08-05T10:00:00Z",
    case_title: "Task scheduler",
    elicited_from: null,
    ...fields,
  });

  it("walks to the whole run from either pass, oldest first", () => {
    // The rail must read the same whichever pass the reader is standing on.
    const listing = [
      pass({ review_id: "rev_2", case_revision: 2, elicited_from: "rev_1" }),
      pass({ review_id: "rev_1", status: "awaiting_answers" }),
    ];

    expect(chainAround("rev_1", listing).map((item) => item.review_id)).toEqual([
      "rev_1",
      "rev_2",
    ]);
    expect(chainAround("rev_2", listing).map((item) => item.review_id)).toEqual([
      "rev_1",
      "rev_2",
    ]);
  });

  it("is just the review itself when nothing links to it", () => {
    expect(chainAround("rev_1", [pass({})])).toHaveLength(1);
  });

  it("ends the walk where a deleted pass leaves a gap", () => {
    const listing = [pass({ review_id: "rev_2", elicited_from: "rev_gone" })];
    expect(chainAround("rev_2", listing).map((item) => item.review_id)).toEqual(["rev_2"]);
  });

  it("is empty for a review the listing has not caught up with", () => {
    // The siblings query lands after the review itself; the rail simply waits.
    expect(chainAround("rev_new", [])).toEqual([]);
  });
});

/**
 * Pressing New revision always runs the check; a check that finds nothing stops there.
 *
 * The whole page rather than the strip alone, because what is under test is the sequence the
 * button sets off — refresh, check, and then either start a run or say why not. A test of the
 * strip would prove the notice renders and prove nothing about the run that must not begin.
 */
describe("new revision, when nothing has changed", () => {
  const REVIEW = {
    review_id: "rev_1",
    status: "succeeded" as ReviewStatus,
    case_id: "case_a",
    case_revision: 1,
    atlas_version_id: "atlas_1",
    reasoning_model: "fake:deterministic",
    prompt_identity: "judge/1",
    repo_id: "repo_1",
    branch_id: "branch_1",
    duration_seconds: 4,
    report: {
      case_title: "Where audio lives",
      problem_and_desired_outcome: "Decide where the store abstraction earns its place.",
      reviewed: [],
      overview: {
        situation: "Two boundaries, both settled.",
        limits: "Nothing outside the indexed repository was read.",
        open_questions: [],
      },
      policies_presented: [],
    },
  } as unknown as ReviewDetail;

  /** Every read the page makes, with the repository resolved so the strip has its button. */
  function workspace() {
    vi.spyOn(api, "review").mockResolvedValue(REVIEW);
    vi.spyOn(api, "reviews").mockResolvedValue([]);
    vi.spyOn(api, "case").mockResolvedValue({} as never);
    vi.spyOn(api, "branches").mockResolvedValue([
      {
        repository: { repo_id: "repo_1" },
        branch: { branch_id: "branch_1", repo_id: "repo_1", branch_name: "main" },
      },
    ] as never);
    vi.spyOn(api, "repositories").mockResolvedValue([
      { version_id: "atlas_1", root_path: "/home/dev/warehouse" },
    ] as never);
    vi.spyOn(api, "refreshRepository").mockResolvedValue({ managed: false } as never);
  }

  function open() {
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter initialEntries={["/reviews/rev_1"]}>
          <RunProvider>
            <TooltipProvider>
              <Routes>
                <Route path="/reviews/:reviewId" element={<ReviewDetailPage />} />
              </Routes>
            </TooltipProvider>
          </RunProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  afterEach(() => vi.restoreAllMocks());

  it("says so and starts nothing", async () => {
    workspace();
    vi.spyOn(api, "preflightRepository").mockResolvedValue({
      changed: false,
      current_against: "rev_1",
      judged: 0,
      addressed: 0,
      resurfaced: 0,
      succeeded: 0,
    });
    const started = vi.spyOn(api, "startFromRepository");

    open();
    fireEvent.click(await screen.findByRole("button", { name: /New revision/ }));

    const notice = await screen.findByRole("status");
    expect(notice.textContent).toContain("Nothing has changed since this revision");
    // The check is the whole of what the button did: no case was opened and no run began, so
    // the branch's line is exactly as long as it was.
    expect(started).not.toHaveBeenCalled();
  });
});
