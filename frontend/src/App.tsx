import { Suspense, lazy, useEffect, useRef } from "react";
import { Route, Routes, useLocation } from "react-router-dom";

import { AppShell, pageName } from "./app/shell";
import { ErrorBoundary } from "./app/error-boundary";
import { LandingPage } from "./features/landing/landing-page";
import { ButtonLink } from "./ui/button";
import { EmptyState, LoadingPanel } from "./ui/states";

/**
 * Routes are loaded when they are visited — except the one that is always visited first.
 *
 * The Markdown renderer alone is a third of the bundle, and it is only needed on the two
 * screens that render authored prose, so the split is worth having. The landing page was in
 * it anyway, which meant a visitor at `/` downloaded the HTML, then the entry bundle, then a
 * *second* round trip for the landing chunk — and saw a blank white page for all of it,
 * because the fallback around it is `null`. The argument for splitting it was an argument
 * about the Markdown renderer, which the landing page never imported.
 *
 * So the first paint is static and the heavy screens stay lazy.
 */
const StartPage = lazy(() =>
  import("./features/start/start-page").then((module) => ({ default: module.StartPage })),
);
const RunPage = lazy(() =>
  import("./features/start/run-page").then((module) => ({ default: module.RunPage })),
);
const ReviewsPage = lazy(() =>
  import("./features/reviews/reviews-page").then((module) => ({ default: module.ReviewsPage })),
);
const ReviewPage = lazy(() =>
  import("./features/review/review-page").then((module) => ({ default: module.ReviewPage })),
);
const RepositoriesPage = lazy(() =>
  import("./features/repositories/repositories-page").then((module) => ({
    default: module.RepositoriesPage,
  })),
);
const CasesPage = lazy(() =>
  import("./features/cases/cases-page").then((module) => ({ default: module.CasesPage })),
);
const PoliciesPage = lazy(() =>
  import("./features/policies/policies-page").then((module) => ({ default: module.PoliciesPage })),
);
const SettingsPage = lazy(() =>
  import("./features/settings/settings-page").then((module) => ({ default: module.SettingsPage })),
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
