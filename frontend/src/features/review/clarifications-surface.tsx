import { useQuery } from "@tanstack/react-query";
import { useMemo, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { api, type Review, type ReviewConversation } from "../../api";
import { absoluteTime, plural } from "../../lib/format";
import { Button } from "../../ui/button";
import { ChevronDown } from "../../ui/icons";
import { Mark } from "../../ui/mark";
import { Label, Panel, PanelBody, PanelHeader } from "../../ui/panel";
import { ErrorNotice, Notice, Skeleton } from "../../ui/states";
import { ConversationExchange } from "./conversation-thread";
import { awaitsAnswers } from "./docket-rules";

type Answer = Review["case"]["answers"][number];
type Question = Review["questions"][number];

/**
 * One round of asking, as a round: which one it was, and every question with what was said.
 *
 * `round` and `case_revision` together are the address. A review keeps one case revision
 * however many rounds it asks, so `round` is exact inside a review and repeats across the
 * life of a case — review 2's round 1 and review 3's round 1 are both "round 1" on the same
 * list of answers, and grouping on it alone would fold two different conversations into one.
 */
type Round = {
  key: string;
  round: number;
  revision: number;
  answers: Answer[];
  /** The questions still open, which is at most one round and always the last. */
  open: Question[];
};

/**
 * Every round this review has been through, oldest first, with the open one last.
 *
 * Answers arrive in the order they were recorded and carry their own address, so this is a
 * grouping rather than a reconstruction. An answer stamped with revision zero was recorded
 * before the stamp existed; it is grouped under the case rather than guessed into a round.
 */
export function roundsOf(review: Review): Round[] {
  const byKey = new Map<string, Round>();
  for (const answer of review.case.answers) {
    const revision = answer.case_revision ?? 0;
    const round = answer.question.round;
    const key = `${revision}:${round}`;
    const existing = byKey.get(key);
    if (existing) existing.answers.push(answer);
    else byKey.set(key, { key, round, revision, answers: [answer], open: [] });
  }
  const rounds = [...byKey.values()].sort(
    (left, right) => left.revision - right.revision || left.round - right.round,
  );
  // Only the questions that have not been answered. `review.questions` is not "the open
  // round" — it is whatever the snapshot was carrying, and a review sealed by *Conclude with
  // remaining uncertainty* (or by hitting the round ceiling, or by CI) goes straight to
  // `seal_case` without passing through `generate_questions`, so it keeps the round it has
  // just answered. Taken as open, that drew the same round twice: once with the reviewer's
  // answers, and once beneath it with every question marked "Asked, and never answered."
  const answered = new Set(review.case.answers.map((answer) => answer.question.id));
  const open = review.questions.filter((question) => !answered.has(question.id));
  if (open.length) {
    rounds.push({
      key: "open",
      round: open[0].round,
      revision: review.case.revision,
      answers: [],
      open,
    });
  }
  return rounds;
}

/**
 * The whole clarification history of this review, in one place.
 *
 * It existed nowhere. Answers were on the review all along — every one of them carrying the
 * question it replies to, who answered and when — and the only surface that rendered them was
 * the per-candidate judgement drawer, which shows the ones bearing on the candidate you have
 * open. Everywhere else they were a count: "6 answers recorded so far". So a reviewer who had
 * been asked twice had no way to see what the first round asked or what they had said to it,
 * and no way to tell that the round in front of them was a second one at all.
 */
/**
 * What became of a question this record still carries unanswered.
 *
 * Four different things, and the surface used to say one of them. "Asked, and never
 * answered" is true only of a review that reached its end with the question outstanding —
 * and it was printed on the commonest case of all: a round somebody had *just* answered.
 * The waiting snapshot is filed by `record_waiting_review` before `revise_case` writes the
 * answers to the case, so a waiting record can never contain the answers to its own
 * questions. Reading their absence as "never answered" therefore says the opposite of what
 * happened, on exactly the records `SupersededNotice` exists to serve.
 */
function standingOf(review: Review): ReactNode {
  if (awaitsAnswers(review)) {
    // The sentence named a destination and was not one: nothing anywhere on this surface was
    // clickable, and this is the whole of what it offered a reader who arrived because the
    // review said it was waiting on them. The docket is what a bare `/reviews/:id` means, so
    // the route already existed and only the link was missing. Underlined in the grey ramp
    // rather than in `--mark`: the accent's budget is spent elsewhere, and an underline with
    // a weight is what the rest of the system uses for "this leads somewhere".
    return (
      <>
        Waiting for an answer, on{" "}
        <Link
          to={`/reviews/${review.id}`}
          className="font-semibold text-ink underline decoration-rule-strong underline-offset-4 transition hover:decoration-ink"
        >
          the docket
        </Link>
        .
      </>
    );
  }
  if (review.status === "cancelled") {
    return "This round was stopped before it was answered.";
  }
  if (review.status === "awaiting_answers") {
    // Closed, and that is the whole of what this record can say. It said "Answered. Every
    // candidate is being judged again against it" for the case with no successor filed, on
    // the reasoning that stopping a review files one immediately — which is true of
    // `cancel(review_id)` and of nothing else. Three other endings leave exactly this shape:
    // *Conclude with remaining uncertainty*, which seals without rejudging anything;
    // `cancel_run`, which stops the thread and binds nothing; and `abandon_running`, which
    // marks a killed process's row failed and binds nothing. The last two are permanent, so
    // the sentence would have claimed judging was in progress for ever.
    //
    // What became of it is not inferable from what became of the review either — see the
    // sibling comment in `hingeFootnote`. So it says where to look, or that it cannot.
    return review.superseded_by
      ? "This round is closed. What became of it is on the record that replaced this one."
      : "This round is closed. This record was filed when it was asked, so what was said is not on it.";
  }
  return "Asked, and never answered.";
}

/**
 * What was worked out about one question, kept beside what was answered to it.
 *
 * A reader who could not make sense of a question asks an agent about it in the round, and
 * what comes back is the reasoning behind the answer they then gave — which finding was
 * waiting, what the code turned out to say, what each answer would have changed. Thrown
 * away when the round closed, the record would keep the reply and lose the reason for it.
 *
 * Closed, and absent where there is nothing. The answer is the record; this is the working.
 */
function QuestionThread({
  thread,
  review,
}: {
  thread: ReviewConversation;
  review: Review;
}) {
  if (!thread.messages.length) return null;
  return (
    <details className="group mt-2 border-t border-rule pt-2">
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2">
        {/* `as="span"`, because `<summary>` takes phrasing content and `Label` is a `div` by
            default — the invalid nesting its `as` prop exists to prevent. */}
        <Label as="span" className="min-w-0 flex-1">
          {plural(thread.messages.length, "question")} asked about this question
        </Label>
        <ChevronDown className="size-4 shrink-0 text-ink-3 transition group-open:rotate-180" />
      </summary>
      <ol className="mt-2 grid gap-4">
        {thread.messages.map((message, index) => (
          <li key={`${message.asked_at}-${index}`}>
            <ConversationExchange message={message} review={review} />
          </li>
        ))}
      </ol>
    </details>
  );
}

export function ClarificationsSurface({ review }: { review: Review }) {
  const rounds = useMemo(() => roundsOf(review), [review]);
  /**
   * The threads this snapshot holds, by the question each is about.
   *
   * This snapshot's, and deliberately not the lineage's. A conversation is filed against
   * the review that was asking, and a review is immutable — so a round answered on an
   * earlier snapshot keeps its working there, reachable from the revision rail, rather than
   * being copied forward into a record that did not hold it.
   */
  const conversations = useQuery({
    queryKey: ["conversations", review.id],
    queryFn: () => api.conversations(review.id),
  });
  const threads = useMemo(() => {
    const byQuestion = new Map<string, ReviewConversation>();
    for (const item of conversations.data ?? []) {
      if (item.question_id) byQuestion.set(item.question_id, item);
    }
    return byQuestion;
  }, [conversations.data]);

  /**
   * The working under one question, or the space where it is about to be.
   *
   * The disclosure used to be drawn only where a thread had already arrived, so a fetch that
   * was still in flight — or one that had failed — looked exactly like a question nobody had
   * asked about. That is the record making a false claim about itself, quietly, which is the
   * one thing the surface exists not to do. The failure is reported once for the surface,
   * under the header, because there is one request behind every one of these.
   */
  const working = (questionId: string) => {
    if (conversations.isLoading) return <Skeleton className="mt-2 h-3 w-40" />;
    const thread = threads.get(questionId);
    return thread ? <QuestionThread thread={thread} review={review} /> : null;
  };

  if (!rounds.length) {
    return (
      <Panel>
        <PanelHeader
          title="Rounds"
          description="Every question this case has been asked, and what was said to it."
        />
        <PanelBody>
          <Notice>
            {/* The second clause only where it is true. A review asks only where a judgement
                turns on something the repository cannot settle — but "this one settled every
                candidate on the evidence" is a claim about how it ended, and a failed review
                reaches here too: `_record_failure` files its snapshot with no questions at
                all. It asked nothing because it stopped, not because nothing needed asking. */}
            <p className="max-w-[62ch] text-[13px] leading-6 text-ink-2">
              Nothing has been asked. A review asks only where a judgement turns on something
              the repository cannot settle
              {review.status !== "completed"
                ? "."
                : review.findings.some((finding) => finding.hinge)
                  ? ", and this one asked nothing — but some candidates are still held, with uncertainty that never became a question."
                  : ", and this one settled every candidate on the evidence."}
            </p>
          </Notice>
        </PanelBody>
      </Panel>
    );
  }

  return (
    /* A panel, like every other surface in this review. This one returned a bare `<div>` on
       the canvas, so the tab whose whole subject is what the review is waiting on was the only
       one that did not read as a surface and the only one that lost its own name — a reader
       arriving from Report had to infer the heading from the tab they had pressed. The intro
       moves into the header's description slot, which also gives the column one right edge:
       the measure used to be on the paragraph alone while the rounds beneath it ran the full
       1168px, so the surface had two right edges 32px apart. */
    <Panel>
      <PanelHeader
        title="Rounds"
        description={
          <>
            {/* "on this case" and not "in this review", because that is what it is. A case
                carries its answers forward across revisions — a second review of the same
                repository continues the newest case — so this list is the case's clarification
                history, and the rounds above the last group belong to the reviews that asked
                them. Claiming it was one review's history put "3 rounds" directly above a
                sentence saying a review asks at most twice, with the list on screen
                contradicting it. */}
            {rounds.length === 1
              ? "One round of questions on this case, and what was said to it."
              : `${plural(rounds.length, "round")} of questions on this case, oldest first.`}{" "}
            A review asks at most twice; after its second round it is filed as it stands,
            whatever is still uncertain. A later review continues the same case.
          </>
        }
      />
      <PanelBody className="grid gap-4">
        {/* One request draws every disclosure on this surface, so its failure is reported
            once, here, rather than under each question it silently emptied. */}
        {conversations.error ? (
          <ErrorNotice
            error={conversations.error}
            title="The working behind these answers could not be loaded"
            action={
              <Button variant="secondary" size="sm" onClick={() => void conversations.refetch()}>
                Try again
              </Button>
            }
          />
        ) : null}

        {rounds.map((entry) => (
          <section key={entry.key} className="overflow-hidden rounded-md border border-rule">
            {/* `bg-surface-2`: a static strip set into a panel, which is what this is, rather
                than `bg-sunken/50` — half of the inset grey over a white panel is a value on
                no ramp in light and a different one again in dark. */}
            <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-b border-rule bg-surface-2 px-4 py-2.5 sm:px-5">
              {/* A heading, and the round number set as the identifier it is.
                  Three `<section>`s with no heading in any of them meant a screen-reader user
                  could not move between rounds at all, and the number — which the experience
                  doc argues is the event, the thing saying being asked twice is not the first
                  time happening again — was set in the quietest tier the product has, at the
                  same weight as the word "resolved". `h3` because `PanelHeader` above is the
                  surface's `h2`.

                  The open round carries no revision, because it has not opened one: a review's
                  revision is opened by `revise_case` when it records an answer, so until then
                  `review.case.revision` is still the number of the review before it — and
                  printing it here headed the open round with the previous review's revision,
                  identical to a group already on screen. */}
              <h3 className="min-w-0">
                <span className="font-mono text-sm font-semibold tabular-nums text-ink">
                  Round {entry.round}
                </span>
                {entry.open.length || !entry.revision ? null : (
                  <Label as="span" className="ml-2">
                    case revision {entry.revision}
                  </Label>
                )}
              </h3>
              <span className="font-mono text-[11.5px] tabular-nums text-ink-3">
                {entry.open.length
                  ? `${plural(entry.open.length, "question")}${awaitsAnswers(review) ? " open" : ""}`
                  : `${plural(entry.answers.length, "answer")} recorded`}
              </span>
              {/* Once for the round, because that is what it is a fact about. `standingOf`
                  takes the review, not the question, so under a round with four open
                  questions it printed the identical sentence four times as though each row
                  had its own standing. */}
              {entry.open.length ? (
                <p className="w-full max-w-[62ch] text-[13px] leading-6 text-ink-2">
                  {standingOf(review)}
                </p>
              ) : null}
            </header>

            <ol className="grid gap-2 px-4 py-3 sm:px-5">
              {entry.answers.map((answer) => (
                <li
                  key={answer.question.id}
                  className="rounded-md border border-rule bg-surface-2 px-3 py-2.5"
                >
                  <div className="flex items-start gap-2">
                    {/* `slash` for a skip, from the register `ui/mark.tsx` keeps for a
                        person's own move, and `pause` left to the open question below. Both
                        wore `pause` at the same size in the same ink, so a decision somebody
                        took and a question nobody has reached were the same mark — and the
                        charter treats an explicit unknown as a first-class record. The
                        skipped one sits a step up the ink ramp for the same reason. */}
                    <Mark
                      shape={answer.status === "skipped" ? "slash" : "check"}
                      className={
                        answer.status === "skipped"
                          ? "mt-0.5 size-[13px] shrink-0 text-ink-2"
                          : "mt-0.5 size-[13px] shrink-0 text-ink-3"
                      }
                    />
                    <div className="min-w-0">
                      <p className="max-w-[62ch] text-[13px] font-semibold leading-6 text-ink wrap-anywhere">
                        {answer.question.text}
                      </p>
                      <p className="mt-0.5 max-w-[62ch] text-[13px] leading-6 text-ink-2 wrap-anywhere">
                        {answer.status === "skipped" ? (
                          <span className="text-ink-3">
                            Recorded as skipped — deliberately left unknown.
                          </span>
                        ) : (
                          answer.value
                        )}
                      </p>
                      <p className="mt-1 text-[11px] text-ink-3">
                        {answer.actor} · {absoluteTime(answer.answered_at)}
                        {/* Said where it is true and nowhere else. These are words an agent
                            offered and this person submitted without changing one of them —
                            still their answer, because they read it and could have written
                            anything, and still worth a reader knowing that nobody typed it.
                            Anything they edited is not marked, because then they did. */}
                        {answer.drafted_by ? (
                          <> · wording drafted by {answer.drafted_by}, submitted unchanged</>
                        ) : null}
                      </p>
                      {working(answer.question.id)}
                    </div>
                  </div>
                </li>
              ))}

              {/* `Notice` rather than the held hue. Amber means one thing in this workbench —
                  a verdict waiting on a person — and an open question is the workspace asking
                  rather than a verdict at all. `docs/design-system.md` and the palette test
                  both hold that line; `working` is the tone for the workspace asking.
                  `--sunken` is where that tone lives, so the emphasis this block needs — it is
                  the item the whole review is stopped on — comes from the title in full ink
                  and a mark at the size a reader is meant to find, rather than from a ground
                  brighter than the settled rows above it. */}
              {entry.open.map((question) => (
                <li key={question.id}>
                  <Notice tone="working" title="Open question">
                    <div className="flex items-start gap-2">
                      <Mark shape="pause" className="mt-0.5 size-4 shrink-0 text-ink" />
                      <div className="min-w-0">
                        <p className="max-w-[62ch] text-[13px] font-semibold leading-6 text-ink wrap-anywhere">
                          {question.text}
                        </p>
                        {working(question.id)}
                      </div>
                    </div>
                  </Notice>
                </li>
              ))}
            </ol>
          </section>
        ))}
      </PanelBody>
    </Panel>
  );
}
