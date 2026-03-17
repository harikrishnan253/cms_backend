import type { TechnicalIssue } from "@/types/api";

interface TechnicalIssuesFormProps {
  issues: TechnicalIssue[];
  replacements: Record<string, string>;
  isPending: boolean;
  canApply: boolean;
  onReplacementChange: (issueKey: string, value: string) => void;
  onSubmit: () => void | Promise<void>;
}

function groupIssuesByCategory(issues: TechnicalIssue[]) {
  const groups = new Map<string, TechnicalIssue[]>();

  issues.forEach((issue) => {
    const key = issue.category?.trim() || "General";
    const existing = groups.get(key) ?? [];
    existing.push(issue);
    groups.set(key, existing);
  });

  return Array.from(groups.entries()).sort(([left], [right]) => left.localeCompare(right));
}

export function TechnicalIssuesForm({
  issues,
  replacements,
  isPending,
  canApply,
  onReplacementChange,
  onSubmit,
}: TechnicalIssuesFormProps) {
  const groupedIssues = groupIssuesByCategory(issues);

  return (
    <section className="technical-review-panel">
      <div className="technical-review-panel__info">
        <div className="technical-review-panel__info-icon">i</div>
        <div>
          <h2>Review Suggestions</h2>
          <p>
            The system has analyzed this document and found the following patterns. Select the
            preferred replacement for each item, then apply the current technical review contract.
          </p>
        </div>
      </div>

      <div className="technical-issue-groups">
        {groupedIssues.map(([category, categoryIssues]) => (
          <section className="technical-issue-group" key={category}>
            <div className="technical-issue-group__header">{category}</div>
            <div className="technical-issue-group__body">
              {categoryIssues.map((issue) => {
                const currentValue = replacements[issue.key] ?? "";
                const hasOptions = issue.options.length > 0;

                return (
                  <article className="technical-issue-row" key={issue.key}>
                    <div className="technical-issue-row__summary">
                      <div className="technical-issue-row__titleline">
                        <span className="technical-issue-row__count">{issue.count}</span>
                        <h3>{issue.label}</h3>
                      </div>
                      {issue.found.length > 0 ? (
                        <p className="technical-issue-row__found">
                          Found: <span>{issue.found.join(", ")}</span>
                        </p>
                      ) : null}
                    </div>

                    <div className="technical-issue-row__options">
                      {hasOptions ? (
                        issue.options.map((option) => (
                          <label className="technical-option" key={`${issue.key}-${option}`}>
                            <input
                              checked={currentValue === option}
                              disabled={isPending}
                              name={issue.key}
                              type="radio"
                              value={option}
                              onChange={(event) =>
                                onReplacementChange(issue.key, event.target.value)
                              }
                            />
                            <span>{option}</span>
                          </label>
                        ))
                      ) : (
                        <label className="field technical-issue-row__manual">
                          <span>Replacement</span>
                          <input
                            className="search-input"
                            disabled={isPending}
                            placeholder="Enter replacement"
                            type="text"
                            value={currentValue}
                            onChange={(event) =>
                              onReplacementChange(issue.key, event.target.value)
                            }
                          />
                        </label>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        ))}
      </div>

      <div className="technical-review-panel__actions">
        <button
          className="button"
          disabled={isPending || !canApply}
          type="button"
          onClick={() => void onSubmit()}
        >
          {isPending ? "Processing..." : "Apply Changes"}
        </button>
      </div>
    </section>
  );
}
