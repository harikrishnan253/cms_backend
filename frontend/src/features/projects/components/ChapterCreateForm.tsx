import { useState } from "react";

interface ChapterCreateFormProps {
  isPending: boolean;
  onCancel?: () => void;
  onSubmit: (number: string, title: string) => Promise<unknown>;
}

export function ChapterCreateForm({ isPending, onCancel, onSubmit }: ChapterCreateFormProps) {
  const [number, setNumber] = useState("");
  const [title, setTitle] = useState("");

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedNumber = number.trim();
    const normalizedTitle = title.trim();
    if (!normalizedNumber || !normalizedTitle) {
      return;
    }

    await onSubmit(normalizedNumber, normalizedTitle);
    setNumber("");
    setTitle("");
  }

  return (
    <section className="project-detail-form-card">
      <div className="project-detail-form-card__header">
        <h3>Create New Chapter</h3>
        {onCancel ? (
          <button className="project-detail-form-card__close" type="button" onClick={onCancel}>
            ×
          </button>
        ) : null}
      </div>

      <form className="project-detail-form-card__form" onSubmit={handleSubmit}>
        <label className="field">
          <span>Chapter Number</span>
          <input
            className="search-input"
            disabled={isPending}
            placeholder="e.g. 01"
            type="text"
            value={number}
            onChange={(event) => setNumber(event.target.value)}
          />
        </label>
        <label className="field">
          <span>Chapter Title</span>
          <input
            className="search-input"
            disabled={isPending}
            placeholder="e.g. Introduction"
            type="text"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
        <div className="project-detail-form-card__actions">
          {onCancel ? (
            <button className="button button--secondary" type="button" onClick={onCancel}>
              Cancel
            </button>
          ) : null}
          <button className="button" disabled={isPending} type="submit">
            {isPending ? "Creating..." : "Create Chapter"}
          </button>
        </div>
      </form>
    </section>
  );
}
