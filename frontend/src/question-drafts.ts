import { useCallback, useEffect, useState } from "react";

/**
 * What a reader has typed against a review's questions, kept where a reload cannot reach.
 *
 * The answers to a review's open questions are the highest-effort input in this product: each
 * one is a sentence about the reader's own project that nothing else in the workspace knows,
 * written in the one place where the review has stopped and is waiting for a person. They were
 * held in component state alone, so the ordinary things a reader does while working out an
 * answer — open the repository in another tab, follow a citation, reload a page that has been
 * sitting open — threw away everything they had written, silently and with no way back.
 *
 * A draft is therefore stored as it is typed, and the storage is the reason there is no
 * navigation blocker anywhere near this. A blocker interrupts the reader to protect work that
 * is no longer at risk, and the interruption is itself the cost: leaving is not the danger,
 * losing what was written is, and that is what this removes.
 *
 * Two kinds of writing are kept, under separate keys. An answer is what may enter the case; a
 * question put to the advisor is not, and running them together would put words the reader
 * asked *about* their answer into the box that becomes it.
 *
 * Nothing here is authoritative. A draft is a copy of what is on screen, dropped the moment the
 * workspace has recorded the real thing, and every path through this module treats storage as
 * something that may simply not be there: a browser in private mode can refuse `localStorage`
 * outright, either by throwing on access or on write, and the honest response is the behaviour
 * this product had before drafts existed rather than an error about a feature nobody asked for.
 */

/** Answers on their way to the case: one map per review, keyed by question reference. */
export const ANSWER_DRAFTS = "archcompass.answer-drafts";

/** Questions put to the advisor about a question. Never recorded, and never a case entry. */
export const DISCUSSION_DRAFTS = "archcompass.discussion-drafts";

export type DraftKind = typeof ANSWER_DRAFTS | typeof DISCUSSION_DRAFTS;

/** What the reader has written, by the question it is written against. */
export type QuestionDrafts = Record<string, string>;

/**
 * One key per review, holding every question's draft as a map.
 *
 * The review is in the key rather than in the value because a review is the unit that is
 * finished and forgotten: when its answers are recorded there is exactly one thing to remove.
 * The question reference is inside the map because it is only stable *within* a review — `Q-1`
 * is the first question of whichever review asked it.
 */
export function draftKey(kind: DraftKind, reviewId: string): string {
  return `${kind}.${reviewId}`;
}

/**
 * The store, or nothing at all.
 *
 * Reading `window.localStorage` is itself the throwing part in a browser that has disabled it,
 * so the access is inside the guard rather than the calls that follow it.
 */
function store(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** Everything stored for one review, and an empty map wherever that cannot be answered. */
export function storedDrafts(kind: DraftKind, reviewId: string): QuestionDrafts {
  const storage = store();
  if (!storage) return {};
  let raw: string | null = null;
  try {
    raw = storage.getItem(draftKey(kind, reviewId));
  } catch {
    return {};
  }
  if (!raw) return {};
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    // Filtered rather than trusted. This value survives a deploy, so a shape this module wrote
    // a version ago — or a key another tab wrote by hand — must not reach a textarea as
    // `[object Object]`. Anything that is not text for a question is simply not a draft.
    return Object.fromEntries(
      Object.entries(parsed as Record<string, unknown>).filter(
        (entry): entry is [string, string] => typeof entry[1] === "string",
      ),
    );
  } catch {
    return {};
  }
}

/**
 * Replace what is stored for one review.
 *
 * Blank drafts are not stored, and a review with nothing left drops its key entirely: an empty
 * map read back is indistinguishable from no map, and leaving one behind would keep a row per
 * review a reader once opened for as long as the browser lives.
 */
export function saveDrafts(
  kind: DraftKind,
  reviewId: string,
  drafts: QuestionDrafts,
): void {
  const storage = store();
  if (!storage) return;
  const written = Object.entries(drafts).filter(([, text]) => text.trim());
  try {
    if (written.length === 0) storage.removeItem(draftKey(kind, reviewId));
    else storage.setItem(draftKey(kind, reviewId), JSON.stringify(Object.fromEntries(written)));
  } catch {
    // A refused write is a reload that loses the draft, which is exactly where this feature
    // started. It is not something to report: the reader is mid-sentence, and an error about
    // the copy would be about a mechanism they never asked for.
  }
}

/**
 * Whether this browser will actually hold a draft, asked before anything says that it will.
 *
 * A probe rather than a check for the object, because the two ways storage is refused look
 * nothing alike: one throws on the way in and the other accepts every call and keeps nothing.
 * Only a write that comes back can tell them apart, and the difference decides whether a
 * sentence promising the reader their words will still be here is true — which is the whole
 * reason this is exported. Copy that says work is kept, in a window where it is not, is worse
 * than saying nothing at all.
 */
export function draftsAreKept(): boolean {
  const storage = store();
  if (!storage) return false;
  // Its own key, outside both namespaces, because this one is written to be deleted: a probe
  // under a draft's key would be a review whose id happened to match losing its answers.
  const probe = "archcompass.drafts-probe";
  try {
    storage.setItem(probe, "1");
    storage.removeItem(probe);
    return true;
  } catch {
    return false;
  }
}

/** Forget the drafts for questions whose answers the workspace has recorded. */
export function dropDrafts(
  kind: DraftKind,
  reviewId: string,
  references: string[],
): void {
  const remaining = storedDrafts(kind, reviewId);
  for (const reference of references) delete remaining[reference];
  saveDrafts(kind, reviewId, remaining);
}

/**
 * A review's drafts as state, restored on the way in and written as they change.
 *
 * The review the drafts belong to is held *beside* them, and a change of review re-reads rather
 * than carries over. The review's page swaps one review for another under a mounted tree — that
 * is what starting a second pass does — so drafts that merely persisted across the swap would be
 * one reader's answers about one review saved under the key of another.
 *
 * Written on every keystroke, which is affordable here and would not be everywhere: this is a
 * few hundred bytes of JSON at the speed a person types prose, not the sixty writes a second a
 * dragged edge would cost.
 */
export function useQuestionDrafts(
  kind: DraftKind,
  reviewId: string,
): [QuestionDrafts, (next: (existing: QuestionDrafts) => QuestionDrafts) => void] {
  const [held, setHeld] = useState(() => ({
    of: reviewId,
    drafts: storedDrafts(kind, reviewId),
  }));
  // Adjusted during the render that noticed, not in an effect: an effect would let one frame of
  // the previous review's answers reach the boxes, and — worse — let the write below run once
  // with the old drafts under the new review's key.
  if (held.of !== reviewId) {
    setHeld({ of: reviewId, drafts: storedDrafts(kind, reviewId) });
  }
  const drafts = held.of === reviewId ? held.drafts : {};

  useEffect(() => {
    saveDrafts(kind, reviewId, drafts);
  }, [kind, reviewId, drafts]);

  const update = useCallback(
    (next: (existing: QuestionDrafts) => QuestionDrafts) =>
      setHeld((current) => ({ of: current.of, drafts: next(current.drafts) })),
    [],
  );

  return [drafts, update];
}
