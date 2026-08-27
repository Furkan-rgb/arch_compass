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
      ? `${plural(bore, "policy", "policies")} bore on this · no retrieval recorded`
      : "No retrieval was recorded for this candidate";
  }
  const retrieved = retrieval.selected_policy_ids.length;
  if (bore) return `${plural(bore, "policy", "policies")} bore on this · ${retrieved} retrieved`;
  if (retrieval.corpus_fingerprint === EMPTY_CORPUS) {
    return "No policy corpus was configured · nothing was searched";
  }
  if (!retrieved) return "The corpus was searched · nothing came back above the threshold";
  return `0 of ${retrieved} retrieved policies bore on this judgement`;
}

/**
 * A fact that supports the block above it, said in one line.
 *
 * `46ch`, not the `62ch` this and every other measured block in the product used to carry.
 * `ch` is the width of Onest's zero, which is about `0.65em` — so `62ch` resolved to roughly
 * 650px at the reading size and admitted 89 lowercase characters, forty per cent more than
 * the number implied. The unit is kept, because it keeps the measure proportional to the size
 * the block is set at; the number is corrected to the 30em a measure actually is.
 *
 * It is the supporting measure now, and no longer the only one. The model's argument left
 * `46ch` for `58ch`, because that same proportionality cuts the other way at the reading
 * size: `ch` scales with the type, so an equal `ch` on a 16px paragraph and on this 12px
 * footnote gives them the same *character count* at two different widths — and the block set
 * largest then held the fewest words on the surface. The count, counted in a browser over the
 * recorded corpus rather than assumed, is **59**: 46ch is 367.08px here, and on that measure a
 * line that is not the last of its block carries 59.0 characters. Fifty-nine is a footnote's
 * line and **75.7** is an argument's, which is the `58ch` next door — measured the same way, and
 * the two are stated in one quantity on purpose, because the whole subject of this comment is a
 * pair of numbers that meant different things while wearing the same words. A footnote is a
 * line under a block and wants the shorter measure; an argument is read and wants the longer.
 *
 * "The same way" is now a method rather than a promise, because this pair has been re-measured
 * four times and moved three: serve the built bundle, render all 375 recorded strings through
 * the real `ModelProse` with its quoted names drawn as chips, cluster a Range per character on
 * the vertical centre of its box, and average the lines that are not the last of their block.
 * The 59 has held every time. The 73 beside it was the same sweep taken over the *string* rather
 * than over the render, which loses the width a mono chip adds; it is 75.7.
 *
 * The half of that method nobody wrote down, and the half that decides the last digit of both
 * numbers: a soft wrap eats a space that is drawn on no line, and it is counted here as
 * belonging to **the line it ended**, so a line holds the source from its own first visible
 * character up to the next line's first. `docs/design-system.md` states the choice and the
 * reason. Counted as the visible run instead, first ink to last, this pair is 58.1 and 74.7 —
 * both perfectly defensible numbers, and not these ones. That is the whole reason this comment
 * has moved three times.
 *
 * 46ch here is 367.08px because a footnote inherits weight 400. It is not 395.76px, which is
 * what the same 46ch resolves to twenty lines up on the 13px `font-semibold` lede, since Onest's
 * zero is 665 units on a 1000-unit em at 400 and 661.8 at 600.
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
 * A finding says which policies bore on it and prints the id it cites them under, and until
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
 * was tappable. This one was a bare line of 11px type with no box at all — well under the
 * 24px minimum, let alone the 44px floor the rest of the product holds. The padding makes the
 * touch box; the matching negative margin hands those pixels straight back to the layout, so
 * nothing moves. A call site that wants to space it does so on a wrapper — `cn` is
 * tailwind-merge, and a `mt-*` passed here sits beside the `-my-3` rather than replacing it.
 */
export function PolicyRef({ id, className }: { id: string; className?: string }) {
  return (
    <Link
      to={`/policies?open=${encodeURIComponent(id)}`}
      title={`Read the policy ${id}`}
      className={cn(
        "-my-3 inline-block py-3 font-mono text-[11px] text-mark underline decoration-rule-strong underline-offset-2 transition hover:decoration-current [overflow-wrap:anywhere]",
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
 */
function HashRow({ label, value }: { label: string; value: string }) {
  return (
    <MetaRow label={label}>
      <span className="flex min-w-0 items-start gap-1">
        <Mono className="min-w-0 flex-1 [overflow-wrap:anywhere]">{value}</Mono>
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
   * threshold" in 11px monospace reads as an identifier that has gone wrong — the failure
   * `surfaces.tsx` names by hand a few files over. So the caller says which voice its own
   * summary is in, and English goes at the footnote step in sans.
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

          `hover:bg-sunken`, not `hover:bg-surface-2`: `#ffffff` to `#fafafa` is five values,
          which is a division a reader is not asked to notice and nowhere near a state that
          appears under a pointer. `--surface-2` is also what the open body is filled with,
          so a hover in it would have been the row previewing its own contents.

          `sm:px-5` rather than `sm:px-6`, so the left edge of an open finding stops stepping
          in and out: the argument, the readings, the evidence and the decision bar all resolve
          to 16px below `sm` and 20px above it, and four pixels is enough to read as a
          misalignment against a hairline and not enough to read as an indent. */}
      <summary className="flex min-h-11 list-none items-start gap-3 px-4 py-3 transition hover:bg-sunken focus-visible:-outline-offset-2 sm:px-5">
        <ChevronDown className="mt-0.5 size-4 shrink-0 text-ink-3 transition group-open:rotate-180" />
        <Label className="shrink-0 leading-5 text-ink">{label}</Label>
        <span
          className={cn(
            "min-w-0 flex-1 text-[12px] leading-5 text-ink-3 [overflow-wrap:anywhere]",
            machine && "font-mono text-[11px]",
          )}
        >
          {summary}
        </span>
      </summary>
      <div className="border-t border-rule bg-surface-2 px-4 py-4 sm:px-5">{children}</div>
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
  const answered = review.case.answers.filter((answer) => answer.status === "answered");
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
        {/* `mt-2.5` is the gap under a 10px attribution label, and `gap-y-3.5` is the gap
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
            is not the same as one number: 38.5rem is 616px and the argument's column is
            `1fr` — 582px at a 1024px viewport, 600px at 1040, and only from about 1060 up is it
            wide enough for the cap to be the narrower of the two. Measured at 1024 the sentence
            was capped 34.00px past the argument it stands over. Latent, because the three
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

              `max-w-[38.5rem]` is a guard, not a measure, and now a guard against one thing
              rather than two. The three descriptions in `lib/format` are 51, 60 and 60
              characters, so at 13px the line is about 390px and wraps only below `sm`. What the
              cap still buys is the wide end: at 1440 the argument's column is about 700px, and
              a fourth verdict with a long description would set a 13px line wider than the 16px
              paragraph under it, which reads as the small text being the important text. What
              it no longer has to buy is the narrow end, where it was quietly failing — the
              column does that, at every width, by construction. The `46ch` it replaced was
              395.76px against a string needing 390 — one character from wrapping a one-line
              sentence.

              In `rem`, and that is the correction rather than the value. This carried the same
              `max-w-[58ch]` the argument below it does, which reads as the two sharing a right
              edge and is not what it means: a `ch` is the advance of the used font's zero, so it
              follows the element's size *and its weight*. This line is 13px `font-semibold` and
              the argument is 16px at 400, and Onest's zero is 665 units on a 1000-unit em at
              wght 400 but 661.8 at wght 600 — so 58 of them is 617.12px there and 499.00px here,
              a gap of 118.12px. One class, two elements, two widths, twenty lines apart — the
              exact trap `ui/prose.tsx` spends four paragraphs warning about. Both figures on
              this line were wrong until the seventh pass, at 398px and 501px, because both were
              taken at 400 on a block set at 600; `docs/design-system.md` carries the weights and
              `ui/markdown.test.tsx` recomputes the arithmetic. 38.5rem is 616px whatever this
              block is set at, and it stays that if somebody changes the size of this line.

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
            className="max-w-[38.5rem] text-[13px] font-semibold leading-6 text-ink-2 lg:col-start-1 lg:row-start-1"
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
            <Footnote className="mt-0">
              Judged against case revision {review.case.revision} and{" "}
              {plural(review.case.answers.length, "answer")}.
            </Footnote>

            {finding.hinge ? (
              <div className="mt-5">
                <BlockLabel>Hinges on</BlockLabel>
                {/* One of the pair is in a box and the other is not, which is a difference a
                    reader sees at a glance. They used to be two boxes drawn from two `Notice`
                    tones — `#fafafa` against `#ebebeb` on a white row, with both call sites
                    then overriding the text to full ink and cancelling the only other thing
                    the tones carried. Fifteen values of grey and a border alpha is not enough
                    to tell *the reason this finding is held* from *a suggestion the product
                    explicitly disclaims*. So the hinge keeps the box, and the recommendation
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
                       system has, since neither Onest nor Plex Mono ships it. */
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
                <Footnote>
                  {hingeFootnote(review, Boolean(openQuestion))}{" "}
                  {plural(answered.length, "answer")} recorded so far.
                </Footnote>
              </div>
            ) : null}

            {finding.recommended_response ? (
              <div className="mt-5">
                <BlockLabel>Recommended response</BlockLabel>
                <p className="mt-1.5 max-w-[46ch] text-[14px] leading-relaxed text-ink wrap-anywhere">
                  <Prose>{finding.recommended_response}</Prose>
                </p>
                <Footnote>
                  A recommendation, not a change. ArchCompass does not write the fix.
                </Footnote>
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
          <ul className="grid max-w-[46ch] gap-2">
            {/* A hairline card with no fill, for the reason `EvidenceBlock` has none: the
                fold body it sits in is `--surface-2`, and `--surface` is above it in light
                and below it in dark, so the same card read as raised in one theme and as a
                hole in the other. And the id at the 11px mono step the scale contains rather
                than at 10.5px, which it does not — the size was there to keep a link that had
                no touch box from looking heavy, and the link has a touch box now. */}
            {finding.policies.map((bearing) => (
              <li key={bearing.policy_id} className="rounded-md border border-rule px-3.5 py-3">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                  <span className="text-[13px] font-semibold text-ink">{bearing.policy_title}</span>
                  <PolicyRef id={bearing.policy_id} />
                </div>
                <p className="mt-1.5 text-[14px] leading-relaxed text-ink-2 wrap-anywhere">
                  <Prose>{bearing.reasoning}</Prose>
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="max-w-[46ch] text-[13px] leading-6 text-ink-2">
            No policy bore on this judgement. The model was given the case, the measurements and
            the evidence, and reached the verdict without a policy to weigh it against.
          </p>
        )}
        {retrieval ? (
          <Footnote>
            {retrieval.selected_policy_ids.length} retrieved for this candidate by{" "}
            {retrieval.retriever}; {finding.policies.length} bore on the judgement.
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
        <MetaList>
          <HashRow label="Candidate" value={finding.candidate.id} />
          <HashRow label="Judge" value={finding.model_identity} />
          <HashRow label="Prompt" value={finding.prompt_identity} />
          <HashRow label="Retrieval" value={finding.retrieval_identity} />
          {finding.investigation_identity ? (
            <HashRow label="Investigation" value={finding.investigation_identity} />
          ) : null}
          {retrieval ? (
            <MetaRow label="Retriever">
              <Mono className="[overflow-wrap:anywhere]">
                {retrieval.retriever}/{retrieval.version}
              </Mono>
            </MetaRow>
          ) : null}
          {retrieval ? <HashRow label="Corpus" value={retrieval.corpus_fingerprint} /> : null}
          {measurements.length ? (
            <MetaRow label="Measured as">
              <span className="flex flex-wrap gap-1.5">
                {measurements.map((item) => (
                  <Tag key={item.name}>
                    <Mono className="text-[11px] text-ink-2 wrap-anywhere">{item.name}</Mono>
                  </Tag>
                ))}
              </span>
            </MetaRow>
          ) : null}
          {firstLocation ? (
            <MetaRow label="First location">
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
