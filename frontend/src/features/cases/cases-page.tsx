import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api, type CaseSummary, type PolicyContext } from "../../api";
import { cn } from "../../lib/cn";
import { absoluteTime, plural, relativeTime, repositoryName, shortId } from "../../lib/format";
import { Tag } from "../../ui/badge";
import { Button, ButtonLink } from "../../ui/button";
import { Field, Input } from "../../ui/field";
import { MetaLine, Mono } from "../../ui/meta";
import { PageHeader } from "../../ui/page";
import { Label, Panel, PanelBody, PanelHeader } from "../../ui/panel";
import { EmptyState, ErrorNotice, LoadingPanel, Skeleton, Spinner } from "../../ui/states";
import { Timeline, TimelineItem } from "../../ui/timeline";
import { useToast } from "../../ui/toast";

/**
 * Cases are the human half of a review: what this architecture is for, what it must live
 * with, what has already been decided, and what a reviewer answered when asked. Each
 * review that asks opens one revision and keeps it, rather than overwriting the last, so
 * the page is built around the sequence rather than around a form.
 */
export function CasesPage() {
  const cases = useQuery({ queryKey: ["cases"], queryFn: api.cases });
  // Identity, lineage and counts, which is everything this page reads off a review. Asking
  // for the reviews themselves downloaded most of a repository's atlas per row to print a
  // number.
  const reviews = useQuery({ queryKey: ["reviews", "summary"], queryFn: api.reviewSummaries });
  const [selected, setSelected] = useState<string | null>(null);

  const selectedId = selected ?? cases.data?.[0]?.case_id ?? null;
  const history = useQuery({
    queryKey: ["case-history", selectedId],
    queryFn: () => api.caseHistory(selectedId!),
    enabled: Boolean(selectedId),
    // A recorded revision is immutable — the charter's third commitment — so there is
    // nothing here that a refetch could learn.
    staleTime: Infinity,
  });

  const header = (
    <PageHeader
      eyebrow="Human context"
      title="Architecture cases"
      description="What people answered when a judgement stopped to ask."
    />
  );

  if (cases.isLoading) {
    return (
      <div>
        {header}
        <LoadingPanel label="Loading architecture cases…" rows={4} />
      </div>
    );
  }
  if (cases.error) {
    return (
      <div>
        {header}
        <ErrorNotice
          error={cases.error}
          action={
            <Button size="sm" variant="secondary" onClick={() => void cases.refetch()}>
              Try again
            </Button>
          }
        />
      </div>
    );
  }

  const all = cases.data ?? [];
  /**
   * Three answers, not two: the name, "no review has used this case", and "not known yet".
   *
   * A case has no title of its own, so this name is the whole of a card's identity — and it
   * comes from a second query the page does not wait for. Returning `null` for both "still
   * loading" and "genuinely never reviewed" made every card on every load read *Not yet
   * reviewed*, a definite claim that was usually false, and then rewrote the whole column a
   * moment later. The charter's rule is that an explicit unknown beats an implied one, so
   * "not known yet" is `undefined` and is drawn as a placeholder rather than as a sentence.
   */
  const repositoryFor = (caseId: string): string | null | undefined => {
    if (reviews.isPending) return undefined;
    const review = (reviews.data ?? []).find((item) => item.case_id === caseId);
    return review ? repositoryName(review.repository.path) : null;
  };
  const related = (reviews.data ?? []).filter((review) => review.case_id === selectedId);
  const latest = history.data?.at(-1) ?? all.find((item) => item.case_id === selectedId);

  return (
    <div>
      {header}

      {!all.length ? (
        /**
         * There is no "New case" button here any more, and there was never anything a case
         * made this way could be used for. `POST /api/repositories/start` picks the case
         * itself — *which case that is, is the application's to decide and not the client's*
         * — so one opened here was never selectable from the form that starts a review, and
         * sat in this list for ever labelled "Not yet reviewed". It was the deleted "confirm
         * the architecture case" step wearing a third shape.
         */
        <EmptyState
          title="No architecture case yet"
          action={<ButtonLink to="/start">Start a review</ButtonLink>}
        >
          A case is opened by the review that needs it, and fills in as later reviews ask for
          what they cannot read from the code.
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

          {/* `order-first` below `xl`, where this column is stacked *after* the whole case
              list. Pressing the third of fifteen cards changed a panel a dozen cards below
              the fold, with no scroll and no announcement, so the press read as doing
              nothing at all. Above `xl` the grid puts the column back on the right, where the
              card and the detail it drives are side by side and the order does not matter.
              The repositories page carries the same class for the same reason. */}
          <div className="order-first grid gap-4 xl:order-none">
            {/* Keyed on the case, so moving to another one gives the snapshot — and the
                scope form inside it — a fresh pair of states. Without the key React kept the
                instance across a selection change, so an open Set scope form stayed open
                holding the *previous* case's draft under the new case's header, and Save
                wrote those values onto the case now on screen. Policy scope decides which
                policies a review can retrieve at all, so that is the one thing about a case
                a person still sets by hand, silently misdirected. Closing the form on a
                selection change is also the honest behaviour: an open form belongs to the
                record it was opened on. */}
            {latest ? <CaseSnapshot key={latest.case_id} value={latest} /> : null}

            <Panel>
              <PanelHeader
                title="Revision history"
                description="Each review that asked opened one revision; earlier ones stay readable."
              />
              <PanelBody>
                {history.isLoading ? (
                  <div className="flex items-center gap-2 text-sm text-ink-3">
                    {/* The label is printed right beside it. */}
                    <Spinner label="" /> Loading revisions…
                  </div>
                ) : history.error ? (
                  <ErrorNotice
                    error={history.error}
                    action={
                      <Button size="sm" variant="secondary" onClick={() => void history.refetch()}>
                        Try again
                      </Button>
                    }
                  />
                ) : (
                  <Timeline>
                    {(history.data ?? []).map((revision, index, list) => (
                      <TimelineItem key={revision.revision} current={index === list.length - 1}>
                        <div className="pb-5">
                          <div className="flex flex-wrap items-center gap-2">
                            <Label>Revision {revision.revision}</Label>
                            <span className="text-[11px] text-ink-3">
                              {relativeTime(revision.updated_at)}
                            </span>
                          </div>
                          {revision.answers.length ? (
                            <ul className="mt-2 grid gap-1.5">
                              {revision.answers.map((answer, position) => (
                                <li
                                  key={position}
                                  className="rounded-md border border-rule bg-surface-2 px-2.5 py-2 text-xs leading-5 text-ink-2"
                                >
                                  <span className="block font-semibold text-ink">
                                    {answer.question}
                                  </span>
                                  {answer.status === "skipped" ? (
                                    <span className="text-ink-3">Explicitly skipped</span>
                                  ) : (
                                    answer.value
                                  )}
                                  <span className="mt-1 block text-[11px] text-ink-3">
                                    {answer.actor}
                                  </span>
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="mt-1.5 text-xs text-ink-3">
                              Opened empty. Nothing has been asked yet.
                            </p>
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
                {/* The same three states the card's own heading answers, for the same
                    reason: a list that has not arrived is not a list that is empty, and a
                    list that could not be read is neither. */}
                {reviews.isPending ? (
                  <div className="flex items-center gap-2 text-sm text-ink-3">
                    <Spinner label="" /> Reading the review history…
                  </div>
                ) : reviews.error ? (
                  <ErrorNotice
                    error={reviews.error}
                    action={
                      <Button size="sm" variant="secondary" onClick={() => void reviews.refetch()}>
                        Try again
                      </Button>
                    }
                  />
                ) : !related.length ? (
                  <p className="text-sm text-ink-3">
                    No review has been recorded for this case yet.
                  </p>
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
                              `case rev ${review.case_revision}`,
                              `${review.finding_count} candidates`,
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
  /** The name, `null` where no review has used this case, `undefined` where it is not known yet. */
  reviewedRepository: string | null | undefined;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={selected ? "true" : undefined}
      className={cn(
        "w-full rounded-lg border p-3.5 text-left transition",
        selected
          ? "border-rule-strong bg-sunken"
          : "border-rule bg-surface hover:border-rule-strong",
      )}
    >
      <div className="flex min-h-5 items-center font-display text-[15px] font-semibold leading-5 text-ink">
        {/* A case has no title of its own to show — what identifies it to a reader is the
            code it has been used to judge. While that is still being fetched the card says
            nothing rather than saying something false; the block is sized to the line it
            will hold, so nothing moves when the name arrives. */}
        {reviewedRepository === undefined ? (
          <Skeleton className="h-3.5 w-32" />
        ) : (
          (reviewedRepository ?? "Not yet reviewed")
        )}
      </div>
      <MetaLine
        className="mt-2"
        items={[
          `Revision ${value.revision}`,
          plural(value.answers.length, "answer"),
          relativeTime(value.updated_at),
        ]}
      />
      <Mono className="mt-1.5 block truncate text-[11px] text-ink-3">
        {shortId(value.case_id, 18)}
      </Mono>
    </button>
  );
}

/**
 * What each field of the policy context does, said beside the box that sets it.
 *
 * These are not free-text notes. `PolicyDocument.applies_in` compares a scoped policy's
 * `applies_to` against exactly one of them, so a value that is nearly right retrieves
 * nothing at all — which is the whole reason the sentence names the comparison rather than
 * describing the field.
 */
const SCOPE_FIELDS = [
  {
    key: "user" as const,
    label: "User",
    hint: "A user-scoped policy is retrieved only when its subject is exactly this.",
  },
  {
    key: "organisation" as const,
    label: "Organisation",
    hint: "An organisation-scoped policy is retrieved only when its subject is exactly this.",
  },
  {
    key: "repository" as const,
    label: "Repository",
    hint: "A repository or accepted-ADR policy is retrieved only when its subject is exactly this.",
  },
];

/**
 * The one thing about a case a person still sets directly, and until now could not.
 *
 * `PolicyContext` decides applicability: a non-general policy whose subject does not match
 * the case's user, organisation or repository never enters the mandatory lane. Nothing set
 * it — `createCase` sent an empty object and the rescope endpoint had no client — so every
 * scoped policy in the corpus was unreachable, and the Policies page offered a scope filter
 * across four kinds of policy that no judgement could retrieve.
 *
 * Not a revision. Scope is patched, because it is a statement about which policies apply
 * rather than an answer to something a review asked, and the case's sequence of revisions is
 * the record of answers.
 */
function PolicyScopeEditor({ value }: { value: CaseSummary }) {
  const client = useQueryClient();
  const say = useToast().say;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<PolicyContext>(value.policy_context);

  const save = useMutation({
    meta: { handled: true },
    mutationFn: () =>
      api.rescopeCase(value.case_id, {
        user: draft.user?.trim() || null,
        organisation: draft.organisation?.trim() || null,
        repository: draft.repository?.trim() || null,
      }),
    onSuccess: async () => {
      setEditing(false);
      await Promise.all([
        client.invalidateQueries({ queryKey: ["cases"] }),
        client.invalidateQueries({ queryKey: ["case-history", value.case_id] }),
      ]);
      say("Scoped policies are retrievable for this case from the next review.", "Scope saved");
    },
  });

  const pinned = SCOPE_FIELDS.filter(({ key }) => value.policy_context[key]);

  if (!editing) {
    return (
      <div>
        <Label>Policy context</Label>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          {pinned.length ? (
            pinned.map(({ key, label }) => (
              <Tag key={key}>
                {label.toLowerCase()}: {value.policy_context[key]}
              </Tag>
            ))
          ) : (
            <span className="text-sm text-ink-3">
              No scope pinned, so only general policies can be retrieved.
            </span>
          )}
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setDraft(value.policy_context);
              setEditing(true);
            }}
          >
            {pinned.length ? "Change scope" : "Set scope"}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <form
      className="grid gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate();
      }}
    >
      <Label>Policy context</Label>
      {SCOPE_FIELDS.map(({ key, label, hint }) => (
        <Field key={key} label={label} hint={hint}>
          {(props) => (
            <Input
              {...props}
              value={draft[key] ?? ""}
              onChange={(event) => setDraft({ ...draft, [key]: event.target.value })}
            />
          )}
        </Field>
      ))}
      {save.error ? <ErrorNotice error={save.error} /> : null}
      <div className="flex flex-wrap items-center gap-2">
        {/* The mark is added beside the word, not swapped for it. Substituting the spinner
            collapsed the button to a third of its width, moved Cancel beside it, and changed
            its accessible name from "Save scope" to "Working" — so a reader lost the
            identity of the thing they had just pressed. This is the same gesture the rest of
            the system uses for a state: something appears, nothing inverts. */}
        <Button size="sm" type="submit" disabled={save.isPending}>
          {save.isPending ? (
            <>
              <Spinner label="" /> Saving scope
            </>
          ) : (
            "Save scope"
          )}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
          Cancel
        </Button>
      </div>
    </form>
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
        <PolicyScopeEditor value={value} />
        {/* The count, not the answers. This panel used to print the newest revision's
            answers in full, and the Revision history directly beneath it prints every
            revision's answers including that same one — the two blocks were
            character-for-character identical markup, one scroll apart, and the duplication
            grew with the number of answers. The timeline is the record: it is ordered
            oldest-first and marks the last item `current`, so it is the place an answer is
            read. What is left here is what the timeline does not repeat — the revision, the
            timestamp and the policy scope. */}
        <div>
          <Label>Answered · {value.answers.length}</Label>
          <p className="mt-1.5 text-sm text-ink-3">
            {value.answers.length
              ? "Read them in the revision history below, beside the review that asked."
              : "Nothing asked yet. A case fills in when a judgement turns on something the repository cannot settle."}
          </p>
        </div>
      </PanelBody>
    </Panel>
  );
}
