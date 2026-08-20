import type { ReactNode } from "react";

import type { Finding, RetrievalProvenance, Review } from "../../api";
import { humanise, plural, shortId, verdictOf } from "../../lib/format";
import { Badge, Tag, VerdictBadge } from "../../ui/badge";
import { Button } from "../../ui/button";
import { EvidenceBlock } from "../../ui/code";
import { ChevronDown } from "../../ui/icons";
import { MetaList, MetaRow, Mono, PathRef } from "../../ui/meta";
import { Notice } from "../../ui/states";
import { deltaStateOf } from "./attention-queue";
import { DecisionBar } from "./decision-bar";

/**
 * What a verdict means for the person reading it, in the words a person would use.
 *
 * `lib/format` carries the label, the glyph and the tone; what it does not carry is the
 * sentence somebody needs on first contact. "Held" is a word this product invented, and a
 * pill that says it and nothing else is a term of art sitting where the answer should be.
 */
const VERDICT_MEANS: Record<string, string> = {
  material: "something to act on",
  held: "waiting on a person",
  cleared: "assessed and settled",
};

/**
 * Where this candidate stands against the last review, said once and unambiguously.
 *
 * `humanise(delta)` produced "New", on a page that also carries the queue's "Moved since
 * review 1" and a review that is itself new. Two meanings of "new" on one screen is one too
 * many, so this states which kind of new it is.
 */
const DELTA_LABELS: Record<string, string> = {
  new: "New this review",
  changed: "Changed since the last review",
  unchanged: "Carried forward unchanged",
};

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
 * would say "nothing came back" about a corpus that was never there. The charter asks for
 * uncertainty to be stated rather than smoothed; these are two different facts.
 */
const EMPTY_CORPUS = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";

/** `1 implementation`, `0 references` — a unit is written plural, so one of it is not. */
function counted(value: number, word: string): string {
  const singular = word.endsWith("s") ? word.slice(0, -1) : word;
  return `${value} ${value === 1 ? singular : word}`;
}

/**
 * What produced the policies this judgement weighed, in the shortest honest form.
 *
 * `finding.retrieval_identity` is a sha256 over everything the retrieval did. That is the
 * right thing to record and the wrong thing to print on an attribution line: 64 hex
 * characters is three lines of a phone spent on a value nobody reads by eye. The retriever
 * and its version is what a reader recognises, and the hash keeps its row in `Provenance`.
 */
function retrievalLabel(finding: Finding, retrieval?: RetrievalProvenance): string {
  if (retrieval) return `${retrieval.retriever}/${retrieval.version}`;
  return finding.retrieval_identity ? shortId(finding.retrieval_identity, 12) : "no retrieval";
}

/** `ports.py:14-17`, or `ports.py:14` when the span is one line. */
function locationLabel(location: { path: string; start_line: number; end_line: number }): string {
  const span =
    location.end_line && location.end_line !== location.start_line
      ? `${location.start_line}-${location.end_line}`
      : `${location.start_line}`;
  return `${location.path}:${span}`;
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
 * Sans rather than mono: this is a caveat written for a person, and mono now means the
 * string was produced by the machine. It was set in mono when the register was carried by
 * three typefaces; there is one family now, and size is what demotes it.
 */
function Footnote({ children }: { children: ReactNode }) {
  return <p className="mt-3 max-w-[62ch] text-[12px] leading-5 text-ink-3">{children}</p>;
}

/** A small uppercase label above a block. Ten pixels, and it never says a sentence. */
function BlockLabel({ children }: { children: ReactNode }) {
  return (
    <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-ink-3 [overflow-wrap:anywhere]">
      {children}
    </div>
  );
}

/**
 * A section folded away, with a closed state that says what is inside it.
 *
 * `<details>` and `<summary>` rather than a button and a piece of state, so the disclosure
 * role, the keyboard path, the browser's own find-in-page and the expanded state announced
 * to a screen reader are all free and correct. Nothing sets `aria-expanded` here on purpose:
 * React does not see the open/closed toggle, so a hand-written one would go stale the first
 * time somebody clicked it.
 *
 * The summary is the part that overflows. It holds counts, a repository-relative path and
 * sometimes a content hash, and on a 390px phone a mono `sha256` is several times the width
 * of the row. So the label and the chevron are the only things allowed their own width, the
 * line between them may be narrower than its content, and it breaks at any character rather
 * than making the panel — and then the page — that wide.
 */
function Disclosure({
  label,
  summary,
  children,
}: {
  label: string;
  summary: ReactNode;
  children: ReactNode;
}) {
  return (
    <details className="group border-t border-rule">
      {/* `list-none` for the marker, and `styles.css` already hides WebKit's older one. The
          focus ring is pulled inside its own edge, because the article is `overflow-hidden`
          and an outline offset outwards on a full-bleed row is clipped by the panel. */}
      <summary className="flex min-h-11 list-none items-start gap-3 px-4 py-3 transition hover:bg-surface-2 focus-visible:-outline-offset-2 sm:px-5">
        <span className="shrink-0 text-[10px] font-bold uppercase leading-5 tracking-[0.12em] text-ink">
          {label}
        </span>
        <span className="min-w-0 flex-1 font-mono text-[11px] leading-5 text-ink-3 [overflow-wrap:anywhere]">
          {summary}
        </span>
        <ChevronDown className="mt-0.5 size-4 shrink-0 text-ink-3 transition group-open:rotate-180" />
      </summary>
      <div className="border-t border-rule bg-surface-2 px-4 py-4 sm:px-5">{children}</div>
    </details>
  );
}

/**
 * One architecture assessment, in the order it is used rather than the order it was made.
 *
 * The order used to be the order the three jobs happen in — measured, judged, decided — which
 * is the right order to *produce* a finding and the wrong one to read thirty of. A reviewer
 * arrives with one question, "what is the call", then one more, "do I believe it", then acts.
 * So the verdict is the first thing on the page, the model's sentence is the second, the one
 * thing blocking it is the third, and everything the machine counted is folded away behind a
 * closed state that says enough that opening it is a choice rather than a gamble.
 *
 * Nothing here is tinted except the verdict pill. `held` was doing two jobs — a verdict the
 * model reached, and the state the page is in while you are blocked — and the second one had
 * painted itself across the hinge, the answer control and the decision bar. The blocked state
 * is structural now: a distinct surface, a rule, and one place to act.
 */
export function FindingDetail({
  review,
  finding,
  next,
  onNext,
  onAnswer,
  onOpenContext,
}: {
  review: Review;
  finding: Finding;
  /** The next candidate still wanting a person, so the control can name where it goes. */
  next?: Finding | null;
  onNext?: () => void;
  onAnswer?: () => void;
  onOpenContext?: () => void;
}) {
  const descriptor = verdictOf(finding.verdict);
  const means = VERDICT_MEANS[finding.verdict] ?? descriptor.description;
  const delta = deltaStateOf(review, finding.candidate.id);
  const measurements = finding.candidate.measurements;
  const retrieval = review.retrieval_manifest.find(
    (entry) => entry.candidate_id === finding.candidate.id,
  );
  const answered = review.case.answers.filter((answer) => answer.status === "answered");
  const identity = finding.candidate.participants[0]?.qualified_name;
  const firstLocation = finding.evidence.find((item) => item.location)?.location;
  // A held verdict says it is waiting on a person. Which person, and on what — the open
  // question that would settle it, if the round is still open.
  const waitingOn =
    review.status === "awaiting_answers"
      ? review.questions.find((question) =>
          question.candidate_ids.includes(finding.candidate.id),
        )
      : undefined;

  // Built here rather than in the summary, because the closed line is the section: every
  // count the open state shows, whether any of them is a proxy rather than a count, and
  // where the first excerpt was quoted from.
  const measured = [
    ...measurements.map(
      (item) =>
        `${counted(item.value, item.unit || measurementLabel(item.name))}${
          item.nature === "structural_proxy" ? " (proxy)" : ""
        }`,
    ),
    ...(finding.evidence.length ? [counted(finding.evidence.length, "excerpts")] : []),
  ];

  return (
    <article
      aria-labelledby={`finding-${finding.candidate.id}`}
      className="animate-fade overflow-hidden rounded-lg border border-rule bg-surface"
    >
      {/* ── The call ──────────────────────────────────────────────────────────────── */}
      <header className="px-4 pb-5 pt-4 sm:px-5 sm:pt-5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          {/* The one tinted thing in this file. Glyph, then word, then hue — the charter's
              order, and the reason the hue may be the only one on the page. */}
          <VerdictBadge verdict={finding.verdict} className="px-3 py-1.5 text-[12px]" />
          <span className="text-[13px] text-ink-2">{means}</span>
          {onOpenContext ? (
            <Button variant="ghost" size="sm" className="sm:ml-auto" onClick={onOpenContext}>
              Judgement context
            </Button>
          ) : null}
        </div>

        {/* The identifier leads, because that is what is being looked for. The sentence
            keeps its place underneath, because that is what explains. */}
        <h2
          id={`finding-${finding.candidate.id}`}
          className="mt-3 font-mono text-[17px] font-medium leading-snug tracking-[-0.01em] text-ink [overflow-wrap:anywhere] sm:text-[19px]"
        >
          {identity ?? finding.candidate.summary}
        </h2>
        {identity ? (
          <p className="mt-2 max-w-[58ch] text-[14px] leading-relaxed text-ink-2">
            {finding.candidate.summary}
          </p>
        ) : null}

        {/* The facts shared by everything below, as chips rather than as three labelled
            blocks. `flex-wrap` wraps between chips and has no answer for one chip wider than
            the row — a participant is a qualified name, so that is the normal case on a
            phone — which is why every chip and every item is capped at the row and breaks
            the name instead. */}
        <div className="mt-3.5 flex flex-wrap gap-1.5">
          <Tag className="py-1">{humanise(finding.candidate.pattern)}</Tag>
          {delta ? <Tag className="py-1">{DELTA_LABELS[delta] ?? humanise(delta)}</Tag> : null}
          {finding.reused_from_review_id ? (
            <Tag className="py-1">
              Reused from{" "}
              <Mono className="text-[11px]">{shortId(finding.reused_from_review_id, 8)}</Mono>
            </Tag>
          ) : null}
        </div>
        <ul aria-label="Involved code" className="mt-1.5 flex flex-wrap gap-1.5">
          {finding.candidate.participants.map((participant) => (
            <li key={`${participant.role}-${participant.qualified_name}`} className="max-w-full">
              <Tag className="items-baseline gap-1.5 py-1">
                <Mono className="font-medium text-ink wrap-anywhere">
                  {participant.qualified_name}
                </Mono>
                <span className="text-[11px] text-ink-3">{humanise(participant.role)}</span>
              </Tag>
            </li>
          ))}
        </ul>
      </header>

      {/* ── Judged ────────────────────────────────────────────────────────────────── */}
      <section className="border-t border-rule px-4 py-5 sm:px-5">
        {/* The attribution, not a heading: it says whose sentence the next paragraph is,
            which is the whole of what the gutter used to say and all of it that was load
            bearing. Mono because every part of it after the first word is a machine string. */}
        <p className="font-mono text-[10.5px] leading-5 text-ink-3 [overflow-wrap:anywhere]">
          <span className="font-semibold uppercase tracking-[0.1em] text-ink">Judged</span>
          {" · "}
          {finding.model_identity}
          {" · "}
          {retrievalLabel(finding, retrieval)}
        </p>
        {/* The only thing on the page set at the reading size. The model's output is an
            argument a reader is meant to weigh and disagree with, and it used to say so by
            being the only serif on screen; there is one family now, so the register is the
            size and the attribution line above it.

            `wrap-anywhere` because the model writes about code: "…duplicated definition of
            CATEGORIES in src/audiobook/benchmarking/corpus.py" puts a 34-character token in
            a paragraph, and at 17px that is wider than a 320px phone. The alternative to
            breaking it is clipping it. */}
        <p className="mt-3 max-w-[60ch] whitespace-pre-line text-[17px] leading-[1.68] text-ink wrap-anywhere">
          {finding.reasoning}
        </p>
        <Footnote>
          {descriptor.description} Judged against case revision {review.case.revision} and{" "}
          {plural(review.case.constraints.length, "constraint")}.
        </Footnote>
      </section>

      {/* ── What to do about it ───────────────────────────────────────────────────── */}
      {finding.hinge || finding.recommended_response ? (
        <section className="border-t border-rule px-4 py-5 sm:px-5">
          {finding.hinge ? (
            <div>
              <BlockLabel>Hinges on</BlockLabel>
              {/* No verdict tint. This block was `held` amber, which made one hue mean two
                  things at once — the verdict the model reached, and the fact that the page
                  is blocked. A rule and a recessed surface say "blocked" without spending
                  the colour that says "this is the call". */}
              <Notice tone="working" className="mt-2 max-w-[62ch]">
                <p className="text-[15px] leading-relaxed text-ink wrap-anywhere">
                  {finding.hinge}
                </p>
                {waitingOn && onAnswer ? (
                  // "Waiting on a person" followed by no way to be that person is a dead
                  // end — and this is the only place in the product where that question is
                  // answered, so the affordance is here and nowhere else.
                  <Button
                    variant="secondary"
                    size="md"
                    className="mt-3 min-h-11"
                    aria-label={`Answer the open question: ${waitingOn.text}`}
                    onClick={onAnswer}
                  >
                    Answer it &rarr;
                  </Button>
                ) : null}
              </Notice>
              <Footnote>
                {waitingOn
                  ? "Answering produces the next case revision and re-judges what it touches."
                  : "No open question covers this. The round was concluded with the uncertainty preserved."}{" "}
                {plural(answered.length, "answer")} recorded so far.
              </Footnote>
            </div>
          ) : null}

          {finding.recommended_response ? (
            <div className={finding.hinge ? "mt-5" : undefined}>
              <BlockLabel>Recommended response</BlockLabel>
              <Notice className="mt-2 max-w-[62ch]">
                <p className="text-[15px] leading-relaxed text-ink wrap-anywhere">
                  {finding.recommended_response}
                </p>
              </Notice>
              <Footnote>
                A recommendation, not a change. ArchCompass does not write the fix.
              </Footnote>
            </div>
          ) : null}
        </section>
      ) : null}

      {/* ── Folded away, each with a closed state that says what is inside ────────── */}
      <Disclosure
        label="Measured"
        summary={
          <>
            {measured.length ? `${measured.join(" · ")}${firstLocation ? " · " : ""}` : null}
            {firstLocation ? (
              // A source location navigates, and says so with weight and an underline. It
              // used to say so with `--mark`, which is not a hue any more: a fourth colour
              // beside three verdicts makes a reader work out which of the four carries
              // meaning.
              <span className="font-medium text-mark underline decoration-rule underline-offset-2">
                {locationLabel(firstLocation)}
              </span>
            ) : null}
            {!measured.length && !firstLocation ? "Nothing was counted for this candidate" : null}
          </>
        }
      >
        {measurements.length ? (
          // A hairline grid, not a row of cards. These are readings; a reading that has been
          // put in a box is asking to be looked at twice.
          <div className="grid gap-px overflow-hidden rounded-md border border-rule bg-rule [grid-template-columns:repeat(auto-fit,minmax(13rem,1fr))]">
            {measurements.map((item) => (
              <div key={item.name} className="bg-surface px-3 py-2.5">
                <div className="font-mono text-[15px] font-medium tabular-nums text-ink">
                  {item.value}
                  {item.unit ? <span className="text-ink-3"> {item.unit}</span> : null}
                </div>
                <div className="mt-0.5 text-[11px] font-semibold text-ink-2 [overflow-wrap:anywhere]">
                  {measurementLabel(item.name)}
                  {item.nature === "structural_proxy" ? (
                    <span className="font-normal text-ink-3"> · a proxy, not a count</span>
                  ) : null}
                </div>
                {/* The caveats survive whatever else moves. "A reference is not evidence
                    that the indirection is or is not earning its place" is the difference
                    between a measurement and a claim, and it is the charter's "say where it
                    came from" in the one place a reader can act on it. */}
                {item.definition ? (
                  <p className="mt-1.5 text-[11.5px] leading-snug text-ink-2">{item.definition}</p>
                ) : null}
                {item.limitations ? (
                  <p className="mt-1 text-[11.5px] leading-snug text-ink-3">{item.limitations}</p>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-[13px] leading-6 text-ink-3">
            This pattern is detected structurally and carries no counts.
          </p>
        )}

        {finding.evidence.length ? (
          <div className={measurements.length ? "mt-4" : undefined}>
            <BlockLabel>Pinned evidence · {finding.evidence.length}</BlockLabel>
            <div className="mt-2 grid gap-2">
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
            <Footnote>Quoted from the indexed snapshot, not re-read from disk.</Footnote>
          </div>
        ) : null}

        <div className="mt-4">
          <BlockLabel>How it was detected</BlockLabel>
          <p className="mt-1.5 max-w-[62ch] text-[13px] leading-6 text-ink-2">
            {finding.candidate.detection_rationale}
          </p>
          {finding.candidate.limitations ? (
            <Footnote>{finding.candidate.limitations}</Footnote>
          ) : null}
        </div>
      </Disclosure>

      <Disclosure label="Policies" summary={policiesSummary(finding, retrieval)}>
        {finding.policies.length ? (
          <ul className="grid max-w-[62ch] gap-2">
            {finding.policies.map((bearing) => (
              <li
                key={bearing.policy_id}
                className="rounded-md border border-rule bg-surface px-3.5 py-3"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                  <span className="text-[13px] font-semibold text-ink">{bearing.policy_title}</span>
                  <Mono className="text-[10.5px] text-ink-3 [overflow-wrap:anywhere]">
                    {bearing.policy_id}
                  </Mono>
                </div>
                <p className="mt-1.5 text-[14px] leading-relaxed text-ink-2 wrap-anywhere">
                  {bearing.reasoning}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="max-w-[62ch] text-[13px] leading-6 text-ink-2">
            No policy bore on this judgement. The model was given the case, the measurements
            and the evidence, and reached the verdict without a policy to weigh it against.
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

      <Disclosure
        label="Provenance"
        summary={
          // The two machine facts that appear nowhere else on the page. The model and the
          // retriever are already on the attribution line above, and printing them here
          // again would make the closed state a summary of what the reader just read.
          retrieval
            ? `Prompt ${finding.prompt_identity} · corpus ${shortId(retrieval.corpus_fingerprint, 12)}`
            : `Prompt ${finding.prompt_identity} · no retrieval recorded for this candidate`
        }
      >
        <MetaList>
          <MetaRow label="Candidate">
            <Mono className="[overflow-wrap:anywhere]">{finding.candidate.id}</Mono>
          </MetaRow>
          <MetaRow label="Judge">
            <Mono className="[overflow-wrap:anywhere]">{finding.model_identity}</Mono>
          </MetaRow>
          <MetaRow label="Prompt">
            <Mono className="[overflow-wrap:anywhere]">{finding.prompt_identity}</Mono>
          </MetaRow>
          <MetaRow label="Retrieval">
            <Mono className="[overflow-wrap:anywhere]">{finding.retrieval_identity}</Mono>
          </MetaRow>
          {retrieval ? (
            <MetaRow label="Retriever">
              <Mono className="[overflow-wrap:anywhere]">
                {retrieval.retriever}/{retrieval.version}
              </Mono>
            </MetaRow>
          ) : null}
          {retrieval ? (
            <MetaRow label="Corpus">
              <Mono className="[overflow-wrap:anywhere]">{retrieval.corpus_fingerprint}</Mono>
            </MetaRow>
          ) : null}
          {/* Where the machine names live. `dependants_of_abstraction` is what the detector,
              the report and the domain all call it, and a reader who needs to match a count
              on screen to a key in the record needs to see both. */}
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

      {/* ── Yours ─────────────────────────────────────────────────────────────────── */}
      {/* The decision bar names itself and says who recorded what, so it takes no label of
          its own here — two headings on one control was the gutter printing the attribution
          twice. It is always reachable: nothing above it collapses onto it, and nothing
          below it is a step. */}
      <section className="border-t border-rule px-4 py-5 sm:px-5">
        <DecisionBar review={review} finding={finding} />
      </section>

      {/* Where a reader arrives once they have decided. Named rather than jumped to: being
          moved somewhere else the moment a decision lands is the interface concluding you
          were finished with this one. */}
      {onNext && next ? (
        <button
          type="button"
          onClick={onNext}
          aria-label={`Next needing you: ${
            next.candidate.participants[0]?.qualified_name ?? next.candidate.summary
          }`}
          className="flex min-h-11 w-full items-baseline gap-2.5 border-t border-rule bg-surface-2 px-4 py-3 text-left transition hover:bg-sunken focus-visible:-outline-offset-2 sm:px-5"
        >
          <span className="shrink-0 text-[10px] font-bold uppercase tracking-[0.12em] text-ink-3">
            Next needing you
          </span>
          <span className="min-w-0 flex-1 truncate font-mono text-[12.5px] text-ink">
            {next.candidate.participants[0]?.qualified_name ?? next.candidate.summary}
          </span>
          <span aria-hidden="true" className="shrink-0 text-ink-3">
            &rarr;
          </span>
        </button>
      ) : null}
    </article>
  );
}

/** The compact header shown above the detail on small screens, with a way back. */
export function FindingBackBar({ onBack, finding }: { onBack: () => void; finding: Finding }) {
  return (
    <div className="mb-3 flex items-center gap-2">
      <Button variant="secondary" size="sm" onClick={onBack}>
        ← Queue
      </Button>
      <Badge tone={verdictOf(finding.verdict).tone} glyph={verdictOf(finding.verdict).glyph}>
        {verdictOf(finding.verdict).label}
      </Badge>
    </div>
  );
}
