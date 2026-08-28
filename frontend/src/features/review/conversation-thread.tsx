import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useState } from "react";

import { api, type Review, type ReviewConversation } from "../../api";
import { shortId, splitQualified } from "../../lib/format";
import { Tag } from "../../ui/badge";
import { Button } from "../../ui/button";
import { CheckIcon, ChevronDown } from "../../ui/icons";
import { Label } from "../../ui/panel";
import { Citations, ModelProse, Prose, plainProse, type Citation } from "../../ui/prose";
import { KeyCap } from "../../ui/shortcuts";
import { Spinner } from "../../ui/states";
import { Attribution } from "./finding-detail";
import { InvestigationTranscript, investigationSummary } from "./investigation";

/**
 * The findings this exchange may cite by identifier, as a lookup.
 *
 * A model writes `[candidate_…]` into its sentences because the listing it was given leads
 * every finding with one — `CANDIDATE_REFERENCE` in `ui/prose.tsx` carries the whole argument.
 * This is the half of the repair that knows what those identifiers are: the review is right
 * here, and one `Map` over its findings turns a key back into the name the sentence needed.
 *
 * A candidate always has participants — the domain refuses one without them — so the guard
 * below is the type's rather than a case anybody has seen. A finding this review does not hold
 * resolves to nothing, and the reference says so rather than inventing a name for it.
 *
 * Keyed on `review` and not on `review.findings`: a review is an immutable record fetched with
 * `staleTime: Infinity`, so its identity is stable for as long as the page is.
 */
function useCitedFindings(review: Review) {
  return useMemo(() => {
    const byId = new Map(review.findings.map((finding) => [finding.candidate.id, finding]));
    return (candidateId: string): Citation | undefined => {
      const finding = byId.get(candidateId);
      const qualified = finding?.candidate.participants[0]?.qualified_name;
      if (!finding || !qualified) return undefined;
      return {
        name: splitQualified(qualified).leaf,
        // The whole name and the claim, because a leaf alone can be two findings. The summary
        // goes through `plainProse` for the same reason the citation chip's does: a title is a
        // string, so a delimiter left standing in it is read out as a backtick.
        title: `${qualified} — ${plainProse(finding.candidate.summary)}`,
      };
    };
  }, [review]);
}

/**
 * One exchange, drawn the same way wherever it is read.
 *
 * Two surfaces hold these now — the Ask tab, over the whole review, and the panel under a
 * clarification question the review is waiting on — and they were never going to stay the
 * same drawn twice. What a reader has to be able to do in both is the same thing: read the
 * answer, open what it looked up, and follow a citation to the finding it rests on.
 */
export function ConversationExchange({
  message,
  review,
  onOpen,
  onUseAnswer,
}: {
  message: ReviewConversation["messages"][number];
  review: Review;
  onOpen?: (candidateId: string) => void;
  /**
   * What "use this wording" does, where the surface has somewhere to put it. Absent on the
   * Ask tab, which has no answer box — and absent is why the control is not drawn there
   * rather than drawn and inert.
   */
  onUseAnswer?: (text: string) => void;
}) {
  const suggested = message.answer.suggested_answer?.trim();
  const [taken, setTaken] = useState(false);
  const cited = useCitedFindings(review);
  return (
    /* Around the whole exchange rather than around the answer, because three blocks in here
       are drawn from strings that can carry an identifier: the answer, the wording offered
       under it, and the reader's own question — which is regularly a line pasted back out of
       an earlier answer. */
    <Citations find={cited} onOpen={onOpen}>
      <div className="grid gap-2">
        <div className="rounded-md border border-rule bg-surface-2 px-3 py-2.5">
          <Label>Question</Label>
          {/* `wrap-anywhere` on both halves: a question is regularly a qualified name with a
              few words around it, and an answer quotes paths back. One token wider than a
              phone and nothing else in the panel can help.

              `max-w-[62ch]` because nothing in this exchange capped its measure, and on the Ask
              surface it is drawn inside the page's whole 76rem column — **about 163 characters a
              line**, the longest prose in the product at the loosest measure.

              Neither number in that sentence is the column's, and the gap is four subtractions
              rather than one. 76rem is 1216px and the route really does draw at it; it spends
              48px on its `sm:p-6`, leaving 1168px for the `Panel`; the panel spends two hairlines
              and `PanelBody` spends 40px on its `sm:px-5`, leaving 1126px; and the box around the
              question spends a last 26px on its `px-3` and two hairlines. So an uncapped `<p>` in
              it measures **1100px** — the same "a measure is a property of the text and not of
              the box around it" the policy cap in `features/review/finding-detail.tsx` is a
              paragraph about. This comment has now been wrong twice by skipping boxes: it said
              1216 less 26, which is 1190, and then 1168 less 26, which is 1142 and left out the
              panel body the exchange is actually inside. Every width here is read off the live
              Ask panel at 1440x960 with `getBoundingClientRect`, and so is every box between the
              paragraph and the document, which is the check the arithmetic kept failing.

              163 is a character count rather than the 62 of the cap: a `ch` is the advance of
              the zero, which is wider than a character of body text, so `62ch` at 14px held
              about 83 under Onest, where it was 577.22px. IBM Plex Sans's zero is 0.600em, so
              the same declaration is 520.80px now and every figure in this paragraph is a
              reading of the old face. Both counts are a `Range` per
              character in a headless Chromium serving the built stylesheet, each line counted
              from its own first visible character to the next line's and averaged over full lines
              only — the sweep `ui/prose.tsx` states in full and `ui/font.test-metrics.ts` keeps
              the per-character reading of. Nothing in the store records a question, so there is
              no corpus of the right kind to sweep; this one is the 139 recorded judgement
              rationales of 400 characters or more in the workspace store, run through this very
              element with its own cap taken off and put back: **162.69** at 1100px and **83.01**
              at 577.22px. The narrow figure is what says the method is the same one — the earlier
              sweep read 82.89 and 83.13 for it, over two other corpora — and the wide figure is
              the one that moved, because 169 was measured in a box 42px wider than this
              paragraph has ever been drawn in. */}
          {/* Through `Prose` even though these are the reader's own typed words, not the
              model's. It is the top half of a pair whose bottom half is rendered, and rendering
              one and not the other is the visible inconsistency — a reviewer who types a
              backtick around a name means it the way the model does. */}
          <p className="mt-1 max-w-[62ch] text-sm leading-6 text-ink wrap-anywhere">
            <Prose>{message.question}</Prose>
          </p>
        </div>
        {/* `bg-sunken`, not `bg-sunken/50`: half of `--sunken` over the panel composites to
            `#f3f2ef` in light, a grey on no ramp and barely a step off the surface under it,
            and to `#23211f` in dark, which is very nearly `--surface-2` arrived at by accident.
            This is a quiet inset, which is the job `--sunken` is named for, in both themes. */}
        <div className="rounded-md border border-rule bg-sunken px-3 py-2.5">
          {/* The model's voice, named and set at the reading size — which is the design system's
              central claim and the one place in the product that ignored it. This was 14px of
              `--ink-2` under a generic 10px "Agent", so a reader could not tell which model had
              answered and the paragraph read as chrome rather than as the judged voice. The
              identity is in the payload and is already trusted enough to be stamped onto the
              answer the reviewer submits, and `Attribution` is the line the finding and the
              report already use for exactly this. */}
          <Attribution voice="Answered" by={message.answer.model_identity || "model not recorded"} />
          {/* Through `ModelProse`, which is where the reading size now lives. This block had the
              same claim on it as the two above — the model's voice, named and set at the reading
              size — and set it at `62ch` against the finding's `58ch` and the synopsis's `46ch`,
              with no sentence split on any answer however long. An answer here is the same kind
              of paragraph a judgement is, from the same models under the same "prose" contract,
              so it is drawn the same way and the measure is argued once.

              The contract also asks the model, in as many words, to "name one by its backticked
              participant, the way the listing does", and the listing it is fed on the way in
              backticks every line. So a span here is guaranteed rather than incidental, and
              `ModelProse` renders it. */}
          <ModelProse className="mt-1">{message.answer.text}</ModelProse>

          {suggested && onUseAnswer ? (
            /* Words offered for the reader's own box, and nothing more than offered.
               Deliberately below the answer rather than beside it: what the agent worked out
               is the thing they came for, and a draft presented first would read as the
               conclusion with the reasoning as footnotes.

               It is also why the button says "put this in my answer" rather than "accept".
               Nothing here submits: the text lands in the box, they change it or delete it,
               and they submit the round. */
            <div className="mt-2.5 border-t border-rule pt-2.5">
              <Label>Wording you could use</Label>
              {/* `text-ink-2`, under an answer that now carries the stronger ink. Placement
                  already obeyed the argument above — the reasoning is what the reader came for
                  — and the weights reversed it: the explanation was secondary and the
                  ready-made sentence beneath it was full ink, so the eye landed on the words to
                  submit before the reasons for them, under a panel whose own doc says the agent
                  must never decide the answer. */}
              {/* Same model, same call, same contract as the answer above — and deliberately
                  not the same treatment, which is the correction this comment carries. It said
                  "so the same treatment" while setting 14px `--ink-2` at `62ch` beside a
                  `ModelProse` block at 16px full ink, so it described the one thing it did not
                  do, in a file where the block above it had just been converged.

                  It stays subordinate on the argument the comment directly above already makes:
                  the reasoning is what the reader came for and the ready-made sentence is
                  offered under it, so promoting this to the reading size and full ink puts the
                  eye on the words to submit before the reasons for them — the exact inversion
                  that was corrected here. There is a second reason it cannot go through
                  `ModelProse` even if somebody wanted it to: the reading size is the one thing
                  that marks the model's voice, and two blocks at it inside one bubble say the
                  answer and the draft are two utterances rather than one answer and an offer
                  taken out of it. `ui/design-system.test.ts` holds that line for the whole tree.

                  What is the same is the rendering, and it always was: `Prose` draws the quoted
                  names, because the raw string is what the button below writes into the
                  reviewer's own box and a delimiter left standing here travels into the record
                  as part of their answer. `62ch` is 14px's measure in this file, shared with the
                  reviewer's own question above — the pairing this block belongs to. */}
              <p className="mt-1 max-w-[62ch] whitespace-pre-line text-sm leading-6 text-ink-2 wrap-anywhere">
                <Prose>{suggested}</Prose>
              </p>
              <div className="mt-1.5 flex flex-wrap items-center gap-2">
                {/* The tick is the whole confirmation, and it is the device `CopyButton` already
                    uses. The press writes into a box that is above this in the DOM and does not
                    yet exist, so the only thing that visibly happened was the panel dropping a
                    hundred pixels; the control the reader was looking at said nothing at all. */}
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    onUseAnswer(suggested);
                    setTaken(true);
                    window.setTimeout(() => setTaken(false), 1500);
                  }}
                >
                  {taken ? (
                    <>
                      <CheckIcon aria-hidden="true" className="size-3.5" /> In your answer box
                    </>
                  ) : (
                    "Put this in my answer"
                  )}
                </Button>
                <span className="text-[11px] leading-5 text-ink-2">
                  It goes in the box for you to change. Nothing is submitted until you do it.
                </span>
              </div>
            </div>
          ) : null}

          {message.answer.investigation ? (
            /* No bleed and no full-width rule: this sits inside a bubble whose walls one
               would burst through. Closed, because the answer is what the reader came for and
               this is the working behind it. */
            <details className="group mt-2 border-t border-rule pt-2">
              <summary className="flex min-h-11 list-none items-center gap-2">
                {/* `as="span"`, because `<summary>` takes phrasing content and `Label` renders a
                    `div` by default — which is the invalid nesting its `as` prop exists for. */}
                <Label as="span">Looked up</Label>
                <span className="min-w-0 flex-1 font-mono text-[11px] leading-5 text-ink-3 [overflow-wrap:anywhere]">
                  {investigationSummary(message.answer.investigation)}
                </span>
                <ChevronDown className="size-4 shrink-0 text-ink-3 transition group-open:rotate-180" />
              </summary>
              <div className="mt-2">
                <InvestigationTranscript investigation={message.answer.investigation} />
              </div>
            </details>
          ) : null}

          {message.answer.supporting_candidate_ids.length ? (
            <div className="mt-2 border-t border-rule pt-2">
              {/* The charter asks every claim to say where it came from, and a row of unheaded
                  chips under a paragraph does not say what it is. */}
              <Label>Answered from these findings</Label>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {message.answer.supporting_candidate_ids.map((id) => {
                  const finding = review.findings.find((item) => item.candidate.id === id);
                  // An answer is told where the evidence sits but never shown the code there,
                  // so a citation is the way to it rather than a footnote. `text-left` because
                  // a button centres its text by default, and a citation is a whole sentence —
                  // on a phone it wrapped to four centred lines, which reads as a pull quote
                  // rather than as a link.
                  if (finding && onOpen) {
                    return (
                      <button
                        key={id}
                        type="button"
                        title={plainProse(finding.candidate.summary)}
                        onClick={() => onOpen(id)}
                        className="max-w-full text-left"
                      >
                        {/* `bare`, and `Tag` is why: it already draws `rounded-xs border
                            border-rule-strong bg-sunken px-2 py-0.5`, so a chip inside it is a
                            box inside a box with two hairlines, at 12px. The mono face is the
                            half that carries the meaning and the tag is already providing the
                            other half. The `title` beside it is a string, so it gets the
                            delimiters taken off rather than drawn — and the two must say the
                            same words.

                            The hover is `border-ink-3` and not `border-rule-strong`, which is
                            what it said while `Tag` rested on `border-rule`. `Tag` rests on
                            `--rule-strong` now, so the old class was a hover that changed
                            nothing — an operable-looking chip that did not answer a pointer.
                            `--ink-3` is the next step that is actually a step, and it stops
                            short of `--rule-control`, which is the edge reserved for something
                            you operate directly rather than a citation you can follow. */}
                        <Tag className="transition hover:border-ink-3 hover:text-ink">
                          <Prose bare>{finding.candidate.summary}</Prose>
                        </Tag>
                      </button>
                    );
                  }
                  // The same citation with nothing to open, so it is drawn the same way: a
                  // citation that changed shape depending on whether it was clickable would
                  // read as two different kinds of thing.
                  if (finding)
                    return (
                      <Tag key={id}>
                        <Prose bare>{finding.candidate.summary}</Prose>
                      </Tag>
                    );
                  // No finding to name it with. A truncated id standing in as a label reads as
                  // the candidate's name, which it is not — so the chip says what happened and
                  // keeps the id in mono, where a machine string belongs.
                  return (
                    <Tag key={id} className="gap-1.5">
                      Cited candidate, not in this review
                      <span className="font-mono text-[11px] text-ink-3">{shortId(id, 12)}</span>
                    </Tag>
                  );
                })}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </Citations>
  );
}

/**
 * The threads held against one review, and the one asking is done in.
 *
 * `questionId` picks which family: `""` is the Ask tab's, over the review as a whole, and a
 * question id is the panel under that question. They are separated here rather than at the
 * request, because the listing is one request per review and splitting it into two would
 * make the Ask tab reload every time somebody asked about a question.
 */
export function useConversations(review: Review, questionId = "") {
  const client = useQueryClient();
  const conversations = useQuery({
    queryKey: ["conversations", review.id],
    queryFn: () => api.conversations(review.id),
  });
  const [conversationId, setConversationId] = useState<string | null>(null);

  const threads = (conversations.data ?? []).filter(
    (item) => (item.question_id ?? "") === questionId,
  );
  const current =
    threads.find((item) => item.id === conversationId) ?? threads[threads.length - 1] ?? null;

  useEffect(() => {
    if (conversationId && !threads.some((item) => item.id === conversationId)) {
      setConversationId(null);
    }
  }, [conversationId, threads]);

  const ask = useMutation({
    mutationFn: async (text: string) => {
      const id = current?.id || (await api.createConversation(review.id, questionId)).id;
      setConversationId(id);
      return api.ask(id, text);
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["conversations", review.id] });
    },
  });

  return { conversations, threads, current, setConversationId, ask };
}

/**
 * The box a question is typed into, with the button that sends it.
 *
 * Shared for the same reason the exchange is: two surfaces, one gesture.
 *
 * A textarea, not an input. The placeholder invites a sentence and a real question is two or
 * three lines of one, so a one-line field meant the words scrolled out of their own box while
 * being typed and could not be re-read before they were sent — at 1440 the same element was a
 * 1060px single line, which is the worst shape a sentence can be given.
 *
 * **The composer is one box, and the button is inside it.** It used to be a `Textarea` with a
 * detached right-aligned row 8px beneath it, which is two bordered objects reading as a field
 * and some unrelated control that happened to be near it. Three arrangements were weighed; the
 * two that lost are written down because they are the two anybody would reach for next.
 *
 * *Floating the button over the field's lower-right*, the chat-app default, was the closest
 * loser. It costs a padding reserve under the text — 52px of it, to clear a 44px target inset
 * 8px — so the field is a box with a permanently empty band at the bottom whether or not the
 * button is there, and the two things overlap on the one pixel that matters: Chromium draws
 * the `resize-y` grip in the textarea's bottom-right corner, which is exactly where the button
 * goes. Keeping the button meant `resize-none` and silently taking away the only way to make
 * this box bigger.
 *
 * *A single row that grows, with the button centred in the right of it*, loses on the sentence
 * two paragraphs up and on a second count: a target that moves as you type is a target you
 * have to re-find, and a centred one moves 12px for every 24px line the field gains.
 *
 * The third is what is here, taken one step further than it was put. Keeping the button outside
 * the field and tying it to it by closing the gap leaves two adjoining borders and a seam; so
 * the field's own edge is promoted to a box instead, the textarea inside it gives up its border
 * and its ground, and a rail along the bottom of that same box holds the button. The button is inside the field's hairline, so it reads as part of it at 390 and at
 * 1440 without either of the costs above: the text never runs under anything, the grip stays
 * where it was and stays reachable, and the rail is a row of its own so a 44px target does not
 * come out of the two rows there are to type in.
 *
 * **It costs nothing in height.** Both arrangements measure 118px, at 1440x960 and at 390x844
 * alike. The old one is a 66px textarea — `min-h-16` is 64 and two 24px lines inside `py-2`
 * and two hairlines are 66, so the min never bound — plus the 8px gap plus a 44px button. This
 * one is two hairlines plus a 64px textarea, where `min-h-16` does bind because `pt-2.5 pb-1`
 * is 14px of padding rather than 16 and there is no border left on it, plus a 52px rail. Both
 * read with `getBoundingClientRect` against the built stylesheet; the old one is reproduced
 * from its own class lists as `cn` resolved them, which is the only way to measure a layout
 * that is no longer in the tree.
 *
 * `features/review/conversation-thread.test.tsx` holds the structure and
 * `tests/browser/test_workspace.py` holds the geometry, which is the split this repository
 * makes everywhere: jsdom computes no layout, so nothing in vitest can see that the button is
 * inside the box.
 */
export function AskBox({
  label,
  placeholder,
  pending,
  value,
  onChange,
  onAsk,
}: {
  label: string;
  placeholder: string;
  pending: boolean;
  /**
   * Controlled, and it has to be. Under a clarification question this box lives inside a
   * panel that three ordinary gestures unmount — stepping to the next question, collapsing
   * the round, walking the docket — and a half-typed question held in here would go with
   * it. The page holds it, the same way it holds the round's answers.
   */
  value: string;
  onChange: (value: string) => void;
  /**
   * Send it, and say when it landed if you can.
   *
   * The box used to be cleared the instant the button was pressed, before the request
   * resolved — and an ask has no timeout, because it runs an agent. So a failure took the
   * reader's sentence off the screen and left them a button offering to resend the identical
   * text, with no way to rephrase the question that had just failed. A caller that hands back
   * the mutation's promise gets the words kept until it resolves and kept for good if it
   * rejects; one that returns nothing keeps exactly the behaviour it had.
   */
  onAsk: (text: string) => void | Promise<unknown>;
}) {
  // The rail's hint is the textarea's description as well as a line of text, so it needs an
  // id, and `useId` is what makes two composers on one page not share one.
  const hintId = useId();
  const send = async () => {
    if (!value.trim() || pending) return;
    try {
      await onAsk(value.trim());
      onChange("");
    } catch {
      // The failure is rendered by the caller, beside this box. What belongs here is the
      // words, still in the field, still editable.
    }
  };
  return (
    /* `34.8rem`, and it was `max-w-[64ch]`, which is two mistakes in one class list.
       The first is that a `ch` is the advance of the zero of the element's **own** used font
       and the wrapper this sat on declared no font size, so 64 of them resolved against the
       root's 16px and drew 614.40px — while the `Textarea` inside it is `text-sm`, whose own
       64ch is 537.60px. Seventy-seven pixels between the number written down and the text it
       was written about. The second is that a measure is a property of prose and this is a box
       to type in. What it should be capped at is not a count of characters but the column the
       exchange is read in: an answer above it is `ModelProse` at 58ch and 16px, which draws
       556.80px, and the question above that stops at 520.80px. At 614.40px the composer was
       the widest thing in the thread by 58px, which reads as a second column rather than as
       the end of the one above it. `34.8rem` is 556.80px — the answer's own edge exactly, said
       in the unit `ui/markdown.tsx` argues for.

       The number moved element when the composer became one box, and it had to stay the same
       number: it is now the width of the box that is *drawn*, where before it was a wrapper
       nobody could see, so the field's own right edge did not move and the button came inside
       it. That is what `test_workspace.py` measures rather than restating.

       Then it moved again, with the face. It was `38.5rem` — 616px, the round number just under
       the 617.12px Onest's zero put `58ch` at. IBM Plex Sans advances its zero 0.600em against
       Onest's 0.665em, so the answer's column came in to 556.80px and this cap sat 59px past
       the block it exists to line up with. Every figure in the two paragraphs above was
       re-derived at the same time; none of them was converted by ratio.

       The rest of this class list is the field's recipe from `ui/field.tsx`, moved one element
       out. `controlClass` is the recipe for *an element that is itself the control*, and here
       the control is this box — so the edge, the ground and the radius are declared on it and
       the textarea inside is transparent. That is the one place this component may not compose
       `Textarea`: passing `border-0 bg-transparent rounded-none` into it would have left a
       class list that says both `border` and `border-0` and reads as neither.

       The focus indicator comes with the edge, at the geometry the base rule declares —
       `2px solid var(--ink)` at `outline-offset: 2px`, from `styles.css` — drawn around the
       box rather than around the textarea. `ui/field.tsx` argues at length that `outline-none`
       on a field is how this product lost its one focus indicator, and this does not reopen
       that: nothing is removed, it is moved onto the rectangle a reader sees as the control.
       Left on the textarea it would draw a rounded rectangle *inside* the box, overlapping the
       box's own left and right edges and cutting across it above the rail.

       `has-[textarea:focus…]` rather than `focus-within`, because the button is in here too
       and draws its own ring from the same base rule — `focus-within` would put a second ring
       around the whole composer every time the button took focus. */
    <div className="max-w-[34.8rem] rounded-sm border border-rule-control bg-control transition has-[textarea:focus]:border-ink has-[textarea:focus-visible]:outline-2 has-[textarea:focus-visible]:outline-offset-2 has-[textarea:focus-visible]:outline-ink">
      {/* `block`, because a textarea is `inline-block` by default and an inline-level child
          puts a line box under it — **seven pixels** of the parent's ground between the text
          and the rail that nothing in either class list accounts for, which is the box
          growing from 118px to 125px. Read by taking `block` off in the source, rebuilding
          the bundle and measuring the live Ask panel at 1440x960: the textarea ends at the
          same place either way and the rail's top moves from 401.64 to 408.64. This comment
          said four, which is neither the gap nor the height it costs; the descender space
          under an inline box is a property of the parent's font metrics rather than a
          constant, so it is a number to measure and not one to reason to. */}
      <textarea
        aria-label={label}
        aria-describedby={hintId}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          // `isComposing` is the whole reason this is not one condition. Anyone writing with
          // an IME — Japanese, Chinese, Korean — presses Enter to commit a candidate, and
          // that press used to send a half-composed question to an agent. Shift+Enter is then
          // the newline, in a box whose entire purpose is a written sentence.
          if (
            event.key === "Enter" &&
            !event.shiftKey &&
            !(event.nativeEvent as KeyboardEvent).isComposing
          ) {
            event.preventDefault();
            void send();
          }
        }}
        rows={2}
        placeholder={placeholder}
        className="block min-h-16 w-full resize-y bg-transparent px-3 pb-1 pt-2.5 text-sm leading-6 text-ink outline-none placeholder:text-ink-3"
      />
      {/* The rail. `pr-2` against the text's `px-3` is not a slip: the button is a filled
          rectangle and the text is glyphs, so setting both to 12px would leave the button
          looking further out than the line above it. */}
      <div className="flex items-center justify-between gap-3 pb-2 pl-3 pr-2">
        {/* Enter already sends, and nothing on this surface said so. The keyboard route is
            the fast one and it is also the surprising one — an ask runs an agent, takes tens
            of seconds and cannot be recalled — so a reader who does not know about it is one
            reflex keystroke away from having sent a question they had not finished writing.
            That is worth a line on a surface this branch has otherwise been clearing. It is
            `aria-describedby` as well as visible, because the person who most needs telling
            that a key does something is the one who cannot see the button beside it.

            **What it costs, measured at 390x844 on the built stylesheet.** No height at all:
            the rail exists to hold a 44px button and this is a 22px line box centred in the
            same row. In width it is 88.89px, in a rail whose content box is 302px — with the
            12px gap and the 54.58px button that is 155.47px spent and 146.53px left.

            **The half that is deliberately missing is "Shift+Enter for a line".** It is
            missing because it is false on the device that width describes. There is no Shift
            key on a soft keyboard, so on a phone the return key sends and there is no newline
            to offer — which is a real gap in this composer and a change to what a key does,
            not a change to what a label says, so it is not this pass's to make. One line that
            is true everywhere beats two where the second is false on the narrow one.

            That reason is the whole of it, and it has to be, because there is no room either.
            This comment said the pair measured 202.98px and left 32.44px at 390, and it does
            not: written the way the first half is written — a `KeyCap`, which is the component
            that exists for exactly this — `<KeyCap>Enter</KeyCap> to send,
            <KeyCap>Shift+Enter</KeyCap> for a line` measures **228.22px** in this very rail,
            leaving **7.20px** of the 302px content box once the 12px gap and the 54.58px
            button are paid for. That one is read in the rail itself, by building the second
            half into this `span` and taking `getBoundingClientRect`. The other renderings are
            read against the built stylesheet in a bare page, which runs about half a pixel
            wide of the live rail on the string both can measure: two separate caps is 241.67px
            there, which does not fit at all, and the closest thing to 202.98 is the second
            half set as bare text at 199.81px — a key in body type beside a key in a cap. No
            rendering that carries a cap comes near 202.98. */}
        <span id={hintId} className="text-[11px] leading-4 text-ink-3">
          <KeyCap>Enter</KeyCap> to send
        </span>
        <Button disabled={!value.trim() || pending} onClick={() => void send()}>
          {pending ? <Spinner /> : "Ask"}
        </Button>
      </div>
    </div>
  );
}
