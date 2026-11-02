import type { ReactNode } from "react";
import type { Value } from "./api";

export function projectLabel(project: Value): string {
  if (!project) return "Unknown source";
  let language = project.language;
  try {
    if (language)
      language = new Intl.DisplayNames(["en"], { type: "language" }).of(
        language,
      );
  } catch {
    /* Preserve uncommon language tags. */
  }
  return [project.title || "Untitled source", language]
    .filter(Boolean)
    .join(" · ");
}
export function presetLabel(name: string): string {
  const words = name.replace(/[_-]+/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
export function Help({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <details className="help">
      <summary aria-label={`About ${label}`}>?</summary>
      <div>{children}</div>
    </details>
  );
}
export function Allowance({ allowances }: { allowances?: Value }) {
  return allowances ? (
    <p className="allowance" role="status">
      Remaining today: <strong>{allowances.builds_remaining} books</strong> and{" "}
      <strong>
        {Math.floor(allowances.build_seconds_remaining / 60)} minutes
      </strong>{" "}
      of compilation time.
      <span className="hint">
        {" "}
        Time for books in progress is already deducted. Your allowance renews
        each day.
      </span>
    </p>
  ) : (
    <p className="hint">Sign in to see your remaining allowance.</p>
  );
}
export function PublishedPresets({
  presets,
  value,
  onChange,
}: {
  presets: Value[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label>
      Starting preset
      <select
        aria-label="Starting preset"
        value={value}
        onChange={(e) => {
          if (e.target.value !== "") onChange(e.target.value);
        }}
      >
        <option value="" disabled>
          Choose a preset…
        </option>
        {presets.map((p, i) => (
          <option key={p.name} value={String(i)}>
            {presetLabel(p.name)}
          </option>
        ))}
      </select>
      <span className="hint">
        A preset loads a starting set of choices. You can change them below.
      </span>
    </label>
  );
}
