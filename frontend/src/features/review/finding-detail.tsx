import { useId, type ReactNode } from "react";
import { Link } from "react-router-dom";

import type { Finding, RetrievalProvenance, Review } from "../../api";
import { cn } from "../../lib/cn";
import { humanise, plural, shortId, verdictOf } from "../../lib/format";
import { awaitsAnswers } from "./docket-rules";
import { InvestigationTranscript, investigationSummary } from "./investigation";
import { Tag } from "../../ui/badge";
import { Button, CopyButton } from "../../ui/button";
import { EvidenceBlock } from "../../ui/code";
import { ArrowRight, ChevronDown } from "../../ui/icons";
import { MetaList, MetaRow, Mono, PathRef } from "../../ui/meta";
import { Label } from "../../ui/panel";
import { ModelProse, Prose } from "../../ui/prose";
import { Notice } from "../../ui/states";

/**
 * A measurement's name, said from the reader's side.
 *
 * `dependants_of_abstraction` is a schema key. It is the name the detector, the report and
 * the domain all use, and it should stay that in every one of them — but a person reading a
 * finding is being shown a count, not a field, and the count is of things that reference the
 * abstraction. The raw key still appears, in `Provenance`, which is where machine names live.
 */
const MEASUREMENT_LABELS: Record<string, string> = {
  dependants_of_abstraction: "referenced by",
  modules_naming_it_from_outside: "named from outside its package",
  modules_stating_it: "modules stating it",
  distinct_values: "distinct values",
  implementations: "implementations",
};

const measurementLabel = (name: string) => MEASUREMENT_LABELS[name] ?? humanise(name).toLowerCase();

/**
 * The empty corpus, as `policies/retrieval.py` fingerprints it.
 *
 * `corpus_fingerprint(())` hashes the empty string, so a review run in a workspace with no
 * policies still records a retrieval entry — it records one that searched nothing. Without
 * this constant both cases arrive here as `selected_policy_ids: []` and the closed state
 * would say "nothing came back" about a corpus that was never there.
 */
const EMPTY_CORPUS = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";

/**
 * What produced the policies this judgement weighed, in the shortest honest form.
 *
 * `finding.retrieval_identity` is a sha256 over everything the retrieval did. That is the
 * right thing to record and the wrong thing to print on an attribution line: 64 hex
 * characters is three lines of a phone spent on a value nobody reads by eye.
 */
function retrievalLabel(finding: Finding, retrieval?: RetrievalProvenance): string {
  if (retrieval) return `${retrieval.retriever}/${retrieval.version}`;
  return finding.retrieval_identity ? shortId(finding.retrieval_identity, 12) : "no retrieval";
}

/**
 * A detection rationale, with the fingerprint it usually ends on taken off the end of it.
 *
 * The deterministic detector regularly closes its sentence with the 64-character participant
 * fingerprint it matched on, and the sentence is prose — so the hash was set in the sans face
 * reserved for prose and then flowed through three lines, breaking mid-hash with no visual
 * seam. It is an identity produced by analysis, which is the Measured voice, and it belongs
 * under the sentence in mono, shortened, with a way to take the whole of it.
 *
 * The prose keeps `wrap-anywhere` for the case this does not match, which is any rationale
 * that names something long somewhere other than at the end.
 */
function splitFingerprint(rationale: string): { prose: string; fingerprint?: string } {
  const found = /\s*\b([0-9a-f]{32,64})\b\.?\s*$/.exec(rationale);
  if (!found) return { prose: rationale };
  return { prose: rationale.slice(0, found.index).trimEnd(), fingerprint: found[1] };
}

/**
 * What `Policies` says while it is closed.
 *
 * Four different situations arrive here as "no policies", and the charter's "say where it
 * came from" is the reason they may not be printed as one: a corpus that was searched and
 * had nothing above the threshold is a fact about this candidate, and a workspace with no
 * corpus at all is a fact about the setup. Only the second is something the reader can fix.
 */
function policiesSummary(finding: Finding, retrieval?: RetrievalProvenance): string {
  const bore = finding.policies.length;
  if (!retrieval) {
    return bore
      ? `${plural(bore, "policy", "policies")} applied · search not recorded`
      : "No retrieval was recorded for this candidate";
  }
  const retrieved = retrieval.selected_policy_ids.length;
  if (bore) return `${bore} of ${retrieved} policies applied`;
  if (retrieval.corpus_fingerprint === EMPTY_CORPUS) {
    return "No policy corpus was configured · nothing was searched";
  }
  if (!retrieved) return "The corpus was searched · nothing came back above the threshold";
  return `0 of ${retrieved} policies applied`;
}

/**
 * A fact that supports the block above it, said in one line.
 *
 * `46ch`, not the `62ch` this and every other measured block in the product used to carry.
 * `ch` is the width of the used font's zero — 0.600em in IBM Plex Sans, 0.665em in the Onest
 * this replaced — so `62ch` resolved to well over 600px at the reading size and admitted far
 * more lowercase characters than the number implied. The unit is kept, because it keeps the
 * measure proportional to the size the block is set at; the number is corrected to the 30em a
 * measure actually is.
 *
 * It is the supporting measure now, and no longer the only one. The model's argument left
 * `46ch` for `58ch`, because that same proportionality cuts the other way at the reading
 * size: `ch` scales with the type, so an equal `ch` on a 16px paragraph and on this 12px
 * footnote gives them the same *character count* at two different widths — and the block set
 * largest then held the fewest words on the surface. The counts, counted in a browser over the
 * recorded corpus rather than assumed, were **59** here and **75.7** for the `58ch` argument
 * next door — measured the same way, and stated in one quantity on purpose, because the whole
 * subject of this comment is a pair of numbers that meant different things while wearing the
 * same words. A footnote is a line under a block and wants the shorter measure; an argument is
 * read and wants the longer. **Both counts are Onest's** and neither has been re-swept since
 * the face moved to IBM Plex Sans; what they establish is the ordering, which is a property of
 * the two measures rather than of the face, and the ordering is what the paragraph argues from.
 * `docs/known-defects.md` carries the re-sweep.
 *
 * "The same way" is now a method rather than a promise, because this pair has been re-measured
 * five times and moved three. Serve the built bundle, so the face is the shipped woff2 and the
 * CSS is the real one. Load every weight involved with `document.fonts.load` and assert them
 * with `document.fonts.check` before reading anything — `font-display: swap` otherwise answers
 * with a fallback zero and every width is five per cent wrong. Render all 375 recorded strings
 * through the real `ModelProse` with its quoted names drawn as chips. Cluster a Range per
 * character on the vertical **centre** of its box, not its top, since a mono chip is taller than
 * the sans beside it and shares its baseline. Then average the lines that are not the last of
 * their block. The 59 held every one of the five Onest runs: 59.01 over 2,846 such lines. The
 * method is what carries over; the number is what has to be read again.
 *
 * **The 73 that used to stand beside it was wrong twice over, and the second way is the one
 * worth recording.** It was said to be this sweep taken over the *string* rather than over the
 * render, on the grounds that a string loses the width a mono chip adds. The sans is *narrower*
 * than the chip that replaces it, so measuring the string can only push the count up. Re-run:
 * flatten every chip back to body text and the same sweep gives **76.07**; draw the
 * recorded string literally, backticks and all, and it gives **76.24**. Both sit above the
 * render's 75.7, so the diagnosis had the direction backwards as well as the digit. 73.1 is this
 * sweep at 56ch, which is the likeliest place a 73 came from at all. It is deleted rather than
 * corrected — a counterfactual nobody wrote a method for is a number nobody can check, and this
 * surface has now shipped seven rounds of those.
 * `features/review/finding-detail.test.tsx` states all three sweeps beside `AVERAGE_CHARACTER_PX`.
 *
 * The half of that method nobody wrote down, and the half that decides the last digit of every
 * number above: a soft wrap eats a space that is drawn on no line, and it is counted here as
 * belonging to **the line it ended**, so a line holds the source from its own first visible
 * character up to the next line's first. `docs/design-system.md` states the choice and the
 * reason. Counted as the visible run instead, first ink to last, this pair is 58.0 and 74.7 —
 * both perfectly defensible numbers, and not these ones. That is the whole reason this comment
 * has moved three times.
 *
 * 46ch here is 331.20px, because a footnote is set at 12px and a `ch` follows the size of the
 * block it is written on. It is not the 358.80px the same 46ch resolves to on the 13px lede
 * twenty lines up or on the 13px policy note below — same count, one pixel of size, two
 * different widths. No figure here is worked out by hand: "resolves every `46ch` this surface
 * declares, and none of them from an ancestor" in `features/review/finding-detail.test.tsx`
 * computes them off these class lists, and it also says the thing this comment cannot — that
 * `max-w-[46ch]` is written on four blocks in this file at four sizes, and therefore stops at
 * four different edges, 55.20px apart end to end. That is defect 9 alive here, and
 * `docs/known-defects.md` carries the table.
 *
 * Under Onest that spread was 61.18px and it had a second cause: one variable file whose zero
 * narrowed from 665 units on a 1000-unit em at 400 to 661.8 at 600, so the same `46ch` at the
 * same 13px landed on two widths depending on weight alone. IBM Plex Sans ships four static
 * cuts that all advance the zero at 600 units, so weight has dropped out of the question and
 * size is the whole of what is left. That makes the defect smaller and not different, which is
 * why the number moved and the paragraph did not.
 *
 * The number is spelled out because this comment's own subject is a number in a comment that
 * drifted. The one it replaces said "sixty", which is what `ch` is worth if you take it as
 * half an em — the same assumption that put `62ch` on three surfaces believing it was 62
 * characters when it was 89, and the assumption this paragraph exists to correct.
 */
function Footnote({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn("mt-3 max-w-[46ch] text-[12px] leading-5 text-ink-3", className)}>{children}</p>;
}

/**
 * A small uppercase label above a block. Ten pixels, and it never says a sentence.
 *
 * `Label` with one addition: a block label here regularly carries a count or a qualified
 * name after its word, and a qualified name is one token to the line breaker.
 */
function BlockLabel({ children, className }: { children: ReactNode; className?: string }) {
  return <Label className={cn("[overflow-wrap:anywhere]", className)}>{children}</Label>;
}

/**
 * A policy, as the way to read it.
 *
 * A finding says which policies applied to it and prints the id it cites them under, and until
 * now that id was plain mono: a reader asking why a candidate was called material could see
 * the title and the model's reasoning about it, and had no way to the policy's own words
 * short of going to Policies and searching the title by hand. The charter's fourth decision
 * rule is that provenance is reachable, and the design system names a policy as one of the
 * three things `--mark` exists to link to.
 *
 * It lives in this file rather than beside the drawer that also uses it because
 * `ui/design-system.test.ts` allowlists the files that may spend the mark, and one link
 * written twice is the drift that allowlist exists to stop.
 *
 * `-my-3 py-3` is `PathRef`'s trick, and this is the other half of the same promise: a
 * finding has two ways out to the source a claim came from, and only the one going to a file
 * was tappable. This one was a bare line of type with no box at all — well under the 24px
 * minimum, let alone the 44px floor the rest of the product holds. The padding makes the touch
 * box; the matching negative margin hands those pixels straight back to the layout, so nothing
 * moves. A call site that wants to space it does so on a wrapper — `cn` is tailwind-merge, and
 * a `mt-*` passed here sits beside the `-my-3` rather than replacing it.
 *
 * **The rest of the class list is `PathRef`'s too, and it was not.** The two are the same
 * promise said about two kinds of source, so a reader who has followed one should recognise the
 * other, and this one was a size and an underline away from it: 11px against the evidence tier's
 * 12.5/500, and `decoration-rule-strong` — a neutral hairline — under a word painted `--mark`.
 * The system splits each signal in two on the WCAG line, so the word takes the text tier and the
 * underline takes `--mark-edge`, which is exactly what `ui/meta.tsx` draws. `hover:decoration-mark`
 * rather than `hover:decoration-current`: `currentColor` here *is* `--mark`, so the two happen to
 * agree, and naming the token says the strengthening is a tier change rather than a coincidence
 * of what the text is painted.
 */
export function PolicyRef({ id, className }: { id: string; className?: string }) {
  return (
    <Link
      to={`/policies?open=${encodeURIComponent(id)}`}
      title={`Read the policy ${id}`}
      className={cn(
        "-my-3 inline-block py-3 font-mono text-[12.5px] font-medium text-mark",
        "underline decoration-mark-edge underline-offset-2 transition hover:decoration-mark",
        "[overflow-wrap:anywhere]",
        className,
      )}
    >
      {id}
    </Link>
  );
}

/**
 * Whose voice the block below belongs to, and who exactly produced it.
 *
 * The charter keeps three jobs apart and this is the whole of what says so now: the word,
 * then the identity behind it. `MEASURED · boundary-scan`, `JUDGED · gemini/judge:v1`,
 * `DECIDED · nobody yet`. There is no gutter and no second typeface; there is a line naming
 * the author, and a reader who has read one finding knows the shape of the next.
 *
 * Exported for the report surface, which sets the review's synopsis — the one other
 * model-authored paragraph in the product. It had grown its own label recipe at its own
 * tracking and its own weight, so the two paragraphs a reader is meant to recognise as the
 * same kind of thing were the two that did not match.
 */
export function Attribution({ voice, by, className }: { voice: string; by?: ReactNode; className?: string }) {
  return (
    <p className={cn("flex flex-wrap items-baseline gap-x-2 gap-y-0.5", className)}>
      {/* A `span`, because a voice sits on the same baseline as the identity beside it and
          this line is a `p`. Full ink rather than the label's meta grey: the voice is the
          thing being named, not a caption on it. */}
      <Label as="span" className="text-ink">
        {voice}
      </Label>
      {by ? (
        <span className="min-w-0 font-mono text-[11px] leading-5 text-ink-3 [overflow-wrap:anywhere]">
          {by}
        </span>
      ) : null}
    </p>
  );
}

/**
 * A provenance value whose whole purpose is to be pasted somewhere else.
 *
 * Nine rows of 64-character hashes, and until there was a clipboard in this product the only
 * way to take one anywhere was to select it by hand across three wrapped lines. The tick is
 * the confirmation and it costs no width until it is earned.
 *
 * `text-ink`, against the `--ink-3` the `Label` beside it is set in. The hash is the content
 * of the row and the key is the caption on it, and under the v1 ramp those two measured
 * **1.22:1 against each other** — both passing comfortably against the ground they sat on,
 * thirteen levels apart, so a key and its value were one colour with two names. This block is
 * the one `docs/design-system.md` names when it says a contrast test cannot see two passing
 * inks landing on top of one another. The v2 ink tiers step 0.100 apart in OKLCH lightness, so
 * the two ends of the ramp this row uses measure 3.01:1 in light and 2.84:1 in dark against
 * each other, and the darkest thing in the row is now the thing worth copying.
 *
 * The size is `Mono`'s own default and not a class written here. The evidence tier moved to
 * 12.5px at 500 — this fold sets the product's longest strings and was setting them at its
 * smallest size, in the face whose stems are thinnest there — and a size written back on at a
 * call site is the drift that component's docstring exists to stop.
 *
 * `py-0`, because the rows are held apart by the list's own gap now rather than by their own
 * padding and a hairline between them. The argument is on the `MetaList` in `Provenance`.
 */
function HashRow({ label, value }: { label: string; value: string }) {
  return (
    <MetaRow label={label} className="py-0">
      <span className="flex min-w-0 items-start gap-1">
        <Mono className="min-w-0 flex-1 text-ink [overflow-wrap:anywhere]">{value}</Mono>
        <CopyButton
          value={value}
          label={`Copy the ${label.toLowerCase()}`}
          className="-my-1 shrink-0"
        />
      </span>
    </MetaRow>
  );
}

/**
 * A section folded away, with a closed state that says what is inside it.
 *
 * `<details>` and `<summary>` rather than a button and a piece of state, so the disclosure
 * role, the keyboard path, the browser's own find-in-page and the expanded state announced
 * to a screen reader are all free and correct.
 *
 * Two of these are left. `Measured` used to be the third, and folding the machine's evidence
 * away behind it was the single worst thing about this screen: a finding claiming five
 * modules reach past a port showed you none of them, and asked you to agree anyway.
 */
function Disclosure({
  label,
  summary,
  machine,
  children,
}: {
  label: string;
  summary: ReactNode;
  /**
   * Whether the closed state is a machine string or a sentence.
   *
   * Every summary used to be set in mono, which is the face this system reserves for names,
   * paths and ids. That is right for Provenance, whose closed state really is two hashes, and
   * wrong for the other two: "The corpus was searched · nothing came back above the
   * threshold" in monospace reads as an identifier that has gone wrong — the failure
   * `surfaces.tsx` names by hand a few files over. So the caller says which voice its own
   * summary is in, and English goes at the footnote step in sans.
   *
   * The machine half sits at the evidence tier — 12.5px at 500 — rather than a step below the
   * sentence it stands in for. Two shortened hashes are the longest string this row ever
   * carries and they were the smallest type on it.
   */
  machine?: boolean;
  children: ReactNode;
}) {
  return (
    <details className="group border-t border-rule">
      {/* The chevron leads. Three bands of the same white split by hairlines, two of which
          open and one of which does not, told a reader nothing at rest — and the only mark
          that said so was 16px wide at the far right of a 1168px row, more than a thousand
          pixels from the word it opens. In front of the label it sits twelve pixels from it.

          **The whole row is the control, and one word in it was drawn like one.** The label
          is full ink; the chevron and the sentence beside it were both `--ink-3`, which the
          ramp gives to labels and meta and explicitly not to a sentence — and two of the three
          summaries here are sentences. Both move to `--ink-2`, the reading tier, and the
          chevron takes full ink under the pointer so the row has a state as well as a rest.
          Nothing here takes a hue: an affordance in this system is a weight, an underline or
          an edge, and `--mark` is spent on something that goes somewhere. Opening a fold goes
          nowhere.

          That pointer state hangs off a named group on the `summary` rather than the `group`
          on the `details`, which covers the open body as well — under it, running a pointer
          across the hashes would have lit the control that closes them.

          `hover:bg-sunken`, and the open body below is `--sunken` too. The last pass rejected
          `--surface-2` for this hover because `#ffffff` to `#fafafa` was five values; the v2
          ramp widens that step into a real one and it is still the wrong one here, at 1.08:1
          against `--sunken`'s 1.25:1 — a division a reader can be shown, not a state that
          arrives under a pointer. What that leaves is the objection the old comment raised
          against exactly this, that a hover in the body's own fill is the row previewing its
          contents. It is a fair description and a poor complaint: the ramp gives one tone to
          *a hover, a code block, an opened fold* on purpose, the summary is what closes an
          open fold, and a fold answering as one block under the pointer is a true statement
          about what a click there does.

          `sm:px-5` rather than `sm:px-6`, so the left edge of an open finding stops stepping
          in and out: the argument, the readings, the evidence and the decision bar all resolve
          to 16px below `sm` and 20px above it, and four pixels is enough to read as a
          misalignment against a hairline and not enough to read as an indent. */}
      <summary className="group/summary flex min-h-11 list-none items-start gap-3 px-4 py-3 transition hover:bg-sunken focus-visible:-outline-offset-2 sm:px-5">
        <ChevronDown className="mt-0.5 size-4 shrink-0 text-ink-2 transition group-hover/summary:text-ink group-open:rotate-180" />
        <Label className="shrink-0 leading-5 text-ink">{label}</Label>
        <span
          className={cn(
            "min-w-0 flex-1 text-[12px] leading-5 text-ink-2 [overflow-wrap:anywhere]",
            machine && "font-mono text-[12.5px] font-medium",
          )}
        >
          {summary}
        </span>
      </summary>
      {/* A ground step, and no hairline drawn over it. `--sunken` is what the ramp calls an
          opened fold, and this is the first fill in the finding that says *you are inside
          something* by being a different colour rather than a different white: `--surface-2`
          on `--surface` is 1.08:1, and `--sunken` on it is 1.25:1 in light and 1.28:1 in dark.
          The `border-t border-rule` that used to draw this seam goes with the change — the
          order is space, then a rule, then a fill, then a border, stopping at the first that
          works, and a fill that separates does not want a rule laid on top of it.

          **Neutral, and that is the rule rather than the absence of a decision.** This is the
          fold that holds nothing but provenance and `--mark` is the hue that means provenance,
          so tinting the body with it is the obvious move and the wrong one: it would be the
          largest chromatic region in the product, and a hue that fills a region has stopped
          signalling and started decorating. The four wash tokens are a badge fill and nothing
          else. Colour in a fold like this is one word wide: an id or a path that leads
          somewhere, painted `--mark`, and nothing around it. */}
      <div className="bg-sunken px-4 py-4 sm:px-5">{children}</div>
    </details>
  );
}

/**
 * What became of the question this finding hinges on, said per state rather than per absence.
 *
 * One ternary used to answer this — is there a question naming this candidate on an
 * `awaiting_answers` review, yes or no — and every no printed "the round was concluded with
 * the uncertainty preserved". That sentence is a positive claim about a deliberate act, and it
 * was rendered on cancelled reviews (where `cancel()` keeps every question, so an open question
 * covering this candidate is sitting right there), on failed ones (where the run crashed and
 * the question was never put), and on open ones whose questions happen to name other
 * candidates. Both of its clauses were false at once on the first of those.
 *
 * `docs/charter.md`: uncertainty is stated, not smoothed, and nothing is inferred on a
 * person's behalf. A round that did not conclude does not get to say it concluded.
 *
 * The re-judgement scope is the backend's, not a guess: `select_rejudgements_node` returns
 * every candidate, because an answer is about intent and intent bears on all of them.
 */
/**
 * What the judgement had from the reader, which is not how many questions were put to them.
 *
 * `case.answers` carries skipped questions beside answered ones — `AnswerStatus` is
 * `answered` or `skipped` — so counting the array called every skip an answer. A round where
 * somebody answered one of three and skipped the rest printed "3 answers" here, four lines
 * above a line counting the same case at 1. Two numbers under one word, and the overstated
 * one was the provenance line, which is the one a reader trusts.
 *
 * A skip is not silence either. The question was put, the reader declined it, and the case
 * revision advanced carrying that. So both are said, and the reader can see which is which.
 */
function judgedAgainst(review: Review): string {
  const answered = review.case.answers.filter(
    (answer) => answer.status === "answered",
  ).length;
  const skipped = review.case.answers.length - answered;
  const revision = `Judged on case revision ${review.case.revision}`;
  if (!answered && !skipped) return `${revision}, before any answer.`;
  if (!answered) return `${revision}, with ${plural(skipped, "question")} skipped and no answer.`;
  if (!skipped) return `${revision}, with ${plural(answered, "answer")}.`;
  return `${revision}, with ${plural(answered, "answer")} and ${skipped} skipped.`;
}

function hingeFootnote(review: Review, asked: boolean): string {
  if (review.status === "cancelled") {
    return asked
      ? "This round was cancelled before the question was answered."
      : "This round was cancelled with the uncertainty unresolved.";
  }
  if (review.status === "failed") {
    // A review can fail *after* a round has been asked and answered — `revise_case` puts the
    // answers on the case, and a raise anywhere downstream files a failed snapshot carrying
    // them. `round` is the fact that separates the two, because it advances only inside
    // `revise_case`: past one, a round was asked and taken before this stopped, and saying
    // the uncertainty was never put to anyone contradicted the answer count in the same line.
    return review.round > 1
      ? "This review did not finish. It had already asked a round, and been answered, before it stopped."
      : "This review did not finish, so the uncertainty was never put to anyone.";
  }
  if (awaitsAnswers(review)) {
    return asked
      ? "Answering completes this review's case revision and judges every candidate again."
      : "No question was asked about this candidate. Answering the open round judges it again with the rest.";
  }
  // Answered, and the two states after that. A snapshot is immutable, so `status` says
  // `awaiting_answers` for ever once it has asked — which is why the branch below used to
  // read off it and tell a reader of a superseded record that no question had been asked
  // about a candidate whose question was rendered directly above, and offer them a round the
  // server would refuse. What separates the two is whether a later snapshot exists yet.
  if (review.superseded_by) {
    // What became of *this round* is not on this record, and cannot be read off what became
    // of the review. A waiting snapshot is superseded by two different acts — its round was
    // answered, or somebody stopped the review — and `superseded_by_status` is the status of
    // the record the execution now stands on, which for round one of a review cancelled at
    // round two says `cancelled` about a round that was answered. Both guesses have been made
    // here and both were wrong for somebody; this says where the answer is instead.
    return asked
      ? "This was asked here; what became of it is on the record that replaced this one."
      : "No question was asked about this candidate in this round, and the review has moved on from this record.";
  }
  if (review.status === "awaiting_answers") {
    // Closed, not answered. The absence of a successor was read as "answered and being
    // judged", which holds only for `cancel(review_id)`; concluding with remaining
    // uncertainty, stopping the run, and a killed process all end the round with nothing
    // bound — the last two permanently. See the sibling comment in `standingOf`.
    return asked
      ? "This was asked here, and the round it belongs to is closed."
      : "No question was asked about this candidate, and the round it belongs to is closed.";
  }
  return "No open question covers this. The round was concluded with the uncertainty preserved.";
}

/**
 * The body of one finding: the model's argument, beside the material it rests on.
 *
 * This is everything a reader needs to check a claim and nothing they need to *find* it —
 * the verdict, the identifier and the decision live on the docket row this expands inside,
 * because those are what the collapsed row shows and a row that restated them on opening
 * would be answering a question already answered.
 *
 * It is laid out by how much room each part actually needs, which is not the same as how
 * important each part is. The evidence is source code, which needs every pixel it can get. A
 * first attempt put the argument in a `1fr` column beside a `24rem` one holding everything
 * the machine produced, and got both wrong at once: seven hundred pixels of empty left column
 * padded out to match its neighbour, and `class Clock(Protocol):` clipped in a gutter. So the
 * argument is a band across the top, and under it the readings take a narrow column beside
 * the excerpts, which take the rest.
 *
 * The band across the top used to be one paragraph capped at `46ch` — "it takes the full
 * width and stops", this comment said, and it did neither: 489px of text in a 1126px row left
 * 57% of the band empty beside the one paragraph the product exists to show. It is now what
 * the verdict means, then the argument at `58ch` beside a rail carrying what the judgement was
 * weighed against and the single thing the finding asks of you. The verdict's own sentence
 * leads the band at every width rather than sitting in the rail, because below `lg` the rail
 * stacks under the argument and an introduction arriving 1,853px after the thing it
 * introduces is not one.
 */
export function FindingBody({
  review,
  finding,
  onAnswer,
  onOpenContext,
}: {
  review: Review;
  finding: Finding;
  onAnswer?: () => void;
  onOpenContext?: () => void;
}) {
  const uid = useId();
  const hingeId = `hinge-${uid}`;
  const descriptor = verdictOf(finding.verdict);
  const measurements = finding.candidate.measurements;
  const retrieval = review.retrieval_manifest.find(
    (entry) => entry.candidate_id === finding.candidate.id,
  );
  const investigation = review.investigation_manifest.find(
    (entry) => entry.candidate_id === finding.candidate.id,
  );
  const firstLocation = finding.evidence.find((item) => item.location)?.location;
  // How many distinct files the excerpts come from, which is what the Evidence header can say
  // that the cards under it cannot — each of those carries its own location.
  const evidenceFiles = new Set(
    finding.evidence.map((item) => item.location?.path).filter(Boolean),
  ).size;
  const detected = splitFingerprint(finding.candidate.detection_rationale);
  // Two separate questions, and folding them into one ternary made the footnote below assert
  // things that were not true. `openQuestion` is whether this review holds a question naming
  // this candidate — it does on a cancelled review, because `cancel()` keeps every question.
  // `waitingOn` is whether that question can still be answered, which only an open round can.
  const openQuestion = review.questions.find((question) =>
    question.candidate_ids.includes(finding.candidate.id),
  );
  const waitingOn = awaitsAnswers(review) ? openQuestion : undefined;

  // What the machine actually produced, as the attribution for its own column: how many
  // things it counted and how many excerpts it pinned.
  const counted = [
    measurements.length ? plural(measurements.length, "measurement") : null,
    finding.evidence.length ? plural(finding.evidence.length, "excerpt") : null,
  ].filter(Boolean) as string[];

  return (
    <div>
      {/* ── The argument, beside what the judgement asks of you ───────────────── */}
      <section className="min-w-0 px-4 py-4 sm:px-5">
        <Attribution
          voice="Judged"
          by={`${finding.model_identity} · ${retrievalLabel(finding, retrieval)}`}
        />
        {/* `mt-2.5` is the gap under an 11px attribution label, and `gap-y-3.5` is the gap
            between the two paragraphs now inside this grid — the verdict's sentence and the
            argument under it. Those were `mt-2.5` on the sentence and `mt-3.5` on the grid when
            the sentence stood outside it, so the same two distances are drawn; only what
            declares them moved.

            **All three children are placed explicitly, and that is the repair rather than a
            tidy-up.** The verdict's sentence takes column one row one, the argument column one
            row two, the rail column two row two. Auto-placement would put the argument in the
            rail's column, so the placement is not optional — but *which* cell each one takes is
            the point. The sentence is inside the argument's own track, so no width it declares
            can take it past the argument's right edge at any viewport. It used to sit above the
            whole grid with a `38.5rem` cap standing in for that edge, and two numbers agreeing
            is not the same as one number: 38.5rem was 616px against an argument column of
            `1fr` — 582px at a 1024px viewport, 600px at 1040, and only from about 1060 up wide
            enough for the cap to be the narrower of the two. Measured at 1024 the sentence was
            capped 34.00px past the argument it stands over. (Those figures are Onest's, from
            when the argument's `58ch` drew 617.12px; the cap is `34.8rem` now and the overhang
            would not reproduce. They are kept because the defect is the arrangement, not the
            arithmetic — two caps agreeing at one viewport is not one edge at every viewport,
            whatever the two numbers happen to be.) Latent, because the three
            descriptions in `lib/format` are 51, 60 and 60 characters and none of them reaches
            580px — which means the guarantee was being held by the length of three strings.

            The rail keeps row two, so its first line still sits on the argument's first line
            and nothing about the band's appearance moves. `mt-1.5` and `lg:mt-0` on it are the
            same arithmetic: stacked below `lg` the rail wants the 20px it always had, which is
            the 14px row gap plus six.

            The band is two columns, and what fills the rail is now one line thinner than when
            the column was argued for. Every finding still has a case footnote, so the rail is
            never literally empty; a held one adds the question it is waiting on and the button
            that answers it, and a material one adds what it suggests. But the verdict's own
            sentence has gone to the head of the band, so on a *cleared* finding — which carries
            neither a hinge nor a recommendation — the rail is a single 12px footnote in a 416px
            column.

            Neither absence comes from `domain/finding.py`, which is where this comment used to
            send a reader. `Finding.__post_init__` refuses a recommendation on a non-material
            finding and refuses a hinge *beside* a recommendation, and it takes a cleared finding
            carrying a hinge alone without a word. The rule is one layer out, at the boundary a
            model's judgement enters by: `FindingOutput.the_verdict_carries_what_it_is_allowed_to`
            in `reasoning/adapters/langchain.py` raises on a hinge under any verdict but `held`.
            306 of the 375 recorded judgements are cleared or material and not one of them
            carries a hinge; all 69 held ones do.

            `lg:self-start` on the rail is what makes that survivable, and it is the whole of
            the fix. A grid item stretches down its row by default, so the rail's hairline ran
            the height of the *argument*: 239px of content at the top of an 1,147px border on
            the longest recorded reasoning, which is 908px of line with nothing beside it —
            79% empty at 1440, 78% at 1024. Measured after the lede moved out of the rail, and
            worse than before it moved, because that took content out of the rail without
            shortening the band. Aligned to the start the border ends where its content does
            and the column is 239px of margin note, which is what it always was; the empty
            space beside a long argument is the margin a long argument has, and a rule drawn
            through it was the only thing claiming otherwise.

            The mirror of it at the short end is not the same defect and does not get the same
            treatment. On the 148-character reasoning the *argument* stops after two lines
            against a 239px rail, which reads as 79% of the left column empty by the same
            arithmetic — but the band is 239px tall there rather than 1,147px, so the ratio is
            190px of white beside a footnote and not 908px of hanging line. Ratios do not
            carry the absolute height, and it is the height that makes the long case a hole.

            The block this replaced reserved a second column only when a hinge and a
            recommendation both arrived — which is a pairing the domain forbids outright, so
            the branch had never once executed. `Finding.__post_init__` raises on a finding that
            hinges and recommends, and raises again on a non-material finding that recommends
            anything at all — named rather than cited by line, because the two line numbers this
            sentence carried had both moved by half a file and `docs/frontend-regions.md` refuses
            line numbers for that reason. The rule that comment stated was right and it was the
            block itself that was breaking it: while it refused to reserve width for an absent
            neighbour, the argument beside it left 637px of empty panel down the right of
            every finding at 1440.

            The rail is on the right, not the left, because the section's own padding is the
            left edge that the argument, the readings, the evidence and the decision bar all
            share — see the `sm:px-5` argument in `Disclosure` above. A left rail would have
            put its hairline in line with the Measured band's, and the price would have been
            indenting the model's paragraph off the one edge five stacked regions agree on.

            `border-rule` and not `border-rule-strong`: the strong rule is reserved for the
            edge of something you could pick up, and this is a margin. It stops short of the
            band's own top hairline, because the grid sits inside the section's `py-4`, and
            short of the bottom one by however far its content ends above it — which is what
            keeps it reading as a margin rule rather than as a divider of the kind the
            Measured band draws below. */}
        <div className="mt-2.5 grid gap-y-3.5 lg:grid-cols-[minmax(0,1fr)_minmax(0,20rem)] lg:gap-x-8 xl:grid-cols-[minmax(0,1fr)_minmax(0,26rem)] xl:gap-x-10">
          {/* What the verdict means, said before the argument rather than beside it.

              It was in the rail, which reads correctly at 1440 and inverts on a phone: below
              `lg` the rail stacks under the argument, so on the longest recorded reasoning this
              sentence arrived 1,853 CSS pixels after the paragraph it exists to introduce —
              measured, rail top 1461 against argument top -392 at 390 — with the button that
              unblocks the review behind it. The one product-authored line in the band was read
              last on the width where the wall is worst: the same string is 38 lines at 1440 and
              64 at 390.

              First in the DOM rather than reordered into place. The pass before this one refused
              an `order` class for the same effect and was right to: a rail that paints above the
              argument and tabs after it is a page whose reading order and keyboard order
              disagree, which is a cost paid by the readers least able to absorb it.
              `col-start` and `row-start` are not that class — they place a grid item, they do
              not renumber the document, and paint order matches document order at every width
              here. Nothing focusable moves in any case: this sentence is not a tab stop.

              `lg:col-start-1 lg:row-start-1` is what actually holds this line inside the
              argument's right edge, and the grid comment above says why it had to.

              `max-w-[34.8rem]` is a guard, not a measure, and now a guard against one thing
              rather than two. The three descriptions in `lib/format` are 51, 60 and 60
              characters, so at 13px the line wraps only below `sm`. What the cap still buys is
              the wide end: at 1440 the argument's column is about 700px, and a fourth verdict
              with a long description would set a 13px line wider than the 16px paragraph under
              it, which reads as the small text being the important text. What it no longer has
              to buy is the narrow end, where it was quietly failing — the column does that, at
              every width, by construction.

              In `rem`, and that is the correction rather than the value. This carried the same
              `max-w-[58ch]` the argument below it does, which reads as the two sharing a right
              edge and is not what it means: a `ch` is the advance of the used font's zero, so it
              follows the element's size. This line is 13px and the argument is 16px, so 58 of
              them is 556.80px there and 452.40px here — one class, two elements, two widths,
              twenty lines apart, the exact trap `ui/prose.tsx` spends four paragraphs warning
              about. `34.8rem` is 556.80px whatever this block is set at, and it stays that if
              somebody changes the size of this line.

              **The number moved with the face and the guard did not, which is the third round of
              this same mistake.** It was `38.5rem` — 616px, the round number just under Onest's
              58ch at 16px, which was 617.12px. Plex Sans's zero is 0.600em against Onest's
              0.665em, so the argument's own edge came in 60px and the guard stayed where it was,
              capping this line 59.2px past the paragraph it exists to line up with. Nothing
              rendered wrong, because the three strings are short; the test next door is what
              caught it, by resolving both edges from the class lists rather than trusting either
              figure. A `ch` under Onest also followed *weight* — 665 units on a 1000-unit em at
              400 against 661.8 at 600 — and the pair of figures on this line were wrong for six
              passes for that reason alone. Plex Sans ships static cuts that all advance at 600
              units, so weight drops out and size is the whole of it.
              `ui/font.test-metrics.ts` holds the advance and
              `features/review/finding-detail.test.tsx` recomputes every figure above.

              13px semibold is the scale's secondary-body row, and `text-ink-2` keeps it under
              the 16px argument. It is promoted in size and weight and never in hue, and never to
              the reading size: this is the product's sentence about a verdict, not the model's
              voice, and the one thing that marks the model's voice is that 16px is used nowhere
              else. The docket row above prints `descriptor.label` and never this, so the lede
              repeats nothing.

              It is also product-authored, which is why it can stand where a promoted first
              sentence of the model's could not. The longest recorded reasoning opens by saying
              the abstraction violates a policy, argues with itself twice in the open, and closes
              on the opposite verdict; a lede taken from the prose would print a claim the
              paragraph goes on to reverse, in the largest type on the page. */}
          <p
            className="max-w-[34.8rem] text-[13px] font-semibold leading-6 text-ink-2 lg:col-start-1 lg:row-start-1"
          >
            {descriptor.description}
          </p>
          {/* The only thing on the surface set at the reading size, and the reason it is one
              element rather than a class list: the measure, the leading, the sentence gap and
              the preserved line breaks all moved into `ModelProse`, which is now the only
              place in the product that sets 16px body.

              They moved because the argument for each of them applied to two other blocks that
              had never heard it. The review's synopsis on the report surface and a model's
              answer in a conversation are the same voice on the same terms — `Attribution`'s
              own doc comment says the first of those is "the same kind of thing" — and the
              three had reached `58ch`, `46ch` and `62ch` with only this one cut into sentences
              at all. Three treatments of one paragraph is what the design system's guards
              exist to prevent, and the fix for it is not a fourth hand-tuned class list.

              What stays here is the choice to render `finding.reasoning` and nothing about how.
              `ui/design-system.test.ts` fails the build if a second block reaches for the
              reading size, so this cannot silently grow its own recipe back. */}
          <ModelProse className="lg:col-start-1 lg:row-start-2">{finding.reasoning}</ModelProse>

          <div
            className="mt-1.5 min-w-0 lg:col-start-2 lg:row-start-2 lg:mt-0 lg:self-start lg:border-l lg:border-rule lg:pl-5 xl:pl-6"
          >
            {/* `mt-0`, because this is the rail's first line now and has to sit on the same
                baseline as the argument's first line beside it. `cn` is tailwind-merge, so it
                replaces `Footnote`'s own `mt-3` rather than fighting it. What stood above it
                was the verdict's description, which has gone to the head of the band — the
                comment arguing for that move went with it. */}
            <Footnote className="mt-0">{judgedAgainst(review)}</Footnote>

            {finding.hinge ? (
              <div className="mt-5">
                <BlockLabel>Hinges on</BlockLabel>
                {/* One of the pair is in a box and the other is not, which is a difference a
                    reader sees at a glance. They used to be two boxes drawn from two `Notice`
                    tones — `#fafafa` against `#ebebeb` on a white row, with both call sites
                    then overriding the text to full ink and cancelling the only other thing
                    the tones carried. Fifteen values of grey and a border alpha is not enough
                    to tell *the reason this finding is held* from *a course of action
                    nobody has taken yet*. So the hinge keeps the box, and the recommendation
                    is prose under its label.

                    `max-w-[30rem]`, which `Notice` itself has none of. Inside the rail it is
                    inert — the column is narrower. It exists for the stacked layout below
                    `lg`, where this box used to run the full width of the row: 1126px of
                    border around one 14px sentence, the widest element in the region by a
                    factor of two and a third, drawn around the smallest text in it. */}
                <Notice tone="working" className="mt-1.5 max-w-[30rem]">
                  <p id={hingeId} className="text-[14px] leading-relaxed text-ink wrap-anywhere">
                    <Prose>{finding.hinge}</Prose>
                  </p>
                  {waitingOn && onAnswer ? (
                    /* `link`, and the demotion runs one step further than the last pass took
                       it — not to a quieter button, but out of the button vocabulary.

                       Two passes argued about the fill on this control and both argued the
                       wrong axis. It was `primary`, which is `--accent-fill`, and
                       `docs/design-system.md` names the five jobs the accent is spent on: the
                       mark, the primary action, `--mark`, a material verdict, a review in
                       flight. This is none of them. It is not "the primary action" either,
                       though that is the tempting reading: the one action the screen is asking
                       for while a review is held is *answer the round*, and that action already
                       carries the page's primary, once, on the clarification card at the head
                       of the docket. A primary per held row is one action with N+1 primaries.
                       The second argument stands as well — `--held` is `#0a0a0a`, "waiting on a
                       person — full ink, present, not an alarm" — so the alarm hue on the held
                       verdict's own control puts back exactly the chroma the palette took off
                       the verdict.

                       What `secondary` then got wrong was the axis. It left five controls in an
                       open row at one recipe and two of them decide nothing: this one is
                       `onOpen("clarification")` in `docket.tsx`, and "Judgement context" in the
                       Measured column opens a drawer. The three voices give a bordered control
                       at control size to **Decided**, "the record of what a person chose", so a
                       way out wearing it is navigation dressed as a disposition — the blur the
                       voices exist to stop. The comment this replaces answered that with "which
                       of the four controls in an open row you meet first is said by position,
                       which is honest". Position can say order; it cannot say kind. And it does
                       not hold order either: on a cleared finding there is no hinge and no
                       control here at all, and "Judgement context" is left sitting a few
                       hundred pixels above three peers it is drawn identically to.

                       So the weight moves to shape. `link` is `PolicyRef`'s gesture in sans —
                       ink, an underline at `--rule-strong` going to the ink on hover, no box —
                       and the prominence a held finding is owed stays where the last pass put
                       it: this is the only interactive thing inside the only bordered block in
                       the band, under its own label, under the question itself. `size="md"`
                       still carries the 44px floor; that is a touch requirement and does not
                       depend on how a control is drawn.

                       Not `ghost`, which is the other quiet variant: `text-ink-2`, a
                       transparent border and a `bg-sunken` hover. The `working` Notice's ground
                       *is* `--sunken`, so a ghost here has no rest state a reader can find and
                       no hover state either. Not `quiet`, for the same collision, which is what
                       the last pass found.

                       The action stays here rather than moving down to the decision bar, and
                       the reason is the domain. That bar writes a `StandingDecision` for one
                       candidate on one branch; answering the round revises the case and judges
                       every candidate again. A fourth control among three peers would read as a
                       fourth disposition whatever it was drawn as.

                       `mt-1` rather than `mt-2.5`: `min-h-11` around a 14px line with `px-0`
                       and no fill brings about fifteen pixels of its own air above the words,
                       which is what the old margin was supplying.

                       No `aria-label`. It named the button "Answer the open question: …" with
                       the whole question folded in, so the visible words were not in the
                       accessible name — nothing to say for anyone driving the page by voice,
                       and a paragraph where a name should be for anyone listening. The question
                       is what `aria-describedby` is for, and it is on screen directly above.

                       How far down a phone this sits is carried in `docs/known-defects.md`, and
                       the number that entry was written from is unreachable. It put this
                       control "roughly 1,500px" below the top of the argument, reasoning from
                       the longest recorded reasoning — 2,139 characters, 57 line boxes in the
                       324px column a 390px viewport gives this block. Reproduced in the live
                       app that string does land the control 1,688px down. But it belongs to a
                       *material* finding, and a material finding has no hinge and therefore no
                       control here at all:
                       `FindingOutput.the_verdict_carries_what_it_is_allowed_to` in
                       `reasoning/adapters/langchain.py` refuses a hinge on any verdict but
                       `held`, and a question is generated per hinge rather than per verdict, so
                       `waitingOn` does not widen it either. Not one of the 306 recorded cleared
                       and material judgements carries a hinge; all 69 held ones do.

                       The arguments this control can stand under are those 69: 156 to 971
                       characters, against 2,139 for the corpus. Swept over all of them at
                       390x844 in the real app, each carrying its own recorded hinge and its
                       blocks cut by the real `sentences`, it lands 275px to 956px below the top
                       of the argument — median 624, five past the 844px viewport, eight past the
                       796px the sticky topbar leaves, none past 1,000. The worst case the
                       population admits at all is the longest held argument against the longest
                       recorded hinge, a pairing that has never occurred: 1,025px. None of the 69
                       reaches `MOST_PARTS`, so `pack` never runs on a held finding — every one of
                       them is cut one block to a sentence.

                       It is also the *first* control a phone reaches in an open row, which is
                       the half the entry left out. Measured below the end of the argument on the
                       same sweep: this at 144–303px, "Judgement context" at 884–1,043px, the
                       decision bar at 1,878–2,037px. Those last two are on every verdict. What a
                       phone buries in an open row is the decisions, and moving this one earlier
                       would make the row that has an extra way out the only row whose controls
                       arrive before its evidence. `tests/browser/test_mobile.py` holds the
                       ordering and the 4px.

                       The arrow is drawn. It was `&rarr;`, the forbidden glyph written as an
                       entity: the guard scans source for the character and an entity contains
                       none, while the browser renders U+2192 out of whatever the operating
                       system has, since neither of this product's latin subsets carries it. */
                    <Button
                      variant="link"
                      size="md"
                      className="mt-1"
                      aria-describedby={hingeId}
                      onClick={onAnswer}
                    >
                      Answer it
                      <ArrowRight aria-hidden="true" className="size-[13px]" />
                    </Button>
                  ) : null}
                </Notice>
                {/* No count after this sentence. It used to end "N answers recorded so
                    far", off a filter this file ran itself, which put a second answer total
                    five lines under the provenance line above — and `clarifications-surface`
                    exists because a bare count is the weaker half of what a reader wants
                    anyway. The Rounds surface has the answers themselves. */}
                <Footnote>{hingeFootnote(review, Boolean(openQuestion))}</Footnote>
              </div>
            ) : null}

            {finding.recommended_response ? (
              <div className="mt-5">
                <BlockLabel>Recommendation</BlockLabel>
                <p className="mt-1.5 max-w-[46ch] text-[14px] leading-relaxed text-ink wrap-anywhere">
                  <Prose>{finding.recommended_response}</Prose>
                </p>
              </div>
            ) : null}
          </div>
        </div>
      </section>

      {/* ── The exhibit: the readings beside the code they were taken from ───── */}
      <div
        className={cn(
          "grid border-t border-rule bg-surface-2",
          // A candidate with no excerpts has nothing to sit beside, and a 26rem column with
          // an empty half of the screen next to it reads as a layout that failed.
          //
          // 26rem, not 22. At 1440 the column with all the text was the narrow one and the
          // column that ran out of content was the wide one: two small excerpts ended and
          // left 535 rows of empty strip under them, while "a proxy, not a count" wrapped its
          // qualifier onto a second line 818px to the left. The other half of that is below —
          // "How it was detected" spans the grid rather than lengthening this column.
          finding.evidence.length > 0 && "lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]",
        )}
      >
        <section className="min-w-0 px-4 py-4 sm:px-5">
          <Attribution voice="Measured" by={counted.join(" · ") || undefined} />

          {/* Which code this is about — all of it, not just the one name the docket row is
              led by. A finding that a port has a single implementation is about two things,
              and the row can only carry the first. */}
          {finding.candidate.participants.length ? (
            <div className="mt-2.5">
              <BlockLabel>
                Involved code
                {/* `font-normal`, and this is a correction rather than a preference. Only 400
                    and 600 of IBM Plex Mono are loaded, so the `font-medium` that stood here
                    asked for a 500 that CSS font matching resolved down to 400 — the class
                    described a weight that never painted. What the count wants is to be
                    lighter than the 700 label it sits inside, which is exactly what 400
                    already was, so nothing moves on screen and the class now names what it
                    renders. The measurement value below took the other road and went to 600,
                    because there the emphasis was the point. */}
                <span className="font-mono font-normal normal-case tracking-normal">
                  {" · "}
                  {finding.candidate.participants.length}
                </span>
              </BlockLabel>
              {/* A name on its own line and what it does under it, rather than a chip with
                  the role stapled inside. `role` is only sometimes a word — the deterministic
                  detector writes "the only implementation of it in this repository", and a
                  sentence sharing a chip with an identifier squeezed the identifier to about
                  thirty pixels and broke it one character to a line.

                  And now without the chip's box, which was drawing nothing. `Tag` is filled
                  with `--surface-2`, which is the exact colour of the exhibit strip it sits
                  on — 1.00:1 — leaving a `--rule` hairline at 1.25:1 in light and 1.36:1 in
                  dark as the whole boundary, under the 3:1 a non-text edge is held to. It
                  cost ten pixels a side to say nothing. Rows on a rule instead, which is what
                  the readings twelve lines below already do, and the same 34rem measure so a
                  name and its role do not end up at opposite ends of the page below `lg`. */}
              <ul
                aria-label="Involved code"
                className="mt-1.5 max-w-[34rem] divide-y divide-rule border-t border-rule"
              >
                {finding.candidate.participants.map((participant) => (
                  <li
                    key={`${participant.qualified_name}-${participant.role}`}
                    className="flex max-w-full items-start gap-1 py-1.5"
                  >
                    <span className="min-w-0 max-w-full flex-1">
                      <Mono className="block text-[11px] text-ink wrap-anywhere">
                        {participant.qualified_name}
                      </Mono>
                      <span className="block text-[11px] leading-4 text-ink-3">
                        {humanise(participant.role)}
                      </span>
                    </span>
                    {/* The reviewer's next action after reading a finding is to go to the
                        code, and the qualified name is what an editor's *go to symbol* box
                        and a search take. */}
                    <CopyButton
                      value={participant.qualified_name}
                      label={`Copy ${participant.qualified_name}`}
                      className="mt-0.5 shrink-0"
                    />
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {measurements.length ? (
            // Readings on a rule, not a row of cards. A reading that has been put in a box is
            // asking to be looked at twice.
            //
            // The measure is the pairing. `justify-between` is right in the 26rem column
            // these were designed for and wrong below `lg`, where the grid collapses and the
            // same rows span the whole 76rem page — `referenced by` on the far left and `7`
            // on the far right, eight hundred pixels apart, is a pair the eye reconstructs
            // rather than reads. 34rem changes nothing in the column and holds it together
            // everywhere else.
            <dl className="mt-3.5 max-w-[34rem] border-t border-rule">
              {measurements.map((item) => (
                <div key={item.name} className="border-b border-rule py-2">
                  <div className="flex items-baseline justify-between gap-3">
                    <dt className="min-w-0 text-[12px] font-semibold text-ink-2 [overflow-wrap:anywhere]">
                      {measurementLabel(item.name)}
                      {item.nature === "structural_proxy" ? (
                        <span className="font-normal text-ink-3"> · a proxy, not a count</span>
                      ) : null}
                    </dt>
                    {/* 14px, not 16. Sixteen is the row the type scale gives to the model's
                        reasoning — "its own size, used nowhere else" — and it is the whole
                        device that keeps the model's voice apart from the machine's. Setting
                        a deterministic count at it made the numeral the largest glyph in the
                        lower half of an open row and told the reader the wrong thing about
                        where it came from. The reading is still the anchor of its line: mono,
                        tabular, right-aligned against a 12px label.

                        `font-semibold`, not `font-medium`. Only 400 and 600 of IBM Plex Mono
                        are loaded, so CSS font matching resolves a desired 500 down to 400 —
                        the emphasis this line believed it had never arrived. The other six
                        mono `font-medium` call sites and the scale row that publishes "14 |
                        Mono, 500" are one decision and are not this file's to take. */}
                    <dd className="shrink-0 font-mono text-[14px] font-semibold tabular-nums text-ink">
                      {item.value}
                      {item.unit ? <span className="text-[11px] text-ink-3"> {item.unit}</span> : null}
                    </dd>
                  </div>
                  {item.definition ? (
                    <p className="mt-1 text-[11.5px] leading-snug text-ink-2">{item.definition}</p>
                  ) : null}
                </div>
              ))}
            </dl>
          ) : (
            <p className="mt-2.5 text-[12.5px] leading-6 text-ink-3">
              This pattern is detected structurally and carries no counts.
            </p>
          )}

          {/* The deeper audit — the case, the policy corpus, what else touches this code, the
              retrieval behind it — at the foot of the machine's own column, which is where a
              reader who wants more of it has just finished reading. It used to sit beside the
              MEASURED label, where a ghost button with no border read as a second heading.

              `link` rather than `secondary`, and that old heading problem is why it is this
              variant and not the ghost it once was: a way out is a line of underlined words
              with an arrow on it, and no block label in this product wears an underline. It
              opens a drawer and records nothing, so it is the same kind of control as "Answer
              it" in the band above and is drawn the same way — which leaves the `secondary`
              recipe meaning one thing in an open row, *this writes a decision*. That is the
              half of the change a cleared or material finding can see, since neither has a
              hinge and this is their only way out.

              `sm` stays. Size is density and shape is kind: this is the dense foot of a column
              rather than the answer to a question, and `sm` grows to the 44px floor by itself
              on a coarse pointer. `mt-2`, not `mt-3.5`, because `min-h-8` with `px-0` around a
              12px line now brings ten pixels of its own air. `px-0` also sets it flush with the
              left edge of the `dl` above it, which a `secondary`'s `px-2.5` had it inset from. */}
          {onOpenContext ? (
            <Button variant="link" size="sm" className="mt-2" onClick={onOpenContext}>
              Judgement context
              <ArrowRight aria-hidden="true" className="size-[12px]" />
            </Button>
          ) : null}
        </section>

        {/* The part that used to be behind a disclosure, and the reason it now takes the
            wider column: you cannot argue with a judgement whose evidence is one click away,
            and you cannot read source code in a gutter. */}
        {finding.evidence.length ? (
          <section className="min-w-0 border-t border-rule px-4 py-4 sm:px-5 lg:border-l lg:border-t-0">
            {/* How many files the evidence spans, not where the first card happens to be.
                The header used to repeat the first excerpt's own location — which that card
                prints 34px below it — and in doing so labelled a column that also holds
                `adapters.py` as though it were all `ports.py`. A reader takes a location under
                a block label as the scope of the block. Each card carries its own `PathRef`;
                the header answers the question the cards cannot. */}
            <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
              <BlockLabel>Evidence</BlockLabel>
              {evidenceFiles ? (
                <Mono className="text-[11px] text-ink-3">{plural(evidenceFiles, "file")}</Mono>
              ) : null}
            </div>
            <div className="mt-1.5 grid gap-2">
              {finding.evidence.map((evidence, index) => (
                <EvidenceBlock
                  key={`${evidence.location?.path}-${index}`}
                  description={evidence.description}
                  path={evidence.location?.path}
                  startLine={evidence.location?.start_line}
                  endLine={evidence.location?.end_line}
                  excerpt={evidence.excerpt}
                />
              ))}
            </div>
          </section>
        ) : null}

        {/* Across the grid rather than down the readings column. It is prose, and prose is
            what the narrow column was worst at: at 1440 the readings ran on while two small
            excerpts beside them ended and left half the strip empty, so the block with a
            measure was in the 26rem column and the block with nothing left to show had 818px.
            Moving the one paragraph in the Measured half out of the column brings the two
            within a few hundred pixels of each other and gives the sentence its own measure.
            It stays on the strip, because it is still the machine's voice. */}
        <section className="min-w-0 border-t border-rule px-4 py-4 sm:px-5 lg:col-span-2">
          <BlockLabel>How it was detected</BlockLabel>
          {/* `wrap-anywhere` for a rationale that names something long in the middle of a
              sentence. The common case — a 64-character participant fingerprint at the end of
              it — is split off below instead, because a hash flowed through a paragraph in the
              sans face breaks mid-hash with no visual seam, and 0/O and 1/l stop being
              distinguishable in a face that was never asked to keep them apart. */}
          <p className="mt-1 max-w-[46ch] text-[12.5px] leading-6 text-ink-2 wrap-anywhere">
            {detected.prose}
          </p>
          {detected.fingerprint ? (
            <span className="mt-1.5 flex items-start gap-1">
              <Mono className="text-[11px] text-ink-3">{shortId(detected.fingerprint, 12)}</Mono>
              <CopyButton
                value={detected.fingerprint}
                label="Copy the participant fingerprint"
                className="-my-1 shrink-0"
              />
            </span>
          ) : null}
          {finding.candidate.limitations ? (
            <Footnote className="mt-2">{finding.candidate.limitations}</Footnote>
          ) : null}
        </section>
      </div>

      {/* ── The audit, folded away, each with a closed state that says what is inside ── */}
      <Disclosure label="Policies" summary={policiesSummary(finding, retrieval)}>
        {finding.policies.length ? (
          /* `24.3rem`, and neither half of that number is `46ch`.
              A `ch` is the advance of the zero of the element's **own** used font, and this
              `ul` declares no font size, so `max-w-[46ch]` resolved against the 16px it
              inherited from the root — a whole size larger than the `text-[14px]` note inside
              it. The name said one measure and the layout drew another, which is the defect
              `ui/markdown.tsx` carries a paragraph about, in a second file.
              The second half is subtler and survives fixing the first. The cap is on the
              *card*, and a measure is a property of the text: the card spends 30px on its own
              `px-3.5` and its two hairlines, so whatever is written here the note reads 30px
              narrower. Writing the text's measure on the box around it is off by whatever that
              box costs.
              So the cap is the note's measure plus the card: `46ch` at the 13px the note is
              now set in is 358.80px, and 358.80 + 30 is 388.80px, which is `24.3rem` exactly.

              **`46ch` is 46 advances of the zero, and not 46 characters.** The sentence this
              replaces said characters, and the two are well apart: 358.80 is 46 x 13 x 0.600,
              the advance read off the shipped `plex-sans-400.woff2` and held once in
              `ui/font.test-metrics.ts`, while a character of body text on a full line costs
              less than a zero does. The note then stops in the same place as the "No policy
              applied here" paragraph below, which is this list's own empty state at
              `max-w-[46ch] text-[13px]` — the two answers to one question, ending in one place.
              That `ui/markdown.tsx` arrives at a similar figure from 46ch at 14px on the block
              itself is a coincidence of two derivations, not a shared constant, and the two
              must not be made into one.

              **The character counts this paragraph used to carry were Onest's, and they are
              gone rather than converted.** It said the note read at 60.58 characters a line
              over 1,531 full lines, and 65.47 at the width and size it had before — both real
              measurements, both a `Range` per character over all 514 recorded notes in a
              headless Chromium, and both properties of a face this product no longer
              downloads. A zero advance is four bytes of `hmtx` and could be re-read here; an
              average character on a full line needs the built bundle, a browser and a
              `workspace.sqlite3` that is not checked in. `docs/known-defects.md` carries the
              re-sweep as an open item. Converting them by ratio would have been the eighth
              round of a number in prose being a copy of a measurement.

              **That number is now the width of a column rather than the width of the list**,
              and it is the same number for the same reason. It was written as `max-w` on the
              `ul`, which caps the card only for as long as there is one card to a row — and
              there is a great deal of row. The docket runs in a `max-w-[76rem]` column, so this
              fold body measures **1,126px at a 1280px viewport and at every width above it**,
              which is the same 1126 this file already argues from twice. Two policies therefore
              spent two rows and one card's width of 1,126, and left most of the fold empty,
              while each note read at exactly the measure derived above.
              `repeat(auto-fill,minmax(0,24.3rem))` moves the cap on to the track, which is
              what the paragraph above says it should have been on all along — the cap belongs
              to the card, and a measure is a property of the text inside it. Each card is at
              most 388.80px, the note inside it draws at 358.80px, and the browser test named
              below measures both rather than trusting this sentence.

              **Intrinsic sizing rather than a container query or a breakpoint**, and the choice
              is available rather than clever. Tailwind is 4.3.3, so `@container` is in core and
              nothing in `frontend/src` uses it yet; a viewport breakpoint would be the wrong
              question outright, because this fold sits inside a docket row inside a panel and
              the panel is not the viewport. But `auto-fill` already answers the right question
              and answers it continuously: the repetition count is computed from the grid's own
              resolved inline size, so it needs no `@container` wrapper, no `container-type`
              containment on a shared `Disclosure` body, and no width written down twice. A
              second column needs 864px of fold — two tracks and the 8px gap — which the fold
              has from a 1024px viewport (934px of body) and has not at 768 (678px). Below 436px
              the formula gives no column at all and `auto-fill` floors it at one; the single
              track then shrinks to the space there is and the card fills the column exactly as
              it did before, so at 390px the fold is 324px, the card is 324px and the note is
              294px, all three unchanged by this edit.

              **How many columns actually get used is settled by the store, not by the grid.**
              Over the 148 findings in `core_review_snapshots`, 69 carry one policy (46.6%) and
              79 carry two (53.4%); none carries none and none carries three. Widen to all 379
              stored findings — those 148 plus the 231 in `core_finding_cache` — and the shape
              holds: 33 with none, 178 with one, 163 with two, and **5 with three, which is the
              most any of them has ever held**. Two columns is therefore the whole of the case,
              and it is also all the fold has room for: `floor((1126 + 8) / 396.8)` is 2, so no
              width this docket reaches offers a third track. That is the answer to the question
              a hand-written `grid-cols-3` would have got wrong from both ends — it would leave
              a third of its row empty on the 53% that carry two, and it would not fit. One
              policy draws exactly what it drew before, and the 5 findings with three draw two
              and then one.

              **Natural height, not equal height**, which is the one place a card grid usually
              goes the other way. A grid item stretches by default and `items-start` is what
              stops it. Two things decide it here. The card has nothing at its bottom edge — no
              action, no footer, no figure — so an equalised bottom hairline would be aligning
              nothing against nothing. And the notes are genuinely unequal: over the 168 stored
              findings holding more than one policy the two notes differ by 43 characters at the
              median and 70.6 at the mean, but 10 of them differ by more than 200 and the worst
              real pair is **1,080 characters against 340**. Drawn side by side at the measure
              this fold had under Onest those were a 504.00px card and a 195.50px one, so
              stretching would have handed the short one 308.50px of nothing — and because the
              fold body is `--sunken` and the card has no fill of its own, that emptiness is the
              same colour on both sides of the rule it is enclosed by. It reads as a box drawn
              too big rather than as a card. The two heights are a browser reading of a face
              this product no longer downloads and both grow at the narrower measure Plex Sans
              gives; the character counts they come from are a property of the store and are
              what the argument rests on.
              A ragged lower edge on two bordered columns is the cheaper failure, and at the
              median difference of 43 characters it is under one line of it.

              The `Footnote` under the list keeps its own `max-w-[46ch]`, which is 331.20px at
              its 12px, and it stays at the fold's left edge under the first column. It is the
              caption for the whole fold rather than for a card, and letting a 12px line run the
              two columns' full width would put it well past **556.80px**, which is where the
              model's own paragraph stops and is the widest reading measure in the product.
              `features/review/finding-detail.test.tsx` holds that 331.20 as one of the four
              widths this surface is allowed to resolve a `46ch` to, so it is not free to move.

              Geometry, so jsdom can see none of it:
              `tests/browser/test_policies_grid.py` is what fails when this stops being true. */
          <ul className="grid grid-cols-[repeat(auto-fill,minmax(0,24.3rem))] items-start gap-2">
            {/* A hairline card with no fill, for the reason `EvidenceBlock` has none: the
                fold body it sits in is `--sunken`, and every other ground in the ramp is above
                it in light and below it in dark, so a filled card would read as raised in one
                theme and as a hole in the other. The body moving from `--surface-2` to
                `--sunken` did not weaken that argument, it widened it — `--surface` and
                `--surface-2` now sit on the same side of this card in each theme.

                `--rule-strong`, because with no fill the hairline is the entire boundary. A
                boundary that groups clears 1.6:1 and `--rule` measures 1.28:1 on this ground,
                which is a card outlined rather than edged; `--rule-strong` is 1.67:1 in light
                and 2.32:1 in dark.

                And the id at 11px rather than at 10.5px — the size was there to keep a link
                with no touch box from looking heavy, and the link has a touch box now. The v2
                scale puts the mono evidence tier at 12.5px/500 and this call site has not
                moved to it; neither have `Attribution`'s identity line, the participant names,
                the detection fingerprint or the evidence file count, and that pass wants
                taking over the file in one go rather than four. */}
            {finding.policies.map((bearing) => (
              <li key={bearing.policy_id} className="rounded-md border border-rule-strong px-3.5 py-3">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                  <span className="text-[13px] font-semibold text-ink">{bearing.policy_title}</span>
                  <PolicyRef id={bearing.policy_id} />
                </div>
                {/* MODEL PROSE THAT IS NOT THE JUDGED VOICE, which is a claim worth the space
                    because the obvious move is the wrong one.
                    The store holds **514 distinct** notes over 519 occurrences — a fifth
                    surface of model-written prose, and until this pass every figure the
                    repository argued from was over the 375 `finding.reasoning` strings and
                    none of them. They are short: 187 characters at the median against the
                    judgement's own longer strings, 25 of the 514 over 400, one at 1,080.
                    `ModelProse` exists exactly so a surface can opt into "this is model prose"
                    rather than restate what that means, and three surfaces already do. This
                    one does not, for two reasons that are measurements rather than taste.
                    The first is that the component would do nothing here. Run `sentences` over
                    all 514 and **432 of them — 84% — come back as a single part**, because a
                    policy note is one sentence with a full stop at the end and nothing after
                    it. The judgement corpus is 5.9% single-part and 38.7% three-part. So the
                    one-block-per-sentence device fires on 16% of this surface, the packing
                    ceiling on 0.8%, and `whitespace-pre-line` on none at all: not one of the
                    514 contains a newline, against a judgement corpus where two do.
                    The second is placement, which is what the design system says the voices
                    are carried by. Judged is three things at once — the reading size, a block
                    alone in a band, and a `JUDGED · <model>` line naming who wrote it. A note
                    here is none of them: it is one card among several, the fold body under it
                    is `--sunken`, and the line above it names a **policy** and its id. A
                    second 16px full-ink block on this page would tell a reader there are two
                    judgements in the finding, which is the one thing the size is spent saying.
                    What was wrong was the size, and it was wrong by being a fourth one. The sentences
                    around it are 13px on `leading-6` — this list's own empty state, which is
                    the other answer to the same question, and the closing paragraph of
                    `InvestigationTranscript` in the fold below — so the fold answered one
                    question at 14px or at 13px depending on whether a policy happened to bear.
                    The retrieval footnote under the list is 12px on `leading-5` and is not in
                    that set; it is a caption for the fold rather than a sentence in it, and
                    `Footnote` is where its size is argued. `leading-relaxed` went with
                    it for the same reason: it is 1.625, and nothing else in the fold uses it.
                    `Prose` stays. Only 13 of the 514 carry a backtick, against 64 of 375 in
                    the judgements, but a quoted name rendered as a literal backtick is the one
                    failure that is unambiguous rather than a matter of degree. */}
                <p className="mt-1.5 text-[13px] leading-6 text-ink-2 wrap-anywhere">
                  <Prose>{bearing.reasoning}</Prose>
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="max-w-[46ch] text-[13px] leading-6 text-ink-2">
            No policy applied here. The model was given the case, the measurements and
            the evidence, and reached the verdict without a policy to weigh it against.
          </p>
        )}
        {retrieval ? (
          <Footnote>
            {retrieval.retriever} found {retrieval.selected_policy_ids.length} policies for
            this candidate. {finding.policies.length} applied.
          </Footnote>
        ) : (
          <Footnote>No retrieval was recorded against this candidate.</Footnote>
        )}
      </Disclosure>

      {/* The lookups behind a hinge, so a reader can tell "the repository is silent" from
          "nothing checked". Absent entirely where nothing looked — an empty fold would be a
          claim that something did. */}
      {investigation ? (
        <Disclosure label="Looked up" summary={investigationSummary(investigation)}>
          <InvestigationTranscript investigation={investigation} />
        </Disclosure>
      ) : null}

      {/* The one fold whose closed state really is a machine string, so the one that keeps
          the mono voice.

          Both halves shortened. It led with the full prompt identity and applied `shortId` to
          only the value beside it, so the line a reader scans on a phone ran to three or four
          wrapped lines of hex before reaching the fact it exists to carry — which is the
          argument `retrievalLabel` makes eight hundred lines above and then was not applied
          here. The whole of both values is inside, in `Provenance`, with a clipboard. */}
      <Disclosure
        label="Provenance"
        machine
        summary={
          retrieval
            ? `Prompt ${shortId(finding.prompt_identity, 12)} · corpus ${shortId(retrieval.corpus_fingerprint, 12)}`
            : `Prompt ${shortId(finding.prompt_identity, 12)} · no retrieval recorded for this candidate`
        }
      >
        {/* Space, not nine hairlines. This is the block `docs/design-system.md` reaches for
            when it says the structural order was backwards in practice: nine rows of a
            definition list held apart by `--rule`, which measures 1.28:1 on this ground and
            separates nothing — it adds eight grey bands to a block already made of grey.
            Separate with space, then a rule, then a fill, then a border, and stop at the first
            that works. Space works here, at any contrast, in both themes, and costs only
            height.

            20px of gap against the 24px line box a value sits in — under a line, which is far
            enough to find the next key and not far enough to read as nine blocks. `py-0` moves
            the row's own padding into that gap rather than adding to it, so the rows are one
            distance apart rather than two summed. Nine rows and eight gaps come out 8px taller
            than the same nine rows with their own `py-2` and eight hairlines between them, and
            the first and last now sit 8px closer to the fold's own `py-4`. That is the whole
            cost of the change.

            Turned off at this call site rather than in `ui/meta.tsx`. `MetaList` also draws
            the context rail, where the rows are single lines under a panel header and a rule
            still has a job to do. This fold is the one where nine of them stack. */}
        <MetaList className="flex flex-col gap-5 divide-y-0">
          <HashRow label="Candidate" value={finding.candidate.id} />
          <HashRow label="Judge" value={finding.model_identity} />
          <HashRow label="Prompt" value={finding.prompt_identity} />
          <HashRow label="Retrieval" value={finding.retrieval_identity} />
          {finding.investigation_identity ? (
            <HashRow label="Investigation" value={finding.investigation_identity} />
          ) : null}
          {retrieval ? (
            /* `text-ink` for the reason `HashRow` gives above: every value in this list is the
               content of its row and every key is the caption on it, and a retriever's name is
               not the one exception to that. */
            <MetaRow label="Retriever" className="py-0">
              <Mono className="text-ink [overflow-wrap:anywhere]">
                {retrieval.retriever}/{retrieval.version}
              </Mono>
            </MetaRow>
          ) : null}
          {retrieval ? <HashRow label="Corpus" value={retrieval.corpus_fingerprint} /> : null}
          {measurements.length ? (
            <MetaRow label="Measured as" className="py-0">
              {/* The chips lift off their ground, and the fold body moving to `--sunken` is
                  what does it rather than anything written here. `Tag` is filled with
                  `--surface-2` and this fold body used to be `--surface-2` as well: four boxes
                  at 1.00:1 against what they sat on, held off it by a `--rule` hairline alone.
                  That is the "outlines around nothing" `docs/design-system.md` names this
                  surface for, and it was a pair of declarations agreeing rather than a value
                  being wrong. On `--sunken` the same fill is a real step: 1.16:1 in light and
                  1.15:1 in dark.

                  `--rule-strong`, because a step that small is not a boundary and `--rule` is
                  not one either. A boundary that groups — a chip, a table head — clears 1.6:1;
                  on this ground `--rule` is 1.28:1 against `--rule-strong`'s 1.67:1 in light
                  and 2.32:1 in dark.

                  The fill runs the opposite way in each theme, because `--sunken` is the top of
                  the dark ramp and near the bottom of the light one, so a chip reads as raised
                  in light and recessed in dark. That is the objection the policy cards in the
                  fold above answer by carrying no fill at all, and it is answered differently
                  here on purpose: at card size the direction is what a reader reads, and at
                  pill size the shape has already said what the box is.

                  Everything the `Mono` inside used to declare — the size, the ink tier, the
                  wrapping — is now what `Mono` declares, and the machine name goes to the
                  evidence tier with the hashes above it. */}
              <span className="flex flex-wrap gap-1.5">
                {measurements.map((item) => (
                  <Tag key={item.name} className="border-rule-strong">
                    <Mono>{item.name}</Mono>
                  </Tag>
                ))}
              </span>
            </MetaRow>
          ) : null}
          {firstLocation ? (
            /* The one thing in this fold that goes somewhere, and therefore the only thing in
               it allowed a hue. `--mark` is provenance and the route back to a source — a file
               path is the first example the design system gives — and it is what `PolicyRef`
               already spends in the fold above.

               It is not spent here yet, and the reason is one file over: `PathRef` paints its
               own button `text-ink` from the v1 position that `--mark` *was* ink, which its
               doc comment in `ui/meta.tsx` still argues. v2 gives the mark a hue of its own, so
               that line is the change, and it has to be made there rather than overridden here
               — `PathRef` is the product's single device for "this is the way back to the
               source" and it is drawn in six files. */
            <MetaRow label="First location" className="py-0">
              <PathRef
                path={firstLocation.path}
                line={firstLocation.start_line}
                endLine={firstLocation.end_line}
              />
            </MetaRow>
          ) : null}
        </MetaList>
      </Disclosure>
    </div>
  );
}
