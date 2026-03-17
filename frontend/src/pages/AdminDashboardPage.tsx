import { Link } from "react-router-dom";

import { getApiErrorMessage } from "@/api/client";
import { AdminStatsGrid } from "@/features/admin/components/AdminStatsGrid";
import { useAdminDashboardQuery } from "@/features/admin/useAdminDashboardQuery";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { getSsrUrl, ssrPaths, uiPaths } from "@/utils/appPaths";

const adminShortcutCards = [
  {
    title: "Manage Users",
    description: "Create, edit, delete users",
    to: uiPaths.adminUsers,
    kind: "ui" as const,
    tone: "users",
  },
  {
    title: "SSR Admin Users",
    description: "Open the retained backend admin users view",
    href: getSsrUrl(ssrPaths.adminUsers),
    kind: "ssr" as const,
    tone: "reports",
  },
  {
    title: "SSR Admin Dashboard",
    description: "Open the retained backend admin dashboard view",
    href: getSsrUrl(ssrPaths.adminDashboard),
    kind: "ssr" as const,
    tone: "settings",
  },
] as const;

export function AdminDashboardPage() {
  useDocumentTitle("CMS UI Admin");
  const dashboardQuery = useAdminDashboardQuery();

  if (dashboardQuery.isPending) {
    return (
      <main className="page admin-dashboard-page admin-dashboard-page--state">
        <section className="panel admin-dashboard-state-card">
          <div className="admin-dashboard-state-card__icon">...</div>
          <h1 className="admin-dashboard-state-card__title">Loading admin dashboard</h1>
          <p className="admin-dashboard-state-card__message">
            Fetching the current /api/v2 admin dashboard contract.
          </p>
        </section>
      </main>
    );
  }

  if (dashboardQuery.isError) {
    return (
      <main className="page admin-dashboard-page admin-dashboard-page--state">
        <section className="panel admin-dashboard-state-card admin-dashboard-state-card--error">
          <div className="admin-dashboard-state-card__icon">!</div>
          <h1 className="admin-dashboard-state-card__title">Admin dashboard unavailable</h1>
          <p className="admin-dashboard-state-card__message">
            {getApiErrorMessage(
              dashboardQuery.error,
              "The frontend shell could not load the admin dashboard contract.",
            )}
          </p>
          <div className="admin-dashboard-state-card__actions">
            <button className="button" onClick={() => void dashboardQuery.refetch()} type="button">
              Retry
            </button>
            <a className="button button--secondary" href={getSsrUrl(ssrPaths.adminDashboard)}>
              Open SSR admin dashboard
            </a>
          </div>
        </section>
      </main>
    );
  }

  const dashboard = dashboardQuery.data;

  return (
    <main className="page admin-dashboard-page">
      <div className="admin-dashboard-shell">
        <div className="admin-dashboard-header">
          <div>
            <h1>Admin Dashboard</h1>
            <p>System overview and management</p>
          </div>
          <Link className="admin-dashboard-header__back" to={uiPaths.dashboard}>
            Back to User Dashboard
          </Link>
        </div>

        <AdminStatsGrid stats={dashboard.stats} />

        <section className="admin-dashboard-shortcuts">
          {adminShortcutCards.map((card) =>
            card.kind === "ui" ? (
              <Link
                className={`admin-shortcut-card admin-shortcut-card--${card.tone}`}
                key={card.title}
                to={card.to}
              >
                <div
                  aria-hidden="true"
                  className={`admin-shortcut-card__icon admin-shortcut-card__icon--${card.tone}`}
                >
                  {card.title.slice(0, 1)}
                </div>
                <div>
                  <h2>{card.title}</h2>
                  <p>{card.description}</p>
                </div>
              </Link>
            ) : (
              <a
                className={`admin-shortcut-card admin-shortcut-card--${card.tone}`}
                href={card.href}
                key={card.title}
              >
                <div
                  aria-hidden="true"
                  className={`admin-shortcut-card__icon admin-shortcut-card__icon--${card.tone}`}
                >
                  {card.title.slice(0, 1)}
                </div>
                <div>
                  <h2>{card.title}</h2>
                  <p>{card.description}</p>
                </div>
              </a>
            ),
          )}
        </section>

        <section className="admin-dashboard-footer-note">
          <span className="helper-text">Viewer: {dashboard.viewer.username}</span>
        </section>
      </div>
    </main>
  );
}
