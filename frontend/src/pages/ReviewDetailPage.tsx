import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, ChevronDown, Download, GitBranch, Info, Play, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

import { ApiError, api } from "../api";
import { AiChatIcon } from "../ai-icon";
import { AddressedLedger, deltaFact } from "../delta";
import { groupIntoChains } from "./ReviewsPage";
import { AskPanel } from "../ask-panel";
import {
  ErrorPanel,
  Group,
  Loading,
  PageHeader,
  formatDate,
  page,
  sheet,
  shortId,
} from "../components";
import { ask } from "../review-capabilities";
import { HeldVerdicts, HoldBanner, contingentCount } from "../review-awaiting";
import { ReviewAtlas } from "../review-atlas";
import { RunLog, watchedProgress } from "../review-in-progress";
import {
  Cite,
  Citations,
  FindingsLedger,
  JudgingLedger,
  VerdictBand,
  type BandFact,
} from "../review-ledger";
import { useRun } from "../run";
import { QuestionDiscussion } from "../question-discussion";
import { BulkDecide } from "../triage";
import { OpenQuestions, type SubmittedAnswer } from "../review-questions";
import type {
  BoundaryReview,
  BoundaryReviewSummary,
  RepositoryBranch,
  BoundaryTriage,
  OpenQuestion,
  RecordedAnswer,
  ReviewDetail,
  ReviewOverview,
  ReviewStatus,
  ReviewedBoundary,
} from "../types";

/**
 * The run this review is one pass of, oldest pass first.
 *
 * Walked in both directions from the review on show: back along `elicited_from` to the pass
 * that asked, and forward to whichever pass answers this one. The listing of the case's
 * reviews already holds both links, so nothing here is guessed — a pass that has been
 * deleted simply ends the walk on that side.
 */
export function chainAround(
  reviewId: string,
  reviews: BoundaryReviewSummary[],
): BoundaryReviewSummary[] {
  const byId = new Map(reviews.map((item) => [item.review_id, item]));
  const current = byId.get(reviewId);
  if (!current) return [];
  const chain = [current];
  let earlier = current.elicited_from ? byId.get(current.elicited_from) : undefined;
  while (earlier) {
    chain.unshift(earlier);
    earlier = earlier.elicited_from ? byId.get(earlier.elicited_from) : undefined;
  }
  let later = reviews.find((item) => item.elicited_from === reviewId);
  while (later) {
    chain.push(later);
    const answeredId = later.review_id;
    later = reviews.find((item) => item.elicited_from === answeredId);
  }
  return chain;
}

/** The word a pass wears in the rail: what it did, or what it is doing. */
function passWord(status: BoundaryReviewSummary["status"]): string {
  if (status === "awaiting_answers") return "asked";
  if (status === "running") return "running";
  if (status === "succeeded") return "judged";
  return status;
}

/**
 * The way between the passes of one run.
 *
 * The listing folds a run to its latest pass, so this rail is where the earlier ones remain
 * reachable — the first pass holds the questions as they were asked, and the second holds
 * what the answers changed. Absent on a run of one pass: a rail with one stop is furniture.
 */
function PassesRail({
  chain,
  currentId,
}: {
  chain: BoundaryReviewSummary[];
  currentId: string;
}) {
  if (chain.length < 2) return null;
  return (
    <nav
      aria-label="Passes of this run"
      className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 font-mono text-micro"
    >
      <span className="tracking-[.09em] uppercase text-ink-3">Passes</span>
      {chain.map((pass, index) => {
        const label = `${index + 1} · ${passWord(pass.status)}`;
        return pass.review_id === currentId ? (
          <span key={pass.review_id} aria-current="page" className="font-[650] text-ink">
            {label}
          </span>
        ) : (
          <Link
            key={pass.review_id}
            to={`/reviews/${pass.review_id}`}
            className="text-accent-ink"
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

/**
 * The branch and the revision this page is showing, and the way to make the next one.
 *
 * The repository model made visible where the reader stands: a branch carries one living
 * review, each run is a revision on its line, and this strip says which line and which
 * point. The button appends to the line — re-analyse the code, judge what changed, ask
 * only about that — which is why it lives here and not on the start step: a next revision
 * is something done *to this branch*, not a fresh errand.
 *
 * It does not always append. The run itself refuses a revision that would change nothing —
 * a repository nothing has touched since this revision earns a floating notice saying so,
 * from the run's own holder, rather than a second revision repeating the first: the line is
 * a history of what happened to the code, not of who pressed what.
 *
 * A picker with one option renders as a plain label: a control that opens a menu of the
 * thing already on screen is furniture.
 */
function RevisionStrip({
  review,
  currentId,
  reviews,
  branches,
  onNewRevision,
  starting,
  startError,
}: {
  review: ReviewDetail;
  currentId: string;
  reviews: BoundaryReviewSummary[];
  branches: RepositoryBranch[];
  onNewRevision: () => void;
  starting: boolean;
  startError: Error | null;
}) {
  const navigate = useNavigate();
  const branchId = review.branch_id ?? null;
  const repoId = review.repo_id ?? null;
  if (!branchId) return null;

  const chains = groupIntoChains(reviews.filter((item) => item.branch_id === branchId));
  const position = chains.findIndex((chain) =>
    chain.passes.some((pass) => pass.review_id === currentId),
  );
  // Branches of this repository that have a line to show. A branch with no reviews has
  // no page to land on, so it is not offered rather than offered and refused.
  const linesOn = new Set(
    reviews.filter((item) => item.repo_id === repoId).map((item) => item.branch_id),
  );
  const branchOptions = branches.filter(
    (item) => item.branch.repo_id === repoId && linesOn.has(item.branch.branch_id),
  );
  const branchName = branches.find((item) => item.branch.branch_id === branchId)?.branch
    .branch_name;

  const staticLabel = "inline-flex items-center gap-1.5 font-mono text-meta text-ink-2";
  const openBranch = (targetBranchId: string) => {
    const tip = groupIntoChains(
      reviews.filter((item) => item.branch_id === targetBranchId),
    )[0]?.tip;
    if (tip) navigate(`/reviews/${tip.review_id}`);
  };

  return (
    <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-2">
      {branchName ? (
        branchOptions.length > 1 ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button type="button" aria-label={`Branch ${branchName} — switch branch`}>
                <GitBranch size={13} aria-hidden /> {branchName}
                <ChevronDown size={13} aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              {branchOptions.map((option) => (
                <DropdownMenuItem
                  key={option.branch.branch_id}
                  disabled={option.branch.branch_id === branchId}
                  onSelect={() => openBranch(option.branch.branch_id)}
                >
                  {option.branch.branch_name}
                  {option.branch.branch_id === branchId ? " — viewing" : ""}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : (
          <span className={staticLabel}>
            <GitBranch size={13} aria-hidden /> {branchName}
          </span>
        )
      ) : null}
      {position !== -1 ? (
        chains.length > 1 ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                aria-label={`Revision ${chains.length - position} of ${chains.length} — switch revision`}
              >
                Revision {chains.length - position}
                {position === 0 ? (
                  <span className="text-micro tracking-[.06em] uppercase text-accent-ink">
                    latest
                  </span>
                ) : null}
                <ChevronDown size={13} aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              {chains.map((chain, index) => (
                <DropdownMenuItem
                  key={chain.tip.review_id}
                  disabled={index === position}
                  onSelect={() => navigate(`/reviews/${chain.tip.review_id}`)}
                >
                  Revision {chains.length - index} · {formatDate(chain.tip.created_at)}
                  {index === 0 ? " · latest" : ""}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : (
          <span className={staticLabel}>Revision {chains.length - position}</span>
        )
      ) : null}
      <span className="ml-auto" />
      <Button
        type="button"
        disabled={starting}
        onClick={onNewRevision}
        title="Re-analyse the code and judge what changed. Unchanged boundaries carry; only what moved can be asked about."
      >
        {starting ? <Spinner /> : <Play size={13} aria-hidden />}{" "}
        {starting ? "Starting…" : "New revision"}
      </Button>
      {startError ? (
        <p role="alert" className="m-0 w-full text-meta text-material">
          {startError.message}
        </p>
      ) : null}
    </div>
  );
}

/**
 * What the verdicts amount to, read as a set.
 *
 * Leads with the bottom line — the situation, what came out wrong, and what to do — because
 * a reader who gets no further than the first sentence should still know where they stand.
 * Closes with the limits, because a reader who has just been told what to do is exactly who
 * needs to know what was not examined.
 *
 * Below the ledger rather than above it. It is the one thing none of the separate calls
 * could produce, and it is also the thing a reader checks *after* seeing which boundaries it
 * is talking about — the citations lead back up into the rows.
 */
export function Overview({ overview }: { overview: ReviewOverview }) {
  const themes = overview.themes || [];
  const sequence = overview.recommended_sequence || [];
  return (
    // "Conclusion", not "Findings": the findings are the boundaries above, each with its own
    // verdict. This is what they amount to read as a set.
    <section data-slot="overview" className={cn(sheet, "p-[var(--card-pad)]")} aria-label="Conclusion">
      <h2 className="m-0 mb-3 text-micro font-[650] tracking-[.09em] uppercase text-accent-ink">
        Conclusion
      </h2>
      <p data-slot="overview-lead" className="m-0 max-w-[74ch] text-body leading-reading">
        {overview.situation}
      </p>

      {themes.length > 0 ? (
        <Group label="Across the boundaries">
          <ul className={overviewList}>
            {themes.map((statement) => (
              <li key={statement.text} className={cn(overviewClaim, overviewBullet)}>
                <span className="min-w-0">{statement.text}</span>
                <Citations references={statement.supporting_references || []} />
              </li>
            ))}
          </ul>
        </Group>
      ) : null}

      {sequence.length > 0 ? (
        <Group label="Recommended actions, in order">
          <ol className={cn(overviewList, "[counter-reset:step]")}>
            {sequence.map((statement) => (
              <li key={statement.text} className={cn(overviewClaim, overviewStep)}>
                <span className="min-w-0">{statement.text}</span>
                <Citations references={statement.supporting_references || []} />
              </li>
            ))}
          </ol>
        </Group>
      ) : null}

      {/* Kept even when there is nothing else: "no theme ran across these boundaries" is a
          result, and a reader still has to know what the method could not see. */}
      <p
        data-slot="overview-limits"
        className="m-0 mt-4 max-w-[82ch] border-t border-rule-soft pt-3 text-ui leading-[1.6] text-ink-2"
      >
        <strong>What this review could not see.</strong> {overview.limits}
      </p>
    </section>
  );
}

/* A claim the conclusion draws, with the boundaries it rests on beside it.
   The marker is a pseudo-element rather than a list bullet or a rendered span, because the
   claim and its citations are one wrapping line of flex items and a marker in that flow
   would be a fourth one — it has to sit outside the text it marks. */
const overviewList = "m-0 grid max-w-[82ch] list-none gap-3 p-0";
const overviewClaim =
  "relative flex flex-wrap items-baseline gap-x-2 gap-y-1 text-body leading-[1.55] before:absolute before:left-[2px]";
const overviewBullet = "pl-4 before:font-bold before:text-primary before:content-['·']";
/* Numbered, because the recommended order is the whole of what that list adds: a dot would
   give the reader nothing to refer to when they come back to the third one. */
const overviewStep =
  "pl-6 [counter-increment:step] before:text-ui before:tabular-nums before:text-accent-ink before:content-[counter(step)_'.']";

/**
 * What the reader's answers actually changed, read off the two passes.
 *
 * The single most persuasive thing this flow can show, and it costs no model call: both
 * reviews are stored, both judged the same atlas, and the only difference between them is
 * what the case says. A verdict that moved is therefore attributable to the answer and to
 * nothing else — which is the claim elicitation makes, put in front of the person who just
 * did the work.
 *
 * Matched by reference, which is safe precisely because detection is deterministic: the same
 * atlas gives the same boundary the same `BR-nnn` in both passes.
 */
export function verdictChanges(
  before: ReviewedBoundary[],
  after: ReviewedBoundary[],
): { reference: string; title: string; from: boolean; to: boolean }[] {
  const previous = new Map(before.map((item) => [item.reference, item]));
  return after.flatMap((item) => {
    const earlier = previous.get(item.reference);
    if (!earlier || earlier.material === item.material) return [];
    return [
      {
        reference: item.reference,
        title: item.candidate.participants[0]?.qualified_name ?? item.candidate.summary,
        from: earlier.material,
        to: item.material,
      },
    ];
  });
}

/**
 * Which of the reader's answers a boundary's verdict rested on.
 *
 * A question names the boundaries it would settle, and the revision names the questions it
 * answered, so the join is already recorded on both sides and nothing here has to guess. It
 * is the reason the provenance was worth storing: without it a second pass can say four
 * verdicts moved, and cannot say which sentence moved any one of them.
 *
 * A changed verdict may have several answers behind it and may have none — a boundary can
 * move because a question about a *different* boundary changed what the case says overall.
 * Both are reported as what they are rather than forced into a single cause.
 */
export function answersBehind(
  reference: string,
  questions: OpenQuestion[],
  answered: RecordedAnswer[],
): { question: string; recordedText: string }[] {
  const recorded = new Map(answered.map((item) => [item.question_reference, item]));
  return questions.flatMap((question) => {
    if (!(question.supporting_references || []).includes(reference)) return [];
    const answer = recorded.get(question.reference);
    if (!answer) return [];
    return [{ question: question.question, recordedText: answer.recorded_text }];
  });
}

/**
 * Which finding a node on the map belongs to, by the reference the ledger files it under.
 *
 * Both participants, because both are on the map: the boundary carries the verdict and the
 * implementation behind it is drawn beside it, and a reader who selected either of them is
 * asking about the same finding. `null` for every other node the atlas returned — most of the
 * map is the neighbourhood, which no finding is about.
 */
export function findingForNode(
  nodeId: string,
  reviewed: ReviewedBoundary[],
): string | null {
  const found = reviewed.find((item) =>
    item.candidate.participants.some((participant) => participant.node_id === nodeId),
  );
  return found?.reference ?? null;
}

function WhatChanged({
  changes,
  total,
  questions,
  answered,
}: {
  changes: ReturnType<typeof verdictChanges>;
  total: number;
  /** The questions the first pass asked, where that pass has loaded. */
  questions: OpenQuestion[];
  /** What the answered revision recorded. Empty for a revision authored by hand. */
  answered: RecordedAnswer[];
}) {
  return (
    // Ruled down its accent side: what the reader's own answers did is a result about this
    // page, not one more panel on it. The `!` on the phone width: `sheet` strips its side
    // walls there, and this card's left edge is not a wall — it is the accent saying
    // "conclusion". Both rules live in the same breakpoint, so importance settles what
    // source order cannot promise.
    <section className={cn(sheet, "border-l-[3px] border-l-primary p-[var(--card-pad)] max-sm:border-l-[3px]!")}>
      <p className="m-0 flex items-start gap-2 text-body leading-reading">
        <ArrowRight size={15} aria-hidden className="mt-1 flex-none text-accent-ink" />
        <span>
          {changes.length === 0 ? (
            <>
              <strong>Your answers changed no verdict.</strong> All {total} came out the
              same way against the answered case — which is a result, not a wasted round: it
              means those verdicts never rested on what you were asked about.
            </>
          ) : (
            <>
              <strong>
                {changes.length} of {total}{" "}
                {changes.length === 1 ? "verdict" : "verdicts"} changed
              </strong>{" "}
              because of what you answered. Same repository, same atlas, same model — the
              only difference between the two passes is what the case now says.
            </>
          )}
        </span>
      </p>
      {changes.length > 0 ? (
        <ul className="m-0 mt-3 grid list-none gap-2 p-0">
          {changes.map((item) => {
            const behind = answersBehind(item.reference, questions, answered);
            return (
              <li
                key={item.reference}
                className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-ui"
              >
                <Cite reference={item.reference} />
                <code className="text-meta text-ink-2">{item.title}</code>
                <span className="text-ui text-ink-2">
                  {item.from ? "should change" : "earning its place"} →{" "}
                  <strong className="text-ink">
                    {item.to ? "should change" : "earning its place"}
                  </strong>
                </span>
                {/* The sentence that did it, where one can be named. Absent rather than
                    guessed at: a verdict can move because a question about another boundary
                    changed what the case says overall, and claiming a cause there would be
                    inventing one.

                    Indented under the row it explains and given the full width of it,
                    because the whole point is that this is the sentence the reader wrote —
                    their words, under the question that drew them out. */}
                {behind.length > 0 ? (
                  <ul className="mt-[2px] mb-1 grid w-full list-none gap-1 border-l-2 border-accent-rule pl-3">
                    {behind.map((answer) => (
                      <li key={answer.question} className="grid gap-0.5 text-ui">
                        <span className="text-ink-3">{answer.question}</span>
                        <span className="text-ink-2">{answer.recordedText}</span>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}

/**
 * The answers that produced this pass, beside the questions they answered.
 *
 * Read off the case revision this review is pinned to rather than recomposed: the workspace
 * recorded which question each answer answered, which is what makes the join possible at all.
 *
 * The answer prints as the reader typed it. It used to be a line composed from the question
 * and the reply, so this section showed the question and then most of it again underneath —
 * the case now keeps the pair, and what is quoted here is a person's own sentence.
 */
function AnsweredHistory({
  questions,
  answered,
  revision,
}: {
  questions: OpenQuestion[];
  answered: RecordedAnswer[];
  revision: number | undefined;
}) {
  const asked = new Map(questions.map((item) => [item.reference, item]));
  return (
    <section className={cn(sheet, "p-[var(--card-pad)]")} aria-label="Answers already recorded">
      <p className="mb-2 text-ui text-ink-2">
        {answered.length} {answered.length === 1 ? "answer" : "answers"} became case revision{" "}
        {revision ?? "?"}, which is what this pass judged against.
      </p>
      <ol className="m-0 grid list-none gap-3 p-0">
        {answered.map((item) => (
          // Ruled down the side rather than bulleted: each of these is a quotation of the
          // reader's own sentence, under the question it was given for.
          <li
            key={item.question_reference}
            className="grid gap-0.5 border-l-2 border-accent-rule pl-3"
          >
            <code className="text-micro tracking-[.07em] text-ink-3">
              {item.question_reference}
            </code>
            <span className="text-ui leading-[1.5] text-ink-3">
              {asked.get(item.question_reference)?.question ?? "The question it answered."}
            </span>
            <span className="text-ui leading-[1.55] text-ink">{item.recorded_text}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

const unfinishedNote = "m-0 text-body leading-[1.6] text-ink-2";

/**
 * A review that ended without a judgement: cancelled, or failed.
 *
 * Not an error page. The row exists from the moment the run starts, so this is what a review
 * page looks like when the run ended and no subject ever will exist. A run still going is a
 * different thing entirely and has its own state; this one is the aftermath.
 */
function Unfinished({ review }: { review: BoundaryReview }) {
  const cancelled = review.status === "cancelled";
  return (
    <div data-slot="review-page" className={cn(page, "pb-6")}>
      <PageHeader
        title={cancelled ? "This review was cancelled" : "This review did not finish"}
        parent={{ to: "/reviews", label: "Reviews" }}
        meta={<Badge>case rev {review.case_revision}</Badge>}
      />
      <div className={cn(sheet, "grid max-w-[76ch] gap-3.5 p-[var(--card-pad)]")}>
        {/* Cancelling records no reason, because there is none to record beyond the choice
            itself. Only what ArchCompass wrote for a person to read reaches this list; an
            unexpected failure is recorded without its text. */}
        {cancelled ? (
          <p className={unfinishedNote}>
            It stopped after the boundary it was judging at the time. The verdicts it had
            already reached were not kept: a review is every boundary or none, and half of
            one would read as a complete answer.
          </p>
        ) : (
          <ul className="m-0 grid gap-2 rounded-panel border border-danger-rule bg-danger-soft py-4 pr-4 pl-8 text-body leading-[1.55] text-danger">
            {(review.sanitized_errors || []).map((message) => (
              <li key={message}>{message}</li>
            ))}
            {(review.sanitized_errors || []).length === 0 ? (
              <li>No reason was recorded.</li>
            ) : null}
          </ul>
        )}
        <p className={unfinishedNote}>
          Nothing was written to the case or the atlas. A review is derived from both, so
          running it again is the whole of the fix. Started {formatDate(review.created_at)} ·
          case <code>{shortId(review.case_id)}</code> · <Link to="/start">Start a review</Link> ·{" "}
          <Link to="/reviews">All reviews</Link>
        </p>
      </div>
    </div>
  );
}

/**
 * The page with its subject missing: deleted, or unreadable.
 *
 * It exists because a review can go while someone is reading it — deleting one from the
 * reviews list in another tab is the ordinary way that happens — and what this page did then
 * was put a red strip on an empty canvas, with no header, no column and no link anywhere. A
 * reader who had followed a link into a review they no longer had was left with the back
 * button as the only way on.
 *
 * The two cases are told apart because their recoveries are opposites. A 404 is settled: the
 * record is gone, asking again asks for the same nothing, and the only useful thing left to
 * offer is the list it came out of. Anything else might be the network, so it gets the second
 * attempt and keeps the reader where they are.
 *
 * Neither is dressed up. The server's own words stay in the strip; the sentence under it says
 * what is known and nothing more — in particular it does not claim the review "may have been
 * deleted" when the reason is a timeout, or promise anything about getting it back.
 */
export function ReviewUnavailable({
  reviewId,
  error,
  onRetry,
  retrying,
}: {
  reviewId: string;
  error: unknown;
  onRetry?: () => void;
  retrying?: boolean;
}) {
  const gone = error instanceof ApiError && error.status === 404;
  return (
    <div data-slot="review-page" className={cn(page, "pb-6")}>
      <PageHeader
        title={gone ? "This review is no longer here" : "This review could not be read"}
        parent={{ to: "/reviews", label: "Reviews" }}
      />
      <div className={cn(sheet, "grid max-w-[76ch] gap-3.5 p-[var(--card-pad)]")}>
        {/* Nothing to retry on a review that has been deleted: the request would succeed at
            fetching the same absence, and a control that cannot change its own outcome is
            worse than no control. */}
        <ErrorPanel
          error={error}
          onRetry={gone ? undefined : onRetry}
          retrying={retrying}
          retryLabel="Read it again"
        />
        <p className={unfinishedNote}>
          {gone ? (
            <>
              Reviews are deleted from the reviews list, and deleting one is permanent — it
              may have gone from another tab while this page was open. Nothing else was
              affected: the case it judged and the atlas it ran against are both untouched,
              and every other review is where it was.
            </>
          ) : (
            <>
              Nothing has been changed by this — reading a review only reads. If it keeps
              failing, the review may still be readable from the list.
            </>
          )}
        </p>
        <p className={unfinishedNote}>
          <Link to="/reviews">All reviews</Link> · <Link to="/start">Start a review</Link> ·{" "}
          <code>{shortId(reviewId)}</code>
        </p>
      </div>
    </div>
  );
}

/**
 * The way into the question panel, and the one place the `ask` rule is enforced.
 *
 * Blocked states keep the button on screen rather than dropping it. A reader who never sees
 * the affordance never learns the review can be asked about at all, and this page is where
 * they would learn it — so it stays, greyed, with the reason on it.
 */
export function AskAction({
  status,
  expanded,
  onToggle,
}: {
  status: ReviewStatus | undefined;
  expanded: boolean;
  onToggle: () => void;
}) {
  const refusal = ask(status);
  const button = (
    <Button
      type="button"
      variant="primary"
      aria-expanded={refusal ? undefined : expanded}
      disabled={refusal !== null}
      onClick={refusal ? undefined : onToggle}
    >
      <AiChatIcon size={14} /> Ask about this review
    </Button>
  );
  if (!refusal) return button;
  return (
    <Tooltip>
      {/* The span is load-bearing: a disabled button dispatches no pointer events, so the
          trigger has to be something above it that does. It takes the tab stop the button
          gave up, so the reason reaches a reader arriving by keyboard too. */}
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          className={cn(
            "inline-flex rounded-control",
            // The ring the button can no longer draw for itself, on the element that now
            // holds its tab stop. Same 2px of accent every focusable thing here draws.
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
          )}
        >
          {button}
        </span>
      </TooltipTrigger>
      <TooltipContent>{refusal}</TooltipContent>
    </Tooltip>
  );
}

/**
 * The review as the file it was already written as.
 *
 * An anchor rather than a request: the workspace answers with `Content-Disposition`, so the
 * browser saves the response itself. Nothing is fetched, held or revoked here, and the
 * control is keyboard-reachable because it is a link — which is also why this is the one
 * call that does not go through `api.ts`, where every function reads a body.
 *
 * `download` is on it so a refusal stays a failed download rather than navigating the reader
 * off their own review onto a page of JSON.
 *
 * Absent rather than greyed while there is nothing to hand over, which is the opposite of
 * what asking does — and for the opposite reason. Asking is a capability of the review that
 * a reader has to learn exists; exporting a report that does not exist is not a refusal
 * worth explaining, it is a run that has not finished.
 */
export function ExportAction({ reviewId, available }: { reviewId: string; available: boolean }) {
  if (!available) return null;
  return (
    <Button asChild>
      <a href={`/api/reviews/${encodeURIComponent(reviewId)}/report`} download>
        <Download size={14} aria-hidden /> Export Markdown
      </a>
    </Button>
  );
}

type TabId = "findings" | "questions" | "runlog" | "atlas";

/** A run's length, in the units a reader counts model calls in. */
function formatDuration(seconds: number | undefined): string | null {
  if (!seconds || seconds <= 0) return null;
  // A run that took less than a second still took some time, and "0s" reads as a bug.
  if (seconds < 1) return "<1s";
  const whole = Math.round(seconds);
  if (whole < 60) return `${whole}s`;
  return `${Math.floor(whole / 60)}m ${String(whole % 60).padStart(2, "0")}s`;
}

export function ReviewDetailPage() {
  const { reviewId = "" } = useParams();
  const client = useQueryClient();
  const [tab, setTab] = useState<TabId>("findings");
  /**
   * Which tabs have been opened. A panel is mounted on first visit and kept mounted after,
   * so the atlas does not re-inspect every boundary each time the reader comes back to it —
   * and does not inspect any of them on a visit that never opens the map.
   */
  const [visited, setVisited] = useState<TabId[]>(["findings"]);
  const [openRow, setOpenRow] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  // The map is one tab of this page, so which node it shows is the page's state: a finding
  // can ask for its own boundary, and the two must not each hold an answer.
  const [atlasNodeId, setAtlasNodeId] = useState<string | null>(null);
  /**
   * Which review these all belong to.
   *
   * The route keeps this component mounted when the reader moves from one review to
   * another — answering navigates from a first pass to the second it started — so without
   * this the new review opens on whichever tab the old one was left on, with a row expanded
   * that its ledger does not contain.
   */
  const [shown, setShown] = useState(reviewId);
  if (shown !== reviewId) {
    setShown(reviewId);
    setTab("findings");
    setVisited(["findings"]);
    setOpenRow(null);
    setAtlasNodeId(null);
    // A panel is about one review, so it does not follow the reader to the next one —
    // answering a held review navigates straight from that pass to the one it starts.
    setAsking(false);
  }
  const run = useRun();

  const review = useQuery({
    queryKey: ["review", reviewId],
    queryFn: () => api.review(reviewId),
    enabled: Boolean(reviewId),
    // A review opened while it is still being produced is a page waiting for its own
    // subject. It polls until the run ends and then stops: the review is immutable
    // afterwards, so there is nothing further to ask about.
    refetchInterval: (query) => (query.state.data?.status === "running" ? 2000 : false),
  });

  const caseId = review.data?.case_id;
  const caseRevision = review.data?.case_revision;
  const atlasVersionId = review.data?.atlas_version_id;

  /**
   * The listing entry for this review, which is where a running review's counts live — the
   * review document has no room for how far it has got.
   *
   * It also feeds the passes rail: the case's other reviews carry the `elicited_from`
   * links, and the rail is the walk along them. It once fed arrows that navigated by case
   * revision instead, which landed readers on the in-progress screen of a pass that was
   * never run — the rail names each pass by what it did, which is the difference.
   */
  const siblings = useQuery({
    queryKey: ["reviews", caseId],
    queryFn: () => api.reviews(caseId),
    enabled: Boolean(caseId),
    refetchInterval: () => (review.data?.status === "running" ? 2000 : false),
  });

  /** The pinned revision, not the latest: the case this review actually judged against. */
  const pinnedCase = useQuery({
    queryKey: ["case", caseId, caseRevision],
    queryFn: () => api.case(caseId!, caseRevision),
    enabled: Boolean(caseId && caseRevision),
  });

  /**
   * The first pass this review answers, where there is one.
   *
   * Fetched rather than derived, because what it is needed for is the verdicts themselves —
   * the listing carries counts, and "which verdicts moved" is a comparison per boundary. Only
   * on a second pass, so an ordinary review makes no extra request.
   */
  const elicitedFrom = review.data?.elicited_from ?? null;
  const earlierPass = useQuery({
    queryKey: ["review", elicitedFrom],
    queryFn: () => api.review(elicitedFrom!),
    enabled: Boolean(elicitedFrom),
  });

  /**
   * The review that asked the questions this revision answered, whichever review that was.
   *
   * Not the same thing as the pass this one answers. Only the answers are recorded on the
   * case, by reference — the wording lives on the review that asked — and a third review
   * judging the same answered revision was elicited from nobody. Reading the asking review
   * off the revision itself is what lets it show the questions rather than a placeholder.
   * The same id on a second pass, so react-query serves it from what `earlierPass` fetched.
   */
  const askedBy = pinnedCase.data?.answered?.review_id ?? null;
  const askingPass = useQuery({
    queryKey: ["review", askedBy],
    queryFn: () => api.review(askedBy!),
    enabled: Boolean(askedBy),
  });

  // The atlas the review pinned answers where the repository is; a review carries the
  // version, and the listing is what turns a version into a path.
  const repositories = useQuery({
    queryKey: ["repositories"],
    queryFn: api.repositories,
  });
  // The whole listing and the branch lineages, for the revision strip: which branches of
  // this repository carry a line, and where this review sits on its own.
  const allReviews = useQuery({ queryKey: ["reviews"], queryFn: () => api.reviews() });
  const branchLineages = useQuery({ queryKey: ["branches"], queryFn: api.branches });
  const indexedAtlas = repositories.data?.find((item) => item.version_id === atlasVersionId);
  const repositoryRoot =
    indexedAtlas?.root_path || pinnedCase.data?.snapshot?.repository?.root_path || null;

  // Answering, in one call. The workspace resolves each `Q-n` against this review's own
  // report, pairs the answer with the question it asked, and records what it answered in the
  // same transaction — which is what makes the link from a case entry back to its question
  // impossible to lose.
  //
  // The new run then names this review as the one it answers, and that is what makes it a
  // second pass: it judges against the answered case and concludes rather than asking again.
  const answer = useMutation({
    mutationFn: async (answers: SubmittedAnswer[]) => {
      if (!caseId || !repositoryRoot) {
        throw new Error("This review's case and repository could not both be resolved.");
      }
      await api.answerReview(reviewId, answers);
      run.start(caseId, repositoryRoot, reviewId);
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["cases"] });
    },
  });

  // The next revision of this branch's line: re-index, continue the branch's case, judge
  // the delta. The same start the start step performs, offered where the line lives.
  const newRevision = useMutation({
    mutationFn: async () => {
      if (!repositoryRoot) {
        throw new Error("This review's repository could not be resolved.");
      }
      // A managed checkout is brought current first, so "re-analyse the code" means the
      // repository's code, not whatever the clone last held. Anyone else's working copy
      // comes back managed:false untouched, so this is safe to ask unconditionally.
      await api.refreshRepository(repositoryRoot);
      // No check here: a revision that would move nothing is the run's own first decision,
      // refused inside the service before anything is written, and the run's holder shows
      // the notice wherever the reader is. This handler only starts the run.
      const revision = await api.startFromRepository(repositoryRoot);
      if (!revision.case_id) {
        throw new Error("The workspace returned a case without an identifier.");
      }
      run.start(revision.case_id, repositoryRoot);
    },
  });

  const report = review.data?.report ?? null;
  const reviewed = report?.reviewed || [];
  const branchId = review.data?.branch_id ?? null;
  // Reference → triage join, for the ledger rows. Rebuilt per render from a list that is
  // at most dozens long; a memo here would be bookkeeping for nothing.
  const triageByReference = new Map<string, BoundaryTriage>(
    (review.data?.boundary_triage ?? []).map((entry) => [entry.reference, entry]),
  );

  const references = reviewed.map((item) => item.reference).join(" ");
  // Material with nobody's name on it — what the bulk gesture would decide.
  const undecided = reviewed.filter(
    (item) =>
      item.material &&
      item.fingerprint &&
      !triageByReference.get(item.reference)?.decision,
  );

  /**
   * A citation opens the row it names, in the tab that holds it.
   *
   * `hashchange` rather than the router's location: an anchor pointing at the same document
   * never reaches the router, so a citation clicked in the conclusion would otherwise scroll
   * to a collapsed row and show nothing. Selecting first and scrolling second, so the
   * reasoning is already open when the row arrives rather than unfolding under the reader.
   */
  const openTab = (id: TabId) => {
    setTab(id);
    setVisited((current) => (current.includes(id) ? current : [...current, id]));
  };
  const openTabRef = useRef(openTab);
  openTabRef.current = openTab;
  useEffect(() => {
    const jump = () => {
      const wanted = decodeURIComponent(window.location.hash.slice(1));
      if (!wanted || !references.split(" ").includes(wanted)) return;
      openTabRef.current("findings");
      setOpenRow(wanted);
      requestAnimationFrame(() =>
        document.getElementById(wanted)?.scrollIntoView({ behavior: "smooth", block: "start" }),
      );
    };
    jump();
    window.addEventListener("hashchange", jump);
    return () => window.removeEventListener("hashchange", jump);
  }, [references]);

  // Both of these are the page, drawn with its subject missing — not something rendered
  // instead of it. A bare strip on the canvas had no header, no column and no width, so the
  // whole layout snapped into place around the reader the moment the review landed.
  if (review.isLoading) {
    return (
      <div data-slot="review-page" className={cn(page, "pb-6")}>
        {/* The id, because it is the whole of what is known about this review before it has
            been read — and because it is also the fallback the loaded page falls back to,
            so a review without a title does not rename its own header on arrival. */}
        <PageHeader title={shortId(reviewId)} parent={{ to: "/reviews", label: "Reviews" }} />
        <div className={sheet}>
          <Loading label="Reading the review…" rows={3} />
        </div>
      </div>
    );
  }
  if (review.isError) {
    return (
      <ReviewUnavailable
        reviewId={reviewId}
        error={review.error}
        onRetry={() => void review.refetch()}
        retrying={review.isFetching}
      />
    );
  }

  const status = review.data?.status;
  // The row exists from the moment the run starts, so this page has to be able to show a
  // review that never reached a judgement. Both of those are aftermaths, not errors.
  if (review.data && status !== "running" && status !== "succeeded" && status !== "awaiting_answers") {
    return <Unfinished review={review.data} />;
  }
  const running = status === "running";
  const holding = status === "awaiting_answers";
  /**
   * The panel obeys the same rule its button does, so there is one answer and not two.
   *
   * Enforcing it on the button alone would leave the panel open over a review that has since
   * stopped being askable — the reader is carried from a concluded pass to the running one it
   * started without this component unmounting. Deriving `open` instead of closing it in an
   * effect means the panel is never briefly open against a review that refuses it.
   */
  const showAsking = asking && ask(status) === null;
  if (!running && !report) {
    // The same dead end as a missing review and fixed the same way: a review that succeeded
    // without a report is unreadable, re-reading it will not produce one, and the reader
    // still needs somewhere to go.
    return (
      <ReviewUnavailable
        reviewId={reviewId}
        error={new Error("This review did not produce a report.")}
      />
    );
  }

  const summary = siblings.data?.find((item) => item.review_id === reviewId);
  const live = run.watching(reviewId) ? run.progress : undefined;
  const progress = watchedProgress(live, summary);
  const policyCount = (report?.policies_presented || []).length;
  const material = reviewed.filter((item) => item.material).length;
  const cleared = reviewed.length - material;
  const openQuestions = report?.overview.open_questions || [];
  const answered = pinnedCase.data?.answered?.answers || [];
  const askedEarlier = askingPass.data?.report?.overview?.open_questions || [];
  const title = report?.case_title || pinnedCase.data?.snapshot?.title || shortId(reviewId);

  // Both passes are stored, both judged the same atlas, and the only difference between them
  // is what the case says — so a verdict that moved is attributable to the answer and to
  // nothing else. Absent until the earlier pass has loaded, and absent entirely on a review
  // nobody was asked anything for.
  const judgedBefore = earlierPass.data?.report?.reviewed;

  // Only when there is a map to be shown in. Selecting first and switching second so the
  // node is already the selected one when the map arrives, rather than settling into place
  // and then changing under the reader.
  const hasAtlas = Boolean(repositoryRoot) && reviewed.length > 0;
  const showInAtlas = hasAtlas
    ? (nodeId: string) => {
        setAtlasNodeId(nodeId);
        openTab("atlas");
      }
    : null;
  /**
   * The same journey back: a node on the map to the finding written about it.
   *
   * Opening the row before switching tabs, for the same reason the citations do — the reasoning
   * is already unfolded when the reader arrives rather than unfolding under them. The panels
   * are force-mounted, so the row is in the document either way and one frame is only what the
   * tab switch needs before the scroll can land on it.
   */
  const openFinding = (nodeId: string) => {
    const reference = findingForNode(nodeId, reviewed);
    if (!reference) return;
    setOpenRow(reference);
    openTab("findings");
    requestAnimationFrame(() =>
      document
        .getElementById(reference)
        ?.scrollIntoView({ behavior: "smooth", block: "start" }),
    );
  };

  // How many verdicts this page can actually see. A tab watching the run's own record has
  // the counts and not the verdicts, and a band reporting 0 and 0 there would be answering a
  // question nobody can answer yet.
  const knownVerdicts = running
    ? (progress?.verdicts.filter((item) => item !== null).length ?? 0)
    : reviewed.length;

  // The directory's own name, with the branch beside it: what a reader calls the repo,
  // where the atlas id below is what the workspace calls one snapshot of it.
  const repositoryName = repositoryRoot?.split("/").filter(Boolean).pop() ?? null;
  const facts: BandFact[] = [
    ...(repositoryName
      ? [
          {
            label: "Repository",
            value: `${repositoryName}${
              indexedAtlas?.branch_name ? ` · ${indexedAtlas.branch_name}` : ""
            }`,
            title: repositoryRoot ?? undefined,
          },
        ]
      : []),
    {
      label: "Atlas",
      value: `${shortId(atlasVersionId || "—")}${indexedAtlas ? " · indexed" : ""}`,
      title: atlasVersionId,
    },
    ...(report ? [{ label: "Policies", value: `${policyCount} weighed` }] : []),
    {
      label: "Model",
      value: review.data?.reasoning_model ?? "—",
      title: review.data?.prompt_identity,
    },
  ];
  // What this revision was, against the previous one — the partition in one line. Reviews
  // written before the delta existed fall back to the raw reuse count, which is the same
  // fact with less to say.
  const carried = reviewed.filter((item) => item.verdict_reused_from).length;
  if (!running && report?.delta) {
    facts.push({ label: "Revision", value: deltaFact(report.delta) });
  } else if (!running && carried > 0) {
    facts.push({ label: "Carried", value: `${carried} of ${reviewed.length} reused` });
  }
  if (running) {
    facts.push({
      label: "Judged",
      value: `${progress?.judged ?? 0} / ${progress?.total ?? 0}`,
    });
  } else if (holding) {
    // What the run could not settle for itself, which is what makes the questions worth
    // answering — and the only thing it says about verdicts it is withholding.
    facts.push({
      label: "Rests on the unstated",
      value: `${contingentCount(reviewed)} of ${reviewed.length} verdicts`,
    });
    facts.push({ label: "Judged", value: `${reviewed.length} · holding` });
  } else {
    const seconds = formatDuration(review.data?.duration_seconds);
    facts.push({
      label: "Finished",
      value: `${formatDate(summary?.updated_at || review.data?.created_at)}${
        seconds ? ` · ${seconds}` : ""
      }`,
    });
  }

  const questions = (
    <OpenQuestions
      reviewId={reviewId}
      questions={openQuestions}
      nextRevision={caseRevision === undefined ? null : caseRevision + 1}
      // The run as well as the POST: the mutation settles the moment the answers are
      // recorded, but the reader is still on this page until the second pass announces
      // itself and navigation happens. A button that re-enabled in that stretch took a
      // second click against a case revision the first click had already advanced.
      pending={answer.isPending || run.running}
      disabled={!repositoryRoot}
      error={answer.error}
      // `mutateAsync` rather than `mutate`, so the surface hears that the workspace took the
      // answers rather than inferring it: it drops its drafts on that promise, and by the time
      // this mutation settles the run it started has usually navigated the reader away.
      // The rejection is handled there and the failure is rendered from `answer.error`.
      onSubmit={(answers) => answer.mutateAsync(answers)}
      renderCitations={(citations) => <Citations references={citations} />}
      renderDiscussion={(question, adopt) => (
        <QuestionDiscussion
          reviewId={reviewId}
          question={question}
          onAdopt={adopt}
          disabled={!repositoryRoot}
        />
      )}
    />
  );

  const ledger = (
    <FindingsLedger
      reviewed={reviewed}
      policyCount={policyCount}
      reviewId={reviewId}
      open={openRow}
      onOpen={setOpenRow}
      onShowInAtlas={showInAtlas}
      triage={triageByReference}
      branchId={branchId}
    />
  );

  const tabs: { id: TabId; label: string; count?: number }[] = [
    { id: "findings", label: "Findings", count: reviewed.length || undefined },
    ...(holding || answered.length > 0
      ? [
          {
            id: "questions" as TabId,
            label: holding ? "Open questions" : "Questions",
            count: holding ? openQuestions.length : answered.length,
          },
        ]
      : []),
    { id: "runlog", label: "Run log" },
    ...(hasAtlas ? [{ id: "atlas" as TabId, label: "Atlas" }] : []),
  ];
  // A tab that stops existing — the atlas, once its repository is gone — must not leave the
  // page showing nothing.
  const current = tabs.some((item) => item.id === tab) ? tab : "findings";

  /**
   * A section's contents, mounted on first visit and kept after.
   *
   * `forceMount` with the hidden state supplied here rather than the tab strip's own: Radix
   * takes an inactive panel out of the DOM, which would re-inspect every boundary each time
   * the reader came back to the map and lose wherever they had explored to. Gating on
   * `visited` is the other half — a reading that never opens the map makes no atlas query
   * at all.
   */
  const panel = (id: TabId) => {
    if (!visited.includes(id)) return null;
    return (
      <TabsContent key={id} value={id} forceMount hidden={current !== id}>
        {id === "findings" ? (
          <>
            {/* First, and only on a second pass: what the reader's own answers changed.
                They did the work a moment ago, and this is the one place the product's
                claim is checkable rather than asserted. */}
            {judgedBefore ? (
              <WhatChanged
                changes={verdictChanges(judgedBefore, reviewed)}
                total={reviewed.length}
                questions={askedEarlier}
                answered={answered}
              />
            ) : null}
            {/* Adoption, when there is a plural to adopt: everything material and
                undecided, one recorded decision each. What used to be the baseline
                button, with an author attached. */}
            {!running && !holding && branchId && undecided.length > 1 ? (
              <BulkDecide boundaries={undecided} branchId={branchId} reviewId={reviewId} />
            ) : null}
            {/* The boundaries this revision closed, above the ledger of the ones it still
                has: the best news first, and it has no row of its own to live in. */}
            {!running && report?.delta?.addressed_boundaries?.length ? (
              <AddressedLedger addressed={report.delta.addressed_boundaries} />
            ) : null}
            {running ? (
              <JudgingLedger progress={progress} />
            ) : holding ? (
              <HeldVerdicts reviewed={reviewed} findings={ledger} />
            ) : (
              ledger
            )}
            {/* No questions here any more. A concluded review has none to ask — the
                summarising stage has no field for one, which is what stops the loop
                reopening — so the conclusion is the conclusion, and asking happens on its
                own surface before this page exists. */}
            {report && !running && !holding ? <Overview overview={report.overview} /> : null}
          </>
        ) : null}
        {id === "questions" ? (
          <>
            {holding ? <div className={cn(sheet, "max-w-[96ch] p-[var(--card-pad)]")}>{questions}</div> : null}
            {answered.length > 0 ? (
              <AnsweredHistory
                questions={askedEarlier}
                answered={answered}
                revision={caseRevision}
              />
            ) : null}
          </>
        ) : null}
        {id === "runlog" && review.data ? (
          <RunLog
            review={review.data}
            progress={progress}
            reviewed={reviewed}
            watching={run.watching(reviewId)}
            pass={review.data.elicited_from ? 2 : 1}
            awaiting={holding ? openQuestions.length : running ? null : 0}
            answersRecorded={answered.length > 0 ? caseRevision : null}
            withVerdicts={!holding}
          />
        ) : null}
        {id === "atlas" && repositoryRoot ? (
          <ReviewAtlas
            repositoryRoot={repositoryRoot}
            boundaries={reviewed}
            selectedNodeId={atlasNodeId}
            onSelectNode={setAtlasNodeId}
            onOpenFinding={openFinding}
          />
        ) : null}
      </TabsContent>
    );
  };

  return (
    <div
      data-slot="review-page"
      // `page--asking` is a rule rather than a utility, and stays one: see its comment.
      className={cn(page, "pb-6", showAsking && "page--asking")}
    >
      <PageHeader
        title={title}
        parent={{ to: "/reviews", label: "Reviews" }}
        meta={<Badge variant="accent">case rev {caseRevision}</Badge>}
        action={
          <>
            {/* Before the primary control and quieter than it: taking the review away is
                something a reader does with a page they have finished with, and asking is
                what the page is for. */}
            <ExportAction
              reviewId={reviewId}
              available={Boolean(review.data?.markdown_report)}
            />
            <AskAction
              status={status}
              expanded={showAsking}
              onToggle={() => setAsking((value) => !value)}
            />
          </>
        }
      />

      {review.data ? (
        <RevisionStrip
          review={review.data}
          currentId={reviewId}
          reviews={allReviews.data || []}
          branches={branchLineages.data || []}
          onNewRevision={() => newRevision.mutate()}
          starting={newRevision.isPending || run.running || running}
          startError={newRevision.error instanceof Error ? newRevision.error : null}
        />
      ) : null}
      <PassesRail chain={chainAround(reviewId, siblings.data || [])} currentId={reviewId} />

      {holding ? (
        <HoldBanner
          questionCount={openQuestions.length}
          nextRevision={caseRevision === undefined ? null : caseRevision + 1}
          onAnswer={() => openTab("questions")}
        />
      ) : null}

      <VerdictBand
        material={
          running ? (progress?.verdicts.filter((item) => item === true).length ?? 0) : material
        }
        cleared={
          running ? (progress?.verdicts.filter((item) => item === false).length ?? 0) : cleared
        }
        judged={running ? (progress?.judged ?? 0) : reviewed.length}
        total={running ? (progress?.total ?? 0) : reviewed.length}
        mode={holding || knownVerdicts === 0 ? "counted" : running ? "live" : "settled"}
        countLabel={running ? `of ${progress?.total ?? 0} judged` : "boundaries judged"}
        facts={facts}
      />

      {/* Sections of one record, not destinations. Arrow keys move between them because a
          tablist that only answers to clicks is a row of buttons wearing the wrong role —
          which the primitive now handles, along with the roving tab stop through the strip. */}
      <Tabs value={current} onValueChange={(value) => openTab(value as TabId)}>
        <TabsList aria-label="Review sections">
          {tabs.map((item) => (
            <TabsTrigger key={item.id} value={item.id}>
              {item.label}
              {item.count === undefined ? null : <i>{item.count}</i>}
            </TabsTrigger>
          ))}
        </TabsList>

        {tabs.map((item) => panel(item.id))}
      </Tabs>

      <AskPanel reviewId={reviewId} open={showAsking} onClose={() => setAsking(false)} />
    </div>
  );
}
