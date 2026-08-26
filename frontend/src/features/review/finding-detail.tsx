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
import { Prose } from "../../ui/prose";
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
 * important each part is. The model's argument is two or three sentences and caps at `46ch`,
 * so it takes the full width and stops; the evidence is source code, which needs every pixel
 * it can get. A first attempt put the argument in a `1fr` column beside a `24rem` one holding
 * everything the machine produced, and got both wrong at once: seven hundred pixels of empty
 * left column padded out to match its neighbour, and `class Clock(Protocol):` clipped in a
 * gutter. So the argument is a band across the top, and under it the readings take a narrow
 * column beside the excerpts, which take the rest.
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
      {/* ── The argument, across the top ─────────────────────────────────────── */}
      <section className="min-w-0 px-4 py-4 sm:px-5">
        <Attribution
          voice="Judged"
          by={`${finding.model_identity} · ${retrievalLabel(finding, retrieval)}`}
        />
        {/* The only thing on the surface set at the reading size. The model's output is an
            argument a reader is meant to weigh and disagree with, and it says so by being
            the longest measure and the largest body text here.

            `wrap-anywhere` because the model writes about code: a 34-character qualified
            name inside a paragraph is wider than a 320px phone.

            And `Prose`, for the same reason: a model writing about code quotes an identifier
            in backticks, and about one reasoning string in eight arrives with a span in it.
            Rendered as raw text those delimiters were on screen, at the one size on this
            surface a reader is asked to read rather than scan. `Prose` returns nodes rather
            than a block, so every measurement above still belongs to this paragraph. */}
        <p className="mt-2.5 max-w-[46ch] whitespace-pre-line text-[16px] leading-[1.65] text-ink wrap-anywhere">
          <Prose>{finding.reasoning}</Prose>
        </p>
        <Footnote>
          {descriptor.description} Judged against case revision {review.case.revision} and{" "}
          {plural(review.case.answers.length, "answer")}.
        </Footnote>

        {/* What the judgement is waiting on and what it suggests: two short blocks that
            never both fill a row, so they share one wherever there is room for two — and
            only then. The split used to be unconditional, so a finding with a hinge and no
            recommendation confined the one thing standing between the reader and six settled
            candidates to 47% of the row and ran 490px of empty panel down the right of it.
            The finding is allowed to change width halfway down; it is not allowed to change
            width for a block that is not there. */}
        {finding.hinge || finding.recommended_response ? (
          <div
            className={cn(
              "mt-4 grid gap-4",
              finding.hinge && finding.recommended_response && "lg:grid-cols-2",
            )}
          >
            {finding.hinge ? (
              <div className="min-w-0">
                <BlockLabel>Hinges on</BlockLabel>
                {/* One of the pair is in a box and the other is not, which is a difference a
                    reader sees at a glance. They used to be two boxes drawn from two `Notice`
                    tones — `#fafafa` against `#ebebeb` on a white row, with both call sites
                    then overriding the text to full ink and cancelling the only other thing
                    the tones carried. Fifteen values of grey and a border alpha is not enough
                    to tell *the reason this finding is held* from *a suggestion the product
                    explicitly disclaims*, which sit side by side in the same grid. So the
                    hinge keeps the box, and the recommendation is prose under its label. */}
                <Notice tone="working" className="mt-1.5">
                  <p id={hingeId} className="text-[14px] leading-relaxed text-ink wrap-anywhere">
                    <Prose>{finding.hinge}</Prose>
                  </p>
                  {waitingOn && onAnswer ? (
                    /* The one action that unblocks every candidate in a waiting review, so it
                       is the primary and not a ghost at the weight of "Judgement context" nine
                       hundred pixels below. Unlike Accept / Park / Waive, which are peers by
                       design, there is no competing choice here.

                       No `aria-label`. It named the button "Answer the open question: …" with
                       the whole question folded in, so the visible words were not in the
                       accessible name — nothing to say for anyone driving the page by voice,
                       and a paragraph where a name should be for anyone listening. The
                       question is what `aria-describedby` is for, and it is already on screen
                       directly above.

                       The arrow is drawn. It was `&rarr;`, which is the forbidden glyph
                       written as an entity: the guard scans source for the character and an
                       entity contains none, while the browser renders U+2192 out of whatever
                       the operating system has, since neither Onest nor Plex Mono ships it. */
                    <Button
                      variant="primary"
                      size="md"
                      className="mt-2.5 min-h-11"
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
              <div className="min-w-0">
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
        ) : null}
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
              MEASURED label, where a ghost button with no border read as a second heading. */}
          {onOpenContext ? (
            <Button variant="secondary" size="sm" className="mt-3.5" onClick={onOpenContext}>
              Judgement context
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
