import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  type Dispatch,
  type ReactNode,
  type SetStateAction,
  useEffect,
  useRef,
  useState,
} from "react";
import { useNavigate } from "react-router-dom";

import { api, type Question, type Review } from "../../api";
import { cn } from "../../lib/cn";
import { Button } from "../../ui/button";
import { CheckIcon } from "../../ui/icons";
import { Label } from "../../ui/panel";
import { ErrorNotice, LiveRegion, Spinner } from "../../ui/states";
import { QuestionItem } from "./question";

/** Where a question stands, which is the only thing its marker has to draw. */
type Standing = "answered" | "skipped" | "open";

/**
 * What has been typed into a clarification round, and who holds it.
 *
 * A round is a form, and a form's contents cannot live in a component that three ordinary
 * gestures unmount. `useRoundAnswers` is called by the page and handed down, so collapsing
 * the card, walking the docket or reading the report all leave the answers where they were.
 */
export type RoundAnswers = {
  values: Record<string, string>;
  setValues: Dispatch<SetStateAction<Record<string, string>>>;
  skipped: Set<string>;
  setSkipped: Dispatch<SetStateAction<Set<string>>>;
  /**
   * Which questions the reviewer has taken off the menu. Tracked separately from the value
   * because "I will write my own" is chosen before there is anything written.
   */
  own: Set<string>;
  setOwn: Dispatch<SetStateAction<Set<string>>>;
};

export function useRoundAnswers(): RoundAnswers {
  const [values, setValues] = useState<Record<string, string>>({});
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const [own, setOwn] = useState<Set<string>>(new Set());
  return { values, setValues, skipped, setSkipped, own, setOwn };
}

/**
 * The mark in the gutter beside one question.
 *
 * Two states are shown at once and they are independent — a reviewer can have question 3
 * open while 1 and 2 are answered — so they are carried by different devices. Fill says
 * resolved, the ring says you are here. One device for both would make reopening an answered
 * question indistinguishable from arriving at an open one.
 */
function Marker({
  standing,
  current,
}: {
  standing: Standing;
  current: boolean;
}) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "mt-0.5 grid size-5 shrink-0 place-items-center rounded-full border transition",
        standing === "answered" && "border-ink bg-ink text-canvas",
        // Dashed, because a skip is a question deliberately left open rather than one that
        // has an answer in it.
        standing === "skipped" && "border-dashed border-rule-strong bg-sunken",
        standing === "open" && "border-rule bg-surface-2",
        current && "ring-2 ring-rule-strong ring-offset-2 ring-offset-surface",
      )}
    >
      {standing === "answered" ? <CheckIcon className="text-[11px]" /> : null}
    </span>
  );
}

/**
 * One question in the stack: open and answerable, or closed and one line.
 *
 * A closed row is not a placeholder. A resolved one carries the answer that was given, so the
 * round reads back as a record of what the reviewer said rather than as a progress bar over
 * questions they can no longer see; an unresolved one carries its question, so nothing
 * further down the round is a surprise waiting to happen.
 */
function RoundRow({
  question,
  standing,
  open,
  takeFocus,
  answer,
  onOpen,
  children,
}: {
  question: Question;
  standing: Standing;
  open: boolean;
  /**
   * Whether this row opening is something the reviewer did, rather than where the round
   * started. False on first paint, and it has to be: a page that grabs focus and scrolls
   * itself the moment it loads is a page that took the screen away from whoever opened it.
   */
  takeFocus: boolean;
  answer: string;
  onOpen: () => void;
  children: ReactNode;
}) {
  const body = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open || !takeFocus) return;
    // The control that was just clicked has unmounted with its row, so focus is on `<body>`
    // and a keyboard is nowhere. Moving it to the question that opened is the only reading
    // of "the round moved on" that also works without a mouse.
    body.current?.focus({ preventScroll: true });
    // `nearest`, so a row already on screen is left exactly where it is. Without this,
    // answering the fourth question of six expands the fifth somewhere below the fold and
    // the round looks like it stopped.
    body.current?.scrollIntoView?.({ block: "nearest" });
  }, [open, takeFocus]);

  if (open) {
    return (
      <li
        aria-current="step"
        className="grid grid-cols-[auto_1fr] items-start gap-x-3 border-t border-rule py-4 first:border-t-0"
      >
        <Marker standing={standing} current />
        {/* Mounted only while the row is open, so the expansion plays every time a row is
            opened rather than once for the life of the round. Nothing unmounts around it —
            the rows above and below keep their height — which is what stops the panel
            snapping to a new size the way the one-at-a-time swap did.

            `tabIndex` is here to be focused, never to be tabbed to: it is the landing place
            when the round moves itself, and the controls inside it are what a tab reaches. */}
        <div
          ref={body}
          tabIndex={-1}
          className="min-w-0 animate-expand outline-none"
        >
          {children}
        </div>
      </li>
    );
  }
  const said =
    standing === "answered"
      ? `answered: ${answer}`
      : standing === "skipped"
        ? "skipped explicitly"
        : "not yet answered";
  return (
    <li className="border-t border-rule first:border-t-0">
      <button
        type="button"
        onClick={onOpen}
        aria-label={`${question.text} — ${said}. Open to change it.`}
        // Bled into the gutter so the hover band reads as a target with room around the
        // words, rather than as a rectangle drawn flush against them.
        className="-mx-2 grid min-h-11 w-[calc(100%+1rem)] grid-cols-[auto_1fr] items-start gap-x-3 rounded-md px-2 py-3 text-left transition hover:bg-sunken/60"
      >
        <Marker standing={standing} current={false} />
        <span className="min-w-0">
          {/* A resolved row leads with what was said, so its question steps back to being the
              caption on an answer. An unresolved one has nothing else to lead with. */}
          <span
            className={cn(
              "block max-w-[54ch] text-sm leading-6",
              standing === "open" ? "text-ink" : "text-ink-3",
            )}
          >
            {question.text}
          </span>
          {/* The answer is clamped because one somebody wrote themselves is a paragraph as
              often as a sentence, and a closed row taller than the open one below it stops
              reading as closed. */}
          {standing === "open" ? null : (
            <span className="mt-0.5 line-clamp-2 max-w-[54ch] text-sm leading-6 text-ink">
              {standing === "skipped" ? "Skipped explicitly" : answer}
            </span>
          )}
        </span>
      </button>
    </li>
  );
}

/**
 * A clarification round, as a stack rather than as a slideshow.
 *
 * The round used to put one question on screen and swap it for the next, which needed a
 * stepper to say where you were, Previous and Next to move, and an animation to survive the
 * swap. All three were paying for the same decision: that answering a question should take it
 * away. It should not. The docket beside this settled the point already — *rows open in
 * place, and recording a decision opens the next row that wants a person while the row you
 * just decided stays listed* — and this is that, for questions.
 *
 * So an answered question collapses to the answer it was given and stays, the next one that
 * wants a person opens beneath it, and nothing leaves the screen. There is no travel to
 * animate because nothing travels, and no height to snap because nothing above or below the
 * opening row moves.
 *
 * Every answer lives here rather than in the question, because a closed row does not render
 * one. And it lives *above* here rather than in this component, because this component is
 * unmounted by three ordinary gestures — see `answers`.
 */
export function ClarificationRound({
  review,
  answers,
  className,
  bare = false,
}: {
  review: Review;
  /**
   * What has been typed into the round, held by the page.
   *
   * These three were `useState` here, and the round is rendered as `{open ? <round /> : null}`
   * inside a card on a docket. So collapsing the card, pressing `j`, and switching to Atlas,
   * Delta, Report or Ask each unmounted it and wiped every answer in the round, with no
   * warning and nothing to undo it with. The experience doc's rule is *never navigate away
   * from unsaved input*, and it had been enforced against the links inside the round and not
   * against the three controls around it.
   */
  answers: RoundAnswers;
  className?: string;
  /**
   * Drop the card and the title block, because something above already said both.
   *
   * The docket lists this round as its first item, under a header reading "1 question wants
   * an answer" and the sentence about what answering does. Rendered whole inside that, the
   * round restated its own name, its own subtitle and its own border: two nested cards and
   * two headings for one question.
   */
  bare?: boolean;
}) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const { values, setValues, skipped, setSkipped, own, setOwn } = answers;
  // Null until the reviewer moves it themselves. The round opens on the first row that wants
  // a person, and which row that is changes as the round is worked — so it is derived rather
  // than seeded, and a stored id cannot go stale against a round that came back shorter.
  //
  // This one stays here on purpose: it is where the round is, not what was typed into it, and
  // it is derived from the answers the moment they come back.
  const [opened, setOpened] = useState<string | null>(null);

  const isResolved = (questionId: string) =>
    skipped.has(questionId) || Boolean(values[questionId]?.trim());

  function standingOf(questionId: string): Standing {
    if (values[questionId]?.trim()) return "answered";
    return skipped.has(questionId) ? "skipped" : "open";
  }

  const answered = review.questions.filter((question) =>
    Boolean(values[question.id]?.trim()),
  );
  const resolved = review.questions.filter((question) =>
    isResolved(question.id),
  );
  const open =
    opened ??
    review.questions.find((question) => !isResolved(question.id))?.id ??
    null;

  /**
   * Answering starts a run, and the page follows it there.
   *
   * This used to be one POST that held the whole rejudgement open — every extant candidate
   * judged again, minutes of model work — and returned the finished review. That made the
   * browser tab the thing keeping the work alive: a reload, a closed laptop or a sixty-second
   * proxy timeout left a person unable to tell whether their answers had been recorded at
   * all. `api.ts` records that this exact failure was already fixed for the initial review,
   * and the clarification path still had it.
   *
   * So it answers with a run, and `/runs/{id}` is somewhere to come back to. The run page
   * hands over to the review the moment one is composed, which is the same hand-over the
   * first review already uses.
   */
  const resume = useMutation({
    mutationFn: (stop: boolean) =>
      api.answerRun(
        review.id,
        review.questions.map((question) => {
          const value = values[question.id]?.trim();
          const skip = skipped.has(question.id) || !value;
          return {
            question_id: question.id,
            status: skip ? ("skipped" as const) : ("answered" as const),
            value: skip ? null : value,
          };
        }),
        stop,
      ),
    onSuccess: async (run) => {
      // The run is listed under the branch and case this review belongs to, so both listings
      // that draw a lineage have a new entry to draw.
      await Promise.all([
        client.invalidateQueries({ queryKey: ["review-runs"] }),
        client.invalidateQueries({ queryKey: ["reviews"] }),
      ]);
      navigate(`/runs/${run.run_id}`);
    },
  });

  /**
   * Open the next row that still wants a person, having just settled this one.
   *
   * Forwards first, then round to anything left above: a reviewer who reopened question two
   * and answered it should be carried on to four rather than dropped at the bottom of a round
   * that is not finished.
   *
   * Where nothing else wants a person the settled row stays open, and that is the rule rather
   * than a special case — a row closes because another one opened, so with nothing to open
   * nothing closes. It matters most in the round of one, which is the common shape: picking
   * an answer there would otherwise fold the only question on screen and read as though the
   * form had swallowed it.
   */
  function openNextAfter(questionId: string) {
    const settled = (item: Question) =>
      item.id === questionId || isResolved(item.id);
    const order = review.questions;
    const index = order.findIndex((item) => item.id === questionId);
    const next =
      order.slice(index + 1).find((item) => !settled(item)) ??
      order.find((item) => !settled(item));
    setOpened(next?.id ?? questionId);
  }

  function choose(questionId: string, option: string) {
    setValues((current) => ({ ...current, [questionId]: option }));
    setOwn((current) => {
      if (!current.has(questionId)) return current;
      const next = new Set(current);
      next.delete(questionId);
      return next;
    });
    openNextAfter(questionId);
  }

  function chooseOwn(questionId: string) {
    // Reaching for the box is a reviewer saying none of these fit, so the row stays open —
    // there is nothing to move on from yet.
    setOpened(questionId);
    // Picking an option and then changing your mind should leave the box empty rather than
    // handing you the model's sentence to edit into something it never said.
    setValues((current) => ({ ...current, [questionId]: "" }));
    setOwn((current) => new Set(current).add(questionId));
  }

  function toggleSkip(questionId: string) {
    const skipping = !skipped.has(questionId);
    setSkipped((current) => {
      const next = new Set(current);
      if (skipping) next.add(questionId);
      else next.delete(questionId);
      return next;
    });
    // A skip is a decision, so it moves the round on the way an answer does. Undoing one is
    // the opposite, and leaves the row open where the reviewer can now answer it.
    if (skipping) openNextAfter(questionId);
    else setOpened(questionId);
  }

  const round = review.questions[0]?.round ?? 1;
  const total = review.questions.length;

  const Wrapper = bare ? "div" : "section";
  return (
    <Wrapper
      aria-labelledby={bare ? undefined : "clarification-heading"}
      aria-label={bare ? `Clarification round ${round}` : undefined}
      className={cn(
        "animate-fade",
        !bare && "overflow-hidden rounded-lg border border-rule bg-surface",
        className,
      )}
    >
      {bare ? (
        // One line, because the item this sits inside already carries the name and the
        // sentence. What it cannot carry is how far through the round you are.
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 px-4 pt-1 sm:px-5">
          <Label>Clarification round {round}</Label>
          <span className="font-mono text-[11.5px] tabular-nums text-ink-3">
            {resolved.length} of {total} resolved
          </span>
        </div>
      ) : (
        <header className="border-b border-rule px-4 py-5 sm:px-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <Label>Clarification round {round}</Label>
              <h2
                id="clarification-heading"
                className="mt-1.5 font-display text-lg font-semibold tracking-tight text-ink sm:text-xl"
              >
                The repository cannot answer these
              </h2>
              <p className="mt-2 max-w-[58ch] text-sm leading-6 text-ink-2">
                Answers complete this review's case revision, and the affected
                candidates are judged again. Asking again does not start another
                revision. Skip anything that should stay explicitly unknown.
              </p>
            </div>
            <div className="rounded-md border border-rule bg-surface-2 px-3 py-2 text-center">
              <div className="font-display text-lg font-semibold tabular-nums text-ink">
                {resolved.length}/{total}
              </div>
              <Label>resolved</Label>
            </div>
          </div>
        </header>
      )}

      <ol
        aria-label={`Questions in clarification round ${round}`}
        className="px-4 py-2 sm:px-5"
      >
        {review.questions.map((question) => (
          <RoundRow
            key={question.id}
            question={question}
            standing={standingOf(question.id)}
            open={question.id === open}
            // `opened` is null only until the reviewer touches the round, so this is exactly
            // "the round moved because somebody moved it" without a second piece of state.
            takeFocus={opened !== null}
            answer={values[question.id]?.trim() || ""}
            onOpen={() => setOpened(question.id)}
          >
            <QuestionItem
              question={question}
              affected={review.findings.filter((finding) =>
                question.candidate_ids.includes(finding.candidate.id),
              )}
              value={values[question.id] || ""}
              writingOwn={own.has(question.id)}
              skipped={skipped.has(question.id)}
              onChoose={(option) => choose(question.id, option)}
              onWriteOwn={() => chooseOwn(question.id)}
              onWrite={(value) =>
                setValues((current) => ({ ...current, [question.id]: value }))
              }
              onToggleSkip={() => toggleSkip(question.id)}
            />
          </RoundRow>
        ))}
      </ol>

      <footer className="border-t border-rule bg-sunken/40 px-4 py-3.5 sm:px-5">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <p className="text-xs leading-5 text-ink-3">
            Anything left blank is recorded as skipped. Nothing is inferred on
            your behalf.
          </p>
          {/* Two full-width rows on a phone rather than one squashed one: the longer of these
              labels is a sentence, and flex-wrap has no answer for a single item that is wider
              than the row it is in. */}
          <div className="grid gap-2 sm:flex sm:flex-wrap">
            <Button
              variant="secondary"
              className="min-h-11"
              disabled={resume.isPending}
              onClick={() => resume.mutate(true)}
            >
              Conclude with remaining uncertainty
            </Button>
            <Button
              className="min-h-11"
              disabled={resume.isPending}
              onClick={() => resume.mutate(false)}
            >
              {resume.isPending ? (
                <>
                  <Spinner label="" /> Saving context…
                </>
              ) : (
                "Save and rejudge"
              )}
            </Button>
          </div>
        </div>
        {/* Deliberately not the counter's own words. A live region that reads back a line
            already on screen is the same sentence twice to anyone using both. */}
        <LiveRegion>
          {`${answered.length} answered, ${skipped.size} skipped, ${total - resolved.length} still open.`}
        </LiveRegion>
        {resume.error ? (
          <div className="mt-3">
            <ErrorNotice
              error={resume.error}
              title="These answers were not recorded"
              action={
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={resume.isPending}
                  onClick={() => resume.mutate(resume.variables ?? false)}
                >
                  Try again
                </Button>
              }
            />
          </div>
        ) : null}
      </footer>
    </Wrapper>
  );
}
