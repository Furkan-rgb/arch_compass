/**
 * Triage: what the team makes of a verdict, recorded where the verdict is read.
 *
 * Everything here is deliberately ink rather than colour. The verdict families — material,
 * cleared — belong to the model's judgement, and a page where the team's opinion wore the
 * same colours would blur the one line this product will not blur: the model judges, the
 * team disposes. A decision is therefore typography — small caps, the author's name, a
 * date, a reason — and the only time triage raises its voice is when the ground moved
 * under a decision, which is a fact about honesty rather than about judgement.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquareText } from "lucide-react";
import { useState } from "react";

import { api } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { formatDate, phoneFlush } from "@/components";
import { cn } from "@/lib/utils";
import type {
  BoundaryTriage,
  DecisionState,
  ReviewedBoundary,
} from "@/types";

/** The last name decisions and remarks were signed with, kept on this browser.
    Self-report, honestly labelled: there is no identity here yet, only a field that
    remembers what it was told. */
const AUTHOR_KEY = "archcompass.triage.author";

export function rememberedAuthor(): string {
  try {
    return localStorage.getItem(AUTHOR_KEY) ?? "";
  } catch {
    return "";
  }
}

function rememberAuthor(name: string) {
  try {
    localStorage.setItem(AUTHOR_KEY, name);
  } catch {
    // A browser that refuses storage refuses the convenience, not the decision.
  }
}

const STATE_WORDS: Record<DecisionState, string> = {
  accepted: "Accepted",
  waived: "Waived",
  parked: "Parked",
};

/** What each state claims, spelled out where the choice is made rather than in a doc. */
const STATE_MEANINGS: Record<DecisionState, string> = {
  accepted: "We agree with this verdict and intend to act on it.",
  waived: "We disagree, or accept the debt. Says why, and stands until re-affirmed.",
  parked: "Seen, undecided. Keeps the boundary from reading as unreviewed.",
};

/**
 * The decision mark a collapsed row carries: one word of small caps, or nothing.
 *
 * Nothing is the design — an unreviewed boundary is silent, so the ledger reads exactly
 * like it did before triage existed until somebody decides something. The one exception
 * to quiet: a decision taken against a verdict this run no longer gives is underlined in
 * the material hue, because inherited approval of a moved verdict is the one lie this
 * mark could otherwise tell.
 */
export function DecisionMark({ triage }: { triage: BoundaryTriage | undefined }) {
  const decision = triage?.decision;
  if (!decision) return null;
  const stale = !decision.taken_on_current_verdict;
  return (
    // A label, cut like the verdict chips beside it but in the team's neutral ink — the
    // two layers stay tellable apart by hue while reading as one vocabulary of stamps.
    // A decision taken against an earlier verdict wears a dashed warning edge: it is
    // still the team's word, and the dashes say the ground under it moved.
    <Badge
      variant="neutral"
      className={cn(
        "font-[650] tracking-[.05em] uppercase",
        stale && "border-dashed border-danger-rule text-material",
      )}
      title={
        stale
          ? `${STATE_WORDS[decision.state]} by ${decision.author} — against an earlier verdict. Review again.`
          : `${STATE_WORDS[decision.state]} by ${decision.author}`
      }
    >
      {STATE_WORDS[decision.state]}
    </Badge>
  );
}

/**
 * The standing footer of an open row: the decision as it stands, the control to change
 * it, and the discussion under both.
 *
 * Lives at the bottom of the detail on purpose — the verdict, its reasoning and its
 * evidence come first, and what the team made of them is read after them, the way a
 * signature follows a letter.
 */
export function StandingFooter({
  boundary,
  triage,
  branchId,
  reviewId,
}: {
  boundary: ReviewedBoundary;
  triage: BoundaryTriage | undefined;
  /** Absent on a review from before branch lineages: with no branch there is nothing to
      file a decision under, and the footer says so instead of guessing. */
  branchId: string | null;
  reviewId: string;
}) {
  const client = useQueryClient();
  const decision = triage?.decision ?? null;
  const [state, setState] = useState<DecisionState | "">("");
  const [author, setAuthor] = useState(rememberedAuthor);
  const [reason, setReason] = useState("");

  const decide = useMutation({
    mutationFn: (next: DecisionState) => {
      if (!branchId || !triage) throw new Error("This boundary has no branch to decide on.");
      rememberAuthor(author.trim());
      return api.postDecision({
        branch_id: branchId,
        boundary_fingerprint: triage.fingerprint,
        state: next,
        author: author.trim(),
        reason: reason.trim() ? reason.trim() : null,
        review_id: reviewId,
        boundary_reference: boundary.reference,
        material: boundary.material,
        verdict_label: boundary.verdict_label,
      });
    },
    onSuccess: async () => {
      setState("");
      setReason("");
      await client.invalidateQueries({ queryKey: ["review", reviewId] });
    },
  });

  if (!branchId) {
    return (
      <div data-slot="standing" className="mt-4">
        <p className={triageSubhead}>Standing</p>
        <p className="max-w-[78ch] text-meta leading-[1.5] text-ink-3">
          This review predates branch lineages, so there is no branch to record a decision
          on. Re-index the repository and run a new review to triage its boundaries.
        </p>
      </div>
    );
  }

  const needsReason = state === "waived" && !reason.trim();
  const ready = state !== "" && author.trim() !== "" && !needsReason;

  return (
    <div data-slot="standing" className="mt-4">
      <p className={triageSubhead}>Standing</p>

      {decision ? (
        <p className="mb-3 max-w-[78ch] text-ui leading-[1.6] text-ink-2">
          <strong className="text-ink">
            {STATE_WORDS[decision.state]} by {decision.author}
          </strong>{" "}
          · {formatDate(decision.decided_at)}
          {decision.reason ? <> — {decision.reason}</> : null}
          {!decision.taken_on_current_verdict ? (
            <span className="mt-1 block border-l-2 border-material pl-3 text-material">
              Decided against an earlier verdict — the run in front of you says something
              different. Review it again; re-affirming is a human act.
            </span>
          ) : null}
        </p>
      ) : (
        <p className="mb-3 max-w-[78ch] text-ui text-ink-3">
          Nobody has decided anything about this boundary yet.
        </p>
      )}

      <div className="flex max-w-[78ch] flex-wrap items-center gap-2">
        <ToggleGroup
          type="single"
          value={state}
          onValueChange={(value) => setState(value as DecisionState | "")}
          aria-label="Disposition"
        >
          {(Object.keys(STATE_WORDS) as DecisionState[]).map((key) => (
            <ToggleGroupItem key={key} value={key} title={STATE_MEANINGS[key]}>
              {key === "accepted" ? "Accept" : key === "waived" ? "Waive" : "Park"}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <Input
          value={author}
          onChange={(event) => setAuthor(event.target.value)}
          placeholder="Your name"
          aria-label="Decided by"
          className="w-40"
        />
        <Button
          type="button"
          disabled={!ready || decide.isPending}
          onClick={() => state && decide.mutate(state)}
        >
          {decide.isPending ? "Recording…" : decision ? "Change decision" : "Record"}
        </Button>
      </div>

      {state ? (
        <div className="mt-2 max-w-[78ch]">
          <Textarea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            rows={2}
            placeholder={
              state === "waived"
                ? "Why this verdict does not bind — a waiver without a reason is refused."
                : "Why, for whoever reads this later. Optional."
            }
            aria-label="Reason"
            aria-required={state === "waived"}
          />
          {needsReason ? (
            <p className="mt-1 text-meta text-ink-3">A waiver has to say why.</p>
          ) : null}
        </div>
      ) : null}
      {decide.isError ? (
        <p role="alert" className="mt-2 max-w-[78ch] text-meta text-material">
          {decide.error instanceof Error
            ? decide.error.message
            : "The decision was not recorded."}
        </p>
      ) : null}

      <Discussion
        branchId={branchId}
        fingerprint={triage?.fingerprint ?? null}
        count={triage?.comment_count ?? 0}
        reviewId={reviewId}
        author={author}
        onAuthor={setAuthor}
      />
    </div>
  );
}

/* The same small-caps rule every other section of a row detail draws over itself. */
const triageSubhead =
  "mt-0 mb-2 flex items-center gap-2 text-micro font-[650] tracking-[.09em] text-ink-3 uppercase after:h-px after:flex-1 after:bg-rule-soft after:content-['']";

/**
 * The append-only thread under a decision — or under nothing, because argument is
 * allowed to precede any decision. Closed by default and loaded only when opened: most
 * boundaries are never discussed, and a page that fetched every empty thread would ask
 * the workspace dozens of questions to learn silence.
 */
function Discussion({
  branchId,
  fingerprint,
  count,
  reviewId,
  author,
  onAuthor,
}: {
  branchId: string;
  fingerprint: string | null;
  count: number;
  reviewId: string;
  author: string;
  onAuthor: (name: string) => void;
}) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [remark, setRemark] = useState("");

  const thread = useQuery({
    queryKey: ["decision-comments", branchId, fingerprint],
    queryFn: () => api.decisionComments(branchId, fingerprint!),
    enabled: open && Boolean(fingerprint),
  });

  const post = useMutation({
    mutationFn: () => {
      rememberAuthor(author.trim());
      return api.postDecisionComment(branchId, fingerprint!, {
        author: author.trim(),
        body: remark.trim(),
      });
    },
    onSuccess: async () => {
      setRemark("");
      await Promise.all([
        client.invalidateQueries({ queryKey: ["decision-comments", branchId, fingerprint] }),
        client.invalidateQueries({ queryKey: ["review", reviewId] }),
      ]);
    },
  });

  if (!fingerprint) return null;
  const comments = thread.data ?? [];

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="mt-3 max-w-[78ch]">
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="inline-flex cursor-pointer items-center gap-1.5 border-0 bg-transparent p-0 text-ui text-accent-ink hover:underline"
        >
          <MessageSquareText size={14} aria-hidden />
          {count > 0
            ? `Discussion — ${count} ${count === 1 ? "remark" : "remarks"}`
            : "Discuss this boundary"}
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-2">
        {thread.isPending && open ? (
          <p className="text-meta text-ink-3">Opening the thread…</p>
        ) : (
          <ul aria-live="polite" className="m-0 flex list-none flex-col gap-2 p-0">
            {comments.map((comment) => (
              <li
                key={comment.comment_id}
                className="rounded-control [border:var(--sheet-border)] bg-sunken px-3.5 py-2.5"
              >
                <p className="m-0 text-micro font-[650] tracking-[.05em] text-ink-3 uppercase">
                  {comment.author} · {formatDate(comment.created_at)}
                </p>
                <p className="m-0 mt-1 text-ui leading-[1.55] text-ink-2">{comment.body}</p>
              </li>
            ))}
            {comments.length === 0 && !thread.isPending ? (
              <li className="text-meta text-ink-3">
                Nothing yet. Remarks are permanent — the thread is a history, not a
                document.
              </li>
            ) : null}
          </ul>
        )}
        <div className="mt-2 flex flex-wrap items-start gap-2">
          <Input
            value={author}
            onChange={(event) => onAuthor(event.target.value)}
            placeholder="Your name"
            aria-label="Remark author"
            className="w-40"
          />
          <Textarea
            value={remark}
            onChange={(event) => setRemark(event.target.value)}
            rows={1}
            placeholder="Say it here rather than in a channel that forgets."
            aria-label="Remark"
            className="min-w-56 flex-1"
          />
          <Button
            type="button"
            disabled={!author.trim() || !remark.trim() || post.isPending}
            onClick={() => post.mutate()}
          >
            {post.isPending ? "Adding…" : "Add remark"}
          </Button>
        </div>
        {post.isError ? (
          <p role="alert" className="mt-2 text-meta text-material">
            {post.error instanceof Error ? post.error.message : "The remark was not added."}
          </p>
        ) : null}
      </CollapsibleContent>
    </Collapsible>
  );
}

/**
 * One decision over everything still undecided — the gesture that adopts a repository.
 *
 * The bulk baseline used to do this with a button that silenced boundaries nobody looked
 * at; this reaches the same quiet with an author and one recorded decision per boundary,
 * which is the difference between silence and sign-off. Offered only when there is a
 * plural to decide: a single boundary has its own footer, and a bar restating it would
 * be furniture.
 */
export function BulkDecide({
  boundaries,
  branchId,
  reviewId,
}: {
  /** The undecided material boundaries this would decide, with their fingerprints. */
  boundaries: ReviewedBoundary[];
  branchId: string;
  reviewId: string;
}) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<DecisionState | "">("");
  const [author, setAuthor] = useState(rememberedAuthor);
  const [reason, setReason] = useState("");
  const decide = useMutation({
    mutationFn: () => {
      if (!state) throw new Error("Choose what the decision is first.");
      rememberAuthor(author.trim());
      return api.postBulkDecisions({
        branch_id: branchId,
        state,
        author: author.trim(),
        reason: reason.trim() ? reason.trim() : null,
        review_id: reviewId,
        boundaries: boundaries
          .filter((item) => item.fingerprint)
          .map((item) => ({
            boundary_fingerprint: item.fingerprint!,
            boundary_reference: item.reference,
            material: item.material,
            verdict_label: item.verdict_label,
          })),
      });
    },
    onSuccess: async () => {
      setOpen(false);
      setState("");
      setReason("");
      await client.invalidateQueries({ queryKey: ["review", reviewId] });
    },
  });
  const ready =
    state !== "" && author.trim() !== "" && (state !== "waived" || reason.trim() !== "");

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <div className={cn("mb-4 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-panel [border:var(--sheet-border)] bg-surface px-[var(--row-pad-x)] py-3", phoneFlush)}>
        <p className="m-0 text-ui text-ink-2">
          <strong className="text-ink">{boundaries.length} boundaries</strong> are material
          with no standing decision. Deciding them is what makes the next revision quiet.
        </p>
        <DialogTrigger asChild>
          <Button type="button" className="ml-auto">
            Decide all {boundaries.length}…
          </Button>
        </DialogTrigger>
      </div>
      <DialogContent className="max-w-[520px]">
        <DialogHeader>
          <DialogTitle>One decision, {boundaries.length} boundaries</DialogTitle>
          <DialogDescription>
            Each gets its own recorded decision under your name — the same standing a
            one-at-a-time decision has, and each can be revisited individually later.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          <ToggleGroup
            type="single"
            value={state}
            onValueChange={(next) => setState((next as DecisionState) || "")}
            aria-label="The decision"
          >
            <ToggleGroupItem value="accepted">Accept</ToggleGroupItem>
            <ToggleGroupItem value="waived">Waive</ToggleGroupItem>
            <ToggleGroupItem value="parked">Park</ToggleGroupItem>
          </ToggleGroup>
          <Input
            value={author}
            onChange={(event) => setAuthor(event.target.value)}
            placeholder="Your name"
            aria-label="Author"
          />
          <Textarea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder={
              state === "waived" ? "Why this debt is being waived — required" : "Reason (optional)"
            }
            aria-label="Reason"
          />
          {decide.error instanceof Error ? (
            <p role="alert" className="m-0 text-meta text-material">
              {decide.error.message}
            </p>
          ) : null}
          <div className="flex justify-end border-t border-rule-soft pt-3">
            <Button
              type="button"
              variant="primary"
              disabled={!ready || decide.isPending}
              onClick={() => decide.mutate()}
            >
              {decide.isPending ? (
                <>
                  <Spinner /> Recording…
                </>
              ) : (
                `Record ${boundaries.length} decisions`
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
