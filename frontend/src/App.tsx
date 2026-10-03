import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { CampaignsPage } from "./pages/CampaignsPage";
import { HealthPage } from "./pages/HealthPage";

export function App() {
  return (
    <>
      <header className="app-head">
        <h1>Campaign Data Hub</h1>
        <nav>
          <NavLink to="/campaigns">campaigns</NavLink>
          <NavLink to="/health">data health</NavLink>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/campaigns" element={<CampaignsPage />} />
          <Route path="/health" element={<HealthPage />} />
          <Route path="*" element={<Navigate to="/campaigns" replace />} />
        </Routes>
      </main>
    </>
  );
}
