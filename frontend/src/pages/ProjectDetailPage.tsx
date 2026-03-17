import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getApiErrorMessage } from "@/api/client";
import { ChapterCreateForm } from "@/features/projects/components/ChapterCreateForm";
import { ProjectChaptersTable } from "@/features/projects/components/ProjectChaptersTable";
import { ProjectMetadataPanel } from "@/features/projects/components/ProjectMetadataPanel";
import { useChapterMutations } from "@/features/projects/useChapterMutations";
import { useProjectChaptersQuery } from "@/features/projects/useProjectChaptersQuery";
import { useProjectDetailQuery } from "@/features/projects/useProjectDetailQuery";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { getSsrUrl, ssrPaths, uiPaths } from "@/utils/appPaths";

export function ProjectDetailPage() {
  const { projectId } = useParams();
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const parsedProjectId = Number.parseInt(projectId ?? "", 10);
  const isValidProjectId = Number.isInteger(parsedProjectId) && parsedProjectId > 0;
  const normalizedProjectId = isValidProjectId ? parsedProjectId : null;
  const projectDetailQuery = useProjectDetailQuery(normalizedProjectId);
  const projectChaptersQuery = useProjectChaptersQuery(normalizedProjectId);
  const chapterMutations = useChapterMutations({ projectId: normalizedProjectId });

  useDocumentTitle(
    normalizedProjectId === null ? "CMS UI Project" : `CMS UI Project ${normalizedProjectId}`,
  );

  if (normalizedProjectId === null) {
    return (
      <main className="page project-detail-page project-detail-page--state">
        <section className="panel project-detail-state-card project-detail-state-card--error">
          <div className="project-detail-state-card__icon">!</div>
          <h1 className="project-detail-state-card__title">Invalid project route</h1>
          <p className="project-detail-state-card__message">
            The selected project identifier is not valid.
          </p>
          <div className="project-detail-state-card__actions">
            <Link className="button" to={uiPaths.projects}>
              Back to projects
            </Link>
          </div>
        </section>
      </main>
    );
  }

  if (projectDetailQuery.isPending || projectChaptersQuery.isPending) {
    return (
      <main className="page project-detail-page project-detail-page--state">
        <section className="panel project-detail-state-card">
          <div className="project-detail-state-card__icon">📁</div>
          <h1 className="project-detail-state-card__title">Loading project</h1>
          <p className="project-detail-state-card__message">
            Fetching the project detail and chapter summary contracts from /api/v2.
          </p>
        </section>
      </main>
    );
  }

  if (projectDetailQuery.isError || projectChaptersQuery.isError) {
    const error = projectDetailQuery.error ?? projectChaptersQuery.error;

    return (
      <main className="page project-detail-page project-detail-page--state">
        <section className="panel project-detail-state-card project-detail-state-card--error">
          <div className="project-detail-state-card__icon">!</div>
          <h1 className="project-detail-state-card__title">Project detail unavailable</h1>
          <p className="project-detail-state-card__message">
            {getApiErrorMessage(error, "The frontend shell could not load the project detail contracts.")}
          </p>
          <div className="project-detail-state-card__actions">
            <button
              className="button"
              onClick={() => {
                void projectDetailQuery.refetch();
                void projectChaptersQuery.refetch();
              }}
            >
              Retry
            </button>
            <Link className="button button--secondary" to={uiPaths.projects}>
              Back to projects
            </Link>
            <a
              className="button button--secondary"
              href={getSsrUrl(ssrPaths.projectDetail(normalizedProjectId))}
            >
              Open SSR project view
            </a>
          </div>
        </section>
      </main>
    );
  }

  if (!projectDetailQuery.data || !projectChaptersQuery.data) {
    return (
      <main className="page project-detail-page project-detail-page--state">
        <section className="panel project-detail-state-card project-detail-state-card--error">
          <div className="project-detail-state-card__icon">!</div>
          <h1 className="project-detail-state-card__title">Project detail unavailable</h1>
          <p className="project-detail-state-card__message">
            The project detail contract returned no data.
          </p>
          <div className="project-detail-state-card__actions">
            <Link className="button" to={uiPaths.projects}>
              Back to projects
            </Link>
          </div>
        </section>
      </main>
    );
  }

  const project = projectDetailQuery.data.project;
  const chapters = projectChaptersQuery.data.chapters;

  return (
    <main className="page project-detail-page">
      <div className="project-detail-shell">
        <div className="project-detail-commandbar">
          <div className="project-detail-commandbar__group">
            <button
              className="project-detail-commandbar__button"
              type="button"
              onClick={() => setIsCreateOpen(true)}
            >
              <span aria-hidden="true">＋</span>
              <span>New</span>
              <span className="project-detail-commandbar__chevron">▾</span>
            </button>
          </div>

          <div className="project-detail-commandbar__group">
            <button
              className={`project-detail-commandbar__button${viewMode === "grid" ? " active" : ""}`}
              type="button"
              onClick={() => setViewMode("grid")}
            >
              <span aria-hidden="true">▦</span>
              <span>View</span>
            </button>
            <button
              className={`project-detail-commandbar__button${viewMode === "list" ? " active" : ""}`}
              type="button"
              onClick={() => setViewMode("list")}
            >
              <span aria-hidden="true">☰</span>
              <span>Details</span>
            </button>
          </div>
        </div>

        <div className="project-detail-addressbar">
          <div className="project-detail-addressbar__nav">
            <Link className="project-detail-addressbar__nav-button" to={uiPaths.projects}>
              ←
            </Link>
            <button
              className="project-detail-addressbar__nav-button"
              type="button"
              onClick={() => window.location.reload()}
            >
              ↻
            </button>
          </div>

          <div className="project-detail-addressbar__path">
            <span className="project-detail-addressbar__icon">🖥</span>
            <div className="project-detail-addressbar__segments">
              <Link className="project-detail-addressbar__link" to={uiPaths.projects}>
                Projects
              </Link>
              <span className="project-detail-addressbar__separator">›</span>
              <span>{project.code}</span>
            </div>
          </div>

          <a
            className="project-detail-addressbar__ssr-link"
            href={getSsrUrl(ssrPaths.projectDetail(normalizedProjectId))}
          >
            Open SSR view
          </a>
        </div>

        <div className="project-detail-explorer">
          <aside className="project-detail-sidebar">
            <div className="project-detail-sidebar__section-label">Quick Access</div>
            <Link className="project-detail-sidebar__item" to={uiPaths.dashboard}>
              <span aria-hidden="true">★</span>
              <span>Favorites</span>
            </Link>
            <Link className="project-detail-sidebar__item" to={uiPaths.projects}>
              <span aria-hidden="true">🕘</span>
              <span>Recent</span>
            </Link>

            <div className="project-detail-sidebar__section-label">This PC</div>
            <div className="project-detail-sidebar__item project-detail-sidebar__item--active">
              <span aria-hidden="true">📂</span>
              <span>{project.code}</span>
            </div>
            <div className="project-detail-sidebar__tree">
              {chapters.map((chapter) => (
                <Link
                  className="project-detail-sidebar__tree-link"
                  key={chapter.id}
                  to={uiPaths.chapterDetail(project.id, chapter.id)}
                >
                  <span aria-hidden="true">📁</span>
                  <span>Ch {chapter.number}</span>
                </Link>
              ))}
            </div>
          </aside>

          <section className="project-detail-main">
            <div className="project-detail-main__section">
              <ProjectMetadataPanel project={project} />
            </div>

            {chapterMutations.status ? (
              <div className={`status-banner status-banner--${chapterMutations.status.tone}`}>
                {chapterMutations.status.message}
              </div>
            ) : null}

            <div className="project-detail-main__section">
              {chapters.length === 0 ? (
                <div className="project-detail-empty">
                  <div className="project-detail-empty__icon">📂</div>
                  <p className="project-detail-empty__title">No chapters available</p>
                  <p className="project-detail-empty__copy">
                    This project currently has no chapter rows to display in the frontend shell.
                  </p>
                </div>
              ) : (
                <ProjectChaptersTable
                  chapters={chapters}
                  isPending={chapterMutations.isPending}
                  onDelete={(chapterId, number) => chapterMutations.deleteChapter(chapterId, number)}
                  onRename={(chapterId, number, title) =>
                    chapterMutations.renameChapter(chapterId, number, title)
                  }
                  projectId={project.id}
                  viewMode={viewMode}
                />
              )}
            </div>
          </section>
        </div>
      </div>

      {isCreateOpen ? (
        <div className="project-detail-modal-backdrop" role="presentation">
          <div className="project-detail-modal">
            <ChapterCreateForm
              isPending={chapterMutations.isPending("create")}
              onCancel={() => setIsCreateOpen(false)}
              onSubmit={async (number, title) => {
                await chapterMutations.createChapter(number, title);
                setIsCreateOpen(false);
              }}
            />
          </div>
        </div>
      ) : null}
    </main>
  );
}
