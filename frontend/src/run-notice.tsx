import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { Button } from "@/components/ui/button";

/**
 * What a run says about itself from outside the page it is drawn on.
 *
 * A review is minutes of model calls, and the only place that ever said so was the page
 * watching it. That is the wrong place for the two moments that matter: a run finishes, or
 * stops on questions it cannot weigh, and by then the reader is reasonably on another tab or
 * another route — so the one thing they were waiting for arrived in silence, and the tool
 * looked like it had hung until they went back and checked.
 *
 * So there are three signals and each answers a different question the reader is actually in
 * a position to ask. The title answers "is it still going?" from the tab strip. The favicon
 * answers "is there something for me?" from a tab whose title is truncated to eight
 * characters, which is what a real tab strip does. The toast answers "where?" — it is the only
 * one of the three that can carry a link, and it is the only one that has to know where the
 * reader already is.
 *
 * Nothing here invents a fact. There is no count, no elapsed time and no case name, because
 * the run's holder has none of those at the moment the run ends: it has a status and an
 * identifier. What the signals say is exactly what that supports.
 *
 * The decisions are pure functions and the effects are one component, for the reason
 * `ask-panel-width.ts` is split the way it is: the parts that can be wrong here are wrong in a
 * way you only find by being away from the screen. A title that stays "Reviewing…" after a run
 * ended, or a toast that fires on the page it is announcing, are both invisible on the machine
 * they were written on.
 */

/** The title with nothing to add to it. Also what a stale one is restored to. */
export const PRODUCT_TITLE = "Arch Compass";

/**
 * A run as the signals see it: in flight, or over in one of three ways.
 *
 * The three settled phases are the stream's own outcomes and not a new state machine — a run
 * either concluded (`succeeded`), stopped for answers (`awaiting_answers`), or reached no
 * verdicts at all. `run.tsx` maps the review it is handed onto them and nothing else does.
 */
export type RunPhase = "running" | "concluded" | "holding" | "failed";

/** A phase a run does not leave on its own. */
export type SettledPhase = Exclude<RunPhase, "running">;

export function isSettled(phase: RunPhase | null): phase is SettledPhase {
  return phase !== null && phase !== "running";
}

/**
 * The prefix a settled run wears in the tab strip, and the sentence its notice leads with.
 *
 * Deliberately flat and deliberately not punctuated with anything: a tab title is read out of
 * the corner of an eye, at whatever width the strip has left, so the informative word goes
 * first — "Questions", "Review" — and no glyph stands in for a word. `failed` says failed
 * rather than softening it; a run that reached no verdicts is not a result.
 */
const TITLE_PREFIX: Record<SettledPhase, string> = {
  concluded: "Review ready",
  holding: "Questions waiting",
  failed: "Review failed",
};

/**
 * The document title for a phase.
 *
 * Two rules, and the second is the one worth stating. A run in flight always says so: that is
 * a fact about the tab whether the reader is looking at it or not, and it is the answer to
 * "did I actually start it?". A *settled* run only says so while its attention is still
 * pending — which is to say, while it ended somewhere the reader could not see it and they
 * have not come back yet. Once they are here, the page in front of them is a better statement
 * of what happened than four words in a tab, and the title goes quiet again.
 *
 * The prefix leads because that is the half of a title a narrow tab keeps.
 */
export function documentTitle(phase: RunPhase | null, attentionPending: boolean): string {
  if (phase === "running") return `Reviewing… · ${PRODUCT_TITLE}`;
  if (isSettled(phase) && attentionPending) {
    return `${TITLE_PREFIX[phase]} · ${PRODUCT_TITLE}`;
  }
  return PRODUCT_TITLE;
}

export const FAVICON_HREF = "/favicon.svg";
export const FAVICON_ATTENTION_HREF = "/favicon-attention.svg";

/**
 * Move the tab's icon onto the badged mark, or back off it.
 *
 * Takes the document so a test can prove the href it lands on rather than the effect that
 * wrote it. A document with no declared icon is left alone: index.html declares one, and a
 * host that has stripped it has said something about what it wants in that slot.
 */
export function applyFavicon(doc: Document, attentionPending: boolean): void {
  const link = doc.querySelector<HTMLLinkElement>('link[rel="icon"]');
  if (!link) return;
  link.setAttribute("href", attentionPending ? FAVICON_ATTENTION_HREF : FAVICON_HREF);
}

/** Where the review a run produced is read. */
export function reviewPath(reviewId: string): string {
  return `/reviews/${reviewId}`;
}

/**
 * Whether the end of this run is news.
 *
 * Two ways it is not. The reader is already on the review's own page, where the run's stages,
 * its hold banner and its verdicts are all drawn live — a floating card repeating any of that
 * would be the same fact twice, one of them in the way. Or the run failed before the stream
 * ever named a review, in which case there is no page to send anyone to: nothing navigated,
 * so the reader is still on the start step, and the start step draws the failure itself.
 *
 * Compared against `pathname` rather than a route match because the review page has no nested
 * routes — its tabs are state, not URLs — so the path is the whole of the question.
 */
export function shouldNotice(
  phase: RunPhase | null,
  reviewId: string | null,
  pathname: string,
): boolean {
  if (!isSettled(phase)) return false;
  if (reviewId === null) return false;
  return pathname !== reviewPath(reviewId);
}

/** What the notice says, in the product's own words rather than a status name. */
const NOTICE_COPY: Record<SettledPhase, { heading: string; sentence: string; action: string }> = {
  concluded: {
    heading: "The review has finished",
    sentence: "Every boundary was judged and the verdicts are in.",
    action: "Read the review",
  },
  holding: {
    heading: "The review is holding",
    sentence:
      "It judged every boundary and stopped on questions it could not weigh from the code " +
      "alone. It resumes once they are answered.",
    action: "Answer the questions",
  },
  failed: {
    heading: "The review did not finish",
    sentence: "It stopped before reaching any verdicts. Its page says where it got to.",
    action: "Open the review",
  },
};

/** How long a notice stays, once there is someone here to read it. */
export const NOTICE_LIFETIME_MS = 12_000;

/**
 * The whole signalling layer, mounted once above the routes.
 *
 * It draws nothing while a run is in flight — the tab title is doing that job, and a card
 * that sat on screen for the length of a multi-minute run would be furniture rather than
 * news.
 */
export function RunSignals({
  phase,
  reviewId,
}: {
  phase: RunPhase | null;
  /** The review this run is producing, once the stream has named it. */
  reviewId: string | null;
}) {
  const { pathname } = useLocation();
  /**
   * A run ended somewhere the reader could not see it, and they have not been back since.
   *
   * Latched at the transition rather than derived, because it is a fact about a moment: the
   * question is whether the tab was hidden *when the run ended*, and by the time anything
   * reads this the answer to "is the tab hidden" may have changed twice.
   */
  const [attentionPending, setAttentionPending] = useState(false);
  const [notice, setNotice] = useState<{ phase: SettledPhase; reviewId: string } | null>(null);

  // Keyed on the phase alone, and that is the point rather than an omission: this reacts to a
  // run *changing* phase, and the pathname it reads is the one that was on screen at the
  // moment it changed. Adding pathname to the deps would re-run the whole decision on every
  // navigation and re-raise a notice the reader had already dismissed.
  useEffect(() => {
    if (!isSettled(phase)) {
      // A new run, or none. Whatever the last one left behind is no longer about anything.
      setAttentionPending(false);
      setNotice(null);
      return;
    }
    if (document.visibilityState === "hidden") setAttentionPending(true);
    if (reviewId !== null && shouldNotice(phase, reviewId, pathname)) {
      setNotice({ phase, reviewId });
    }
  }, [phase]);

  // Coming back is what clears it, and there are two ways to come back that a browser reports
  // separately: switching to the tab, and focusing a window that was never hidden but was
  // behind another application. Both are listened for; whichever fires first wins.
  useEffect(() => {
    if (!attentionPending) return;
    const clear = () => {
      if (document.visibilityState === "visible") setAttentionPending(false);
    };
    document.addEventListener("visibilitychange", clear);
    window.addEventListener("focus", clear);
    return () => {
      document.removeEventListener("visibilitychange", clear);
      window.removeEventListener("focus", clear);
    };
  }, [attentionPending]);

  // The cleanup is not tidiness. This component is above the routes and lives as long as the
  // app does, so the only thing that unmounts it is the app going away — and a title left
  // saying "Reviewing…" would outlive the run it described in every browser session restore.
  useEffect(() => {
    document.title = documentTitle(phase, attentionPending);
    return () => {
      document.title = PRODUCT_TITLE;
    };
  }, [phase, attentionPending]);

  useEffect(() => {
    applyFavicon(document, attentionPending);
    return () => applyFavicon(document, false);
  }, [attentionPending]);

  /*
    The countdown only runs while someone is here to see it.

    A notice raised against a hidden tab would otherwise spend its whole life unread and be
    gone before the reader came back — which is the exact failure this module exists to fix,
    reintroduced by a timer. So the clock starts when the tab is visible and is re-armed each
    time visibility changes.
  */
  useEffect(() => {
    if (!notice) return;
    let timer: number | undefined;
    const arm = () => {
      window.clearTimeout(timer);
      if (document.visibilityState !== "visible") return;
      timer = window.setTimeout(() => setNotice(null), NOTICE_LIFETIME_MS);
    };
    arm();
    document.addEventListener("visibilitychange", arm);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", arm);
    };
  }, [notice]);

  const copy = notice ? NOTICE_COPY[notice.phase] : null;

  return (
    // The region is always mounted and always polite: a live region announces what is inserted
    // into it, so one that appears alongside its own content has nothing to announce. It never
    // takes the pointer — only the card inside it does — or it would be an invisible sheet of
    // glass over the bottom corner of every page.
    <div
      data-slot="run-notices"
      aria-live="polite"
      className="pointer-events-none fixed right-[var(--gutter)] bottom-[var(--gutter)] z-40 flex max-w-[calc(100vw_-_2*var(--gutter))] flex-col items-end"
    >
      {notice && copy ? (
        // The floating panel this design already has: the sheet's radius and surface, the
        // border that is nothing by day and a hairline by night, and the depth reserved for
        // things that are over the page rather than on it.
        <div
          data-slot="run-notice"
          className="run-notice pointer-events-auto grid w-[360px] max-w-full gap-1.5 rounded-panel [border:var(--sheet-border)] bg-surface p-[var(--card-pad)] shadow-float"
        >
          <div className="flex items-start gap-3">
            <b className="flex-1 text-ui leading-[1.4] font-[650] text-ink">{copy.heading}</b>
            <Button
              type="button"
              size="icon"
              className="-mt-1 -mr-1.5 size-7 flex-none border-0 bg-transparent"
              onClick={() => setNotice(null)}
            >
              <X size={14} aria-hidden />
              <span className="sr-only">Dismiss this notice</span>
            </Button>
          </div>
          <p className="m-0 text-meta leading-[1.55] text-ink-2">{copy.sentence}</p>
          {/* The action is the whole reason a card is used here rather than a third
              wordless signal: it is the only one of the three that can say where. */}
          <Link
            to={reviewPath(notice.reviewId)}
            onClick={() => setNotice(null)}
            className="justify-self-start text-meta font-medium text-accent-ink hover:underline"
          >
            {copy.action}
          </Link>
        </div>
      ) : null}
    </div>
  );
}
