import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getApiErrorMessage } from "@/api/client";
import { StructuringMetadataPanel } from "@/features/structuringReview/components/StructuringMetadataPanel";
import { StructuringReturnAction } from "@/features/structuringReview/components/StructuringReturnAction";
import { StructuringSaveForm } from "@/features/structuringReview/components/StructuringSaveForm";
import { useStructuringReviewQuery } from "@/features/structuringReview/useStructuringReviewQuery";
import { useStructuringSave } from "@/features/structuringReview/useStructuringSave";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { uiPaths } from "@/utils/appPaths";

export function StructuringReviewPage() {
  const { projectId, chapterId, fileId } = useParams();
  const parsedProjectId = Number.parseInt(projectId ?? "", 10);
  const parsedChapterId = Number.parseInt(chapterId ?? "", 10);
  const parsedFileId = Number.parseInt(fileId ?? "", 10);
  const normalizedProjectId =
    Number.isInteger(parsedProjectId) && parsedProjectId > 0 ? parsedProjectId : null;
  const normalizedChapterId =
    Number.isInteger(parsedChapterId) && parsedChapterId > 0 ? parsedChapterId : null;
  const normalizedFileId =
    Number.isInteger(parsedFileId) && parsedFileId > 0 ? parsedFileId : null;
  const reviewQuery = useStructuringReviewQuery(normalizedFileId);
  const saveMutation = useStructuringSave(normalizedFileId);
  const [changesJson, setChangesJson] = useState("{}");
  const [parseError, setParseError] = useState<string | null>(null);

  useDocumentTitle(
    normalizedFileId === null
      ? "CMS UI Structuring Review"
      : `CMS UI Structuring Review ${normalizedFileId}`,
  );

  if (normalizedProjectId === null || normalizedChapterId === null || normalizedFileId === null) {
    return (
      <main className="page structuring-review-page structuring-review-page--state">
        <section className="structuring-review-state-card structuring-review-state-card--error">
          <div className="structuring-review-state-card__icon">!</div>
          <h1 className="structuring-review-state-card__title">Invalid structuring review route</h1>
          <p className="structuring-review-state-card__message">
            The selected project, chapter, or file identifier is not valid.
          </p>
          <div className="structuring-review-state-card__actions">
            <Link className="button" to={uiPaths.projects}>
              Back to projects
            </Link>
          </div>
        </section>
      </main>
    );
  }

  if (reviewQuery.isPending) {
    return (
      <main className="page structuring-review-page structuring-review-page--state">
        <section className="structuring-review-state-card">
          <div className="structuring-review-state-card__spinner">...</div>
          <h1 className="structuring-review-state-card__title">Loading structuring review</h1>
          <p className="structuring-review-state-card__message">
            Fetching the current /api/v2 structuring-review metadata contract.
          </p>
        </section>
      </main>
    );
  }

  if (reviewQuery.isError) {
    return (
      <main className="page structuring-review-page structuring-review-page--state">
        <section className="structuring-review-state-card structuring-review-state-card--error">
          <div className="structuring-review-state-card__icon">!</div>
          <h1 className="structuring-review-state-card__title">Structuring review unavailable</h1>
          <p className="structuring-review-state-card__message">
            {getApiErrorMessage(
              reviewQuery.error,
              "The frontend shell could not load the structuring review metadata.",
            )}
          </p>
          <div className="structuring-review-state-card__actions">
            <button className="button" onClick={() => void reviewQuery.refetch()} type="button">
              Retry
            </button>
            <Link
              className="button button--secondary"
              to={uiPaths.chapterDetail(normalizedProjectId, normalizedChapterId)}
            >
              Back to chapter
            </Link>
          </div>
        </section>
      </main>
    );
  }

  if (!reviewQuery.data) {
    return (
      <main className="page structuring-review-page structuring-review-page--state">
        <section className="structuring-review-state-card structuring-review-state-card--error">
          <div className="structuring-review-state-card__icon">!</div>
          <h1 className="structuring-review-state-card__title">Structuring review unavailable</h1>
          <p className="structuring-review-state-card__message">
            The structuring review contract returned no data.
          </p>
          <div className="structuring-review-state-card__actions">
            <Link
              className="button"
              to={uiPaths.chapterDetail(normalizedProjectId, normalizedChapterId)}
            >
              Back to chapter
            </Link>
          </div>
        </section>
      </main>
    );
  }

  const review = reviewQuery.data;

  async function handleSave() {
    setParseError(null);

    let parsedChanges: Record<string, unknown>;
    try {
      const parsed = JSON.parse(changesJson);
      if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
        setParseError("Changes must be a JSON object.");
        return;
      }
      parsedChanges = parsed as Record<string, unknown>;
    } catch {
      setParseError("Changes must be valid JSON.");
      return;
    }

    await saveMutation.save(review.actions.save_endpoint, parsedChanges);
  }

  return (
    <main className="page structuring-review-page">
      <div className="structuring-review-shell">
        <header className="structuring-review-toolbar">
          <div className="structuring-review-toolbar__title">
            <span aria-hidden="true" className="structuring-review-toolbar__icon">
              DOC
            </span>
            <div>
              <h1>{review.file.filename}</h1>
              <p>Structuring review shell</p>
            </div>
            {saveMutation.result ? (
              <span className="structuring-review-toolbar__saved">Saved</span>
            ) : null}
          </div>

          <div className="structuring-review-toolbar__actions">
            <StructuringReturnAction
              actions={review.actions}
              className="button button--secondary"
              label="Save & Exit"
            />
            <a className="button button--secondary" href={review.actions.export_href}>
              Export Word
            </a>
            <button className="button" disabled={saveMutation.isPending} type="button" onClick={() => void handleSave()}>
              {saveMutation.isPending ? "Saving..." : "Save Changes"}
            </button>
          </div>
        </header>

        <div className="structuring-review-body">
          <div className="structuring-review-main">
            {saveMutation.statusMessage ? (
              <div
                className={`status-banner ${
                  saveMutation.isPending ? "status-banner--pending" : "status-banner--success"
                }`}
              >
                {saveMutation.statusMessage}
              </div>
            ) : null}
            {saveMutation.errorMessage ? (
              <div className="status-banner status-banner--error">{saveMutation.errorMessage}</div>
            ) : null}
            {parseError ? <div className="status-banner status-banner--error">{parseError}</div> : null}

            <section className="structuring-review-editor-shell">
              {review.editor.collabora_url ? (
                <div className="structuring-review-launch">
                  <h2>Editor handoff</h2>
                  <p>
                    The editor remains backend-owned. Launch the backend-provided Collabora session
                    from this shell.
                  </p>
                  <a
                    className="button"
                    href={review.editor.collabora_url}
                    rel="noreferrer"
                    target="_blank"
                  >
                    Open provided editor URL
                  </a>
                </div>
              ) : (
                <div className="structuring-review-fallback">
                  <div className="structuring-review-fallback__icon">!</div>
                  <h2>LibreOffice Online not configured</h2>
                  <p>
                    The backend did not provide a Collabora launch URL. Export the processed file
                    or return to the chapter view.
                  </p>
                  <div className="structuring-review-fallback__actions">
                    <a className="button" href={review.actions.export_href}>
                      Download & Edit Locally
                    </a>
                    <StructuringReturnAction actions={review.actions} />
                  </div>
                </div>
              )}
            </section>

            <StructuringSaveForm
              isPending={saveMutation.isPending}
              onChange={setChangesJson}
              value={changesJson}
            />

            {saveMutation.result ? (
              <section className="structuring-review-result">
                <div className="structuring-review-result__header">
                  <h2>Save result</h2>
                  <button
                    className="button button--secondary"
                    type="button"
                    onClick={saveMutation.clearMessages}
                  >
                    Clear message
                  </button>
                </div>
                <div className="structuring-review-result__grid">
                  <article className="structuring-review-result__card">
                    <strong>Saved changes</strong>
                    <span>{saveMutation.result.saved_change_count}</span>
                  </article>
                  <article className="structuring-review-result__card">
                    <strong>Target file</strong>
                    <span>{saveMutation.result.target_filename}</span>
                  </article>
                </div>
              </section>
            ) : null}
          </div>

          <StructuringMetadataPanel review={review} />
        </div>
      </div>
    </main>
  );
}
