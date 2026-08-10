import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";

import { Booting, Shell } from "./components";
import { RunProvider } from "./run";

const AboutPage = lazy(() =>
  import("./pages/AboutPage").then(({ AboutPage }) => ({ default: AboutPage })),
);
const HomePage = lazy(() =>
  import("./pages/HomePage").then(({ HomePage }) => ({ default: HomePage })),
);
const StartPage = lazy(() =>
  import("./pages/StartPage").then(({ StartPage }) => ({ default: StartPage })),
);
const PoliciesPage = lazy(() =>
  import("./pages/PoliciesPage").then(({ PoliciesPage }) => ({ default: PoliciesPage })),
);
const ReviewDetailPage = lazy(() =>
  import("./pages/review-detail/ReviewDetailPage").then(({ ReviewDetailPage }) => ({
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
      {/* A tooltip is a label for something already on screen, so the delay and the
          skip-window are one shared setting rather than a decision each caller makes. */}
      <TooltipProvider>
        <Shell>
          {/* The only wait with no shape to draw: which page is arriving is not yet known,
              so there are no rows to reserve and the turning compass has nothing to
              displace. */}
          <Suspense fallback={<Booting label="Opening field notes…" />}>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/start" element={<StartPage />} />
              {/* Past reviews are a standing record, like the policy corpus, so they keep
                  their own place rather than growing without limit under the start step. */}
              <Route path="/reviews" element={<ReviewsPage />} />
              <Route path="/reviews/:reviewId" element={<ReviewDetailPage />} />
              <Route path="/policies" element={<PoliciesPage />} />
              <Route path="/about" element={<AboutPage />} />
              {/* Cases dissolved into the start step, and the standalone atlas explorer into
                  the review that raises the question (workspace-design §4). A bookmark must
                  not 404. */}
              <Route path="/cases" element={<Navigate to="/start" replace />} />
              <Route path="/repositories" element={<Navigate to="/start" replace />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </Shell>
      </TooltipProvider>
    </RunProvider>
  );
}
