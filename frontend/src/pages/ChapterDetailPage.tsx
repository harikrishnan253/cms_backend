import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getApiErrorMessage } from "@/api/client";
import {
  ChapterCategorySummary,
  type ChapterSection,
} from "@/features/projects/components/ChapterCategorySummary";
import { ChapterFilesTable } from "@/features/projects/components/ChapterFilesTable";
import { ChapterMetadataPanel } from "@/features/projects/components/ChapterMetadataPanel";
import { ChapterUploadPanel } from "@/features/projects/components/ChapterUploadPanel";
import { useChapterFileActions } from "@/features/projects/useChapterFileActions";
import { useChapterDetailQuery } from "@/features/projects/useChapterDetailQuery";
import { useChapterFilesQuery } from "@/features/projects/useChapterFilesQuery";
import { useChapterUpload } from "@/features/projects/useChapterUpload";
import { ProcessingStatusPanel } from "@/features/processing/components/ProcessingStatusPanel";
import { useStructuringProcessing } from "@/features/processing/useStructuringProcessing";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import type { ChapterCategoryCounts } from "@/types/api";
import { getSsrUrl, ssrPaths, uiPaths } from "@/utils/appPaths";

const categoryOrder: Array<keyof ChapterCategoryCounts> = [
  "Manuscript",
  "Art",
  "InDesign",
  "Proof",
  "XML",
  "Miscellaneous",
];

function normalizeSection(value: string | null | undefined): ChapterSection {
  if (!value) {
    return "Overview";
  }

  if (value === "Overview") {
    return "Overview";
  }

  if (categoryOrder.includes(value as keyof ChapterCategoryCounts)) {
    return value as keyof ChapterCategoryCounts;
  }

  return "Overview";
}

function getPreferredCategory(value: string | null | undefined): keyof ChapterCategoryCounts {
  const normalized = normalizeSection(value);
  if (normalized === "Overview") {
    return "Manuscript";
  }

  return normalized;
}

export function ChapterDetailPage() {
  const { projectId, chapterId } = useParams();
  const parsedProjectId = Number.parseInt(projectId ?? "", 10);
  const parsedChapterId = Number.parseInt(chapterId ?? "", 10);
  const hasValidProjectId = Number.isInteger(parsedProjectId) && parsedProjectId > 0;
  const hasValidChapterId = Number.isInteger(parsedChapterId) && parsedChapterId > 0;
  const normalizedProjectId = hasValidProjectId ? parsedProjectId : null;
  const normalizedChapterId = hasValidChapterId ? parsedChapterId : null;
  const chapterDetailQuery = useChapterDetailQuery(normalizedProjectId, normalizedChapterId);
  const chapterFilesQuery = useChapterFilesQuery(normalizedProjectId, normalizedChapterId);
  const fileActions = useChapterFileActions({
    projectId: normalizedProjectId,
    chapterId: normalizedChapterId,
  });
  const chapterUpload = useChapterUpload({
    projectId: normalizedProjectId,
    chapterId: normalizedChapterId,
  });
  const structuringProcessing = useStructuringProcessing({
    projectId: normalizedProjectId,
    chapterId: normalizedChapterId,
  });
  const [selectedSection, setSelectedSection] = useState<ChapterSection>("Overview");
  const [searchQuery, setSearchQuery] = useState("");
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const hasInitializedSection = useRef(false);
  const filePaneRef = useRef<HTMLDivElement | null>(null);

  useDocumentTitle(
    normalizedChapterId === null ? "CMS UI Chapter" : `CMS UI Chapter ${normalizedChapterId}`,
  );

  const activeTab = chapterDetailQuery.data?.active_tab ?? "Manuscript";
  const preferredCategory = getPreferredCategory(activeTab);

  useEffect(() => {
    if (!chapterDetailQuery.data || hasInitializedSection.current) {
      return;
    }

    setSelectedSection(preferredCategory);
    hasInitializedSection.current = true;
  }, [chapterDetailQuery.data, preferredCategory]);

  const statusBanners = useMemo(() => {
    const items: Array<{ tone: "pending" | "success" | "error"; message: string }> = [];

    if (fileActions.status) {
      items.push({
        tone: fileActions.status.tone,
        message: fileActions.status.message,
      });
    }

    if (chapterUpload.errorMessage && !isUploadOpen) {
      items.push({
        tone: "error",
        message: chapterUpload.errorMessage,
      });
    } else if (chapterUpload.statusMessage && !isUploadOpen) {
      items.push({
        tone: chapterUpload.isPending ? "pending" : "success",
        message: chapterUpload.statusMessage,
      });
    }

    return items;
  }, [
    chapterUpload.errorMessage,
    chapterUpload.isPending,
    chapterUpload.statusMessage,
    fileActions.status,
    isUploadOpen,
  ]);

  if (normalizedProjectId === null || normalizedChapterId === null) {
    return (
      <main className="page chapter-detail-page chapter-detail-page--state">
        <section className="panel chapter-detail-state-card chapter-detail-state-card--error">
          <div className="chapter-detail-state-card__icon">!</div>
          <h1 className="chapter-detail-state-card__title">Invalid chapter route</h1>
          <p className="chapter-detail-state-card__message">
            The selected project or chapter identifier is not valid.
          </p>
          <div className="chapter-detail-state-card__actions">
            <Link className="button" to={uiPaths.projects}>
              Back to projects
            </Link>
          </div>
        </section>
      </main>
    );
  }

  if (chapterDetailQuery.isPending || chapterFilesQuery.isPending) {
    return (
      <main className="page chapter-detail-page chapter-detail-page--state">
        <section className="panel chapter-detail-state-card">
          <div className="chapter-detail-state-card__icon">...</div>
          <h1 className="chapter-detail-state-card__title">Loading chapter</h1>
          <p className="chapter-detail-state-card__message">
            Fetching the chapter details and files.
          </p>
        </section>
      </main>
    );
  }

  if (chapterDetailQuery.isError || chapterFilesQuery.isError) {
    const error = chapterDetailQuery.error ?? chapterFilesQuery.error;

    return (
      <main className="page chapter-detail-page chapter-detail-page--state">
        <section className="panel chapter-detail-state-card chapter-detail-state-card--error">
          <div className="chapter-detail-state-card__icon">!</div>
          <h1 className="chapter-detail-state-card__title">Chapter detail unavailable</h1>
          <p className="chapter-detail-state-card__message">
            {getApiErrorMessage(
              error,
              "The chapter detail page could not be loaded.",
            )}
          </p>
          <div className="chapter-detail-state-card__actions">
            <button
              className="button"
              onClick={() => {
                void chapterDetailQuery.refetch();
                void chapterFilesQuery.refetch();
              }}
              type="button"
            >
              Retry
            </button>
            <Link className="button button--secondary" to={uiPaths.projectDetail(normalizedProjectId)}>
              Back to project
            </Link>
            <a
              className="button button--secondary"
              href={getSsrUrl(ssrPaths.chapterDetail(normalizedProjectId, normalizedChapterId))}
            >
              Open fallback chapter page
            </a>
          </div>
        </section>
      </main>
    );
  }

  if (!chapterDetailQuery.data || !chapterFilesQuery.data) {
    return (
      <main className="page chapter-detail-page chapter-detail-page--state">
        <section className="panel chapter-detail-state-card chapter-detail-state-card--error">
          <div className="chapter-detail-state-card__icon">!</div>
          <h1 className="chapter-detail-state-card__title">Chapter detail unavailable</h1>
          <p className="chapter-detail-state-card__message">
            No chapter detail data was returned for this view.
          </p>
          <div className="chapter-detail-state-card__actions">
            <Link className="button" to={uiPaths.projectDetail(normalizedProjectId)}>
              Back to project
            </Link>
          </div>
        </section>
      </main>
    );
  }

  const { project, chapter } = chapterDetailQuery.data;
  const files = chapterFilesQuery.data.files;
  const totalFiles = files.length;
  const filePaneLabel =
    selectedSection === "Overview" ? "Overview" : `${selectedSection} folder`;

  return (
    <main className="page chapter-detail-page">
      <div className="chapter-detail-shell">
        <div className="chapter-detail-commandbar">
          <div className="chapter-detail-commandbar__group">
            <button
              className="chapter-detail-commandbar__button chapter-detail-commandbar__button--primary"
              type="button"
              onClick={() => setIsUploadOpen(true)}
            >
              <span>Upload</span>
              <span className="chapter-detail-commandbar__chevron">v</span>
            </button>
          </div>

          <div className="chapter-detail-commandbar__group">
            <button className="chapter-detail-commandbar__button" disabled type="button">
              Delete
            </button>
            <button
              className="chapter-detail-commandbar__button"
              type="button"
              onClick={() => filePaneRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
            >
              Automate
            </button>
          </div>
        </div>

        <div className="chapter-detail-addressbar">
          <div className="chapter-detail-addressbar__nav">
            <Link className="chapter-detail-addressbar__nav-button" to={uiPaths.projectDetail(project.id)}>
              Back
            </Link>
            <button
              className="chapter-detail-addressbar__nav-button"
              type="button"
              onClick={() => window.location.reload()}
            >
              Reload
            </button>
          </div>

          <div className="chapter-detail-addressbar__path">
            <div className="chapter-detail-addressbar__segments">
              <Link className="chapter-detail-addressbar__link" to={uiPaths.projects}>
                Projects
              </Link>
              <span className="chapter-detail-addressbar__separator">/</span>
              <Link
                className="chapter-detail-addressbar__link"
                to={uiPaths.projectDetail(project.id)}
              >
                {project.code}
              </Link>
              <span className="chapter-detail-addressbar__separator">/</span>
              <span className="chapter-detail-addressbar__link">Chapter {chapter.number}</span>
              {selectedSection !== "Overview" ? (
                <>
                  <span className="chapter-detail-addressbar__separator">/</span>
                  <span>{selectedSection}</span>
                </>
              ) : null}
            </div>
          </div>

          <label className="chapter-detail-addressbar__search">
            <span className="visually-hidden">Search chapter files</span>
            <input
              placeholder={`Search Chapter ${chapter.number}`}
              type="search"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
          </label>
        </div>

        <div className="chapter-detail-explorer">
          <aside className="chapter-detail-sidebar">
            <div className="chapter-detail-sidebar__section-label">Chapter sections</div>
            <button
              className={`chapter-detail-sidebar__item${
                selectedSection === "Overview" ? " chapter-detail-sidebar__item--active" : ""
              }`}
              aria-pressed={selectedSection === "Overview"}
              type="button"
              onClick={() => setSelectedSection("Overview")}
            >
              <span>Overview</span>
            </button>
            {categoryOrder.map((category) => (
              <button
                className={`chapter-detail-sidebar__item${
                  selectedSection === category ? " chapter-detail-sidebar__item--active" : ""
                }`}
                aria-pressed={selectedSection === category}
                key={category}
                type="button"
                onClick={() => setSelectedSection(category)}
              >
                <span>{category}</span>
                <span className="chapter-detail-sidebar__count">
                  {chapter.category_counts[category]}
                </span>
              </button>
            ))}
          </aside>

          <section className="chapter-detail-main">
            <div className="chapter-detail-main__header">
              <div>
                <p className="chapter-detail-main__eyebrow">Chapter workspace</p>
                <h1 className="chapter-detail-main__title">
                  Chapter {chapter.number} - {chapter.title}
                </h1>
                <p className="chapter-detail-main__subtitle">
                  {project.code} / {filePaneLabel}
                </p>
              </div>
            </div>

            {statusBanners.length > 0 ? (
              <div className="chapter-detail-alerts">
                {statusBanners.map((status, index) => (
                  <div className={`status-banner status-banner--${status.tone}`} key={`${status.tone}-${index}`}>
                    {status.message}
                  </div>
                ))}
              </div>
            ) : null}

            <div className="chapter-detail-main__section">
              <ChapterMetadataPanel
                chapter={chapter}
                currentSection={selectedSection}
                projectCode={project.code}
                totalFiles={totalFiles}
              />
            </div>

            <div className="chapter-detail-main__section">
              <div className="chapter-detail-section-title">
                <div>
                  <h2>Folders</h2>
                  <p>Folder counts stay in view here. Use the left sidebar to change folders.</p>
                </div>
              </div>
              <ChapterCategorySummary
                counts={chapter.category_counts}
                selectedSection={selectedSection}
              />
            </div>

            <div className="chapter-detail-main__section">
              <ProcessingStatusPanel sectionLabel={filePaneLabel} status={structuringProcessing.status} />
            </div>

            <div className="chapter-detail-main__section" ref={filePaneRef}>
              <ChapterFilesTable
                chapterId={chapter.id}
                files={files}
                isActionPending={(fileId, action) => fileActions.isPending(fileId, action)}
                isProcessingPending={(fileId) => structuringProcessing.isPending(fileId)}
                onCancelCheckout={(file) => fileActions.handleCancelCheckout(file)}
                onCheckout={(file) => fileActions.handleCheckout(file)}
                onDelete={(file) => fileActions.handleDelete(file)}
                onDownload={(file) => fileActions.handleDownload(file)}
                onRunStructuring={(file) => structuringProcessing.startStructuring(file)}
                projectId={project.id}
                searchQuery={searchQuery}
                selectedSection={selectedSection}
              />
            </div>
          </section>
        </div>
      </div>

      {isUploadOpen ? (
        <div className="chapter-detail-modal-backdrop" role="presentation">
          <div
            aria-label="Upload files"
            className="chapter-detail-modal"
            role="dialog"
          >
            <ChapterUploadPanel
              activeTab={selectedSection === "Overview" ? preferredCategory : selectedSection}
              errorMessage={chapterUpload.errorMessage}
              isPending={chapterUpload.isPending}
              onClearResult={chapterUpload.clearResult}
              onClose={() => setIsUploadOpen(false)}
              onUpload={chapterUpload.submitUpload}
              result={chapterUpload.result}
              statusMessage={chapterUpload.statusMessage}
            />
          </div>
        </div>
      ) : null}
    </main>
  );
}
