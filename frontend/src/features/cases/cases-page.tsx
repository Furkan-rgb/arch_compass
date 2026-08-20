import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api, type CaseSummary } from "../../api";
import { cn } from "../../lib/cn";
import { absoluteTime, humanise, relativeTime, repositoryName, shortId } from "../../lib/format";
import { Tag } from "../../ui/badge";
import { Button, ButtonLink } from "../../ui/button";
import { MetaLine, Mono } from "../../ui/meta";
import { PageHeader } from "../../ui/page";
import { Label, Panel, PanelBody, PanelHeader } from "../../ui/panel";
import { EmptyState, ErrorNotice, LoadingPanel, Spinner } from "../../ui/states";
import { Timeline, TimelineItem } from "../../ui/timeline";

/**
 * Cases are the human half of a review: what this architecture is for, what it must live
 * with, what has already been decided, and what a reviewer answered when asked. Each
 * clarification produces a new revision rather than overwriting the last, so the page is
 * built around the sequence rather than around a form.
 */
export function CasesPage() {
  const client = useQueryClient();
  const cases = useQuery({ queryKey: ["cases"], queryFn: api.cases });
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: api.reviews });
  const [selected, setSelected] = useState<string | null>(null);

  const selectedId = selected ?? cases.data?.[0]?.case_id ?? null;
  const history = useQuery({
    queryKey: ["case-history", selectedId],
    queryFn: () => api.caseHistory(selectedId!),
    enabled: Boolean(selectedId),
  });
  const create = useMutation({
    mutationFn: () => api.createCase(),
    onSuccess: async (created) => {
      setSelected(created.case_id);
      await client.invalidateQueries({ queryKey: ["cases"] });
    },
  });

  if (cases.isLoading) return <LoadingPanel label="Loading architecture cases…" rows={4} />;
  if (cases.error) return <ErrorNotice error={cases.error} />;

  const all = cases.data ?? [];
  const repositoryFor = (caseId: string) => {
    const review = (reviews.data ?? []).find((item) => item.case.id === caseId);
    return review ? repositoryName(review.repository.path) : null;
  };
  const related = (reviews.data ?? []).filter((review) => review.case.id === selectedId);
  const latest = history.data?.at(-1) ?? all.find((item) => item.case_id === selectedId);

  return (
    <div>
      <PageHeader
        eyebrow="Human context"
        title="Architecture cases"
        description="A case carries the constraints, decisions and clarification answers a review is judged against. It starts empty and grows by revision as reviews ask for what they need; nothing is overwritten."
        actions={
          <Button disabled={create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? <Spinner /> : "New case"}
          </Button>
        }
      />
      {create.error ? (
        <div className="mb-5">
          <ErrorNotice error={create.error} />
        </div>
      ) : null}

      {!all.length ? (
        <EmptyState
          title="No architecture case yet"
          action={<ButtonLink to="/start">Start a review</ButtonLink>}
        >
          A case is opened automatically when a repository review starts. Opening one here gives
          you an empty case that reviews will fill in.
        </EmptyState>
      ) : (
        <div className="grid items-start gap-4 xl:grid-cols-[minmax(280px,0.75fr)_minmax(0,1.25fr)]">
          <ul className="grid gap-2">
            {all.map((item) => (
              <li key={item.case_id}>
                <CaseCard
                  value={item}
                  selected={selectedId === item.case_id}
                  onSelect={() => setSelected(item.case_id)}
                  reviewedRepository={repositoryFor(item.case_id)}
                />
              </li>
            ))}
          </ul>

          <div className="grid gap-4">
            {latest ? <CaseSnapshot value={latest} /> : null}

            <Panel>
              <PanelHeader
                title="Revision history"
                description="Every clarification answered produces the next revision; earlier ones stay readable."
              />
              <PanelBody>
                {history.isLoading ? (
                  <div className="flex items-center gap-2 text-sm text-ink-3">
                    <Spinner /> Loading revisions…
                  </div>
                ) : history.error ? (
                  <ErrorNotice error={history.error} />
                ) : (
                  <Timeline>
                    {(history.data ?? []).map((revision, index, list) => (
                      <TimelineItem key={revision.revision} current={index === list.length - 1}>
                        <div className="pb-5">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-[11px] font-bold uppercase tracking-[0.1em] text-accent">
                              Revision {revision.revision}
                            </span>
                            <span className="text-[11px] text-ink-3">
                              {relativeTime(revision.updated_at)}
                            </span>
                          </div>
                          {revision.constraints.length ? (
                            <ul className="mt-2 grid gap-1.5">
                              {revision.constraints.map((constraint, position) => (
                                <li
                                  key={position}
                                  className="rounded-md border border-rule bg-surface-2 px-2.5 py-2 text-xs leading-5 text-ink-2"
                                >
                                  <span className="mr-1.5 font-semibold text-accent">
                                    {humanise(constraint.facet ?? "constraint")}
                                  </span>
                                  {constraint.text}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="mt-1.5 text-xs text-ink-3">No constraint recorded yet.</p>
                          )}
                        </div>
                      </TimelineItem>
                    ))}
                  </Timeline>
                )}
              </PanelBody>
            </Panel>

            <Panel>
              <PanelHeader
                title="Reviews judged against this case"
                description="The same case can be reviewed repeatedly as the code changes."
              />
              <PanelBody>
                {!related.length ? (
                  <p className="text-sm text-ink-3">No review has been recorded for this case yet.</p>
                ) : (
                  <ul className="grid gap-1.5">
                    {related.map((review) => (
                      <li key={review.id}>
                        <Link
                          to={`/reviews/${review.id}`}
                          className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-rule bg-surface-2 px-3 py-2.5 transition hover:border-rule-strong"
                        >
                          <span className="text-sm font-semibold text-ink">
                            Review {review.sequence}
                          </span>
                          <MetaLine
                            items={[
                              `case rev ${review.case.revision}`,
                              `${review.findings.length} candidates`,
                              relativeTime(review.started_at),
                            ]}
                          />
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </PanelBody>
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
}

function CaseCard({
  value,
  selected,
  onSelect,
  reviewedRepository,
}: {
  value: CaseSummary;
  selected: boolean;
  onSelect: () => void;
  reviewedRepository: string | null;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={selected ? "true" : undefined}
      className={cn(
        "w-full rounded-lg border p-3.5 text-left transition",
        selected
          ? "border-accent/45 bg-accent-soft"
          : "border-rule bg-surface hover:border-rule-strong",
      )}
    >
      <div className="font-display text-[15px] font-semibold leading-5 text-ink">
        {/* A case has no title of its own to show — what identifies it to a reader is the
            code it has been used to judge. */}
        {reviewedRepository || "Not yet reviewed"}
      </div>
      <MetaLine
        className="mt-2"
        items={[
          `Revision ${value.revision}`,
          `${value.constraints.length} constraints`,
          `${value.decisions.length} decisions`,
          relativeTime(value.updated_at),
        ]}
      />
      <Mono className="mt-1.5 block truncate text-[11px] text-ink-3">
        {shortId(value.case_id, 18)}
      </Mono>
    </button>
  );
}

function CaseSnapshot({ value }: { value: CaseSummary }) {
  return (
    <Panel>
      <PanelHeader
        title="Current context"
        description={`Revision ${value.revision} · updated ${absoluteTime(value.updated_at)}`}
      />
      <PanelBody className="grid gap-4 md:grid-cols-2">
        <div>
          <Label>Policy context</Label>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {Object.entries(value.policy_context)
              .filter(([, scope]) => Boolean(scope))
              .map(([key, scope]) => (
                <Tag key={key}>
                  {key}: {String(scope)}
                </Tag>
              ))}
            {Object.values(value.policy_context).every((scope) => !scope) ? (
              <span className="text-sm text-ink-3">No scope pinned.</span>
            ) : null}
          </div>
        </div>
        <div>
          <Label>Constraints · {value.constraints.length}</Label>
          {value.constraints.length ? (
            <ul className="mt-1.5 grid gap-1.5">
              {value.constraints.map((constraint, index) => (
                <li
                  key={index}
                  className="rounded-md border border-rule bg-surface-2 px-2.5 py-2 text-xs leading-5 text-ink-2"
                >
                  <span className="mr-1.5 font-semibold text-accent">
                    {humanise(constraint.facet ?? "constraint")}
                  </span>
                  {constraint.text}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1.5 text-sm text-ink-3">None recorded.</p>
          )}
        </div>
        <div>
          <Label>Decisions · {value.decisions.length}</Label>
          {value.decisions.length ? (
            <ul className="mt-1.5 grid gap-1.5">
              {value.decisions.map((decision, index) => (
                <li
                  key={index}
                  className="rounded-md border border-rule bg-surface-2 px-2.5 py-2 text-xs leading-5 text-ink-2"
                >
                  {decision.text}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1.5 text-sm text-ink-3">None recorded.</p>
          )}
        </div>
      </PanelBody>
    </Panel>
  );
}
