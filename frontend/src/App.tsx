import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { Booting, Shell } from "./components";
import { RunProvider } from "./run";

const HomePage = lazy(() =>
  import("./pages/HomePage").then(({ HomePage }) => ({ default: HomePage })),
);
const PoliciesPage = lazy(() =>
  import("./pages/PoliciesPage").then(({ PoliciesPage }) => ({ default: PoliciesPage })),
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
        {/* The only wait with no shape to draw: which page is arriving is not yet known,
            so there are no rows to reserve and the turning compass has nothing to displace. */}
        <Suspense fallback={<Booting label="Opening field notes…" />}>
          <Routes>
            <Route path="/" element={<HomePage />} />
            {/* Past reviews are a standing record, like the policy corpus, so they keep
                their own place rather than growing without limit under the start step. */}
            <Route path="/reviews" element={<ReviewsPage />} />
            <Route path="/reviews/:reviewId" element={<ReviewDetailPage />} />
            <Route path="/policies" element={<PoliciesPage />} />
            {/* Cases dissolved into Home, and the standalone atlas explorer into the review
                that raises the question (workspace-design §4). A bookmark must not 404. */}
            <Route path="/cases" element={<Navigate to="/" replace />} />
            <Route path="/repositories" element={<Navigate to="/" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </Shell>
    </RunProvider>
  );
}
