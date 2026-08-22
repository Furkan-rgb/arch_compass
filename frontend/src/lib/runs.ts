import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import type { ReviewRun } from "../api";

/**
 * A run that finished becomes a review, without a reload.
 *
 * That is what polling the run list was always for, and it did not do it. The list refetched
 * every four seconds and `["reviews"]` was never invalidated when it changed — and with
 * `refetchOnWindowFocus` off, a page left open on a second monitor never refetched anything
 * at all. So a batch judged for twenty minutes, the progress row silently vanished, and the
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
    void client.invalidateQueries({ queryKey: ["reviews"] });
    void client.invalidateQueries({ queryKey: ["review"] });
  }, [listed, client]);
}
