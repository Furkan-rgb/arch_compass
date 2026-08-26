import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import type { ReviewRun } from "../api";

/**
 * A run that finished becomes a review, without a reload.
 *
 * That is what polling the run list was always for, and it did not do it. The list refetched
 * every four seconds and `["reviews"]` was never invalidated when it changed — and with
 * `refetchOnWindowFocus` off, a page left open on a second monitor never refetched anything
 * at all. So a review judged for twenty minutes, the progress row silently vanished, and the
 * review it had produced was not on the page until somebody pressed reload.
 *
 * The signal is the run *leaving* the list. A run is listed until it is genuinely done, so an
 * id that was there a moment ago and is not there now is a run that finished, failed or was
 * cancelled — every one of which changes what `/api/reviews` answers. Both keys are
 * invalidated by prefix, which reaches the summary listings and each open review with them.
 *
 * It lives in `lib/` because three pages poll that list for this reason — the reviews page,
 * the review page and the start page — and a hook one feature imports from another is a
 * dependency between two things that only have the shell in common. Two copies would be two
 * chances to get the shrink test wrong, which is the part that is easy to get wrong: the
 * comparison is against the *previous* set, so it has to survive a render that changes
 * nothing.
 */
/**
 * How often to ask what is running, given what was running last time.
 *
 * It used to be `data?.length ? 4000 : false`, and `false` is a trap: once the list answers
 * empty, nothing re-enables the poll while the reader stays on that route.
 * `refetchOnWindowFocus` is off, and a run started anywhere else — a second tab, the CLI,
 * CI — invalidates nothing here. So sitting on `/reviews` when a run began meant the run
 * never appeared, and because it never appeared it never *left*, so `useRunsBecomeReviews`
 * never fired either: the review it produced was not on the page until somebody reloaded.
 * That is the failure this file's docstring describes, reached from the other direction.
 *
 * Idle is a slow cadence rather than a stopped one. Two 2-byte requests a minute for a
 * workspace with nothing running, and none at all on a hidden tab — React Query's focus
 * manager already stops the timer there, which is measured rather than assumed.
 */
export const runPollInterval = (runs: ReviewRun[] | undefined) => (runs?.length ? 4_000 : 30_000);

export function useRunsBecomeReviews(runs: ReviewRun[] | undefined) {
  const client = useQueryClient();
  const seen = useRef<string[]>([]);
  // Joined and sorted into one string so the effect's dependency is a value rather than an
  // array identity: the query hands back a fresh array on every poll, and depending on it
  // directly would run this every four seconds whether or not anything moved.
  const listed = (runs ?? [])
    .map((run) => run.run_id)
    .sort()
    .join(" ");

  useEffect(() => {
    const current = listed ? listed.split(" ") : [];
    const gone = seen.current.some((id) => !current.includes(id));
    seen.current = current;
    if (!gone) return;
    // By prefix, which is why every review query key begins with one of these two words.
    // The summary listing was fetched under `["review-summaries"]` at four call sites, which
    // no prefix here reaches — so a finished background run refreshed the pages keyed
    // `["reviews", "summary"]` and left the review page's own revision rail stale, which is
    // the exact thing this hook exists to prevent.
    void client.invalidateQueries({ queryKey: ["reviews"] });
    void client.invalidateQueries({ queryKey: ["review"] });
  }, [listed, client]);
}

/**
 * The record this page's own rejudgement produced, once there is one to read.
 *
 * Answering a round does not navigate anywhere, and that is right: it used to jump to the
 * run's address, which swapped the heading, the findings and the surface for a progress list
 * — on a review the reader was already looking at. But staying put was only half the
 * behaviour. The waiting snapshot becomes an *earlier record* the moment its successor is
 * filed, so the reader who answered was left on a page announcing itself as out of date,
 * holding their own question and the verdicts from before their answer, with a link they had
 * to notice and press. The revision they asked for was one click away and nothing took them
 * to it.
 *
 * So the page follows, and only ever its own work. `watched` is set when a rejudgement of
 * *this* record is seen running, which means a reader who opened an old record from the rail
 * is never carried off it: nothing was watched, so nothing is followed. A run is listed until
 * it is genuinely done, so leaving the list is the signal — the same one `useRunsBecomeReviews`
 * reads, and for the same reason its docstring gives.
 *
 * Two steps rather than one, because the successor does not exist at the moment the run ends.
 * The run leaving invalidates the review, the review comes back carrying `superseded_by`, and
 * only then is there an address to go to. Both halves are state rather than refs so the
 * second reacts to the first.
 */
export function useRecordToFollow(
  review: { id: string; superseded_by?: string | null } | undefined,
  rejudging: ReviewRun | null,
  inFlight: readonly ReviewRun[] | undefined,
): string | null {
  const [watched, setWatched] = useState<string | null>(null);
  const [ended, setEnded] = useState(false);
  const listed = (inFlight ?? [])
    .map((run) => run.run_id)
    .sort()
    .join(" ");

  useEffect(() => {
    if (rejudging && rejudging.status === "running") {
      setWatched(rejudging.run_id);
      setEnded(false);
      return;
    }
    // `undefined` is the list not having answered yet, which is not an absence — reading it
    // as one would follow before anything had run.
    if (!watched || inFlight === undefined) return;
    if (!listed.split(" ").filter(Boolean).includes(watched)) setEnded(true);
  }, [rejudging, listed, inFlight, watched]);

  if (!ended || !watched) return null;
  const next = review?.superseded_by;
  // Never itself: a successor that is this record is not a successor, and navigating to it
  // would be a loop the reader cannot leave.
  return next && next !== review?.id ? next : null;
}
