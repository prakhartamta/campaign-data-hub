import { Link, NavLink, Navigate, Route, Routes } from "react-router-dom";
import { CampaignsPage } from "./pages/CampaignsPage";
import { HealthPage } from "./pages/HealthPage";
import { LogoMark } from "./components/icons";

export function App() {
  return (
    <>
      <header className="app-head">
        {/* The product name is the brand, so each page's own h1 names the page instead. */}
        <Link to="/campaigns" className="brand" aria-label="Campaign Data Hub, home">
          <LogoMark />
          <span className="brand-text">
            <b>Campaign</b>
            <span>Data Hub</span>
          </span>
        </Link>
        <nav>
          <NavLink to="/campaigns">
            <span className="cap">campaigns</span>
          </NavLink>
          <NavLink to="/health">
            <span className="cap">data health</span>
          </NavLink>
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
