import { Link } from "react-router-dom";

import { DashboardAdminShortcuts } from "@/features/dashboard/components/DashboardAdminShortcuts";
import { DashboardProjectGrid } from "@/features/dashboard/components/DashboardProjectGrid";
import { DashboardStatsGrid } from "@/features/dashboard/components/DashboardStatsGrid";
import { useDashboardQuery } from "@/features/dashboard/useDashboardQuery";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { getSsrUrl, ssrPaths, uiPaths } from "@/utils/appPaths";

export function DashboardPage() {
  useDocumentTitle("CMS UI Dashboard");
  const dashboardQuery = useDashboardQuery();

  if (dashboardQuery.isPending) {
    return (
      <main className="page dashboard-page dashboard-page--state">
        <section className="panel dashboard-state-card">
          <div className="dashboard-state-card__icon">◌</div>
          <h1 className="dashboard-state-card__title">Loading dashboard</h1>
          <p className="dashboard-state-card__message">
            Fetching the dashboard summary and project cards from /api/v2/dashboard.
          </p>
        </section>
      </main>
    );
  }

  if (dashboardQuery.isError) {
    return (
      <main className="page dashboard-page dashboard-page--state">
        <section className="panel dashboard-state-card dashboard-state-card--error">
          <div className="dashboard-state-card__icon">!</div>
          <h1 className="dashboard-state-card__title">Dashboard unavailable</h1>
          <p className="dashboard-state-card__message">
            The frontend shell could not load the dashboard contract.
          </p>
          <div className="dashboard-state-card__actions">
            <button className="button" onClick={() => dashboardQuery.refetch()}>
              Retry
            </button>
            <a className="button button--secondary" href={getSsrUrl(ssrPaths.dashboard)}>
              Open SSR dashboard
            </a>
          </div>
        </section>
      </main>
    );
  }

  const { projects, stats, viewer } = dashboardQuery.data;
  const isAdmin = viewer.roles.includes("Admin");

  return (
    <main className="page dashboard-page">
      <header className="dashboard-hero">
        <h1 className="dashboard-hero__title">S4carlisle Production Dashboard</h1>
        <p className="dashboard-hero__subtitle">Publishing Production Overview</p>
      </header>

      <DashboardStatsGrid stats={stats} />

      {isAdmin ? <DashboardAdminShortcuts userId={viewer.id} /> : null}

      <section className="dashboard-projects panel">
        <div className="dashboard-section-title">
          <div>
            <h2 className="dashboard-section-heading">Projects</h2>
            <p className="dashboard-section-copy">
              {projects.length} loaded from the current /api/v2 dashboard contract
            </p>
          </div>
          <div className="dashboard-projects__actions">
            <Link className="button button--secondary" to={uiPaths.projects}>
              Open projects
            </Link>
          </div>
        </div>

        {projects.length === 0 ? (
          <div className="dashboard-empty">
            <div className="dashboard-empty__icon">📘</div>
            <p className="dashboard-empty__title">No projects yet</p>
            <p className="dashboard-empty__copy">
              Project summaries will appear here once books are created through the current backend flows.
            </p>
            <div className="dashboard-empty__actions">
              <a className="button" href={getSsrUrl(ssrPaths.projectCreate)}>
                Open SSR project creation
              </a>
            </div>
          </div>
        ) : (
          <DashboardProjectGrid projects={projects} />
        )}
      </section>
    </main>
  );
}
