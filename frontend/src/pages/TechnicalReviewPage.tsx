import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getApiErrorMessage } from "@/api/client";
import { TechnicalIssuesForm } from "@/features/technicalReview/components/TechnicalIssuesForm";
import { useTechnicalApply } from "@/features/technicalReview/useTechnicalApply";
import { useTechnicalReviewQuery } from "@/features/technicalReview/useTechnicalReviewQuery";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { getSsrUrl, ssrPaths, uiPaths } from "@/utils/appPaths";

function buildInitialReplacements(
  issues: Array<{
    key: string;
    options: string[];
    found: string[];
  }>,
) {
  return issues.reduce<Record<string, string>>((accumulator, issue) => {
    accumulator[issue.key] = issue.options[0] ?? issue.found[0] ?? "";
    return accumulator;
  }, {});
}

export function TechnicalReviewPage() {
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
  const technicalReviewQuery = useTechnicalReviewQuery(normalizedFileId);
  const technicalApply = useTechnicalApply({
    projectId: normalizedProjectId,
    chapterId: normalizedChapterId,
    fileId: normalizedFileId,
  });
  const [replacements, setReplacements] = useState<Record<string, string>>({});

  useDocumentTitle(
    normalizedFileId === null
      ? "CMS UI Technical Review"
      : `CMS UI Technical Review ${normalizedFileId}`,
  );

  useEffect(() => {
    if (!technicalReviewQuery.data) {
      return;
    }

    setReplacements(buildInitialReplacements(technicalReviewQuery.data.issues));
  }, [technicalReviewQuery.data]);

  const canApply = useMemo(() => {
    const issues = technicalReviewQuery.data?.issues ?? [];
    if (issues.length === 0) {
      return false;
    }

    return issues.every((issue) => (replacements[issue.key] ?? "").trim().length > 0);
  }, [replacements, technicalReviewQuery.data?.issues]);

  if (normalizedProjectId === null || normalizedChapterId === null || normalizedFileId === null) {
    return (
      <main className="page technical-review-page technical-review-page--state">
        <section className="technical-review-state-card technical-review-state-card--error">
          <div className="technical-review-state-card__icon">!</div>
          <h1 className="technical-review-state-card__title">Invalid technical review route</h1>
          <p className="technical-review-state-card__message">
            The selected project, chapter, or file identifier is not valid.
          </p>
          <div className="technical-review-state-card__actions">
            <Link className="button" to={uiPaths.projects}>
              Back to projects
            </Link>
          </div>
        </section>
      </main>
    );
  }

  if (technicalReviewQuery.isPending) {
    return (
      <main className="page technical-review-page technical-review-page--state">
        <section className="technical-review-state-card">
          <div className="technical-review-state-card__spinner">...</div>
          <h1 className="technical-review-state-card__title">Scanning document for technical patterns...</h1>
          <p className="technical-review-state-card__message">
            Fetching normalized technical issues from /api/v2.
          </p>
        </section>
      </main>
    );
  }

  if (technicalReviewQuery.isError) {
    return (
      <main className="page technical-review-page technical-review-page--state">
        <section className="technical-review-state-card technical-review-state-card--error">
          <div className="technical-review-state-card__icon">!</div>
          <h1 className="technical-review-state-card__title">Technical review unavailable</h1>
          <p className="technical-review-state-card__message">
            {getApiErrorMessage(
              technicalReviewQuery.error,
              "The frontend shell could not load the technical review contract.",
            )}
          </p>
          <div className="technical-review-state-card__actions">
            <button className="button" onClick={() => void technicalReviewQuery.refetch()} type="button">
              Try Again
            </button>
            <Link
              className="button button--secondary"
              to={uiPaths.chapterDetail(normalizedProjectId, normalizedChapterId)}
            >
              Back to chapter
            </Link>
            <a
              className="button button--secondary"
              href={getSsrUrl(ssrPaths.chapterDetail(normalizedProjectId, normalizedChapterId))}
            >
              Open SSR chapter view
            </a>
          </div>
        </section>
      </main>
    );
  }

  if (!technicalReviewQuery.data) {
    return (
      <main className="page technical-review-page technical-review-page--state">
        <section className="technical-review-state-card technical-review-state-card--error">
          <div className="technical-review-state-card__icon">!</div>
          <h1 className="technical-review-state-card__title">Technical review unavailable</h1>
          <p className="technical-review-state-card__message">
            The technical review contract returned no data.
          </p>
          <div className="technical-review-state-card__actions">
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

  const { file, issues } = technicalReviewQuery.data;

  async function handleApply() {
    if (!canApply) {
      return;
    }

    await technicalApply.apply(replacements);
  }

  return (
    <main className="page technical-review-page">
      <div className="technical-review-shell">
        <header className="technical-review-header">
          <div>
            <h1>Technical Editing</h1>
            <p>
              File: <span>{file.filename}</span>
            </p>
          </div>

          <div className="technical-review-header__actions">
            <Link
              className="button button--secondary"
              to={uiPaths.chapterDetail(normalizedProjectId, normalizedChapterId)}
            >
              Cancel
            </Link>
            <button
              className="button"
              disabled={technicalApply.isPending || !canApply || issues.length === 0}
              type="button"
              onClick={() => void handleApply()}
            >
              {technicalApply.isPending ? "Processing..." : "Apply Changes"}
            </button>
          </div>
        </header>

        <div className="technical-review-content">
          {technicalApply.statusMessage ? (
            <div
              className={`status-banner ${
                technicalApply.isPending ? "status-banner--pending" : "status-banner--success"
              }`}
            >
              {technicalApply.statusMessage}
            </div>
          ) : null}

          {technicalApply.errorMessage ? (
            <div className="status-banner status-banner--error">{technicalApply.errorMessage}</div>
          ) : null}

          {technicalApply.result ? (
            <section className="technical-review-result">
              <h2>Apply result</h2>
              <div className="technical-review-result__grid">
                <article className="technical-review-result__card">
                  <strong>New file</strong>
                  <span>{technicalApply.result.new_file.filename}</span>
                </article>
                <article className="technical-review-result__card">
                  <strong>New file id</strong>
                  <span>{technicalApply.result.new_file_id}</span>
                </article>
              </div>
              <button
                className="button button--secondary"
                type="button"
                onClick={technicalApply.clearMessages}
              >
                Clear message
              </button>
            </section>
          ) : null}

          {issues.length === 0 ? (
            <section className="technical-review-empty">
              <div className="technical-review-empty__icon">OK</div>
              <p className="technical-review-empty__title">No technical editing issues found.</p>
              <p className="technical-review-empty__copy">
                The normalized issues list is empty for this file.
              </p>
            </section>
          ) : (
            <TechnicalIssuesForm
              canApply={canApply}
              isPending={technicalApply.isPending}
              issues={issues}
              onReplacementChange={(issueKey, value) =>
                setReplacements((current) => ({ ...current, [issueKey]: value }))
              }
              onSubmit={handleApply}
              replacements={replacements}
            />
          )}
        </div>
      </div>
    </main>
  );
}
