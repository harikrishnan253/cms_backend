import { NavLink, Outlet } from "react-router-dom";

import { NotificationBell } from "@/features/notifications/components/NotificationBell";
import { useLogout } from "@/features/session/useLogout";
import { useSessionStore } from "@/stores/sessionStore";
import { getSsrUrl, uiPaths } from "@/utils/appPaths";

type ShellNavItem = {
  label: string;
  to: string;
  icon: string;
  end?: boolean;
};

const primaryNavItems: ShellNavItem[] = [
  { label: "Dashboard", to: uiPaths.dashboard, icon: "▦", end: false },
  { label: "Projects", to: uiPaths.projects, icon: "▤", end: false },
];

const adminNavItems: ShellNavItem[] = [
  { label: "Admin Dashboard", to: uiPaths.adminDashboard, icon: "🛡" },
  { label: "Users", to: uiPaths.adminUsers, icon: "👥" },
];

export function AppLayout() {
  const viewer = useSessionStore((state) => state.viewer);
  const logoutMutation = useLogout();
  const isAdmin = viewer?.roles.includes("Admin") ?? false;
  const viewerInitial = viewer?.username?.[0]?.toUpperCase() ?? "U";
  const primaryRole = viewer?.roles[0] ?? "Viewer";

  return (
    <div className="shell-root">
      <aside className="shell-sidebar">
        <div className="shell-sidebar__brand">
          <img
            alt="S4Carlisle Logo"
            className="shell-sidebar__logo"
            src={getSsrUrl("/static/images/S4c.png")}
          />
          <div>
            <h1 className="shell-sidebar__title">Pub CMS</h1>
            <p className="shell-sidebar__subtitle">Production Suite</p>
          </div>
        </div>

        <nav className="shell-nav" aria-label="Primary navigation">
          {primaryNavItems.map((item) => (
            <NavLink
              key={item.to}
              className={({ isActive }) => `shell-nav__item${isActive ? " active" : ""}`}
              end={item.end}
              to={item.to}
            >
              <span aria-hidden="true" className="shell-nav__icon">
                {item.icon}
              </span>
              <span>{item.label}</span>
            </NavLink>
          ))}

          {isAdmin ? (
            <>
              <div className="shell-nav__section-label">Admin</div>
              {adminNavItems.map((item) => (
                <NavLink
                  key={item.to}
                  className={({ isActive }) => `shell-nav__item${isActive ? " active" : ""}`}
                  to={item.to}
                >
                  <span aria-hidden="true" className="shell-nav__icon">
                    {item.icon}
                  </span>
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </>
          ) : null}
        </nav>

        <div className="shell-sidebar__footer">
          <div className="shell-user-card">
            <div className="shell-user-card__avatar">{viewerInitial}</div>
            <div className="shell-user-card__meta">
              <p className="shell-user-card__name">{viewer?.username ?? "User"}</p>
              <p className="shell-user-card__role">{primaryRole}</p>
            </div>
          </div>
          <button
            className="shell-logout"
            disabled={logoutMutation.isPending}
            type="button"
            onClick={() => logoutMutation.mutate()}
          >
            <span aria-hidden="true" className="shell-nav__icon">
              ↩
            </span>
            <span>{logoutMutation.isPending ? "Signing out..." : "Logout"}</span>
          </button>
        </div>
      </aside>

      <div className="shell-main">
        <div className="shell-toolbar">
          <div className="shell-toolbar__spacer" />
          <NotificationBell />
        </div>
        <main className="shell-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
