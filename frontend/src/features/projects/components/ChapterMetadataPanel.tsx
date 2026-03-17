import type { ChapterSection } from "@/features/projects/components/ChapterCategorySummary";
import type { ChapterDetail } from "@/types/api";

interface ChapterMetadataPanelProps {
  chapter: ChapterDetail;
  currentSection: ChapterSection;
  projectCode: string;
  totalFiles: number;
}

const categoryOrder = [
  "Manuscript",
  "Art",
  "InDesign",
  "Proof",
  "XML",
  "Miscellaneous",
] as const;

export function ChapterMetadataPanel({
  chapter,
  currentSection,
  projectCode,
  totalFiles,
}: ChapterMetadataPanelProps) {
  const currentSectionLabel =
    currentSection === "Overview" ? "Overview" : `${currentSection} folder`;
  const visibleFileCount =
    currentSection === "Overview" ? totalFiles : chapter.category_counts[currentSection];

  return (
    <div className="chapter-detail-meta">
      <div className="chapter-detail-meta__header">
        <div>
          <p className="chapter-detail-meta__eyebrow">Chapter {chapter.number}</p>
          <h1 className="chapter-detail-meta__title">{chapter.title}</h1>
          <p className="chapter-detail-meta__subtitle">{projectCode}</p>
        </div>
      </div>

      <div className="chapter-detail-meta__grid">
        <article className="chapter-detail-meta__card chapter-detail-meta__card--accent">
          <strong>Current folder</strong>
          <span>{currentSectionLabel}</span>
        </article>
        <article className="chapter-detail-meta__card chapter-detail-meta__card--accent">
          <strong>Files in view</strong>
          <span>{visibleFileCount}</span>
        </article>
        <article className="chapter-detail-meta__card">
          <strong>All files</strong>
          <span>{totalFiles}</span>
        </article>
        {categoryOrder.map((category) => (
          <article
            className={`chapter-detail-meta__card${
              currentSection === category ? " chapter-detail-meta__card--selected" : ""
            }`}
            key={category}
          >
            <strong>{category}</strong>
            <span>{chapter.category_counts[category]}</span>
          </article>
        ))}
      </div>
    </div>
  );
}
