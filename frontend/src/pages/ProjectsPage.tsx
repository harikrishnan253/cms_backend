import { Link } from "react-router-dom";

import { ProjectsTable } from "@/features/projects/components/ProjectsTable";
import { useProjectsQuery } from "@/features/projects/useProjectsQuery";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { getSsrUrl, ssrPaths, uiPaths } from "@/utils/appPaths";

export function ProjectsPage() {
  useDocumentTitle("CMS UI Projects");
  const projectsQuery = useProjectsQuery(0, 100);

  if (projectsQuery.isPending) {
    return (
      <main className="page projects-page projects-page--state">
        <section className="panel projects-state-card">
          <div className="projects-state-card__icon">📚</div>
          <h1 className="projects-state-card__title">Loading projects</h1>
          <p className="projects-state-card__message">
            Fetching the projects list from /api/v2/projects.
          </p>
        </section>
      </main>
    );
  }

  if (projectsQuery.isError) {
    return (
      <main className="page projects-page projects-page--state">
        <section className="panel projects-state-card projects-state-card--error">
          <div className="projects-state-card__icon">!</div>
          <h1 className="projects-state-card__title">Projects unavailable</h1>
          <p className="projects-state-card__message">
            The frontend shell could not load the projects list contract.
          </p>
          <div className="projects-state-card__actions">
            <button className="button" onClick={() => projectsQuery.refetch()}>
              Retry
            </button>
            <a className="button button--secondary" href={getSsrUrl(ssrPaths.projects)}>
              Open SSR projects
            </a>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="page projects-page">
      <section className="projects-shell">
        <header className="projects-shell__header">
          <div className="projects-shell__breadcrumbs">
            <Link className="projects-shell__breadcrumb-link" to={uiPaths.dashboard}>
              Dashboard
            </Link>
            <span className="projects-shell__breadcrumb-separator">›</span>
            <h1 className="projects-shell__title">Projects</h1>
          </div>

          <div className="projects-shell__actions">
            <a className="button projects-shell__create-button" href={getSsrUrl(ssrPaths.projectCreate)}>
              <span aria-hidden="true">＋</span>
              <span>New Project</span>
            </a>
          </div>
        </header>

        <div className="projects-shell__content">
          {projectsQuery.data.projects.length === 0 ? (
            <div className="projects-empty">
              <div className="projects-empty__icon">📘</div>
              <p className="projects-empty__title">No projects found</p>
              <a className="projects-empty__link" href={getSsrUrl(ssrPaths.projectCreate)}>
                Create your first project
              </a>
            </div>
          ) : (
            <ProjectsTable projects={projectsQuery.data.projects} />
          )}
        </div>
      </section>
    </main>
  );
}
