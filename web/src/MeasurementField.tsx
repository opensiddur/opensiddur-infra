import React, { useEffect, useState } from "react";

type Model = { units: string[]; patterns: string[] };
export function measurementModel(variants: any[]): Model | undefined {
  const patterns = variants.map(v => v.pattern).filter((pattern): pattern is string => typeof pattern === "string" && pattern.includes("\\d"));
  const units = [...new Set(patterns.flatMap(pattern => {
    const suffix = pattern.match(/\(\?:([a-z]+(?:\|[a-z]+)*)\)\$$/);
    return suffix ? suffix[1].split("|") : pattern.endsWith("%$") ? ["%"] : [];
  }))];
  return units.length ? { units, patterns } : undefined;
}
const parse = (value: unknown) => typeof value === "string" ? value.match(/^(-?(?:\d+(?:\.\d+)?|\.\d+))([a-z]+|%)$/) : null;
export function MeasurementField({ id, label, value, defaultValue, model, named = [], nullable, required, onChange, reportPending, numericPoints = false, schema = {} }: {
  id: string; label: string; value: any; defaultValue: any; model: Model; named?: string[];
  nullable: boolean; required: boolean; onChange: (value: any) => void;
  reportPending: (id: string, pending: boolean) => void; numericPoints?: boolean; schema?: any;
}) {
  function initial(current: any) {
    const displayed = current === undefined ? defaultValue : current;
    const parts = parse(displayed);
    return {
      mode: current === undefined ? "default" : current === null ? "undefined" : named.includes(current) ? `named:${named.indexOf(current)}` : "measure",
      amount: numericPoints && typeof displayed === "number" ? String(displayed) : parts?.[1] || "",
      unit: parts?.[2] || model.units[0],
    };
  }
  const [draft, setDraft] = useState(() => initial(value));
  useEffect(() => setDraft(initial(value)), [value, defaultValue, model.units.join("|"), named.join("|")]);
  function valid(amount: string, unit: string) {
    if (!amount.trim() || !Number.isFinite(Number(amount)) || !model.units.includes(unit)) return false;
    const n = Number(amount);
    if (numericPoints) return !(schema.exclusiveMinimum !== undefined && n <= schema.exclusiveMinimum)
      && !(schema.minimum !== undefined && n < schema.minimum)
      && !(schema.maximum !== undefined && n > schema.maximum);
    return model.patterns.some(pattern => new RegExp(pattern).test(String(n) + unit));
  }
  const invalid = draft.mode === "measure" && !valid(draft.amount, draft.unit);
  useEffect(() => {
    reportPending(id + "-measurement", invalid);
    return () => reportPending(id + "-measurement", false);
  }, [id, invalid, reportPending]);
  function edit(amount: string, unit: string) {
    setDraft({ mode: "measure", amount, unit });
    if (valid(amount, unit)) onChange(numericPoints ? Number(amount) : String(Number(amount)) + unit);
  }
  function reset(next: null | undefined) { setDraft(initial(next)); onChange(next); }
  return <div className="field">
    <label htmlFor={named.length ? id + "-choice" : id}>{label}{required && <span className="required-mark" aria-label="required"> *</span>}</label>
    {named.length > 0 && <select id={id + "-choice"} aria-label={label + " choice"} value={draft.mode} onChange={e => {
      const mode = e.target.value;
      if (mode === "default") reset(undefined);
      else if (mode === "undefined") reset(null);
      else if (mode.startsWith("named:")) { setDraft(old => ({ ...old, mode })); onChange(named[Number(mode.slice(6))]); }
      else { setDraft(old => ({ ...old, mode: "measure" })); if (valid(draft.amount, draft.unit)) onChange(String(Number(draft.amount)) + draft.unit); }
    }}>
      <option value="default">(default)</option>
      {named.map((name, index) => <option key={name} value={`named:${index}`}>{name}</option>)}
      <option value="measure">Custom measurement…</option>
      {nullable && <option value="undefined">(undefined)</option>}
    </select>}
    {(!named.length || draft.mode === "measure") && <div className="measurement-row">
      <input id={id} aria-label={label + (named.length ? " amount" : "")} type="number" step="any"
        min={numericPoints ? schema.minimum ?? schema.exclusiveMinimum : model.patterns.some(pattern => new RegExp(pattern).test("-1" + draft.unit)) ? undefined : 0}
        aria-invalid={invalid || undefined} aria-required={required || undefined}
        aria-describedby={invalid ? id + "-error" : undefined} className={invalid ? "required-empty" : undefined}
        value={draft.amount} placeholder={draft.mode === "undefined" ? "(undefined)" : "(default)"}
        onChange={e => edit(e.target.value, draft.unit)} />
      <select aria-label={label + " unit"} value={draft.unit} onChange={e => edit(draft.amount, e.target.value)}>
        {!model.units.includes(draft.unit) && <option value={draft.unit} disabled>{draft.unit} (invalid)</option>}
        {model.units.map(unit => <option key={unit} value={unit}>{unit}</option>)}
      </select>
    </div>}
    {invalid && <p id={id + "-error"} className="field-error" role="alert">Enter a valid number and choose a unit, or reset to (default).</p>}
    {!named.length && <div className="row wrap">
      <button type="button" onClick={() => reset(undefined)}>(default)</button>
      {nullable && <button type="button" onClick={() => reset(null)}>(undefined)</button>}
    </div>}
    {defaultValue != null && <p className="hint">Default: {String(defaultValue)}{numericPoints ? "pt" : ""}.</p>}
  </div>;
}
