import { Link } from "react-router-dom";

import { getSsrUrl, uiPaths } from "@/utils/appPaths";

type DashboardAdminShortcutsProps = {
  userId: number;
};

export function DashboardAdminShortcuts({ userId }: DashboardAdminShortcutsProps) {
  const shortcutItems = [
    {
      title: "Admin",
      description: "Overview",
      colorClass: "dashboard-shortcut__icon dashboard-shortcut__icon--emerald",
      icon: "🛡",
      to: uiPaths.adminDashboard,
      external: false,
    },
    {
      title: "Users",
      description: "Manage accounts",
      colorClass: "dashboard-shortcut__icon dashboard-shortcut__icon--blue",
      icon: "👥",
      to: uiPaths.adminUsers,
      external: false,
    },
    {
      title: "Create User",
      description: "Add new admin/user",
      colorClass: "dashboard-shortcut__icon dashboard-shortcut__icon--indigo",
      icon: "➕",
      to: uiPaths.adminUsers,
      external: false,
    },
    {
      title: "Stats",
      description: "System metrics",
      colorClass: "dashboard-shortcut__icon dashboard-shortcut__icon--amber",
      icon: "📊",
      to: uiPaths.adminDashboard,
      external: false,
    },
    {
      title: "Change Password",
      description: "Your admin password",
      colorClass: "dashboard-shortcut__icon dashboard-shortcut__icon--rose",
      icon: "🔑",
      to: getSsrUrl(`/admin/users/${userId}/password`),
      external: true,
    },
  ] as const;

  return (
    <section className="dashboard-shortcuts panel">
      <h2 className="dashboard-section-heading">Admin Shortcuts</h2>
      <div className="dashboard-shortcuts__grid">
        {shortcutItems.map((item) =>
          item.external ? (
            <a className="dashboard-shortcut" href={item.to} key={item.title}>
              <div className={item.colorClass}>{item.icon}</div>
              <div className="dashboard-shortcut__title">{item.title}</div>
              <div className="dashboard-shortcut__description">{item.description}</div>
            </a>
          ) : (
            <Link className="dashboard-shortcut" key={item.title} to={item.to}>
              <div className={item.colorClass}>{item.icon}</div>
              <div className="dashboard-shortcut__title">{item.title}</div>
              <div className="dashboard-shortcut__description">{item.description}</div>
            </Link>
          ),
        )}
      </div>
    </section>
  );
}
