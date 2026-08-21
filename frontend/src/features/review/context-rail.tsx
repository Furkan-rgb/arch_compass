import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, type Finding, type Review } from "../../api";
import { cn } from "../../lib/cn";
import { absoluteTime, humanise, shortId, splitQualified } from "../../lib/format";
import { Tag } from "../../ui/badge";
import { Button } from "../../ui/button";
import { Input } from "../../ui/field";
import { ChevronDown } from "../../ui/icons";
import { MetaList, MetaRow, Mono } from "../../ui/meta";
import { Label } from "../../ui/panel";
import { Tabs, TabPanel } from "../../ui/tabs";
import { EmptyState, ErrorNotice, Spinner } from "../../ui/states";

/**
 * Why ArchCompass reached the conclusion beside it.
 *
 * Four answers, in the order a sceptical reader asks for them: the human context the
 * judgement was made against, the policies retrieval put in front of the model, the
 * structure around the code it judged, and the machinery that produced all three.
 *
 * Structure and Provenance used to be surfaces of their own across the top of the review,
 * where they competed with the queue and answered nobody's question in particular. They
 * belong here because here they are scoped to the candidate a reader is deciding — which
 * is the only scope at which either of them helps decide anything.
 *
 * No heading of its own: the drawer that holds this already carries the title, and the two
 * printed it twice.
 */
export function ContextRail({
  review,
  finding,
  className,
}: {
  review: Review;
  finding: Finding | null;
  className?: string;
}) {
  const [tab, setTab] = useState("case");
  const provenance = finding
    ? review.retrieval_manifest.find((item) => item.candidate_id === finding.candidate.id)
    : undefined;

  return (
    <div className={cn("flex min-h-0 flex-col", className)}>
      <div className="border-b border-rule px-3 pt-2.5">
        <p className="mb-2 text-xs text-ink-3">
          {finding
            ? `For ${finding.candidate.participants[0]?.qualified_name ?? "the selected candidate"}`
            : "For this review"}
        </p>
        <Tabs
          label="Judgement context"
          active={tab}
          onChange={setTab}
          items={[
            { id: "case", label: "Case" },
            { id: "policies", label: "Policies", count: finding?.policies.length },
            { id: "structure", label: "Structure" },
            { id: "provenance", label: "Provenance" },
          ]}
        />
      </div>

      <div className="scrollbar-slim min-h-0 flex-1 overflow-y-auto px-3 py-3">
        <TabPanel id="case" active={tab}>
          <CaseContext review={review} finding={finding} />
        </TabPanel>

        <TabPanel id="policies" active={tab}>
          {!finding ? (
            <EmptyState title="Select a candidate" className="border-0 bg-transparent py-8">
              Retrieved policies are shown per candidate.
            </EmptyState>
          ) : !finding.policies.length ? (
            <EmptyState title="No policy bearing" className="border-0 bg-transparent py-8">
              Retrieval returned no policy that bears on this candidate.
            </EmptyState>
          ) : (
            <>
              <ul className="grid gap-2">
                {finding.policies.map((bearing) => (
                  <li
                    key={bearing.policy_id}
                    className="rounded-md border border-rule bg-surface-2 p-3"
                  >
                    <div className="text-sm font-semibold leading-5 text-ink">
                      {bearing.policy_title}
                    </div>
                    <Mono className="mt-1 block text-[11px] text-ink-3">{bearing.policy_id}</Mono>
                    <p className="mt-1.5 text-xs leading-5 text-ink-2">{bearing.reasoning}</p>
                  </li>
                ))}
              </ul>
              {/* Retrieved against bore-on: the count the status ribbon used to print at
                  review scale, said where it can be compared with what it counts. */}
              {provenance ? (
                <p className="mt-2.5 font-mono text-[10.5px] leading-relaxed text-ink-3">
                  {provenance.selected_policy_ids.length} policies retrieved for this candidate;{" "}
                  {finding.policies.length} bore on the judgement.
                </p>
              ) : null}
            </>
          )}
        </TabPanel>

        <TabPanel id="structure" active={tab}>
          <StructureContext
            key={finding?.candidate.id ?? "review"}
            review={review}
            finding={finding}
          />
        </TabPanel>

        <TabPanel id="provenance" active={tab}>
          {finding ? (
            <MetaList>
              <MetaRow label="Judge">
                <Mono>{finding.model_identity}</Mono>
              </MetaRow>
              <MetaRow label="Prompt">
                <Mono>{finding.prompt_identity}</Mono>
              </MetaRow>
              {provenance ? (
                <>
                  <MetaRow label="Retriever">
                    <Mono>
                      {provenance.retriever} · v{provenance.version}
                    </Mono>
                  </MetaRow>
                  <MetaRow label="Embedding">
                    <Mono>{provenance.model_identity || "non-embedding strategy"}</Mono>
                  </MetaRow>
                  <MetaRow label="Corpus">
                    <Mono className="break-all">{provenance.corpus_fingerprint}</Mono>
                  </MetaRow>
                  {provenance.query_fingerprint ? (
                    <MetaRow label="Query">
                      <Mono className="break-all">{provenance.query_fingerprint}</Mono>
                    </MetaRow>
                  ) : null}
                  <MetaRow label="Selected">
                    <span className="flex flex-wrap gap-1">
                      {provenance.selected_policy_ids.length ? (
                        provenance.selected_policy_ids.map((id) => (
                          <Tag key={id}>
                            <Mono className="text-[11px]">{id}</Mono>
                          </Tag>
                        ))
                      ) : (
                        <span className="text-ink-3">None</span>
                      )}
                    </span>
                  </MetaRow>
                  {Object.entries(provenance.metadata).map(([key, value]) => (
                    <MetaRow key={key} label={humanise(key)}>
                      <Mono className="break-all">{value}</Mono>
                    </MetaRow>
                  ))}
                </>
              ) : (
                <MetaRow label="Retrieval">
                  <span className="text-ink-3">Nothing was retrieved for this candidate.</span>
                </MetaRow>
              )}
              <MetaRow label="Atlas">
                <span>
                  {review.atlas.node_count.toLocaleString()} nodes ·{" "}
                  {review.atlas.edge_count.toLocaleString()} edges
                </span>
              </MetaRow>
              <MetaRow label="Parser">
                <Mono>
                  {Object.entries(review.atlas.parser_configuration)
                    .map(([key, value]) => `${key}=${value}`)
                    .join(" ") || "—"}
                </Mono>
              </MetaRow>
            </MetaList>
          ) : (
            <ReviewProvenance review={review} />
          )}
        </TabPanel>
      </div>
    </div>
  );
}

/**
 * The audit view: every candidate's retrieval at once.
 *
 * This was a surface of its own, sitting beside the queue as though a reviewer working
 * down a list might switch to reading a table of corpus fingerprints. It is an audit, and
 * an audit belongs behind the thing being audited — reachable in one action, from the same
 * drawer that answers the same question about one candidate.
 */
function ReviewProvenance({ review }: { review: Review }) {
  if (!review.retrieval_manifest.length) {
    return (
      <EmptyState title="No retrieval recorded" className="border-0 bg-transparent py-8">
        This review judged no candidate, so no policy retrieval was performed.
      </EmptyState>
    );
  }
  return (
    <div className="grid gap-2">
      <p className="text-xs leading-5 text-ink-3">
        Every candidate in this review, and what retrieval put in front of the model for it.
      </p>
      {review.retrieval_manifest.map((item) => {
        const finding = review.findings.find((entry) => entry.candidate.id === item.candidate_id);
        const identity =
          finding?.candidate.participants[0]?.qualified_name ?? shortId(item.candidate_id, 16);
        return (
          <div
            key={item.candidate_id}
            className="rounded-md border border-rule bg-surface-2 px-3 py-2.5"
          >
            <Mono className="block break-all text-[12px] text-ink">{identity}</Mono>
            <MetaList className="mt-1.5">
              <MetaRow label="Retriever">
                <Mono>
                  {item.retriever} · v{item.version}
                </Mono>
              </MetaRow>
              <MetaRow label="Embedding">
                <Mono>{item.model_identity || "non-embedding strategy"}</Mono>
              </MetaRow>
              <MetaRow label="Corpus">
                <Mono className="break-all">{item.corpus_fingerprint}</Mono>
              </MetaRow>
              {item.query_fingerprint ? (
                <MetaRow label="Query">
                  <Mono className="break-all">{item.query_fingerprint}</Mono>
                </MetaRow>
              ) : null}
              <MetaRow label="Selected">
                <span className="flex flex-wrap gap-1">
                  {item.selected_policy_ids.length ? (
                    item.selected_policy_ids.map((id) => (
                      <Tag key={id}>
                        <Mono className="text-[11px]">{id}</Mono>
                      </Tag>
                    ))
                  ) : (
                    <span className="text-ink-3">None</span>
                  )}
                </span>
              </MetaRow>
              {Object.entries(item.metadata).map(([key, value]) => (
                <MetaRow key={key} label={humanise(key)}>
                  <Mono>{value}</Mono>
                </MetaRow>
              ))}
            </MetaList>
          </div>
        );
      })}
    </div>
  );
}

/**
 * What else touches the code this candidate is about.
 *
 * The atlas used to be a surface: a search box over the whole repository, seeded from the
 * review's first five participant names and then entirely the reader's. It answered "what
 * is in this codebase", which is a real question and not one the review page is for.
 *
 * Seeded from *this candidate* instead, it answers the question a reviewer actually has
 * while judging a coupling finding — what else is in the neighbourhood — and the box is
 * still there for when the seed is not what they meant. Repository-wide exploration lives
 * on the repositories page, which is the page for a repository.
 *
 * One term, not five. The atlas ANDs its terms: every one has to appear in the same node's
 * name or path. Seeding it with a list of participants therefore asked for a single node
 * called both `ports.Clock` and `adapters.SystemClock`, which is why the surface this
 * replaces returned nothing almost every time it was opened. The leaf of the first
 * participant is the term that finds the abstraction *and* what implements it.
 */
function StructureContext({ review, finding }: { review: Review; finding: Finding | null }) {
  const root = review.repository.path;
  const primary = finding?.candidate.participants[0]?.qualified_name ?? "";
  const seeds = primary ? [splitQualified(primary).leaf] : [];
  const [query, setQuery] = useState(seeds.join(" "));
  const explore = useMutation({ mutationFn: (terms: string[]) => api.searchAtlas(root, terms) });

  const { mutate } = explore;
  useEffect(() => {
    if (seeds.length) mutate(seeds.slice(0, 10));
    // Seeded once from this candidate; every search after that is the reader's.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [root, mutate]);

  function search() {
    const terms = query
      .split(/\s+/)
      .map((item) => item.trim())
      .filter(Boolean)
      .slice(0, 10);
    if (terms.length) mutate(terms);
  }

  return (
    <div className="grid gap-3">
      <div className="flex gap-2">
        <Input
          aria-label="Search the repository structure"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") search();
          }}
          className="min-w-0 flex-1"
          placeholder="module, class, function"
        />
        <Button size="sm" onClick={search} disabled={!query.trim() || explore.isPending}>
          Search
        </Button>
      </div>

      {explore.error ? <ErrorNotice error={explore.error} /> : null}

      {explore.isPending ? (
        <div className="flex items-center gap-2 text-sm text-ink-3">
          <Spinner /> Reading the atlas…
        </div>
      ) : !explore.data ? (
        <EmptyState title="Nothing searched yet" className="border-0 bg-transparent py-8">
          Search for a module, class or function to see where it sits in the structure.
        </EmptyState>
      ) : !explore.data.node_summaries?.length ? (
        <EmptyState title="No node matches all of that" className="border-0 bg-transparent py-8">
          Every term has to appear in the same node&rsquo;s name or path. Try one of them on its
          own.
        </EmptyState>
      ) : (
        <>
          <p className="font-mono text-[10.5px] text-ink-3">
            {explore.data.node_summaries?.length ?? 0} matched ·{" "}
            {explore.data.relationships?.length ?? 0} relations ·{" "}
            {explore.data.signals?.length ?? 0} signals
          </p>
          <ul className="grid gap-1.5">
            {explore.data.node_summaries?.map((node) => (
              <li
                key={node.node_id}
                className="rounded-md border border-rule bg-surface-2 px-2.5 py-2"
              >
                <Mono className="block break-all text-[12px] text-ink">{node.qualified_name}</Mono>
                <div className="mt-1 flex items-center justify-between gap-2">
                  <Tag>{humanise(node.node_type)}</Tag>
                  <span className="truncate font-mono text-[10.5px] text-ink-3">{node.path}</span>
                </div>
              </li>
            ))}
          </ul>
          {explore.data.signals?.length ? (
            <div className="border-t border-rule pt-2.5">
              <Label>Architectural signals</Label>
              <ul className="mt-1.5 grid gap-1.5">
                {explore.data.signals.slice(0, 12).map((signal, index) => (
                  <li
                    key={`${signal.code}-${index}`}
                    className="rounded-md border border-rule bg-surface-2 px-2.5 py-2 text-xs leading-5 text-ink-2"
                  >
                    <Mono className="mr-2 text-[11px] text-ink-3">{signal.code}</Mono>
                    {signal.message}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

/**
 * The answers this candidate was judged against, and the rest of the case beneath them.
 *
 * Every question records the candidates it was asked about — the model returns a position
 * in the findings list and the application resolves it to a real id — so `candidate_ids`
 * is an application-owned fact, not a model's guess, and this is what it is for.
 *
 * The other answers stay on the page rather than being filtered away, folded shut. The tab
 * is called Judgement context and it has to be true: the judge is shown the whole case, so
 * a rail that hid two thirds of it would be describing a prompt that was never sent. What a
 * reader actually needed was not a smaller case but an order — this candidate's answers
 * first, and the rest where they can still be reached.
 */
function CaseContext({ review, finding }: { review: Review; finding: Finding | null }) {
  const { case: architectureCase } = review;
  const bearing = finding
    ? architectureCase.answers.filter((answer) =>
        answer.question.candidate_ids.includes(finding.candidate.id),
      )
    : architectureCase.answers;
  const rest = finding
    ? architectureCase.answers.filter((answer) => !bearing.includes(answer))
    : [];

  return (
    <div className="grid gap-3">
      {/* One block, because there is one channel. The case used to show Constraints,
          Decisions and Clarification answers as three peers, two of which were always
          empty — nothing in the product could write them, so the drawer's honest report on
          most reviews was "None recorded" twice above the only list that ever filled. */}
      <div>
        <Label>
          {finding ? "Answered about this candidate" : "Answered"} · {bearing.length}
        </Label>
        {bearing.length ? (
          <ul className="mt-1.5 grid gap-1.5">
            {bearing.map((answer) => (
              <AnswerCard key={answer.question.id} answer={answer} />
            ))}
          </ul>
        ) : (
          <p className="mt-1.5 text-xs text-ink-3">
            {architectureCase.answers.length
              ? "No question was asked about this candidate. It was judged against the rest of the case below."
              : "Nothing has been asked yet. A case fills in when a judgement turns on something the repository cannot settle."}
          </p>
        )}
      </div>

      {rest.length ? (
        <details className="group">
          <summary className="flex min-h-11 list-none items-center gap-2 rounded-md px-1 py-2 text-[10px] font-bold uppercase tracking-[0.14em] text-ink-3 transition hover:bg-surface-2 focus-visible:-outline-offset-2">
            <span className="min-w-0 flex-1 text-left">
              Asked about other candidates · {rest.length}
            </span>
            <ChevronDown className="size-4 shrink-0 transition group-open:rotate-180" />
          </summary>
          <ul className="mt-1.5 grid gap-1.5">
            {rest.map((answer) => (
              <AnswerCard key={answer.question.id} answer={answer} />
            ))}
          </ul>
        </details>
      ) : null}

      <MetaList className="mt-1 border-t border-rule pt-1">
        <MetaRow label="Revision">{architectureCase.revision}</MetaRow>
        <MetaRow label="Updated">{absoluteTime(architectureCase.updated_at)}</MetaRow>
        <MetaRow label="Case">
          <Mono className="break-all">{architectureCase.id}</Mono>
        </MetaRow>
      </MetaList>
    </div>
  );
}

function AnswerCard({ answer }: { answer: Review["case"]["answers"][number] }) {
  return (
    <li className="rounded-md border border-rule bg-surface-2 px-2.5 py-2">
      <div className="text-xs font-semibold leading-5 text-ink">{answer.question.text}</div>
      <div className="mt-1 text-xs leading-5 text-ink-2">
        {answer.status === "skipped" ? (
          <span className="text-ink-3">Explicitly skipped</span>
        ) : (
          answer.value
        )}
      </div>
      <div className="mt-1 text-[11px] text-ink-3">
        {answer.actor} · {absoluteTime(answer.answered_at)}
      </div>
    </li>
  );
}
