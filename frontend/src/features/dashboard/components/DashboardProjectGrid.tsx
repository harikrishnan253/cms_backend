import { Link } from "react-router-dom";

import type { ProjectSummary } from "@/types/api";
import { uiPaths } from "@/utils/appPaths";

interface DashboardProjectGridProps {
  projects: ProjectSummary[];
}

export function DashboardProjectGrid({ projects }: DashboardProjectGridProps) {
  return (
    <div className="dashboard-project-grid">
      {projects.map((project) => (
        <Link className="dashboard-project-card" key={project.id} to={uiPaths.projectDetail(project.id)}>
          <div className="dashboard-project-card__header">
            <div>
              <div className="dashboard-project-card__code">{project.code}</div>
              <h3 className="dashboard-project-card__title">{project.title}</h3>
            </div>
            <div className="dashboard-project-card__status">{project.status}</div>
          </div>
          <div className="dashboard-project-card__meta">
            <span>{project.client_name || "No client name"}</span>
            <span>{project.xml_standard}</span>
          </div>
          <div className="dashboard-project-card__footer">
            <span>{project.chapter_count} chapters</span>
            <span>{project.file_count} files</span>
          </div>
        </Link>
      ))}
    </div>
  );
}
