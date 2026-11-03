import { useState } from "react";
import type { Value } from "./api";
import { Help, projectLabel } from "./BuilderControls";
import { SearchSelect } from "./SearchSelect";
export { SchemaField, resolve } from "./SchemaField";
export function Sources({
  label,
  projects,
  value,
  onChange,
  ordered = true,
}: {
  label: string;
  projects: Value[];
  value: string[];
  onChange: (v: string[]) => void;
  ordered?: boolean;
}) {
  const List = ordered ? "ol" : "ul";
  const help: Record<string, string> = {
    "Text priorities":
      "When a passage is available in more than one source, the compiler uses the first source in this list that contains it. Put your preferred edition first and other editions below it as fallbacks. Use the arrows to change the order.",
    "Translation priorities":
      "The compiler looks for a translation to place alongside each passage, trying these sources from top to bottom. The first matching translation is used. Adding a translation does not guarantee that it covers every passage.",
    "Instruction priorities":
      "Instructions explain how or when to recite a passage. When several sources provide instructions for the same passage, the compiler tries the sources in this order and uses the first match.",
    "Annotation sources":
      "Annotations include commentary, editorial notes and other explanations. All matching annotations from the sources you select are included; this list has no priority order. A source may not have notes for every passage.",
  };
  return (
    <section>
      <div className="source-heading">
        <h3>{label}</h3>
        <Help label={label}>{help[label]}</Help>
      </div>
      <List>
        {value.map((id, i) => (
          <li key={id}>
            <span>{projectLabel(projects.find((p) => p.id === id))}</span>
            <div>
              {ordered && (
                <>
                  <button
                    aria-label={`Move ${projectLabel(projects.find((p) => p.id === id))} earlier`}
                    disabled={!i}
                    onClick={() => {
                      const next = [...value];
                      [next[i - 1], next[i]] = [next[i], next[i - 1]];
                      onChange(next);
                    }}
                  >
                    ↑
                  </button>
                  <button
                    aria-label={`Move ${projectLabel(projects.find((p) => p.id === id))} later`}
                    disabled={i === value.length - 1}
                    onClick={() => {
                      const next = [...value];
                      [next[i + 1], next[i]] = [next[i], next[i + 1]];
                      onChange(next);
                    }}
                  >
                    ↓
                  </button>
                </>
              )}
              <button onClick={() => onChange(value.filter((x) => x !== id))}>
                Remove
              </button>
            </div>
          </li>
        ))}
      </List>
      <SearchSelect
        label={`Add ${label.toLowerCase()}`}
        options={projects
          .filter((p) => !value.includes(p.id))
          .map((p) => ({
            value: p.id,
            label: projectLabel(p),
            keywords: p.id,
          }))}
        clearAfterSelect
        onSelect={(id) => onChange([...value, id])}
      />
    </section>
  );
}
export function Declarations({
  registry,
  labels,
  value,
  onChange,
}: {
  registry: Value;
  labels: Value;
  value: Value;
  onChange: (v: Value) => void;
}) {
  const [openNames, setOpenNames] = useState<Record<string, string>>({});
  const update = (group: string, feature: string, next: Value) => {
    const result = { ...(value || {}) };
    const features = { ...(result[group] || {}) };
    if (next === undefined) delete features[feature];
    else features[feature] = next;
    result[group] = features;
    onChange(result);
  };
  return (
    <section>
      <h3>Customs, calendar & conditional text</h3>
      <p className="hint">
        Inherited leaves a choice unset. Undefined explicitly overrides a value
        with undefined. True and false are separate choices.
      </p>
      <select
        aria-label="Add setting group"
        value=""
        onChange={(e) => onChange({ ...value, [e.target.value]: {} })}
      >
        <option value="">Add a setting group…</option>
        {Object.keys(registry || {})
          .filter((g) => !Object.hasOwn(value || {}, g))
          .map((g) => (
            <option key={g} value={g}>
              {g.replace("opensiddur:", "")}
            </option>
          ))}
      </select>
      {Object.entries(value || {}).map(([group, entries]) => {
        const definition = registry?.[group] || {};
        const features = [
          ...new Set([
            ...Object.keys(definition.features || {}),
            ...Object.keys(entries as Value),
          ]),
        ];
        return (
          <details key={group} open>
            <summary>{group.replace("opensiddur:", "")}</summary>
            {definition.supplied === "derived" && (
              <p className="hint">
                Normally calculated from other settings; use these fields only
                to override the calculated result.
              </p>
            )}
            {features.map((feature) => {
              const kind =
                definition.features?.[feature] || definition.open?.value;
              const current = (entries as Value)[feature];
              const label =
                labels?.features?.[group]?.[feature]?.label || feature;
              const state =
                current === undefined
                  ? "inherit"
                  : current === null
                    ? "undefined"
                    : "set";
              const edit = (next: Value) => update(group, feature, next);
              return (
                <div className="field" key={feature}>
                  <label>
                    {label}
                    <select
                      aria-label={`${group} ${feature} state`}
                      value={
                        kind === "binary"
                          ? current === undefined
                            ? "inherit"
                            : current === null
                              ? "undefined"
                              : String(current)
                          : state
                      }
                      onChange={(e) =>
                        edit(
                          e.target.value === "inherit"
                            ? undefined
                            : e.target.value === "undefined"
                              ? null
                              : kind === "binary"
                                ? e.target.value === "true"
                                : kind?.numeric
                                  ? 0
                                  : "",
                        )
                      }
                    >
                      <option value="inherit">(default)</option>
                      <option value="undefined">Explicitly undefined</option>
                      {kind === "binary" ? (
                        <>
                          <option value="true">True</option>
                          <option value="false">False</option>
                        </>
                      ) : (
                        <option value="set">Set a value</option>
                      )}
                    </select>
                  </label>
                  {state === "set" &&
                    kind !== "binary" &&
                    (kind?.symbol?.values ? (
                      <select
                        aria-label={label}
                        value={current}
                        onChange={(e) => edit(e.target.value)}
                      >
                        {kind.symbol.values.map((v: string) => (
                          <option key={v}>{v}</option>
                        ))}
                      </select>
                    ) : kind?.numeric ? (
                      <input
                        aria-label={label}
                        type="number"
                        min={kind.numeric.min}
                        max={kind.numeric.max}
                        step={kind.numeric.integer === false ? "any" : 1}
                        value={current}
                        onChange={(e) =>
                          edit(
                            e.target.value === ""
                              ? null
                              : Number(e.target.value),
                          )
                        }
                      />
                    ) : (
                      <input
                        aria-label={label}
                        value={current}
                        onChange={(e) => edit(e.target.value)}
                      />
                    ))}
                </div>
              );
            })}
            {definition.open && (
              <div className="row">
                <input
                  aria-label={`Additional ${group} feature`}
                  placeholder="Additional feature name / condition URN"
                  value={openNames[group] || ""}
                  onChange={(e) =>
                    setOpenNames({ ...openNames, [group]: e.target.value })
                  }
                />
                <button
                  onClick={() => {
                    const key = openNames[group]?.trim();
                    if (key) update(group, key, null);
                  }}
                >
                  Add feature
                </button>
              </div>
            )}
            <button
              onClick={() => {
                const next = { ...value };
                delete next[group];
                onChange(next);
              }}
            >
              Remove group
            </button>
          </details>
        );
      })}
    </section>
  );
}
