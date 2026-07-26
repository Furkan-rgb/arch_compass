import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { Loading, Shell } from "./components";
import { RunProvider } from "./run";

const HomePage = lazy(() =>
  import("./pages/HomePage").then(({ HomePage }) => ({ default: HomePage })),
);
const PoliciesPage = lazy(() =>
  import("./pages/PoliciesPage").then(({ PoliciesPage }) => ({ default: PoliciesPage })),
);
const RepositoriesPage = lazy(() =>
  import("./pages/RepositoriesPage").then(({ RepositoriesPage }) => ({
    default: RepositoriesPage,
  })),
);
const ReviewDetailPage = lazy(() =>
  import("./pages/ReviewDetailPage").then(({ ReviewDetailPage }) => ({
    default: ReviewDetailPage,
  })),
);
const ReviewsPage = lazy(() =>
  import("./pages/ReviewsPage").then(({ ReviewsPage }) => ({ default: ReviewsPage })),
);

export function App() {
  return (
    // Above the routes, because a run is not a property of any page: it outlives the page
    // that started it, and the page that watches it is a different one.
    <RunProvider>
      <Shell>
        <Suspense fallback={<Loading label="Opening field notes…" />}>
          <Routes>
            <Route path="/" element={<HomePage />} />
            {/* Past reviews are a standing record, like the policy corpus, so they keep
                their own place rather than growing without limit under the start step. */}
            <Route path="/reviews" element={<ReviewsPage />} />
            <Route path="/reviews/:reviewId" element={<ReviewDetailPage />} />
            {/* The atlas explorer keeps its route and leaves the navigation: it is entered
                from the repository picker, with a question attached, rather than standing
                beside the flow as a map of its own (workspace-design §4). */}
            <Route path="/repositories" element={<RepositoriesPage />} />
            <Route path="/policies" element={<PoliciesPage />} />
            {/* Cases dissolved into Home. A bookmark must not 404. */}
            <Route path="/cases" element={<Navigate to="/" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </Shell>
    </RunProvider>
  );
}
