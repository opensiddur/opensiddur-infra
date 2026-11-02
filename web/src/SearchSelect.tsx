import { useEffect, useId, useRef, useState } from "react";

export type SearchOption = { value: string; label: string; keywords?: string };
const normalize = (text: string) =>
  text.normalize("NFKD").replace(/\p{M}/gu, "").toLocaleLowerCase();
export function searchMatches(
  options: SearchOption[],
  query: string,
): SearchOption[] {
  const term = normalize(query.trim());
  const words = term.split(/\s+/).filter(Boolean);
  return options
    .map((option, index) => {
      const label = normalize(option.label);
      const text = label + " " + normalize(option.keywords || "");
      const score =
        !term || label.startsWith(term)
          ? 0
          : words.every((w) =>
                label.split(/\s+/).some((part) => part.startsWith(w)),
              )
            ? 1
            : label.includes(term)
              ? 2
              : 3;
      return { option, index, text, score };
    })
    .filter((item) => words.every((w) => item.text.includes(w)))
    .sort((a, b) => a.score - b.score || a.index - b.index)
    .map((item) => item.option);
}

/** One editable combobox used by every catalog/source search. Selection is explicit. */
export function SearchSelect({
  id,
  label,
  options,
  value = "",
  onSelect,
  disabled = false,
  clearAfterSelect = false,
  allowClear = false,
  labelClassName,
}: {
  id?: string;
  label: string;
  options: SearchOption[];
  value?: string;
  onSelect: (value: string) => void;
  disabled?: boolean;
  clearAfterSelect?: boolean;
  allowClear?: boolean;
  labelClassName?: string;
}) {
  const generated = useId();
  const inputId = id || generated;
  const listId = inputId + "-results";
  const selectedLabel = options.find((o) => o.value === value)?.label || "";
  const [query, setQuery] = useState(selectedLabel);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const matches = searchMatches(options, query === selectedLabel ? "" : query);
  const shown = matches.slice(0, 8);
  const current = Math.min(active, Math.max(0, shown.length - 1));
  useEffect(() => setQuery(selectedLabel), [value, selectedLabel]);
  useEffect(() => {
    if (open)
      listRef.current
        ?.querySelector('[aria-selected="true"]')
        ?.scrollIntoView({ block: "nearest" });
  }, [current, open, query]);
  function select(option: SearchOption) {
    onSelect(option.value);
    setQuery(clearAfterSelect ? "" : option.label);
    setOpen(false);
    setActive(0);
  }
  return (
    <div
      className="search-select"
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) {
          setOpen(false);
          setQuery(selectedLabel);
        }
      }}
    >
      <label htmlFor={inputId} className={labelClassName}>
        {label}
      </label>
      <div className="search-input">
        <input
          id={inputId}
          ref={inputRef}
          role="combobox"
          autoComplete="off"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={listId}
          aria-activedescendant={
            open && shown.length ? `${listId}-${current}` : undefined
          }
          disabled={disabled}
          value={query}
          placeholder="Search titles or editions…"
          onFocus={(e) => {
            setOpen(true);
            e.currentTarget.select();
          }}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
            setOpen(true);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
              e.preventDefault();
              setOpen(true);
              setActive(
                !open
                  ? e.key === "ArrowDown"
                    ? 0
                    : Math.max(0, shown.length - 1)
                  : (current +
                      (e.key === "ArrowDown" ? 1 : -1) +
                      Math.max(1, shown.length)) %
                      Math.max(1, shown.length),
              );
            } else if (e.key === "Enter" && open) {
              e.preventDefault();
              if (shown[current]) select(shown[current]);
            } else if (e.key === "Escape") {
              e.preventDefault();
              setOpen(false);
              setQuery(selectedLabel);
            } else if (e.key === "Tab") setOpen(false);
          }}
        />
        {allowClear && value && (
          <button
            type="button"
            className="search-clear"
            aria-label="Clear chosen title"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => {
              onSelect("");
              setQuery("");
              setOpen(true);
              inputRef.current?.focus();
            }}
          >
            ×
          </button>
        )}
        <button
          type="button"
          className="search-toggle"
          tabIndex={-1}
          disabled={disabled}
          aria-label={open ? `Hide ${label} results` : `Show ${label} results`}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => {
            inputRef.current?.focus();
            setOpen(!open);
          }}
        >
          ▾
        </button>
      </div>
      {open && (
        <div className="search-results">
          <ul
            role="listbox"
            id={listId}
            aria-label={`${label} matches`}
            ref={listRef}
          >
            {shown.map((option, i) => (
              <li
                role="option"
                id={`${listId}-${i}`}
                key={option.value}
                aria-selected={i === current}
                onMouseEnter={() => setActive(i)}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => select(option)}
              >
                {option.label}
              </li>
            ))}
          </ul>
          <p className="search-status" role="status">
            {matches.length
              ? `${matches.length} match${matches.length === 1 ? "" : "es"}${matches.length > shown.length ? "; showing the top 8. Keep typing to narrow the list." : "."}`
              : "No matching titles. Try another spelling."}
          </p>
        </div>
      )}
    </div>
  );
}
