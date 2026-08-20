import { Suspense, lazy, useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { AppShell } from "./app/shell";
import { LoadingPanel } from "./ui/states";

/**
 * Routes are loaded when they are visited.
 *
 * The Markdown renderer alone is a third of the bundle, and it is only needed on the two
 * screens that render authored prose — so the landing page, which is what a first visit
 * actually loads, no longer carries it.
 */
const LandingPage = lazy(() =>
  import("./features/landing/landing-page").then((module) => ({ default: module.LandingPage })),
);
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

/** The landing page carries its own chrome; everything else lives inside the workbench shell. */
function Shell() {
  return (
    <AppShell>
      <Suspense fallback={<LoadingPanel label="Loading…" />}>
        <Routes>
          <Route path="/start" element={<StartPage />} />
          <Route path="/runs/:runId" element={<RunPage />} />
          <Route path="/reviews" element={<ReviewsPage />} />
          <Route path="/reviews/:reviewId" element={<ReviewPage />} />
          <Route path="/repositories" element={<RepositoriesPage />} />
          <Route path="/cases" element={<CasesPage />} />
          <Route path="/policies" element={<PoliciesPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/start" replace />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}

/** A route change should start at the top, the way following a link in a document does. */
function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
  }, [pathname]);
  return null;
}

export function App() {
  return (
    <>
      <ScrollToTop />
      <Suspense fallback={null}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="*" element={<Shell />} />
        </Routes>
      </Suspense>
    </>
  );
}
