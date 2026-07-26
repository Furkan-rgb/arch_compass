import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { Loading, Shell } from "./components";

const CasesPage = lazy(() =>
  import("./pages/CasesPage").then(({ CasesPage }) => ({ default: CasesPage })),
);
const DashboardPage = lazy(() =>
  import("./pages/DashboardPage").then(({ DashboardPage }) => ({ default: DashboardPage })),
);
const PoliciesPage = lazy(() =>
  import("./pages/PoliciesPage").then(({ PoliciesPage }) => ({ default: PoliciesPage })),
);
const RepositoriesPage = lazy(() =>
  import("./pages/RepositoriesPage").then(({ RepositoriesPage }) => ({
    default: RepositoriesPage,
  })),
);
const ReviewsPage = lazy(() =>
  import("./pages/ReviewsPage").then(({ ReviewsPage }) => ({ default: ReviewsPage })),
);
const ReviewDetailPage = lazy(() =>
  import("./pages/ReviewDetailPage").then(({ ReviewDetailPage }) => ({
    default: ReviewDetailPage,
  })),
);

export function App() {
  return (
    <Shell>
      <Suspense fallback={<Loading label="Opening field notes…" />}>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/cases" element={<CasesPage />} />
          <Route path="/repositories" element={<RepositoriesPage />} />
          <Route path="/reviews" element={<ReviewsPage />} />
          <Route path="/reviews/:reviewId" element={<ReviewDetailPage />} />
          <Route path="/policies" element={<PoliciesPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </Shell>
  );
}
