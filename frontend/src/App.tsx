import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/app-shell";
import { CasesPage } from "./pages/CasesPage";
import { PoliciesPage } from "./pages/PoliciesPage";
import { RepositoriesPage } from "./pages/RepositoriesPage";
import { ReviewPage } from "./pages/ReviewPage";
import { ReviewsPage } from "./pages/ReviewsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StartPage } from "./pages/StartPage";

export function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to="/start" replace />} />
        <Route path="/start" element={<StartPage />} />
        <Route path="/reviews" element={<ReviewsPage />} />
        <Route path="/reviews/:reviewId" element={<ReviewPage />} />
        <Route path="/repositories" element={<RepositoriesPage />} />
        <Route path="/cases" element={<CasesPage />} />
        <Route path="/policies" element={<PoliciesPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/start" replace />} />
      </Routes>
    </AppShell>
  );
}
