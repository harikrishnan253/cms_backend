import { Link } from "react-router-dom";

import type { FileRecord } from "@/types/api";
import { uiPaths } from "@/utils/appPaths";
import type { ChapterSection } from "@/features/projects/components/ChapterCategorySummary";

type FileActionKind = "download" | "checkout" | "cancel_checkout" | "delete";

interface ChapterFilesTableProps {
  projectId: number;
  chapterId: number;
  files: FileRecord[];
  selectedSection: ChapterSection;
  searchQuery: string;
  isActionPending: (fileId: number, action: FileActionKind) => boolean;
  isProcessingPending: (fileId: number) => boolean;
  onDownload: (file: FileRecord) => void | Promise<void>;
  onCheckout: (file: FileRecord) => void | Promise<void>;
  onCancelCheckout: (file: FileRecord) => void | Promise<void>;
  onDelete: (file: FileRecord) => void | Promise<void>;
  onRunStructuring: (file: FileRecord) => void | Promise<void>;
}

function lockLabel(file: FileRecord) {
  if (!file.lock.is_checked_out) {
    return "Unlocked";
  }

  if (file.lock.checked_out_by_username) {
    return `Locked by ${file.lock.checked_out_by_username}`;
  }

  return "Locked";
}

export function ChapterFilesTable({
  projectId,
  chapterId,
  files,
  selectedSection,
  searchQuery,
  isActionPending,
  isProcessingPending,
  onDownload,
  onCheckout,
  onCancelCheckout,
  onDelete,
  onRunStructuring,
}: ChapterFilesTableProps) {
  const normalizedSearch = searchQuery.trim().toLowerCase();
  const selectedCategory = selectedSection === "Overview" ? null : selectedSection;
  const filteredFiles = files
    .filter((file) => selectedSection === "Overview" || file.category === selectedSection)
    .filter((file) => {
      if (!normalizedSearch) {
        return true;
      }

      return (
        file.filename.toLowerCase().includes(normalizedSearch) ||
        file.category.toLowerCase().includes(normalizedSearch) ||
        file.file_type.toLowerCase().includes(normalizedSearch)
      );
    })
    .sort((left, right) => {
      if (
        selectedCategory !== null &&
        left.category === selectedCategory &&
        right.category !== selectedCategory
      ) {
        return -1;
      }

      if (
        selectedCategory !== null &&
        left.category !== selectedCategory &&
        right.category === selectedCategory
      ) {
        return 1;
      }

      const categoryCompare = left.category.localeCompare(right.category);
      if (categoryCompare !== 0) {
        return categoryCompare;
      }

      return left.filename.localeCompare(right.filename);
    });

  const sectionTitle =
    selectedSection === "Overview" ? "Overview" : `${selectedSection} folder`;
  const sectionMessage =
    selectedSection === "Overview"
      ? "All chapter files in the current chapter."
      : `Files currently stored in ${selectedSection}.`;

  return (
    <section className="chapter-file-pane">
      <div className="chapter-file-pane__header">
        <div>
          <h2 className="chapter-file-pane__title">{sectionTitle}</h2>
          <p className="chapter-file-pane__subtitle">{sectionMessage}</p>
        </div>
        <span className="chapter-file-pane__count">
          {filteredFiles.length} item{filteredFiles.length === 1 ? "" : "s"}
        </span>
      </div>

      {filteredFiles.length === 0 ? (
        <div className="chapter-file-pane__empty">
          <p className="chapter-file-pane__empty-title">No files in this folder</p>
          <p className="chapter-file-pane__empty-copy">
            {normalizedSearch
              ? "No files matched the current search."
              : "This section currently has no file rows to display."}
          </p>
        </div>
      ) : (
        <div className="chapter-file-pane__table-wrap">
          <table className="chapter-file-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Category</th>
                <th>Type</th>
                <th>Version</th>
                <th>Lock</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredFiles.map((file) => (
                <tr key={file.id}>
                  <td>
                    <div className="chapter-file-table__name">
                      <strong>{file.filename}</strong>
                    </div>
                  </td>
                  <td>
                    <span
                      className={`badge${
                        selectedCategory !== null && file.category === selectedCategory
                          ? " badge--active"
                          : ""
                      }`}
                    >
                      {file.category}
                    </span>
                  </td>
                  <td>{file.file_type}</td>
                  <td>v{file.version}</td>
                  <td>{lockLabel(file)}</td>
                  <td>
                    <div className="table-actions">
                      <button
                        className="button button--secondary button--small"
                        disabled={isActionPending(file.id, "download")}
                        type="button"
                        onClick={() => void onDownload(file)}
                      >
                        {isActionPending(file.id, "download") ? "Downloading..." : "Download"}
                      </button>
                      {file.available_actions.includes("checkout") ? (
                        <button
                          className="button button--secondary button--small"
                          disabled={isActionPending(file.id, "checkout")}
                          type="button"
                          onClick={() => void onCheckout(file)}
                        >
                          {isActionPending(file.id, "checkout") ? "Checking out..." : "Checkout"}
                        </button>
                      ) : null}
                      {file.available_actions.includes("cancel_checkout") ? (
                        <button
                          className="button button--secondary button--small"
                          disabled={isActionPending(file.id, "cancel_checkout")}
                          type="button"
                          onClick={() => void onCancelCheckout(file)}
                        >
                          {isActionPending(file.id, "cancel_checkout")
                            ? "Cancelling..."
                            : "Cancel checkout"}
                        </button>
                      ) : null}
                      <button
                        className="button button--secondary button--small"
                        disabled={isActionPending(file.id, "delete")}
                        type="button"
                        onClick={() => void onDelete(file)}
                      >
                        {isActionPending(file.id, "delete") ? "Deleting..." : "Delete"}
                      </button>
                      <button
                        className="button button--secondary button--small"
                        disabled={isProcessingPending(file.id)}
                        type="button"
                        onClick={() => void onRunStructuring(file)}
                      >
                        {isProcessingPending(file.id) ? "Structuring..." : "Run structuring"}
                      </button>
                      {file.available_actions.includes("technical_edit") ? (
                        <Link
                          className="button button--secondary button--small"
                          to={uiPaths.technicalReview(projectId, chapterId, file.id)}
                        >
                          Technical review
                        </Link>
                      ) : null}
                      <Link
                        className="button button--secondary button--small"
                        to={uiPaths.structuringReview(projectId, chapterId, file.id)}
                      >
                        Structuring review
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
