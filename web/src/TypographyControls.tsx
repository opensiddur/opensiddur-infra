import React, { createContext } from "react";
import { Help } from "./BuilderControls";
export type FontGroup = { label: string; fonts: string[] };
export type FontCatalog = { installed: string[]; hebrew: FontGroup[]; latin: FontGroup[]; other: FontGroup[] };
export const TypographyMetadata = createContext<{ fonts?: FontCatalog; codes?: string[] }>({});

export function templateError(text: string, codes?: string[]): string | undefined {
  for (let i = 0; i < text.length;) {
    const char = text[i];
    if ((char === "{" || char === "}") && text[i + 1] === char) { i += 2; continue; }
    if (char === "{") {
      const end = text.indexOf("}", i + 1);
      if (end < 0) return 'Missing closing }. Use {{ for a literal opening brace.';
      const code = text.slice(i + 1, end);
      if (codes && !codes.includes(code)) return `Unknown placeholder {${code}}. Choose a supported placeholder from the help.`;
      i = end + 1;
    } else if (char === "}") return 'Unmatched }. Use }} for a literal closing brace.';
    else i++;
  }
}
export function runningHeadIssues(typography: any, codes?: string[]): string[] {
  const issues: string[] = [];
  for (const key of ["page_header", "page_footer"]) {
    const config = typography?.[key];
    if (!config || typeof config !== "object") continue;
    if (config.all != null && (config.odd != null || config.even != null))
      issues.push(`${key.replaceAll("_", " ")}: use all pages or odd/even pages, rather than both.`);
    for (const side of ["all", "odd", "even"]) for (const position of ["left", "center", "right"]) {
      const slot = config[side]?.[position];
      for (const [field, text] of typeof slot === "string" ? [["text", slot]] : [["text", slot?.text], ["if", slot?.if]]) {
        if (typeof text === "string") {
          const issue = templateError(text, codes);
          if (issue) issues.push(`${key.replaceAll("_", " ")} · ${side} · ${position} · ${field}: ${issue}`);
        }
      }
      if (slot?.language != null && !/^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{1,8})*$/.test(slot.language))
        issues.push(`${key.replaceAll("_", " ")} · ${side} · ${position}: use a language tag such as en or he.`);
    }
  }
  return issues;
}
const descriptions: Record<string, string> = {
  page: "Page number", "page-hebrew": "Page number in Hebrew letters",
  "document-title": "Document title", "book-title": "Current book title",
  "book-title-alt": "Book title from the other parallel column",
  "chapter-number": "Current chapter number", "chapter-number-hebrew": "Chapter number in Hebrew letters",
  "section-title": "Current section title", "section-title-alt": "Section title from the other parallel column",
};
export function RunningHeadHelp({ label, codes }: { label: string; codes?: string[] }) {
  return <Help label={label}>
    <p>Enter ordinary text, placeholders in braces, or a mixture. For example: <code>Page {"{page}"}</code> or <code>{"{section-title} · {page}"}</code>. Leave text empty for a blank slot. LaTeX formatting is not supported; use plain text and the placeholders below.</p>
    <p>Use <code>all</code> for every page, or <code>odd</code> and <code>even</code> for facing pages. Left, center and right are positions on the printed page.</p>
    <p><code>language</code>: use <code>en</code> for English or <code>he</code> for Hebrew. <code>if</code>: optionally enter a placeholder such as <code>{"{chapter-number}"}</code> to hide this slot when that value is empty.</p>
    <p>Write <code>{"{{"}</code> and <code>{"}}"}</code> for literal braces. Placeholders ending in <code>-alt</code> read the other parallel column and can be empty in a single-column book.</p>
    <ul>{(codes || []).map(code => <li key={code}><code>{`{${code}}`}</code> — {descriptions[code] || (/^head[1-4](-alt)?$/.test(code) ? `Heading level ${code[4]}${code.endsWith("-alt") ? " from the other column" : ""}` : "Supported running title value")}</li>)}</ul>
  </Help>;
}
export function FontSelect({ id, label, value, family, catalog, onChange, required }: {
  id: string; label: React.ReactNode; value?: string; family: string; catalog?: FontCatalog;
  onChange: (value: string | undefined) => void; required: boolean;
}) {
  const groups = !catalog ? [] : family === "hebrew" ? catalog.hebrew : family === "latin" ? catalog.latin : [...catalog.hebrew, ...catalog.latin, ...catalog.other];
  const seen = new Set<string>();
  const available = groups.flatMap(group => group.fonts);
  const unavailable = !!value && !available.includes(value);
  return <div className="field">
    <label htmlFor={id}>{label}</label>
    <select id={id} value={value || ""} disabled={!catalog} aria-required={required || undefined}
      onChange={e => onChange(e.target.value || undefined)}>
      <option value="">{required ? "Choose an installed font…" : "(default)"}</option>
      {unavailable && <option value={value} disabled>{value} (not offered in this font group)</option>}
      {groups.map(group => <optgroup key={group.label} label={group.label}>
        {group.fonts.filter(name => { if (seen.has(name)) return false; seen.add(name); return true; }).map(name => <option key={name} value={name}>{name}</option>)}
      </optgroup>)}
    </select>
    {unavailable && <p className="hint">This saved fallback is not offered here. Choose an installed font or remove this fallback entry.</p>}
    <p className="hint">Use the PDF preview to see these fonts.</p>
    {family === "hebrew" && <p className="hint">Consonant-only and historical fonts may omit vowel or cantillation marks. Choose the corresponding supported section for pointed Hebrew.</p>}
  </div>;
}
