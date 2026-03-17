import { Link } from "react-router-dom";

import type { ProjectSummary } from "@/types/api";
import { uiPaths } from "@/utils/appPaths";

interface ProjectsTableProps {
  projects: ProjectSummary[];
}

export function ProjectsTable({ projects }: ProjectsTableProps) {
  return (
    <div className="projects-grid">
      {projects.map((project) => (
        <article className="projects-card" key={project.id}>
          <Link className="projects-card__link" to={uiPaths.projectDetail(project.id)}>
            <div className="projects-card__header">
              <div>
                <h2 className="projects-card__title">{project.title}</h2>
                <p className="projects-card__code">{project.code}</p>
              </div>
              <div className="projects-card__icon" aria-hidden="true">
                📚
              </div>
            </div>
            <p className="projects-card__client">{project.client_name || ""}</p>
            <div className="projects-card__meta">
              <span>{project.status}</span>
              <span>{project.xml_standard}</span>
              <span>{project.chapter_count} chapters</span>
              <span>{project.file_count} files</span>
            </div>
          </Link>
        </article>
      ))}
    </div>
  );
}
