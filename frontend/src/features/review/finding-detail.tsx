import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import type { Finding, RetrievalProvenance, Review } from "../../api";
import { cn } from "../../lib/cn";
import { humanise, plural, shortId, verdictOf } from "../../lib/format";
import { InvestigationTranscript, investigationSummary } from "./investigation";
import { Tag } from "../../ui/badge";
import { Button, CopyButton } from "../../ui/button";
import { EvidenceBlock } from "../../ui/code";
import { ChevronDown } from "../../ui/icons";
import { MetaList, MetaRow, Mono, PathRef } from "../../ui/meta";
import { Label } from "../../ui/panel";
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

/** A fact that supports the block above it, said in one line. */
function Footnote({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn("mt-3 max-w-[62ch] text-[12px] leading-5 text-ink-3", className)}>{children}</p>;
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
 */
export function PolicyRef({ id, className }: { id: string; className?: string }) {
  return (
    <Link
      to={`/policies?open=${encodeURIComponent(id)}`}
      title={`Read the policy ${id}`}
      className={cn(
        "font-mono text-[11px] text-mark underline decoration-rule-strong underline-offset-2 transition hover:decoration-current [overflow-wrap:anywhere]",
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
 */
function Attribution({ voice, by, className }: { voice: string; by?: ReactNode; className?: string }) {
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
  children,
}: {
  label: string;
  summary: ReactNode;
  children: ReactNode;
}) {
  return (
    <details className="group border-t border-rule">
      <summary className="flex min-h-11 list-none items-start gap-3 px-4 py-3 transition hover:bg-surface-2 focus-visible:-outline-offset-2 sm:px-6">
        <Label className="shrink-0 leading-5 text-ink">{label}</Label>
        <span className="min-w-0 flex-1 font-mono text-[11px] leading-5 text-ink-3 [overflow-wrap:anywhere]">
          {summary}
        </span>
        <ChevronDown className="mt-0.5 size-4 shrink-0 text-ink-3 transition group-open:rotate-180" />
      </summary>
      <div className="border-t border-rule bg-surface-2 px-4 py-4 sm:px-6">{children}</div>
    </details>
  );
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
 * important each part is. The model's argument is two or three sentences and caps at `62ch`,
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
  const waitingOn =
    review.status === "awaiting_answers"
      ? review.questions.find((question) => question.candidate_ids.includes(finding.candidate.id))
      : undefined;

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
              name inside a paragraph is wider than a 320px phone. */}
          <p className="mt-2.5 max-w-[62ch] whitespace-pre-line text-[16px] leading-[1.65] text-ink wrap-anywhere">
            {finding.reasoning}
          </p>
          <Footnote>
            {descriptor.description} Judged against case revision {review.case.revision} and{" "}
            {plural(review.case.answers.length, "answer")}.
          </Footnote>

        {/* What the judgement is waiting on and what it suggests: two short blocks that
            never both fill a row, so they share one wherever there is room for two. */}
        {finding.hinge || finding.recommended_response ? (
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            {finding.hinge ? (
              <div className="min-w-0">
                <BlockLabel>Hinges on</BlockLabel>
                <Notice tone="working" className="mt-1.5">
                  <p className="text-[14px] leading-relaxed text-ink wrap-anywhere">
                    {finding.hinge}
                  </p>
                  {waitingOn && onAnswer ? (
                    <Button
                      variant="secondary"
                      size="md"
                      className="mt-2.5 min-h-11"
                      aria-label={`Answer the open question: ${waitingOn.text}`}
                      onClick={onAnswer}
                    >
                      Answer it &rarr;
                    </Button>
                  ) : null}
                </Notice>
                <Footnote>
                  {waitingOn
                    ? "Answering completes this review's case revision and re-judges what it touches."
                    : "No open question covers this. The round was concluded with the uncertainty preserved."}{" "}
                  {plural(answered.length, "answer")} recorded so far.
                </Footnote>
              </div>
            ) : null}

            {finding.recommended_response ? (
              <div className="min-w-0">
                <BlockLabel>Recommended response</BlockLabel>
                <Notice className="mt-1.5">
                  <p className="text-[14px] leading-relaxed text-ink wrap-anywhere">
                    {finding.recommended_response}
                  </p>
                </Notice>
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
          // A candidate with no excerpts has nothing to sit beside, and a 22rem column with
          // an empty half of the screen next to it reads as a layout that failed.
          finding.evidence.length > 0 && "lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]",
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
                <span className="font-mono font-medium normal-case tracking-normal">
                  {" · "}
                  {finding.candidate.participants.length}
                </span>
              </BlockLabel>
              {/* A name on its own line and what it does under it, rather than a chip with
                  the role stapled inside. `role` is only sometimes a word — the deterministic
                  detector writes "the only implementation of it in this repository", and a
                  sentence sharing a chip with an identifier squeezed the identifier to about
                  thirty pixels and broke it one character to a line. */}
              <ul aria-label="Involved code" className="mt-1.5 grid gap-1.5">
                {finding.candidate.participants.map((participant) => (
                  <li
                    key={`${participant.qualified_name}-${participant.role}`}
                    className="flex max-w-full items-start gap-1"
                  >
                    <Tag className="min-w-0 flex-col items-start gap-0.5 px-2.5 py-1.5">
                      <Mono className="text-[11px] text-ink wrap-anywhere">
                        {participant.qualified_name}
                      </Mono>
                      <span className="text-[11px] leading-4 text-ink-3">
                        {humanise(participant.role)}
                      </span>
                    </Tag>
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
            <dl className="mt-3.5 border-t border-rule">
              {measurements.map((item) => (
                <div key={item.name} className="border-b border-rule py-2">
                  <div className="flex items-baseline justify-between gap-3">
                    <dt className="min-w-0 text-[12px] font-semibold text-ink-2 [overflow-wrap:anywhere]">
                      {measurementLabel(item.name)}
                      {item.nature === "structural_proxy" ? (
                        <span className="font-normal text-ink-3"> · a proxy, not a count</span>
                      ) : null}
                    </dt>
                    <dd className="shrink-0 font-mono text-[16px] font-medium tabular-nums text-ink">
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

          <div className="mt-3.5">
            <BlockLabel>How it was detected</BlockLabel>
            {/* `wrap-anywhere`: a detection rationale regularly ends in a 64-character
                participant fingerprint, which is one token to the line breaker. */}
            <p className="mt-1 text-[12.5px] leading-6 text-ink-2 wrap-anywhere">
              {finding.candidate.detection_rationale}
            </p>
            {finding.candidate.limitations ? (
              <Footnote className="mt-2">{finding.candidate.limitations}</Footnote>
            ) : null}
          </div>

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
            {/* The location was set in the mark with an underline under it and did nothing at
                all when pressed — the one decoration this system reserves for "this goes to
                the source", promising a destination it did not have. `PathRef` is that
                promise kept: it copies `path:line`, and opens the file where somebody has
                said which editor they use. */}
            <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
              <BlockLabel>Evidence</BlockLabel>
              {firstLocation ? (
                <PathRef
                  path={firstLocation.path}
                  line={firstLocation.start_line}
                  endLine={firstLocation.end_line}
                />
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
      </div>

      {/* ── The audit, folded away, each with a closed state that says what is inside ── */}
      <Disclosure label="Policies" summary={policiesSummary(finding, retrieval)}>
        {finding.policies.length ? (
          <ul className="grid max-w-[62ch] gap-2">
            {finding.policies.map((bearing) => (
              <li key={bearing.policy_id} className="rounded-md border border-rule bg-surface px-3.5 py-3">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                  <span className="text-[13px] font-semibold text-ink">{bearing.policy_title}</span>
                  <PolicyRef id={bearing.policy_id} className="text-[10.5px]" />
                </div>
                <p className="mt-1.5 text-[14px] leading-relaxed text-ink-2 wrap-anywhere">
                  {bearing.reasoning}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="max-w-[62ch] text-[13px] leading-6 text-ink-2">
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

      <Disclosure
        label="Provenance"
        summary={
          retrieval
            ? `Prompt ${finding.prompt_identity} · corpus ${shortId(retrieval.corpus_fingerprint, 12)}`
            : `Prompt ${finding.prompt_identity} · no retrieval recorded for this candidate`
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
