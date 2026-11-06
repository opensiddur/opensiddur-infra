import { SearchSelect } from "./SearchSelect";
import { RequiredMark } from "./RequiredMark";
import React, { useId, useState } from "react";

export function PresetNameForm({ initialName = "", onSave, onCancel, disabled = false, presets = [] }: {
  initialName?: string;
  disabled?: boolean;
  presets?: { id: string; name: string }[];
  onSave: (name: string, existingId?: string) => Promise<void>;
  onCancel: () => void;
}) {
  const id = useId();
  const [name, setName] = useState(initialName);
  const [chosenId, setChosenId] = useState<string>();
  const matching = presets.filter((preset) => preset.name === name.trim());
  const target = matching.find((preset) => preset.id === chosenId) || (matching.length === 1 ? matching[0] : undefined);
  const ambiguous = matching.length > 1 && !target;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <form className="preset-name-form" onSubmit={async (event) => {
      event.preventDefault();
      if (busy || disabled || ambiguous || !name.trim()) return;
      setBusy(true);
      setError("");
      try {
        await onSave(name.trim(), target?.id);
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Could not save preset. Try again.");
      } finally {
        setBusy(false);
      }
    }}>
      {presets.length > 0 ? <>
        <SearchSelect id={id} label="Preset name" required allowCustom autoFocus maxLength={200}
          options={presets.map((preset) => ({ value: preset.id, label: preset.name }))}
          value={target?.id || ""} textValue={name} disabled={busy}
          onTextChange={(value) => { setName(value); setChosenId(undefined); }}
          onSelect={(presetId) => {
            const preset = presets.find((item) => item.id === presetId);
            if (preset) { setChosenId(presetId); setName(preset.name); }
          }} />
        <p className="hint">{ambiguous ? "Choose an existing preset from the list to replace it."
          : target ? `Saving will replace the settings in “${target.name}”.`
          : "Type a new name to create a preset, or choose an existing preset to replace it."}</p>
      </> : <>
      <label htmlFor={id}>Preset name<RequiredMark /></label>
      <input id={id} aria-required="true" aria-invalid={!name.trim() || undefined}
        className={!name.trim() ? "required-empty" : undefined} autoFocus required maxLength={200} value={name}
        disabled={busy} onChange={(event) => setName(event.target.value)} />
      </>}
      {error && <p role="alert">{error}</p>}
      <div className="row">
        <button type="submit" disabled={busy || disabled || ambiguous || !name.trim()}>{busy ? "Saving…" : "Save"}</button>
        <button type="button" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}
