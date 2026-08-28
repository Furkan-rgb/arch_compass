import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import {
  useDeferredValue,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
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
import { useIsTabletUp } from "../../lib/media";
import { StrengthBadge, Tag } from "../../ui/badge";
import { Button, ToggleButton } from "../../ui/button";
import { Field, Input, SearchInput, Select } from "../../ui/field";
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
 * The dense size for this page's two selects, written once rather than beside each of them.
 *
 * Both used to be a hand-rolled `<select>` with its own class list — `border-rule bg-surface
 * px-2 py-1` — which made three spellings of one control on one page: this, `ui/field.tsx`'s
 * `Select`, and the vendored Radix one. `--rule` is the hairline that *separates*; a border
 * belongs to something you could pick up, and a select is exactly that. On the filter bar the
 * result was a 32px `ToggleButton` on the control film beside a 26px select on the panel
 * colour with a fainter edge, which is two different claims about what is operable.
 *
 * So the paint comes from `controlClass` now — `--rule-control`, `--control`, the invalid and
 * focus behaviour every other field in the product has — and only the *size* is said here.
 * That size is the one the system already made five times: 32px on a fine pointer, because a
 * filter bar is dense, and the 44px floor on a coarse one, because 44px is a touch
 * requirement and is answered where touch is. `pr-7` leaves the native arrow its room after
 * `pl-2.5` has taken the rest away.
 */
const DENSE_SELECT = "w-auto min-h-8 pointer-coarse:min-h-11 py-1 pl-2.5 pr-7 text-xs";

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
  const disclosure = useRef<HTMLButtonElement | null>(null);

  /**
   * A citation that names a policy has to arrive at the policy, not at the top of the list.
   *
   * `OPEN_PARAM` above already expands the right card; it was the other half of the promise
   * that was missing. The corpus is 54 cards and some 8,000 pixels, so following a review's
   * bearing landed a reader at scroll 0 with every cue that anything had happened — the
   * chevron, the body, the provenance — below the fold. Nothing on screen said which of the
   * 54 the link had named.
   *
   * Mount only, and the ref is what makes that mean *arrival*: a card that is already open
   * the first time it renders is one the address named, while a card the reader pressed was
   * mounted long before and is already under their pointer. Re-scrolling that one would drag
   * the page out from under the gesture that opened it.
   *
   * The focus goes with the scroll because a keyboard arrival is the same arrival — landing
   * on the disclosure means the next key collapses it or the next tab enters the body.
   * `preventScroll` so the two do not fight; the alignment is `scrollIntoView`'s to decide,
   * and `scroll-mt-32` below is what keeps the card clear of the sticky filter bar.
   * `styles.css` sets `scroll-behavior: smooth` on `html` and collapses it under
   * `prefers-reduced-motion`, so the motion contract is honoured without asking for it here.
   */
  const openedOnArrival = useRef(expanded);
  useEffect(() => {
    if (!openedOnArrival.current) return;
    const node = disclosure.current;
    node?.focus({ preventScroll: true });
    node?.scrollIntoView?.({ block: "start" });
  }, []);

  return (
    <article
      className={cn(
        // No `hover:border-rule-strong`. The edge is the card's whole outline, and lighting
        // the whole outline promised a click on the description, the meta line and the tags —
        // none of which do anything. The paint moved to the row that actually acts, below.
        "scroll-mt-32 overflow-hidden rounded-lg border bg-surface transition",
        expanded ? "border-rule-strong" : "border-rule",
      )}
    >
      {/* Only the title and what identifies it are inside the control. The disclosure used
          to wrap the description, the scope, the author and every tag as well, so one row's
          accessible name was a paragraph read aloud before the reader learnt it was a
          button. Everything else is a sibling now — still on the row, no longer in its name. */}
      <div className="px-4 py-3.5 sm:px-5">
        {/* The heading is the exact extent of the control, so it is the element that answers
            a pointer: the visual target and the real target are now the same shape. The
            negative margin takes the wash out to the card's edges, because a tint that stops
            short of them reads as a second box rather than as a row lighting up. `--sunken`
            flat, which is the ramp's step for a hover — an alpha of it composites to six
            values in light and does nothing. */}
        <h3 className="-mx-4 -my-1 px-4 py-1 transition has-[button:focus-visible]:bg-sunken has-[button:hover]:bg-sunken sm:-mx-5 sm:px-5">
          <button
            type="button"
            ref={disclosure}
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
              <p className="mt-1.5 flex items-center gap-2 text-sm text-ink-2">
                {/* The label is printed right beside it. */}
                <Spinner label="" /> Reading the stored reviews…
              </p>
            ) : citations.failed ? (
              // An explicit unknown outranks an implied one, and "none" is the wrong answer
              // to a question that was not asked successfully.
              <p className="mt-1.5 text-sm text-ink-2">
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
              <p className="mt-1.5 text-sm text-ink-2">
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
                    <span className="text-xs text-ink-2">
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
              <p className="text-xs text-ink-2">
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
    queryKey: ["reviews", "summary"],
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
  /**
   * Whether there is room for the six filters on one line beside the search box.
   *
   * `useIsTabletUp` rather than a class, because below it the filters are a different control
   * and not the same one made narrower — a disclosure with a count, against a row. It is left
   * *uncontrolled* past the first paint: React writes `open` when this value changes and
   * never again, so a reader who opens the disclosure on a phone keeps it open. Holding the
   * state here instead would put a `toggle` event, a set and a second commit between the
   * first paint and the list, which is a re-render bought for nothing.
   */
  const wideEnoughForFilters = useIsTabletUp();
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
  /** How many of the folded filters are narrowing the list, for the summary that hides them. */
  const activeFilters =
    (strength === "all" ? 0 : 1) +
    (scope === "all" ? 0 : 1) +
    (authoredHere ? 1 : 0);

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
   * The blocked decision has to arrive where the press happened.
   *
   * `requestEditor` refuses the switch and renders the prompt below, at the top of a document
   * that is 54 policies and some 8,000 pixels long — so pressing Edit on a policy two thirds
   * down produced no visible change whatsoever. The notice was thousands of pixels above the
   * viewport, the editor was too, and nothing scrolled, focused or announced. The reasonable
   * reading of a press that does nothing is that it did nothing, which is what had people
   * pressing Edit on a second policy and racing two loads.
   *
   * So the prompt comes to the reader: it scrolls itself into view, `role="alert"` on the
   * wrapper says it out loud, and the focus lands on *Keep writing* — the choice that loses
   * nothing, which is the one a person who did not know they were being asked should land on.
   * `preventScroll` so the focus does not fight the alignment the scroll just chose.
   */
  const promptRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!pending) return;
    const node = promptRef.current;
    node?.scrollIntoView?.({ block: "center" });
    node
      ?.querySelector<HTMLButtonElement>("[data-keep-writing]")
      ?.focus({ preventScroll: true });
  }, [pending]);

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
              <Select
                aria-label="Corpus repository"
                value={root ?? ""}
                onChange={(event) => setChosenRoot(event.target.value || null)}
                className={cn(DENSE_SELECT, "max-w-48")}
              >
                <option value="">Workspace only</option>
                {repositories.map((path) => (
                  <option key={path} value={path}>
                    {repositoryName(path)}
                  </option>
                ))}
              </Select>
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
        <div ref={promptRef} role="alert" className="scroll-mt-20">
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
              <Button
                size="sm"
                variant="ghost"
                data-keep-writing=""
                onClick={() => setPending(null)}
              >
                Keep writing
              </Button>
            </div>
          </Notice>
        </div>
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
              back after that padding.

              Pinned *from `lg`*, though. On a phone the coarse-pointer floor makes each of
              the five switches 44px, so the row wrapped to three lines and the bar stood at
              roughly 200px — a third of a 619px viewport, permanently, over the list it exists
              to make scannable. A bar that removes a third of the list is not helping anyone
              scan it. Below `lg` the whole thing scrolls away with the content, and the
              filters fold into the disclosure below. */}
          <div className="-mx-2 mb-3 px-2 py-2 lg:sticky lg:top-12 lg:z-10 lg:bg-canvas">
            <div className="grid gap-2 rounded-lg border border-rule bg-surface p-2 lg:grid-cols-[minmax(0,1fr)_auto]">
              <SearchInput
                label="Search policies"
                value={query}
                onValueChange={setQuery}
                placeholder="Search title, body or tag"
              />
              {/* The search box is the one filter worth a permanent line on a phone, so it
                  stays and the other six fold in. `open` is forced from `lg` up, where there is
                  room for all of them and nothing changes; below it the summary carries how
                  many are on, because a collapsed filter nobody can see is a list narrowed for
                  a reason they cannot read. `lg:contents` dissolves the wrapper back into the
                  grid so the desk layout is the one it always was. */}
              <details open={wideEnoughForFilters} className="group min-w-0 lg:contents">
                <summary className="inline-flex min-h-8 list-none items-center gap-1.5 rounded-sm px-1 text-xs font-semibold text-ink-2 pointer-coarse:min-h-11 lg:hidden [&::-webkit-details-marker]:hidden">
                  Filters
                  {activeFilters ? (
                    <span className="tabular-nums text-ink-3">
                      {activeFilters} on
                    </span>
                  ) : null}
                  <ChevronDown className="size-3.5 text-ink-3 transition group-open:rotate-180" />
                </summary>
                <div className="mt-2 flex flex-wrap items-center gap-3 lg:mt-0">
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
                        // `all` is the reset, and a reset is exempt. The other three are
                        // disabled when they would filter to nothing, which is what the
                        // attribute is for — but `strengthCounts.all` is the corpus after the
                        // search, the scope and the origin have already narrowed it, so it
                        // reaches zero exactly when the list is empty. Pick `required`, type
                        // something that matches nothing, and all four went inert at once
                        // including the one that undoes the choice, while the empty state
                        // below said "widen the strength and scope filters". Pressing `all`
                        // can only ever widen, so it can never filter to nothing.
                        disabled={
                          item !== "all" &&
                          strength !== item &&
                          !strengthCounts[item]
                        }
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
                    <Select
                      aria-label="Filter by scope"
                      value={scope}
                      onChange={(event) =>
                        setScope(event.target.value as (typeof SCOPES)[number])
                      }
                      className={DENSE_SELECT}
                    >
                      {SCOPES.map((item) => (
                        <option key={item} value={item}>
                          {humanise(item)}
                        </option>
                      ))}
                    </Select>
                  </label>
                </div>
              </details>
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
          <p className="text-sm text-ink-2">Loading sources…</p>
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
          <p className="text-sm text-ink-2">
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
          <p className="text-sm leading-6 text-ink-2">
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
