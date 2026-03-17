import { useEffect, useMemo, useRef, useState } from "react";

import type { FileUploadResponse } from "@/types/api";

const categoryOptions = [
  "Manuscript",
  "Art",
  "InDesign",
  "Proof",
  "XML",
  "Miscellaneous",
] as const;

interface ChapterUploadPanelProps {
  activeTab: string;
  isPending: boolean;
  result: FileUploadResponse | null;
  statusMessage: string | null;
  errorMessage: string | null;
  onUpload: (category: string, files: File[]) => Promise<unknown>;
  onClearResult: () => void;
  onClose?: () => void;
}

function uploadedItemLabel(item: FileUploadResponse["uploaded"][number]) {
  if (item.operation === "created") {
    return "Created";
  }

  if (item.archived_version_num !== null) {
    return `Replaced, archived v${item.archived_version_num}`;
  }

  return "Replaced";
}

export function ChapterUploadPanel({
  activeTab,
  isPending,
  result,
  statusMessage,
  errorMessage,
  onUpload,
  onClearResult,
  onClose,
}: ChapterUploadPanelProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [category, setCategory] = useState(
    categoryOptions.includes(activeTab as (typeof categoryOptions)[number])
      ? activeTab
      : "Manuscript",
  );
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);

  useEffect(() => {
    if (
      selectedFiles.length === 0 &&
      categoryOptions.includes(activeTab as (typeof categoryOptions)[number])
    ) {
      setCategory(activeTab);
    }
  }, [activeTab, selectedFiles.length]);

  const hasResult = result !== null || statusMessage !== null || errorMessage !== null;
  const canSubmit = selectedFiles.length > 0 && !isPending;
  const selectedLabel = useMemo(() => {
    if (selectedFiles.length === 0) {
      return "No files selected";
    }

    if (selectedFiles.length === 1) {
      return selectedFiles[0].name;
    }

    return `${selectedFiles.length} files selected`;
  }, [selectedFiles]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }

    try {
      await onUpload(category, selectedFiles);
      setSelectedFiles([]);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch {
      // The error message is surfaced via the hook state.
    }
  }

  return (
    <section className="chapter-upload-panel">
      <div className="chapter-upload-panel__header">
        <div>
          <h2>Upload files</h2>
          <span className="helper-text">Add files to the selected folder. Replacements keep version history.</span>
        </div>
        {onClose ? (
          <button
            className="chapter-upload-panel__close"
            disabled={isPending}
            type="button"
            onClick={onClose}
          >
            Close
          </button>
        ) : null}
      </div>

      <form className="upload-form chapter-upload-panel__form" onSubmit={handleSubmit}>
        <label className="field">
          <span>Category</span>
          <select
            className="select-input"
            disabled={isPending}
            value={category}
            onChange={(event) => setCategory(event.target.value)}
          >
            {categoryOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <label className="field field--grow">
          <span>Files</span>
          <input
            ref={fileInputRef}
            className="file-input"
            disabled={isPending}
            multiple
            type="file"
            onChange={(event) => setSelectedFiles(Array.from(event.target.files ?? []))}
          />
          <span className="helper-text">{selectedLabel}</span>
        </label>

        <div className="upload-actions">
          <button className="button" disabled={!canSubmit} type="submit">
            {isPending ? "Uploading..." : "Upload"}
          </button>
          {hasResult ? (
            <button
              className="button button--secondary"
              disabled={isPending}
              type="button"
              onClick={onClearResult}
            >
              Clear results
            </button>
          ) : null}
        </div>
      </form>

      {statusMessage ? (
        <div className={`status-banner ${isPending ? "status-banner--pending" : "status-banner--success"}`}>
          {statusMessage}
        </div>
      ) : null}
      {errorMessage ? <div className="status-banner status-banner--error">{errorMessage}</div> : null}

      {result ? (
        <div className="upload-results stack">
          <div className="upload-result-block">
            <h3>Uploaded</h3>
            {result.uploaded.length === 0 ? (
              <p className="helper-text">No files were uploaded.</p>
            ) : (
              <ul className="result-list">
                {result.uploaded.map((item) => (
                  <li className="result-item" key={`${item.file.id}-${item.file.version}`}>
                    <strong>{item.file.filename}</strong>
                    <span>{uploadedItemLabel(item)}</span>
                    <span className="helper-text">
                      {item.file.category} | v{item.file.version}
                    </span>
                    {item.archive_path ? (
                      <span className="helper-text">Archive: {item.archive_path}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="upload-result-block">
            <h3>Skipped</h3>
            {result.skipped.length === 0 ? (
              <p className="helper-text">No files were skipped.</p>
            ) : (
              <ul className="result-list">
                {result.skipped.map((item) => (
                  <li className="result-item" key={`${item.code}-${item.filename}`}>
                    <strong>{item.filename}</strong>
                    <span>{item.code}</span>
                    <span className="helper-text">{item.message}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}
