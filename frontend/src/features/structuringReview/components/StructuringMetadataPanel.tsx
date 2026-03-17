import type { StructuringReviewResponse } from "@/types/api";

interface StructuringMetadataPanelProps {
  review: StructuringReviewResponse;
}

export function StructuringMetadataPanel({ review }: StructuringMetadataPanelProps) {
  return (
    <aside className="structuring-review-sidebar">
      <section className="structuring-review-sidebar__panel">
        <h2>Review metadata</h2>
        <div className="structuring-review-meta-list">
          <article className="structuring-review-meta-list__item">
            <strong>Source file</strong>
            <span>{review.file.filename}</span>
          </article>
          <article className="structuring-review-meta-list__item">
            <strong>Processed file</strong>
            <span>{review.processed_file.filename}</span>
          </article>
          <article className="structuring-review-meta-list__item">
            <strong>Editor mode</strong>
            <span>{review.editor.mode}</span>
          </article>
          <article className="structuring-review-meta-list__item">
            <strong>WOPI mode</strong>
            <span>{review.editor.wopi_mode}</span>
          </article>
          <article className="structuring-review-meta-list__item">
            <strong>Save mode</strong>
            <span>{review.editor.save_mode}</span>
          </article>
        </div>
      </section>

      <section className="structuring-review-sidebar__panel">
        <h2>Styles</h2>
        <div className="structuring-review-style-list">
          {review.styles.map((style) => (
            <span className="structuring-review-style-chip" key={style}>
              {style}
            </span>
          ))}
        </div>
      </section>
    </aside>
  );
}
