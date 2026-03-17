import type { ChapterCategoryCounts } from "@/types/api";

export type ChapterSection = "Overview" | keyof ChapterCategoryCounts;

interface ChapterCategorySummaryProps {
  counts: ChapterCategoryCounts;
  selectedSection: ChapterSection;
}

const orderedCategories: Array<keyof ChapterCategoryCounts> = [
  "Manuscript",
  "Art",
  "InDesign",
  "Proof",
  "XML",
  "Miscellaneous",
];

function categoryTone(category: keyof ChapterCategoryCounts) {
  switch (category) {
    case "Manuscript":
      return "manuscript";
    case "Art":
      return "art";
    case "InDesign":
      return "indesign";
    case "Proof":
      return "proof";
    case "XML":
      return "xml";
    default:
      return "misc";
  }
}

export function ChapterCategorySummary({ counts, selectedSection }: ChapterCategorySummaryProps) {
  const totalFiles = orderedCategories.reduce((sum, category) => sum + counts[category], 0);
  const selectedLabel =
    selectedSection === "Overview" ? "Viewing all folders" : `Viewing ${selectedSection} folder`;

  return (
    <div className="chapter-category-summary">
      <article
        className={`chapter-folder-tile${
          selectedSection === "Overview" ? " chapter-folder-tile--selected" : ""
        }`}
      >
        <span className="chapter-folder-tile__icon">Overview</span>
        <strong className="chapter-folder-tile__label">Overview</strong>
        <span className="chapter-folder-tile__count">{totalFiles} files</span>
        {selectedSection === "Overview" ? (
          <span className="chapter-folder-tile__status">{selectedLabel}</span>
        ) : null}
      </article>

      {orderedCategories.map((category) => (
        <article
          className={`chapter-folder-tile chapter-folder-tile--${categoryTone(category)}${
            selectedSection === category ? " chapter-folder-tile--selected" : ""
          }`}
          key={category}
        >
          <span className="chapter-folder-tile__icon">{category}</span>
          <strong className="chapter-folder-tile__label">{category}</strong>
          <span className="chapter-folder-tile__count">{counts[category]} files</span>
          {selectedSection === category ? (
            <span className="chapter-folder-tile__status">{selectedLabel}</span>
          ) : null}
        </article>
      ))}
    </div>
  );
}
