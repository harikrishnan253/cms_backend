interface StructuringSaveFormProps {
  value: string;
  isPending: boolean;
  onChange: (value: string) => void;
}

export function StructuringSaveForm({
  value,
  isPending,
  onChange,
}: StructuringSaveFormProps) {
  return (
    <section className="structuring-save-panel">
      <div className="structuring-save-panel__header">
        <h2>Manual save payload</h2>
        <span className="helper-text">Submit the current backend `changes` JSON object.</span>
      </div>

      <label className="field">
        <span>Changes JSON</span>
        <textarea
          className="textarea-input structuring-save-panel__textarea"
          disabled={isPending}
          rows={10}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      </label>
    </section>
  );
}
