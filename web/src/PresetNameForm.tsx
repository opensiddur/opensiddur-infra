import { RequiredMark } from "./RequiredMark";
import React, { useId, useState } from "react";

export function PresetNameForm({ initialName = "", onSave, onCancel, disabled = false }: {
  initialName?: string;
  disabled?: boolean;
  onSave: (name: string) => Promise<void>;
  onCancel: () => void;
}) {
  const id = useId();
  const [name, setName] = useState(initialName);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <form className="preset-name-form" onSubmit={async (event) => {
      event.preventDefault();
      if (busy || disabled || !name.trim()) return;
      setBusy(true);
      setError("");
      try {
        await onSave(name.trim());
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Could not save preset. Try again.");
      } finally {
        setBusy(false);
      }
    }}>
      <label htmlFor={id}>Preset name<RequiredMark /></label>
      <input id={id} aria-required="true" aria-invalid={!name.trim() || undefined}
        className={!name.trim() ? "required-empty" : undefined} autoFocus required maxLength={200} value={name}
        disabled={busy} onChange={(event) => setName(event.target.value)} />
      {error && <p role="alert">{error}</p>}
      <div className="row">
        <button type="submit" disabled={busy || disabled || !name.trim()}>{busy ? "Saving…" : "Save"}</button>
        <button type="button" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}
