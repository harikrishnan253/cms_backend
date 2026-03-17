import type { AdminDashboardStats } from "@/types/api";

interface AdminStatsGridProps {
  stats: AdminDashboardStats;
}

export function AdminStatsGrid({ stats }: AdminStatsGridProps) {
  const cards = [
    {
      label: "Total Users",
      value: stats.total_users,
      tone: "users",
    },
    {
      label: "Total Files",
      value: stats.total_files,
      tone: "files",
    },
    {
      label: "Total Validations",
      value: stats.total_validations,
      tone: "validations",
    },
    {
      label: "Total Macro",
      value: stats.total_macro,
      tone: "macro",
    },
  ] as const;

  return (
    <div className="admin-dashboard-stats">
      {cards.map((card) => (
        <article className="admin-stat-card" key={card.label}>
          <div
            aria-hidden="true"
            className={`admin-stat-card__icon admin-stat-card__icon--${card.tone}`}
          >
            {card.label.split(" ")[1]?.slice(0, 1) ?? card.label.slice(0, 1)}
          </div>
          <strong>{card.value}</strong>
          <span>{card.label}</span>
        </article>
      ))}
    </div>
  );
}
