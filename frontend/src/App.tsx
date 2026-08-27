import { Suspense, lazy, useEffect, useRef } from "react";
import { Route, Routes, useLocation } from "react-router-dom";

import { AppShell, pageName } from "./app/shell";
import { ErrorBoundary } from "./app/error-boundary";
import { CasesPage } from "./features/cases/cases-page";
import { LandingPage } from "./features/landing/landing-page";
import { RepositoriesPage } from "./features/repositories/repositories-page";
import { ReviewsPage } from "./features/reviews/reviews-page";
import { SettingsPage } from "./features/settings/settings-page";
import { RunPage } from "./features/start/run-page";
import { StartPage } from "./features/start/start-page";
import { ButtonLink } from "./ui/button";
import { EmptyState, LoadingPanel } from "./ui/states";

/**
 * Every screen is in the entry bundle, except the two that are doors to a large dependency.
 *
 * The routes used to be eight `lazy()` sites, and the split cost more than it bought. A
 * document holds the hashed filenames of the build it was served by, so a navigation after a
 * rebuild fetches a name that no longer exists — a screen the reader merely walked to,
 * dead-ending on an error boundary. What the split was buying is small: the eight route
 * chunks plus `report-surface` and `exhibit` come to 302,570 bytes, and folding six of the
 * eight in takes the entry chunk from 440,848 bytes to 528,204. (Both from `stat` over the
 * emitted chunks: this tree as it stands, and this tree with the eight routes put back behind
 * `lazy()` and built into a scratch `--outDir`. An earlier revision of this comment said
 * 316,164 for the first figure and cited `vite build`'s report for it; the number was an
 * estimate re-presented as a measurement and does not reproduce.) The workbench is served
 * from `127.0.0.1` by the workspace process, so fetching those bytes at navigation time
 * rather than at load is a local file read either way. It bought no measurable latency and it
 * paid for it with a failure class.
 *
 * The two exceptions are not routes that are large; they are routes that *reach* something
 * large, and each is the only path to it:
 *
 * - `ReviewPage` reaches the syntax highlighter — 58,878 bytes of `highlight.js` grammars —
 *   through `docket.tsx` to `finding-detail.tsx` to the `EvidenceBlock` it renders.
 * - `PoliciesPage` reaches the Markdown renderer — 162,130 bytes, which pulls the highlighter
 *   under it — because a policy body is authored Markdown and the page shows it rendered.
 *
 * Folding those two in as well was measured rather than argued: the entry chunk goes from
 * 528,204 bytes to 992,062 (both `stat`, the second on a scratch build of this tree with the
 * two imports made static), and every first paint of the landing page — the one route
 * guaranteed to be somebody's first — then parses a quarter of a megabyte of Markdown and
 * highlighting machinery for a screen it does not draw.
 *
 * `tests/browser/test_first_load.py` is what stops that arriving by accident through a chain
 * nobody noticed, and it stops it by weighing what a real Chromium downloads for `/` rather
 * than by reasoning about the emitted graph. The distinction is not academic: the landing
 * page's own `lazy()` boundary is mounted unconditionally, so it defers nothing and a static
 * walk of the build called 632,413 bytes 528,204.
 *
 * There is no recovery machinery behind these two any more, and that is the point of the
 * change: `vite-plugins/grace-window.ts` keeps the previous build's chunks on disk so a tab
 * open across one rebuild simply succeeds, and a tab that outlives two lands on the chunk
 * case in `app/error-boundary.tsx`, which offers the reload that fixes it.
 */
const ReviewPage = lazy(() =>
  import("./features/review/review-page").then((module) => ({ default: module.ReviewPage })),
);
const PoliciesPage = lazy(() =>
  import("./features/policies/policies-page").then((module) => ({ default: module.PoliciesPage })),
);

/**
 * A URL that is not a screen says so.
 *
 * It used to redirect to `/start` without a word, so a stale link — a review that was
 * deleted, a bookmark from before a rename — landed somebody on a form with no explanation
 * and no way to tell whether they had mistyped or the thing was gone. Naming the address is
 * the whole of the fix: it is the one piece of information the reader does not have.
 *
 * And only that. It also said "It may have been a review that has since been deleted", which
 * was a guess about every address it was ever shown for — `/modles`, a truncated paste, a
 * link from a blog post — and could not be true of any of them: `/reviews/:reviewId` is a
 * route, so a review id that no longer exists renders the review page and its own error,
 * never this. A guess offered as a possibility is still a guess, and this one sent people
 * looking for a deleted review when what they had was a typo.
 */
function NotFound() {
  const { pathname } = useLocation();
  return (
    <EmptyState
      title="No screen at that address"
      action={
        <>
          <ButtonLink to="/reviews" variant="secondary">
            Your reviews
          </ButtonLink>
          <ButtonLink to="/start">Start a review</ButtonLink>
        </>
      }
    >
      <span className="font-mono text-[12px] text-ink-2 wrap-anywhere">{pathname}</span> is not
      part of the workbench.
    </EmptyState>
  );
}

/** The landing page carries its own chrome; everything else lives inside the workbench shell. */
function Shell() {
  return (
    <AppShell>
      {/* The boundary is inside `<main>`, so a route that throws loses the route and not the
          rail — the reader can still navigate away from the one screen that broke. */}
      <ErrorBoundary>
        {/* The same measured box the review page draws itself in. `null` here would be the
            landing page's bug again one level down, and a full-bleed panel touching both
            edges of the viewport is not what the screen it is standing in for looks like. */}
        <Suspense
          fallback={
            <div className="mx-auto max-w-[76rem] p-4 sm:p-6">
              <LoadingPanel label="Loading…" />
            </div>
          }
        >
          <Routes>
            <Route path="/start" element={<StartPage />} />
            <Route path="/runs/:runId" element={<RunPage />} />
            <Route path="/reviews" element={<ReviewsPage />} />
            <Route path="/reviews/:reviewId" element={<ReviewPage />} />
            <Route path="/repositories" element={<RepositoriesPage />} />
            <Route path="/cases" element={<CasesPage />} />
            <Route path="/policies" element={<PoliciesPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </ErrorBoundary>
    </AppShell>
  );
}

/** What the tab says on a route that has not named itself. */
const PRODUCT_TITLE = "ArchCompass — architecture review workbench";

/**
 * Everything a navigation owes the reader, in the one effect that knows a navigation happened.
 *
 * It was `ScrollToTop` and it did exactly that, which left two things undone on every
 * navigation in the product — a nav link, a docket row, a palette entry, a lineage row.
 *
 * The first is where the keyboard goes. The page area is replaced and focus stays where it
 * was, so a screen reader hears nothing and the next Tab restarts from the top of the
 * document. After the palette it is worse: the focus trap restores to whatever opened it, and
 * ⌘K was opened by `<body>`, which is not focusable — so the most-used way to reach a review
 * lands you on the review with focus nowhere. The shell built the target for this years ago
 * and never called it: `<main id="main" tabIndex={-1}>` is programmatically focusable with its
 * ring suppressed, and it is the same element the skip link names, so the keyboard has one
 * destination rather than two. Not on the first paint — arriving at a URL is not a navigation,
 * and stealing focus from a reader who has not moved yet is a bug of its own.
 *
 * The second is what the tab is called. `index.html` names the product, and nothing changed it
 * per route, so eight screens announced themselves identically to a screen reader, to the
 * history and to a row of open tabs. The names come from the same `NAV` labels the rail and
 * the palette print. A route that knows more than its section — the run page, which has a
 * stage — sets its own from deeper in the tree and wins, because a child's effect runs after
 * this one.
 */
function StartOfRoute() {
  const { pathname } = useLocation();
  const arrived = useRef(false);
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
    const name = pageName(pathname);
    document.title = name ? `${name} · ArchCompass` : PRODUCT_TITLE;
    if (!arrived.current) {
      arrived.current = true;
      return;
    }
    document.getElementById("main")?.focus({ preventScroll: true });
  }, [pathname]);
  return null;
}

export function App() {
  return (
    <>
      <StartOfRoute />
      {/* No Suspense here any more: the landing page is static, and everything under
          `Shell` has its own boundary with a fallback that looks like the page it replaces. */}
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="*" element={<Shell />} />
      </Routes>
    </>
  );
}
