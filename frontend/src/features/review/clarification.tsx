import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  type Dispatch,
  type ReactNode,
  type SetStateAction,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { api, type Question, type Review } from "../../api";
import { cn } from "../../lib/cn";
import { Button } from "../../ui/button";
import { ChevronDown } from "../../ui/icons";
import { Mark } from "../../ui/mark";
import { Label } from "../../ui/panel";
import { ErrorNotice, LiveRegion, Notice, Spinner } from "../../ui/states";
import { QuestionItem } from "./question";

/** Where a question stands, which is the only thing its marker has to draw. */
type Standing = "answered" | "skipped" | "open";

/**
 * What has been typed into a clarification round, and who holds it.
 *
 * A round is a form, and a form's contents cannot live in a component that three ordinary
 * gestures unmount. `useRoundAnswers` is called by the page and handed down, so collapsing
 * the card, walking the docket or reading the report all leave the answers where they were —
 * and the draft it reads is held above the page too, so leaving the page does as well. See
 * `RoundDraft` for where the words actually live and how long they live for.
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
  /**
   * What has been half-typed into a question's help panel, per question.
   *
   * Here for the same reason the answers are. The panel lives inside a question that steps
   * out of the way when you move to the next one, and somebody two sentences into asking
   * "what does this even mean" should find those two sentences when they come back.
   */
  asking: Record<string, string>;
  setAsking: Dispatch<SetStateAction<Record<string, string>>>;
  /**
   * Wording an agent offered that the reviewer took, per question, with who wrote it.
   *
   * Kept so the round can tell an accepted draft from a sentence somebody wrote. It is not
   * the value: the value is in `values`, under the reviewer's hand, and this is the thing
   * it is compared against when the round is submitted. Change one word and the comparison
   * fails, which is the point — the words are then theirs.
   */
  drafts: Record<string, { text: string; model: string }>;
  setDrafts: Dispatch<SetStateAction<Record<string, { text: string; model: string }>>>;
  /**
   * Which questions have their help panel open, per question.
   *
   * Open-or-closed is DOM state on a `<details>`, and the round only mounts a question's
   * children while its row is open — so a panel somebody deliberately opened, with two typed
   * sentences in it, came back shut and the sentences came back invisible. `asking` above
   * kept the words and this keeps the door they are behind.
   */
  helpOpen: Set<string>;
  setHelpOpen: Dispatch<SetStateAction<Set<string>>>;
  /**
   * Say that what is in the draft right now has been recorded, which is what takes the
   * unload guard off it.
   *
   * Not a reset: `RoundRecorded` in the docket reads these same values back to show what was
   * said while the rejudgement runs, and a draft thrown away on success would replace every
   * answer there with "recorded on this review's case revision". So the words stay and only
   * the claim on them changes.
   */
  settle: () => void;
};

/**
 * The draft itself, held for exactly as long as the page is loaded.
 *
 * Hoisting the round's state into the review page bought three gestures — collapsing the
 * card, walking the docket, switching surface — and nothing outside that page: the topbar's
 * links, the command palette, the back gesture and a reload all unmount the page and take ten
 * minutes of typing with them. The experience doc's rule is *never navigate away from unsaved
 * input*, without the qualification that it was only being enforced against the three
 * controls the hoist happened to be written for.
 *
 * So the draft lives in module state, the way `features/start/choice.ts` holds the start
 * page's half-made choice, and for the same reason: the lifetime wanted is the lifetime of
 * the loaded page. `sessionStorage` would hand a half-answered round back after a reload the
 * reviewer meant as a reset, and `localStorage` would hand it back next week — both do more
 * than was asked, in the one direction that was ruled out. The reload itself is guarded by
 * `beforeunload` below rather than survived.
 *
 * Keyed by question id and by nothing else, because a question id is unique across reviews:
 * the entries a round reads are exactly the ones it names, and no second review can pick up
 * the first's answers by sharing a slot with it.
 */
type RoundDraft = {
  values: Record<string, string>;
  skipped: Set<string>;
  own: Set<string>;
  asking: Record<string, string>;
  helpOpen: Set<string>;
  drafts: Record<string, { text: string; model: string }>;
  /**
   * The draft as it stood when a round was last recorded, or null before one was.
   *
   * A fingerprint rather than a flag, so a second round re-arms the guard the moment somebody
   * types into it. It is the same shape as the policy editor's `dirty`: what is on screen
   * against what has been filed.
   */
  filed: string | null;
};

function emptyDraft(): RoundDraft {
  return {
    values: {},
    skipped: new Set(),
    own: new Set(),
    asking: {},
    helpOpen: new Set(),
    drafts: {},
    filed: null,
  };
}

let remembered: RoundDraft = emptyDraft();

/**
 * Module state outlives a `render`, so without this one test answering a round would hand its
 * answers to every test after it in the file. `features/start/choice.ts` exports the same
 * escape for the same reason, and `start-page.test.tsx` calls it in `beforeEach`.
 */
export function forgetRoundAnswers(): void {
  remembered = emptyDraft();
}

/**
 * One slice of the draft, as state that writes itself back to the module on every change.
 *
 * The write happens inside the updater rather than in an effect, so the module and what is on
 * screen can never disagree: `choose` sets a value and clears `own` in one event, and an
 * effect would have both of them reading the same stale copy. React may run an updater twice
 * in development, and writing the same object twice is the same write.
 */
function useDraftSlice<K extends keyof RoundDraft>(
  key: K,
): [RoundDraft[K], Dispatch<SetStateAction<RoundDraft[K]>>] {
  const [value, setValue] = useState<RoundDraft[K]>(remembered[key]);
  const set = useCallback<Dispatch<SetStateAction<RoundDraft[K]>>>(
    (next) => {
      setValue((current) => {
        const resolved =
          typeof next === "function"
            ? (next as (previous: RoundDraft[K]) => RoundDraft[K])(current)
            : next;
        remembered[key] = resolved;
        return resolved;
      });
    },
    [key],
  );
  return [value, set];
}

export function useRoundAnswers(): RoundAnswers {
  const [values, setValues] = useDraftSlice("values");
  const [skipped, setSkipped] = useDraftSlice("skipped");
  const [own, setOwn] = useDraftSlice("own");
  const [asking, setAsking] = useDraftSlice("asking");
  const [helpOpen, setHelpOpen] = useDraftSlice("helpOpen");
  const [drafts, setDrafts] = useDraftSlice("drafts");
  const [filed, setFiled] = useDraftSlice("filed");

  // What is in the round, as one comparable value. `own` and `helpOpen` are left out: neither
  // is anything a person typed, and a menu taken off with nothing written in the box is not
  // work worth stopping a reload for.
  const fingerprint = JSON.stringify([values, [...skipped].sort(), asking]);
  const started =
    Object.values(values).some((value) => value.trim()) ||
    skipped.size > 0 ||
    Object.values(asking).some((value) => value.trim());

  const settle = useCallback(() => setFiled(fingerprint), [setFiled, fingerprint]);

  /**
   * The one way out of a half-answered round that no control on this page can intercept.
   *
   * A reload, a typed address, the back gesture — none of them go through a button, and a
   * browser only offers to stop them if something asks. `preventDefault` is the whole ask;
   * the wording is the browser's and cannot be set. Modelled on the policy editor, which
   * reasoned this out for the other long form in the product.
   *
   * Armed only where there is something to lose: nothing typed yet, or everything typed
   * already recorded, and a reload is exactly what the reader asked for.
   */
  useEffect(() => {
    if (!started || fingerprint === filed) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [started, fingerprint, filed]);

  return {
    values,
    setValues,
    skipped,
    setSkipped,
    own,
    setOwn,
    asking,
    setAsking,
    drafts,
    setDrafts,
    helpOpen,
    setHelpOpen,
    settle,
  };
}

/**
 * The mark in the gutter beside one question, which is the round's whole scanning device.
 *
 * It was a hand-drawn disc carrying two things at once — a fill for resolved, a ring for "you
 * are here" — and only one of the three standings could be seen. An answered question was ink
 * on white at 19.8:1; a skip was a dashed `--rule-strong` circle at 1.41:1 and an open one a
 * `--surface-2` circle at 1.04:1, so the round scanned as *done* against *not drawn yet* and
 * a skip — a decision somebody took — had no mark at all.
 *
 * Three drawn glyphs on the ink ramp now, from the vocabulary `ui/mark.tsx` already defines
 * and the Rounds surface already uses for these same three standings: `check` for an answer,
 * `slash` from the person's-own-move register for a skip, `pause` for a question nobody has
 * reached. Every one of them clears 5:1 on the panel in both themes, and the slice has one
 * mark system rather than two.
 *
 * The ring is gone rather than fixed. `design-system.md` killed a ring around a circle by
 * name — it is two concentric circles and says nothing — and the present is marked by taking
 * emphasis off everything else: the open row is the only expanded one on screen, it carries
 * `aria-current="step"`, and its question is full ink where a closed row's is `--ink-3`.
 */
function Marker({ standing }: { standing: Standing }) {
  return (
    <Mark
      shape={standing === "answered" ? "check" : standing === "skipped" ? "slash" : "pause"}
      className={cn(
        "mt-1 size-[15px]",
        standing === "answered" && "text-ink",
        standing === "skipped" && "text-ink-2",
        standing === "open" && "text-ink-3",
      )}
    />
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
        <Marker standing={standing} />
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
        //
        // `hover:bg-sunken` rather than `hover:bg-sunken/60`: sixty per cent of `#ebebeb` over
        // the panel's white composites to `#f2f2f2`, six values, which is not a state a reader
        // finds under a pointer. The ramp's own hover step is twenty values in light and
        // eighteen in dark, and it is the one this row is entitled to.
        className="-mx-2 grid min-h-11 w-[calc(100%+1rem)] grid-cols-[auto_1fr_auto] items-start gap-x-3 rounded-md px-2 py-3 text-left transition hover:bg-sunken"
      >
        <Marker standing={standing} />
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
        {/* The only thing at rest that says a closed row is a control. It carried a hover fill
            and nothing else — invisible to a touch reader — while the card above it and the
            help panel below it both announce themselves with a rotating chevron. Three
            disclosures on one screen, two of them announced. The open row keeps two columns,
            so the chevron's presence is itself the "this can be opened" signal. */}
        <ChevronDown aria-hidden="true" className="mt-1 size-4 shrink-0 text-ink-3" />
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
   * against the three controls around it. It is enforced against everything now: the draft
   * outlives the page as well as the card, and what no in-app state can survive — a reload, a
   * closed tab — is stopped by a `beforeunload` in the hook rather than lost quietly.
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
  const client = useQueryClient();
  const {
    values,
    setValues,
    skipped,
    setSkipped,
    own,
    setOwn,
    asking,
    setAsking,
    drafts,
    setDrafts,
    helpOpen,
    setHelpOpen,
    settle,
  } = answers;
  // Null until the reviewer moves it themselves. The round opens on the first row that wants
  // a person, and which row that is changes as the round is worked — so it is derived rather
  // than seeded, and a stored id cannot go stale against a round that came back shorter.
  //
  // This one stays here on purpose: it is where the round is, not what was typed into it, and
  // it is derived from the answers the moment they come back.
  const [opened, setOpened] = useState<string | null>(null);

  const isResolved = (questionId: string) =>
    skipped.has(questionId) || Boolean(values[questionId]?.trim());

  /**
   * The skip wins, because the skip is what gets sent.
   *
   * This read the value first, and the payload below reads the skip first — so typing an
   * answer and then pressing *Skip explicitly* collapsed the row to a tick and the sentence
   * you had written, over a payload recording `skipped` with no value at all. The screen and
   * the record disagreed about what a person had said, on the one question the charter is
   * most explicit about: a skipped question is recorded as skipped and nothing is inferred.
   *
   * `toggleSkip` deliberately keeps the words — undoing a skip hands them back rather than
   * making somebody retype them — so the precedence is what has to say which one counts.
   */
  function standingOf(questionId: string): Standing {
    if (skipped.has(questionId)) return "skipped";
    return values[questionId]?.trim() ? "answered" : "open";
  }

  // Through `standingOf` rather than straight off `values`, so the count agrees with the
  // gutter and with the payload: a question with words in it that was then skipped is one
  // skip, not one of each.
  const answered = review.questions.filter(
    (question) => standingOf(question.id) === "answered",
  );
  const resolved = review.questions.filter((question) =>
    isResolved(question.id),
  );
  const open =
    opened ??
    review.questions.find((question) => !isResolved(question.id))?.id ??
    null;

  /**
   * Answering starts a run, and the page stays where it is to watch it.
   *
   * This used to be one POST that held the whole rejudgement open — every extant candidate
   * judged again, minutes of model work — and returned the finished review. That made the
   * browser tab the thing keeping the work alive: a reload, a closed laptop or a sixty-second
   * proxy timeout left a person unable to tell whether their answers had been recorded at
   * all. `api.ts` records that this exact failure was already fixed for the initial review,
   * and the clarification path still had it. So it answers with a run.
   *
   * What it no longer does is navigate to that run's own page. The review being rejudged is
   * the review this reader is on — the run is a state of it, not another object — and going
   * to `/runs/{id}` swapped the heading, the findings and the surface for a progress list,
   * discarding the scroll position, the open finding and the filter on the way. The run's
   * progress is on this page now, and `/runs/{id}` is still a real address for anybody who
   * lands on it.
   *
   * The invalidations are the other half of why pressing this used to do nothing visible for
   * seconds. `["review", id]` is the review on screen, whose `answerable` has just become
   * false; nothing invalidated it, so the form stayed live over a round that had been taken.
   * `["review-runs"]` is what draws the progress. Neither is awaited: the 202 already said
   * the answers were accepted, and the acknowledgement belongs on the next frame rather than
   * behind a refetch. It used to await `["reviews"]` as well — the full listing, every review
   * with all its findings and its whole atlas — which is megabytes between the press and any
   * sign of it. Nothing here needs it: `useRunsBecomeReviews` refreshes the listings when a
   * run turns into a review, which is when they actually change.
   */
  const resume = useMutation({
    mutationFn: (stop: boolean) =>
      api.answerRun(
        review.id,
        review.questions.map((question) => {
          const value = values[question.id]?.trim();
          const skip = skipped.has(question.id) || !value;
          const draft = drafts[question.id];
          return {
            question_id: question.id,
            status: skip ? ("skipped" as const) : ("answered" as const),
            value: skip ? null : value,
            // Only where what is being submitted is, word for word, what the agent offered.
            // Change anything and the sentence is the reviewer's — which is why this is a
            // comparison rather than a flag set when they pressed the button. Pressing it
            // and then rewriting the whole thing is the ordinary way this is used.
            drafted_by: !skip && draft && draft.text.trim() === value ? draft.model : "",
          };
        }),
        stop,
      ),
    onSuccess: () => {
      // The words stay where they are — the docket reads them back while the rejudgement
      // runs — but they are on the record now, so a reload is no longer something to stop.
      settle();
      void client.invalidateQueries({ queryKey: ["review", review.id] });
      void client.invalidateQueries({ queryKey: ["review-runs"] });
    },
  });

  /**
   * The round has been taken, whether or not the review has come back saying so.
   *
   * `isPending` alone was the gate, and it ends at the 202 — which leaves a window, the length
   * of a refetch, where the form is live over a round the server already has.
   */
  const sent = resume.isPending || resume.isSuccess;

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

  /**
   * Take the agent's wording into the answer box, as the reviewer's to change.
   *
   * It lands exactly where a sentence they typed would, and it takes the menu off the same
   * way writing your own does — the wording is not one of the offered options, and leaving
   * an option selected under it would show a radio and a box disagreeing about the answer.
   *
   * The row deliberately does not move on. Everywhere else in the round, settling a question
   * opens the next one that wants a person; here it must not, because nothing has been
   * settled yet. The reader has words in front of them to read, edit or delete, and a round
   * that scrolled away at that moment would have answered the question for them.
   */
  function useDraft(questionId: string, text: string, model: string) {
    setOpened(questionId);
    setValues((current) => ({ ...current, [questionId]: text }));
    setOwn((current) => new Set(current).add(questionId));
    setSkipped((current) => {
      if (!current.has(questionId)) return current;
      const next = new Set(current);
      next.delete(questionId);
      return next;
    });
    setDrafts((current) => ({ ...current, [questionId]: { text, model } }));
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
        //
        // Two things changed about that line. It said "2 of 6 resolved", which folds the
        // round's one real distinction — an answer against a deliberate skip — into a single
        // number, while the split existed on the page only in the screen-reader region below:
        // the sighted reader was told less than the listening one about what pressing Save
        // would file. And it was set at 11.5px in the meta tier, a few hundred pixels under
        // the docket's own progress line, which says the same kind of fact at 12.5px with the
        // count in full ink. Same fact, same column, and the smaller treatment belonged to the
        // thing blocking everything below it. This is the docket's recipe, without a second
        // segment strip: the item above already carries one.
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 px-4 pt-1 sm:px-5">
          <Label>Clarification round {round}</Label>
          <span className="text-[12.5px] text-ink-2">
            <span className="font-mono font-semibold tabular-nums text-ink">
              {answered.length}
            </span>{" "}
            answered ·{" "}
            <span className="font-mono font-semibold tabular-nums text-ink">{skipped.size}</span>{" "}
            skipped ·{" "}
            <span className="font-mono font-semibold tabular-nums text-ink">
              {total - resolved.length}
            </span>{" "}
            open
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
              {/* Every candidate, not "the affected" ones: an answer is about intent, and
                  intent bears on all of them, which is what `select_rejudgements_node`
                  does. The narrower phrasing understated what pressing this costs. */}
              <p className="mt-2 max-w-[58ch] text-sm leading-6 text-ink-2">
                Answers complete this review's case revision, and every candidate is judged
                again — minutes of model work. Asking again does not start another revision.
                Skip anything that should stay explicitly unknown.
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

      {/* Inert from the press, not from the refetch.
          `isPending` ends when the 202 arrives, and the card only swaps to the recorded state
          once the invalidated `["review", id]` query comes back — so between the two the
          radios, the boxes and the skip toggles were live over a round that had already been
          taken, and both buttons re-enabled. A `fieldset` is the one element that turns a
          whole form off in one place, and every control inside it is drawn off by the
          `disabled:` recipes the design system already gives them. `min-w-0` because a
          `fieldset` defaults to `min-width: min-content`, which would let a long answer widen
          the column. */}
      <fieldset disabled={sent} className="min-w-0">
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
                review={review}
                value={values[question.id] || ""}
                writingOwn={own.has(question.id)}
                skipped={skipped.has(question.id)}
                asking={asking[question.id] || ""}
                helpOpen={helpOpen.has(question.id)}
                onChoose={(option) => choose(question.id, option)}
                onWriteOwn={() => chooseOwn(question.id)}
                onWrite={(value) =>
                  setValues((current) => ({ ...current, [question.id]: value }))
                }
                onAsking={(value) =>
                  setAsking((current) => ({ ...current, [question.id]: value }))
                }
                onHelpOpen={(next) =>
                  setHelpOpen((current) => {
                    if (current.has(question.id) === next) return current;
                    const updated = new Set(current);
                    if (next) updated.add(question.id);
                    else updated.delete(question.id);
                    return updated;
                  })
                }
                onUseDraft={(text, model) => useDraft(question.id, text, model)}
                onToggleSkip={() => toggleSkip(question.id)}
              />
            </RoundRow>
          ))}
        </ol>
      </fieldset>

      {/* `bg-surface-2`, not `bg-sunken/40`. Forty per cent of `#ebebeb` over the card
          composites to `#f7f7f7` in light — a sixth grey belonging to no ramp — and to
          `#141414` in dark, which is `--surface-2` arrived at by accident. A footer is a
          static strip set into a panel, which is the job the token is named for. */}
      <footer className="border-t border-rule bg-surface-2 px-4 py-3.5 sm:px-5">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          {/* Three sentences, because there are three things the press can cost and the copy
              named one of them. The second is the clause the unreachable header held and no
              reader has ever seen: skipping is a first-class move, not a failure to answer.
              The third belongs to the button beside it — *Conclude with remaining uncertainty*
              seals the case without another round, and it stood here with no sentence saying
              what it ends while the reversible button beside it had one. */}
          <p className="max-w-[62ch] text-xs leading-5 text-ink-3">
            Anything left blank is recorded as skipped. Nothing is inferred on
            your behalf. Skip anything that should stay explicitly unknown; concluding files
            the review as it stands, with these questions unanswered.
          </p>
          {/* Two full-width rows on a phone rather than one squashed one: the longer of these
              labels is a sentence, and flex-wrap has no answer for a single item that is wider
              than the row it is in. */}
          <div className="grid gap-2 sm:flex sm:flex-wrap">
            {/* The pending state goes on the button that was pressed. Both share one
                `isPending`, and only the primary ever drew it — so pressing Conclude drew the
                spinner on its neighbour and said "Saving context…", which is the other action.
                `resume.variables` already carries which one is in flight; it was read for the
                retry and nowhere else. */}
            <Button
              variant="secondary"
              className="min-h-11"
              disabled={sent}
              onClick={() => resume.mutate(true)}
            >
              {resume.isPending && resume.variables === true ? (
                <>
                  <Spinner label="" /> Filing this review…
                </>
              ) : (
                "Conclude with remaining uncertainty"
              )}
            </Button>
            <Button className="min-h-11" disabled={sent} onClick={() => resume.mutate(false)}>
              {resume.isPending && resume.variables === false ? (
                <>
                  <Spinner label="" /> Saving context…
                </>
              ) : (
                "Save and rejudge"
              )}
            </Button>
          </div>
        </div>
        {/* Said on the frame the 202 lands on, rather than when the refetched review gets
            here. The mutation's own comment argues that the invalidations are deliberately not
            awaited because the acknowledgement belongs on the next frame — and there was no
            acknowledgement, so for the length of a refetch the only thing that had happened
            was that two buttons went grey. */}
        {resume.isSuccess ? (
          <div className="mt-3">
            <Notice tone="working">
              {resume.variables
                ? "Your answers are recorded on this review's case revision, and the review is being filed as it stands."
                : "Your answers are recorded on this review's case revision. Every candidate is being judged again."}
            </Notice>
          </div>
        ) : null}
        {/* The same three facts as the counter above, and deliberately so now that the counter
            carries them: a count that changes only on screen tells a listener nothing, and a
            live region is how a change gets announced. The wording differs because a listener
            hearing the round move should hear a sentence, not a row of separators. */}
        <LiveRegion>
          {resume.isSuccess
            ? "Recorded. Every candidate is being judged again."
            : `${answered.length} answered, ${skipped.size} skipped, ${total - resolved.length} still open.`}
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
