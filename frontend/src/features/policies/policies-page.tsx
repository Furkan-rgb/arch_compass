import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import { useDeferredValue, useId, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  api,
  type PolicyContext,
  type PolicyDocument,
  type PolicySourceRegistration,
  type Review,
} from "../../api";
import { cn } from "../../lib/cn";
import {
  humanise,
  relativeTime,
  repositoryName,
  strengthOf,
} from "../../lib/format";
import { StrengthBadge, Tag } from "../../ui/badge";
import { Button, ToggleButton } from "../../ui/button";
import { Field, Input, SearchInput } from "../../ui/field";
import { ChevronDown } from "../../ui/icons";
import { Markdown } from "../../ui/markdown";
import { MetaLine, Mono } from "../../ui/meta";
import { PageHeader } from "../../ui/page";
import { Label, Panel, PanelBody, PanelHeader } from "../../ui/panel";
import {
  EmptyState,
  ErrorNotice,
  LoadingPanel,
  Notice,
  Spinner,
} from "../../ui/states";
import { useToast } from "../../ui/toast";
import { PolicyEditor } from "./policy-editor";

const STRENGTHS = ["all", "required", "preferred", "guidance"] as const;
const SCOPES = [
  "all",
  "general",
  "user",
  "organisation",
  "repository",
  "accepted_adr",
] as const;

/**
 * Which policy is open, in the address bar.
 *
 * A policy is one of the three things `--mark` exists to link to, and the review cites one
 * by id in every bearing it prints. Held in component state it could not be linked to,
 * bookmarked, or reopened after a refresh — so the citation had nowhere to point and the
 * charter's fourth rule, *if it appears on screen its provenance is reachable*, was half
 * kept. A query parameter rather than a path segment for the reason `review-page.tsx` gives
 * at length: a parameter never changes which route matched, so the page is never rebuilt.
 */
const OPEN_PARAM = "open";

/** What a policy is, for the search box: title, description, body and tags, lowercased once. */
function indexOf(policies: PolicyDocument[]): Map<string, string> {
  return new Map(
    policies.map((policy) => [
      policy.id,
      `${policy.title} ${policy.description ?? ""} ${policy.body} ${policy.tags.join(" ")}`.toLowerCase(),
    ]),
  );
}

/**
 * Whether the case a review would run under can retrieve this policy at all.
 *
 * A mirror of `PolicyDocument.applies_in` in `policies/records.py`, and deliberately a
 * literal one: a non-general policy whose `applies_to` does not match the case's user,
 * organisation or repository never enters the mandatory lane. Without this on screen you
 * can filter the page to organisation policies, read them, and never learn that not one of
 * them can be selected for a judgement.
 *
 * `null` for a general policy, which reaches every case and has nothing to report.
 */
function scopeReach(
  policy: PolicyDocument,
  context: PolicyContext | null,
): { reaches: boolean; sentence: string } | null {
  if (policy.scope === "general") return null;
  const field =
    policy.scope === "user"
      ? "user"
      : policy.scope === "organisation"
        ? "organisation"
        : "repository";
  const pinned = context?.[field] ?? null;
  if (!policy.applies_to) {
    return {
      reaches: false,
      sentence: `This policy names no ${field}, so nothing matches it.`,
    };
  }
  if (!pinned) {
    return {
      reaches: false,
      sentence: `The current case pins no ${field}, so retrieval never selects this policy.`,
    };
  }
  if (pinned !== policy.applies_to) {
    return {
      reaches: false,
      sentence: `The current case is scoped to the ${field} ${pinned}, and this policy is filed under ${policy.applies_to}.`,
    };
  }
  return {
    reaches: true,
    sentence: `The current case is scoped to the ${field} ${pinned}, so retrieval can select this policy.`,
  };
}

/** What is known about which reviews weighed a policy, including "not yet" and "not read". */
type Citations = { pending: boolean; failed: boolean; reviews: Review[] };

function PolicyCard({
  policy,
  expanded,
  onToggle,
  onEdit,
  onDelete,
  deleting,
  fromRepository,
  reach,
  citations,
}: {
  policy: PolicyDocument;
  expanded: boolean;
  onToggle: () => void;
  onEdit: () => void;
  onDelete: () => void;
  deleting: boolean;
  fromRepository: boolean;
  reach: { reaches: boolean; sentence: string } | null;
  citations: Citations;
}) {
  const [confirming, setConfirming] = useState(false);
  const bodyId = useId();
  const strength = strengthOf(policy.strength);
  const workspaceOwned = policy.origin === "workspace";

  return (
    <article
      className={cn(
        "overflow-hidden rounded-lg border bg-surface transition",
        expanded
          ? "border-rule-strong"
          : "border-rule hover:border-rule-strong",
      )}
    >
      {/* Only the title and what identifies it are inside the control. The disclosure used
          to wrap the description, the scope, the author and every tag as well, so one row's
          accessible name was a paragraph read aloud before the reader learnt it was a
          button. Everything else is a sibling now — still on the row, no longer in its name. */}
      <div className="px-4 py-3.5 sm:px-5">
        <h3>
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={expanded}
            aria-controls={bodyId}
            className="flex w-full items-start justify-between gap-3 text-left"
          >
            <span className="flex min-w-0 flex-wrap items-center gap-2">
              <span className="font-display text-base font-semibold tracking-tight text-ink">
                {policy.title}
              </span>
              <StrengthBadge strength={policy.strength} />
              {workspaceOwned ? <Tag>workspace</Tag> : null}
              {fromRepository ? <Tag>repository</Tag> : null}
            </span>
            <ChevronDown
              className={cn(
                "mt-1 size-4 shrink-0 text-ink-3 transition",
                expanded && "rotate-180",
              )}
            />
          </button>
        </h3>
        <p className="mt-1.5 text-sm leading-6 text-ink-2">
          {policy.description}
        </p>
        <MetaLine
          className="mt-2"
          items={[
            humanise(policy.scope),
            policy.applies_to ? `applies to ${policy.applies_to}` : null,
            reach
              ? reach.reaches
                ? "in scope for this case"
                : "out of scope for this case"
              : null,
            policy.source.author,
            ...policy.tags.map((tag) => <Tag key={tag}>{tag}</Tag>),
          ]}
        />
      </div>

      {expanded ? (
        <div
          id={bodyId}
          className="animate-expand border-t border-rule px-4 py-4 sm:px-5"
        >
          <Markdown>{policy.body}</Markdown>

          {reach ? (
            <p className="mt-4 text-sm leading-6 text-ink-2">
              {reach.sentence}{" "}
              <Link
                to="/cases"
                className="underline decoration-rule-strong underline-offset-2 transition hover:decoration-ink"
              >
                Set the case scope
              </Link>
              .
            </p>
          ) : null}

          <div className="mt-5 border-t border-rule pt-4">
            <Label>Cited by</Label>
            {citations.pending ? (
              <p className="mt-1.5 flex items-center gap-2 text-sm text-ink-3">
                {/* The label is printed right beside it. */}
                <Spinner label="" /> Reading the stored reviews…
              </p>
            ) : citations.failed ? (
              // An explicit unknown outranks an implied one, and "none" is the wrong answer
              // to a question that was not asked successfully.
              <p className="mt-1.5 text-sm text-ink-3">
                The stored reviews could not be read, so this is unknown.
              </p>
            ) : citations.reviews.length ? (
              <ul className="mt-1.5 grid gap-1.5">
                {citations.reviews.map((review) => (
                  <li key={review.id}>
                    <Link
                      to={`/reviews/${review.id}`}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-rule bg-surface-2 px-3 py-2 transition hover:border-rule-strong"
                    >
                      <span className="text-sm font-semibold text-ink">
                        {repositoryName(review.repository.path)} · review{" "}
                        {review.sequence}
                      </span>
                      <MetaLine items={[relativeTime(review.started_at)]} />
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              // An explicit unknown outranks an implied one: a blank here reads as a page
              // that failed to load rather than as a policy nothing has weighed yet.
              <p className="mt-1.5 text-sm text-ink-3">
                No stored review has weighed this policy.
              </p>
            )}
          </div>

          <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-rule pt-4">
            <div className="min-w-0">
              <Label>Provenance</Label>
              <MetaLine
                className="mt-1"
                items={[
                  <Mono key="id" className="text-[11px]">
                    {policy.id}
                  </Mono>,
                  <Mono key="path" className="text-[11px]">
                    {policy.source_path}
                  </Mono>,
                  <Mono key="hash" className="text-[11px]">
                    {policy.content_hash.slice(0, 12)}
                  </Mono>,
                  strength.label,
                ]}
              />
            </div>
            {workspaceOwned ? (
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <Button size="sm" variant="secondary" onClick={onEdit}>
                  Edit
                </Button>
                {confirming ? (
                  <>
                    <span className="text-xs text-ink-3">
                      Delete permanently?
                    </span>
                    <Button
                      size="sm"
                      variant="danger"
                      disabled={deleting}
                      onClick={onDelete}
                    >
                      Confirm
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setConfirming(false)}
                    >
                      Keep
                    </Button>
                  </>
                ) : (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setConfirming(true)}
                  >
                    Delete
                  </Button>
                )}
              </div>
            ) : (
              <p className="text-xs text-ink-3">
                Read from a registered source — edit it where it is authored.
              </p>
            )}
          </div>
        </div>
      ) : null}
    </article>
  );
}

/** Which policy the editor is holding: an existing one, or `null` for a new one. */
type EditorTarget = { policy: PolicyDocument | null };

export function PoliciesPage() {
  const client = useQueryClient();
  const say = useToast().say;
  const [search, setSearch] = useSearchParams();
  const expanded = search.get(OPEN_PARAM);

  // Identity and lineage, which is all the chooser and the case lookup need. Asking for the
  // reviews themselves to read a path and a case id would download most of a repository's
  // atlas per row.
  const summaries = useQuery({
    queryKey: ["review-summaries"],
    queryFn: api.reviewSummaries,
  });
  const cases = useQuery({ queryKey: ["cases"], queryFn: api.cases });
  const workspace = useQuery({
    queryKey: ["workspace"],
    queryFn: api.workspace,
  });

  /** Stored reviews, newest first, which is the order the chooser and the case default read. */
  const newestFirst = useMemo(
    () =>
      [...(summaries.data ?? [])].sort(
        (left, right) =>
          Date.parse(right.started_at) - Date.parse(left.started_at),
      ),
    [summaries.data],
  );
  const repositories = useMemo(
    () => [...new Set(newestFirst.map((review) => review.repository.path))],
    [newestFirst],
  );

  /**
   * `undefined` means nobody has chosen, and the page follows the newest review.
   *
   * Every review loads its corpus *with* a repository root, which adds that repository's own
   * `.archcompass/policies`. This page asked for the corpus without one, so a team keeping
   * its architecture rules in the repository saw them applied in every finding and absent
   * from the page called Policies. Defaulting to the newest review's repository makes the
   * first thing on screen the corpus that actually judged.
   */
  const [chosenRoot, setChosenRoot] = useState<string | null | undefined>(
    undefined,
  );
  const root =
    chosenRoot === undefined ? (repositories[0] ?? null) : chosenRoot;

  const policies = useQuery({
    queryKey: ["policies", root],
    queryFn: ({ signal }) => api.policies({ repositoryRoot: root, signal }),
    // Held until the listing answers, so the corpus is fetched once against the repository
    // it is going to be read for rather than fetched twice and swapped underneath the reader.
    enabled: !summaries.isPending,
  });
  const sources = useQuery({
    queryKey: ["policy-sources"],
    queryFn: api.policySources,
  });

  const [query, setQuery] = useState("");
  const [strength, setStrength] = useState<(typeof STRENGTHS)[number]>("all");
  const [scope, setScope] = useState<(typeof SCOPES)[number]>("all");
  const [authoredHere, setAuthoredHere] = useState(false);
  const [open, setOpen] = useState<EditorTarget | null>(null);
  const [dirty, setDirty] = useState(false);
  const [pending, setPending] = useState<{ next: EditorTarget | null } | null>(
    null,
  );

  const remove = useMutation({
    meta: { handled: true },
    mutationFn: (id: string) => api.deletePolicy(id),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["policies"] });
    },
  });

  const all = useMemo(() => policies.data ?? [], [policies.data]);

  /**
   * The haystack, built once per corpus rather than once per keystroke.
   *
   * It concatenated and lowercased every title, description, **full Markdown body** and tag
   * on every render of every character typed. The bundled corpus is 54 policies; at 200 of
   * about 3KB each that is 600KB of string work between one letter and the next, and the box
   * falls behind the typing. `useDeferredValue` is the other half: the input takes the
   * keystroke immediately and the list catches up.
   */
  const haystacks = useMemo(() => indexOf(all), [all]);
  const deferredQuery = useDeferredValue(query);
  const needle = deferredQuery.trim().toLowerCase();

  /**
   * Which reviews cite each policy id — the reverse of the bearing a finding prints.
   *
   * The only thing on this page that needs the reviews rather than the listing of them, and
   * a stored review is most of a repository's atlas. So it is asked for when somebody opens
   * a policy and not before; arriving from a review, it is already in the cache.
   */
  const reviews = useQuery({
    queryKey: ["reviews"],
    queryFn: api.reviews,
    enabled: Boolean(expanded),
  });
  const citations = useMemo(() => {
    const map = new Map<string, Review[]>();
    for (const review of reviews.data ?? []) {
      const cited = new Set(
        review.findings.flatMap((finding) =>
          finding.policies.map((bearing) => bearing.policy_id),
        ),
      );
      for (const id of cited) {
        const existing = map.get(id);
        if (existing) existing.push(review);
        else map.set(id, [review]);
      }
    }
    return map;
  }, [reviews.data]);

  /** The case a review of this repository would run under, and therefore what it can reach. */
  const context = useMemo(() => {
    const list = cases.data ?? [];
    const active =
      list.find((item) => item.case_id === newestFirst[0]?.case_id) ?? list[0];
    return active?.policy_context ?? null;
  }, [cases.data, newestFirst]);

  const matches = (
    policy: PolicyDocument,
    axis: "strength" | "origin" | null = null,
  ) =>
    (!needle || (haystacks.get(policy.id) ?? "").includes(needle)) &&
    (scope === "all" || policy.scope === scope) &&
    (axis === "strength" ||
      strength === "all" ||
      policy.strength === strength) &&
    (axis === "origin" || !authoredHere || policy.origin === "workspace");

  const visible = all.filter((policy) => matches(policy));
  const byStrength = all.filter((policy) => matches(policy, "strength"));
  const authoredCount = all.filter(
    (policy) => matches(policy, "origin") && policy.origin === "workspace",
  ).length;
  const strengthCounts = {
    all: byStrength.length,
    required: byStrength.filter((policy) => policy.strength === "required")
      .length,
    preferred: byStrength.filter((policy) => policy.strength === "preferred")
      .length,
    guidance: byStrength.filter((policy) => policy.strength === "guidance")
      .length,
  };

  const setExpanded = (id: string | null) =>
    setSearch(
      (current) => {
        const params = new URLSearchParams(current);
        if (id) params.set(OPEN_PARAM, id);
        else params.delete(OPEN_PARAM);
        return params;
      },
      { replace: true },
    );

  /**
   * Every way into and out of the editor goes through here, because every one of them can
   * throw a draft away. The experience doc: *never navigate away from unsaved input*.
   */
  const requestEditor = (next: EditorTarget | null) => {
    const sameForm = next !== null && next.policy?.id === open?.policy?.id;
    if (open && dirty && !sameForm) {
      setPending({ next });
      return;
    }
    setPending(null);
    setDirty(false);
    setOpen(next);
  };

  const header = (
    <PageHeader
      eyebrow="Auditable guidance"
      title="Policies"
      description="The corpus a review is judged against."
      actions={
        <>
          {repositories.length ? (
            <label className="flex items-center gap-1.5 text-xs text-ink-3">
              Repository
              <select
                aria-label="Corpus repository"
                value={root ?? ""}
                onChange={(event) => setChosenRoot(event.target.value || null)}
                className="max-w-48 rounded-sm border border-rule bg-surface px-2 py-1 text-xs text-ink"
              >
                <option value="">Workspace only</option>
                {repositories.map((path) => (
                  <option key={path} value={path}>
                    {repositoryName(path)}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <Button
            variant={open ? "secondary" : "primary"}
            onClick={() => requestEditor(open ? null : { policy: null })}
          >
            {/* It read "Author policy" while an existing policy was open in the editor, and
                pressing it remounted the form empty over the draft. */}
            {open ? "Close editor" : "Author policy"}
          </Button>
        </>
      }
    />
  );

  if (summaries.isPending || policies.isPending) {
    return (
      <div>
        {header}
        <LoadingPanel label="Loading the policy corpus…" rows={5} />
      </div>
    );
  }

  if (policies.error) {
    return (
      <div>
        {header}
        <ErrorNotice
          error={policies.error}
          action={
            <Button
              size="sm"
              variant="secondary"
              onClick={() => void policies.refetch()}
            >
              Try again
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div>
      {header}

      {pending ? (
        <Notice tone="working" title="Unsaved draft" className="mb-5">
          <div className="flex flex-wrap items-center gap-3">
            <span>This policy has changes that have not been saved.</span>
            <Button
              size="sm"
              variant="danger"
              onClick={() => {
                const next = pending.next;
                setPending(null);
                setDirty(false);
                setOpen(next);
              }}
            >
              Discard them
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setPending(null)}>
              Keep writing
            </Button>
          </div>
        </Notice>
      ) : null}

      {open ? (
        <div className="mb-5">
          <PolicyEditor
            key={open.policy?.id ?? "new"}
            policy={open.policy}
            onDirtyChange={setDirty}
            onCancel={() => requestEditor(null)}
            onSaved={() => {
              setDirty(false);
              setOpen(null);
            }}
          />
        </div>
      ) : null}

      <div className="mb-5 grid gap-4 xl:grid-cols-[minmax(0,1fr)_300px] xl:items-start">
        <div>
          {/* Pinned, because this corpus is 54 policies and some 8,000 pixels long, and the
              search box that makes it navigable was reachable only from the top of it. The
              wrapper paints the canvas so the list scrolls behind the bar rather than through
              the gap between it and the rail, and `-mx-2 px-2` gives the card its full width
              back after that padding. */}
          <div className="sticky top-12 z-10 -mx-2 mb-3 bg-canvas px-2 py-2">
            <div className="grid gap-2 rounded-lg border border-rule bg-surface p-2 lg:grid-cols-[minmax(0,1fr)_auto]">
              <SearchInput
                label="Search policies"
                value={query}
                onValueChange={setQuery}
                placeholder="Search title, body or tag"
              />
              <div className="flex flex-wrap items-center gap-3">
                {/* The counts used to be a four-row Corpus panel beside the list, and the
                  content rule is that a count is a control or it is not on screen. Required
                  restated a number this row already owned as a button; Showing restated the
                  length of the list underneath it. */}
                <div
                  role="group"
                  aria-label="Filter by strength"
                  className="flex gap-1"
                >
                  {STRENGTHS.map((item) => (
                    <ToggleButton
                      key={item}
                      pressed={strength === item}
                      disabled={strength !== item && !strengthCounts[item]}
                      onClick={() => setStrength(item)}
                      className="capitalize"
                    >
                      {item}
                      <span className="tabular-nums text-ink-3">
                        {strengthCounts[item]}
                      </span>
                    </ToggleButton>
                  ))}
                </div>
                <ToggleButton
                  pressed={authoredHere}
                  disabled={!authoredHere && !authoredCount}
                  onClick={() => setAuthoredHere(!authoredHere)}
                >
                  Authored here
                  <span className="tabular-nums text-ink-3">
                    {authoredCount}
                  </span>
                </ToggleButton>
                <label className="flex items-center gap-1.5 text-xs text-ink-3">
                  Scope
                  <select
                    aria-label="Filter by scope"
                    value={scope}
                    onChange={(event) =>
                      setScope(event.target.value as (typeof SCOPES)[number])
                    }
                    className="rounded-sm border border-rule bg-surface px-2 py-1 text-xs text-ink"
                  >
                    {SCOPES.map((item) => (
                      <option key={item} value={item}>
                        {humanise(item)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </div>
          </div>

          {!visible.length ? (
            <EmptyState
              title={
                all.length ? "No policy matches that" : "No policies loaded"
              }
            >
              {all.length
                ? "Clear the search, or widen the strength and scope filters."
                : "Author a workspace policy, or register a folder of Markdown policies as a source."}
            </EmptyState>
          ) : (
            <div className="grid gap-2.5">
              {visible.map((policy) => (
                <PolicyCard
                  key={policy.id}
                  policy={policy}
                  expanded={expanded === policy.id}
                  onToggle={() =>
                    setExpanded(expanded === policy.id ? null : policy.id)
                  }
                  onEdit={() => requestEditor({ policy })}
                  onDelete={() => remove.mutate(policy.id)}
                  deleting={remove.isPending}
                  fromRepository={
                    Boolean(root) && policy.source_path.startsWith(`${root}/`)
                  }
                  reach={scopeReach(policy, context)}
                  citations={{
                    pending: reviews.isPending,
                    failed: Boolean(reviews.error),
                    reviews: citations.get(policy.id) ?? [],
                  }}
                />
              ))}
            </div>
          )}

          {remove.error ? (
            <div className="mt-4">
              <ErrorNotice error={remove.error} />
            </div>
          ) : null}
        </div>

        <SourcesPanel
          sources={sources}
          hosted={Boolean(workspace.data?.hosted)}
          onChanged={async (message) => {
            await Promise.all([
              client.invalidateQueries({ queryKey: ["policy-sources"] }),
              client.invalidateQueries({ queryKey: ["policies"] }),
            ]);
            say(message, "Sources");
          }}
        />
      </div>
    </div>
  );
}

/**
 * The folders this workspace reads, and the way to add one.
 *
 * It was a read-only list of something nobody could add to, so its empty state — *only the
 * bundled corpus and anything authored here* — read as a limit of the product rather than
 * as a thing you had not done yet. The panel described the capability and withheld it.
 *
 * The server refuses this on the hosted demo, because the folder named would be one of the
 * server's, so the field is not shown there and the sentence says why. A control that
 * returns a 403 every time is worse than no control.
 */
function SourcesPanel({
  sources,
  hosted,
  onChanged,
}: {
  sources: UseQueryResult<PolicySourceRegistration[]>;
  hosted: boolean;
  onChanged: (message: string) => Promise<void>;
}) {
  const [path, setPath] = useState("");

  const add = useMutation({
    meta: { handled: true },
    mutationFn: (source: string) => api.addPolicySource(source),
    onSuccess: async (registered) => {
      setPath("");
      await onChanged(`${registered.canonical_path} is read on every review.`);
    },
  });
  const drop = useMutation({
    mutationFn: (source: string) => api.removePolicySource(source),
    onSuccess: async (_result, source) => {
      await onChanged(`${source} is no longer read.`);
    },
  });

  return (
    <Panel>
      <PanelHeader
        title="Sources"
        description="Folders of Markdown policies this workspace reads on every review."
      />
      <PanelBody className="grid gap-3">
        {sources.isLoading ? (
          <p className="text-sm text-ink-3">Loading sources…</p>
        ) : sources.error ? (
          <ErrorNotice
            error={sources.error}
            action={
              <Button
                size="sm"
                variant="secondary"
                onClick={() => void sources.refetch()}
              >
                Try again
              </Button>
            }
          />
        ) : !sources.data?.length ? (
          <p className="text-sm text-ink-3">
            Only the bundled corpus and anything authored here.
          </p>
        ) : (
          <ul className="grid gap-1.5">
            {sources.data.map((source) => (
              <li
                key={source.canonical_path}
                className="flex items-center gap-2"
              >
                <Mono className="min-w-0 flex-1 truncate text-[11px]">
                  {source.canonical_path}
                </Mono>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={drop.isPending}
                  onClick={() => drop.mutate(source.canonical_path)}
                >
                  Stop reading
                </Button>
              </li>
            ))}
          </ul>
        )}

        {hosted ? (
          <p className="text-sm leading-6 text-ink-3">
            This is the hosted demo, so a folder on the server cannot be
            registered. Policies you write here are kept in your own workspace
            and read by every review you run.
          </p>
        ) : (
          <form
            className="grid gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (path.trim()) add.mutate(path.trim());
            }}
          >
            <Field
              label="Add a folder"
              hint="An absolute path on this machine. Every Markdown policy under it joins the corpus."
            >
              {(props) => (
                <Input
                  {...props}
                  value={path}
                  onChange={(event) => setPath(event.target.value)}
                  placeholder="/work/architecture/policies"
                />
              )}
            </Field>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                type="submit"
                variant="secondary"
                disabled={!path.trim() || add.isPending}
              >
                {add.isPending ? <Spinner /> : "Register source"}
              </Button>
            </div>
            {add.error ? <ErrorNotice error={add.error} /> : null}
          </form>
        )}
      </PanelBody>
    </Panel>
  );
}
