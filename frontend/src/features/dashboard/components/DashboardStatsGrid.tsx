import type { DashboardStats } from "@/types/api";

interface DashboardStatsGridProps {
  stats: DashboardStats;
}

export function DashboardStatsGrid({ stats }: DashboardStatsGridProps) {
  const metricCards = [
    {
      value: stats.total_projects,
      label: "Total Projects",
      trend: stats.on_time_trend,
      icon: "📄",
      tone: "dashboard-metric dashboard-metric--blue",
      chipTone: "dashboard-metric__chip dashboard-metric__chip--emerald",
    },
    {
      value: `${stats.on_time_rate}%`,
      label: "On-Time Delivery",
      trend: `${stats.on_time_rate}%`,
      icon: "✓",
      tone: "dashboard-metric dashboard-metric--emerald",
      chipTone: "dashboard-metric__chip dashboard-metric__chip--emerald",
    },
    {
      value: stats.avg_days,
      label: "Avg. Days to Complete",
      trend: stats.avg_days_trend,
      icon: "◷",
      tone: "dashboard-metric dashboard-metric--amber",
      chipTone: "dashboard-metric__chip dashboard-metric__chip--amber",
    },
    {
      value: stats.delayed_count,
      label: "Delayed Projects",
      trend: stats.delayed_count,
      icon: "!",
      tone: "dashboard-metric dashboard-metric--rose",
      chipTone: "dashboard-metric__chip dashboard-metric__chip--rose",
    },
  ] as const;

  return (
    <div className="dashboard-metrics">
      {metricCards.map((card) => (
        <article className={card.tone} key={card.label}>
          <div className="dashboard-metric__backdrop" />
          <div className="dashboard-metric__content">
            <div className="dashboard-metric__header">
              <div className="dashboard-metric__icon">{card.icon}</div>
              <span className={card.chipTone}>{card.trend}</span>
            </div>
            <p className="dashboard-metric__value">{card.value}</p>
            <p className="dashboard-metric__label">{card.label}</p>
          </div>
        </article>
      ))}
    </div>
  );
}
