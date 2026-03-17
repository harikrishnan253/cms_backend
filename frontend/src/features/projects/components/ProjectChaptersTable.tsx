import { Link } from "react-router-dom";
import { useEffect, useState } from "react";

import type { ChapterSummary } from "@/types/api";
import { uiPaths } from "@/utils/appPaths";

type ChapterActionKind = "create" | "rename" | "delete";

interface ProjectChaptersTableProps {
  projectId: number;
  chapters: ChapterSummary[];
  viewMode: "grid" | "list";
  isPending: (action: ChapterActionKind, chapterId?: number | null) => boolean;
  onRename: (chapterId: number, number: string, title: string) => Promise<unknown>;
  onDelete: (chapterId: number, number: string) => Promise<unknown>;
}

function ProjectChapterGridCard({
  projectId,
  chapter,
  isPending,
  onRename,
  onDelete,
}: {
  projectId: number;
  chapter: ChapterSummary;
  isPending: ProjectChaptersTableProps["isPending"];
  onRename: ProjectChaptersTableProps["onRename"];
  onDelete: ProjectChaptersTableProps["onDelete"];
}) {
  const [isRenameOpen, setIsRenameOpen] = useState(false);
  const [number, setNumber] = useState(chapter.number);
  const [title, setTitle] = useState(chapter.title);

  useEffect(() => {
    setNumber(chapter.number);
    setTitle(chapter.title);
  }, [chapter.number, chapter.title]);

  return (
    <>
      <article className="project-chapter-card">
        <div className="project-chapter-card__icon-wrap">
          <div className="project-chapter-card__icon">📁</div>
          <div className="project-chapter-card__number">{chapter.number}</div>
        </div>
        <Link className="project-chapter-card__title" to={uiPaths.chapterDetail(projectId, chapter.id)}>
          Chapter {chapter.number} - {chapter.title}
        </Link>
        <div className="project-chapter-card__badges">
          {chapter.has_manuscript ? <span className="project-chapter-card__badge">Manuscript</span> : null}
          {chapter.has_art ? <span className="project-chapter-card__badge">Art</span> : null}
          {chapter.has_indesign ? <span className="project-chapter-card__badge">InDesign</span> : null}
          {chapter.has_proof ? <span className="project-chapter-card__badge">Proof</span> : null}
          {chapter.has_xml ? <span className="project-chapter-card__badge">XML</span> : null}
        </div>
        <div className="project-chapter-card__actions">
          <button
            className="button button--secondary button--small"
            type="button"
            onClick={() => setIsRenameOpen(true)}
          >
            Rename
          </button>
          <a
            className="button button--secondary button--small"
            href={`/api/v2/projects/${projectId}/chapters/${chapter.id}/package`}
          >
            Download ZIP
          </a>
          <button
            className="button button--secondary button--small"
            disabled={isPending("delete", chapter.id)}
            type="button"
            onClick={() => void onDelete(chapter.id, chapter.number)}
          >
            {isPending("delete", chapter.id) ? "Deleting..." : "Delete"}
          </button>
        </div>
      </article>

      {isRenameOpen ? (
        <div className="project-detail-modal-backdrop" role="presentation">
          <div className="project-detail-modal">
            <section className="project-detail-form-card">
              <div className="project-detail-form-card__header">
                <h3>Rename Chapter</h3>
                <button
                  className="project-detail-form-card__close"
                  type="button"
                  onClick={() => setIsRenameOpen(false)}
                >
                  ×
                </button>
              </div>

              <form
                className="project-detail-form-card__form"
                onSubmit={async (event) => {
                  event.preventDefault();
                  await onRename(chapter.id, number.trim(), title.trim());
                  setIsRenameOpen(false);
                }}
              >
                <label className="field">
                  <span>Chapter Number</span>
                  <input
                    className="search-input"
                    disabled={isPending("rename", chapter.id)}
                    required
                    type="text"
                    value={number}
                    onChange={(event) => setNumber(event.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Chapter Title</span>
                  <input
                    className="search-input"
                    disabled={isPending("rename", chapter.id)}
                    required
                    type="text"
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                  />
                </label>
                <div className="project-detail-form-card__actions">
                  <button
                    className="button button--secondary"
                    type="button"
                    onClick={() => setIsRenameOpen(false)}
                  >
                    Cancel
                  </button>
                  <button className="button" disabled={isPending("rename", chapter.id)} type="submit">
                    {isPending("rename", chapter.id) ? "Saving..." : "Save Changes"}
                  </button>
                </div>
              </form>
            </section>
          </div>
        </div>
      ) : null}
    </>
  );
}

export function ProjectChaptersTable({
  projectId,
  chapters,
  viewMode,
  isPending,
  onRename,
  onDelete,
}: ProjectChaptersTableProps) {
  if (viewMode === "grid") {
    return (
      <div className="project-chapter-grid">
        {chapters.map((chapter) => (
          <ProjectChapterGridCard
            chapter={chapter}
            isPending={isPending}
            key={chapter.id}
            onDelete={onDelete}
            onRename={onRename}
            projectId={projectId}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="project-chapter-list">
      <table className="list-table project-chapter-list__table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Manuscript</th>
            <th>Art</th>
            <th>InDesign</th>
            <th>Proof</th>
            <th>XML</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {chapters.map((chapter) => (
            <tr key={chapter.id}>
              <td>
                <div className="project-chapter-list__name-cell">
                  <span className="project-chapter-list__folder">📁</span>
                  <Link className="table-link" to={uiPaths.chapterDetail(projectId, chapter.id)}>
                    Chapter {chapter.number} - {chapter.title}
                  </Link>
                </div>
              </td>
              <td>{chapter.has_manuscript ? "Yes" : "No"}</td>
              <td>{chapter.has_art ? "Yes" : "No"}</td>
              <td>{chapter.has_indesign ? "Yes" : "No"}</td>
              <td>{chapter.has_proof ? "Yes" : "No"}</td>
              <td>{chapter.has_xml ? "Yes" : "No"}</td>
              <td>
                <div className="table-actions">
                  <a
                    className="button button--secondary button--small"
                    href={`/api/v2/projects/${projectId}/chapters/${chapter.id}/package`}
                  >
                    Package
                  </a>
                  <button
                    className="button button--secondary button--small"
                    disabled={isPending("delete", chapter.id)}
                    type="button"
                    onClick={() => void onDelete(chapter.id, chapter.number)}
                  >
                    {isPending("delete", chapter.id) ? "Deleting..." : "Delete"}
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
