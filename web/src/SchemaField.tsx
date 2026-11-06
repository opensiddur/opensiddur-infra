import { MeasurementField, measurementModel } from "./MeasurementField";
import { FontSelect, RunningHeadHelp, TypographyMetadata, templateError } from "./TypographyControls";
import { RequiredMark } from "./RequiredMark";
import { SettingHelp } from "./BuilderControls";
import { createContext, useContext, useEffect, useId, useState } from "react";
export const SettingsEditContext = createContext<
  (id: string, pending: boolean) => void
>(() => {});
import type { Value } from "./api";

/** Reference-site defaults/descriptions override the reusable definition. */
export function resolve(schema: Value, root: Value): Value {
  if (!schema) return {};
  if (!schema.$ref) return schema;
  const { $ref, ...site } = schema;
  return { ...resolve(root.$defs?.[$ref.split("/").at(-1)], root), ...site };
}
function matches(schema: Value, value: Value): boolean {
  if (schema.enum) return schema.enum.some((v: Value) => Object.is(v, value));
  if (Object.hasOwn(schema, "const")) return Object.is(schema.const, value);
  if (schema.type === "null") return value === null;
  if (schema.type === "array") return Array.isArray(value);
  if (schema.type === "object" || schema.properties)
    return value !== null && typeof value === "object" && !Array.isArray(value);
  return (
    schema.type === typeof value ||
    (schema.type === "integer" && Number.isInteger(value))
  );
}
function shape(schema: Value, root: Value, value: Value) {
  const base = resolve(schema, root);
  const variants = (base.anyOf || base.oneOf || [base]).map((v: Value) =>
    resolve(v, root),
  );
  const nonNull = variants.filter((v: Value) => v.type !== "null");
  const selected =
    nonNull.find((v: Value) => matches(v, value)) || nonNull[0] || variants[0];
  return {
    schema: { ...selected, ...base },
    variants,
    nullable: variants.some((v: Value) => v.type === "null"),
  };
}
export function validDraft(schema: Value, root: Value, value: Value): boolean {
  if (value === undefined) return false;
  const base = resolve(schema, root);
  if (base.anyOf || base.oneOf)
    return (base.anyOf || base.oneOf).some((v: Value) =>
      validDraft(
        {
          ...resolve(v, root),
          ...Object.fromEntries(
            Object.entries(base).filter(
              ([k]) => !["anyOf", "oneOf"].includes(k),
            ),
          ),
        },
        root,
        value,
      ),
    );
  if (base.enum && !base.enum.some((v: Value) => Object.is(v, value)))
    return false;
  if (Object.hasOwn(base, "const") && !Object.is(base.const, value))
    return false;
  if (base.type && !matches({ ...base, enum: undefined }, value)) return false;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return false;
    if (
      base.multipleOf &&
      Math.abs(value / base.multipleOf - Math.round(value / base.multipleOf)) >
        1e-9
    )
      return false;
    if (
      (base.minimum !== undefined && value < base.minimum) ||
      (base.maximum !== undefined && value > base.maximum) ||
      (base.exclusiveMinimum !== undefined && value <= base.exclusiveMinimum) ||
      (base.exclusiveMaximum !== undefined && value >= base.exclusiveMaximum)
    )
      return false;
  }
  if (typeof value === "string") {
    if (
      value.length < (base.minLength || 0) ||
      (base.maxLength !== undefined && value.length > base.maxLength)
    )
      return false;
    try {
      if (base.pattern && !new RegExp(base.pattern).test(value)) return false;
    } catch {
      /* Server validation remains authoritative. */
    }
  }
  if (Array.isArray(value))
    return (
      value.length >= (base.minItems || 0) &&
      (base.maxItems === undefined || value.length <= base.maxItems) &&
      value.every((v) => validDraft(base.items || {}, root, v))
    );
  if (value && typeof value === "object") {
    if ((base.required || []).some((key: string) => !Object.hasOwn(value, key)))
      return false;
    return Object.entries(value).every(([key, v]) =>
      base.properties?.[key]
        ? validDraft(base.properties[key], root, v)
        : base.additionalProperties === false
          ? false
          : typeof base.additionalProperties === "object"
            ? validDraft(base.additionalProperties, root, v)
            : true,
    );
  }
  return true;
}
export function numericChoices(
  schema: Value,
): { values: number[]; custom: boolean } | null {
  const low = schema.minimum ?? schema.exclusiveMinimum;
  const high = schema.maximum ?? schema.exclusiveMaximum;
  if (!Number.isFinite(low) || !Number.isFinite(high)) return null;
  const step = schema.multipleOf || (schema.type === "integer" ? 1 : undefined);
  if (step) {
    const nearInteger = (v: number) =>
      Math.abs(v - Math.round(v)) < 1e-10 ? Math.round(v) : v;
    const first =
      schema.exclusiveMinimum !== undefined
        ? Math.floor(nearInteger(low / step)) + 1
        : Math.ceil(nearInteger(low / step));
    const last =
      schema.exclusiveMaximum !== undefined
        ? Math.ceil(nearInteger(high / step)) - 1
        : Math.floor(nearInteger(high / step));
    const count = last - first + 1;
    if (count >= 0 && count <= 1000)
      return {
        values: Array.from({ length: count }, (_, i) =>
          Number(((first + i) * step).toPrecision(12)),
        ),
        custom: false,
      };
  }
  // Continuous/large ranges retain arbitrary valid values through a custom field.
  return {
    values: [
      ...new Set(
        [schema.minimum, schema.default, schema.maximum].filter(
          (v) => typeof v === "number" && v >= low && v <= high,
        ),
      ),
    ] as number[],
    custom: true,
  };
}
const objectValue = (value: Value) =>
  value && typeof value === "object" && !Array.isArray(value) ? value : {};

const FieldPath = createContext<string[]>([]);
const fieldHelp: Record<string, string> = {
  project: "Choose the source project that supplies the structure and starting text for the book.",
  file_name: "Choose the XML entry point within the starting project.",
  title: "Set the title displayed for this book.",
  transclusion: "Choose source projects in order of preference for included passages.",
  instructions: "Choose source projects in order of preference for recitation instructions.",
  projects: "Choose translation projects in order of preference.",
  notice: "Choose how attribution and licensing are displayed in the book.",
  back_notice: "Choose the notice shown at the end of the book.",
  electronic: "Set the behavior of the reflowable HTML book.",
  print: "Set the option used for printed output.",
  logo: "Choose the logo shown with the publication notice.",
  position: "Choose where the notice appears in the book.",
  text: "Enter the text that appears in this part of the book.",
  day: "Choose the initial calendar setting for the electronic book.",
  columns: "Choose how parallel text is displayed when the HTML book opens.",
  psalm_titles: "Choose how psalm titles appear in the electronic book.",
  commentary: "Control whether repeated commentary appears only once.",
  editorial: "Control whether repeated editorial notes appear only once.",
  all: "Apply this header or footer to every page.",
  odd: "Apply this header or footer to odd pages.",
  even: "Apply this header or footer to even pages.",
  language: "Set the language of this text, for example en for English or he for Hebrew.",
  if: "Show this part of the header or footer only when the placeholder has a value.",
  normal_size: "Set the normal print size for this font in points.",
};
const fontPriorityHelp = "Fonts are tried in order, starting with the preferred font. An alternative supplies characters the browser cannot display with an earlier font.";
export function SchemaField(props: Parameters<typeof SchemaFieldInner>[0]) {
  const parent = useContext(FieldPath);
  return <FieldPath.Provider value={[...parent, props.label.replaceAll(" ", "_")]}><SchemaFieldInner {...props} /></FieldPath.Provider>;
}
function SchemaFieldInner({
  schema,
  root,
  value,
  onChange,
  label,
  advanced = true,
  expanded = false,
  required = false,
  showDefaultValue = false,
}: {
  schema: Value;
  root: Value;
  value: Value;
  onChange: (v: Value) => void;
  label: string;
  advanced?: boolean;
  expanded?: boolean;
  required?: boolean;
  showDefaultValue?: boolean;
}) {
  const id = useId();
  const path = useContext(FieldPath);
  const metadata = useContext(TypographyMetadata);
  const runningHead = path.includes("page_header") || path.includes("page_footer");
  const template = runningHead && ["text", "if"].includes(path.at(-1) || "");
  const fieldError = template && typeof value === "string" ? templateError(value, metadata.codes)
    : runningHead && path.at(-1) === "language" && value != null && !/^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{1,8})*$/.test(value)
      ? "Use a language tag such as en for English or he for Hebrew." : undefined;
  const [newKey, setNewKey] = useState("");
  const [draftKey, setDraftKey] = useState("");
  const [draft, setDraft] = useState<Value>();
  const [adding, setAdding] = useState(false);
  const [custom, setCustom] = useState(false);
  const [objectDraft, setObjectDraft] = useState<Value>();
  const reportPending = useContext(SettingsEditContext);
  const pending = objectDraft !== undefined || adding || !!draftKey || !!fieldError;
  useEffect(() => {
    reportPending(id, pending);
    return () => reportPending(id, false);
  }, [reportPending, id, pending]);
  const valueSignature = JSON.stringify(value);
  useEffect(() => {
    setObjectDraft(undefined);
    setAdding(false);
    setDraftKey("");
  }, [valueSignature]);
  const model = shape(schema, root, value),
    s = model.schema;
  const isRequired = required && !Object.hasOwn(s, "default");
  const missingRequired = isRequired && (value === undefined || (value === "" && !validDraft(schema, root, value)));
  const fieldLabel = <>{label}{isRequired && <RequiredMark />}</>;
  const objectSchema = model.variants.find(
    (v: Value) => v.type === "object" || v.properties,
  );
  const literals = model.variants.flatMap(
    (v: Value) => v.enum || (Object.hasOwn(v, "const") ? [v.const] : []),
  );
  const reset = (
    <button
      type="button"
      className="use-default"
      onClick={() => {
        onChange(undefined);
        setCustom(false);
        setObjectDraft(undefined);
        setAdding(false);
        setDraftKey("");
      }}
    >
      {showDefaultValue ? `Reset to ${s.default == null ? "(undefined)" : typeof s.default === "boolean" ? (s.default ? "Yes" : "No") : String(s.default)}` : "(default)"}
    </button>
  );
  const help = s.description || fieldHelp[path.at(-1) || ""] ||
    (objectSchema ? `Settings that control ${label}.` : `Choose a value for ${label}, or use the default supplied by the builder.`);
  if (objectSchema) {
    const group = { ...objectSchema, ...resolve(schema, root) };
    const properties = path.length === 2 && path[0] === "typography" && path[1] === "fonts" &&
      group.additionalProperties && typeof group.additionalProperties === "object"
      ? { latin: group.additionalProperties, hebrew: group.additionalProperties, ...group.properties }
      : group.properties || {};
    const current = objectDraft || objectValue(value);
    const set = (key: string, next: Value) => {
      const result = { ...current };
      if (next === undefined) delete result[key];
      else result[key] = next;
      if (
        !Object.keys(result).length ||
        (next === undefined &&
          (group.required || []).some((k: string) => !Object.hasOwn(result, k)))
      ) {
        setObjectDraft(undefined);
        onChange(undefined);
      } else if (validDraft(group, root, result)) {
        setObjectDraft(undefined);
        onChange(result);
      } else setObjectDraft(result);
    };
    const isObject =
      value !== null && typeof value === "object" && !Array.isArray(value);
    return (
      <details
        className="field field-group"
        open={
          expanded || value !== undefined || custom || objectDraft !== undefined
        }
      >
        <summary>
          {fieldLabel}
          {value === undefined && <span className="hint"> (default)</span>}
          {runningHead && ["page_header", "page_footer"].includes(path.at(-1) || "")
            ? <RunningHeadHelp label={label} codes={metadata.codes} />
            : <SettingHelp label={label}>{help}</SettingHelp>}
        </summary>
        {reset}
        {objectDraft !== undefined && (
          <p className="hint" role="status">
            Complete valid values to apply these changes.
          </p>
        )}
        {(literals.length > 0 || model.nullable) && (
          <label>
            Value
            <select
              aria-label={`${label} value`}
              value={
                custom || isObject
                  ? "object"
                  : value === undefined
                    ? ""
                    : value === null
                      ? "null"
                      : String(
                          literals.findIndex((v: Value) => Object.is(v, value)),
                        )
              }
              onChange={(e) => {
                if (e.target.value === "object") setCustom(true);
                else {
                  setCustom(false);
                  onChange(
                    e.target.value === ""
                      ? undefined
                      : e.target.value === "null"
                        ? null
                        : literals[Number(e.target.value)],
                  );
                }
              }}
            >
              <option value="">(default)</option>
              <option value="object">Custom settings</option>
              {literals.map((v: Value, i: number) => (
                <option key={i} value={String(i)}>
                  {String(v)}
                </option>
              ))}
              {model.nullable && <option value="null">(undefined)</option>}
            </select>
          </label>
        )}
        {(value === undefined ||
          isObject ||
          custom ||
          objectDraft !== undefined) && (
          <div className="nested">
            {Object.entries(properties).map(([key, child]) => (
              <SchemaField
                key={key}
                advanced={advanced}
                schema={child}
                root={root}
                value={current[key]}
                label={key.replaceAll("_", " ")}
                required={(group.required || []).includes(key) &&
                  (required || value !== undefined || objectDraft !== undefined || expanded || custom)}
                onChange={(v) => set(key, v)}
              />
            ))}
            {group.additionalProperties && (
              <>
                {Object.entries(current)
                  .filter(([key]) => !Object.hasOwn(properties, key))
                  .map(([key, v]) => (
                    <SchemaField
                      key={key}
                      advanced={advanced}
                      schema={
                        typeof group.additionalProperties === "object"
                          ? group.additionalProperties
                          : {}
                      }
                      root={root}
                      value={v}
                      label={key}
                      onChange={(v) => set(key, v)}
                    />
                  ))}
                {advanced && (
                  <div className="property-draft">
                    <label>
                      Setting name
                      <input
                        value={newKey}
                        onChange={(e) => setNewKey(e.target.value)}
                      />
                    </label>
                    <button
                      type="button"
                      disabled={
                        !newKey.trim() || Object.hasOwn(current, newKey.trim()) ||
                        Object.hasOwn(properties, newKey.trim())
                      }
                      onClick={() => {
                        setDraftKey(newKey.trim());
                        setDraft(undefined);
                      }}
                    >
                      Edit new setting
                    </button>
                    {draftKey && (
                      <>
                        <SchemaField
                          expanded
                          schema={
                            typeof group.additionalProperties === "object"
                              ? group.additionalProperties
                              : {}
                          }
                          root={root}
                          value={draft}
                          onChange={setDraft}
                          label={draftKey}
                          required
                          advanced={advanced}
                        />
                        <button
                          disabled={
                            !validDraft(group.additionalProperties, root, draft)
                          }
                          onClick={() => {
                            set(draftKey, draft);
                            setDraftKey("");
                            setNewKey("");
                          }}
                        >
                          Add setting
                        </button>
                        <button onClick={() => setDraftKey("")}>Cancel</button>
                      </>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </details>
    );
  }
  if (s.type === "array") {
    const entries = Array.isArray(value) ? value : [];
    const fontFamily = path.length === 4 && path[0] === "typography" &&
      path[1] === "fonts" && path[3] === "names" ? path[2] : undefined;
    const defaultFont = fontFamily && metadata.fonts?.defaults?.[fontFamily];
    const remove = (index: number) => {
      const next = entries.filter((_: Value, i: number) => i !== index);
      onChange(next.length < (s.minItems || 0) ? undefined : next);
    };
    return (
      <details
        className="field field-group"
        open={!!fontFamily || expanded || value !== undefined || adding}
      >
        <summary>
          {fontFamily ? "Font priority" : fieldLabel}
          {!fontFamily && value === undefined && <span className="hint"> (default)</span>}
          <SettingHelp label={fontFamily ? "Font priority" : label}>
            {fontFamily ? fontPriorityHelp : help}
          </SettingHelp>
        </summary>
        {(!fontFamily || entries.length > 0) && reset}
        {fontFamily && entries.length === 0 && (
          <FontSelect
            id={id}
            label="Preferred font"
            family={fontFamily}
            catalog={metadata.fonts}
            required={false}
            help="Choose the first font to try for this script. Default uses the compiler’s built-in font."
            onChange={(name) => onChange(name ? [{ name }] : undefined)}
          />
        )}
        {entries.map((v: Value, i: number) => (
          <div className="array-item" key={i}>
            <SchemaField
              advanced={advanced}
              schema={s.items || {}}
              root={root}
              value={v}
              label={fontFamily ? i === 0 ? "Preferred font" : `Alternative font ${i}` : `Item ${i + 1}`}
              expanded={!!fontFamily}
              required
              onChange={(v) =>
                v === undefined
                  ? remove(i)
                  : onChange(
                      entries.map((old: Value, j: number) =>
                        j === i ? v : old,
                      ),
                    )
              }
            />
            {(!fontFamily || i > 0) && (
              <button onClick={() => remove(i)}>
                {fontFamily ? `Remove alternative ${i}` : `Remove item ${i + 1}`}
              </button>
            )}
          </div>
        ))}
        {!(s.minItems > 0) && (
          <button onClick={() => onChange([])}>No items</button>
        )}
        <button
          disabled={!!fontFamily && !entries.length && !defaultFont}
          onClick={() => {
            setAdding(true);
            setDraft(undefined);
          }}
        >
          {fontFamily ? "Add alternative font" : "Add item"}
        </button>
        {adding && (
          <div className="item-draft">
            <SchemaField
              expanded
              advanced={advanced}
              schema={s.items || {}}
              root={root}
              value={draft}
              label={fontFamily ? "New alternative font" : "New item"}
              required
              onChange={setDraft}
            />
            {!fontFamily && <p className="hint">
              Complete the item before adding it to your settings.
            </p>}
            <button
              disabled={!validDraft(s.items || {}, root, draft)}
              onClick={() => {
                const preferred = !entries.length && defaultFont ? [{ name: defaultFont }] : entries;
                onChange([...preferred, draft]);
                setAdding(false);
              }}
            >
              {fontFamily ? "Add alternative" : "Add to list"}
            </button>
            <button onClick={() => setAdding(false)}>Cancel</button>
          </div>
        )}
      </details>
    );
  }
  const fontRoot = path.indexOf("fonts");
  if (fontRoot >= 0 && path.includes("names") && path.at(-1) === "name") {
    return <FontSelect id={id} label={fieldLabel} value={value} family={path[fontRoot + 1]}
      catalog={metadata.fonts} onChange={onChange} required={isRequired}
      help="Choose an installed font for this position in the priority list." />;
  }
  const numericPoints = fontRoot >= 0 && path.at(-1) === "normal_size";
  const measurement = measurementModel(model.variants);
  if (measurement || numericPoints) {
    return <MeasurementField id={id} label={label} value={value} defaultValue={s.default}
      model={measurement || { units: ["pt"], patterns: [] }} named={literals.filter((v: Value) => typeof v === "string")}
      nullable={model.nullable} required={isRequired} numericPoints={numericPoints} schema={s}
      onChange={onChange} reportPending={reportPending} help={help} />;
  }
  const range =
    s.type === "integer" || s.type === "number" ? numericChoices(s) : null;
  const choices = literals.length
    ? literals
    : s.type === "boolean"
      ? [true, false]
      : range?.values;
  const displayedValue = showDefaultValue && value === undefined ? s.default ?? null : value;
  const index = choices?.findIndex((v: Value) => Object.is(v, displayedValue)) ?? -1;
  let editor;
  if (choices) {
    const mode =
      value === undefined && !custom && !showDefaultValue
        ? ""
        : displayedValue === null && model.nullable
          ? "null"
          : custom || (range?.custom && index < 0)
            ? "custom"
            : index >= 0
              ? String(index)
              : "invalid";
    editor = (
      <>
        <select
          id={id}
          aria-required={isRequired || undefined}
          aria-invalid={missingRequired || !!fieldError || undefined}
          className={missingRequired || fieldError ? "required-empty" : undefined}
          value={mode}
          onChange={(e) => {
            if (e.target.value === "custom") setCustom(true);
            else {
              setCustom(false);
              onChange(
                e.target.value === ""
                  ? undefined
                  : e.target.value === "null"
                    ? null
                    : choices[Number(e.target.value)],
              );
            }
          }}
        >
          {!showDefaultValue && <option value="">(default)</option>}
          {choices.map((v: Value, i: number) => (
            <option key={i} value={String(i)}>
              {typeof v === "boolean" ? (v ? "Yes" : "No") : String(v)}
            </option>
          ))}
          {model.nullable && <option value="null">(undefined)</option>}
          {range?.custom && <option value="custom">Custom value…</option>}
          {mode === "invalid" && (
            <option value="invalid" disabled>
              {String(value)} (invalid)
            </option>
          )}
        </select>
        {mode === "custom" && (
          <input
            aria-label={`${label} custom value`}
            aria-required={isRequired || undefined}
            aria-invalid={missingRequired || !!fieldError || undefined}
            className={missingRequired || fieldError ? "required-empty" : undefined}
            type="number"
            min={s.minimum}
            max={s.maximum}
            step={s.multipleOf || (s.type === "integer" ? 1 : "any")}
            value={value ?? ""}
            placeholder="(default)"
            onChange={(e) =>
              onChange(
                e.target.value === "" ? undefined : Number(e.target.value),
              )
            }
          />
        )}
      </>
    );
  } else {
    const numeric = s.type === "integer" || s.type === "number";
    editor = (
      <div className="scalar-input">
        <input
          id={id}
          aria-required={isRequired || undefined}
          aria-invalid={missingRequired || !!fieldError || undefined}
          className={missingRequired || fieldError ? "required-empty" : undefined}
          type={numeric ? "number" : "text"}
          value={
            displayedValue === null || displayedValue === undefined
              ? ""
              : typeof displayedValue === "object"
                ? JSON.stringify(displayedValue)
                : displayedValue
          }
          placeholder={
            value === undefined
              ? showDefaultValue ? s.default == null ? "(undefined)" : String(s.default) : "(default)"
              : value === null
                ? "(undefined)"
                : undefined
          }
          min={s.minimum}
          max={s.maximum}
          minLength={s.minLength}
          maxLength={s.maxLength}
          pattern={s.pattern}
          step={
            numeric
              ? s.multipleOf || (s.type === "integer" ? 1 : "any")
              : undefined
          }
          onChange={(e) => {
            const text = e.target.value;
            if (!text) onChange(numeric ? undefined : "");
            else if (numeric) onChange(Number(text));
            else if (!s.type) {
              try {
                onChange(JSON.parse(text));
              } catch {
                onChange(text);
              }
            } else onChange(text);
          }}
        />
        {reset}
        {model.nullable && (
          <button onClick={() => onChange(null)}>(undefined)</button>
        )}
      </div>
    );
  }
  return (
    <div className="field">
      <label htmlFor={id}>{fieldLabel}</label>
      {template ? <RunningHeadHelp label={label} codes={metadata.codes} />
        : <SettingHelp label={label}>{help}</SettingHelp>}
      {editor}
      {fieldError && <p className="field-error" role="alert">{fieldError}</p>}
      {template && value && !fieldError && <p className="hint" role="status">Valid header/footer template.</p>}
      {s.default !== undefined &&
        s.default !== null &&
        typeof s.default !== "object" && (
          <p className="hint">Default: {typeof s.default === "boolean" ? (s.default ? "Yes" : "No") : String(s.default)}.</p>
        )}
    </div>
  );
}
