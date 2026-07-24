import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { Loading, Shell } from "./components";

const CasesPage = lazy(() =>
  import("./pages/CasesPage").then(({ CasesPage }) => ({ default: CasesPage })),
);
const DashboardPage = lazy(() =>
  import("./pages/DashboardPage").then(({ DashboardPage }) => ({ default: DashboardPage })),
);
const NewConsultationPage = lazy(() =>
  import("./pages/NewConsultationPage").then(({ NewConsultationPage }) => ({
    default: NewConsultationPage,
  })),
);
const PoliciesPage = lazy(() =>
  import("./pages/PoliciesPage").then(({ PoliciesPage }) => ({ default: PoliciesPage })),
);
const RepositoriesPage = lazy(() =>
  import("./pages/RepositoriesPage").then(({ RepositoriesPage }) => ({
    default: RepositoriesPage,
  })),
);
const RunDetailPage = lazy(() =>
  import("./pages/RunDetailPage").then(({ RunDetailPage }) => ({ default: RunDetailPage })),
);
const RunsPage = lazy(() =>
  import("./pages/RunsPage").then(({ RunsPage }) => ({ default: RunsPage })),
);

export function App() {
  return (
    <Shell>
      <Suspense fallback={<Loading label="Opening field notes…" />}>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/new" element={<NewConsultationPage />} />
          <Route path="/cases" element={<CasesPage />} />
          <Route path="/repositories" element={<RepositoriesPage />} />
          <Route path="/runs" element={<RunsPage />} />
          <Route path="/runs/:runId" element={<RunDetailPage />} />
          <Route path="/policies" element={<PoliciesPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </Shell>
  );
}
