interface ProcessingStatusPanelProps {
  sectionLabel: string;
  status:
    | {
        tone: "pending" | "success" | "error";
        message: string;
        compatibilityStatus?: string;
        derivedFilename?: string | null;
      }
    | null;
}

export function ProcessingStatusPanel({ sectionLabel, status }: ProcessingStatusPanelProps) {
  return (
    <section className="chapter-processing-panel">
      <div className="chapter-processing-panel__header">
        <h2>Processing status</h2>
        <span className="helper-text">Working in {sectionLabel}. Start structuring from a file row below.</span>
      </div>

      {status ? (
        <div className={`status-banner status-banner--${status.tone}`}>
          <strong>{status.message}</strong>
          {status.compatibilityStatus ? (
            <div className="helper-text">Status: {status.compatibilityStatus}</div>
          ) : null}
          {status.derivedFilename ? (
            <div className="helper-text">Output file: {status.derivedFilename}</div>
          ) : null}
        </div>
      ) : (
        <div className="chapter-processing-panel__empty">No structuring run started yet.</div>
      )}
    </section>
  );
}
